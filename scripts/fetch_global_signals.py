#!/usr/bin/env python3
"""
Phase 2 - Global Signal Fetcher
Pulls Dataroma-wide signals:
  1. Grand Portfolio   — aggregate consensus holdings across all tracked superinvestors
  2. All Activity Feed — recent buys/adds across all managers in a single pass

Writes to:
  - SQLite: grand_portfolio_snapshot, global_activity_signals
  - Returns: structured dicts for report integration
"""

import datetime
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Constants ────────────────────────────────────────────────────────────────
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA}

# Guru codes we track (from the main skill config)
TRACKED_GURU_CODES = {
    "HC", "HH", "BRK", "PI", "aq", "SE", "FS", "MKL", "psc", "AM", "oc", "GLRE"
}

# Dataroma guru code → short name mapping (for display in reports)
GURU_SHORT_NAMES = {
    "HC": "李录", "HH": "段永平", "BRK": "巴菲特",
    "PI": "帕布莱", "aq": "斯皮尔", "SE": "霍金斯",
    "FS": "史密斯", "MKL": "盖纳",
    "psc": "阿克曼", "AM": "泰珀", "oc": "马克斯", "GLRE": "艾因霍恩",
}
GURU_TIER = {
    "HC": 1, "HH": 1, "BRK": 1,
    "PI": 2, "aq": 2, "SE": 2, "FS": 2, "MKL": 2,
    "psc": 3, "AM": 3, "oc": 3, "GLRE": 3,
}


def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1.0,
                    status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


SESSION = get_session()


# ─── 1. Grand Portfolio ───────────────────────────────────────────────────────

