# -*- coding: utf-8 -*-
"""数据拉取（akshare 默认），增量更新
offline=true 时直接退出。
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = json.load(open(ROOT / "config.json", encoding="utf-8"))
if CFG["offline"]:
    print("离线模式，跳过拉取")
    sys.exit(0)

try:
    import akshare as ak
except Exception as e:
    print("akshare 不可用:", e)
    sys.exit(1)

RAW = ROOT / "data" / "raw"
QFQ = RAW / "qfq"
UNQ = RAW / "raw"
DIV = RAW / "dividend" / "all_a_dividend"
IDX = RAW / "index"
START = "20140101"
END = pd.Timestamp.today().strftime("%Y%m%d")

def codes_all():
    d = ak.stock_info_a_code_name()
    d.columns = ["code", "name"]
    d["code"] = d["code"].astype(str).str.zfill(6)
    return d

def update_price(code, outdir, adjust):
    f = outdir / f"{code}.csv"
    last = None
    if f.exists():
        try:
            old = pd.read_csv(f, usecols=["date"])
            last = pd.to_datetime(old["date"]).max()
        except Exception:
            last = None
    start = (last + pd.Timedelta(days=1)).strftime("%Y%m%d") if last is not None else START
    try:
        d = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=END, adjust=adjust)
    except Exception:
        return False
    if d is None or len(d) == 0:
        return True
    d = d.rename(columns={"日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
                          "最低": "low", "成交量": "volume", "成交额": "amount",
                          "换手率": "turnover"})
    d["date"] = pd.to_datetime(d["date"])
    if f.exists():
        old = pd.read_csv(f)
        d = pd.concat([old, d], ignore_index=True).drop_duplicates("date").sort_values("date")
    d.to_csv(f, index=False, encoding="utf-8-sig")
    return True

def update_dividend(code):
    f = DIV / f"{code}.csv"
    if f.exists():
        return True
    try:
        d = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    except Exception:
        return False
    if d is not None and len(d):
        d.to_csv(f, index=False, encoding="utf-8-sig")
    return True

def update_index():
    IDX.mkdir(parents=True, exist_ok=True)
    for code, name in [("000300", "沪深300"), ("000922", "中证红利")]:
        try:
            d = ak.index_zh_a_hist(symbol=code, period="daily", start_date="20190101", end_date=END)
            d.rename(columns={"日期": "date", "收盘": "close"}).to_csv(IDX / f"{name}.csv", index=False, encoding="utf-8-sig")
        except Exception as e:
            print("指数失败", name, e)

def main():
    QFQ.mkdir(parents=True, exist_ok=True)
    UNQ.mkdir(parents=True, exist_ok=True)
    DIV.mkdir(parents=True, exist_ok=True)
    cs = codes_all()
    print("股票数", len(cs))
    for i, code in enumerate(cs["code"]):
        update_price(code, QFQ, "qfq")
        update_price(code, UNQ, "")
        update_dividend(code)
        if (i + 1) % 200 == 0:
            print("进度", i + 1)
            time.sleep(0.5)
    update_index()
    print("数据拉取完成")

if __name__ == "__main__":
    main()
