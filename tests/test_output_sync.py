import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_report_pipeline import _output_paths_for_pdf, _sync_txt_outputs, process_pdfs  # noqa: E402


class TestOutputSync(unittest.TestCase):
    def test_output_paths_mirror_input_root(self) -> None:
        input_root = Path("/tmp/input_root")
        txt_out = Path("/tmp/output/txt")
        pdf_path = input_root / "nested" / "a.pdf"
        out_path, meta_path = _output_paths_for_pdf(pdf_path, input_root, txt_out)
        self.assertEqual(out_path.as_posix(), (txt_out / "nested" / "a.txt").as_posix())
        self.assertEqual(meta_path.as_posix(), (txt_out / "nested" / "a.meta.json").as_posix())

    def test_sync_removes_orphan_txt_and_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt_out = Path(tmp) / "txt"
            (txt_out / "keep").mkdir(parents=True)
            (txt_out / "stale").mkdir(parents=True)

            keep_txt = txt_out / "keep" / "a.txt"
            keep_meta = txt_out / "keep" / "a.meta.json"
            stale_txt = txt_out / "stale" / "b.txt"
            stale_meta = txt_out / "stale" / "b.meta.json"
            other = txt_out / "stale" / "note.md"

            keep_txt.write_text("x", encoding="utf-8")
            keep_meta.write_text("{}", encoding="utf-8")
            stale_txt.write_text("y", encoding="utf-8")
            stale_meta.write_text("{}", encoding="utf-8")
            other.write_text("z", encoding="utf-8")

            _sync_txt_outputs(txt_out, {keep_txt, keep_meta})

            self.assertTrue(keep_txt.exists())
            self.assertTrue(keep_meta.exists())
            self.assertFalse(stale_txt.exists())
            self.assertFalse(stale_meta.exists())
            self.assertTrue(other.exists())

    def test_process_pdfs_empty_with_sync_cleans_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            txt_out = root / "txt"
            csv_out = root / "out.csv"
            (txt_out / "stale").mkdir(parents=True, exist_ok=True)
            stale_txt = txt_out / "stale" / "b.txt"
            stale_meta = txt_out / "stale" / "b.meta.json"
            stale_txt.write_text("y", encoding="utf-8")
            stale_meta.write_text("{}", encoding="utf-8")

            process_pdfs([], root, txt_out, csv_out, force=False, sync_output=True)

            self.assertFalse(stale_txt.exists())
            self.assertFalse(stale_meta.exists())
            self.assertTrue(csv_out.exists())


if __name__ == "__main__":
    unittest.main()
