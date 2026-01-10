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
cd pdftotxtconverter_csv
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

過去の出力（txt/meta.json）を入力フォルダと同期して不要ファイルを自動削除するには `--sync` を使います。
（`./run.sh` と `./watch.sh` はデフォルトで `--sync` を有効にしています）

短縮コマンド:

```bash
./run.sh                 # input_pdfs/ を処理（デフォルト）
./run.sh /path/to/pdfs   # 任意のフォルダを処理
./run.sh /path/to/a.pdf  # PDF 1本だけ処理
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
- `first_author`（筆頭著者）
- `first_author_affiliations`（筆頭著者の所属）
- `first_author_specialties`（所属から推測した診療科名）
- `tentative_diagnoses`（途中の暫定診断）
- `final_diagnoses`（最終診断）
- `affiliations`（所属）
- `abstract`, `introduction`, `case_presentation`, `discussion`（章ごとの本文）
- `figure_legends`（Figure legend / 図のキャプション）
- `full_text`（txt全文）

txt/CSV の `full_text` は、PDF由来の「無駄な改行」や `suggest-\ning` のような改行ハイフン分割に加えて、ページヘッダ/フッタ（例: `Corresponding author:`）や Figure/Table のキャプション混入も可能な範囲で除去してから格納します。

メタデータは **抽出テキストからのルールベース推定** のため、レイアウトや雑誌ごとの差で誤りが出ることがあります（必要なら後続で精度向上できます）。

※ `output/case_reports.csv` は Excel での文字化け（Shift-JIS誤判定）を避けるため **UTF-8 with BOM** で出力します。

## テスト（任意）

```bash
cd pdftotxtconverter_csv
python3 -m unittest discover -s tests
```
