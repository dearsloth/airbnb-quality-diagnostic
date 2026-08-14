-- 01_city_quality_summary.sql
-- 執行前須先跑 00_load.sql；請在專案根目錄執行。
--
-- 全市品質彙總（對齊 scripts/01_city_quality_summary.py）
--
-- 常數必須與 config.local.json 一致：
--
--   參數                 值     用途
--   low_score_threshold  4.5    低分（rating < 4.5）

-- ============================================================
-- 拆成兩個 CTE ，分母分開算
-- all_rows(分母為全部房源)：算覆蓋率、活躍率、超讚房東率
-- rated_rows(分母為有評分房源)：算均分、低分率、有評分房源數
-- ============================================================
WITH all_rows AS (
    SELECT
        COUNT(*) AS n_listings,

        -- 有至少 1 則評論的占比
        AVG(
            CASE
                WHEN number_of_reviews >= 1 THEN 1.0
                ELSE 0.0
            END
        ) AS review_coverage,

        -- 近一年至少 1 則評論的占比
        AVG(
            CASE
                WHEN number_of_reviews_ltm >= 1 THEN 1.0
                ELSE 0.0
            END
        ) AS ltm_active_rate,

        -- 超讚房東占比
        AVG(
            CASE
                WHEN is_superhost THEN 1.0
                ELSE 0.0
            END
        ) AS superhost_rate
    FROM listings_clean
),

rated_rows AS (
    SELECT
        --下面的  WHERE 已去掉 NULL，所以 COUNT(*) 就是非空筆數
        COUNT(*) AS rating_nonnull_n,

        -- 均分
        -- SQL 的 AVG 會自動跳過 NULL；這裡已先過濾
        AVG(review_scores_rating) AS avg_rating,

        -- 低分率：評分 < 4.5 的占比
        AVG(
            CASE
                WHEN review_scores_rating < 4.5 THEN 1.0
                ELSE 0.0
            END
        ) AS low_score_rate
    FROM listings_clean
    WHERE review_scores_rating IS NOT NULL
)

SELECT
    'Taipei' AS city,
    all_rows.n_listings,
    all_rows.review_coverage,
    all_rows.ltm_active_rate,
    ROUND(rated_rows.avg_rating, 3) AS avg_rating,  -- ROUND(..., 3)：四捨五入到小數點第3位
    4.5 AS low_score_threshold,
    rated_rows.low_score_rate,
    all_rows.superhost_rate,
    rated_rows.rating_nonnull_n,
    'airbnb_Taiwan/listings.csv' AS source_file,
    -- 轉成百分比
    ROUND(all_rows.review_coverage * 100, 2) AS review_coverage_pct,
    ROUND(all_rows.ltm_active_rate * 100, 2) AS ltm_active_rate_pct,
    ROUND(rated_rows.low_score_rate * 100, 2) AS low_score_rate_pct,
    ROUND(all_rows.superhost_rate * 100, 2) AS superhost_rate_pct
FROM all_rows, rated_rows;
