#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _extract_text_with_pdftotext(pdf_path: Path) -> str:
    cmd = ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(pdf_path), "-"]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"pdftotext failed for {pdf_path.name}: {stderr}")
    return result.stdout.decode("utf-8", errors="replace")


def _extract_text_with_pymupdf(pdf_path: Path) -> str:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Text extraction backend not found. Install either:\n"
            "- poppler (`pdftotext`)\n"
            "- PyMuPDF (`pip install pymupdf`)"
        ) from exc

    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def extract_text(pdf_path: Path) -> tuple[str, str]:
    if shutil.which("pdftotext"):
        return _extract_text_with_pdftotext(pdf_path), "pdftotext"
    return _extract_text_with_pymupdf(pdf_path), "pymupdf"


def iter_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError("--input must be a .pdf file or a directory containing PDFs")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"--input not found: {input_path}")

    return sorted(input_path.rglob("*.pdf"))


_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_CITATION_RE = re.compile(
    r"(?P<journal>.+?)\s+(?P<year>20\d{2})\s*[:;]\s*(?P<volume>\d+)\s*\((?P<issue>[^)]+)\)\s*[:;]\s*(?P<pages>[A-Za-z]?\d+\s*[-–]\s*[A-Za-z]?\d+)",
    re.IGNORECASE,
)
_ARTICLE_TYPE_HINT_RE = re.compile(r"\b(case report|short case report)\b", re.IGNORECASE)
_FRONT_MATTER_STOP_RE = re.compile(r"^(abstract|introduction|background)\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    return text


def _extract_doi(text: str) -> str:
    match = _DOI_RE.search(text)
    return match.group(0) if match else ""


def _looks_like_affiliation_line(line: str) -> bool:
    if re.search(r"\b\d+\)\s+", line):
        return True
    if "department" in line.lower() and ("hospital" in line.lower() or "university" in line.lower()):
        return True
    return False


def _split_affiliations_from_line(line: str) -> list[str]:
    if not re.search(r"\b\d+\)\s+", line):
        return []
    parts = re.split(r"(?=\b\d+\)\s+)", line)
    return [p.strip() for p in parts if re.match(r"^\d+\)\s+", p.strip())]


def _find_citation(lines: list[str]) -> dict[str, str]:
    for line in lines[:200]:
        match = _CITATION_RE.search(line)
        if not match:
            continue
        return {
            "journal_name": match.group("journal").strip(),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": match.group("issue").strip(),
            "pages": re.sub(r"\s+", "", match.group("pages")),
        }
    return {}


def _extract_labeled_fields(text: str) -> dict[str, str]:
    raw_lines = [line.rstrip("\n") for line in text.split("\n")]
    front_lines: list[str] = []
    for raw in raw_lines[:250]:
        line = raw.strip()
        if not line:
            continue
        if _FRONT_MATTER_STOP_RE.match(line):
            break
        front_lines.append(line)

    label_re = re.compile(r"(?i)\b(Journal|Title|Type|Authors|Affiliations)\s*:\s*")
    extracted: dict[str, str] = {}
    for line in front_lines:
        matches = list(label_re.finditer(line))
        if not matches:
            continue

        for i, match in enumerate(matches):
            key = match.group(1).lower()
            value_start = match.end()
            value_end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            value = line[value_start:value_end].strip()
            if not value:
                continue
            if key == "journal":
                extracted.setdefault("journal_raw", value)
            elif key == "title":
                extracted.setdefault("title", value)
            elif key == "authors":
                extracted.setdefault("authors", value)
            elif key == "affiliations":
                extracted.setdefault("affiliations", value)

    return extracted


def _find_journal_name(lines: list[str]) -> str:
    for line in lines[:40]:
        if "journal" not in line.lower():
            continue
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.lower().startswith(("http://", "https://")):
            continue
        candidate = re.sub(r"https?://\S+", "", candidate).strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered.startswith("journal:"):
            continue
        if any(x in lowered for x in ["title:", "authors:", "author:", "affiliations:", "affiliation:"]):
            continue
        if candidate and "journal" in lowered:
            return candidate
    return ""


def _find_title(lines: list[str]) -> str:
    for i, line in enumerate(lines[:120]):
        if not _ARTICLE_TYPE_HINT_RE.search(line):
            continue
        for j in range(i + 1, min(i + 12, len(lines))):
            candidate = lines[j].strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if any(x in lowered for x in ["http", "doi", "creativecommons"]):
                continue
            if lowered.startswith(("abstract", "keywords", "references")):
                continue
            if _looks_like_affiliation_line(candidate):
                continue
            return candidate

    candidates: list[str] = []
    for line in lines[:80]:
        candidate = line.strip()
        if len(candidate) < 10:
            continue
        lowered = candidate.lower()
        if any(
            x in lowered
            for x in [
                "http",
                "doi",
                "creativecommons",
                "license",
                "received",
                "accepted",
                "conflict",
                "keywords",
                "abstract",
                "references",
            ]
        ):
            continue
        if _CITATION_RE.search(candidate):
            continue
        if _looks_like_affiliation_line(candidate):
            continue
        if candidate.isupper() and "journal" in lowered:
            continue
        candidates.append(candidate)

    if not candidates:
        return ""
    return max(candidates, key=lambda s: len(s))


def _find_authors(lines: list[str], title: str) -> str:
    authors_label_re = re.compile(r"^\s*authors?\s*:\s*(?P<authors>.+?)\s*$", re.IGNORECASE)
    for line in lines[:200]:
        match = authors_label_re.match(line)
        if match:
            return match.group("authors").strip()

    title_idx = -1
    for i, line in enumerate(lines[:200]):
        if title and line.strip() == title.strip():
            title_idx = i
            break

    search_start = title_idx + 1 if title_idx >= 0 else 0
    window = lines[search_start : search_start + 20]
    candidate_lines: list[str] = []
    for line in window:
        lowered = line.lower()
        if lowered.startswith(("abstract", "keywords")):
            break
        if any(x in lowered for x in ["received", "accepted", "conflict", "copyright", "creativecommons"]):
            break
        if _looks_like_affiliation_line(line) and any(
            k in lowered for k in ["department", "hospital", "university", "institute", "centre", "center", "clinic"]
        ):
            break
        candidate_lines.append(line.strip())

    raw = " ".join(part for part in candidate_lines if part)
    raw = _EMAIL_RE.sub("", raw)
    raw = re.sub(r"(?:\b\d+\)\s*)+", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -–—―")
    if raw and len(raw.split()) >= 2 and len(raw) <= 200:
        return raw

    for line in lines[search_start : search_start + 10]:
        candidate = line.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(
            x in lowered
            for x in ["department", "hospital", "university", "abstract", "keywords", "received", "accepted"]
        ):
            continue
        if re.search(r"\d", candidate) or re.search(r"\b\d+\)\b", candidate):
            continue
        if len(candidate.split()) < 2:
            continue
        if len(candidate) > 140:
            continue
        return candidate

    return ""


def _find_affiliations(lines: list[str]) -> str:
    collected: list[str] = []
    for line in lines[:250]:
        collected.extend(_split_affiliations_from_line(line))

    if not collected:
        for line in lines[:250]:
            if _looks_like_affiliation_line(line):
                collected.append(line.strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in collected:
        entry = re.sub(r"\s+", " ", entry).strip()
        if not entry or entry in seen:
            continue
        match = re.match(r"^(?P<num>\d+)\)\s+(?P<rest>.+)$", entry)
        if match:
            rest = match.group("rest").strip()
            rest_lower = rest.lower()
            if rest_lower.startswith("and "):
                continue
            if not any(
                k in rest_lower
                for k in [
                    "department",
                    "division",
                    "faculty",
                    "school",
                    "university",
                    "hospital",
                    "institute",
                    "centre",
                    "center",
                    "clinic",
                    "laboratory",
                    "research",
                ]
            ) and not ("," in rest and len(rest) >= 20):
                continue
        seen.add(entry)
        cleaned.append(entry)

    return " | ".join(cleaned)


def extract_metadata(text: str) -> dict[str, str]:
    text = _normalize_text(text)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    doi = _extract_doi(text)
    labeled = _extract_labeled_fields(text)

    citation: dict[str, str] = {}
    if labeled.get("journal_raw"):
        match = _CITATION_RE.search(labeled["journal_raw"])
        if match:
            citation = {
                "journal_name": match.group("journal").strip(),
                "year": match.group("year").strip(),
                "volume": match.group("volume").strip(),
                "issue": match.group("issue").strip(),
                "pages": re.sub(r"\s+", "", match.group("pages")),
            }
        else:
            citation = {}
    if not citation:
        citation = _find_citation(lines)

    journal_name = _find_journal_name(lines) or citation.get("journal_name", "")

    title = labeled.get("title") or _find_title(lines)

    labeled_authors = labeled.get("authors") or ""
    authors = labeled_authors or _find_authors(lines, title)

    labeled_aff = labeled.get("affiliations") or ""
    affiliations = labeled_aff or _find_affiliations(lines)

    return {
        "paper_title": title,
        "journal_name": journal_name,
        "year": citation.get("year", ""),
        "volume": citation.get("volume", ""),
        "issue": citation.get("issue", ""),
        "pages": citation.get("pages", ""),
        "authors": authors,
        "affiliations": affiliations,
        "doi": doi,
    }


def write_csv(rows: list[dict[str, str]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pdf_path",
        "txt_path",
        "paper_title",
        "journal_name",
        "year",
        "volume",
        "issue",
        "pages",
        "authors",
        "affiliations",
        "doi",
        "extracted_at",
        "extractor",
        "full_text",
    ]
    # Use UTF-8 with BOM so Excel (JP) opens without mojibake (Shift-JIS mis-detection).
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _pdf_states(pdfs: list[Path]) -> list[tuple[str, int, int]]:
    states: list[tuple[str, int, int]] = []
    for pdf_path in pdfs:
        try:
            stat = pdf_path.stat()
        except FileNotFoundError:
            continue
        states.append((str(pdf_path.resolve()), int(stat.st_size), int(stat.st_mtime_ns)))
    states.sort()
    return states


def process_pdfs(
    pdfs: list[Path],
    txt_out: Path,
    csv_out: Path | None,
    force: bool,
) -> None:
    if not pdfs:
        return

    txt_out.mkdir(parents=True, exist_ok=True)

    extracted_at = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
    rows: list[dict[str, str]] = []

    for pdf_path in pdfs:
        out_path = txt_out / f"{pdf_path.stem}.txt"
        wrote_txt = False
        if out_path.exists() and not force:
            if not csv_out:
                continue
            text = out_path.read_text(encoding="utf-8-sig", errors="replace")
            extractor = "txt-cache"
        else:
            text, extractor = extract_text(pdf_path)
            # UTF-8 with BOM improves compatibility with apps that otherwise assume Shift-JIS.
            out_path.write_text(text, encoding="utf-8-sig", newline="\n")
            wrote_txt = True

        metadata = extract_metadata(text)
        rows.append(
            {
                "pdf_path": str(pdf_path),
                "txt_path": str(out_path),
                "extracted_at": extracted_at,
                "extractor": extractor,
                "full_text": text,
                **metadata,
            }
        )
        if wrote_txt:
            print(out_path)

    if csv_out:
        write_csv(rows, csv_out)
        print(csv_out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract case-report PDFs into UTF-8 .txt and aggregate metadata + full text into a CSV."
    )
    parser.add_argument("--input", type=Path, required=True, help="PDF file or directory")
    parser.add_argument(
        "--txt-out",
        type=Path,
        required=True,
        help="Output directory for UTF-8 text files",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        help="Output CSV path (includes metadata + full text)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .txt files",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch a directory and re-run when PDFs change",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Polling interval seconds for --watch (default: 10)",
    )
    args = parser.parse_args(argv)

    if args.watch and args.input.is_file():
        raise SystemExit("--watch requires --input to be a directory")

    if args.watch and not args.input.exists():
        args.input.mkdir(parents=True, exist_ok=True)

    if not args.watch:
        pdfs = iter_pdfs(args.input)
        if not pdfs:
            raise SystemExit("No PDFs found.")
        process_pdfs(pdfs, args.txt_out, args.csv_out, args.force)
        return 0

    print(f"Watching: {args.input} (interval={args.interval}s)")
    last_states: list[tuple[str, int, int]] | None = None
    try:
        while True:
            pdfs = iter_pdfs(args.input)
            states = _pdf_states(pdfs)
            if last_states is None:
                last_states = states
                if pdfs:
                    process_pdfs(pdfs, args.txt_out, args.csv_out, args.force)
            elif states != last_states:
                last_states = states
                process_pdfs(pdfs, args.txt_out, args.csv_out, args.force)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
