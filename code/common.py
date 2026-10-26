# -*- coding: utf-8 -*-
"""公共工具：配置、路径、指标"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.load(open(ROOT / "config.json", encoding="utf-8"))
if os.getenv("OFFLINE", "").lower() == "false":
    CONFIG["offline"] = False

def path(key):
    return ROOT / CONFIG["paths"][key]

def outdir(key):
    p = ROOT / CONFIG["paths"]["output"] / key
    p.mkdir(parents=True, exist_ok=True)
    return p

def metrics(nav):
    """返回 年化、最大回撤、夏普、终值"""
    r = nav.pct_change().dropna()
    y = (nav.index[-1] - nav.index[0]).days / 365.25
    ann = (nav.iloc[-1] / nav.iloc[0]) ** (1 / y) - 1 if y > 0 else 0
    dd = (nav / nav.cummax() - 1).min()
    sh = r.mean() / r.std() * (252 ** 0.5) if r.std() > 0 else 0
    return ann, dd, sh, nav.iloc[-1]

def load_nav(p):
    import pandas as pd
    d = pd.read_csv(p, parse_dates=[0])
    return d.set_index(d.columns[0]).iloc[:, 0].astype(float).sort_index()
