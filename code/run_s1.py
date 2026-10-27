# -*- coding: utf-8 -*-
"""策略1 BCD 层：选股（冻结持仓）+ 行业内权重 + 外层择时，次日成交"""
import json
import numpy as np
import pandas as pd

from common import CONFIG, path, outdir, metrics

CACHE = path("cache")
z = np.load(CACHE / ("daily_cache_slim.npz" if (CACHE / "daily_cache_slim.npz").exists() else "daily_cache.npz"), allow_pickle=True)
dates = pd.to_datetime(z["dates"])
codes = z["codes"]
raw = pd.DataFrame(z["raw"], index=dates, columns=codes)
_t = np.load(CACHE / ("ret_tr_slim.npz" if (CACHE / "ret_tr_slim.npz").exists() else "ret_tr.npz"), allow_pickle=True)
TR = pd.DataFrame(_t["ret"], index=pd.to_datetime(_t["dates"]), columns=_t["codes"])

h = {int(k): v for k, v in json.load(open(path("holdings"), encoding="utf-8")).items()}
ind = path("industry")
mp = json.load(open(ind / "sw_industry_map.json", encoding="utf-8"))["map"]
hz = pd.read_csv(ind / "数据_哈耶克三角分类.csv", dtype=str)
hz.columns = ["code", "name", "l1", "l2", "l3", "stage", "holder", "chg", "gzw", "real"]
hz["code"] = hz["code"].str.zfill(6)
NAME = dict(zip(hz["code"], hz["name"]))
L3 = dict(zip(hz["code"], hz["l3"]))
l1of = {c: mp.get(c, {}).get("l1") for c in sum(h.values(), [])}
l3of = {c: mp.get(c, {}).get("l3") for c in sum(h.values(), [])}

jj = pd.read_csv(ind / "行业景气_修正.csv")
jj["avail"] = pd.to_datetime(jj["avail"])
def coef(industry, t):
    rel = jj[jj["avail"] <= t]
    if len(rel) == 0:
        return 1.0
    q = rel.sort_values("avail").iloc[-1]
    row = jj[(jj["industry"] == industry) & (jj["y"] == q["y"]) & (jj["q"] == q["q"])]
    if len(row) == 0:
        return 1.0
    g = row.iloc[0]["g_ttm"]
    dg = row.iloc[0]["dg_ttm"]
    if pd.isna(g):
        return 1.0
    return 1.0 if (g > 0 and pd.notna(dg) and dg > 0) else (0.5 if (g > 0 and pd.notna(dg) and dg <= 0) else 0.2)

p1 = pd.read_csv(ind / "申万三级_行业收益面板.csv")
p1["date"] = pd.to_datetime(p1["date"])
p1 = p1.set_index("date").sort_index()
mk = pd.read_csv(ind / "sh000852.csv")
mk["date"] = pd.to_datetime(mk["date"])
mk = mk.set_index("date")["close"].sort_index()
mk_r = mk.pct_change().reindex(p1.index).ffill()
l3to1 = {}
for k, v in mp.items():
    if v.get("l3") and v.get("l1"):
        l3to1.setdefault(v["l3"], v["l1"])
LEAD = {}
for l1 in set(l3to1.values()):
    cols = [c for c in p1.columns if l3to1.get(c) == l1]
    if len(cols) < 2:
        for c in cols:
            LEAD[(l1, c)] = pd.Series(0.0, index=p1.index)
        continue
    idio = {c: (p1[c] - p1[c].rolling(250).cov(mk_r) / mk_r.rolling(250).var() * mk_r) for c in cols}
    common = pd.concat([idio[x] for x in cols], axis=1).mean(axis=1)
    for c in cols:
        LEAD[(l1, c)] = idio[c].shift(1).rolling(60).corr(common)

short = [1, 5, 10, 15, 20]
longs = [5, 10, 15, 20, 30, 40, 60, 90, 120, 180, 250]
def dratio(s):
    return pd.concat([(s.rolling(a).mean() < s.rolling(b).mean()).astype(float)
                      for a in short for b in longs if a < b], axis=1).mean(axis=1)

rt = path("rates")
cv = pd.read_csv(rt / "cgb_curve_full.csv").iloc[:, [1, 8]]
cv.columns = ["date", "t10"]
cv["date"] = pd.to_datetime(cv["date"])
cv = cv.set_index("date").sort_index()
sh = pd.read_csv(rt / "shibor_1y_cache.csv")
sh["date"] = pd.to_datetime(sh["date"])
sh = sh.set_index("date")["s1"].sort_index()
rp = pd.read_csv(rt / "repo_rate_full.csv")
rp["date"] = pd.to_datetime(rp["date"])
rp = rp.set_index("date")["FDR007"].sort_index()
rs = dratio((pd.to_numeric(cv["t10"], errors="coerce") - sh.reindex(cv.index).ffill()).dropna()).reindex(dates).ffill()
rv = dratio(rp.dropna().diff().abs().rolling(20).mean().dropna()).reindex(dates).ffill()

