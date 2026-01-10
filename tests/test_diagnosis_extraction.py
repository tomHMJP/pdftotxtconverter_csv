import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import extract_diagnoses  # noqa: E402


class TestDiagnosisExtraction(unittest.TestCase):
    def test_extracts_tentative_and_final_diagnoses(self) -> None:
        sections = {
            "case_presentation": (
                "Although aspiration pneumonia was considered as a possible diagnosis, "
                "acute cholangitis due to a common bile duct stone was suspected. "
                "The patient was diagnosed with acute cholangitis due to choledocholithiasis."
            ),
            "abstract": "",
            "discussion": "",
        }
        dx = extract_diagnoses(sections)
        self.assertIn("aspiration pneumonia", dx.get("tentative_diagnoses", "").lower())
        self.assertIn("acute cholangitis due to a common bile duct stone", dx.get("tentative_diagnoses", "").lower())
        self.assertIn("acute cholangitis due to choledocholithiasis", dx.get("final_diagnoses", "").lower())

    def test_extracts_diagnosed_and_confirmed_findings(self) -> None:
        sections = {
            "case_presentation": (
                "As shown in Fig. 1, proximal deep vein thrombosis (DVT) of the left lower extremity was promptly "
                "diagnosed using lower limb venous ultrasonography. Pulmonary perfusion scintigraphy was used to "
                "confirm the presence of pulmonary embolism."
            ),
            "abstract": "",
            "discussion": "",
        }
        dx = extract_diagnoses(sections)
        self.assertIn("proximal deep vein thrombosis", dx.get("final_diagnoses", "").lower())
        self.assertIn("pulmonary embolism", dx.get("final_diagnoses", "").lower())


if __name__ == "__main__":
    unittest.main()

