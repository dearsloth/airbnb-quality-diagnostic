# -*- coding: utf-8 -*-
"""
評論主題頻次（spaCy + 規則字典）

路徑與參數請放在 config.local.json（由 config.example.json 複製修改）。
主題字典：rules/theme_lexicon.json

品質／抽樣規則：
  - 空白或過短評論（len < min_comment_chars）不納入分母
  - 去除簡單 HTML 標籤（如 <br/>）
  - 同一 listing_id + 相同 comments 去重，只留一則
  - 以 theme_sample_seed 可重現抽樣；theme_sample_n 為 null 則用全部有效評論，不抽樣
  - 一則評論同一主題最多計 1 次；一則可多標籤

指標定義：
  主題占比 = 該主題出現則數 ÷ 有效評論數
"""

import os
import re
import json
import sys

import pandas as pd
import spacy
from spacy.matcher import PhraseMatcher

# 專案路徑與設定檔位置
script_dir = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(script_dir)
config_path = os.path.join(ROOT, "config.local.json")

HTML_TAG_RE = re.compile(r"<[^>]+>")  # 抓 HTML 標籤的正規表達式


# 讀取設定檔
def load_config():
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


# 如果path_value是絕對路徑，則直接回傳；如果不是，則接到專案根目錄(相對路徑)
def resolve_path(path_value):
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(ROOT, path_value)


