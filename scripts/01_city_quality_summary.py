# -*- coding: utf-8 -*-
"""
全市品質彙總表

路徑與參數請放在 config.local.json（由 config.example.json 複製修改）
"""
import os
import json
import sys

import pandas as pd

# 專案路徑與設定檔位置
script_dir = os.path.dirname(os.path.abspath(__file__))  # 此檔案所在的資料夾(scripts)
ROOT = os.path.dirname(script_dir)  # 專案目錄(scripts 的上一層)

config_path = os.path.join(ROOT, "config.local.json")


# 讀取 JSON 檔轉成字典
def load_config():
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


# 讀取 listings（只讀取需要的欄位）
def read_listings(path):
    usecols = [
        "id",
        "number_of_reviews",
        "number_of_reviews_ltm",
        "review_scores_rating",
        "host_is_superhost",
    ]
    df = pd.read_csv(path, usecols=usecols, encoding="utf-8")
    return df


def main():
    # 讀設定
    cfg = load_config()

    # 路徑接到專案根目錄
    data_path = os.path.join(ROOT, cfg["listings_csv"])
    out_dir = os.path.join(ROOT, cfg["output_dir"])
    out_path = os.path.join(out_dir, cfg["city_summary_filename"])
    threshold = float(cfg["low_score_threshold"])
    city = cfg["city_name"]

    # 確認資料檔存在
    if not os.path.exists(data_path):
        print("找不到 listings.csv 檔案：", data_path)
        print("請檢查 config.local.json 的 listings_csv")
        sys.exit(1)

    # 載入資料
    df = read_listings(data_path)

    # 將欄位變成可計算的數字，遺漏值改成 0
    # pd.to_numeric(...)：把一欄資料轉成數字，如遇到空白或亂碼改成NaN
    # .fillna(0)：把NaN改成0
    df["number_of_reviews"] = pd.to_numeric(df["number_of_reviews"], errors="coerce").fillna(0)
    df["number_of_reviews_ltm"] = pd.to_numeric(df["number_of_reviews_ltm"], errors="coerce").fillna(0)
    df["review_scores_rating"] = pd.to_numeric(df["review_scores_rating"], errors="coerce")
    df["is_superhost"] = df["host_is_superhost"] == "t"

    # 全部房源數、有評分的房源
    n = len(df)
    rated = df["review_scores_rating"].notna() # 標記哪些房源「有評分」
    rated_n = rated.sum()

    # 計算全市指標
    summary = {
        "city": city, # 城市名稱
        "n_listings": n, # 總房源數
        "review_coverage": (df["number_of_reviews"] >= 1).mean(), # 有評論的房源比率
        "ltm_active_rate": (df["number_of_reviews_ltm"] >= 1).mean(), # 近 1 年有評論的房源比率
        "avg_rating": df.loc[rated, "review_scores_rating"].mean(), # 有評分的房源之平均分數
        "low_score_threshold": threshold, # 低分數門檻
        "low_score_rate": (df.loc[rated, "review_scores_rating"] < threshold).mean(), # 低分數房源比率
        "superhost_rate": df["is_superhost"].mean(), # 超讚房東比率
        "rating_nonnull_n": int(rated_n), # 有評分的房源數
        "source_file": cfg["listings_csv"], # 資料來源檔案路徑
    }

    # 轉成表格，比率改成百分比方便看
    out_df = pd.DataFrame([summary])
    out_df["review_coverage_pct"] = (out_df["review_coverage"] * 100).round(2)
    out_df["ltm_active_rate_pct"] = (out_df["ltm_active_rate"] * 100).round(2)
    out_df["low_score_rate_pct"] = (out_df["low_score_rate"] * 100).round(2)
    out_df["superhost_rate_pct"] = (out_df["superhost_rate"] * 100).round(2)
    out_df["avg_rating"] = out_df["avg_rating"].round(3)

    # 欄位名稱改成中文
    """
    out_df = out_df.rename(columns={
        "city": "城市",
        "n_listings": "房源總數",
        "review_coverage": "有評比率",
        "ltm_active_rate": "近一年活躍比率",
        "avg_rating": "平均評分",
        "low_score_threshold": "低分門檻",
        "low_score_rate": "低分占比",
        "superhost_rate": "超讚房東占比",
        "rating_nonnull_n": "有評分房源數",
        "source_file": "資料來源",
        "review_coverage_pct": "有評率_百分比",
        "ltm_active_rate_pct": "近一年活躍率_百分比",
        "low_score_rate_pct": "低分占比_百分比",
        "superhost_rate_pct": "超讚房東占比_百分比",
    })
    """

    # 若 output 資料夾不存在就先建立，再存檔
    os.makedirs(out_dir, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")

    # 印出結果
    print("=== City quality summary ===")
    print(out_df.T)
    print("\nSaved:", out_path)


if __name__ == "__main__":
    main()
