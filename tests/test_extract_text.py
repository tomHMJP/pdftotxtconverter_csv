import tempfile
import unittest
import warnings
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import extract_text  # noqa: E402


class TestExtractText(unittest.TestCase):
    def test_extract_text_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"

            warnings.filterwarnings("ignore", category=DeprecationWarning)
            import fitz  # type: ignore

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Hello Case Report")
            doc.save(str(pdf_path))
            doc.close()

            text, extractor = extract_text(pdf_path)
            self.assertIn("Hello Case Report", text)
            self.assertIn(extractor, {"pdftotext", "pymupdf"})


if __name__ == "__main__":
    unittest.main()
