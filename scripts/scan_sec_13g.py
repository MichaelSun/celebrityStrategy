#!/usr/bin/env python3
"""
P1 Optimization - SEC Schedule 13G / 13D Early Warning Scanner
Bypasses the 45-day Form 13F reporting lag by monitoring 5%+ beneficial ownership filings.

Two-Track Detection:
  Track 1: Guru CIK Direct Query
           Checks if any of our tracked superinvestor CIKs filed a 13G or 13D recently.
  Track 2: Candidate Ticker Whales Query
           Scans SEC EFTS for recent 13G/13D filings on our candidate watchlist
           to see if institutional whales (e.g., Berkshire, Dodge & Cox, Elliott)
           have acquired or amended a 5%+ stake.

Outputs:
  - SQLite: sec_13g_signals table in data/investor_radar.db
  - Markdown: section for inclusion in quarterly audit reports
"""

import argparse
import datetime
import os
import re
import sqlite3
import sys
import time
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Headers & Session Setup ──────────────────────────────────────────────────
SEC_UA = "MichaelSun ResearchAgent/1.0 (contact@example.com)"
SEC_HEADERS = {"User-Agent": SEC_UA}

def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session

SESSION = get_session()

# Tracked gurus with SEC CIKs
TRACKED_GURUS_CIK = {
    "BRK": {"name": "Warren Buffett - Berkshire Hathaway", "short": "巴菲特", "cik": "0001067983", "tier": 1},
    "HC":  {"name": "Li Lu - Himalaya Capital", "short": "李录", "cik": "0001709323", "tier": 1},
    "HH":  {"name": "Duan Yongping - H&H International", "short": "段永平", "cik": "0001759760", "tier": 1},
    "SE":  {"name": "Mason Hawkins - Southeastern", "short": "霍金斯", "cik": "0000720875", "tier": 2},
    "MKL": {"name": "Thomas Gayner - Markel Group", "short": "盖纳", "cik": "0001096343", "tier": 2},
}

DEFAULT_CANDIDATE_TICKERS = [
    "PDD", "BRK.B", "CROX", "EWBC", "OXY", "DHI", "TME", "GOOGL", "GOOG", "DAL", "LEN", "BABA"
]


# ── Database Schema Setup ────────────────────────────────────────────────────
def ensure_13g_table(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sec_13g_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_date TEXT NOT NULL,
        form_type TEXT NOT NULL,
        filer_name TEXT NOT NULL,
        filer_cik TEXT,
        subject_name TEXT,
        subject_ticker TEXT,
        accession_num TEXT UNIQUE,
        url TEXT,
        ownership_pct REAL DEFAULT 0.0,
        is_tracked_guru INTEGER DEFAULT 0,
        tier INTEGER DEFAULT 0,
        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()


KNOWN_ISSUER_TICKERS = {
    "LENNAR": "LEN",
    "DELTA AIR": "DAL",
    "BERKSHIRE": "BRK.A",
    "OCCIDENTAL": "OXY",
    "EAST WEST": "EWBC",
    "CROCS": "CROX",
    "PINDUODUO": "PDD",
    "PDD HOLDINGS": "PDD",
    "TENCENT MUSIC": "TME",
    "ALPHABET": "GOOGL",
    "D.R. HORTON": "DHI",
    "APPLE": "AAPL",
    "MARKEL": "MKL",
    "LIBERTY MEDIA": "FWONA",
    "SIRIUS XM": "SIRI",
    "KRAFT HEINZ": "KHC",
    "AMERICAN EXPRESS": "AXP",
    "BANK OF AMERICA": "BAC",
    "CHEVRON": "CVX",
    "COCA COLA": "KO",
    "MOODY'S": "MCO",
    "DYNATRONICS": "DYNT",
    "HAGERTY": "HGTY",
    "CHUBB": "CB",
    "CONSTELLATION": "STZ",
    "DOMINO": "DPZ",
    "LIBERTY LATIN AMERICA": "LILA",
    "LIBERTY LIVE": "LLYVA",
    "NEW YORK TIMES": "NYT",
    "POOL": "POOL",
    "VERISIGN": "VRSN",
}

def _infer_ticker(name: str) -> str:
    upper = name.upper()
    for k, t in KNOWN_ISSUER_TICKERS.items():
        if k in upper:
            return t
    return ""

def _fetch_13g_details(cik: str, acc: str) -> tuple:
    """Fetch primary XML and extract (issuer_name, percent_of_class, ticker)"""
    cik_int = str(int(cik))
    acc_nodash = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/primary_doc.xml"
    try:
        r = SESSION.get(url, headers=SEC_HEADERS, timeout=8)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.text)
            issuer = ""
            pct = 0.0
            for elem in root.iter():
                tag = elem.tag.split("}")[-1]
                if tag == "issuerName" and not issuer:
                    issuer = (elem.text or "").strip()
                elif tag in ("classPercent", "percentOfClass") and pct == 0.0:
                    try:
                        pct = float(elem.text.strip())
                    except (ValueError, AttributeError):
                        pass
            ticker = _infer_ticker(issuer)
            return issuer, pct, ticker
    except Exception:
        pass
    return "", 0.0, ""

