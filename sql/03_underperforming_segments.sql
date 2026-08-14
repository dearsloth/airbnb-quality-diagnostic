-- 03_underperforming_segments.sql
-- 只留偏低分群（對齊 output/pandas_02_underperforming_segments.csv 裡 is_underperforming = True）
-- 執行前須先跑 00_load.sql；請在專案根目錄執行。
--
-- 常數必須與 config.local.json 一致：
--
--   參數                      值     用途
--   min_rated_n               30     有評分房源數門檻
--   flag_avg_rating_gap       0.05   低均分
--   flag_low_score_rate_lift  1.3    高低分率
--
-- 做法：把 02 整段查詢包進 CTE seg_all，再加 WHERE。
-- 預期至少：飯店類、南港區、<=1500（Unknown 若也被標，與 pandas 一致即可）


-- city / stacked / seg 與 02 相同
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

stacked AS (
    SELECT
        'district' AS segment_dim,
        COALESCE(neighbourhood_cleansed, 'Unknown') AS segment_value,
        number_of_reviews,
        number_of_reviews_ltm,
        review_scores_rating,
        is_superhost
    FROM listings_clean

    UNION ALL

    SELECT
        'price_band' AS segment_dim,
        price_band AS segment_value,
        number_of_reviews,
        number_of_reviews_ltm,
        review_scores_rating,
        is_superhost
    FROM listings_clean

    UNION ALL

    SELECT
        'stay_category' AS segment_dim,
        stay_category AS segment_value,
        number_of_reviews,
        number_of_reviews_ltm,
        review_scores_rating,
        is_superhost
    FROM listings_clean
),

seg AS (
    SELECT
        segment_dim,
        segment_value,
        COUNT(*) AS n_listings,
        COUNT(review_scores_rating) AS rating_nonnull_n,
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
    GROUP BY segment_dim, segment_value
),

-- 把 02 的最終 SELECT 包成一張暫存表
seg_all AS (
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
        (seg.rating_nonnull_n >= 30) AS is_eligible,
        (
            seg.rating_nonnull_n >= 30
            AND (
                seg.avg_rating <= city.city_avg_rating - 0.05
                OR seg.low_score_rate >= city.city_low_score_rate * 1.3
            )
        ) AS is_underperforming,
        CASE
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
)

SELECT *
FROM seg_all
WHERE is_underperforming = TRUE
ORDER BY low_score_rate DESC, avg_rating ASC;
