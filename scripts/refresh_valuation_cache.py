#!/usr/bin/env python3
"""
Phase 2 - Valuation Cache Refresher
Populates the valuation_cache table with key fundamental metrics from yfinance,
plus HK/A-share real-time prices from yfinance ADR proxies.

Fetched per ticker:
  - current_price, pe_ttm, forward_pe, fcf_yield, market_cap_b
  - week52_low, week52_high, sector

For off-13F holdings (HK/A-shares), uses ADR or related ticker as proxy.
"""

import datetime
import os
import sqlite3
import sys

try:
    import yfinance as yf
except ImportError:
    print("❌ yfinance not installed. Run: pip install yfinance")
    sys.exit(1)


# ── Off-13F HK/A-share proxy map ────────────────────────────────────────────
# Maps official ticker (as in off_13f_holdings.yaml) → yfinance-queryable symbol
OFF_13F_PROXIES = {
    "1211.HK": "BYDDY",      # BYD Co. — US ADR
    "1658.HK": "PSBC.HK",    # Postal Savings Bank of China — HK direct (works via yfinance)
    "0700.HK": "TCEHY",      # Tencent Holdings — US ADR (Pink Sheet)
    "600519.SH": "CRHKY",    # Kweichow Moutai — OTC ADR
    "9992.HK": "9992.HK",    # Pop Mart — directly queryable via yfinance HK
}

# Canonical tickers to always include in valuation refresh (guru core holdings)
CORE_TICKERS = [
    # HC (Li Lu) core
    "GOOGL", "GOOG", "PDD", "BRK-B", "EWBC", "CROX", "TME", "AAPL",
    # HH (Duan Yongping) core
    "BABA", "NVDA", "MSFT", "TSLA", "DIS", "CRDO",
    # BRK (Buffett) core
    "OXY", "AXP", "KO", "BAC", "CVX", "MCO", "DAL",
    # Off-13F proxies
    "BYDDY", "TCEHY", "CRHKY",
]


def get_all_tickers_from_db(db_path):
    """Pull all unique tickers currently in portfolio_history with actual holdings."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
    SELECT DISTINCT ticker FROM portfolio_history
    WHERE portfolio_weight > 0 OR shares_held > 0
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


import concurrent.futures

def fetch_single_ticker_valuation(orig_ticker: str, yf_ticker: str) -> dict:
    """Fetch valuation and price metrics for a single ticker via yfinance."""
    try:
        tk = yf.Ticker(yf_ticker)
        info = tk.info or {}
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if not current_price:
            try:
                current_price = tk.fast_info.get("lastPrice") or tk.fast_info.get("previousClose")
            except Exception:
                pass

        pe_ttm = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        market_cap = info.get("marketCap")
        if not market_cap:
            try:
                market_cap = tk.fast_info.get("marketCap")
            except Exception:
                pass

        week52_low = info.get("fiftyTwoWeekLow")
        if not week52_low:
            try:
                week52_low = tk.fast_info.get("yearLow")
            except Exception:
                pass

        week52_high = info.get("fiftyTwoWeekHigh")
        if not week52_high:
            try:
                week52_high = tk.fast_info.get("yearHigh")
            except Exception:
                pass

        sector = info.get("sector", "")
        fcf = info.get("freeCashflow")
        fcf_yield = None
        if fcf and market_cap and market_cap > 0:
            fcf_yield = round(fcf / market_cap * 100, 2)  # as percentage

        market_cap_b = round(market_cap / 1e9, 2) if market_cap else None

        return {
            "ticker": orig_ticker,
            "current_price": current_price,
            "pe_ttm": pe_ttm,
            "forward_pe": forward_pe,
            "fcf_yield": fcf_yield,
            "market_cap_b": market_cap_b,
            "week52_low": week52_low,
            "week52_high": week52_high,
            "sector": sector,
            "error": None
        }
    except Exception as e:
        return {
            "ticker": orig_ticker,
            "current_price": None,
            "pe_ttm": None,
            "forward_pe": None,
            "fcf_yield": None,
            "market_cap_b": None,
            "week52_low": None,
            "week52_high": None,
            "sector": "",
            "error": str(e)
        }


def refresh_valuation_cache(db_path, extra_tickers=None, verbose=True, max_workers=16):
    """
    Fetch valuation data from yfinance concurrently and write to valuation_cache table.
    Returns count of successfully updated tickers.
    """
    # Collect all tickers to refresh
    db_tickers = get_all_tickers_from_db(db_path)
    all_tickers = sorted(list(set(CORE_TICKERS + db_tickers + (extra_tickers or []))))

    # Normalize for yfinance (e.g. BRK.B -> BRK-B, off-13F proxies)
    yf_map = {}
    for t in all_tickers:
        if t in OFF_13F_PROXIES:
            yf_map[t] = OFF_13F_PROXIES[t]
        else:
            yf_map[t] = t.replace(".", "-")

    if verbose:
        print(f"  📡 Concurrently fetching valuation data for {len(all_tickers)} tickers from yfinance ({max_workers} threads)...")

    now_ts = datetime.datetime.now().isoformat(timespec="seconds")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_single_ticker_valuation, t, yf_map[t]): t
            for t in all_tickers
        }
        for future in concurrent.futures.as_completed(future_map):
            res = future.result()
            results.append(res)
            if verbose and res.get("current_price"):
                p = res["current_price"]
                pe = f"PE={res['pe_ttm']:.1f}" if res.get('pe_ttm') else "PE=N/A"
                fcf = f"FCF%={res['fcf_yield']:.1f}%" if res.get('fcf_yield') else "FCF=N/A"
                print(f"    ✅ {res['ticker']:12s} ${p:<8.2f} {pe:12s} {fcf}")
            elif verbose:
                print(f"    ⚠️ {res['ticker']:12s} — no price data ({res.get('error') or 'empty'})")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    updated = 0

    for res in results:
        if res.get("current_price"):
            cur.execute("""
            INSERT OR REPLACE INTO valuation_cache
            (ticker, current_price, pe_ttm, forward_pe, fcf_yield,
             market_cap_b, week52_low, week52_high, sector, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                res["ticker"], res["current_price"], res["pe_ttm"], res["forward_pe"], res["fcf_yield"],
                res["market_cap_b"], res["week52_low"], res["week52_high"], res["sector"], now_ts,
            ))
            updated += 1

    conn.commit()
    conn.close()
    return updated


