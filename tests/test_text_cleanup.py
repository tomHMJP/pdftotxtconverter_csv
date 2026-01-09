import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import clean_extracted_text, extract_structured_sections  # noqa: E402


class TestTextCleanup(unittest.TestCase):
    def test_cleanup_removes_hyphen_linebreaks_and_reflows_lines(self) -> None:
        raw = """JOURNAL OF TEST
Short Case Report
Test Title
Author Name
Abstract
This was suggest-
ing acute cholangitis, as observed in
our
patient.
Because
acute
cholangitis
can
be
life-
threatening,
we measured liver function test re-
sults.
References
1. Example.
"""
        cleaned = clean_extracted_text(raw)
        self.assertIn(
            "This was suggesting acute cholangitis, as observed in our patient. Because acute cholangitis can be life-threatening, we measured liver function test results.",
            cleaned,
        )
        self.assertNotIn("suggest-\n", cleaned)
        self.assertNotIn("re-\n", cleaned)

    def test_cleanup_keeps_front_matter_lines_separate(self) -> None:
        raw = """JOURNAL OF TEST
Short Case Report
Test Title
Author Name
Abstract
Body line one.
"""
        cleaned = clean_extracted_text(raw)
        self.assertIn("JOURNAL OF TEST\nShort Case Report\nTest Title\nAuthor Name\n", cleaned)
        self.assertNotIn("JOURNAL OF TEST Short Case Report", cleaned)

    def test_extract_structured_sections_returns_abstract(self) -> None:
        raw = """JOURNAL OF TEST
Test Title
Abstract
Line one.
Line two.
References
1. Example.
"""
        cleaned = clean_extracted_text(raw)
        sections = extract_structured_sections(cleaned)
        self.assertIn("Line one. Line two.", sections.get("abstract", ""))


if __name__ == "__main__":
    unittest.main()