def fetch_grand_portfolio():
    """
    Fetch the Dataroma Grand Portfolio — aggregate holdings across all superinvestors.
    Returns list of dicts:
      ticker, company, portfolio_pct, ownership_count, hold_price,
      max_pct, current_price, week52_low, week52_high
    Sorted by portfolio_pct descending (consensus weight).
    """
    url = "https://www.dataroma.com/m/g/portfolio.php"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 5000:
            return []
    except Exception as e:
        print(f"  ⚠️ Grand Portfolio fetch failed: {e}")
        return []

    # Each <tr> in the tbody corresponds to one holding row
    # columns: sym, stock, pct, ownership_count, hold_price, max_pct,
    #          current_price, 52w_low, 52w_high (no 52w_high shown directly)
    rows = re.findall(
        r'<td class="sym"><a href="/m/stock\.php\?sym=([A-Z.]+)">[^<]+</a></td>\s*'
        r'<td class="stock"><a[^>]+>([^<]+)</a></td>\s*'
        r'<td[^>]*>([\d.]+)</td>\s*'         # portfolio_pct
        r'<td[^>]*>(\d+)</td>\s*'             # ownership_count
        r'<td class="hld">\$([\d.,]+)</td>\s*' # hold_price
        r'<td class="hld">([\d.]+)</td>\s*'  # max_pct
        r'<td[^>]*>\$([\d.,]+)</td>\s*'      # current_price
        r'<td[^>]*>\$([\d.,]+)</td>',         # 52w_low
        resp.text
    )

    holdings = []
    for r in rows:
        try:
            holdings.append({
                "ticker": r[0],
                "company": r[1].strip(),
                "portfolio_pct": float(r[2]),
                "ownership_count": int(r[3]),
                "hold_price": float(r[4].replace(",", "")),
                "max_pct": float(r[5]),
                "current_price": float(r[6].replace(",", "")),
                "week52_low": float(r[7].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue

    return sorted(holdings, key=lambda x: x["portfolio_pct"], reverse=True)


# ─── 2. All Activity Feed ──────────────────────────────────────────────────────

def fetch_all_activity(activity_type="a"):
    """
    Fetch Dataroma All Activity page — latest buys/sells across ALL superinvestors.
    activity_type: 'a' = all, 'b' = buys only, 's' = sells only.

    Returns list of dicts per manager row:
      firm, firm_code, period, top_actions=[{ticker, company, action_text, is_buy}]

    Also filters and marks which entries match TRACKED_GURU_CODES.
    """
    url = f"https://www.dataroma.com/m/allact.php?typ={activity_type}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 5000:
            return []
    except Exception as e:
        print(f"  ⚠️ All Activity fetch failed: {e}")
        return []

    results = []
    # Each <tr> = one firm's latest activity summary
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.S)
    for row in rows:
        firm_m = re.search(r'href="/m/m_activity\.php\?m=([^&]+)&typ=a"[^>]*>([^<]+)</a>', row)
        if not firm_m:
            continue
        firm_code = firm_m.group(1).strip()
        firm_name = firm_m.group(2).strip()

        period_m = re.search(r'<td class="period">(.*?)</td>', row)
        period = period_m.group(1).strip().replace("&nbsp;", " ").replace("&nbsp", " ") if period_m else ""

        # Extract ticker actions — each is wrapped in <span class="tit_ctl">
        actions = []
        for span in re.finditer(
            r'<a class="(buy|sell)" href="/m/activity\.php\?sym=([A-Z.]+)&typ=a">([A-Z.]+)</a>\s*'
            r'<div>([^<]+)<br/>([^<]+)<br/>([^<]+)</div>',
            row, re.S
        ):
            is_buy = span.group(1) == "buy"
            ticker = span.group(2)
            company = span.group(4).strip()
            action_text = span.group(5).strip()
            pct_change = span.group(6).strip()
            actions.append({
                "ticker": ticker,
                "company": company,
                "action_text": action_text,
                "pct_change": pct_change,
                "is_buy": is_buy,
            })

        # Determine if this is one of our tracked gurus
        is_tracked = firm_code in TRACKED_GURU_CODES
        results.append({
            "firm_code": firm_code,
            "firm_name": firm_name,
            "period": period,
            "is_tracked": is_tracked,
            "tier": GURU_TIER.get(firm_code, 0),
            "short_name": GURU_SHORT_NAMES.get(firm_code, firm_name),
            "top_actions": actions,
        })

    return results


# ─── 3. Portfolio History Weights Backfill ────────────────────────────────────

def fetch_portfolio_history_weights(code):
    """
    Fetch /m/hist/p_hist.php?f={code} — quarterly portfolio snapshots (Top 20 per quarter).
    Returns dict: { "YYYY Q{N}": {ticker: pct, ...}, ... }
    Used to backfill portfolio_weight in portfolio_history table.
    """
    url = f"https://www.dataroma.com/m/hist/p_hist.php?f={code}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 3000:
            return {}
    except Exception as e:
        print(f"  ⚠️ p_hist fetch failed for {code}: {e}")
        return {}

    # Each <tr> = one quarter row
    # Period cell: "2026 &nbsp Q2" → "2026 Q2" → normalize to "Q2 2026"
    quarters = {}
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.S)
    for row in rows:
        period_m = re.search(r'<td class="period">(.*?)</td>', row)
        if not period_m:
            continue
        period_raw = period_m.group(1).replace("&nbsp;", " ").replace("&nbsp", " ").strip()
        # "2026  Q2" → "Q2 2026"
        period_parts = period_raw.split()
        if len(period_parts) >= 2:
            year_part = next((p for p in period_parts if p.isdigit() and len(p) == 4), None)
            q_part = next((p for p in period_parts if p.startswith("Q")), None)
            if year_part and q_part:
                period_key = f"{q_part} {year_part}"
            else:
                period_key = period_raw
        else:
            period_key = period_raw

        # Extract all tickers + weights in this row
        ticker_weights = {}
        for m in re.finditer(
            r'<a href="/m/stock\.php\?sym=([A-Z.]+)"[^>]*>[A-Z.]+</a>\s*'
            r'<div><b>[^<]+</b><br/>([\d.]+)% of portfolio</div>',
            row
        ):
            ticker = m.group(1)
            pct = float(m.group(2))
            ticker_weights[ticker] = pct

        if ticker_weights:
            quarters[period_key] = ticker_weights

    return quarters


def backfill_portfolio_weights(db_path, guru_codes, delay=1.0):
    """
    For each guru in guru_codes, fetch p_hist and update portfolio_history rows
    that currently have portfolio_weight = 0.0.
    Returns total updated count.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    total_updated = 0

    for code in guru_codes:
        print(f"  📡 Fetching p_hist for {code}...")
        quarter_data = fetch_portfolio_history_weights(code)
        if not quarter_data:
            print(f"    ⚠️ No data for {code}")
            continue

        for quarter, ticker_weights in quarter_data.items():
            for ticker, weight in ticker_weights.items():
                rows_updated = cur.execute("""
                    UPDATE portfolio_history
                    SET portfolio_weight = ?
                    WHERE guru_code = ? AND quarter = ? AND ticker = ?
                      AND portfolio_weight = 0.0
                """, (weight, code, quarter, ticker)).rowcount
                total_updated += rows_updated

        time.sleep(delay)

    conn.commit()
    conn.close()
    return total_updated


# ─── 4. SQLite Schema Extensions ──────────────────────────────────────────────

def ensure_phase2_tables(db_path):
    """Create Phase 2 tables if they don't already exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Grand Portfolio consensus snapshot
    cur.execute("""
    CREATE TABLE IF NOT EXISTS grand_portfolio_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        company TEXT,
        portfolio_pct REAL DEFAULT 0.0,
        ownership_count INTEGER DEFAULT 0,
        hold_price REAL DEFAULT 0.0,
        max_pct REAL DEFAULT 0.0,
        current_price REAL DEFAULT 0.0,
        week52_low REAL DEFAULT 0.0,
        UNIQUE(snapshot_date, ticker)
    )
    """)

    # Global activity signals (cross-manager buy signals)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS global_activity_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TEXT NOT NULL,
        firm_code TEXT NOT NULL,
        period TEXT,
        ticker TEXT NOT NULL,
        company TEXT,
        action_text TEXT,
        pct_change TEXT,
        is_buy INTEGER DEFAULT 1,
        is_tracked INTEGER DEFAULT 0,
        tier INTEGER DEFAULT 0,
        UNIQUE(snapshot_date, firm_code, ticker)
    )
    """)

    conn.commit()
    conn.close()


def save_grand_portfolio(db_path, holdings):
    """Persist grand portfolio snapshot with today's date."""
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    inserted = 0
    for h in holdings:
        try:
            cur.execute("""
            INSERT OR REPLACE INTO grand_portfolio_snapshot
            (snapshot_date, ticker, company, portfolio_pct, ownership_count,
             hold_price, max_pct, current_price, week52_low)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today, h["ticker"], h["company"], h["portfolio_pct"],
                h["ownership_count"], h["hold_price"], h["max_pct"],
                h["current_price"], h["week52_low"],
            ))
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


def save_activity_signals(db_path, activity_rows):
    """Persist global activity signals."""
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    inserted = 0
    for firm in activity_rows:
        for act in firm.get("top_actions", []):
            try:
                cur.execute("""
                INSERT OR REPLACE INTO global_activity_signals
                (snapshot_date, firm_code, period, ticker, company,
                 action_text, pct_change, is_buy, is_tracked, tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    today, firm["firm_code"], firm.get("period", ""),
                    act["ticker"], act["company"],
                    act["action_text"], act["pct_change"],
                    1 if act["is_buy"] else 0,
                    1 if firm["is_tracked"] else 0,
                    firm.get("tier", 0),
                ))
                inserted += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    return inserted


