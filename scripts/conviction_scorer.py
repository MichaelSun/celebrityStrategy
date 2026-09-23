#!/usr/bin/env python3
"""
Phase 2 - Building Conviction Scorer
Automatically computes multi-quarter conviction scores from SQLite portfolio_history.

Scoring Logic:
  Per ticker-guru pair (rolling last N quarters):
    +3  per NEW position quarter
    +2  per ADD/BUY quarter (increasing)
    +0  per NO_CHANGE quarter
    -1  per REDUCE quarter
    -4  per SOLD quarter (resets streak)

  Cross-guru Resonance Multiplier (applied to final score):
    × 1.5  for Tier 1 + Tier 1 simultaneous buy
    × 1.3  for Tier 1 + Tier 2 simultaneous buy
    × 1.1  for Tier 2 + Tier 2 simultaneous buy
    × 1.0  otherwise

  Building Streak: consecutive quarters of ADD or NEW (no reductions in between)

Outputs:
  - SQLite: conviction_scores table
  - Markdown: top conviction leaderboard section
"""

import datetime
import math
import os
import sqlite3
from collections import defaultdict


# ── Tier Configuration ──────────────────────────────────────────────────────
GURU_TIER = {
    "HC": 1, "HH": 1, "BRK": 1,
    "PI": 2, "aq": 2, "SE": 2, "FS": 2, "MKL": 2,
    "psc": 3, "AM": 3, "oc": 3, "GLRE": 3,
}
GURU_SHORT = {
    "HC": "李录", "HH": "段永平", "BRK": "巴菲特",
    "PI": "帕布莱", "aq": "斯皮尔", "SE": "霍金斯",
    "FS": "史密斯", "MKL": "盖纳",
    "psc": "阿克曼", "AM": "泰珀", "oc": "马克斯", "GLRE": "艾因霍恩",
}


def _classify_activity(activity: str) -> str:
    """Normalize activity string to signal category."""
    if not activity:
        return "NO_CHANGE"
    a = activity.lower()
    if "sell" in a and "100" in a:
        return "SOLD"
    if "sell" in a or "sold" in a:
        return "SOLD"
    if "reduce" in a or "trim" in a:
        return "REDUCE"
    if "add" in a or "increase" in a:
        return "INCREASED"
    if "buy" in a or "new" in a:
        return "NEW"
    return "NO_CHANGE"


SCORE_MAP = {
    "NEW": 3,
    "INCREASED": 2,
    "NO_CHANGE": 0,
    "REDUCE": -1,
    "SOLD": -4,
}