all_dates = pd.DatetimeIndex([d for d in dates if d >= pd.Timestamp(CONFIG["start_date"])])
pos = {c: i for i, c in enumerate(codes)}
def reb_date(y):
    for d in all_dates:
        if d.year == y and d.month >= CONFIG["s1"]["rebalance_month"]:
            return d
reb = {y: reb_date(y) for y in range(2020, 2027)}

def weights_at(d, y):
    bd = all_dates[all_dates.get_loc(d) - 1]
    g3 = {}
    for c in h[y]:
        l3 = l3of.get(c)
        l1 = l1of.get(c)
        if l3 and l1:
            g3.setdefault((l1, l3), []).append(c)
    w3 = {}
    for (l1, l3), cs in g3.items():
        base = coef(l1, bd)
        sib = sorted(set(k for (ll, k) in g3 if ll == l1))
        s = pd.Series({k: LEAD.get((l1, k), pd.Series()).shift(1).get(d, np.nan) for k in sib}).dropna()
        if len(s) > 1:
            rq = s.rank(pct=True) - 0.5
            base *= max(1.0 + 2.0 * rq.get(l3, 0.0), 0.05)
        w3[(l1, l3)] = base
    tot = sum(w3.values()) or 1
    cur = {}
    for (l1, l3), cs in g3.items():
        for c in cs:
            cur[c] = w3[(l1, l3)] / tot / len(cs)
    return cur

def run(ret2d):
    cur = {}
    pending = None
    st = 0
    hc = 0
    lastm = None
    hold_y = None
    rets = pd.Series(0.0, index=all_dates)
    annual = []
    monthly = []
    state = []
    for i, d in enumerate(all_dates):
        if d in reb.values():
            hold_y = [yy for yy, dd in reb.items() if dd == d][0]
        if (d.year, d.month) != lastm:
            lastm = (d.year, d.month)
            if hold_y is None:
                continue
            neww = weights_at(d, hold_y)
            if cur:
                pending = neww
            else:
                cur = neww
            if d in reb.values():
                for c, w in neww.items():
                    annual.append({"date": d, "year": hold_y, "code": c, "name": NAME.get(c, ""),
                                   "l3": L3.get(c, ""), "weight": w})
            for c, w in neww.items():
                monthly.append({"date": d, "code": c, "weight": w})
        if i == 0:
            continue
        od = all_dates[i - 1]
        c_ = (rs.get(od, 0) >= 0.5) or (rv.get(od, 0) >= 0.5)
        if st == 0:
            if c_:
                st = 1
                hc = 0
        else:
            if (not c_) and hc >= 15:
                st = 0
            else:
                hc += 1
        row = ret2d[dates.get_loc(d)]
        pr = 0.0
        for cc, w in cur.items():
            if cc in pos:
                v = row[pos[cc]]
                if pd.notna(v):
                    pr += w * st * v
        rets[d] = pr
        state.append({"date": d, "exposure": st})
        if pending is not None:
            cur = pending
            pending = None
    nav = (1 + rets).cumprod()
    return nav / nav.iloc[0], pd.DataFrame(annual), pd.DataFrame(monthly), pd.DataFrame(state)

navp, H, MW, ST = run(raw.pct_change().values)
navt, _, _, _ = run(TR.values)

navdir = outdir("nav")
pd.DataFrame({"date": navp.index, "nav": navp.values}).to_csv(navdir / "BCD_不复权.csv", index=False, encoding="utf-8-sig")
pd.DataFrame({"date": navt.index, "nav": navt.values}).to_csv(navdir / "BCD_含分红.csv", index=False, encoding="utf-8-sig")
hold = outdir("holdings")
H.to_csv(hold / "BCD_年度持仓.csv", index=False, encoding="utf-8-sig")
H.groupby(["date", "year"]).size().reset_index(name="n").to_csv(hold / "BCD_年度只数.csv", index=False, encoding="utf-8-sig")
MW.to_csv(hold / "BCD_monthly_weights.csv", index=False, encoding="utf-8-sig")
ST.to_csv(hold / "BCD_state.csv", index=False, encoding="utf-8-sig")
stt = outdir("stats")
rows = []
for tag, nav in [("不复权", navp), ("含分红", navt)]:
    a, d, s, f = metrics(nav)
    rows.append({"口径": tag, "年化%": round(a * 100, 2), "回撤%": round(d * 100, 2), "夏普": round(s, 2), "终值": round(f, 3)})
pd.DataFrame(rows).to_csv(stt / "绩效.csv", index=False, encoding="utf-8-sig")
print(pd.DataFrame(rows).to_string(index=False))
print("BCD 计算完成")
