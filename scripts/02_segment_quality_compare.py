# -*- coding: utf-8 -*-
"""
分群品質對比：
1) 行政區
2) 價格帶
3) 住宿類型(歸類成四類：住宅/民宿/合宿/飯店）
並標出偏低分群
"""

import os
import json
import sys
import pandas as pd

# 專案路徑與設定檔位置
script_dir = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(script_dir)
config_path = os.path.join(ROOT, "config.local.json")

# 讀取 JSON 檔轉成字典
def load_config():
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)

# 讀取 listings（只讀取需要的欄位）
def read_listings(path):
    usecols = [
        "id",
        "neighbourhood_cleansed",
        "price",
        "property_type",
        "room_type",
        "number_of_reviews",
        "number_of_reviews_ltm",
        "review_scores_rating",
        "host_is_superhost",
    ]
    return pd.read_csv(path, usecols=usecols, encoding="utf-8")

# 將價格欄未轉成數字
def clean_price_to_numeric(series):
    text_series = series.astype(str) # 先轉成字串
    only_number_text = text_series.str.replace(r"[^\d.]", "", regex=True) #移除多餘字元（如 $ 及 ,）
    number_series = pd.to_numeric(only_number_text, errors="coerce") # 轉成數字，轉失敗就變成 NaN
    return number_series

# 住宿類型歸類成四大類
# 優先順序：合宿 > 飯店 > 民宿 > 住宅（先判 shared room，避免被 hotel/hostel/minsu 等關鍵字蓋掉）
def map_stay_category(property_type, room_type):
    p = (property_type or "").lower()
    r = (room_type or "").lower()
    # 合宿類
    if "shared room" in p or "shared room" in r:
        return "合宿類"
    # 飯店類
    if any(k in p for k in ["hotel", "hostel", "aparthotel", "boutique hotel", "serviced apartment", "resort", "ryokan", "kezhan", "motel", "inn"]):
        return "飯店類"
    # 民宿類
    if any(k in p for k in ["minsu", "bed and breakfast", "guesthouse", "kezhan", "ryokan"]):
        return "民宿類"
    # 住宅類
    return "住宅類"

# 計算各群組的品質指標
def summarize_group(df_group, threshold):
    # 先找出有評分的資料列
    rated_mask = df_group["review_scores_rating"].notna()
    rated_df = df_group[rated_mask]
    rated_n = len(rated_df)
    
    n_listings = len(df_group) # 房源數
    review_coverage = (df_group["number_of_reviews"] >= 1).mean() # 有評價覆蓋率（至少 1 則評價）
    ltm_active_rate = (df_group["number_of_reviews_ltm"] >= 1).mean() # 近一年活躍率（近一年至少 1 則評價）
    
    # 平均評分、低分率（只用有評分資料）
    if rated_n > 0:
        avg_rating = rated_df["review_scores_rating"].mean()
        low_score_rate = (rated_df["review_scores_rating"] < threshold).mean()
    else:
        avg_rating = float("nan")
        low_score_rate = float("nan")
    
    superhost_rate = df_group["is_superhost"].mean() # 超讚房東率
    
    # 組成結果
    summary = {
        "n_listings": int(n_listings),
        "rating_nonnull_n": int(rated_n),
        "review_coverage": review_coverage,
        "ltm_active_rate": ltm_active_rate,
        "avg_rating": avg_rating,
        "low_score_rate": low_score_rate,
        "superhost_rate": superhost_rate,
    }

    return pd.Series(summary)


