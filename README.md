# 红利运行（策略1 BCD 独立版）

在 `红利\` 之外独立运行策略1 的 BCD 层：选股（冻结持仓）+ 行业内权重 + 外层择时，次日成交。

## 目录

```
红利运行\
  config.json           # 开关、参数、路径
  data\
    raw\                # 原始行情/分红/指数
    cache\              # 日频缓存、分红再投资收益
    industry\           # 行业景气、三级收益面板、行业映射
    rates\              # 国债、回购、Shibor
  frozen\
    s1_holdings.json    # 冻结持仓（上游选股结果）
    reference\          # 对账用参考净值（不复权/含分红）
    benchmark\          # 000922/红利低波/红利质量/沪深300
  code\
    common.py
    fetch_data.py       # akshare 增量拉取
    build_cache.py      # 原始 -> 缓存
    run_s1.py           # BCD 计算
    verify.py           # 与参考净值对账
    report.py           # 图表 + HTML
    run_all.py          # 一键运行
  output\
    nav\  holdings\  stats\  charts\  report\
    run.log  summary.txt
```

## 运行

```bash
python code/run_all.py
```

- `config.json` 中 `offline: true` 时跳过拉取，直接用本地缓存。
- 首次或缓存缺失时才运行 `build_cache.py`。

## 对账

`verify.py` 会把重算净值与 `frozen/reference` 逐日比对：

- 容差 `1e-8`
- 年化差 < 0.01pct
- 不通过则退出码 2，不生成报告

## 输出

- `output/nav/BCD_不复权.csv`、`BCD_含分红.csv`
- `output/holdings/BCD_年度持仓.csv`
- `output/stats/绩效.csv`、`对账.csv`
- `output/charts/*.png`（净值、回撤、超额、行业权重）
- `output/report/report.html`
- `output/summary.txt`

## 说明

- 上游选股依赖缺失的 60% 筛选表，因此冻结为持仓 JSON，不在本目录重跑选股。
- 基准均为含分红全收益，策略线同时提供不复权与含分红两套。

## GitHub 自动运行

1. 新建 GitHub 仓库，推送本目录
2. Settings → Pages → Source 选择 **GitHub Actions**
3. Actions 中启用 daily-bcd 工作流
4. 面板地址：https://<用户名>.github.io/<仓库名>/dashboard.html

工作流：

- 时间：每个工作日 UTC 10:00（北京时间 18:00）
- 只拉取 26 只持仓股票 + 利率，不使用全市场数据
- 自动提交 data/cache、data/rates、output，并部署 Pages
- 支持手动触发（workflow_dispatch）

注意：

- akshare 可能对 GitHub IP 限流；若失败可改用自托管 runner
- 瘦缓存已提交在 data/cache/*_slim.npz，无需首次全量下载
- 基准指数与行业文件已随仓库提交
