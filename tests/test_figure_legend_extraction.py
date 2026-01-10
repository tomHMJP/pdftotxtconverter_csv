import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import extract_figure_legends  # noqa: E402


class TestFigureLegendExtraction(unittest.TestCase):
    def test_extracts_multiline_figure_legend_and_skips_body(self) -> None:
        raw = """Case Report
Although no stone was visible in
Figure 1. Imaging findings on admission. (A) Contrast-enhanced computed tomography showing
no common bile duct dilation nor presence of a common bile duct stone.
1A
the papilla, cannulation during ERBD was difficult.
"""
        legends = extract_figure_legends(raw)
        self.assertIn("Figure 1. Imaging findings on admission.", legends)
        self.assertIn("no common bile duct dilation", legends)
        self.assertNotIn("the papilla", legends)
        self.assertNotIn("1A", legends)

    def test_dedupes_repeated_legends(self) -> None:
        raw = """Case Report
Brain natriuretic peptide was also normal at 7.0
Figure 1. Initial examination findings. A: Duplex ultrasound of the lower extremity veins.
1A
pg/mL (normal <18.4 pg/mL).
Figure 1. Initial examination findings. A: Duplex ultrasound of the lower extremity veins.
References
1. Example.
"""
        legends = extract_figure_legends(raw)
        self.assertEqual(
            legends.count("Figure 1. Initial examination findings. A: Duplex ultrasound of the lower extremity veins."),
            1,
        )
        self.assertNotIn("pg/mL", legends)


if __name__ == "__main__":
    unittest.main()

