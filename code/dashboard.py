# -*- coding: utf-8 -*-
"""持仓面板：仓位按月锁定，价格/收益实时估值。

- 股数在最近一次月度换仓日锁定，持有到下次换仓日；
- 实时行情只更新价格、市值、实际权重、盈亏，不重算股数；
- 目标权重与手数在两次换仓之间不变。
"""
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from common import path, outdir

CAPITAL = 1_000_000

CACHE = path("cache")
z = np.load(CACHE / ("daily_cache_slim.npz" if (CACHE / "daily_cache_slim.npz").exists() else "daily_cache.npz"), allow_pickle=True)
dates = pd.to_datetime(z["dates"])
codes = z["codes"]
raw = pd.DataFrame(z["raw"], index=dates, columns=codes)
rawf = raw.ffill()

H = pd.read_csv(outdir("holdings") / "BCD_monthly_weights.csv", parse_dates=["date"], dtype={"code": str})
H["code"] = H["code"].str.zfill(6)
A = pd.read_csv(outdir("holdings") / "BCD_年度持仓.csv", parse_dates=["date"], dtype={"code": str})
A["code"] = A["code"].str.zfill(6)
META = A.drop_duplicates("code").set_index("code")[["name", "l3"]].to_dict("index")
ST = pd.read_csv(outdir("holdings") / "BCD_state.csv", parse_dates=["date"]).set_index("date")["exposure"]

D = raw.index
today = D[-1]
prev = D[-2]
mwd = H[H["date"] <= today]["date"].max()
base = H[H["date"] == mwd].set_index("code")["weight"]
expo = float(ST.asof(mwd)) if pd.notna(ST.asof(mwd)) else 1.0