# 標註偏低群組(有評價且評分低於全市平均)
def mark_underperforming_groups(df_summary, city_avg_rating, city_low_score_rate, cfg):
    # 從設定檔讀出門檻
    min_rated_n = int(cfg["min_rated_n"])   # 至少要有幾筆(30筆以上)評分才納入比較
    gap_th = float(cfg["flag_avg_rating_gap"])   # 評分比全市平均評分低多少(0.05分以上)才算偏低
    lift_th = float(cfg["flag_low_score_rate_lift"])   # 低分相對倍率門檻（1.3 倍以上）才算高低分率

    out = df_summary.copy()

    # 加上全市基準欄位(平均評分、低分率)
    out["city_avg_rating"] = city_avg_rating
    out["city_low_score_rate"] = city_low_score_rate
    # 加上與全市的平均評分差距、低分率差距倍數欄位
    out["avg_rating_gap"] = out["avg_rating"] - out["city_avg_rating"]
    out["low_score_rate_lift"] = out["low_score_rate"] / out["city_low_score_rate"]
    # 有評分房源數 ≥ 30 才納入偏低比較
    out["is_eligible"] = out["rating_nonnull_n"] >= min_rated_n
    # 兩個偏低條件(評分比全市低0.05分以上、低分相對倍率 ≥ 1.3)
    cond_low_avg = out["avg_rating"] <= (out["city_avg_rating"] - gap_th)
    cond_high_low = out["low_score_rate"] >= (out["city_low_score_rate"] * lift_th)
    # 有評分房源數 ≥ 30，且符合任一偏低條件
    out["is_underperforming"] = out["is_eligible"] & (cond_low_avg | cond_high_low)
    
    # 標註偏低原因
    reasons = []
    for i in range(len(out)):
        row = out.iloc[i]
        if not row["is_underperforming"]:
            reasons.append("")
            continue
        low_avg = row["avg_rating"] <= (row["city_avg_rating"] - gap_th)
        high_low = row["low_score_rate"] >= (row["city_low_score_rate"] * lift_th)
        if low_avg and high_low:
            reasons.append("低均分且高低分率")
        elif low_avg:
            reasons.append("低均分")
        elif high_low:
            reasons.append("高低分率")
        else:
            reasons.append("")
    out["flag_reason"] = reasons

    # 加上百分比與小數位數欄位
    out["review_coverage_pct"] = (out["review_coverage"] * 100).round(2)
    out["ltm_active_rate_pct"] = (out["ltm_active_rate"] * 100).round(2)
    out["low_score_rate_pct"] = (out["low_score_rate"] * 100).round(2)
    out["superhost_rate_pct"] = (out["superhost_rate"] * 100).round(2)
    out["avg_rating"] = out["avg_rating"].round(3)
    out["avg_rating_gap"] = out["avg_rating_gap"].round(3)
    out["low_score_rate_lift"] = out["low_score_rate_lift"].round(3)

    return out


# 依分群欄位分組，計算品質指標，標出偏低分群，並加上欄位順序
def build_segment_table(df, dim_name, group_col, threshold, city_avg_rating, city_low_score_rate, cfg):
    # 依傳入的分群欄位分組（一次一種：行政區、價格帶、住宿類型）
    grouped_obj = df.groupby(group_col, dropna=False)  # dropna=False:遺漏值(NaN)也納入分組
    # 每一組各自計算品質指標(平均評分、低分率、有評價覆蓋率、近一年活躍率、超讚房東率)
    def calc_one_group(g):
        return summarize_group(g, threshold)
    # 將每個分群的品質指標彙總成表
    summary = grouped_obj.apply(calc_one_group, include_groups=False)  # include_groups=False:不包含分組名稱
    # 把分組名稱從 index 變回一般欄位
    summary = summary.reset_index()
    # 分組欄位名稱統一改成 segment_value (以行政區為例:原欄位名稱叫 neighbourhood_cleansed，改叫 segment_value)
    summary = summary.rename(columns={group_col: "segment_value"})
    # 記下這張表是哪一種分群
    summary["segment_dim"] = dim_name
    # NaN 改成 Unknown
    summary["segment_value"] = summary["segment_value"].fillna("Unknown")
    # 跟全市基準比較，標出偏低分群
    flagged = mark_underperforming_groups(summary, city_avg_rating, city_low_score_rate, cfg)  # 傳入全市基準、設定檔
    # 欄位順序統一(依分群欄位、品質指標、全市基準、偏低分群標註)
    cols = [
        "segment_dim", "segment_value",
        "n_listings", "rating_nonnull_n",
        "review_coverage", "review_coverage_pct",
        "ltm_active_rate", "ltm_active_rate_pct",
        "avg_rating", "avg_rating_gap",
        "low_score_rate", "low_score_rate_pct", "low_score_rate_lift",
        "superhost_rate", "superhost_rate_pct",
        "city_avg_rating", "city_low_score_rate",
        "is_eligible", "is_underperforming", "flag_reason",
    ]
    return flagged[cols]



