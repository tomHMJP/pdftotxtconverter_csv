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

SAMPLE_TEXT_VOL_NO = """Hereditary Spherocytosis Presenting with Immunoglobulin
A Nephropathy in Post-Splenectomy
Yoshinosuke Shimamura, MD,1 Takako Akimoto, MD,1
Norihito Moniwa, MD,1 Koichi Hasegawa, MD,1
Yayoi Ogawa, MD,2 and Hideki Takizawa, MD1
1 Department of Nephrology, Teine Keijinkai Medical Center, Sapporo, Hokkaido, Japan
2 Hokkaido Renal Pathology Center, Sapporo, Hokkaido, Japan
Hereditary spherocytosis is a familial hemolytic anemia.
Keywords: hereditary spherocytosis, IgA nephropathy, angiotensin converting enzyme inhibitor
Introduction
...
Case Presentation
A 72-year-old male was referred to our medical center.
© 2016 Japan Primary Care Association Journal of General and Family Medicine 2016, vol. 17, no. 4, p. 307–310.
Discussion
...
References
Wyatt RJ, Julian BA: IgA nephropathy. N Engl J Med. 2013; 368(25): 2402–2414.
"""

SAMPLE_TEXT_VOL_PAGES_YEAR = """144
doi: 10.2169/internalmedicine.5419-25
Intern Med 65: 144-148, 2026
http://internmed.jp
【CASE REPORT 】
Factor V Leiden Mutation Diagnosed After the Onset of
DVT During Pregnancy in a Woman of
Half-Japanese, Half-European Descent
Kazuhiro Shimizu
1, Masahiro Iwakawa
1, Yusuke Suzuki
1 and Takeyoshi Murano
2

Abstract:
...
Case Report
...
7.0
１Department of Internal Medicine, Toho University Sakura Medical Center, Japan and
２Clinical Laboratory Program, Faculty of Science, Toho
University, Japan
Received: February 9, 2025; Accepted: April 22, 2025; Advance Publication by J-STAGE: June 12, 2025
Correspondence to Dr. Kazuhiro Shimizu, k432@sakura.med.toho-u.ac.jp
References
1. Example.
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

    def test_extract_metadata_vol_no_style(self) -> None:
        meta = extract_metadata(SAMPLE_TEXT_VOL_NO)
        self.assertEqual(
            meta["paper_title"],
            "Hereditary Spherocytosis Presenting with Immunoglobulin A Nephropathy in Post-Splenectomy",
        )
        self.assertEqual(meta["journal_name"], "Journal of General and Family Medicine")
        self.assertEqual(meta["year"], "2016")
        self.assertEqual(meta["volume"], "17")
        self.assertEqual(meta["issue"], "4")
        self.assertEqual(meta["pages"], "307–310")
        self.assertIn("Yoshinosuke Shimamura", meta["authors"])
        self.assertIn("Hideki Takizawa", meta["authors"])
        self.assertIn("1) Department of Nephrology", meta["affiliations"])
        self.assertIn("2) Hokkaido Renal Pathology Center", meta["affiliations"])

    def test_extract_metadata_vol_pages_year_style(self) -> None:
        meta = extract_metadata(SAMPLE_TEXT_VOL_PAGES_YEAR)
        self.assertEqual(
            meta["paper_title"],
            "Factor V Leiden Mutation Diagnosed After the Onset of DVT During Pregnancy in a Woman of Half-Japanese, Half-European Descent",
        )
        self.assertEqual(meta["journal_name"], "Intern Med")
        self.assertEqual(meta["year"], "2026")
        self.assertEqual(meta["volume"], "65")
        self.assertEqual(meta["issue"], "")
        self.assertEqual(meta["pages"], "144-148")
        self.assertEqual(meta["doi"], "10.2169/internalmedicine.5419-25")
        self.assertIn("Kazuhiro Shimizu", meta["authors"])
        self.assertIn("Masahiro Iwakawa", meta["authors"])
        self.assertIn("Yusuke Suzuki", meta["authors"])
        self.assertIn("Takeyoshi Murano", meta["authors"])
        self.assertNotIn("Half-European", meta["authors"])
        self.assertIn("1) Department of Internal Medicine", meta["affiliations"])
        self.assertIn("2) Clinical Laboratory Program", meta["affiliations"])


if __name__ == "__main__":
    unittest.main()
