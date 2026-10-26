# -*- coding: utf-8 -*-
"""每日持仓面板：只保留持仓表，含 100 万初始资金与手数"""
from pathlib import Path
import numpy as np
import pandas as pd

from common import path, outdir

CAPITAL = 1_000_000

z = np.load(path("cache") / "daily_cache.npz", allow_pickle=True)
dates = pd.to_datetime(z["dates"])
codes = z["codes"]
qfq = pd.DataFrame(z["qfq"], index=dates, columns=codes)
raw = pd.DataFrame(z["raw"], index=dates, columns=codes)

H = pd.read_csv(outdir("holdings") / "BCD_monthly_weights.csv", parse_dates=["date"], dtype={"code": str})
H["code"] = H["code"].str.zfill(6)
A = pd.read_csv(outdir("holdings") / "BCD_年度持仓.csv", parse_dates=["date"], dtype={"code": str})
A["code"] = A["code"].str.zfill(6)
META = A.drop_duplicates("code").set_index("code")[["name", "l3"]].to_dict("index")
ST = pd.read_csv(outdir("holdings") / "BCD_state.csv", parse_dates=["date"]).set_index("date")["exposure"]

D = qfq.index
today = D[-1]
prev = D[-2]
mwd = H[H["date"] <= today]["date"].max()
base = H[H["date"] == mwd].set_index("code")["weight"]
expo = float(ST.asof(today)) if pd.notna(ST.asof(today)) else 1.0

def drift(day):
    px0 = qfq.loc[mwd, base.index]
    pxt = qfq.loc[day, base.index]
    val = base * (pxt / px0)
    return val / val.sum()

w_t = drift(today)
w_p = drift(prev)
ret_t = qfq.loc[today, w_t.index] / qfq.loc[prev, w_t.index] - 1
contrib = w_p * ret_t
price = raw.loc[today, w_t.index]

T = pd.DataFrame({"code": w_t.index,
                  "name": [META.get(c, {}).get("name", "") for c in w_t.index],
                  "l3": [META.get(c, {}).get("l3", "") for c in w_t.index],
                  "target": base.reindex(w_t.index).values,
                  "now": w_t.values,
                  "prev": w_p.reindex(w_t.index).values,
                  "ret": ret_t.reindex(w_t.index).values,
                  "contrib": contrib.reindex(w_t.index).values,
                  "price": price.reindex(w_t.index).values})
T["dw"] = T["now"] - T["prev"]
T["value"] = T["now"] * CAPITAL * expo
T["lots"] = np.floor(T["value"] / (T["price"] * 100)).astype(int)
T["shares"] = T["lots"] * 100
T["actual_value"] = T["shares"] * T["price"]
T["actual_w"] = T["actual_value"] / CAPITAL
T["pnl"] = T["actual_value"] * T["ret"]
T = T.sort_values("actual_value", ascending=False).reset_index(drop=True)

mv = T["actual_value"].sum()
cash = CAPITAL - mv
pnl = T["pnl"].sum()

def cell(v, fmt, cls=""):
    return f"<td class='{cls}'>{fmt.format(v)}</td>"

rows = []
for _, r in T.iterrows():
    cls = "up" if r["dw"] > 0 else ("down" if r["dw"] < 0 else "")
    pcls = "up" if r["pnl"] > 0 else ("down" if r["pnl"] < 0 else "")
    rows.append(
        f"<tr><td>{r['name']}</td><td>{r['code']}</td><td>{r['l3']}</td>"
        + cell(r["target"] * 100, "{:.2f}")
        + cell(r["now"] * 100, "{:.2f}")
        + cell(r["dw"] * 100, "{:+.2f}", cls)
        + cell(r["ret"] * 100, "{:+.2f}%", cls)
        + cell(r["contrib"] * 100, "{:+.2f}%", pcls)
        + cell(r["price"], "{:.2f}")
        + cell(r["lots"], "{:,}")
        + cell(r["actual_value"], "{:,.0f}")
        + cell(r["actual_w"] * 100, "{:.2f}")
        + "</tr>")

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>策略1 BCD 今日持仓</title>
<style>
body{{font-family:Microsoft YaHei,sans-serif;margin:24px;color:#222;background:#fafafa}}
h1{{font-size:20px}} .cards{{display:flex;gap:14px;margin:12px 0;flex-wrap:wrap}}
.card{{background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:10px 16px;min-width:140px}}
.card span{{color:#777;font-size:12px}} .card b{{display:block;font-size:20px;margin-top:4px}}
table{{border-collapse:collapse;background:#fff;margin:8px 0}}
td,th{{border:1px solid #ddd;padding:5px 9px;font-size:13px;text-align:right}}
th{{background:#f2f2f2;text-align:center}}
td:nth-child(-n+3){{text-align:left}} .up{{color:#c0392b}} .down{{color:#2c7fb8}}
tfoot td{{background:#f7f7f7;font-weight:bold}}
</style></head><body>
<h1>策略1 BCD 今日持仓</h1>
<div>数据日期：<b>{today.date()}</b> ｜ 目标权重基准日：{mwd.date()} ｜ 初始资金：{CAPITAL:,} 元 ｜ 仓位：{expo*100:.0f}%</div>
<div class="cards">
<div class="card"><span>持仓市值</span><b>{mv:,.0f}</b></div>
<div class="card"><span>现金</span><b>{cash:,.0f}</b></div>
<div class="card"><span>今日盈亏</span><b class="{'up' if pnl>0 else 'down'}">{pnl:+,.0f}</b></div>
<div class="card"><span>今日收益率</span><b class="{'up' if pnl>0 else 'down'}">{pnl/CAPITAL*100:+.2f}%</b></div>
<div class="card"><span>持仓只数</span><b>{len(T)}</b></div>
</div>
<table>
<thead><tr><th>名称</th><th>代码</th><th>行业</th><th>目标%</th><th>当前%</th><th>Δ昨日</th>
<th>涨跌</th><th>贡献</th><th>价格</th><th>手数</th><th>市值(元)</th><th>实际%</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><td colspan="3">合计（含现金）</td><td></td><td></td><td></td><td></td>
<td>{pnl/CAPITAL*100:+.2f}%</td><td></td><td></td><td>{mv:,.0f}</td><td>{mv/CAPITAL*100:.2f}</td></tr></tfoot>
</table>
<p style="color:#777">手数 = 向下取整（当前权重 × 初始资金 × 仓位 ÷ (价格 × 100)）；现金 = 初始资金 − 持仓市值。</p>
<p style="color:#777">自动生成：红利运行 / code/dashboard.py</p>
</body></html>"""
out = outdir("report") / "dashboard.html"
out.write_text(html, encoding="utf-8")
T.to_csv(outdir("stats") / "今日权重.csv", index=False, encoding="utf-8-sig")
print("面板已生成:", out)
print(T[["name", "now", "price", "lots", "actual_value", "actual_w"]].to_string(index=False))
print(f"持仓市值 {mv:,.0f} 现金 {cash:,.0f} 今日盈亏 {pnl:+,.0f}")
