# -*- coding: utf-8 -*-
"""
一鍵跑 SQL：00 載入 → 01 全市 → 02 分群 → 03 偏低分群 → 04 JOIN 核對
最後用 pandas 已產出的 CSV 對帳(把 pandas 及 SQL 分別算出來的數字擺在一起核對)。

請在專案根目錄執行：
    python scripts/04_run_sql.py

腳本會自己切到專案根目錄，SQL 裡的相對路徑
airbnb_Taiwan/listings.csv 才找得到。
"""
import os
import sys

import duckdb
import pandas as pd

# 專案路徑（此檔在 scripts/，上一層才是根目錄）
script_dir = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(script_dir)

# 一定要先切到根目錄，DuckDB 才讀得到相對路徑
os.chdir(ROOT)

listings_path = os.path.join(ROOT, "airbnb_Taiwan", "listings.csv")
reviews_path = os.path.join(ROOT, "airbnb_Taiwan", "reviews.csv")
out_dir = os.path.join(ROOT, "output")


def check_one(name, pandas_value, sql_value, ok):
    """印出一項對帳，並更新是否全部通過。"""
    same = pandas_value == sql_value
    mark = "OK" if same else "FAIL"
    print(" ", name, "pandas=", pandas_value, "SQL=", sql_value, mark)
    if not same:
        ok = False
    return ok


def reconcile_with_pandas():
    """
    把 SQL 剛存的 CSV，跟先前 pandas 腳本的 CSV 對一下。
    須先跑過 scripts/01、02（才會有 pandas_01_…、pandas_02_… 等檔）。
    """
    print("\n=== 步驟 8：與 pandas CSV 對帳 ===")

    city_p_path = os.path.join(out_dir, "pandas_01_city_quality_summary.csv")
    city_s_path = os.path.join(out_dir, "sql_01_city_quality_summary.csv")
    seg_p_path = os.path.join(out_dir, "pandas_02_underperforming_segments.csv")
    seg_s_path = os.path.join(out_dir, "sql_03_underperforming_segments.csv")

    missing = []
    for p in [city_p_path, city_s_path, seg_p_path, seg_s_path]:
        if not os.path.exists(p):
            missing.append(p)
    if missing:
        print("找不到對帳檔，請先跑 pandas 腳本 01／02：")
        for p in missing:
            print(" ", p)
        sys.exit(1)

    ok = True

    # ---- 全市 ----
    city_p = pd.read_csv(city_p_path)
    city_s = pd.read_csv(city_s_path)
    print("全市：")
    ok = check_one(
        "n_listings",
        int(city_p["n_listings"].iloc[0]),
        int(city_s["n_listings"].iloc[0]),
        ok,
    )
    ok = check_one(
        "avg_rating（小數 3 位）",
        round(float(city_p["avg_rating"].iloc[0]), 3),
        round(float(city_s["avg_rating"].iloc[0]), 3),
        ok,
    )
    ok = check_one(
        "low_score_rate（小數 5 位）",
        round(float(city_p["low_score_rate"].iloc[0]), 5),
        round(float(city_s["low_score_rate"].iloc[0]), 5),
        ok,
    )
    ok = check_one(
        "rating_nonnull_n",
        int(city_p["rating_nonnull_n"].iloc[0]),
        int(city_s["rating_nonnull_n"].iloc[0]),
        ok,
    )

    # ---- 偏低分群 ----
    seg_p = pd.read_csv(seg_p_path)
    seg_s = pd.read_csv(seg_s_path)
    # pandas 那份含全部組，只留標成偏低的
    p_keys = set(
        zip(
            seg_p.loc[seg_p["is_underperforming"], "segment_dim"],
            seg_p.loc[seg_p["is_underperforming"], "segment_value"],
        )
    )
    s_keys = set(zip(seg_s["segment_dim"], seg_s["segment_value"]))

    print("偏低分群：")
    print("  pandas", sorted(p_keys))
    print("  SQL   ", sorted(s_keys))
    if p_keys == s_keys:
        print("  組別完全相同 OK")
    else:
        print("  組別不同 FAIL")
        print("  只在 pandas", sorted(p_keys - s_keys))
        print("  只在 SQL   ", sorted(s_keys - p_keys))
        ok = False

    # 至少要有這三組（Unknown 可有可無，有的話兩邊都要有）
    must = {
        ("stay_category", "飯店類"),
        ("district", "南港區"),
        ("price_band", "<=1500"),
    }
    if must.issubset(s_keys):
        print("  必要三組（飯店類／南港區／<=1500）都在 SQL OK")
    else:
        print("  必要三組缺", sorted(must - s_keys), "FAIL")
        ok = False

    if ok:
        print("\n對帳通過：SQL 與 pandas 數字一致。")
    else:
        print("\n對帳失敗：請回頭查 00 清洗或 01／02／03 公式。")
        sys.exit(1)


def main():
    if not os.path.exists(listings_path):
        print("找不到 listings.csv：", listings_path)
        print("請先把資料放到 airbnb_Taiwan/，並在專案根目錄跑本腳本")
        sys.exit(1)

    if not os.path.exists(reviews_path):
        print("找不到 reviews.csv：", reviews_path)
        print("04_qa_join_reviews.sql 需要這份檔（JOIN 核對用）")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    # 同一個連線跑完全部，00 建的 listings_clean 後面才用得到
    con = duckdb.connect()

    sql_files = [
        "sql/00_load.sql",
        "sql/01_city_quality_summary.sql",
        "sql/02_segment_quality_compare.sql",
        "sql/03_underperforming_segments.sql",
        "sql/04_qa_join_reviews.sql",
    ]

    for path in sql_files:
        print("\n===", path, "===")
        sql_text = open(path, encoding="utf-8").read()
        result = con.execute(sql_text)

        # 00 只有 CREATE TABLE / VIEW，沒有查詢結果可存
        if path.endswith("00_load.sql"):
            print("已建立 listings_raw、listings_clean")
            continue

        df = result.fetchdf()
        print(df.to_string(index=False))

        # sql/01_city_….sql → sql_01_city_….csv
        out_name = "sql_" + os.path.basename(path).replace(".sql", ".csv")
        out_path = os.path.join(out_dir, out_name)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print("Saved:", out_path)

    print("\nSQL 跑完。品質指標請看 output/sql_01、sql_02、sql_03 的 CSV；sql_04 只是 JOIN 核對。")
    reconcile_with_pandas()


if __name__ == "__main__":
    main()
