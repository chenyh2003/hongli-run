# -*- coding: utf-8 -*-
"""一键运行：拉数据 -> 缓存 -> BCD -> 对账 -> 报告"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.load(open(ROOT / "config.json", encoding="utf-8"))
LOG = ROOT / "output" / "run.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line.replace("\ufffd", "?"))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(script):
    log(f"运行 {script}")
    r = subprocess.run([sys.executable, str(ROOT / "code" / script)], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.stdout:
        log(r.stdout.strip())
    if r.returncode != 0:
        if r.stderr:
            log(r.stderr.strip())
        log(f"{script} 失败，退出码 {r.returncode}")
        sys.exit(r.returncode)
    return r

try:
    mode = os.getenv("UPDATE_MODE", "")
    if mode == "daily":
        run("update_daily.py")
    elif not CFG["offline"]:
        run("fetch_data.py")
    else:
        log("离线模式：跳过数据拉取")

    cache = ROOT / CFG["paths"]["cache"] / "daily_cache.npz"
    if not cache.exists():
        run("build_cache.py")
    else:
        log("日频缓存已存在，跳过构建")

    run("run_s1.py")
    run("verify.py")
    run("report.py")
    run("dashboard.py")

    import pandas as pd
    st = pd.read_csv(ROOT / CFG["paths"]["output"] / "stats" / "绩效.csv")
    txt = "\n".join(f"{r['口径']}: 年化 {r['年化%']}% 回撤 {r['回撤%']}% 夏普 {r['夏普']}" for _, r in st.iterrows())
    (ROOT / "output" / "summary.txt").write_text(txt, encoding="utf-8")
    log("完成")
    log(txt)
except SystemExit as e:
    raise
