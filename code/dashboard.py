# -*- coding: utf-8 -*-
"""每日持仓面板：持仓表 + 100 万资金 + 手数
权重按日更新（收盘），打开页面时自动拉取最新一日的 CSV。
"""
from pathlib import Path

import numpy as np
import pandas as pd

from common import path, outdir

CAPITAL = 1_000_000

CACHE = path("cache")
z = np.load(CACHE / ("daily_cache_slim.npz" if (CACHE / "daily_cache_slim.npz").exists() else "daily_cache.npz"), allow_pickle=True)
dates = pd.to_datetime(z["dates"])
codes = z["codes"]
qfq = pd.DataFrame(z["qfq"], index=dates, columns=codes)
raw = pd.DataFrame(z["raw"], index=dates, columns=codes)
qfqf = qfq.ffill()
rawf = raw.ffill()

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
    px0 = qfqf.loc[mwd, base.index]
    pxt = qfqf.loc[day, base.index]
    val = base * (pxt / px0)
    return val / val.sum()

w_t = drift(today)
w_p = drift(prev)
ret_t = qfqf.loc[today, w_t.index] / qfqf.loc[prev, w_t.index] - 1
contrib = w_p * ret_t
price = rawf.loc[today, w_t.index]

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
T["contrib"] = T["contrib"].fillna(0)
T["value"] = T["now"] * CAPITAL * expo
px = T["price"].ffill().fillna(0)
T["price"] = px
T["lots"] = np.floor(T["value"] / (px * 100)).fillna(0).astype(int)
T["shares"] = T["lots"] * 100
T["actual_value"] = T["shares"] * px
T["actual_w"] = T["actual_value"] / CAPITAL
T["pnl"] = T["actual_value"] * T["ret"].fillna(0)
T["data_date"] = str(today.date())
T = T.sort_values("actual_value", ascending=False).reset_index(drop=True)

mv = T["actual_value"].sum()
cash = CAPITAL - mv
pnl = T["pnl"].sum()

