import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import extract_metadata  # noqa: E402


SAMPLE_TEXT = """JOURNAL OF HOSPITAL GENERAL MEDICINE https://doi.org/10.60227/jhgmeibun.2025-0015 http://hgm-japan.com/english-2/about-the-journal/

Short Case Report

Acute Cholangitis with Normal Liver Function Tests

Koichiro Okumura and Takashi Ikeya

1) Department of General Internal Medicine, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan 2) Nephrology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan 3) Gastroenterology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan

Keywords acute cholangitis, cholestasis, liver function tests

J Hosp Gen Med 2025:7(6):253-255
"""

SAMPLE_TEXT_LABELED = """Article Information
Journal: Journal of Hospital General Medicine 2025;7(6):253-255 Title: Acute Cholangitis with Normal Liver Function Tests Type: Short Case Report Authors: Koichiro Okumura and Takashi Ikeya Affiliations: 1) Department of General Internal Medicine, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan 2) Nephrology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan 3) Gastroenterology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan
"""

SAMPLE_TEXT_MULTILINE_AUTHORS = """253
https://doi.org/10.60227/jhgmeibun.2025-0015
http://hgm-japan.com/english-2/about-the-journal/
JOURNAL OF HOSPITAL GENERAL MEDICINE
― Short Case Report ―
Acute Cholangitis with Normal Liver Function Tests
Koichiro Okumura
1)2) and Takashi Ikeya
3)
1) Department of General Internal Medicine, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan
2) Nephrology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan
3) Gastroenterology Department, Tokyo Metropolitan Ohkubo Hospital, Tokyo, Japan
Abstract
...
"""


class TestMetadataExtraction(unittest.TestCase):
    def test_extract_metadata_basic_fields(self) -> None:
        meta = extract_metadata(SAMPLE_TEXT)
        self.assertEqual(meta["paper_title"], "Acute Cholangitis with Normal Liver Function Tests")
        self.assertEqual(meta["journal_name"], "JOURNAL OF HOSPITAL GENERAL MEDICINE")
        self.assertEqual(meta["year"], "2025")
        self.assertEqual(meta["volume"], "7")
        self.assertEqual(meta["issue"], "6")
        self.assertEqual(meta["pages"], "253-255")
        self.assertEqual(meta["authors"], "Koichiro Okumura and Takashi Ikeya")
        self.assertEqual(meta["doi"], "10.60227/jhgmeibun.2025-0015")

        affiliations = meta["affiliations"]
        self.assertIn("1) Department of General Internal Medicine", affiliations)
        self.assertIn("2) Nephrology Department", affiliations)
        self.assertIn("3) Gastroenterology Department", affiliations)

    def test_extract_metadata_labeled_line(self) -> None:
        meta = extract_metadata(SAMPLE_TEXT_LABELED)
        self.assertEqual(meta["paper_title"], "Acute Cholangitis with Normal Liver Function Tests")
        self.assertEqual(meta["journal_name"], "Journal of Hospital General Medicine")
        self.assertEqual(meta["year"], "2025")
        self.assertEqual(meta["volume"], "7")
        self.assertEqual(meta["issue"], "6")
        self.assertEqual(meta["pages"], "253-255")
        self.assertEqual(meta["authors"], "Koichiro Okumura and Takashi Ikeya")

        affiliations = meta["affiliations"]
        self.assertIn("1) Department of General Internal Medicine", affiliations)
        self.assertIn("2) Nephrology Department", affiliations)
        self.assertIn("3) Gastroenterology Department", affiliations)

    def test_extract_metadata_multiline_authors(self) -> None:
        meta = extract_metadata(SAMPLE_TEXT_MULTILINE_AUTHORS)
        self.assertEqual(meta["journal_name"], "JOURNAL OF HOSPITAL GENERAL MEDICINE")
        self.assertEqual(meta["paper_title"], "Acute Cholangitis with Normal Liver Function Tests")
        self.assertEqual(meta["authors"], "Koichiro Okumura and Takashi Ikeya")

        affiliations = meta["affiliations"]
        self.assertNotIn("and Takashi Ikeya", affiliations)
        self.assertIn("1) Department of General Internal Medicine", affiliations)
        self.assertIn("2) Nephrology Department", affiliations)
        self.assertIn("3) Gastroenterology Department", affiliations)


if __name__ == "__main__":
    unittest.main()
