-- 00_load.sql
-- 只做一次清洗：讀 CSV → 轉型 → 切價格帶 → 歸類房型。
-- 請在專案根目錄執行（相對路徑才找得到 airbnb_Taiwan/listings.csv）。
--
-- 常數必須與 config.local.json 一致（改設定時請同步改 SQL）：
--
--   參數                      值                    用途
--   low_score_threshold       4.5                   低分
--   min_rated_n               30                    有評分房源數門檻
--   flag_avg_rating_gap       0.05                  低均分
--   flag_low_score_rate_lift  1.3                   高低分率
--   價格切點                  0 / 1500 / 2500 / 4000
--                             與 pd.cut(right=True, include_lowest=True) 相同
--                             labels: <=1500 / 1501-2500 / 2501-4000 / >4000
--                             price_band_edges: [0, 1500, 2500, 4000, 999999]
--
-- 本檔負責：載入 listings、清洗價格、切價格帶、歸類房型。


-- =============================================================
-- 第一步：把 CSV 讀進來，存成資料表 listings_raw
-- sample_size = -1 代表「看完全部列再決定欄位型別」
-- （如果沒設定sample_size = -1，DuckDB 預設只抽前面幾列猜型別，可能把評分、價格誤判成文字）
-- =============================================================
CREATE OR REPLACE TABLE listings_raw AS
SELECT
    id,                       -- 房源 ID
    neighbourhood_cleansed,   -- 鄰里
    property_type,            -- 房型 (飯店、民宿、住宅等大類)
    room_type,                -- 房間類型 (獨立房間、共用空間等)
    number_of_reviews,        -- 評論數
    number_of_reviews_ltm,    -- 去年評論數
    review_scores_rating,     -- 評分
    host_is_superhost,        -- 超讚房東
    price                     -- 價格
FROM read_csv_auto(
    'airbnb_Taiwan/listings.csv',
    header = true,
    sample_size = -1
);


-- ============================================================
-- 第二步：清洗後的 VIEW（後面 01 / 02 / 03 都查這張）
-- (VIEW：不另存資料，是「一張會自動重算的虛擬表」)
-- 用 CTE (暫存結果集，用 WITH 宣告) 分兩小步，先算出 price_num，再切價格帶（比較好讀）
-- ============================================================
CREATE OR REPLACE VIEW listings_clean AS
WITH step1 AS (
    SELECT
        id,
        neighbourhood_cleansed,
        property_type,
        room_type,

        -- 評論數：遺漏值當 0（沒評論 = 0 則）
        -- COALESCE(x, 0)：若 x 是 NULL，改成 0
        -- 用 BIGINT (整數型別)
        COALESCE(TRY_CAST(number_of_reviews AS BIGINT), 0)
            AS number_of_reviews,
        COALESCE(TRY_CAST(number_of_reviews_ltm AS BIGINT), 0)
            AS number_of_reviews_ltm,

        -- 評分：遺漏值保持 NULL（不填 0，否則會被當成超低分）
        -- 用 DOUBLE (浮點數型別)
        TRY_CAST(review_scores_rating AS DOUBLE)
            AS review_scores_rating,

        -- 超讚房東：CSV 裡 t = 是、f / 空白 = 不是
        CASE
            WHEN host_is_superhost = 't' THEN TRUE
            ELSE FALSE
        END AS is_superhost,

        -- 價格：$1,200.00 → 拿掉 $ 和逗號 → 1200.00
        -- 轉失敗（空白、亂碼）→ NULL( 數字缺值)，下一步會變成 Unknown(文字缺值)
        -- VARCHAR(字串型別) 轉成 DOUBLE(浮點數型別)
        -- 不要填 0，否則會被切進 <=1500
        TRY_CAST(
            REPLACE(REPLACE(CAST(price AS VARCHAR), '$', ''), ',', '')
            AS DOUBLE
        ) AS price_num,

        -- 房型歸類：順序必須與 scripts/02_segment_quality_compare.py 相同
        -- 合宿 → 飯店 → 民宿 → 住宅（先判 shared room，避免被 hotel 蓋掉）
        CASE
            WHEN LOWER(COALESCE(property_type, '')) LIKE '%shared room%'
              OR LOWER(COALESCE(room_type, '')) LIKE '%shared room%'
                THEN '合宿類'

            WHEN LOWER(COALESCE(property_type, '')) LIKE '%hotel%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%hostel%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%aparthotel%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%boutique hotel%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%serviced apartment%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%resort%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%ryokan%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%kezhan%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%motel%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%inn%'
                THEN '飯店類'

            WHEN LOWER(COALESCE(property_type, '')) LIKE '%minsu%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%bed and breakfast%'
              OR LOWER(COALESCE(property_type, '')) LIKE '%guesthouse%'
                THEN '民宿類'

            ELSE '住宅類'
        END AS stay_category
    FROM listings_raw
)
SELECT
    id,
    neighbourhood_cleansed,
    property_type,
    room_type,
    number_of_reviews,
    number_of_reviews_ltm,
    review_scores_rating,
    is_superhost,
    price_num,
    stay_category,

    -- 價格帶：對齊 pd.cut(right=True, include_lowest=True)
    --   [0, 1500]      → <=1500
    --   (1500, 2500]   → 1501-2500
    --   (2500, 4000]   → 2501-4000
    --   (4000, +)      → >4000
    -- 沒有價格（NULL）→ Unknown（不要當 0）
    CASE
        WHEN price_num IS NULL THEN 'Unknown'
        WHEN price_num <= 1500 THEN '<=1500'
        WHEN price_num <= 2500 THEN '1501-2500'
        WHEN price_num <= 4000 THEN '2501-4000'
        ELSE '>4000'
    END AS price_band
FROM step1;
