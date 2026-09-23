#!/usr/bin/env python3
"""
Pipeline Bridge: Connects celebrityStrategy (13F Radar) with cfo-check (Forensic Valuation Engine)
Extracts top-conviction guru candidates and feeds them directly into cfo-check batch scanner.
"""

import argparse
import os
import re
import subprocess
import sys
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFO_CHECK_ROOT = "/Users/michael/Documents/GoogleAntigravity/cfo-check"

def find_latest_report():
    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    files = [f for f in os.listdir(reports_dir) if f.startswith("celebrity_clone_") and f.endswith(".md")]
    if not files:
        return None
    # Sort by modification time
    files.sort(key=lambda f: os.path.getmtime(os.path.join(reports_dir, f)), reverse=True)
    return os.path.join(reports_dir, files[0])

def extract_candidates_from_report(report_path):
    candidates = []
    if not report_path or not os.path.exists(report_path):
        return ["PDD", "BRK.B", "TSLA", "CRDO"]
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"本季度最高确信度与共振候选标的为：\*\*`([^`]+)`\*\*", text)
        if m:
            cands = [x.strip() for x in m.group(1).split(",") if x.strip()]
            if cands:
                return cands
    except Exception:
        pass
    return ["PDD", "BRK.B", "TSLA", "CRDO"]

def main():
    parser = argparse.ArgumentParser(description="Bridge 13F Top Candidates to CFO-Check Valuation Pipeline")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers (e.g. PDD,TSLA,CRDO). Auto-detects if empty.")
    parser.add_argument("--mode", type=str, choices=["screen", "full"], default="screen", help="cfo-check mode: screen (fast pre-screen) or full (5-report deep dive)")
    parser.add_argument("--archive-obsidian", action="store_true", help="Sync full reports to Obsidian (full mode only)")
    parser.add_argument("--dry-run", action="store_true", help="Generate watchlist YAML without running cfo-check")
    args = parser.parse_args()

    if not os.path.exists(CFO_CHECK_ROOT):
        print(f"❌ cfo-check project not found at: {CFO_CHECK_ROOT}")
        sys.exit(1)

    # 1. Resolve Tickers
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        latest = find_latest_report()
        tickers = extract_candidates_from_report(latest)
        print(f"📡 Auto-detected Top Candidates from latest report ({os.path.basename(latest) if latest else 'default'}): {', '.join(tickers)}")

    if not tickers:
        print("❌ No tickers specified or detected.")
        sys.exit(1)

    # 2. Build cfo-check watchlist YAML
    watchlist_dir = os.path.join(CFO_CHECK_ROOT, "batch-scanner", "watchlists")
    os.makedirs(watchlist_dir, exist_ok=True)
    watchlist_path = os.path.join(watchlist_dir, "13f_top_candidates.yaml")

    watchlist_data = {
        "name": "13F 聪明钱高决心与共振候选池",
        "description": "由 celebrityStrategy 前道雷达筛选出的顶级投资人重注、共振与成本优势标的",
        "companies": [{"ticker": t, "name": t, "currency": "USD", "priority": "high"} for t in tickers]
    }

    with open(watchlist_path, "w", encoding="utf-8") as f:
        yaml.dump(watchlist_data, f, allow_unicode=True, sort_keys=False)

    print(f"✅ Generated cfo-check watchlist: {watchlist_path}")

    if args.dry_run:
        print("🔍 Dry-run complete. Exiting.")
        return

    # 3. Invoke cfo-check batch_runner.py
    runner_script = os.path.join(CFO_CHECK_ROOT, "batch-scanner", "scripts", "batch_runner.py")
    cmd = [
        sys.executable,
        runner_script,
        "--watchlist", "batch-scanner/watchlists/13f_top_candidates.yaml",
        "--mode", args.mode,
    ]
    if args.archive_obsidian:
        cmd.append("--archive-obsidian")

    print(f"\n🚀 Invoking cfo-check forensic engine ({args.mode} mode)...")
    print(f"   Command: {' '.join(cmd)}")
    print(f"   Working Directory: {CFO_CHECK_ROOT}\n")

    try:
        res = subprocess.run(cmd, cwd=CFO_CHECK_ROOT)
        if res.returncode == 0:
            print("\n🎉 cfo-check forensic analysis completed successfully!")
        else:
            print(f"\n⚠️ cfo-check exited with code {res.returncode}")
    except Exception as e:
        print(f"❌ Failed to run cfo-check: {e}")

if __name__ == "__main__":
    main()
