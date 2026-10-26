# -*- coding: utf-8 -*-
"""与冻结参考净值对账"""
import sys
import pandas as pd

from common import CONFIG, path, outdir, load_nav, metrics

tol = CONFIG["verify"]["tolerance"]
ann_tol = CONFIG["verify"]["ann_tolerance_pct"]
rows = []
ok = True
for tag, fn in [("不复权", "BCD_不复权.csv"), ("含分红", "BCD_含分红.csv")]:
    a = load_nav(outdir("nav") / fn)
    b = load_nav(path("reference") / fn)
    idx = a.index.intersection(b.index)
    a0 = a.reindex(idx) / a.reindex(idx).iloc[0]
    b0 = b.reindex(idx) / b.reindex(idx).iloc[0]
    diff = (a0 - b0).abs()
    mx = float(diff.max())
    ann_a = metrics(a0)[0] * 100
    ann_b = metrics(b0)[0] * 100
    passed = mx < tol and abs(ann_a - ann_b) < ann_tol
    ok = ok and passed
    rows.append({"口径": tag, "交易日": len(idx), "最大差异": mx,
                 "年化_重算%": round(ann_a, 2), "年化_参考%": round(ann_b, 2),
                 "差异pct": round(ann_a - ann_b, 4), "结果": "通过" if passed else "失败"})
T = pd.DataFrame(rows)
T.to_csv(outdir("stats") / "对账.csv", index=False, encoding="utf-8-sig")
print(T.to_string(index=False))
if not ok:
    print("对账失败")
    sys.exit(2)
print("对账通过")
