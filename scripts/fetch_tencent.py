#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯源 A 股日线抓取（纯 urllib 实现, 零第三方依赖, 不装 akshare 也能用）

用法:
    python3 fetch_tencent.py                 # 抓内置篮子到 data/
    python3 fetch_tencent.py 600519 000858  # 抓指定代码

输出: data/<code>.csv, 列 = date,open,close,high,low,volume (前复权 qfq)
字段口径与 akshare stock_zh_a_hist_tx 一致, 下游 rqalpha/backtrader 通用。
"""
import os
import sys
import json
import time
import urllib.request

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/certs/cacert.pem")

DEFAULT_BASKET = {
    "600519": "贵州茅台", "000858": "五粮液", "601318": "中国平安", "600036": "招商银行",
    "000333": "美的集团", "002594": "比亚迪", "600276": "恒瑞医药", "601899": "紫金矿业",
    "600900": "长江电力", "600030": "中信证券", "000651": "格力电器", "601012": "隆基绿能",
    "600887": "伊利股份", "300750": "宁德时代", "000001": "平安银行",
}
START, END = "2023-01-01", "2026-09-01"     # 腾讯接口用 YYYY-MM-DD
try:
    _BASE = os.path.dirname(os.path.abspath(__file__))
except Exception:
    _BASE = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(_BASE, "..", "data")


def prefix(code):
    """6 开头 → sh, 其余(0/3) → sz"""
    return ("sh" if code.startswith("6") else "sz") + code


MAX_PER_CALL = 640   # 腾讯 fqkline 接口单次最多返回约 640 根


def fetch_one(code):
    """抓单只前复权日线(分段直到覆盖 START), 落盘 CSV, 返回行数"""
    import csv
    sym = prefix(code)
    all_rows, seen = [], set()
    end = END
    for _ in range(8):                            # 最多 8 段(≈8 年日线)
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
               f"param={sym},day,{START},{end},{MAX_PER_CALL},qfq")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        node = data["data"][sym]
        rows = node.get("qfqday") or node.get("day")     # qfqday=前复权
        if not rows:
            break
        # 每条: [date, open, close, high, low, volume, ...]
        new_rows = []
        for r in rows:
            if len(r) >= 6 and r[0] not in seen:
                seen.add(r[0])
                new_rows.append([r[0], float(r[1]), float(r[2]),
                                 float(r[3]), float(r[4]), float(r[5])])
        all_rows = new_rows + all_rows              # 段间首尾相接
        earliest = rows[0][0]
        if earliest <= START or len(new_rows) < MAX_PER_CALL - 1:
            break
        end = earliest                              # 以本段最早日为下一段终点
        time.sleep(0.5)
    if not all_rows:
        return 0
    with open(os.path.join(DATA_DIR, f"{code}.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "close", "high", "low", "volume"])
        w.writerows(all_rows)
    return len(all_rows)


def main(codes):
    os.makedirs(DATA_DIR, exist_ok=True)
    for code in codes:
        path = os.path.join(DATA_DIR, f"{code}.csv")
        if os.path.exists(path) and os.path.getsize(path) > 2000:
            print(f"{code}: 缓存已存在, 跳过")
            continue
        for attempt in range(3):
            try:
                rows = fetch_one(code)
                if rows:
                    print(f"{code}: {len(rows)} 行 ({prefix(code)})")
                    break
            except Exception as e:
                print(f"{code}: 第{attempt+1}次失败 {type(e).__name__}, 重试...")
                time.sleep(3)
        else:
            print(f"{code}: FAILED")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    codes = args if args else list(DEFAULT_BASKET)
    main(codes)