def ensure_conviction_table(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS conviction_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        computed_at TEXT NOT NULL,
        ticker TEXT NOT NULL,
        guru_code TEXT NOT NULL,
        raw_score INTEGER DEFAULT 0,
        resonance_multiplier REAL DEFAULT 1.0,
        final_score REAL DEFAULT 0.0,
        building_streak INTEGER DEFAULT 0,
        quarters_active INTEGER DEFAULT 0,
        latest_signal TEXT,
        latest_quarter TEXT,
        resonance_gurus TEXT,
        UNIQUE(computed_at, ticker, guru_code)
    )
    """)
    conn.commit()


def quarter_sort_key(q_str):
    """Parse 'Q2 2026' or '2026 Q2' into (year, quarter_num) tuple for chronological sorting."""
    parts = q_str.strip().split()
    year = 0
    q_num = 0
    for p in parts:
        if p.isdigit() and len(p) == 4:
            year = int(p)
        elif p.upper().startswith("Q") and p[1:].isdigit():
            q_num = int(p[1:])
    return (year, q_num)


def compute_conviction_scores(db_path, rolling_quarters=6):
    """
    Main computation:
    1. Load portfolio_history for last N quarters
    2. For each (ticker, guru) pair, compute score + streak
    3. Compute cross-guru resonance multiplier
    4. Return sorted leaderboard list
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ensure_conviction_table(conn)

    # Get all distinct quarters and sort chronologically descending
    raw_quarters = [row[0] for row in cur.execute("SELECT DISTINCT quarter FROM portfolio_history").fetchall()]
    quarters = sorted(raw_quarters, key=quarter_sort_key, reverse=True)[:rolling_quarters]
    if not quarters:
        conn.close()
        return []

    # Load all relevant history
    rows = cur.execute("""
    SELECT ticker, company_name, guru_code, quarter, activity, portfolio_weight, shares_held
    FROM portfolio_history
    WHERE quarter IN ({})
    ORDER BY ticker, guru_code, quarter ASC
    """.format(",".join("?" * len(quarters))), quarters).fetchall()

    # Build per-ticker-guru timeline
    # Structure: { ticker: { guru_code: [(quarter, activity, weight, shares)] } }
    timeline = defaultdict(lambda: defaultdict(list))
    ticker_names = {}
    for row in rows:
        timeline[row["ticker"]][row["guru_code"]].append({
            "quarter": row["quarter"],
            "signal": _classify_activity(row["activity"]),
            "weight": row["portfolio_weight"] or 0.0,
            "shares": row["shares_held"] or 0,
        })
        if row["company_name"]:
            ticker_names[row["ticker"]] = row["company_name"]

    # Compute scores
    scores = []  # list of dicts
    computed_at = datetime.date.today().isoformat()

    for ticker, guru_map in timeline.items():
        for guru_code, history in guru_map.items():
            # Sort by quarter (ascending = chronological)
            history_sorted = sorted(history, key=lambda x: quarter_sort_key(x["quarter"]))

            raw_score = 0
            streak = 0
            streak_broken = False
            latest_signal = "NO_CHANGE"
            latest_quarter = ""

            for entry in history_sorted:
                sig = entry["signal"]
                raw_score += SCORE_MAP.get(sig, 0)
                latest_signal = sig
                latest_quarter = entry["quarter"]

                if sig in ("NEW", "INCREASED"):
                    if not streak_broken:
                        streak += 1
                elif sig == "SOLD":
                    streak = 0
                    streak_broken = True
                elif sig == "REDUCE":
                    streak_broken = True  # breaks streak but doesn't zero it

            scores.append({
                "ticker": ticker,
                "company": ticker_names.get(ticker, ticker),
                "guru_code": guru_code,
                "raw_score": raw_score,
                "building_streak": streak,
                "quarters_active": len(history_sorted),
                "latest_signal": latest_signal,
                "latest_quarter": latest_quarter,
                "resonance_multiplier": 1.0,
                "final_score": float(raw_score),
                "resonance_gurus": "",
            })

    # Compute cross-guru resonance multiplier
    # Group by ticker → find which gurus are buying this quarter
    latest_q = quarters[0]  # most recent quarter
    ticker_buyers = defaultdict(list)  # ticker → [guru_code, ...]
    for row in rows:
        if row["quarter"] == latest_q and _classify_activity(row["activity"]) in ("NEW", "INCREASED"):
            ticker_buyers[row["ticker"]].append(row["guru_code"])

    # Apply resonance multiplier
    for s in scores:
        buyers = ticker_buyers.get(s["ticker"], [])
        other_buyers = [g for g in buyers if g != s["guru_code"]]
        if not other_buyers:
            continue

        # Compute max multiplier from any pair
        best_mult = 1.0
        for other in other_buyers:
            t1 = GURU_TIER.get(s["guru_code"], 3)
            t2 = GURU_TIER.get(other, 3)
            min_tier = min(t1, t2)
            if min_tier == 1:
                mult = 1.5
            elif min_tier == 2:
                mult = 1.3
            else:
                mult = 1.1
            best_mult = max(best_mult, mult)

        s["resonance_multiplier"] = best_mult
        s["final_score"] = round(s["raw_score"] * best_mult, 2)
        s["resonance_gurus"] = "+".join(
            GURU_SHORT.get(g, g) for g in other_buyers
        )

    # Persist to DB
    conn.execute(
        f"DELETE FROM conviction_scores WHERE computed_at = '{computed_at}'"
    )
    for s in scores:
        conn.execute("""
        INSERT OR REPLACE INTO conviction_scores
        (computed_at, ticker, guru_code, raw_score, resonance_multiplier,
         final_score, building_streak, quarters_active, latest_signal,
         latest_quarter, resonance_gurus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            computed_at, s["ticker"], s["guru_code"], s["raw_score"],
            s["resonance_multiplier"], s["final_score"], s["building_streak"],
            s["quarters_active"], s["latest_signal"], s["latest_quarter"],
            s["resonance_gurus"],
        ))
    conn.commit()
    conn.close()

    # Sort by final_score descending, only keep non-SOLD with score > 0
    leaderboard = sorted(
        [s for s in scores if s["latest_signal"] != "SOLD" and s["final_score"] > 0],
        key=lambda x: (x["final_score"], x["building_streak"]),
        reverse=True,
    )
    return leaderboard


def format_conviction_section(leaderboard, top_n=15):
    """Generate Markdown section: Building Conviction Leaderboard."""
    lines = []
    L = lines.append
    L("## 🏆 多季度决心积累排行榜（Building Conviction Leaderboard）")
    L("")
    L("> **积分规则：** 新建仓 +3 · 加仓 +2 · 不变 0 · 减仓 -1 · 清仓 -4")
    L("> **共振乘数：** Tier1+Tier1 ×1.5 · Tier1+Tier2 ×1.3 · Tier2+Tier2 ×1.1")
    L("> **建仓连续性：** 连续季度加仓/新买计为 Building Streak 不断档加分")
    L("")
    L("| 排名 | 标的 | 大师 | 原始分 | 共振乘数 | **最终积分** | 连续季度 | 共振伙伴 | 最新信号 |")
    L("|:---:|:---|:---|:---:|:---:|:---:|:---:|:---|:---|")

    signal_emoji = {
        "NEW": "✨ 新买入",
        "INCREASED": "🔺 加仓",
        "NO_CHANGE": "🔵 持有",
        "REDUCE": "🔻 减仓",
        "SOLD": "❌ 清仓",
    }

    for i, s in enumerate(leaderboard[:top_n], 1):
        tier = GURU_TIER.get(s["guru_code"], 0)
        tier_label = ["", "🥇", "🥈", "🥉"][tier] if tier in (1, 2, 3) else ""
        guru_disp = f"{tier_label}{GURU_SHORT.get(s['guru_code'], s['guru_code'])}"
        mult_str = f"×{s['resonance_multiplier']:.1f}" if s["resonance_multiplier"] > 1.0 else "—"
        resonance = s["resonance_gurus"] if s["resonance_gurus"] else "—"
        sig = signal_emoji.get(s["latest_signal"], s["latest_signal"])
        streak_str = f"**{s['building_streak']}季**" if s["building_streak"] >= 3 else f"{s['building_streak']}季"
        L(
            f"| {i} | **{s['ticker']}** {s['company'][:20]} "
            f"| {guru_disp} | {s['raw_score']} | {mult_str} "
            f"| **{s['final_score']:.1f}** | {streak_str} "
            f"| {resonance} | {sig} |"
        )

    L("")
    # Highlight extreme streak holders
    long_streaks = [s for s in leaderboard if s["building_streak"] >= 4]
    if long_streaks:
        L("### 🔥 超长连续建仓（≥4 季不断档）")
        for s in long_streaks[:5]:
            guru = GURU_SHORT.get(s["guru_code"], s["guru_code"])
            L(
                f"- **{s['ticker']}** ({s['company'][:25]}) — {guru} "
                f"已连续 **{s['building_streak']} 个季度** 持续买入，积分 {s['final_score']:.0f}"
            )
        L("")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys, argparse

    parser = argparse.ArgumentParser(description="Phase 2: Building Conviction Scorer")
    parser.add_argument("--db", type=str, default="", help="Path to investor_radar.db")
    parser.add_argument("--quarters", type=int, default=6, help="Rolling window of quarters to analyze")
    parser.add_argument("--top", type=int, default=15, help="Top N in leaderboard")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.normpath(os.path.join(script_dir, "..", "data", "investor_radar.db"))

    if not os.path.exists(db_path):
        print(f"❌ DB not found: {db_path}")
        sys.exit(1)

    print(f"🧮 Computing conviction scores (rolling {args.quarters} quarters)...")
    leaderboard = compute_conviction_scores(db_path, rolling_quarters=args.quarters)
    print(f"  ✅ {len(leaderboard)} active conviction entries computed")
    print()
    print(format_conviction_section(leaderboard, top_n=args.top))
