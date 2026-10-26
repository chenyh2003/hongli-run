# -*- coding: utf-8 -*-
"""可视化与 HTML 报告"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

from common import CONFIG, path, outdir, load_nav, metrics

for fp in [r"C:\Windows\Fonts\msyh.ttc"]:
    if Path(fp).exists():
        font_manager.fontManager.addfont(fp)
        plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=fp).get_name()]
plt.rcParams["axes.unicode_minus"] = False

navdir = outdir("nav")
chart = outdir("charts")
stats = outdir("stats")
P = load_nav(navdir / "BCD_不复权.csv")
T = load_nav(navdir / "BCD_含分红.csv")

BENCH = {}
for f in path("benchmark").glob("*.csv"):
    BENCH[f.stem] = load_nav(f)

def save_nav():
    fig, ax = plt.subplots(figsize=(13, 6.5))
    for tag, s, c, lw in [("BCD 不复权", P, "#1f4e79", 2.0), ("BCD 含分红", T, "#c0392b", 2.0)]:
        a, d, sh, _ = metrics(s)
        ax.plot(s.index, s / s.iloc[0], lw=lw, color=c, label=f"{tag} {a*100:.1f}%/{d*100:.1f}%/{sh:.2f}")
    for k, s in BENCH.items():
        ax.plot(s.index, s / s.iloc[0], lw=1.1, alpha=.8, label=k)
    ax.set_yscale("log"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("策略1 BCD vs 基准")
    fig.tight_layout(); fig.savefig(chart / "净值.png", dpi=140); plt.close(fig)

def save_dd():
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for tag, s, c in [("BCD 不复权", P, "#1f4e79"), ("BCD 含分红", T, "#c0392b")]:
        dd = s / s.cummax() - 1
        ax.plot(dd.index, dd.values * 100, lw=1.5, color=c, label=tag)
    ax.axhline(0, color="k", lw=.8); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("BCD 回撤 %")
    fig.tight_layout(); fig.savefig(chart / "回撤.png", dpi=140); plt.close(fig)

def save_excess():
    for k, b in BENCH.items():
        idx = T.index.intersection(b.index)
        ex_t = (T.reindex(idx) / T.reindex(idx).iloc[0]) / (b.reindex(idx) / b.reindex(idx).iloc[0])
        ex_p = (P.reindex(idx) / P.reindex(idx).iloc[0]) / (b.reindex(idx) / b.reindex(idx).iloc[0])
        fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [1.4, 1]})
        axes[0].plot(ex_p.index, ex_p.values, lw=1.3, color="#1f4e79", label=f"不复权 {ex_p.iloc[-1]:.2f}")
        axes[0].plot(ex_t.index, ex_t.values, lw=1.8, color="#c0392b", label=f"含分红 {ex_t.iloc[-1]:.2f}")
        axes[0].axhline(1, color="k", lw=.8); axes[0].grid(alpha=.3); axes[0].legend(fontsize=8)
        axes[0].set_title(f"超额净值 vs {k}")
        for tag, ex, c in [("不复权", ex_p, "#1f4e79"), ("含分红", ex_t, "#c0392b")]:
            axes[1].plot(ex.index, (ex / ex.cummax() - 1).values * 100, lw=1.3, color=c, label=tag)
        axes[1].axhline(0, color="k", lw=.8); axes[1].grid(alpha=.3); axes[1].legend(fontsize=8)
        axes[1].set_title("超额回撤 %")
        fig.tight_layout(); fig.savefig(chart / f"超额_{k}.png", dpi=140); plt.close(fig)

def save_ind():
    H = pd.read_csv(outdir("holdings") / "BCD_年度持仓.csv", parse_dates=["date"])
    g = H.groupby(["year", "l3"])["weight"].sum().unstack().fillna(0) * 100
    ax = g.plot(kind="bar", stacked=True, figsize=(13, 5.5), colormap="tab20")
    ax.set_ylabel("%"); ax.set_title("BCD 年度行业权重")
    ax.legend(fontsize=6, ncol=4)
    fig = ax.get_figure(); fig.tight_layout(); fig.savefig(chart / "行业权重.png", dpi=140); plt.close(fig)

def yearly(s):
    return (1 + s.pct_change().fillna(0)).groupby(s.index.year).prod() - 1

def save_html():
    rows = []
    for tag, s in [("不复权", P), ("含分红", T)]:
        a, d, sh, f = metrics(s)
        rows.append(f"<tr><td>{tag}</td><td>{a*100:.2f}%</td><td>{d*100:.2f}%</td><td>{sh:.2f}</td><td>{f:.3f}</td></tr>")
    bench_rows = []
    for k, s in BENCH.items():
        a, d, sh, f = metrics(s)
        bench_rows.append(f"<tr><td>{k}</td><td>{a*100:.2f}%</td><td>{d*100:.2f}%</td><td>{sh:.2f}</td></tr>")
    yr = pd.DataFrame({"不复权": yearly(P), "含分红": yearly(T)}) * 100
    yr_html = yr.round(1).to_html()
    er = pd.read_csv(stats / "对账.csv")
    er_html = er.to_html(index=False)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>策略1 BCD 运行报告</title>
<style>body{{font-family:Microsoft YaHei,sans-serif;margin:30px;color:#222}}table{{border-collapse:collapse;margin:10px 0}}td,th{{border:1px solid #ccc;padding:5px 8px}}img{{max-width:100%;margin:10px 0}}</style></head><body>
<h1>策略1 BCD 运行报告</h1>
<p>运行日期：{pd.Timestamp.now():%Y-%m-%d %H:%M} ｜ 区间：{P.index[0].date()} ~ {P.index[-1].date()}</p>
<h2>绩效</h2><table><tr><th>口径</th><th>年化</th><th>回撤</th><th>夏普</th><th>终值</th></tr>{''.join(rows)}</table>
<h2>基准</h2><table><tr><th>基准</th><th>年化</th><th>回撤</th><th>夏普</th></tr>{''.join(bench_rows)}</table>
<h2>对账</h2>{er_html}
<h2>年度收益 %</h2>{yr_html}
<h2>净值</h2><img src="../charts/净值.png">
<h2>回撤</h2><img src="../charts/回撤.png">
<h2>行业权重</h2><img src="../charts/行业权重.png">
</body></html>"""
    (outdir("report") / "report.html").write_text(html, encoding="utf-8")

save_nav(); save_dd(); save_excess(); save_ind(); save_html()
print("图表与报告完成")