def main():
    # 讀設定檔、確認 listings.csv 存在
    cfg = load_config()
    data_path = os.path.join(ROOT, cfg["listings_csv"])
    out_dir = os.path.join(ROOT, cfg["output_dir"])
    if not os.path.exists(data_path):
        print("找不到 listings.csv：", data_path)
        sys.exit(1)
    os.makedirs(out_dir, exist_ok=True)

    # 讀取分析門檻
    threshold = float(cfg["low_score_threshold"])  # 低分門檻（例如 4.5）
    edges = cfg["price_band_edges"]   # 價格帶切點(0, 1500, 2500, 4000, 999999)
    labels = cfg["price_band_labels"]   # 價格帶名稱("<=1500", "1501-2500", "2501-4000", ">4000")
    # 切點數量要等於名稱數量+1
    if len(edges) != len(labels) + 1:  
        print("price_band_edges 與 price_band_labels 長度不符")
        sys.exit(1)

    # 讀取房源資料(只讀取需要的欄位)
    df = read_listings(data_path)

    # 清洗欄位(欄位類型轉為數字，遺漏值改成0/NaN)
    # NaN 是數字裡的缺值(Unknown 是文字裡的缺值，不能被計算)
    df["number_of_reviews"] = pd.to_numeric(df["number_of_reviews"], errors="coerce").fillna(0) # 評價數(遺漏值改成0)
    df["number_of_reviews_ltm"] = pd.to_numeric(df["number_of_reviews_ltm"], errors="coerce").fillna(0) # 近一年評價數(遺漏值改成0)
    df["review_scores_rating"] = pd.to_numeric(df["review_scores_rating"], errors="coerce") # 評分(遺漏值改成NaN，0 會被當成超低分，平均評分被拉低，低分率也被灌高)
    df["is_superhost"] = df["host_is_superhost"] == "t" # 是否為超讚房東(True/False)
    df["price_num"] = clean_price_to_numeric(df["price"]) # 價格(遺漏值改成NaN，0會被切進<=1500價格帶，所以要用NaN)

    # 切價格帶；沒有價格的改成 Unknown
    df["price_band"] = pd.cut(
        df["price_num"],
        bins=edges,
        labels=labels,
        right=True,  #區間不包含左邊、包含右邊(例如1500-2500，不包含1500、包含2500，也就是1501-2500)
        include_lowest=True,   #最左邊的切點 0 也要算進去
    )
    df["price_band"] = df["price_band"].astype("object").fillna("Unknown") 

    # 住宿類型歸成四類
    stay_categories = []
    for i in range(len(df)):
        row = df.iloc[i]
        stay_type = map_stay_category(row["property_type"], row["room_type"])
        stay_categories.append(stay_type)
    df["stay_category"] = stay_categories

    # 計算全市基準（只用有評分的房源）
    has_rating = df["review_scores_rating"].notna()  # 有評分的房源
    rated_df = df[has_rating]  # 有評分的房源表
    city_avg_rating = rated_df["review_scores_rating"].mean()  # 全市平均評分
    city_low_score_rate = (rated_df["review_scores_rating"] < threshold).mean()  # 全市低分率

    # 做三種分群表(一次一種：行政區、價格帶、住宿類型)
    district_tbl = build_segment_table(
        df, "district", "neighbourhood_cleansed",
        threshold, city_avg_rating, city_low_score_rate, cfg
    )
    price_tbl = build_segment_table(
        df, "price_band", "price_band",
        threshold, city_avg_rating, city_low_score_rate, cfg
    )
    stay_tbl = build_segment_table(
        df, "stay_category", "stay_category",
        threshold, city_avg_rating, city_low_score_rate, cfg
    )

    # 存成 CSV(三種分群表、偏低分群表)
    district_path = os.path.join(out_dir, "pandas_02_district_quality_summary.csv")
    price_path = os.path.join(out_dir, "pandas_02_price_band_quality_summary.csv")
    stay_path = os.path.join(out_dir, "pandas_02_stay_category_quality_summary.csv")
    all_seg_path = os.path.join(out_dir, "pandas_02_underperforming_segments.csv")

    district_tbl.to_csv(district_path, index=False, encoding="utf-8-sig")
    price_tbl.to_csv(price_path, index=False, encoding="utf-8-sig")
    stay_tbl.to_csv(stay_path, index=False, encoding="utf-8-sig")

    # 三張表合併，偏低分群排前面
    all_seg = pd.concat([district_tbl, price_tbl, stay_tbl], ignore_index=True)
    # 偏低分群排前面(順序:偏低分群，低分率，平均評分)
    all_seg = all_seg.sort_values(
        by=["is_underperforming", "low_score_rate", "avg_rating"],
        ascending=[False, False, True]
    )
    all_seg.to_csv(all_seg_path, index=False, encoding="utf-8-sig")

    # 在終端機檢查輸出
    print("=== 行政區/價格帶/住宿類型分群表、偏低分群表以存成CSV檔 ===")
    print(district_path)
    print(price_path)
    print(stay_path)
    print(all_seg_path)

    print("\n=== 顯示偏低分群前20筆資料 ===") 
    show_cols = [
        "segment_dim", "segment_value", "n_listings", "rating_nonnull_n",
        "avg_rating", "low_score_rate_pct", "low_score_rate_lift", "flag_reason"
    ]
    underperforming = all_seg[all_seg["is_underperforming"]]
    print(underperforming[show_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()