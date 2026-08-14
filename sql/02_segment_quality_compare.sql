-- 02_segment_quality_compare.sql
-- 執行前須先跑 00_load.sql；請在專案根目錄執行。
--
-- 行政區／價格帶／住宿類型分群品質對比（對齊 scripts/02_segment_quality_compare.py）
--
--
-- 常數必須與 config.local.json 一致：
--
--   參數                      值                      用途
--   low_score_threshold       4.5                     低分（rating < 4.5）
--   min_rated_n               30                      有評分房源數門檻
--   flag_avg_rating_gap       0.05                    低均分
--   flag_low_score_rate_lift  1.3                     高低分率
--   價格切點                  0 / 1500 / 2500 / 4000  已在 00_load 切好
--
-- 指標公式與 01 全市彙總相同，只是多了分組。


-- ============================================================
-- 拆成三個 CTE
-- city：全市基準（只算有評分房源，與 01 的 rated_rows 相同）
-- stacked：同一批房源，複製成三份（行政區／價格帶／房型）
-- seg：依「哪一種分群 + 組名」GROUP BY，算出每組指標
-- 最後把每組數字接到全市基準，算出差距、是否偏低
-- ============================================================
WITH city AS (
    SELECT
        AVG(review_scores_rating) AS city_avg_rating,
        AVG(
            CASE
                WHEN review_scores_rating < 4.5 THEN 1.0
                ELSE 0.0
            END
        ) AS city_low_score_rate
    FROM listings_clean
    WHERE review_scores_rating IS NOT NULL
),

-- 每一筆房源會出現 3 次：一次當行政區、一次當價格帶、一次當房型
stacked AS (
    SELECT
        'district' AS segment_dim,
        COALESCE(neighbourhood_cleansed, 'Unknown') AS segment_value,  -- 行政區
        number_of_reviews,  -- 評論數
        number_of_reviews_ltm,  -- 去年評論數
        review_scores_rating,  -- 評分
        is_superhost  -- 超讚房東
    FROM listings_clean

    UNION ALL  -- 上下的 SELECT 資料接在一起

    SELECT
        'price_band' AS segment_dim,
        price_band AS segment_value,  -- 價格帶 (在 00_load 已切好 Unknown )
        number_of_reviews,
        number_of_reviews_ltm,
        review_scores_rating,
        is_superhost
    FROM listings_clean

    UNION ALL  -- 上下的 SELECT 資料接在一起

    SELECT
        'stay_category' AS segment_dim,
        stay_category AS segment_value,  -- 住宿類型 (不會有 Unknown )
        number_of_reviews,
        number_of_reviews_ltm,
        review_scores_rating,
        is_superhost
    FROM listings_clean
),

-- 公式與 01 相同；AVG(評分) 會自動跳過 NULL
seg AS (
    SELECT
        segment_dim,
        segment_value,
        COUNT(*) AS n_listings,
        COUNT(review_scores_rating) AS rating_nonnull_n, --

        AVG(
            CASE
                WHEN number_of_reviews >= 1 THEN 1.0
                ELSE 0.0
            END
        ) AS review_coverage,

        AVG(
            CASE
                WHEN number_of_reviews_ltm >= 1 THEN 1.0
                ELSE 0.0
            END
        ) AS ltm_active_rate,

        AVG(review_scores_rating) AS avg_rating,

        -- 沒評分 → NULL，AVG 會跳過，分母只剩有評分的
        AVG(
            CASE
                WHEN review_scores_rating IS NULL THEN NULL
                WHEN review_scores_rating < 4.5 THEN 1.0
                ELSE 0.0
            END
        ) AS low_score_rate,

        AVG(
            CASE
                WHEN is_superhost THEN 1.0
                ELSE 0.0
            END
        ) AS superhost_rate
    FROM stacked
    GROUP BY segment_dim, segment_value  -- 相同分組的資料收成一列，再算 COUNT／AVG (如行政區-南港區 10 筆資料收成一列，再算 COUNT／AVG)
)

SELECT
    seg.segment_dim,
    seg.segment_value,
    seg.n_listings,
    seg.rating_nonnull_n,
    seg.review_coverage,
    ROUND(seg.review_coverage * 100, 2) AS review_coverage_pct,
    seg.ltm_active_rate,
    ROUND(seg.ltm_active_rate * 100, 2) AS ltm_active_rate_pct,
    ROUND(seg.avg_rating, 3) AS avg_rating,
    ROUND(seg.avg_rating - city.city_avg_rating, 3) AS avg_rating_gap,
    seg.low_score_rate,
    ROUND(seg.low_score_rate * 100, 2) AS low_score_rate_pct,
    ROUND(seg.low_score_rate / city.city_low_score_rate, 3) AS low_score_rate_lift,
    seg.superhost_rate,
    ROUND(seg.superhost_rate * 100, 2) AS superhost_rate_pct,
    city.city_avg_rating,
    city.city_low_score_rate,

    -- 有評分數(非空值)至少 30 筆才拿來比
    (seg.rating_nonnull_n >= 30) AS is_eligible,

    -- 有評分房源數 ≥ 30，且（均分過低 或 低分率過高）
    (
        seg.rating_nonnull_n >= 30
        AND (
            seg.avg_rating <= city.city_avg_rating - 0.05
            OR seg.low_score_rate >= city.city_low_score_rate * 1.3
        )
    ) AS is_underperforming,

    CASE
        -- 有評分房源數不足 30，或分數沒問題
        WHEN NOT (
            seg.rating_nonnull_n >= 30
            AND (
                seg.avg_rating <= city.city_avg_rating - 0.05
                OR seg.low_score_rate >= city.city_low_score_rate * 1.3
            )
        ) THEN ''
        WHEN seg.avg_rating <= city.city_avg_rating - 0.05
         AND seg.low_score_rate >= city.city_low_score_rate * 1.3
            THEN '低均分且高低分率'
        WHEN seg.avg_rating <= city.city_avg_rating - 0.05
            THEN '低均分'
        ELSE '高低分率'
    END AS flag_reason
FROM seg, city
ORDER BY is_underperforming DESC, low_score_rate DESC, avg_rating ASC;