# ─── 5. Report Sections ────────────────────────────────────────────────────────

def format_grand_portfolio_section(holdings, tracked_codes=None, top_n=30):
    """Generate Markdown section: Grand Portfolio Consensus Heatmap."""
    lines = []
    L = lines.append
    L("## 🌐 全市场大师共识热力图（Grand Portfolio Consensus）")
    L("")
    L("> **数据源：** Dataroma Grand Portfolio — 覆盖所有追踪超级投资人的合并持仓")
    L("> **字段说明：** `共识%` = 所有大师加权合并的总持仓占比；`持有者数` = 持有该标的的大师数量；`最高单持` = 持仓最重的单一大师占比")
    L("")
    L("| 标的 | 公司名称 | 共识持仓% | 持有者数 | 申报均价 | 最高单持% | 当前现价 | 52W低 |")
    L("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
    for h in holdings[:top_n]:
        is_tracked_str = "⭐" if tracked_codes and h["ticker"] in tracked_codes else ""
        L(
            f"| {is_tracked_str}**{h['ticker']}** | {h['company'][:30]} "
            f"| **{h['portfolio_pct']:.3f}%** | {h['ownership_count']} 家 "
            f"| ${h['hold_price']:.2f} | {h['max_pct']:.2f}% "
            f"| ${h['current_price']:.2f} | ${h['week52_low']:.2f} |"
        )
    L("")
    return "\n".join(lines)


def format_tracked_activity_section(activity_rows):
    """Generate Markdown section for tracked gurus in the All Activity feed."""
    tracked = [r for r in activity_rows if r["is_tracked"]]
    if not tracked:
        return ""

    lines = []
    L = lines.append
    L("## 📡 本期追踪大师全市场最新操作速览（All Activity Feed）")
    L("")
    L("以下为 Dataroma 全市场 Activity 页面中，本次追踪的核心大师的最新买卖操作：")
    L("")

    # Sort by tier then name
    tracked.sort(key=lambda x: (x["tier"], x["firm_code"]))
    for firm in tracked:
        tier_label = ["", "🥇 Tier 1", "🥈 Tier 2", "🥉 Tier 3"][firm["tier"]]
        L(f"### {tier_label} · {firm['short_name']} ({firm['firm_code']}) — {firm.get('period', '')}")
        buys = [a for a in firm["top_actions"] if a["is_buy"]]
        sells = [a for a in firm["top_actions"] if not a["is_buy"]]
        if buys:
            buy_strs = [f"**{a['ticker']}** ({a['action_text']})" for a in buys]
            L(f"- 🔺 **买入/加仓：** {' · '.join(buy_strs)}")
        if sells:
            sell_strs = [f"**{a['ticker']}** ({a['action_text']})" for a in sells]
            L(f"- 🔻 **减持/清仓：** {' · '.join(sell_strs)}")
        L("")

    return "\n".join(lines)


# ─── 6. Main Entrypoint ────────────────────────────────────────────────────────

def run_global_signals(db_path, backfill_codes=None, save_to_db=True, verbose=True):
    """
    Main function: fetch all global signals and optionally persist to DB.
    Returns: (grand_portfolio_holdings, activity_rows, backfill_count)
    """
    # Ensure tables exist
    ensure_phase2_tables(db_path)

    # 1. Grand Portfolio
    if verbose:
        print("📡 Fetching Grand Portfolio consensus heatmap...")
    gp = fetch_grand_portfolio()
    if verbose:
        print(f"  ✅ {len(gp)} holdings in Grand Portfolio (top: "
              + ", ".join(h["ticker"] for h in gp[:5]) + ")")

    # 2. All Activity
    if verbose:
        print("📡 Fetching All Activity feed (buys + sells)...")
    activity = fetch_all_activity("a")
    tracked_firms = [r for r in activity if r["is_tracked"]]
    if verbose:
        print(f"  ✅ {len(activity)} firms in activity feed, "
              f"{len(tracked_firms)} are our tracked gurus")

    # 3. Save to DB
    if save_to_db:
        gp_inserted = save_grand_portfolio(db_path, gp)
        act_inserted = save_activity_signals(db_path, activity)
        if verbose:
            print(f"  💾 Saved: {gp_inserted} grand portfolio rows, {act_inserted} activity signals")

    # 4. Backfill historical weights
    backfill_count = 0
    if backfill_codes:
        if verbose:
            print(f"\n📡 Backfilling historical portfolio_weight for: {', '.join(backfill_codes)}...")
        backfill_count = backfill_portfolio_weights(db_path, backfill_codes)
        if verbose:
            print(f"  ✅ Updated {backfill_count} historical rows with portfolio_weight")

    return gp, activity, backfill_count


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Phase 2: Global Signal Fetcher")
    parser.add_argument("--db", type=str, default="", help="Path to investor_radar.db")
    parser.add_argument("--backfill", type=str, default="HC,HH", help="Comma-separated guru codes to backfill (e.g. HC,HH,BRK)")
    parser.add_argument("--no-db", action="store_true", help="Skip database writes (dry run)")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Auto-discover from script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, "..", "data", "investor_radar.db")
        db_path = os.path.normpath(db_path)

    if not os.path.exists(db_path):
        print(f"⚠️ DB not found at {db_path}. Run init_radar_database.py first.")
        sys.exit(1)

    backfill_codes = [c.strip() for c in args.backfill.split(",") if c.strip()]

    gp, activity, backfill_count = run_global_signals(
        db_path=db_path,
        backfill_codes=backfill_codes,
        save_to_db=not args.no_db,
        verbose=True,
    )

    # Print report sections
    print("\n" + "="*70)
    # Build set of tracked tickers currently in our portfolios
    tracked_tickers = set()
    for code in TRACKED_GURU_CODES:
        pass  # We'd normally load from DB; here just use grand portfolio top 30

    print(format_grand_portfolio_section(gp, top_n=20))
    print(format_tracked_activity_section(activity))
    print(f"\n✅ Phase 2 Global Signals complete. Backfill updated: {backfill_count} rows")
