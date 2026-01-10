#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def iter_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError("--input must be a .pdf file or a directory containing PDFs")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"--input not found: {input_path}")

    pdfs: list[Path] = []
    for path in input_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".pdf":
            continue
        pdfs.append(path)
    return sorted(pdfs)


def _output_paths_for_pdf(pdf_path: Path, input_root: Path, txt_out: Path) -> tuple[Path, Path]:
    try:
        rel = pdf_path.relative_to(input_root)
    except ValueError:
        rel = Path(pdf_path.name)
    out_path = (txt_out / rel).with_suffix(".txt")
    meta_path = out_path.with_suffix(".meta.json")
    return out_path, meta_path


def _sync_txt_outputs(txt_out: Path, keep_files: set[Path]) -> None:
    if not txt_out.exists():
        return
    keep_files = {p.resolve() for p in keep_files}
    for path in txt_out.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if not (name.endswith(".txt") or name.endswith(".meta.json")):
            continue
        if path.resolve() in keep_files:
            continue
        try:
            path.unlink()
        except OSError:
            pass

    for directory in sorted([p for p in txt_out.rglob("*") if p.is_dir()], reverse=True):
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            continue


_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_CITATION_RE = re.compile(
    r"(?P<journal>.+?)\s+(?P<year>20\d{2})\s*[:;]\s*(?P<volume>\d+)\s*\((?P<issue>[^)]+)\)\s*[:;]\s*(?P<pages>[A-Za-z]?\d+\s*[-–]\s*[A-Za-z]?\d+)",
    re.IGNORECASE,
)
_CITATION_VOL_PAGES_YEAR_RE = re.compile(
    r"(?P<journal>.+?)\s+(?P<volume>\d+)(?:\s*\((?P<issue>[^)]+)\))?\s*[:;]\s*(?P<pages>[A-Za-z]?\d+\s*[-–]\s*[A-Za-z]?\d+)\s*,\s*(?P<year>20\d{2})",
    re.IGNORECASE,
)
_VOL_NO_PAGES_RE = re.compile(
    r"(?P<journal>.+)\s+(?P<year>20\d{2})\s*,?\s*vol\.?\s*(?P<volume>\d+)\s*,?\s*no\.?\s*(?P<issue>\d+)(?:\s*,?\s*p(?:p)?\.?\s*(?P<pages>\d+\s*[-–]\s*\d+))?",
    re.IGNORECASE,
)
_ARTICLE_TYPE_HINT_RE = re.compile(r"\b(case report|short case report)\b", re.IGNORECASE)
_FRONT_MATTER_STOP_RE = re.compile(r"^(abstract|introduction|background)\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"^https?://doi\.org/\S+$", re.IGNORECASE)
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_CAPTION_START_RE = re.compile(r"^(?:figure|table)\s*\d+\s*[.:]\s+\S+", re.IGNORECASE)
_CASE_START_RE = re.compile(r"\b(?:A|An)\s+\d{1,3}\s*[-–]?\s*year[- ]old\b", re.IGNORECASE)
_FIGURE_CAPTION_START_RE = re.compile(r"^(?:figure|fig\.?)\s*\d+\s*[.:]\s+\S+", re.IGNORECASE)
_FIGURE_PANEL_LABEL_RE = re.compile(r"^\d{0,2}[A-Z]{1,2}\d{0,2}$")

_HYPHEN_CHARS = "-\u2010\u2011\u00ad"
_HYPHEN_LINEBREAK_RE = re.compile(rf"(?P<left>[A-Za-z0-9]{{1,}})[{_HYPHEN_CHARS}]\n\s*(?P<right>[A-Za-z0-9]{{1,}})")
_KEEP_HYPHEN_LEFT = {
    "life",
    "long",
    "short",
    "high",
    "low",
    "well",
}
_COMMON_SUFFIXES = {
    "a",
    "able",
    "al",
    "ally",
    "ation",
    "ations",
    "ed",
    "er",
    "ers",
    "es",
    "est",
    "ful",
    "ically",
    "ic",
    "ics",
    "ing",
    "ion",
    "ions",
    "ism",
    "ist",
    "ists",
    "ity",
    "ities",
    "ive",
    "ize",
    "ized",
    "izes",
    "izing",
    "less",
    "ly",
    "ment",
    "ments",
    "ness",
    "ous",
    "s",
    "tion",
    "tions",
    # medical-ish suffixes
    "emia",
    "itis",
    "logy",
    "mography",
    "opathy",
    "osis",
    "scopy",
    "titis",
    "uria",
}

_KNOWN_HEADINGS = {
    "abstract",
    "acknowledgments",
    "acknowledgements",
    "article information",
    "author contributions",
    "background",
    "case presentation",
    "case report",
    "conclusion",
    "conflicts of interest",
    "discussion",
    "figure captions",
    "introduction",
    "keywords",
    "key words",
    "main text",
    "references",
    "results",
}


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    # Normalize fullwidth digits so regexes can match across PDF extractors.
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return text


def _fix_common_mojibake(text: str) -> str:
    # Some PDFs (font maps) mis-extract the multiplication sign "×" as "©".
    # Fix only in numeric contexts to avoid touching copyright marks.
    text = re.sub(r"(?<=\d)\s*©\s*(?=\d)", " × ", text)

    def replace_multiply_symbol(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        number = match.group("number")
        if len(number) == 4 and number.startswith(("19", "20")):
            return match.group(0)
        return f"{prefix}×{number}"

    text = re.sub(r"(?P<prefix>[\s(,])©\s*(?P<number>\d{1,4})", replace_multiply_symbol, text)
    def replace_leading_multiply_symbol(match: re.Match[str]) -> str:
        number = match.group("number")
        if len(number) == 4 and number.startswith(("19", "20")):
            return match.group(0)
        return f"×{number}"

    text = re.sub(r"^©\s*(?P<number>\d{1,4})", replace_leading_multiply_symbol, text)

    # Common lab notation: "×10^3/µL" sometimes becomes "× 103/µL" (caret lost).
    text = re.sub(
        r"×\s*10\s*(?P<exp>\d)\s*/\s*(?P<unit>[µμ]L)\b",
        r"× 10^\g<exp>/\g<unit>",
        text,
    )
    text = re.sub(
        r"×\s*10\s*(?P<exp>\d)\s*/\s*(?P<unit>L)\b",
        r"× 10^\g<exp>/\g<unit>",
        text,
    )
    return text


def _extract_doi(text: str) -> str:
    match = _DOI_RE.search(text)
    return match.group(0) if match else ""

def _fix_hyphen_linebreaks(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        left = match.group("left")
        right = match.group("right")
        left_lower = left.lower()
        right_lower = right.lower()

        if any(ch.isdigit() for ch in left):
            return f"{left}-{right}"
        if left_lower in _KEEP_HYPHEN_LEFT:
            return f"{left}-{right}"
        if right_lower in _COMMON_SUFFIXES:
            return f"{left}{right}"
        return f"{left}{right}"

    return _HYPHEN_LINEBREAK_RE.sub(repl, text)


def _is_heading_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip()).strip(":：").lower()
    if not normalized:
        return False
    if normalized in _KNOWN_HEADINGS:
        return True
    if normalized.startswith(("figure ", "table ")):
        return True
    if len(normalized) <= 30 and normalized.isupper():
        return True
    return False


def _is_layout_noise_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    if lowered.startswith("corresponding author:"):
        return True
    if lowered.startswith(("e-mail:", "email:")):
        return True
    if lowered.startswith(("received for publication", "received for")):
        return True
    if lowered.startswith(("received:", "accepted:", "copyright")):
        return True
    if lowered.startswith(("©", "(c)")):
        return True
    if re.fullmatch(r"[—–-]\s*\d{1,4}\s*[—–-]", line.strip()):
        return True
    if lowered.startswith("this is an open access journal distributed"):
        return True
    if "creativecommons.org" in lowered or "creative commons" in lowered:
        return True
    return False


def _looks_like_repeated_header_line(line: str) -> bool:
    if _DOI_URL_RE.match(line) or _URL_RE.match(line):
        return True
    if _PAGE_NUMBER_RE.match(line):
        return True
    if re.match(r"(?i)^doi:\s*10\.\d{4,9}/\S+$", line.strip()):
        return True
    match = _CITATION_RE.fullmatch(line)
    if match and len(line) <= 120 and not line.rstrip().endswith("."):
        return True
    match = _CITATION_VOL_PAGES_YEAR_RE.fullmatch(line)
    if match and len(line) <= 120 and not line.rstrip().endswith("."):
        return True
    return False


def _canonical_heading(line: str) -> str:
    line = re.sub(r"\s+", " ", line.strip())
    if not line:
        return ""
    lowered = line.strip(":：").lower()
    if lowered in _KNOWN_HEADINGS:
        return lowered
    match = re.match(
        r"(?i)^(abstract|introduction|background|keywords|key words|case presentation|case report|discussion|references|conclusion|acknowledgements|acknowledgments)\b",
        line,
    )
    if not match:
        return ""
    return match.group(1).lower()


def _clean_journal_name(journal_raw: str) -> str:
    journal = re.sub(r"\s+", " ", journal_raw).strip().strip(" .;,:-–—")
    if not journal:
        return ""
    lowered = journal.lower()
    last_journal = lowered.rfind("journal")
    if last_journal != -1:
        journal = journal[last_journal:].strip()
    journal = re.sub(r"^(?:©|\(c\)|copyright)\s*\d{4}\s*", "", journal, flags=re.IGNORECASE).strip()
    return journal.strip(" .;,:-–—")


def _should_resume_after_caption(line: str, paragraph: list[str], previous_text: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    if _CASE_START_RE.match(line):
        return True
    if lowered.startswith(("the patient", "he ", "she ", "they ", "we ")):
        return True
    tail = paragraph[-1].strip() if paragraph else previous_text.strip()
    preposition_tail = bool(
        tail and re.search(r"(?i)\b(in|of|to|for|with|without|by|as|at|from|during|on)\s*$", tail)
    )
    if tail and not preposition_tail and _should_join_soft_break(tail, line):
        return True
    if preposition_tail and re.match(r"(?i)^(the|a|an)\b", lowered):
        return True
    return False


def _should_join_soft_break(prev: str, nxt: str) -> bool:
    prev = prev.strip()
    nxt = nxt.strip()
    if not prev or not nxt:
        return False
    if _is_heading_line(prev) or _is_heading_line(nxt):
        return False
    if prev.endswith((".", "!", "?", ":", ";")):
        return False
    if re.match(r"^[a-z]", nxt):
        return True
    if re.search(r"(?i)\b(in|of|to|for|with|without|by|as|at|from|during|on)\s*$", prev) and re.match(
        r"(?i)^(the|a|an)\b", nxt
    ):
        return True
    return False


def _join_soft_paragraph_breaks(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "" and out and i + 1 < len(lines) and lines[i + 1] != "":
            prev = out[-1]
            nxt = lines[i + 1]
            if _should_join_soft_break(prev, nxt):
                out[-1] = f"{prev.rstrip()} {nxt.lstrip()}".strip()
                i += 2
                continue
        out.append(line)
        i += 1

    deduped: list[str] = []
    blank_pending = False
    for line in out:
        if line == "":
            blank_pending = True
            continue
        if blank_pending and deduped:
            deduped.append("")
        blank_pending = False
        deduped.append(line)
    return deduped


def clean_extracted_text(text: str) -> str:
    text = _normalize_text(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    # Some extractors emit control characters for symbols (e.g., "≥").
    text = text.replace("\x02", "≥")
    text = _fix_common_mojibake(text)
    text = _fix_hyphen_linebreaks(text)

    raw_lines = [line.rstrip() for line in text.split("\n")]
    counts: dict[str, int] = {}
    for raw in raw_lines:
        normalized = re.sub(r"\s+", " ", raw.strip())
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1

    out_lines: list[str] = []
    paragraph: list[str] = []
    last_emitted = ""
    in_front_matter = True
    front_matter_budget = 80
    in_caption_block = False
    caption_budget = 0
    in_correspondence_block = False
    correspondence_budget = 0
    in_affiliation_block = False
    affiliation_budget = 0
    seen_deduped: set[str] = set()

    def _front_matter_ended_by_heading(line: str) -> bool:
        normalized = re.sub(r"\s+", " ", line.strip()).strip(":：").lower()
        return normalized in {
            "abstract",
            "introduction",
            "background",
            "case presentation",
            "case report",
            "main text",
        }

    def flush_paragraph() -> None:
        nonlocal paragraph
        nonlocal last_emitted
        if not paragraph:
            return
        merged = " ".join(part.strip() for part in paragraph if part.strip())
        merged = re.sub(r"\s+", " ", merged).strip()
        if merged:
            out_lines.append(merged)
            last_emitted = merged
        paragraph = []

    def add_blank_line() -> None:
        if out_lines and out_lines[-1] != "":
            out_lines.append("")

    def _is_correspondence_start(line: str) -> bool:
        lowered = line.strip().lower()
        return lowered.startswith(("corresponding author:", "correspondence:", "correspondence to"))

    def _is_correspondence_noise(line: str) -> bool:
        lowered = line.strip().lower()
        if not lowered:
            return False
        if _is_layout_noise_line(line):
            return True
        if "e-mail" in lowered or "email" in lowered or _EMAIL_RE.search(line):
            return True
        if lowered in {"japan", "u.s.a.", "usa", "united states", "u.k.", "uk"}:
            return True
        if lowered.startswith(
            (
                "department",
                "division",
                "section",
                "unit",
                "faculty",
                "school",
                "university",
                "hospital",
                "medical center",
                "medical centre",
                "centre",
                "center",
                "clinic",
                "institute",
                "laboratory",
            )
        ):
            return True
        if "journal" in lowered and len(line) <= 120:
            return True
        if re.match(r"^20\d{2}\s*,?\s*vol\.?\s*\d+\b", lowered) or (
            "vol" in lowered and "no" in lowered and re.search(r"\b20\d{2}\b", lowered)
        ):
            return True
        if lowered in {"case reports", "case report"}:
            return True
        if re.search(r"(?:[—–-]\s*\d{1,4}\s*[—–-])\s*$", line.strip()):
            return True
        return False

    for raw_line in raw_lines:
        line = raw_line.strip()
        line = re.sub(r"\s+", " ", line).strip()

        if in_correspondence_block:
            if not line:
                in_correspondence_block = False
            elif _is_correspondence_noise(line):
                correspondence_budget -= 1
                if correspondence_budget <= 0:
                    in_correspondence_block = False
                continue
            else:
                in_correspondence_block = False

        if in_affiliation_block:
            if not line:
                in_affiliation_block = False
            else:
                lowered = line.lower()
                if (
                    affiliation_budget > 0
                    and len(line) <= 160
                    and not line.endswith(".")
                    and any(
                        k in lowered
                        for k in [
                            "department",
                            "division",
                            "faculty",
                            "school",
                            "university",
                            "hospital",
                            "medical center",
                            "medical centre",
                            "centre",
                            "center",
                            "clinic",
                            "clinical",
                            "institute",
                            "laboratory",
                            "program",
                            "japan",
                        ]
                    )
                ):
                    affiliation_budget -= 1
                    if affiliation_budget <= 0:
                        in_affiliation_block = False
                    continue
                in_affiliation_block = False

        if in_caption_block:
            if not line:
                in_caption_block = False
                continue
            if _CAPTION_START_RE.match(line):
                caption_budget = 30
                continue
            if _should_resume_after_caption(line, paragraph, last_emitted):
                in_caption_block = False
            else:
                caption_budget -= 1
                if caption_budget <= 0:
                    in_caption_block = False
                continue

        if not line:
            flush_paragraph()
            add_blank_line()
            continue

        if _PAGE_NUMBER_RE.match(line):
            continue

        if not in_front_matter and re.match(r"(?i)^doi:\s*10\.", line):
            continue

        if not in_front_matter and _looks_like_affiliation_line(line):
            flush_paragraph()
            in_affiliation_block = True
            affiliation_budget = 6
            continue

        if _is_correspondence_start(line):
            in_correspondence_block = True
            correspondence_budget = 30
            continue

        if _is_layout_noise_line(line):
            continue

        if counts.get(line, 0) >= 2 and _looks_like_repeated_header_line(line):
            if line in seen_deduped:
                continue
            seen_deduped.add(line)
            flush_paragraph()
            out_lines.append(line)
            last_emitted = line
            continue

        if not in_front_matter and _CAPTION_START_RE.match(line):
            in_caption_block = True
            caption_budget = 30
            continue

        if _URL_RE.match(line) or _DOI_URL_RE.match(line) or _PAGE_NUMBER_RE.match(line):
            flush_paragraph()
            out_lines.append(line)
            last_emitted = line
            continue

        if _is_heading_line(line):
            flush_paragraph()
            add_blank_line()
            out_lines.append(line)
            add_blank_line()
            if in_front_matter and _front_matter_ended_by_heading(line):
                in_front_matter = False
            continue

        if in_front_matter:
            front_matter_budget -= 1
            if front_matter_budget <= 0:
                in_front_matter = False
            flush_paragraph()
            out_lines.append(re.sub(r"\s+", " ", line).strip())
            continue

        paragraph.append(line)

    flush_paragraph()

    cleaned: list[str] = []
    blank_pending = False
    for line in out_lines:
        if line == "":
            blank_pending = True
            continue
        if blank_pending and cleaned:
            cleaned.append("")
        blank_pending = False
        cleaned.append(line)

    cleaned = _join_soft_paragraph_breaks(cleaned)

    return "\n".join(cleaned).strip() + "\n"


def extract_figure_legends(text: str) -> str:
    text = _normalize_text(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = text.replace("\x02", "≥")
    text = _fix_common_mojibake(text)
    text = _fix_hyphen_linebreaks(text)

    raw_lines = [line.rstrip() for line in text.split("\n")]
    counts: dict[str, int] = {}
    for raw in raw_lines:
        normalized = re.sub(r"\s+", " ", raw.strip())
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1

    legends: list[str] = []
    current: list[str] = []

    paragraph: list[str] = []
    last_emitted = ""
    seen_deduped: set[str] = set()
    in_caption_block = False
    caption_budget = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        nonlocal last_emitted
        if not paragraph:
            return
        merged = " ".join(part.strip() for part in paragraph if part.strip())
        merged = re.sub(r"\s+", " ", merged).strip()
        if merged:
            last_emitted = merged
        paragraph = []

    def flush_caption() -> None:
        nonlocal current
        if not current:
            return
        merged = " ".join(part.strip() for part in current if part.strip())
        merged = re.sub(r"\s+", " ", merged).strip()
        if merged:
            legends.append(merged)
        current = []

    for raw_line in raw_lines:
        line = re.sub(r"\s+", " ", raw_line.strip()).strip()

        if in_caption_block:
            if not line:
                flush_caption()
                in_caption_block = False
                continue
            if _FIGURE_CAPTION_START_RE.match(line):
                flush_caption()
                current = [line]
                caption_budget = 40
                continue
            if len(line) <= 3 and _FIGURE_PANEL_LABEL_RE.fullmatch(line):
                continue
            if _is_heading_line(line):
                flush_caption()
                in_caption_block = False
                continue
            if _should_resume_after_caption(line, paragraph, last_emitted):
                flush_caption()
                in_caption_block = False
            else:
                caption_budget -= 1
                if caption_budget <= 0:
                    flush_caption()
                    in_caption_block = False
                    continue
                lowered = line.lower()
                if _URL_RE.match(line) or _DOI_URL_RE.match(line) or _PAGE_NUMBER_RE.match(line):
                    continue
                if counts.get(line, 0) >= 2 and _looks_like_repeated_header_line(line):
                    continue
                if _is_layout_noise_line(line):
                    continue
                if lowered.startswith(("http://", "https://", "doi:")):
                    continue
                current.append(line)
                continue

        if not line:
            flush_paragraph()
            continue

        if _FIGURE_CAPTION_START_RE.match(line):
            in_caption_block = True
            caption_budget = 40
            current = [line]
            continue

        if _URL_RE.match(line) or _DOI_URL_RE.match(line) or _PAGE_NUMBER_RE.match(line):
            flush_paragraph()
            continue

        if _is_layout_noise_line(line):
            continue

        if counts.get(line, 0) >= 2 and _looks_like_repeated_header_line(line):
            if line in seen_deduped:
                continue
            seen_deduped.add(line)
            flush_paragraph()
            last_emitted = line
            continue

        if _is_heading_line(line):
            flush_paragraph()
            continue

        paragraph.append(line)

    flush_paragraph()
    flush_caption()

    legends = _dedupe_keep_order(legends)
    return "\n\n".join(legends).strip()


def _looks_like_affiliation_line(line: str) -> bool:
    if re.search(r"^\s*\d+\)\s+", line):
        return True
    lowered = line.lower()
    if re.match(
        r"^\s*\d+\s*(?:\)|[).]|,)?\s*(?:department|division|faculty|school|university|hospital|medical center|medical centre|centre|center|clinic|clinical|institute|laboratory|unit|program)\b",
        lowered,
    ):
        return True
    if "department" in lowered and any(
        k in lowered
        for k in [
            "hospital",
            "university",
            "medical center",
            "medical centre",
            "centre",
            "center",
            "clinic",
            "institute",
        ]
    ):
        return True
    return False


def _looks_like_author_line(line: str) -> bool:
    line = line.strip()
    if not line or _looks_like_affiliation_line(line):
        return False
    lowered = line.lower()
    if re.search(r"(?i)\b(md|phd|m\.d\.|msc|m\.sc\.|ms)\b", line):
        return True
    if "," in line:
        name_like = re.findall(r"\b[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3}\b", line)
        if len(name_like) >= 2:
            return True
    if " and " in lowered:
        return True
    if len(line) <= 60 and re.fullmatch(r"[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3}", line):
        return True
    return False


def _split_affiliations_from_line(line: str) -> list[str]:
    line = line.strip()
    if not re.search(r"\b\d+\)\s+", line):
        return []
    lowered = line.lower()
    if "affiliat" not in lowered and not re.match(r"^\d+\)\s+", line):
        return []
    parts = re.split(r"(?=\b\d+\)\s+)", line)
    return [p.strip() for p in parts if re.match(r"^\d+\)\s+", p.strip())]


def _find_citation(lines: list[str]) -> dict[str, str]:
    ref_idx = -1
    for i, line in enumerate(lines):
        if _canonical_heading(line) == "references":
            ref_idx = i
            break
    search_lines = lines[:ref_idx] if ref_idx != -1 else lines

    def iter_candidates(lines_in: list[str]) -> list[str]:
        candidates: list[str] = []
        candidates.extend(lines_in)
        for i in range(len(lines_in) - 1):
            candidates.append(f"{lines_in[i]} {lines_in[i + 1]}")
        return candidates

    primary_lines = search_lines[:250]
    candidates = iter_candidates(primary_lines)
    for candidate in candidates:
        match = _VOL_NO_PAGES_RE.search(candidate)
        if not match:
            continue
        pages = match.group("pages") or ""
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": match.group("issue").strip(),
            "pages": re.sub(r"\s+", "", pages),
        }

    for candidate in candidates:
        match = _CITATION_VOL_PAGES_YEAR_RE.search(candidate)
        if not match:
            continue
        issue = (match.group("issue") or "").strip()
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": issue,
            "pages": re.sub(r"\s+", "", match.group("pages")),
        }

    for candidate in candidates:
        match = _CITATION_RE.search(candidate)
        if not match:
            continue
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": match.group("issue").strip(),
            "pages": re.sub(r"\s+", "", match.group("pages")),
        }

    candidates = iter_candidates(search_lines)
    for candidate in candidates:
        match = _VOL_NO_PAGES_RE.search(candidate)
        if not match:
            continue
        pages = match.group("pages") or ""
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": match.group("issue").strip(),
            "pages": re.sub(r"\s+", "", pages),
        }

    for candidate in candidates:
        match = _CITATION_VOL_PAGES_YEAR_RE.search(candidate)
        if not match:
            continue
        issue = (match.group("issue") or "").strip()
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
            "year": match.group("year").strip(),
            "volume": match.group("volume").strip(),
            "issue": issue,
            "pages": re.sub(r"\s+", "", match.group("pages")),
        }

    for candidate in candidates:
        match = _CITATION_RE.search(candidate)
        if not match:
            continue
        return {
            "journal_name": _clean_journal_name(match.group("journal")),
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
        if len(candidate) > 120:
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
        title_lines: list[str] = []
        for j in range(i + 1, min(i + 20, len(lines))):
            candidate = lines[j].strip()
            if not candidate:
                if title_lines:
                    break
                continue
            lowered = candidate.lower()
            if any(x in lowered for x in ["http", "doi", "creativecommons"]):
                continue
            if lowered.startswith(("abstract", "keywords", "references")):
                break
            if _looks_like_affiliation_line(candidate):
                if title_lines:
                    break
                continue
            if _looks_like_author_line(candidate):
                if title_lines:
                    break
                continue
            if _canonical_heading(candidate) in {"abstract", "introduction", "background", "keywords", "references"}:
                break
            if len(candidate) > 200:
                if title_lines:
                    break
                continue
            title_lines.append(candidate)
            if len(title_lines) >= 6:
                break
        if title_lines:
            merged = re.sub(r"\s+", " ", " ".join(title_lines)).strip()
            if len(merged) >= 10:
                return merged

    stop_idx = len(lines)
    for i, line in enumerate(lines[:60]):
        heading = _canonical_heading(line)
        if heading in {
            "abstract",
            "introduction",
            "background",
            "case presentation",
            "case report",
            "keywords",
            "key words",
            "main text",
        }:
            stop_idx = i
            break
        if _looks_like_affiliation_line(line):
            stop_idx = i
            break

    pool = lines[:stop_idx] if stop_idx > 0 else lines[:60]
    title_lines: list[str] = []
    started = False
    for line in pool:
        candidate = line.strip()
        if not candidate:
            if started:
                break
            continue
        lowered = candidate.lower()
        if any(x in lowered for x in ["http", "doi", "creativecommons", "license"]):
            continue
        if candidate.isupper() and "journal" in lowered:
            continue
        if _ARTICLE_TYPE_HINT_RE.search(candidate):
            continue
        if _looks_like_author_line(candidate):
            if started:
                break
            continue
        if len(candidate) > 200:
            if started:
                break
            continue
        title_lines.append(candidate)
        started = True
        if len(title_lines) >= 3:
            break

    if title_lines:
        merged = re.sub(r"\s+", " ", " ".join(title_lines)).strip()
        if len(merged) >= 10:
            return merged

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
    if title_idx < 0 and title:
        title_lower = title.lower()
        for i, line in enumerate(lines[:200]):
            candidate = line.strip()
            if len(candidate) < 10:
                continue
            if candidate.lower() in title_lower:
                title_idx = i
                break

    search_start = title_idx + 1 if title_idx >= 0 else 0
    window = lines[search_start : search_start + 20]
    candidate_lines: list[str] = []
    for line in window:
        trimmed = line.strip()
        if title and len(trimmed) >= 10 and trimmed.lower() in title.lower():
            continue
        lowered = trimmed.lower()
        if any(x in lowered for x in ["http", "doi"]):
            continue
        if _ARTICLE_TYPE_HINT_RE.search(trimmed):
            continue
        if lowered.startswith(("abstract", "keywords")):
            break
        if any(x in lowered for x in ["received", "accepted", "conflict", "copyright", "creativecommons"]):
            break
        if _looks_like_affiliation_line(line) and any(
            k in lowered
            for k in [
                "department",
                "hospital",
                "university",
                "medical center",
                "medical centre",
                "institute",
                "centre",
                "center",
                "clinic",
            ]
        ):
            break
        candidate_lines.append(trimmed)

    raw = " ".join(part for part in candidate_lines if part)
    raw = _EMAIL_RE.sub("", raw)
    raw = re.sub(r"(?:\b\d+\)\s*)+", "", raw)
    raw = re.sub(r"\d+", "", raw)
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

def _extract_first_author(authors: str) -> str:
    authors = re.sub(r"\s+", " ", authors).strip()
    if not authors:
        return ""
    if "," in authors:
        return authors.split(",", 1)[0].strip().strip(",;")
    match = re.split(r"\s+(?:and|&)\s+", authors, maxsplit=1, flags=re.IGNORECASE)
    if match and match[0] and match[0] != authors:
        return match[0].strip().strip(",;")
    if ";" in authors:
        return authors.split(";", 1)[0].strip().strip(",;")
    if "," in authors:
        return authors.split(",", 1)[0].strip().strip(",;")
    return authors.strip().strip(",;")


def _parse_affiliations_map(affiliations: str) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for part in affiliations.split("|"):
        part = part.strip()
        match = re.match(r"^(?P<num>\d+)\)\s+(?P<rest>.+)$", part)
        if not match:
            continue
        mapping[int(match.group("num"))] = match.group("rest").strip()
    return mapping


def _extract_first_author_aff_nums(text: str, title: str, first_author: str) -> list[int]:
    if not first_author:
        return []
    text = _normalize_text(text)
    lines = [line.strip() for line in text.split("\n")]

    title_idx = -1
    for i, line in enumerate(lines[:300]):
        if title and line.strip() == title.strip():
            title_idx = i
            break

    author_block_lines: list[str] = []
    if title_idx >= 0:
        for line in lines[title_idx + 1 : title_idx + 30]:
            if not line:
                continue
            lowered = line.lower().strip(":：")
            if lowered in _KNOWN_HEADINGS:
                break
            if re.match(r"^\d+\)\s+.+", line) and any(
                k in lowered for k in ["department", "hospital", "university", "institute", "centre", "center", "clinic"]
            ):
                break
            author_block_lines.append(line)

    search_text = " ".join(author_block_lines) if author_block_lines else " ".join(lines[:200])
    search_text = _EMAIL_RE.sub("", search_text)
    search_text = re.sub(r"\s+", " ", search_text).strip()

    pattern = re.compile(
        rf"(?i){re.escape(first_author)}\s*(?P<nums>(?:\d+\s*\)?\s*)+)"
    )
    match = pattern.search(search_text)
    if not match:
        return []
    nums = [int(n) for n in re.findall(r"\d+", match.group("nums"))]
    deduped: list[int] = []
    for n in nums:
        if n not in deduped:
            deduped.append(n)
    return deduped


def _infer_specialties_from_affiliations(affiliations_text: str) -> str:
    specialties: list[str] = []
    for aff in [a.strip() for a in affiliations_text.split("|") if a.strip()]:
        match = re.search(r"(?i)\b(?:Department|Division|Section|Unit)\s+of\s+([^,]+)", aff)
        if match:
            specialties.append(match.group(1).strip())
            continue
        match = re.search(r"(?i)\b([^,]+?)\s+Department\b", aff)
        if match:
            specialties.append(match.group(1).strip())
            continue
    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specialties:
        key = spec.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return " | ".join(deduped)


def _find_affiliations(lines: list[str]) -> str:
    collected: list[str] = []
    for line in lines[:250]:
        collected.extend(_split_affiliations_from_line(line))

    if not collected:
        block_lines: list[str] = []
        in_block = False
        for raw in lines[:400]:
            line = re.sub(r"\s+", " ", raw.strip())
            if not line:
                if in_block:
                    break
                continue
            lowered = line.lower()
            if _looks_like_affiliation_line(line):
                block_lines.append(line)
                in_block = True
                continue
            if not in_block:
                continue
            if _canonical_heading(line) in _KNOWN_HEADINGS:
                break
            if lowered.startswith(("received:", "accepted:", "advance publication", "correspondence")):
                break
            if lowered.startswith(("http://", "https://", "doi:")):
                break
            if _is_layout_noise_line(line):
                break
            if "correspond" in lowered:
                break
            if len(line) <= 120 and not line.endswith(".") and any(
                k in lowered
                for k in [
                    "department",
                    "division",
                    "faculty",
                    "school",
                    "university",
                    "hospital",
                    "medical center",
                    "medical centre",
                    "centre",
                    "center",
                    "clinic",
                    "institute",
                    "laboratory",
                    "program",
                    "japan",
                ]
            ):
                block_lines.append(line)
                continue
            break

        if block_lines:
            entries: list[str] = []
            for line in block_lines:
                match = re.match(r"^(?P<num>\d+)\s*(?:\)|[).]|,)?\s*(?P<rest>.+)$", line)
                if match:
                    entries.append(f"{match.group('num')}) {match.group('rest').strip()}")
                elif entries:
                    entries[-1] = f"{entries[-1]} {line}".strip()
            collected = entries

    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in collected:
        entry = re.sub(r"\s+", " ", entry).strip()
        if not entry or entry in seen:
            continue
        match = re.match(r"^(?P<num>\d+)\s*(?:\)|[.)]|,)?\s*(?P<rest>.+)$", entry)
        if match:
            rest = match.group("rest").strip()
            if rest.lower().endswith(" and"):
                rest = rest[:-4].strip()
            rest = rest.strip(" ;,")
            entry = f"{match.group('num')}) {rest}"
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
                    "medical center",
                    "medical centre",
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

    front_end = len(lines)
    for i, line in enumerate(lines[:300]):
        if _canonical_heading(line) in {
            "abstract",
            "introduction",
            "background",
            "keywords",
            "key words",
            "case presentation",
            "case report",
            "main text",
        }:
            front_end = i
            break
    front_lines = lines[:front_end] if front_end > 0 else lines[: min(len(lines), 120)]

    citation: dict[str, str] = {}
    if labeled.get("journal_raw"):
        for pat in (_VOL_NO_PAGES_RE, _CITATION_RE, _CITATION_VOL_PAGES_YEAR_RE):
            match = pat.search(labeled["journal_raw"])
            if not match:
                continue
            if pat is _VOL_NO_PAGES_RE:
                pages = match.group("pages") or ""
                citation = {
                    "journal_name": _clean_journal_name(match.group("journal")),
                    "year": match.group("year").strip(),
                    "volume": match.group("volume").strip(),
                    "issue": match.group("issue").strip(),
                    "pages": re.sub(r"\s+", "", pages),
                }
            elif pat is _CITATION_VOL_PAGES_YEAR_RE:
                issue = (match.group("issue") or "").strip()
                citation = {
                    "journal_name": _clean_journal_name(match.group("journal")),
                    "year": match.group("year").strip(),
                    "volume": match.group("volume").strip(),
                    "issue": issue,
                    "pages": re.sub(r"\s+", "", match.group("pages")),
                }
            else:
                citation = {
                    "journal_name": _clean_journal_name(match.group("journal")),
                    "year": match.group("year").strip(),
                    "volume": match.group("volume").strip(),
                    "issue": match.group("issue").strip(),
                    "pages": re.sub(r"\s+", "", match.group("pages")),
                }
            break
    if not citation:
        citation = _find_citation(lines)

    journal_name = _find_journal_name(front_lines) or citation.get("journal_name", "")

    title = labeled.get("title") or _find_title(front_lines)

    labeled_authors = labeled.get("authors") or ""
    authors = labeled_authors or _find_authors(front_lines, title)

    labeled_aff = labeled.get("affiliations") or ""
    affiliations = labeled_aff or _find_affiliations(front_lines)
    if not affiliations:
        affiliations = _find_affiliations(lines)

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

def extract_structured_sections(clean_text: str) -> dict[str, str]:
    clean_text = _normalize_text(clean_text)
    lines = [line.rstrip() for line in clean_text.split("\n")]

    def norm(line: str) -> str:
        return re.sub(r"\s+", " ", line.strip()).strip(":：").lower()

    def is_heading(line: str, names: set[str]) -> bool:
        n = norm(line)
        for name in names:
            if n == name:
                return True
            if n.startswith(name) and len(n) > len(name) and n[len(name)] in {" ", ":", "："}:
                return True
        return False

    def find_heading(names: set[str]) -> int:
        for i, line in enumerate(lines):
            if is_heading(line, names):
                return i
        return -1

    def collect_between(start_names: set[str], end_names: set[str]) -> str:
        start = find_heading(start_names)
        if start < 0:
            return ""
        buf: list[str] = []
        for line in lines[start + 1 :]:
            if is_heading(line, end_names):
                break
            buf.append(line)
        return _normalize_section_text(buf)

    def slice_main_text() -> str:
        start = find_heading({"keywords", "key words"})
        if start >= 0:
            start += 1
        else:
            start = 0
        end = find_heading({"references"})
        if end < 0:
            end = len(lines)
        return _normalize_section_text(lines[start:end])

    def _normalize_section_text(section_lines: list[str]) -> str:
        paragraphs: list[str] = []
        cur: list[str] = []
        for raw in section_lines:
            line = raw.strip()
            if not line:
                if cur:
                    paragraphs.append(re.sub(r"\s+", " ", " ".join(cur)).strip())
                    cur = []
                continue
            cur.append(line)
        if cur:
            paragraphs.append(re.sub(r"\s+", " ", " ".join(cur)).strip())
        return "\n\n".join(p for p in paragraphs if p)

    abstract = collect_between({"abstract"}, {"keywords", "key words", "introduction", "background", "references"})
    introduction = collect_between(
        {"introduction", "background"},
        {"case presentation", "case report", "discussion", "conclusion", "references"},
    )

    discussion = collect_between({"discussion"}, {"conclusion", "acknowledgments", "acknowledgements", "references"})
    case_presentation = collect_between({"case presentation", "case report"}, {"discussion", "conclusion", "references"})

    if not abstract:
        kw_idx = find_heading({"keywords", "key words"})
        if kw_idx >= 0:
            end_idx = kw_idx
        else:
            intro_idx = find_heading({"introduction", "background"})
            end_idx = intro_idx if intro_idx >= 0 else -1
        if end_idx > 0:
            last_aff = -1
            for i in range(0, end_idx):
                if _looks_like_affiliation_line(lines[i]):
                    last_aff = i
            start_idx = last_aff + 1 if last_aff >= 0 else 0
            abstract = _normalize_section_text(lines[start_idx:end_idx])

    if not (case_presentation and discussion):
        main_text = slice_main_text()
        if not discussion:
            citation_match = re.search(r"\[\d+\]", main_text)
            if citation_match:
                split_at = citation_match.start()
                paragraph_start = main_text.rfind("\n\n", 0, split_at)
                if paragraph_start != -1:
                    discussion = main_text[paragraph_start + 2 :].strip()
                    case_presentation = main_text[:paragraph_start].strip()
                else:
                    sentence_start = main_text.rfind(". ", 0, split_at)
                    if sentence_start != -1:
                        discussion = main_text[sentence_start + 2 :].strip()
                        case_presentation = main_text[: sentence_start + 1].strip()
                    else:
                        discussion = main_text.strip()
                        case_presentation = ""
    if not case_presentation:
        case_presentation = main_text.strip()

    match = _CASE_START_RE.search(case_presentation)
    if match:
        case_presentation = case_presentation[match.start() :].lstrip()

    return {
        "abstract": abstract,
        "introduction": introduction,
        "case_presentation": case_presentation,
        "discussion": discussion,
    }


_LEADING_CONNECTOR_RE = re.compile(
    r"(?i)^(?:although|however|but|therefore|thus|then|instead|overall|given that|because|since|in this case|in the present case|in the current case|on day\s+\d+)\b[,:]?\s*"
)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = re.sub(r"\s+", " ", item).strip().strip(" ,;:-–—―")
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _strip_leading_connectors(text: str) -> str:
    text = text.strip().strip(" ,;:-–—―")
    while True:
        updated = _LEADING_CONNECTOR_RE.sub("", text).strip()
        updated = updated.lstrip(",").strip()
        if updated == text:
            return text
        text = updated


def _normalize_dx_key(dx: str) -> str:
    dx = dx.lower()
    dx = re.sub(r"[^a-z0-9]+", " ", dx)
    dx = re.sub(r"\s+", " ", dx).strip()
    return dx


def _extract_preceding_phrase(text: str, match_start: int) -> str:
    boundaries = [
        text.rfind("\n", 0, match_start),
        text.rfind(".", 0, match_start),
        text.rfind("!", 0, match_start),
        text.rfind("?", 0, match_start),
        text.rfind(";", 0, match_start),
    ]
    start = max(boundaries)
    if start == -1:
        start = 0
    else:
        start += 1
    prefix = text[start:match_start].strip()
    if "," in prefix:
        prefix = prefix.split(",")[-1].strip()
    prefix = _strip_leading_connectors(prefix)
    prefix = prefix.strip().strip(" ,;:-–—―")
    words = prefix.split()
    if len(words) > 16:
        prefix = " ".join(words[-16:])
    return prefix


def _extract_following_phrase(text: str, match_end: int) -> str:
    tail = text[match_end:]
    tail = re.sub(r"^\s+", "", tail)
    tail = re.split(r"[.;\n]", tail, maxsplit=1)[0]
    return tail.strip().strip(" ,;:-–—―")


def extract_diagnoses(sections: dict[str, str]) -> dict[str, str]:
    case_text = sections.get("case_presentation", "") or ""
    abstract_text = sections.get("abstract", "") or ""
    discussion_text = sections.get("discussion", "") or ""

    tentative_source = re.sub(r"\s+", " ", case_text).strip()
    final_source = re.sub(r"\s+", " ", "\n".join([case_text, abstract_text, discussion_text])).strip()

    tentative: list[str] = []
    for match in re.finditer(r"(?i)\b(?:was|were)\s+(?:also\s+)?considered\b", tentative_source):
        dx = _extract_preceding_phrase(tentative_source, match.start())
        tentative.append(dx)
    for match in re.finditer(r"(?i)\b(?:was|were)\s+suspected\b", tentative_source):
        dx = _extract_preceding_phrase(tentative_source, match.start())
        tentative.append(dx)
    for match in re.finditer(r"(?i)\bsuspicion\s+of\b", tentative_source):
        dx = _extract_following_phrase(tentative_source, match.end())
        tentative.append(dx)

    tentative = [
        dx
        for dx in tentative
        if dx
        and not dx.lower().startswith(("the patient", "patient", "he ", "she ", "they ", "we "))
        and len(dx) <= 200
    ]
    tentative = _dedupe_keep_order(tentative)

    final: list[str] = []
    for match in re.finditer(
        r"(?i)\b(?:was|were)\s+(?:promptly\s+|clinically\s+|presumptively\s+|ultimately\s+|definitively\s+|finally\s+)?diagnosed\b",
        final_source,
    ):
        dx = _extract_preceding_phrase(final_source, match.start())
        final.append(dx)
    for match in re.finditer(r"(?i)\bdiagnosed\s+(?:with|as)\b", final_source):
        dx = _extract_following_phrase(final_source, match.end())
        final.append(dx)
    for match in re.finditer(
        r"(?i)\bconfirm(?:ed)?\s+(?:the\s+presence\s+of|presence\s+of|the\s+diagnosis\s+of|diagnosis\s+of)\s+",
        final_source,
    ):
        dx = _extract_following_phrase(final_source, match.end())
        final.append(dx)
    for match in re.finditer(r"(?i)\b(?:revealed|identified)\s+(?:a|an)\s+", final_source):
        dx = _extract_following_phrase(final_source, match.end())
        if "mutation" in dx.lower() or "thromb" in dx.lower():
            final.append(dx)

    final = [
        dx
        for dx in final
        if dx
        and not dx.lower().startswith(("the patient", "patient", "he ", "she ", "they ", "we "))
        and len(dx) <= 240
    ]
    final = _dedupe_keep_order(final)

    if tentative and final:
        final_keys = [_normalize_dx_key(dx) for dx in final]
        filtered: list[str] = []
        for dx in tentative:
            key = _normalize_dx_key(dx)
            if not key:
                continue
            overlap = any(
                key == other
                or (len(key) >= 10 and key in other)
                or (len(other) >= 10 and other in key)
                for other in final_keys
            )
            if overlap:
                continue
            filtered.append(dx)
        tentative = filtered

    return {
        "tentative_diagnoses": " | ".join(tentative),
        "final_diagnoses": " | ".join(final),
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
        "first_author",
        "first_author_affiliations",
        "first_author_specialties",
        "tentative_diagnoses",
        "final_diagnoses",
        "affiliations",
        "doi",
        "extracted_at",
        "extractor",
        "abstract",
        "introduction",
        "case_presentation",
        "discussion",
        "figure_legends",
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


def _utc_now_iso() -> str:
    ts = time.time()
    seconds = int(ts)
    micros = int(round((ts - seconds) * 1_000_000))
    if micros >= 1_000_000:
        seconds += 1
        micros = 0
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds))
    return f"{base}.{micros:06d}Z"


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
    input_root: Path,
    txt_out: Path,
    csv_out: Path | None,
    force: bool,
    sync_output: bool,
) -> None:
    if not pdfs:
        if csv_out:
            write_csv([], csv_out)
            print(csv_out)
        if sync_output:
            _sync_txt_outputs(txt_out, set())
        return

    txt_out.mkdir(parents=True, exist_ok=True)

    extracted_at = _utc_now_iso()
    rows: list[dict[str, str]] = []
    expected_outputs: set[Path] = set()

    for pdf_path in pdfs:
        out_path, meta_path = _output_paths_for_pdf(pdf_path, input_root, txt_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        expected_outputs.add(out_path)
        expected_outputs.add(meta_path)
        wrote_txt = False
        figure_legends = ""
        pdf_stat = pdf_path.stat()
        pdf_size = int(pdf_stat.st_size)
        pdf_mtime_ns = int(pdf_stat.st_mtime_ns)
        pdf_sha256 = ""

        needs_extract = force or not out_path.exists()
        if not needs_extract:
            try:
                out_mtime_ns = int(out_path.stat().st_mtime_ns)
            except FileNotFoundError:
                out_mtime_ns = 0
            if out_mtime_ns >= pdf_mtime_ns:
                needs_extract = False
            else:
                cached_meta: dict[str, str] = {}
                if meta_path.exists():
                    try:
                        cached = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                        if isinstance(cached, dict):
                            cached_meta = {str(k): str(v) for k, v in cached.items()}
                    except Exception:
                        cached_meta = {}
                meta_sha256 = cached_meta.get("source_pdf_sha256", "")
                meta_size = int(cached_meta.get("source_pdf_size", "0") or "0")
                if meta_sha256 and meta_size == pdf_size:
                    try:
                        pdf_sha256 = _sha256_file(pdf_path)
                    except OSError:
                        pdf_sha256 = ""
                    needs_extract = not (pdf_sha256 and pdf_sha256 == meta_sha256)
                else:
                    needs_extract = True

        if not needs_extract:
            if not csv_out:
                continue
            cleaned_text = out_path.read_text(encoding="utf-8-sig", errors="replace")
            extractor = "txt-cache"
        else:
            raw_text, extractor = extract_text(pdf_path)
            if csv_out:
                figure_legends = extract_figure_legends(raw_text)
            cleaned_text = clean_extracted_text(raw_text)
            out_path.write_text(cleaned_text, encoding="utf-8-sig", newline="\n")
            wrote_txt = True
            try:
                pdf_sha256 = _sha256_file(pdf_path)
            except OSError:
                pdf_sha256 = ""

        metadata: dict[str, str] = {}
        if needs_extract:
            metadata = extract_metadata(raw_text)
            if csv_out and figure_legends:
                metadata["figure_legends"] = figure_legends
            metadata["source_pdf_path"] = str(pdf_path)
            metadata["source_pdf_size"] = str(pdf_size)
            metadata["source_pdf_mtime_ns"] = str(pdf_mtime_ns)
            if pdf_sha256:
                metadata["source_pdf_sha256"] = pdf_sha256
            try:
                meta_path.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            except OSError:
                pass
        else:
            if meta_path.exists():
                try:
                    cached = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(cached, dict):
                        metadata = {str(k): str(v) for k, v in cached.items()}
                except Exception:
                    metadata = {}

            if not metadata:
                metadata = extract_metadata(raw_text)

            if csv_out:
                figure_legends = metadata.get("figure_legends", "")

            needs_meta_refresh = not metadata.get("year") or not metadata.get("journal_name")
            needs_fig_refresh = bool(csv_out and not figure_legends)
            if needs_meta_refresh or needs_fig_refresh:
                cached_figures = figure_legends
                pdf_text, meta_extractor = extract_text(pdf_path)
                if needs_meta_refresh:
                    metadata = extract_metadata(pdf_text)
                    if cached_figures:
                        metadata["figure_legends"] = cached_figures
                if needs_fig_refresh:
                    figure_legends = extract_figure_legends(pdf_text)
                    if figure_legends:
                        metadata["figure_legends"] = figure_legends
                if needs_meta_refresh and needs_fig_refresh:
                    extractor = f"txt-cache+{meta_extractor}-meta+fig"
                elif needs_meta_refresh:
                    extractor = f"txt-cache+{meta_extractor}-meta"
                else:
                    extractor = f"txt-cache+{meta_extractor}-fig"
                try:
                    meta_path.write_text(
                        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                except OSError:
                    pass

        sections = extract_structured_sections(cleaned_text)

        first_author = _extract_first_author(metadata.get("authors", ""))
        aff_map = _parse_affiliations_map(metadata.get("affiliations", ""))
        first_aff_nums = _extract_first_author_aff_nums(cleaned_text, metadata.get("paper_title", ""), first_author)
        if not first_aff_nums and aff_map:
            first_aff_nums = [sorted(aff_map.keys())[0]]
        first_affs = " | ".join(aff_map.get(n, "").strip() for n in first_aff_nums if aff_map.get(n, "").strip())
        first_specs = _infer_specialties_from_affiliations(first_affs)
        diagnoses = extract_diagnoses(sections)

        rows.append(
            {
                "pdf_path": str(pdf_path),
                "txt_path": str(out_path),
                "extracted_at": extracted_at,
                "extractor": extractor,
                "full_text": cleaned_text,
                **metadata,
                "first_author": first_author,
                "first_author_affiliations": first_affs,
                "first_author_specialties": first_specs,
                **diagnoses,
                **sections,
            }
        )
        if wrote_txt:
            print(out_path)

    if csv_out:
        write_csv(rows, csv_out)
        print(csv_out)
    if sync_output:
        _sync_txt_outputs(txt_out, expected_outputs)


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
        "--sync-output",
        "--sync",
        dest="sync_output",
        action="store_true",
        help="Remove output .txt/.meta.json files that are not present under --input",
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

    input_root = args.input.parent if args.input.is_file() else args.input

    if not args.watch:
        pdfs = iter_pdfs(args.input)
        if not pdfs:
            if args.sync_output:
                process_pdfs([], input_root, args.txt_out, args.csv_out, args.force, True)
                print(f"No PDFs found under --input: {args.input} (synced outputs)")
                return 0
            raise SystemExit(
                f"No PDFs found under --input: {args.input}\n"
                "Put PDFs in that folder (recursively) or specify a PDF path with --input.\n"
                "Examples:\n"
                "  ./run.sh /path/to/pdfs\n"
                "  ./run.sh /path/to/file.pdf\n"
                "Tip: add --sync to also remove stale outputs."
            )
        process_pdfs(pdfs, input_root, args.txt_out, args.csv_out, args.force, args.sync_output)
        return 0

    print(f"Watching: {args.input} (interval={args.interval}s)")
    last_states: list[tuple[str, int, int]] | None = None
    try:
        while True:
            pdfs = iter_pdfs(args.input)
            states = _pdf_states(pdfs)
            if last_states is None:
                last_states = states
                if pdfs or args.sync_output:
                    process_pdfs(pdfs, input_root, args.txt_out, args.csv_out, args.force, args.sync_output)
            elif states != last_states:
                last_states = states
                process_pdfs(pdfs, input_root, args.txt_out, args.csv_out, args.force, args.sync_output)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
