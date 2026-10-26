# -*- coding: utf-8 -*-
"""从原始行情与分红构建日频缓存（仅当缓存不存在时运行）"""
import json
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = json.load(open(ROOT / "config.json", encoding="utf-8"))
RAW = ROOT / "data" / "raw"
QFQ = RAW / "qfq"
UNQ = RAW / "raw"
DIV = RAW / "dividend" / "all_a_dividend"
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

def read_close(f):
    d = pd.read_csv(f, usecols=["date", "close"])
    d["date"] = pd.to_datetime(d["date"])
    return d.drop_duplicates("date").set_index("date")["close"].astype(float)

qfq, raw, sh = {}, {}, {}
for f in sorted(QFQ.glob("*.csv")):
    c = f.stem
    try:
        qfq[c] = read_close(f)
    except Exception:
        continue
for f in sorted(UNQ.glob("*.csv")):
    c = f.stem
    try:
        d = pd.read_csv(f, usecols=["date", "close", "outstanding_share"])
        d["date"] = pd.to_datetime(d["date"])
        d = d.drop_duplicates("date").set_index("date")
        raw[c] = d["close"].astype(float)
        sh[c] = d["outstanding_share"].astype(float)
    except Exception:
        continue

QF = pd.DataFrame(qfq).sort_index()
RW = pd.DataFrame(raw).reindex(columns=QF.columns).sort_index()
SH = pd.DataFrame(sh).reindex(columns=QF.columns).reindex(RW.index).ffill()
dates = QF.index

ev = {}
for f in sorted(DIV.glob("*.csv")):
    c = f.stem
    if c not in QF.columns:
        continue
    try:
        d = pd.read_csv(f, usecols=[0, 5, 15])
    except Exception:
        continue
    d.columns = ["rep", "amt", "ex"]
    d["ex"] = pd.to_datetime(d["ex"], errors="coerce")
    d["amt"] = pd.to_numeric(d["amt"], errors="coerce") / 10
    d = d.dropna(subset=["ex", "amt"])
    d = d[d["amt"] > 0]
    if len(d):
        ev[c] = d.groupby("ex")["amt"].sum()

DIVM = pd.DataFrame(ev).reindex(index=dates, columns=QF.columns).fillna(0.0)
ret_tr = (RW + DIVM) / RW.shift(1) - 1
ret_tr = ret_tr.replace([np.inf, -np.inf], np.nan)

np.savez_compressed(CACHE / "daily_cache.npz",
                    qfq=QF.values.astype(np.float32), raw=RW.values.astype(np.float32),
                    sh=SH.values.astype(np.float32), dps=DIVM.values.astype(np.float32),
                    streak=np.zeros_like(QF.values, dtype=np.float32),
                    dates=dates.values, codes=QF.columns.values)
np.savez_compressed(CACHE / "ret_tr.npz",
                    ret=ret_tr.values.astype(np.float32), dates=dates.values, codes=QF.columns.values)
print("缓存构建完成", QF.shape)
