import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import iter_pdfs  # noqa: E402


class TestIterPdfs(unittest.TestCase):
    def test_iter_pdfs_finds_pdf_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.PDF").write_bytes(b"")
            (root / "b.pdf").write_bytes(b"")
            (root / "c.txt").write_text("x", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "d.PdF").write_bytes(b"")

            pdfs = iter_pdfs(root)
            names = {p.name for p in pdfs}
            self.assertEqual(names, {"a.PDF", "b.pdf", "d.PdF"})


if __name__ == "__main__":
    unittest.main()

