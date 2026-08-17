# Airbnb 房源品質與評論洞察（臺北市）

## 1. 資料

從 [Inside Airbnb](http://insideairbnb.com/get-the-data) 下載 Taipei **Detailed** 檔：

- `listings.csv.gz`
- `reviews.csv.gz`

解壓後放到 `airbnb_Taiwan/`（或自訂路徑）。

### 本專案用的是哪一份？

Inside Airbnb 同一城市常同時提供 **Detailed（.gz）** 與 **Summary（.csv）** 兩種檔案，請勿混用：

| 檔案 | 類型 | 本專案 |
|------|------|--------|
| `listings.csv.gz` | Detailed Listings（完整房源欄位） | **使用**（解壓為 `listings.csv`） |
| `reviews.csv.gz` | Detailed Reviews（完整評論文字） | **使用**（解壓為 `reviews.csv`） |
| `listings.csv`（無 .gz） | Summary listings（視覺化用摘要） | **不使用** |
| `reviews.csv`（無 .gz） | Summary reviews（僅 listing_id 等摘要） | **不使用** |

`01`／`02` 需要 `listings.csv` 的評分、行政區、價格等欄位；`03` 需要 `reviews.csv` 的 `comments` 全文，因此必須用 **Detailed** 解壓檔。

## 2. 環境

需 Python 3.10+。在專案根目錄：

```bash
python -m venv .venv
source .venv/Scripts/activate   # PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Windows 請一律用 `python`，不要用 `py -3`。

## 3. 設定

```bash
cp config.example.json config.local.json
```

至少改這兩個路徑，指向你解壓後的 CSV：

```json
{
  "listings_csv": "airbnb_Taiwan/listings.csv",
  "reviews_csv": "airbnb_Taiwan/reviews.csv"
}
```

其他欄位可沿用 `config.example.json`。正式跑全量主題分析時，把 `theme_sample_n` 改成 `null`。

`config.local.json` 已在 `.gitignore`，不要提交。

## 4. 執行

在專案根目錄、venv 內依序跑：

```bash
python scripts/01_city_quality_summary.py
python scripts/02_segment_quality_compare.py
python scripts/03_theme_frequency.py
python scripts/04_run_sql.py
```

結果會寫進 `output/`。Power BI 檔在 `powerbi/Airbnb_Taipei_Quality.pbix`。

### 跑 SQL：一律在專案根目錄

`.sql` 用相對路徑讀資料，例如 `airbnb_Taiwan/listings.csv`。DuckDB 以**目前工作目錄**解析這個路徑，因此**一律在專案根目錄執行**，不要 `cd sql/` 再跑。

```bash
cd /path/to/airbnb_analysis   # 必須在這裡（直接開 DuckDB CLI 跑 .sql 時）
python scripts/04_run_sql.py  # 腳本會自己 chdir 到根目錄，相對路徑才找得到
```

| 工作目錄 | `airbnb_Taiwan/listings.csv` 實際指向 | 結果 |
|----------|----------------------------------------|------|
| 專案根目錄（正確） | `airbnb_analysis/airbnb_Taiwan/listings.csv` | 找得到 |
| `sql/`（錯誤） | `airbnb_analysis/sql/airbnb_Taiwan/listings.csv` | 找不到檔案 |

Python 腳本會依 `__file__` 自己找到專案根目錄；SQL 不會，所以工作目錄特別重要。

## 5. 授權與引用

- 資料來源：[Inside Airbnb](http://insideairbnb.com/get-the-data)
- 請遵守該站資料授權條款；本專案僅示範分析流程，**不重新散布原始資料檔**。
- 引用時請註明 Inside Airbnb 與資料抓取／檔案日期。
- 分析程式碼可依 GitHub 選定的授權釋出；**原始 Airbnb／Inside Airbnb 資料檔不包含在本倉庫中**。
