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

    def test_cleanup_removes_corresponding_author_block(self) -> None:
        raw = """Case Presentation
A 72-year-old male was referred.
His family history also includes HS in his two children. The results of
Corresponding author: Yoshinosuke Shimamura, MD
Department of Nephrology, Teine Keijinkai Medical Center, 1-12 Maeda, Teine-ku, Sapporo, Hokkaido 006-8555,
Japan
E-Mail: yoshinosukeshimamura@gmail.com
Received for publication 27 November 2014 and accepted in revised form 24 September 2015
© 2016 Japan Primary Care Association
Journal of General and Family Medicine
2016, vol. 17, no. 4, p. 307–310.
Case Reports
— 307 —

testing four years before admission reported mild microscopic hematuria.
References
1. Example.
"""
        cleaned = clean_extracted_text(raw)
        self.assertIn(
            "His family history also includes HS in his two children. The results of testing four years before admission reported mild microscopic hematuria.",
            cleaned,
        )
        self.assertNotIn("Corresponding author:", cleaned)
        self.assertNotIn("E-Mail:", cleaned)
        self.assertNotIn("Japan Primary Care Association", cleaned)


if __name__ == "__main__":
    unittest.main()