def first_weekday(y, m):
    d = date(y, m, 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def next_reb(td):
    y, m = td.year, td.month
    if td >= first_weekday(y, m):
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return first_weekday(y, m)


nxt = next_reb(today.date())

px0 = rawf.loc[mwd, base.index]
shares = (np.floor(base * CAPITAL * expo / px0 / 100) * 100).astype(int)
cost = shares * px0
cash = CAPITAL - cost.sum()

close_px = rawf.loc[today, base.index]
prev_px = rawf.loc[prev, base.index]
value = shares * close_px
day_pnl = shares * (close_px - prev_px)
cum_pnl = value - cost
total = value.sum() + cash
aw = value / total

T = pd.DataFrame({
    "code": base.index,
    "name": [META.get(c, {}).get("name", "") for c in base.index],
    "l3": [META.get(c, {}).get("l3", "") for c in base.index],
    "target": base.values,
    "shares": shares.reindex(base.index).values,
    "lots": (shares.reindex(base.index) // 100).values,
    "base_px": px0.reindex(base.index).values,
    "prev_close": prev_px.reindex(base.index).values,
    "close_px": close_px.reindex(base.index).values,
    "value": value.reindex(base.index).values,
    "aw": aw.reindex(base.index).values,
    "day_pnl": day_pnl.reindex(base.index).values,
    "cum_pnl": cum_pnl.reindex(base.index).values,
})
T["day_ret"] = T["close_px"] / T["prev_close"] - 1
T["contrib"] = T["day_pnl"] / CAPITAL
T["cost"] = cost.reindex(base.index).values
T = T.sort_values("value", ascending=False).reset_index(drop=True)

mv = T["value"].sum()
pnl = T["day_pnl"].sum()
cum = total - CAPITAL
pret = pnl / (mv - pnl + cash) * 100 if (mv - pnl + cash) else 0.0
ctret = cum / CAPITAL * 100

rows = []
for _, r in T.iterrows():
    dcls = "up" if r["day_ret"] > 0 else ("down" if r["day_ret"] < 0 else "")
    ccls = "up" if r["cum_pnl"] > 0 else ("down" if r["cum_pnl"] < 0 else "")
    rows.append(
        f"<tr data-code='{r['code']}'><td>{r['name']}</td><td>{r['code']}</td><td>{r['l3']}</td>"
        + f"<td class='c-target'>{r['target']*100:.2f}</td>"
        + f"<td class='c-now'><b>{r['aw']*100:.2f}</b></td>"
        + f"<td class='c-dw'>{0:+.2f}</td>"
        + f"<td class='c-ret {dcls}'>{r['day_ret']*100:+.2f}%</td>"
        + f"<td class='c-contrib {dcls}'>{r['contrib']*100:+.2f}%</td>"
        + f"<td class='c-price'>{r['close_px']:.2f}</td>"
        + f"<td class='c-lots'>{r['lots']:,}</td>"
        + f"<td class='c-value'>{r['value']:,.0f}</td>"
        + f"<td class='c-cum {ccls}'>{r['cum_pnl']:+,.0f}</td>"
        + "</tr>")

DATA = {
    "capital": CAPITAL,
    "cash": round(float(cash), 2),
    "exposure": expo,
    "mwd": str(mwd.date()),
    "next_reb": str(nxt),
    "rows": [
        {
            "code": r["code"], "name": r["name"], "l3": r["l3"],
            "target": float(r["target"]), "shares": int(r["shares"]),
            "cost": round(float(r["cost"]), 2), "base_px": round(float(r["base_px"]), 4),
            "prev_close": round(float(r["prev_close"]), 4), "close_px": round(float(r["close_px"]), 4),
        }
        for _, r in T.iterrows()
    ],
}

JS = r"""
const SYM = c => (c[0] === '6' ? 'sh' : 'sz') + c;
function apply() {
  const px = {}, pv = {}, tm = {};
  let tstr = '';
  for (const r of DATA.rows) {
    const v = window['v_' + SYM(r.code)];
    if (!v) continue;
    const f = v.split('~');
    const p = parseFloat(f[3]), q = parseFloat(f[4]);
    if (!isFinite(p) || !isFinite(q) || q <= 0) continue;
    px[r.code] = p; pv[r.code] = q; tm[r.code] = f[30] || '';
    if (f[30]) tstr = f[30];
  }
  if (!Object.keys(px).length) return;

  const vals = {};
  let mv = 0, dayPnl = 0, prevMv = 0;
  for (const r of DATA.rows) {
    const p = px[r.code] || r.close_px;
    const q = pv[r.code] || r.prev_close;
    const val = r.shares * p;
    const pval = r.shares * q;
    vals[r.code] = { p, q, val, pval };
    mv += val; prevMv += pval; dayPnl += r.shares * (p - q);
  }
  const total = mv + DATA.cash;
  const prevTotal = prevMv + DATA.cash;
  const tb = document.getElementById('tb');

  for (const r of DATA.rows) {
    const x = vals[r.code];
    const aw = x.val / total, paw = x.pval / prevTotal;
    const dw = aw - paw;
    const ret = x.p / x.q - 1;
    const contrib = r.shares * (x.p - x.q) / prevTotal;
    const cum = x.val - r.cost;
    const tr = tb.querySelector("tr[data-code='" + r.code + "']");
    if (!tr) continue;
    tr.querySelector('.c-now').innerHTML = '<b>' + (aw * 100).toFixed(2) + '</b>';
    const e1 = tr.querySelector('.c-dw');
    e1.textContent = (dw >= 0 ? '+' : '') + (dw * 100).toFixed(2);
    e1.className = 'c-dw ' + (dw > 0 ? 'up' : (dw < 0 ? 'down' : ''));
    const e2 = tr.querySelector('.c-ret');
    e2.textContent = (ret >= 0 ? '+' : '') + (ret * 100).toFixed(2) + '%';
    e2.className = 'c-ret ' + (ret > 0 ? 'up' : (ret < 0 ? 'down' : ''));
    const e3 = tr.querySelector('.c-contrib');
    e3.textContent = (contrib >= 0 ? '+' : '') + (contrib * 100).toFixed(2) + '%';
    e3.className = 'c-contrib ' + (contrib > 0 ? 'up' : (contrib < 0 ? 'down' : ''));
    tr.querySelector('.c-price').textContent = x.p.toFixed(2);
    tr.querySelector('.c-value').textContent = Math.round(x.val).toLocaleString();
    const e4 = tr.querySelector('.c-cum');
    e4.textContent = (cum >= 0 ? '+' : '') + Math.round(cum).toLocaleString();
    e4.className = 'c-cum ' + (cum > 0 ? 'up' : (cum < 0 ? 'down' : ''));
  }

  const cum = total - DATA.capital;
  const pret = dayPnl / prevTotal * 100;
  document.getElementById('total').textContent = Math.round(total).toLocaleString();
  document.getElementById('mv').textContent = Math.round(mv).toLocaleString();
  document.getElementById('cash').textContent = Math.round(DATA.cash).toLocaleString();
  const ec = document.getElementById('cum');
  ec.textContent = (cum >= 0 ? '+' : '') + Math.round(cum).toLocaleString();
  ec.className = cum >= 0 ? 'up' : 'down';
  const ep = document.getElementById('pnl');
  ep.textContent = (dayPnl >= 0 ? '+' : '') + Math.round(dayPnl).toLocaleString();
  ep.className = dayPnl >= 0 ? 'up' : 'down';
  const er = document.getElementById('pret');
  er.textContent = (pret >= 0 ? '+' : '') + pret.toFixed(2) + '%';
  er.className = pret >= 0 ? 'up' : 'down';
  document.getElementById('tcontrib').textContent = (pret >= 0 ? '+' : '') + pret.toFixed(2) + '%';
  document.getElementById('tmv').textContent = Math.round(mv).toLocaleString();
  document.getElementById('tcum').textContent = (cum >= 0 ? '+' : '') + Math.round(cum).toLocaleString();

  const t = tstr && tstr.length >= 14
    ? tstr.slice(0, 4) + '-' + tstr.slice(4, 6) + '-' + tstr.slice(6, 8) + ' ' + tstr.slice(8, 10) + ':' + tstr.slice(10, 12) + ':' + tstr.slice(12, 14)
    : '';
  document.getElementById('st').textContent = '实时估值 ' + new Date().toLocaleTimeString() + (t ? ' · 行情时间 ' + t : '') + ' · 仓位锁定 ' + DATA.mwd + ' · 下次换仓 ' + DATA.next_reb;
}

function refresh() {
  const s = document.createElement('script');
  s.charset = 'gbk';
  s.src = 'https://qt.gtimg.cn/q=' + DATA.rows.map(r => SYM(r.code)).join(',') + '&_=' + Date.now();
  s.onload = () => { try { apply(); } catch (e) { console.log(e); } s.remove(); };
  s.onerror = () => { document.getElementById('st').textContent = '实时行情不可用，显示收盘估值 · 仓位锁定 ' + DATA.mwd; s.remove(); };
  document.head.appendChild(s);
}
refresh();
setInterval(refresh, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
"""

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
<div>数据日期：<b>{today.date()}</b> ｜ 目标权重基准日：{mwd.date()} ｜ 初始资金：{CAPITAL:,} 元 ｜ 仓位：{expo*100:.0f}% ｜ 下次换仓：{nxt}</div>
<div id="st">仓位锁定在 {mwd.date()} 换仓日；盘中只更新价格、市值、实际权重、盈亏</div>
<div class="cards">
<div class="card"><span>总资产</span><b id="total">{total:,.0f}</b></div>
<div class="card"><span>持仓市值</span><b id="mv">{mv:,.0f}</b></div>
<div class="card"><span>现金</span><b id="cash">{cash:,.0f}</b></div>
<div class="card"><span>累计盈亏</span><b id="cum" class="{'up' if cum>0 else 'down'}">{cum:+,.0f}</b></div>
<div class="card"><span>今日盈亏</span><b id="pnl" class="{'up' if pnl>0 else 'down'}">{pnl:+,.0f}</b></div>
<div class="card"><span>今日收益率</span><b id="pret" class="{'up' if pret>0 else 'down'}">{pret:+.2f}%</b></div>
</div>
<table>
<thead><tr><th>名称</th><th>代码</th><th>行业</th><th>目标%</th><th>当前%</th><th>Δ昨日</th>
<th>今日涨跌</th><th>今日贡献</th><th>价格</th><th>手数</th><th>市值(元)</th><th>累计盈亏</th></tr></thead>
<tbody id="tb">{''.join(rows)}</tbody>
<tfoot><tr><td colspan="3">合计（含现金）</td><td></td><td></td><td></td><td></td>
<td id="tcontrib">{pret:+.2f}%</td><td></td><td></td><td id="tmv">{mv:,.0f}</td>
<td id="tcum">{cum:+,.0f}</td></tr></tfoot>
</table>
<p style="color:#777">手数在 {mwd.date()} 换仓日锁定（目标权重 × 100 万 ÷ 换仓价，向下取整到 100 股），持有到 {nxt} 再换；盘中不因价格变化改股数。</p>
<p style="color:#777">当前% = 实时市值 ÷ 总资产；累计盈亏 = 市值 − 换仓成本；今日盈亏 = 股数 ×（现价 − 昨收）。</p>
<script>
const DATA = {json.dumps(DATA, ensure_ascii=False)};
{JS}
</script>
</body></html>"""

out = outdir("report") / "dashboard.html"
out.write_text(html, encoding="utf-8")
(outdir("report") / "index.html").write_text('<meta http-equiv="refresh" content="0; url=dashboard.html">', encoding="utf-8")
T.to_csv(outdir("report") / "今日权重.csv", index=False, encoding="utf-8-sig")
T.to_csv(outdir("stats") / "今日权重.csv", index=False, encoding="utf-8-sig")
print("面板已生成:", out)
print(T[["name", "target", "aw", "lots", "value", "cum_pnl"]].to_string(index=False))
print(f"总资产 {total:,.0f} 持仓市值 {mv:,.0f} 现金 {cash:,.0f} 累计盈亏 {cum:+,.0f} 今日盈亏 {pnl:+,.0f}")
