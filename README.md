# 症例報告PDF → UTF-8 txt + CSV（メタデータ付き）

このプロジェクトは、症例報告（case report）のPDFをまとめて処理し、以下を自動生成します。

- PDFごとの **UTF-8 txt**（本文テキスト抽出）
- 全PDFの **メタデータ + 全文テキストを1つのCSV** に統合

## 前提

以下のどちらかでテキスト抽出します。

- 推奨: `pdftotext`（Poppler）
- 代替: PyMuPDF（`pip install pymupdf`）

## 使い方

### 最短セットアップ（推奨）

```bash
cd case-report-pdf-pipeline
./bootstrap.sh
```

### 実行

1) PDFを `input_pdfs/` に入れる

2) 実行（出力は `output/` にまとめる例）

```bash
.venv/bin/python case_report_pipeline.py \
  --input input_pdfs \
  --txt-out output/txt \
  --csv-out output/case_reports.csv
```

※ txt/CSVともに文字化け（Shift-JIS誤判定）を避けるため **UTF-8 with BOM** で出力します。既存txtを同形式で作り直すには `--force` を付けて再実行してください。

短縮コマンド:

```bash
./run.sh
```

### 自動化（フォルダ監視）

PDFを `input_pdfs/` に追加するたびに自動で更新したい場合:

```bash
.venv/bin/python case_report_pipeline.py \
  --watch \
  --interval 10 \
  --input input_pdfs \
  --txt-out output/txt \
  --csv-out output/case_reports.csv
```

短縮コマンド:

```bash
./watch.sh
```

## CSVに入る主な列

- `paper_title`（論文タイトル）
- `journal_name`（雑誌名）
- `volume`（巻）, `issue`（号）, `year`, `pages`
- `authors`（著者）
- `affiliations`（所属 / specialty）
- `full_text`（txt全文）

メタデータは **抽出テキストからのルールベース推定** のため、レイアウトや雑誌ごとの差で誤りが出ることがあります（必要なら後続で精度向上できます）。

※ `output/case_reports.csv` は Excel での文字化け（Shift-JIS誤判定）を避けるため **UTF-8 with BOM** で出力します。

## テスト（任意）

```bash
cd case-report-pdf-pipeline
python3 -m unittest discover -s tests
```
