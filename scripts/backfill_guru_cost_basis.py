#!/usr/bin/env python3
"""
Institutional Historical Cost Basis & Multi-Quarter Acquisition Inflow Engine
Resolves the SEC Form 13F "Reported Price = Quarter-End Closing Market Price" illusion.

Background:
  By SEC law, Form 13F DOES NOT require institutions to report purchase price or cost basis.
  The "Reported Price" on Form 13F / Dataroma is strictly:
    Fair Market Value ÷ Shares Held = Quarter-End Closing Market Price on the last day of the quarter.
  For long-term core holdings (e.g., Buffett in AAPL since 2016, Li Lu in GOOGL since 2022,
  Guy Spier in BRK since 2014), the Q2 2026 quarter-end market price is 2x to 10x higher than
  their true historical acquisition cost basis!

This engine:
  1. Crawls full historical quarterly filings for every active guru holding from Dataroma (/m/hist/hist.php).
  2. Reconstructs the position lot inflow trail:
     - Tracks initial Buy quarter & price
     - Tracks subsequent Adds & accumulated share capital
     - Adjusts for share reductions (FIFO / proportional lot relief)
     - Computes the TRUE estimated capital-weighted historical acquisition cost basis.
  3. Stores the derived cost basis, first-buy period, and full quarter-by-quarter JSON trail
     in SQLite table `guru_cost_basis`.
"""

import concurrent.futures
import json
import os
import re
import sqlite3
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "investor_radar.db")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session

SESSION = get_session()


def ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guru_cost_basis (
        guru_code TEXT NOT NULL,
        ticker TEXT NOT NULL,
        first_buy_period TEXT,
        first_buy_price REAL DEFAULT 0.0,
        estimated_avg_cost REAL DEFAULT 0.0,
        latest_period TEXT,
        latest_reported_price REAL DEFAULT 0.0,
        holding_quarters INTEGER DEFAULT 0,
        history_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guru_code, ticker)
    )
    """)
    conn.commit()


def fetch_holding_history(guru_code: str, ticker: str) -> Optional[List[Dict]]:
    """Fetch quarter-by-quarter history from Dataroma for a guru position."""
    url = f"https://www.dataroma.com/m/hist/hist.php?f={guru_code}&s={ticker}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
    except Exception as e:
        return None

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.DOTALL)
    history = []
    for row in rows:
        tds = [re.sub(r"<[^>]+>", "", td).strip().replace("&nbsp;", " ").replace("&nbsp", " ") for td in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
        if len(tds) >= 6:
            period = tds[0].strip()
            # Normalize whitespace
            period = " ".join(period.split())
            if not any(period.startswith(str(y)) for y in range(1990, 2035)):
                continue
            shares_str = tds[1].replace(",", "").strip()
            shares = int(shares_str) if shares_str.isdigit() else 0
            act = tds[3].strip()
            price_str = tds[5].replace("$", "").replace(",", "").strip()
            try:
                price = float(price_str) if price_str else 0.0
            except ValueError:
                price = 0.0
            history.append({
                "period": period,
                "shares": shares,
                "activity": act,
                "reported_price": price
            })
    return history if history else None


def calculate_cost_basis(guru_code: str, ticker: str, history: List[Dict]) -> Dict:
    """
    Simulate lot inflows and compute true historical acquisition cost basis.
    history is from newest to oldest in raw table, so we reverse it to chronological order.
    """
    chrono = list(reversed(history))

    lots = []  # list of [shares, price, period]
    first_buy_period = None
    first_buy_price = 0.0

    for h in chrono:
        shares = h["shares"]
        price = h["reported_price"]

        if shares == 0:
            lots = []
            continue

        cur_held = sum(lot[0] for lot in lots)
        if cur_held == 0:
            # Initial Buy
            lots = [[shares, price, h["period"]]]
            if not first_buy_period:
                first_buy_period = h["period"]
                first_buy_price = price
        elif shares > cur_held:
            # Added shares in this quarter
            diff = shares - cur_held
            lots.append([diff, price, h["period"]])
        elif shares < cur_held:
            # Reduced shares - proportional relief across lots
            ratio = shares / cur_held
            for lot in lots:
                lot[0] *= ratio

    total_shares = sum(lot[0] for lot in lots)
    latest_reported_price = history[0]["reported_price"] if history else 0.0
    latest_period = history[0]["period"] if history else ""

    if total_shares > 0:
        total_invested = sum(lot[0] * lot[1] for lot in lots if lot[1] > 0)
        valid_shares = sum(lot[0] for lot in lots if lot[1] > 0)
        avg_cost = total_invested / valid_shares if valid_shares > 0 else latest_reported_price
    else:
        avg_cost = latest_reported_price

    if not first_buy_period and history:
        first_buy_period = history[-1]["period"]
        first_buy_price = history[-1]["reported_price"]

    # Filter out quarters where shares == 0 at the end if already exited
    active_history = [h for h in history if h["shares"] > 0]
    holding_quarters = len(active_history)

    return {
        "guru_code": guru_code,
        "ticker": ticker,
        "first_buy_period": first_buy_period or latest_period,
        "first_buy_price": round(first_buy_price, 2),
        "estimated_avg_cost": round(avg_cost, 2),
        "latest_period": latest_period,
        "latest_reported_price": round(latest_reported_price, 2),
        "holding_quarters": holding_quarters,
        "history_json": json.dumps(history, ensure_ascii=False)
    }


def process_target(target: Tuple[str, str]) -> Optional[Dict]:
    guru_code, ticker = target
    hist = fetch_holding_history(guru_code, ticker)
    if not hist:
        return None
    return calculate_cost_basis(guru_code, ticker, hist)


def run_cost_backfill(db_path: str = DB_PATH, max_workers: int = 8):
    print(f"📡 Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    cur = conn.cursor()

    # Query all active holdings in the most recent quarter (Q2 2026)
    cur.execute("""
    SELECT DISTINCT guru_code, ticker 
    FROM portfolio_history 
    WHERE quarter = 'Q2 2026' AND shares_held > 0
    """)
    targets = cur.fetchall()
    print(f"🎯 Found {len(targets)} active guru positions in Q2 2026 to backfill.")

    results = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {executor.submit(process_target, t): t for t in targets}
        for future in concurrent.futures.as_completed(future_to_target):
            t = future_to_target[future]
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                pass
            completed += 1
            if completed % 25 == 0 or completed == len(targets):
                print(f"  ⏳ Processed {completed}/{len(targets)} positions ({len(results)} successful)...")

    print(f"\n💾 Persisting {len(results)} calculated historical cost bases into database...")
    for r in results:
        cur.execute("""
        INSERT OR REPLACE INTO guru_cost_basis 
        (guru_code, ticker, first_buy_period, first_buy_price, estimated_avg_cost, latest_period, latest_reported_price, holding_quarters, history_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            r["guru_code"], r["ticker"], r["first_buy_period"], r["first_buy_price"],
            r["estimated_avg_cost"], r["latest_period"], r["latest_reported_price"],
            r["holding_quarters"], r["history_json"]
        ))
    conn.commit()
    conn.close()
    print(f"✅ Successfully backfilled {len(results)} guru historical cost bases into SQLite!\n")


if __name__ == "__main__":
    run_cost_backfill()