def format_valuation_section(db_path, tickers=None, top_n=20):
    """Generate Markdown valuation snapshot table from valuation_cache."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if tickers:
        placeholders = ",".join("?" * len(tickers))
        rows = conn.execute(
            f"SELECT * FROM valuation_cache WHERE ticker IN ({placeholders}) ORDER BY market_cap_b DESC NULLS LAST",
            tickers
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM valuation_cache ORDER BY market_cap_b DESC NULLS LAST LIMIT ?",
            (top_n,)
        ).fetchall()
    conn.close()

    if not rows:
        return ""

    lines = []
    L = lines.append
    L("## 📊 基本面估值快照（Valuation Cache — yfinance 实时刷新）")
    L("")
    L(f"> **更新时间：** {rows[0]['updated_at'] if rows else '—'}")
    L("")
    L("| 标的 | 行业板块 | 当前价 | TTM P/E | Fwd P/E | FCF Yield | 市值 | 52W低 | 52W高 |")
    L("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

    for row in rows:
        pe = f"{row['pe_ttm']:.1f}" if row["pe_ttm"] else "—"
        fwd_pe = f"{row['forward_pe']:.1f}" if row["forward_pe"] else "—"
        fcf_y = f"**{row['fcf_yield']:.1f}%**" if row["fcf_yield"] else "—"
        cap = f"${row['market_cap_b']:.0f}B" if row["market_cap_b"] else "—"
        lo = f"${row['week52_low']:.2f}" if row["week52_low"] else "—"
        hi = f"${row['week52_high']:.2f}" if row["week52_high"] else "—"
        price = f"${row['current_price']:.2f}" if row["current_price"] else "—"
        L(
            f"| **{row['ticker']}** | {(row['sector'] or '—')[:20]} "
            f"| {price} | {pe} | {fwd_pe} | {fcf_y} | {cap} | {lo} | {hi} |"
        )

    L("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2: Valuation Cache Refresher")
    parser.add_argument("--db", type=str, default="", help="Path to investor_radar.db")
    parser.add_argument("--tickers", type=str, default="", help="Extra comma-sep tickers to add")
    parser.add_argument("--no-verbose", action="store_true", help="Suppress per-ticker output")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.normpath(os.path.join(script_dir, "..", "data", "investor_radar.db"))

    if not os.path.exists(db_path):
        print(f"❌ DB not found: {db_path}")
        sys.exit(1)

    extra = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else []
    count = refresh_valuation_cache(db_path, extra_tickers=extra, verbose=not args.no_verbose)
    print(f"\n✅ Valuation cache updated: {count} tickers")
    print("\n" + format_valuation_section(db_path, top_n=15))
