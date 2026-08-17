# Airbnb 房源品質與評論洞察（臺北）

以 [Inside Airbnb](http://insideairbnb.com/get-the-data) 臺北公開資料，建立可重現的品質指標與評論主題分析，回答：

1. **哪裡差**：行政區／價格帶／房型的品質落差  
2. **差在什麼**：評論主題（spaCy + 規則字典）  
3. **先改什麼**：2～3 個可驗證的改善優先順序  

本 repo 含全市品質彙總、行政區／價格帶／房型分群對比、偏低分群標記、spaCy 評論主題頻次、可驗證的改善優先順序（見 `output/recommendations.md`），以及 Power BI 儀表板來源檔（`powerbi/`）。互動版見作品頁內嵌。

---

## 專案結構

```text
airbnb_analysis/           # ← 專案根目錄（跑 SQL／腳本都在這裡）
├── README.md
├── requirements.txt
├── config.example.json    # 設定範本（可提交 GitHub）
├── config.local.json      # 本機路徑／參數（勿提交；複製 example 後自行填）
├── rules/
│   └── theme_lexicon.json # 主題關鍵詞字典（規則）
├── sql/                   # DuckDB 查詢（相對路徑對準根目錄）
│   ├── 00_load.sql
│   ├── 01_city_quality_summary.sql
│   ├── 02_segment_quality_compare.sql
│   ├── 03_underperforming_segments.sql
│   └── 04_qa_join_reviews.sql   # JOIN 核對（非品質指標）
├── scripts/
│   ├── 01_city_quality_summary.py
│   ├── 02_segment_quality_compare.py
│   ├── 03_theme_frequency.py
│   └── 04_run_sql.py      # 一鍵跑 SQL，並與 pandas CSV 交叉核對
├── powerbi/
│   ├── Airbnb_Taipei_Quality.pbix   # 儀表板（Desktop 開啟／發佈用）
│   ├── recommendations_table.csv    # 建議表（報表資料來源之一）
│   └── taipei_districts.topojson.json
├── output/                # 小型結果快照（評論明細等大檔不提交）
│   ├── recommendations.md # 產品建議（哪裡差 → 差在什麼 → 先改什麼）
│   ├── lexicon_fix_execution_report.md
│   └── …（pandas／SQL 彙總 CSV）
└── airbnb_Taiwan/         # 原始資料（本機放置，勿提交）
    ├── listings.csv       # 由 listings.csv.gz 解壓
    ├── reviews.csv        # 由 reviews.csv.gz 解壓
    └── ...
```

---

## 資料取得（請自行下載）

原始 CSV **不放在 GitHub**（檔案大，且 Inside Airbnb 授權通常要求分析用途、勿重新散布原始檔）。

1. 前往 [Inside Airbnb — Get the Data](http://insideairbnb.com/get-the-data)  
2. 選 **Taipei, Taiwan**，下載 **Detailed** 壓縮檔（不要用 Summary 版）：
   - `listings.csv.gz` — Detailed Listings data（房源明細）
   - `reviews.csv.gz` — Detailed Review Data（評論明細）
   - （可選）`neighbourhoods.csv` — 行政區對照
3. 解壓後得到 `listings.csv`、`reviews.csv`，放到 `airbnb_Taiwan/`（或你自訂的資料夾）  
4. 在 `config.local.json` 的 `listings_csv`、`reviews_csv` 指向解壓後的 `.csv` 路徑

### 本專案用的是哪一份？

Inside Airbnb 同一城市常同時提供 **Detailed（.gz）** 與 **Summary（.csv）** 兩種檔案，請勿混用：

| 檔案 | 類型 | 本專案 |
|------|------|--------|
| `listings.csv.gz` | Detailed Listings（完整房源欄位） | **使用**（解壓為 `listings.csv`） |
| `reviews.csv.gz` | Detailed Reviews（完整評論文字） | **使用**（解壓為 `reviews.csv`） |
| `listings.csv`（無 .gz） | Summary listings（視覺化用摘要） | **不使用** |
| `reviews.csv`（無 .gz） | Summary reviews（僅 listing_id 等摘要） | **不使用** |

`01`／`02` 腳本需要 `listings.csv` 的評分、行政區、價格等欄位；`03` 需要 `reviews.csv` 的 `comments` 全文做 spaCy 主題分析，因此必須用 **Detailed** 解壓檔。

```text
下載 listings.csv.gz、reviews.csv.gz
    → 解壓
    → airbnb_Taiwan/listings.csv
    → airbnb_Taiwan/reviews.csv
    → config.local.json 指向上述路徑
```

---

## 本機設定（路徑與個人資料分開存）

程式**不硬編碼**本機絕對路徑。請：

```bash
cp config.example.json config.local.json
```

編輯 `config.local.json`（此檔已在 `.gitignore`）：

```json
{
  "city_name": "Taipei",
  "listings_csv": "airbnb_Taiwan/listings.csv",
  "output_dir": "output",
  "city_summary_filename": "pandas_01_city_quality_summary.csv",
  "low_score_threshold": 4.5,

  "min_rated_n": 30,
  "flag_avg_rating_gap": 0.05,
  "flag_low_score_rate_lift": 1.3,

  "price_band_edges": [0, 1500, 2500, 4000, 999999],
  "price_band_labels": ["<=1500", "1501-2500", "2501-4000", ">4000"],

  "reviews_csv": "airbnb_Taiwan/reviews.csv",
  "theme_lexicon_path": "rules/theme_lexicon.json",
  "min_comment_chars": 20,
  "theme_sample_n": 30000,
  "theme_sample_seed": 42,
  "spacy_model": "en_core_web_sm"
}
```

| 欄位 | 說明 |
|------|------|
| `listings_csv` / `reviews_csv` | 相對**專案根目錄**，或改成你的本機絕對路徑 |
| `output_dir` | 輸出資料夾 |
| `low_score_threshold` | 低分門檻（預設 4.5；評分低於此值計入低分率） |
| `min_rated_n` | 分群至少要有幾筆有評分房源數才納入偏低比較（預設 30） |
| `flag_avg_rating_gap` | 均分低於全市此差距以上 → 判定「低均分」（預設 0.05） |
| `flag_low_score_rate_lift` | 低分相對倍率 ≥ 1.3 → 判定「高低分率」（預設 1.3） |
| `price_band_edges` / `price_band_labels` | 價格帶切點與名稱；對齊 `pd.cut(right=True, include_lowest=True)` |
| `city_name` | 彙總表上的城市名稱 |
| `min_comment_chars` | 評論最短字數；低於此值不進主題分母（預設 20） |
| `theme_sample_n` | 抽樣筆數；`null` = 用全部有效評論（全量）；數字如 `30000` = 可重現抽樣 |
| `theme_sample_seed` | 隨機種子（固定後每次抽到同一組評論） |
| `theme_lexicon_path` | 主題關鍵詞字典路徑 |
| `spacy_model` | spaCy 模型名稱（預設 `en_core_web_sm`） |

`config.example.json` 預設 `theme_sample_n: 30000` 方便快速試跑；正式結果建議改為 `null` 跑全量。

---

## 環境安裝

需 Python 3.10+。在專案根目錄：

```bash
cd /path/to/airbnb_analysis
python -m venv .venv

# Git Bash
source .venv/Scripts/activate

# PowerShell
# .\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp config.example.json config.local.json
```

**重要（Windows）**：啟動 venv 後，裝套件、下載 spaCy 模型、跑腳本請一律用 **`python`**，不要用 `py -3`，否則模型可能裝到不同環境。

驗證 spaCy：

```bash
python -c "import spacy; nlp=spacy.load('en_core_web_sm'); print('OK')"
```

---

## 執行分析

在 venv 內、**專案根目錄**依序執行：

```bash
# 1) 全市品質彙總
python scripts/01_city_quality_summary.py

# 2) 行政區／價格帶／住宿類型分群對比
python scripts/02_segment_quality_compare.py

# 3) 評論主題頻次（spaCy + 規則字典）
python scripts/03_theme_frequency.py
```

### 主要輸出

| 腳本 | 輸出檔 | 內容 |
|------|--------|------|
| `01_…` | `output/pandas_01_city_quality_summary.csv` | 全市品質一列摘要 |
| `02_…` | `output/pandas_02_district_quality_summary.csv` | 行政區品質對比 |
| `02_…` | `output/pandas_02_price_band_quality_summary.csv` | 價格帶品質對比 |
| `02_…` | `output/pandas_02_stay_category_quality_summary.csv` | 住宿類型品質對比 |
| `02_…` | `output/pandas_02_underperforming_segments.csv` | 三維合併；偏低分群排前 |
| `03_…` | `output/pandas_03_theme_frequency.csv` | 全市主題頻次／占比 |
| `03_…` | `output/pandas_03_theme_review_hits.csv` | 命中主題的評論明細（人工抽查用；本機產生，不提交） |
| — | `output/pandas_03_theme_by_underperforming_segment.csv` | 偏低分群 × 噪音／清潔負向交叉（建議用快照） |
| — | `output/recommendations.md` | 產品建議（情境／假設／動作／驗證） |

查看主題頻次：

```bash
python -c "import pandas as pd; print(pd.read_csv('output/pandas_03_theme_frequency.csv'))"
```

### 跑 SQL：一律在專案根目錄

`.sql` 用相對路徑讀資料，例如 `airbnb_Taiwan/listings.csv`。DuckDB 以**目前工作目錄**解析這個路徑，因此**一律在專案根目錄執行**，不要 `cd sql/` 再跑。

```bash
cd /path/to/airbnb_analysis   # 必須在這裡（直接開 DuckDB CLI 跑 .sql 時）
python scripts/04_run_sql.py  # 腳本會自己 chdir 到根目錄，相對路徑才找得到
```

會依序跑 `sql/00`～`04`（同一 DuckDB 連線），把查詢結果存 CSV，再與 pandas 產出交叉核對：

| SQL | 輸出 |
|-----|------|
| `01_….sql` | `output/sql_01_city_quality_summary.csv` |
| `02_….sql` | `output/sql_02_segment_quality_compare.csv` |
| `03_….sql` | `output/sql_03_underperforming_segments.csv` |
| `04_….sql` | `output/sql_04_qa_join_reviews.csv` |

`00_load.sql` 只建表／VIEW，不存 CSV。跑完後會自動交叉核對（須先跑過 `scripts/01`、`02`）：

- 全市：`n_listings`、`avg_rating`、`low_score_rate`、`rating_nonnull_n`
- 偏低分群組別：`pandas_02_underperforming_segments.csv`（只留 `is_underperforming = True`）↔ `sql_03_…`
- 必要三組必須都在：飯店類、南港區、`<=1500`（`Unknown` 價格帶若被標，兩邊都要有）

| 工作目錄 | `airbnb_Taiwan/listings.csv` 實際指向 | 結果 |
|----------|----------------------------------------|------|
| 專案根目錄（正確） | `airbnb_analysis/airbnb_Taiwan/listings.csv` | 找得到 |
| `sql/`（錯誤） | `airbnb_analysis/sql/airbnb_Taiwan/listings.csv` | 找不到檔案 |

Python 腳本會依 `__file__` 自己找到專案根目錄；SQL 不會，所以工作目錄特別重要。

### SQL 做什麼／不做什麼

| 檔案 | 用途 |
|------|------|
| `00_load.sql` | 讀 listings、清洗、切價格帶／房型（`listings_raw` → `listings_clean`） |
| `01_city_quality_summary.sql` | 全市品質彙總 |
| `02_segment_quality_compare.sql` | 行政區／價格帶／房型分群（含偏低標記） |
| `03_underperforming_segments.sql` | 只留偏低分群 |
| `04_qa_join_reviews.sql` | `listings.id = reviews.listing_id` **核對則數** |

**品質指標以 `listings` 欄位為準**（`number_of_reviews`、`number_of_reviews_ltm`、`review_scores_rating`）。  
`01`／`02`／`03` **不必 JOIN** reviews。`04` 的 JOIN 只檢查「房源表上的評論則數」是否等於「reviews 表實際列數」，**不要拿來取代有評率／活躍率**。

---

## 全市品質彙總指標說明

單位：一列房源（`listings.csv`）。全市輸出為一列摘要。指標皆來自 listings 既有欄位，不經 reviews JOIN。

| 指標 | 定義 |
|------|------|
| `n_listings` | 房源總數 |
| `review_coverage` | `number_of_reviews >= 1` 占比 |
| `ltm_active_rate` | `number_of_reviews_ltm >= 1` 占比 |
| `avg_rating` | `review_scores_rating` 平均（僅非空） |
| `low_score_rate` | 評分 `< low_score_threshold` 占比（分母＝有評分房源） |
| `superhost_rate` | `host_is_superhost == t` 占比 |

目前全市快照（`output/pandas_01_city_quality_summary.csv`，與 SQL 交叉核對通過）：

| 房源數 | 有評率 | 近一年活躍率 | 均分 | 低分率 | Superhost 率 | 有評分房源數 |
|--------|--------|--------------|------|--------|--------------|------------|
| 6,419 | 80.95% | 69.37% | 4.743 | 11.18% | 48.20% | 5,196 |

JOIN 核對（`output/sql_04_qa_join_reviews.csv`）：6,419 筆房源，`review_count_match_rate = 1.0`，0 筆則數不符。

---

## 分群與偏低標記

`02` 依三個維度各做一張表，再合併成 `pandas_02_underperforming_segments.csv`：

| 維度 | 欄位 | 說明 |
|------|------|------|
| 行政區 | `neighbourhood_cleansed` | 缺值標成 Unknown |
| 價格帶 | `price` 清洗後切帶 | `<=1500`／`1501-2500`／`2501-4000`／`>4000`；無價格 → Unknown |
| 住宿類型 | `property_type` + `room_type` | 合宿類 → 飯店類 → 民宿類 → 住宅類（先判 shared room，避免被 hotel 蓋掉） |

偏低條件（有評分房源數 ≥ 30 **且** 符合任一）：

1. **低均分**：`avg_rating ≤ 全市均分 − flag_avg_rating_gap`
2. **高低分率**：`low_score_rate ≥ 全市低分率 × flag_low_score_rate_lift`

目前被標記為偏低的分群：

| 分群維度 | 分群 | 均分 | 低分率 | 低分相對倍率 | 有評分房源數 | 標記原因 |
|----------|------|------|--------|------|------------|----------|
| 房型 | **飯店類** | 4.61 | 24.72% | 2.21× | 267 | 低均分且高低分率 |
| 行政區 | **南港區** | 4.68 | 22.22% | 1.99× | 54 | 低均分且高低分率 |
| 價格帶 | **≤1500 元** | 4.65 | 18.84% | 1.69× | 1,003 | 低均分且高低分率 |
| 價格帶 | Unknown | 4.70 | 17.57% | 1.57× | 313 | 高低分率（資料缺漏，非建議重點） |

---

## 評論主題分析（spaCy + 規則字典）

腳本：`scripts/03_theme_frequency.py`（規則亦寫在 docstring）。  
字典：`rules/theme_lexicon.json`（7 個主題：清潔、噪音、溝通、取消、地點、性價比、設備）。

### 方法概要

```text
reviews.csv
  → 清洗（空白／過短／HTML／去重）
  → 抽樣（theme_sample_n；null 則全量）
  → spaCy PhraseMatcher + 字串包含比對（中文補強）
  → 每則評論多標籤
  → pandas_03_theme_frequency.csv / pandas_03_theme_review_hits.csv
  → pandas_03_theme_by_underperforming_segment.csv（同一批有效評論）
```

### 品質／抽樣規則

| 規則 | 設定 |
|------|------|
| 空白評論 | 排除 |
| 過短 | `len(comments) < min_comment_chars`（預設 20）排除 |
| HTML | 去掉 `<br/>` 等標籤 |
| 抽樣 | `sample(n=theme_sample_n, random_state=theme_sample_seed)`；`null` = 不抽樣 |
| 重複評論 | 同一 `listing_id` + 相同 `comments` 去重 |
| 分母 | **有效評論數**（通過清洗者） |
| 計數 | 一則評論同一主題最多計 1 次 |

### 指標

- **有效評論數** = 通過清洗規則者  
- **主題占比** = 該主題出現則數 ÷ 有效評論數  
- 一則評論可同時命中多個主題（多標籤）  
- **命中＝提及該主題**，第一版不區分正負面（提及 ≠ 抱怨）

### 字典修正紀錄（v1 → v2）

初版 `communication` 含 `host`，英文好評幾乎都會命中，占比虛高（43%）。  
已移除 `host`，改以 `unresponsive`、`slow reply`、`回覆慢` 等窄片語；30k 抽樣下溝通占比約 43% → 30%。

### 全量結果（最終數字，theme_sample_n: null）

分母：**202,548** 則有效評論（清洗／去重後，不抽樣）。

| 主題 | 則數 | 占比 |
|------|------|------|
| 地點／交通 | 108,452 | 53.54% |
| 設備 | 95,288 | 47.04% |
| 溝通 | 62,449 | 30.83% |
| 清潔 | 65,041 | 32.11% |
| 噪音 | 9,995 | 4.93% |
| 性價比 | 9,511 | 4.70% |
| 取消／入住異常 | 697 | 0.34% |

解讀注意：地點、設備、清潔、溝通占比高，多為正面或中性提及；**噪音**較適合作為問題線索。詳見 `output/lexicon_fix_execution_report.md`。

### 抽樣 vs 全量

| 模式 | 設定 | 用途 |
|------|------|------|
| 快速試跑 | `"theme_sample_n": 30000` | 調字典、除錯（約 1 分鐘） |
| 正式結果 | `"theme_sample_n": null` | 作品集／報告用最終數字（約 4～5 分鐘） |

### 偏低分群 × 主題交叉

`output/pandas_03_theme_by_underperforming_segment.csv`（與上方主題頻次同一批全量 202,548 則。臺北市基準：噪音 4.93%、清潔負向 2.44%。清潔僅計負向命中）：

| 分群 | 有效評論數 | 噪音占比 | 清潔負向占比 | 解讀 |
|------|-----------|----------|--------------|------|
| 價格 ≤1500 | 27,931 | **6.15%** | 2.66% | 噪音高於臺北市 4.93%；清潔負向略高，可順帶檢查，不以清潔為主 |
| 飯店類 | 5,944 | **5.70%** | **3.10%** | 噪音高約 0.8 個百分點、清潔負向高約 0.7 個百分點 → 兩主題均可列 |
| 南港區 | 916 | 3.17% | 2.40% | 噪音低於臺北市、清潔負向持平 → 主題無法解釋低分 |

---

## 先改什麼（產品建議）

完整推論、假設與 8–12 週驗證方式見 `output/recommendations.md`。摘要：

| 順位 | 分群 × 主題 | 證據強度 | 建議先做的事 |
|------|-------------|----------|--------------|
| 1 | ≤1500 元 × 噪音 | 高（有效評論 27,931，噪音明顯偏高） | 房源揭露 + 隔音低成本輔導 |
| 2 | 飯店類 × 噪音＋清潔負向 | 高（噪音 5.70%、清潔負向 3.10%，皆高於臺北市；低分率仍最高） | 噪音揭露 + 隔音；同步檢查清潔／異味；另抽查其他根因 |
| 3 | 南港區 × 主題未對上 | 有效評論 916；噪音低於臺北市 | 人工複核低分評論，不套噪音／清潔方案 |

三種偏低分群不能套同一套改善方案：≤1500 以噪音為主；飯店類可對噪音與清潔負向行動；南港區主題未對上，先抽查。

---

## 授權與引用

- 資料來源：[Inside Airbnb](http://insideairbnb.com/get-the-data)  
- 請遵守該站資料授權條款；本專案僅示範分析流程，**不重新散布原始資料檔**。  
- 引用時請註明 Inside Airbnb 與資料抓取／檔案日期。

---

## Roadmap

- [x] 全市品質彙總（`01_city_quality_summary.py`）  
- [x] 行政區／價格帶／住宿類型分群對比（`02_segment_quality_compare.py`）  
- [x] 偏低分群標記（均分落差／低分相對倍率 + 有評分房源數門檻）  
- [x] spaCy 評論主題抽取（`03_theme_frequency.py` + `rules/theme_lexicon.json`）  
- [x] 全量主題頻次（`theme_sample_n: null`）  
- [x] 偏低分群 × 主題交叉  
- [x] DuckDB SQL（全市／分群／偏低分群 + JOIN 核對 + pandas 交叉核對）  
- [x] 改善優先順序結論（`output/recommendations.md`）  
- [x] Power BI 儀表板（`powerbi/Airbnb_Taipei_Quality.pbix`，作品頁公開內嵌）  
- [x] 作品頁填入實際數字與建議  

---

## License

分析程式碼可依你上傳 GitHub 時選定的授權（例如 MIT）釋出；**原始 Airbnb／Inside Airbnb 資料檔不包含在本倉庫中**。