# 讀取主題字典
def load_lexicon(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# 讀取評論資料
def read_reviews(path):
    usecols = ["listing_id", "id", "date", "comments"]
    return pd.read_csv(path, usecols=usecols, encoding="utf-8")


# 清洗評論文字
def clean_comment_text(text): 
    if pd.isna(text):  # 如果評論文字是遺漏值，則回傳空字串
        return ""
    s = str(text)  # 將評論文字轉換為字串
    # HTML 標籤先去除常見 case，再加通用的正規表達式(把所有 HTML 標籤換成" ")
    s = s.replace("<br/>", " ").replace("<br />", " ").replace("<br>", " ")
    s = HTML_TAG_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip() # 將多個空格換成一個空格
    return s


# 清洗、長度門檻、同房源同文去重 → 有效評論
def prepare_eligible_reviews(df, min_chars): 
    out = df.copy()
    out["comments_clean"] = out["comments"].map(clean_comment_text)  # 清洗評論文字
    out = out[out["comments_clean"].str.len() >= min_chars].copy()  # 長度門檻(評論字數>=20)
    out = out.drop_duplicates(subset=["listing_id", "comments_clean"], keep="first")  # 同房源同文去重
    out = out.reset_index(drop=True)  # 重置索引
    return out


# 可重現抽樣；無法／不需抽樣時回傳全部有效評論
def sample_reviews(df, sample_n, seed):
    # 設定為 null：明確指定跑全量（不抽樣）
    if sample_n is None: 
        return df.copy()
    
    sample_n = int(sample_n)
    # n 不合理，或 n 已涵蓋全部有效評論 → 等同用全部，不必再抽樣
    if sample_n <= 0 or sample_n >= len(df):
        return df.copy()
    # 抽樣：固定 seed(每次都抽到同一組評論)，結果可重現
    return df.sample(n=sample_n, random_state=int(seed)).reset_index(drop=True)
    # 真隨機抽樣：不固定 seed，每次結果不同，結果不可重現
    # return df.sample(n=sample_n).reset_index(drop=True) 


# 依主題字典建立 PhraseMatcher（片語／關鍵詞匹配器）
def build_matcher(nlp, lexicon):  # nlp：spaCy模型
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")  # attr="LOWER"：不分大小寫
    for theme_name, meta in lexicon["themes"].items():  # theme_name：字串，如 "cleanliness"
        word_list = meta.get("patterns", [])  # 這個主題的關鍵詞列表
        docs = []
        # 把每個關鍵詞轉成 spaCy 的 Doc(斷詞)，才能給 PhraseMatcher 用
        for word in word_list:
            word = str(word).strip()
            if word != "":
                docs.append(nlp.make_doc(word))  # 如 "check in" → ['check', 'in']
        if len(docs) > 0:
            matcher.add(theme_name, docs)

    return matcher


# 建立小寫字串(包含比對)
def build_substring_patterns(lexicon):
    out = {}
    for theme_name, meta in lexicon["themes"].items():  # theme_name：字串
        pats = []
        for p in meta.get("patterns", []):
            p = str(p).strip().lower()
            if p != "":
                pats.append(p)
        out[theme_name] = pats
    return out


# 對每則文字回傳命中的 theme_name 集合列表
def tag_themes(texts, nlp, matcher, substring_patterns):
    results = []
    for doc in nlp.pipe(texts, batch_size=200):  # 批量斷詞；每批 200 則
        hits = set()  # 這則評論命中的主題名稱（字串）
        matches = matcher(doc)  # [(theme_id數字, start, end), ...]
        for theme_id, start, end in matches:  # theme_id：spaCy 內部數字 ID
            theme_name = nlp.vocab.strings[theme_id]  # 數字 → 字串主題名
            hits.add(theme_name)

        text_lower = doc.text.lower() 
        for theme_name, patterns in substring_patterns.items():
            if theme_name in hits: # 如果這個主題已經在 hits 集合裡，則跳過(不重複計算)
                continue
            for p in patterns: 
                if p in text_lower: # 如果評論字串包含小寫字串，則加入主題名稱至 hits 集合
                    hits.add(theme_name)
                    break  # 同一主題最多計 1 次

        results.append(hits)

    return results


# 建立主題頻次表格
def build_frequency_table(theme_sets, lexicon, eligible_n, sample_n_used): # eligible_n：占比分母（有效評論數）；sample_n_used：抽樣後的有效評論數
    rows = []
    version = lexicon.get("version", "")   # 主題字典版本
    for theme_name, meta in lexicon["themes"].items():
        mention_n = 0  # 提到此主題的評論數
        for s in theme_sets:  # s 是一則評論的主題集合
            if theme_name in s:
                mention_n = mention_n + 1
        
        # 算提到此主題的評論數占比
        if eligible_n > 0:
            share = mention_n / eligible_n  # 占比 = 提到這個主題的評論數 / 分母
            share_pct = round(share * 100, 2)  # 占比(%) = 占比 * 100
        else:
            share = float("nan")      # 沒有分母就無法算
            share_pct = float("nan")

        # 組成一列結果
        one_row = {
            "theme_name": theme_name,                          # 如 "cleanliness"
            "label_zh": meta.get("label_zh", theme_name),      # 如 "清潔"
            "mention_n": mention_n,                            # 命中主題的評論數
            "eligible_n": eligible_n,                          # 有效評論數（主題占比分母）
            "share": round(share, 6),                          # 提到此主題的評論數占比(小數)
            "share_pct": share_pct,                            # 提到此主題的評論數占比(%)
            "sample_n": sample_n_used,                         # 抽樣後的有效評論數
            "lexicon_version": version,                        # 主題字典版本
        }
        rows.append(one_row)
    return pd.DataFrame(rows)


# 建立主題命中表格
def build_hits_table(sample_df, theme_sets, preview_chars=160): # preview_chars：預覽字數
    rows = []
    for i, hits in enumerate(theme_sets):
        if len(hits) == 0:  # 沒命中任何主題就跳過
            continue
        # 對回同一則評論的原始資料列
        row = sample_df.iloc[i]
        text = row["comments_clean"] # 第 i 則評論的清洗後評論文字

        # 評論字數>=160字就截斷
        if len(text) <= preview_chars:  
            preview = text
        else:
            preview = text[:preview_chars] + "…"

        # 主題名稱排序後用 | 串起來，如 "cleanliness|noise"
        theme_list = sorted(hits) 
        themes_str = "|".join(theme_list)
        
        one_row = {
            "listing_id": row["listing_id"],
            "review_id": row["id"],
            "date": row["date"],
            "themes": themes_str,
            "comments_preview": preview,
        }
        rows.append(one_row)

    return pd.DataFrame(rows)



def main():
    # Windows 主控台預設常是 cp950；強制 UTF-8，避免重導向 log 變成亂碼
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    # 檢查設定檔
    if not os.path.exists(config_path):
        print("找不到 config.local.json，請先從 config.example.json 複製修改")
        sys.exit(1)

    cfg = load_config()
    # 讀取設定
    reviews_path = resolve_path(cfg["reviews_csv"])
    lexicon_path = resolve_path(cfg["theme_lexicon_path"])
    out_dir = resolve_path(cfg["output_dir"])

    min_chars = int(cfg.get("min_comment_chars", 20))
    sample_n = cfg.get("theme_sample_n", 30000)
    sample_seed = int(cfg.get("theme_sample_seed", 42))
    model_name = cfg.get("spacy_model", "en_core_web_sm")

    freq_out = os.path.join(out_dir, "pandas_03_theme_frequency.csv")
    hits_out = os.path.join(out_dir, "pandas_03_theme_review_hits.csv")

    # 檢查檔案是否存在
    if not os.path.exists(reviews_path):
        print("找不到 reviews.csv：", reviews_path)
        print("請檢查 config.local.json 的 reviews_csv")
        sys.exit(1)

    if not os.path.exists(lexicon_path):
        print("找不到主題字典：", lexicon_path)
        print("請檢查 config.local.json 的 theme_lexicon_path")
        sys.exit(1)

    # 讀資料 + 清洗
    lexicon = load_lexicon(lexicon_path)
    reviews = read_reviews(reviews_path)
    eligible = prepare_eligible_reviews(reviews, min_chars)
    eligible_n_all = len(eligible)

    # 抽樣
    sample_df = sample_reviews(eligible, sample_n, sample_seed)
    sample_n_used = len(sample_df)
    eligible_n = sample_n_used  # 主題占比分母 = 本次有效評論數

    # 載入 spaCy 模型
    try:
        nlp = spacy.load(
            model_name,
            disable=["ner", "parser", "lemmatizer", "attribute_ruler"],
        )
    except OSError:
        print("找不到 spaCy 模型：", model_name)
        print("請執行：py -3 -m spacy download", model_name)
        sys.exit(1)

    # 建立匹配器 + 標記主題
    matcher = build_matcher(nlp, lexicon)
    substring_patterns = build_substring_patterns(lexicon)

    comment_texts = sample_df["comments_clean"].tolist()
    theme_sets = tag_themes(comment_texts, nlp, matcher, substring_patterns)

    # 彙總成表
    freq_df = build_frequency_table(theme_sets, lexicon, eligible_n, sample_n_used) # 主題頻次表格
    hits_df = build_hits_table(sample_df, theme_sets)  # 主題命中表格

    # 輸出 CSV
    os.makedirs(out_dir, exist_ok=True)
    freq_df.to_csv(freq_out, index=False, encoding="utf-8-sig")
    hits_df.to_csv(hits_out, index=False, encoding="utf-8-sig")

    # 印出摘要
    hit_count = 0
    for s in theme_sets:
        if len(s) > 0:
            hit_count = hit_count + 1

    print("=== 評論主題頻次 ===")
    print("原始評論數：", len(reviews))
    print("有效評論數（清洗／去重後）：", eligible_n_all)
    print("有效評論數（占比分母，含抽樣）：", eligible_n)
    print("至少命中 1 個主題的評論數：", hit_count)
    print(freq_df.to_string(index=False))
    print("\n已儲存主題頻次表格：", freq_out)
    print("已儲存主題命中表格：", hits_out)


if __name__ == "__main__":
    main()