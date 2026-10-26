# -*- coding: utf-8 -*-
"""每日增量更新（只更新持仓股票与利率），用于 GitHub Actions"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
CFG = json.load(open(ROOT / "config.json", encoding="utf-8"))

try:
    import akshare as ak
except Exception as e:
    print("akshare 不可用:", e)
    sys.exit(1)

SLIM = CACHE / "daily_cache_slim.npz"
RET = CACHE / "ret_tr_slim.npz"
if not SLIM.exists():
    print("缺少瘦缓存，请先运行本地 build/slim")
    sys.exit(1)

z = np.load(SLIM, allow_pickle=True)
old_dates = pd.to_datetime(z["dates"])
codes = list(z["codes"])
QF = pd.DataFrame(z["qfq"], index=old_dates, columns=codes)
RW = pd.DataFrame(z["raw"], index=old_dates, columns=codes)
SH = pd.DataFrame(z["sh"], index=old_dates, columns=codes)
DPS = pd.DataFrame(z["dps"], index=old_dates, columns=codes)
STK = pd.DataFrame(z["streak"], index=old_dates, columns=codes)
_t = np.load(RET, allow_pickle=True)
TR = pd.DataFrame(_t["ret"], index=pd.to_datetime(_t["dates"]), columns=_t["codes"])

last = old_dates.max()
start = (last + pd.Timedelta(days=1)).strftime("%Y%m%d")
end = pd.Timestamp.today().strftime("%Y%m%d")

def fetch_hist(code, adjust):
    d = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust=adjust)
    if d is None or len(d) == 0:
        return pd.Series(dtype=float)
    d = d.rename(columns={"日期": "date", "收盘": "close"})
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)

def fetch_div(code):
    try:
        d = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    except Exception:
        return pd.Series(dtype=float)
    if d is None or len(d) == 0:
        return pd.Series(dtype=float)
    excol = [c for c in d.columns if "除权除息" in str(c)]
    paycol = [c for c in d.columns if "派息" in str(c)]
    if not excol or not paycol:
        return pd.Series(dtype=float)
    d = d[[excol[0], paycol[0]]].copy()
    d.columns = ["ex", "pay"]
    d["ex"] = pd.to_datetime(d["ex"], errors="coerce")
    d["pay"] = pd.to_numeric(d["pay"], errors="coerce") / 10.0
    d = d.dropna()
    d = d[d["pay"] > 0]
    d = d[d["ex"] > last]
    return d.groupby("ex")["pay"].sum()

new_q, new_r, new_d = {}, {}, {}
for i, c in enumerate(codes):
    try:
        new_q[c] = fetch_hist(c, "qfq")
        new_r[c] = fetch_hist(c, "")
        new_d[c] = fetch_div(c)
    except Exception as e:
        print("跳过", c, e)
    if (i + 1) % 10 == 0:
        time.sleep(0.3)

QN = pd.DataFrame(new_q).sort_index()
RN = pd.DataFrame(new_r).sort_index()
DN = pd.DataFrame(new_d).reindex(columns=codes).fillna(0.0) if new_d else pd.DataFrame(index=[], columns=codes)
if QN.empty:
    print("没有新数据")
    sys.exit(0)

idx_new = QN.index.union(RN.index)
QF2 = pd.concat([QF, QN.reindex(idx_new)]).sort_index()
QF2 = QF2[~QF2.index.duplicated(keep="last")]
RW2 = pd.concat([RW, RN.reindex(idx_new)]).sort_index()
RW2 = RW2[~RW2.index.duplicated(keep="last")]
SH2 = SH.reindex(QF2.index).ffill()
DPS2 = pd.concat([DPS, DN.reindex(idx_new)]).sort_index()
DPS2 = DPS2[~DPS2.index.duplicated(keep="last")].fillna(0.0)
TR2 = TR.reindex(QF2.index).copy()
prev_close = RW2.shift(1)
mask = QF2.index > last
TR2.loc[mask] = (RW2.loc[mask] + DPS2.loc[mask]) / prev_close.loc[mask] - 1
TR2 = TR2.replace([np.inf, -np.inf], np.nan)
ST2 = pd.DataFrame(np.zeros_like(QF2.values), index=QF2.index, columns=codes)

np.savez_compressed(SLIM, qfq=QF2.values.astype(np.float32), raw=RW2.values.astype(np.float32),
                    sh=SH2.values.astype(np.float32), dps=DPS2.values.astype(np.float32),
                    streak=ST2.values.astype(np.float32), dates=QF2.index.values,
                    codes=np.array(codes))
np.savez_compressed(RET, ret=TR2.values.astype(np.float32), dates=QF2.index.values,
                    codes=np.array(codes))
print("行情更新完成:", last.date(), "->", QF2.index[-1].date(), "新增", int(mask.sum()), "天")

# 利率（尽力更新；失败则冻结）
RT = ROOT / "data" / "rates"
try:
    sh = ak.macro_china_shibor_all()
    sh["日期"] = pd.to_datetime(sh["日期"])
    col = [c for c in sh.columns if str(c).startswith("1Y")]
    if col:
        s = sh.set_index("日期")[col[0]].astype(float)
        s = s[s.index > pd.to_datetime(pd.read_csv(RT / "shibor_1y_cache.csv")["date"]).max()]
        if len(s):
            old = pd.read_csv(RT / "shibor_1y_cache.csv")
            old["date"] = pd.to_datetime(old["date"])
            add = pd.DataFrame({"date": s.index, "s1": s.values})
            pd.concat([old, add]).drop_duplicates("date").sort_values("date").to_csv(
                RT / "shibor_1y_cache.csv", index=False, encoding="utf-8-sig")
            print("shibor 更新", len(s))
except Exception as e:
    print("shibor 更新失败，冻结", e)

try:
    cg = ak.bond_china_yield(start_date=start, end_date=end)
    cg["日期"] = pd.to_datetime(cg["日期"])
    cg = cg[cg["曲线名称"].astype(str).str.contains("国债")]
    if len(cg):
        old = pd.read_csv(RT / "cgb_curve_full.csv")
        old["日期"] = pd.to_datetime(old["日期"])
        add = cg[["日期", "3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]].copy()
        add.insert(0, "曲线名称", "国债")
        pd.concat([old, add]).drop_duplicates("日期").sort_values("日期").to_csv(
            RT / "cgb_curve_full.csv", index=False, encoding="utf-8-sig")
        print("国债曲线更新", len(add))
except Exception as e:
    print("国债更新失败，冻结", e)

print("每日更新完成")
