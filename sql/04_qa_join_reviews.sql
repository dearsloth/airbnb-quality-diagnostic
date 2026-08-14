-- 04_qa_join_reviews.sql
-- 執行前須先跑 00_load.sql；請在專案根目錄執行。
--
-- JOIN 核對：listings.number_of_reviews 是否等於 reviews 表實際則數
--
-- 這條「不要」拿來算 01／02 的有評率、活躍率。
-- 品質指標以 listings 欄位為準；本檔只做資料品質檢查。
-- 關聯鍵：listings.id = reviews.listing_id


-- ============================================================
-- 第一步：讀入評論明細（sample_size = -1：看完全部列再定型別）
-- ============================================================
CREATE OR REPLACE TABLE reviews_raw AS
SELECT
    id,
    listing_id
FROM read_csv_auto(
    'airbnb_Taiwan/reviews.csv',
    header = true,
    sample_size = -1
);


-- ============================================================
-- 第二步：LEFT JOIN 核對
--   子查詢：每間房在 reviews 裡有幾則
--   有房源、沒評論 → review_n 是 NULL → 當成 0
--   相符：listings.number_of_reviews = 實際則數
-- ============================================================
SELECT
    COUNT(*) AS n_listings,

    -- 兩邊則數相同的房源占比（1.0 = 全部相符）
    AVG(
        CASE
            WHEN l.number_of_reviews = COALESCE(r.review_n, 0) THEN 1.0
            ELSE 0.0
        END
    ) AS review_count_match_rate,

    -- 不相符的房源數（方便抽查）
    SUM(
        CASE
            WHEN l.number_of_reviews = COALESCE(r.review_n, 0) THEN 0
            ELSE 1
        END
    ) AS n_mismatch
FROM listings_clean AS l
LEFT JOIN (
    SELECT
        listing_id,
        COUNT(*) AS review_n
    FROM reviews_raw
    GROUP BY listing_id
) AS r
    ON l.id = r.listing_id;