rows = []
for _, r in T.iterrows():
    cls = "up" if r["dw"] > 0 else ("down" if r["dw"] < 0 else "")
    pcls = "up" if r["pnl"] > 0 else ("down" if r["pnl"] < 0 else "")
    rows.append(
        f"<tr data-code='{r['code']}'><td>{r['name']}</td><td>{r['code']}</td><td>{r['l3']}</td>"
        + f"<td class='c-target'>{r['target']*100:.2f}</td>"
        + f"<td class='c-now'><b>{r['now']*100:.2f}</b></td>"
        + f"<td class='c-dw {cls}'>{r['dw']*100:+.2f}</td>"
        + f"<td class='c-ret {cls}'>{r['ret']*100:+.2f}%</td>"
        + f"<td class='c-contrib {pcls}'>{r['contrib']*100:+.2f}%</td>"
        + f"<td class='c-price'>{r['price']:.2f}</td>"
        + f"<td class='c-lots'>{r['lots']:,}</td>"
        + f"<td class='c-value'>{r['actual_value']:,.0f}</td>"
        + f"<td class='c-aw'>{r['actual_w']*100:.2f}</td>"
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
#st{{color:#777;font-size:12px;margin:6px 0}}
</style></head><body>
<h1>策略1 BCD 今日持仓</h1>
<div>数据日期：<b id="ddate">{today.date()}</b> ｜ 目标权重基准日：{mwd.date()} ｜ 初始资金：{CAPITAL:,} 元 ｜ 仓位：{expo*100:.0f}%</div>
<div id="st">打开页面时自动检查最新数据（每日收盘后更新一次）</div>
<div class="cards">
<div class="card"><span>持仓市值</span><b id="mv">{mv:,.0f}</b></div>
<div class="card"><span>现金</span><b id="cash">{cash:,.0f}</b></div>
<div class="card"><span>今日盈亏</span><b id="pnl" class="{'up' if pnl>0 else 'down'}">{pnl:+,.0f}</b></div>
<div class="card"><span>今日收益率</span><b id="pret" class="{'up' if pnl>0 else 'down'}">{pnl/CAPITAL*100:+.2f}%</b></div>
<div class="card"><span>持仓只数</span><b>{len(T)}</b></div>
</div>
<table>
<thead><tr><th>名称</th><th>代码</th><th>行业</th><th>目标%</th><th>当前%</th><th>Δ昨日</th>
<th>涨跌</th><th>贡献</th><th>价格</th><th>手数</th><th>市值(元)</th><th>实际%</th></tr></thead>
<tbody id="tb">{''.join(rows)}</tbody>
<tfoot><tr><td colspan="3">合计（含现金）</td><td></td><td></td><td></td><td></td>
<td id="tcontrib">{pnl/CAPITAL*100:+.2f}%</td><td></td><td></td><td id="tmv">{mv:,.0f}</td><td id="taw">{mv/CAPITAL*100:.2f}</td></tr></tfoot>
</table>
<p style="color:#777">手数 = 向下取整（当前权重 × 初始资金 × 仓位 ÷ (价格 × 100)）；现金 = 初始资金 − 持仓市值。</p>
<p style="color:#777">权重按收盘价计算，每天更新一次；打开页面时自动加载最新数据。</p>
<script>
const CAPITAL = {CAPITAL};
const CUR_DATE = '{today.date()}';

function num(x) {{ const v = parseFloat(x); return isFinite(v) ? v : 0; }}

function loadLatest() {{
  fetch('今日权重.csv?_=' + Date.now(), {{cache: 'no-store'}})
    .then(r => r.text())
    .then(txt => {{
      const lines = txt.trim().split(/\\r?\\n/);
      if (lines.length < 2) return;
      const head = lines[0].split(',').map(s => s.replace(/^\\uFEFF/, '').trim());
      const col = n => head.indexOf(n);
      const recs = lines.slice(1).map(l => l.split(','));
      const d = recs[0][col('data_date')] || CUR_DATE;
      let mv = 0, pnl = 0;
      const tb = document.getElementById('tb');
      for (const r of recs) {{
        const code = r[col('code')].padStart(6, '0');
        const tr = tb.querySelector("tr[data-code='" + code + "']");
        if (!tr) continue;
        const now = num(r[col('now')]) * 100;
        const dw = num(r[col('dw')]) * 100;
        const ret = num(r[col('ret')]) * 100;
        const ct = num(r[col('contrib')]) * 100;
        const price = num(r[col('price')]);
        const lots = Math.round(num(r[col('lots')]));
        const value = num(r[col('actual_value')]);
        const aw = num(r[col('actual_w')]) * 100;
        const p = num(r[col('pnl')]);
        mv += value; pnl += p;
        tr.querySelector('.c-now').innerHTML = '<b>' + now.toFixed(2) + '</b>';
        const e1 = tr.querySelector('.c-dw'); e1.textContent = (dw >= 0 ? '+' : '') + dw.toFixed(2); e1.className = 'c-dw ' + (dw > 0 ? 'up' : (dw < 0 ? 'down' : ''));
        const e2 = tr.querySelector('.c-ret'); e2.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%'; e2.className = 'c-ret ' + (ret > 0 ? 'up' : (ret < 0 ? 'down' : ''));
        const e3 = tr.querySelector('.c-contrib'); e3.textContent = (ct >= 0 ? '+' : '') + ct.toFixed(2) + '%'; e3.className = 'c-contrib ' + (ct > 0 ? 'up' : (ct < 0 ? 'down' : ''));
        tr.querySelector('.c-price').textContent = price.toFixed(2);
        tr.querySelector('.c-lots').textContent = lots.toLocaleString();
        tr.querySelector('.c-value').textContent = Math.round(value).toLocaleString();
        tr.querySelector('.c-aw').textContent = aw.toFixed(2);
      }}
      const cash = CAPITAL - mv, pr = pnl / CAPITAL * 100;
      document.getElementById('mv').textContent = Math.round(mv).toLocaleString();
      document.getElementById('cash').textContent = Math.round(cash).toLocaleString();
      const ep = document.getElementById('pnl'); ep.textContent = (pnl >= 0 ? '+' : '') + Math.round(pnl).toLocaleString(); ep.className = pnl >= 0 ? 'up' : 'down';
      const er = document.getElementById('pret'); er.textContent = (pr >= 0 ? '+' : '') + pr.toFixed(2) + '%'; er.className = pr >= 0 ? 'up' : 'down';
      document.getElementById('tcontrib').textContent = (pr >= 0 ? '+' : '') + pr.toFixed(2) + '%';
      document.getElementById('tmv').textContent = Math.round(mv).toLocaleString();
      document.getElementById('taw').textContent = (mv / CAPITAL * 100).toFixed(2);
      document.getElementById('ddate').textContent = d;
      document.getElementById('st').textContent = '已加载最新数据（数据日期 ' + d + '，检查时间 ' + new Date().toLocaleTimeString() + '）';
    }})
    .catch(() => {{ document.getElementById('st').textContent = '无法读取最新数据，显示页面生成时的结果'; }});
}}
loadLatest();
document.addEventListener('visibilitychange', () => {{ if (!document.hidden) loadLatest(); }});
</script>
</body></html>"""
out = outdir("report") / "dashboard.html"
out.write_text(html, encoding="utf-8")
(outdir("report") / "index.html").write_text('<meta http-equiv="refresh" content="0; url=dashboard.html">', encoding="utf-8")
T.to_csv(outdir("report") / "今日权重.csv", index=False, encoding="utf-8-sig")
T.to_csv(outdir("stats") / "今日权重.csv", index=False, encoding="utf-8-sig")
print("面板已生成:", out)
print(T[["name", "now", "price", "lots", "actual_value", "actual_w"]].to_string(index=False))
print(f"持仓市值 {mv:,.0f} 现金 {cash:,.0f} 今日盈亏 {pnl:+,.0f}")