# ── Track 1: Guru CIK Direct Query ───────────────────────────────────────────
def scan_guru_13g_filings(ciks_dict: Dict, days_back: int = 180) -> List[Dict]:
    """
    Query SEC Submissions API for tracked guru CIKs and extract recent 13G/13D filings.
    """
    signals = []
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()

    for code, info in ciks_dict.items():
        cik = info.get("cik")
        if not cik:
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            resp = SESSION.get(url, headers=SEC_HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accs = recent.get("accessionNumber", [])
            docs = recent.get("primaryDocument", [])

            for i, f in enumerate(forms):
                if "13G" in f or "13D" in f:
                    f_date = dates[i] if i < len(dates) else ""
                    if f_date and f_date >= cutoff_date:
                        acc = accs[i] if i < len(accs) else ""
                        acc_nodash = acc.replace("-", "")
                        cik_int = str(int(cik))

                        # Fetch issuer and percent from XML details
                        issuer, pct, ticker = _fetch_13g_details(cik, acc)
                        subject_name = issuer if issuer else "（见申报明细）"

                        filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{acc}-index.html"
                        signals.append({
                            "filing_date": f_date,
                            "form_type": f,
                            "filer_name": info["name"],
                            "filer_cik": cik,
                            "subject_name": subject_name,
                            "subject_ticker": ticker,
                            "accession_num": acc,
                            "url": filing_url,
                            "ownership_pct": pct,
                            "is_tracked_guru": 1,
                            "tier": info["tier"],
                            "guru_code": code,
                        })
            time.sleep(0.1)  # Respect SEC rate limit
        except Exception as e:
            print(f"  ⚠️ Error scanning CIK {cik} ({info['name']}): {e}")

    return signals


# ── Track 2: Candidate Ticker Whales Query (EFTS) ─────────────────────────────
def scan_ticker_13g_filings(tickers: List[str], days_back: int = 180) -> List[Dict]:
    """
    Search SEC EFTS for recent 13G/13D filings on specific candidate tickers/names.
    """
    signals = []
    start_dt = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()
    end_dt = datetime.date.today().isoformat()

    # Map tickers to query names where needed to avoid false positives
    TICKER_QUERY_MAP = {
        "PDD": '"PDD Holdings"',
        "BRK.B": '"Berkshire Hathaway"',
        "CROX": '"Crocs, Inc."',
        "EWBC": '"East West Bancorp"',
        "OXY": '"Occidental Petroleum"',
        "DHI": '"D.R. Horton"',
        "TME": '"Tencent Music"',
        "GOOGL": '"Alphabet Inc."',
        "GOOG": '"Alphabet Inc."',
        "DAL": '"Delta Air Lines"',
        "LEN": '"Lennar Corp"',
        "BABA": '"Alibaba Group"',
    }

    for ticker in tickers:
        q_term = TICKER_QUERY_MAP.get(ticker, f'"{ticker}"')
        url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q={requests.utils.quote(q_term)}"
            f"&forms=SC%2013D,SC%2013D/A,SC%2013G,SC%2013G/A"
            f"&startdt={start_dt}&enddt={end_dt}"
        )
        try:
            resp = SESSION.get(url, headers=SEC_HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for h in hits:
                s = h.get("_source", {})
                adsh = s.get("adsh")
                if not adsh:
                    continue
                file_date = s.get("file_date", "")
                form = s.get("form", "")
                display_names = s.get("display_names", [])

                # Usually display_names[0] is subject company, display_names[1] is reporting person
                subject = display_names[0] if len(display_names) > 0 else ticker
                filer = display_names[1] if len(display_names) > 1 else "Institutional Whale"

                ciks = s.get("ciks", [])
                primary_cik = ciks[0] if ciks else ""
                adsh_nodash = adsh.replace("-", "")
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{primary_cik}/{adsh_nodash}/{adsh}-index.html"

                signals.append({
                    "filing_date": file_date,
                    "form_type": form,
                    "filer_name": filer,
                    "filer_cik": ciks[1] if len(ciks) > 1 else "",
                    "subject_name": subject,
                    "subject_ticker": ticker,
                    "accession_num": adsh,
                    "url": filing_url,
                    "ownership_pct": 0.0,
                    "is_tracked_guru": 0,
                    "tier": 0,
                })
            time.sleep(0.1)
        except Exception as e:
            print(f"  ⚠️ Error scanning ticker {ticker}: {e}")

    return signals


# ── Database Ingestion ────────────────────────────────────────────────────────
def save_13g_signals(db_path: str, signals: List[Dict]) -> int:
    """Save detected 13G/13D signals into SQLite database."""
    if not signals:
        return 0
    conn = sqlite3.connect(db_path)
    ensure_13g_table(conn)
    cur = conn.cursor()
    saved = 0

    for s in signals:
        try:
            cur.execute("""
            INSERT OR REPLACE INTO sec_13g_signals
            (filing_date, form_type, filer_name, filer_cik, subject_name,
             subject_ticker, accession_num, url, ownership_pct, is_tracked_guru, tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s["filing_date"], s["form_type"], s["filer_name"], s.get("filer_cik", ""),
                s["subject_name"], s.get("subject_ticker", ""), s["accession_num"],
                s["url"], s.get("ownership_pct", 0.0), s.get("is_tracked_guru", 0),
                s.get("tier", 0),
            ))
            saved += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    return saved


# ── Markdown Section Formatter ────────────────────────────────────────────────
def format_13g_section(signals: List[Dict], top_n: int = 10) -> str:
    """Render a structured Markdown section for SEC 13G/13D early warning radar."""
    if not signals:
        return ""

    lines = []
    L = lines.append
    L("## ⚡ 早期预警雷达：SEC 13G/13D 举牌扫描（突破 45 天 13F 滞后）")
    L("")
    L("> 💡 **核心逻辑：** 13F 申报有法定 45 天滞后，但依据 SEC 法规，**任何实体持股达到或增减超过 5% 时，必须在 10 天内披露 Schedule 13D/13G**。")
    L("> 本雷达对核心关注标的及顶尖机构进行高频穿透，比全市场 13F 申报提前数周捕捉主力建仓：")
    L("")
    L("| 申报日期 | 申报类型 | 投资机构 / 申报人 | 标的 / 标的代号 | 持股占比 | 预警级别 | 备案链接 |")
    L("|:---:|:---:|:---|:---|:---:|:---:|:---:|")

    # Sort signals by date descending
    sorted_signals = sorted(signals, key=lambda x: x["filing_date"], reverse=True)

    for s in sorted_signals[:top_n]:
        f_type = s["form_type"]
        is_guru = s.get("is_tracked_guru", 0) == 1
        level = "🚨 大师自身举牌" if is_guru else "🐳 机构5%+举牌"
        ticker_disp = f"**{s['subject_ticker']}**" if s.get("subject_ticker") else "—"
        subject_disp = (s.get("subject_name") or ticker_disp)[:28]
        filer_disp = s["filer_name"][:26]
        pct_val = s.get("ownership_pct", 0.0)
        pct_str = f"**{pct_val:.1f}%**" if pct_val > 0 else "—"
        link_str = f"[EDGAR 备案]({s['url']})" if s.get("url") else "—"

        L(f"| {s['filing_date']} | `{f_type}` | {filer_disp} | {ticker_disp} {subject_disp} | {pct_str} | {level} | {link_str} |")

    L("")
    return "\n".join(lines)


# ── Main Entrypoint ─────────────────────────────────────────────────────────
def run_13g_scanner(db_path: str, tickers: Optional[List[str]] = None, days_back: int = 180, verbose: bool = True) -> List[Dict]:
    """Run full two-track 13G/13D early warning scan and persist to DB."""
    if tickers is None:
        tickers = DEFAULT_CANDIDATE_TICKERS

    if verbose:
        print(f"🚀 [SEC 13G/13D Early Warning Scanner] Days back: {days_back}")
        print("📡 Track 1: Scanning SEC CIK submissions for tracked gurus...")
    guru_signals = scan_guru_13g_filings(TRACKED_GURUS_CIK, days_back=days_back)
    if verbose:
        print(f"  ✅ Found {len(guru_signals)} recent 13G/13D filings by tracked gurus")

    if verbose:
        print(f"📡 Track 2: Scanning SEC EFTS for {len(tickers)} candidate tickers...")
    ticker_signals = scan_ticker_13g_filings(tickers, days_back=days_back)
    if verbose:
        print(f"  ✅ Found {len(ticker_signals)} recent whale 13G/13D filings on candidate tickers")

    all_signals = guru_signals + ticker_signals
    # Deduplicate by accession_num
    seen_acc = set()
    dedup_signals = []
    for s in all_signals:
        acc = s.get("accession_num")
        if acc and acc not in seen_acc:
            seen_acc.add(acc)
            dedup_signals.append(s)

    if os.path.exists(db_path):
        saved = save_13g_signals(db_path, dedup_signals)
        if verbose:
            print(f"💾 Persisted {saved} 13G/13D signals to database: {db_path}")

    return dedup_signals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC 13G/13D Early Warning Beneficial Ownership Scanner")
    parser.add_argument("--db", type=str, default="", help="Path to investor_radar.db")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated candidate tickers to scan")
    parser.add_argument("--days", type=int, default=180, help="Days to look back (default: 180)")
    parser.add_argument("--top", type=int, default=15, help="Top N entries to show in Markdown section")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_file = args.db if args.db else os.path.join(project_root, "data", "investor_radar.db")

    custom_tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None
    signals = run_13g_scanner(db_file, tickers=custom_tickers, days_back=args.days, verbose=True)

    print("\n" + "=" * 70)
    print(format_13g_section(signals, top_n=args.top))
