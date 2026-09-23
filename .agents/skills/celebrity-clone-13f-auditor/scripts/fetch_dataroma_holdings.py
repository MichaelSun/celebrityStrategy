#!/usr/bin/env python3
"""
Celebrity Clone 13F Signal Extraction Script (Gemini / Antigravity Native)

Primary:   Dataroma (current + historical Q-1 filings)
Validate:  SEC EDGAR 13F XML (raw filings)
           yfinance (current prices & cost-window comparison)
Output:    Markdown opportunity reports with versioning and optional Obsidian sync.

Core Principles:
1. Opportunity-first: measure conviction (Weight Δ%, Position Multiplier ×) rather than market cap noise.
2. Cost window edge: compare current market price vs guru filing price (🟢 below guru cost = cloning edge).
3. Cross-institutional resonance: detect 🤝 buy-side consensus and ⚖️ divergence across gurus.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import pandas as pd
except ImportError:
    pd = None

# ── Network Headers & Session Setup ──────────────────────────────────────────
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SEC_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) research-agent@example.com"

HEADERS = {"User-Agent": BROWSER_UA}
SEC_HEADERS = {"User-Agent": SEC_UA}

def get_session():
    """Create a resilient requests session with automatic retry on 429/500/502/503/504."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

SESSION = get_session()

# ── Tracked Gurus Configuration ─────────────────────────────────────────────
# Note: Li Lu and Duan Yongping are the primary monitored investors with active SEC 13F CIKs.
TRACKED_GURUS = {
    "HC": {"name": "Li Lu - Himalaya Capital (李录)", "cik": "0001709323", "cik_active": True},
    "HH": {"name": "Duan Yongping - H&H International (段永平)", "cik": "0001759760", "cik_active": True},
}

GURU_SHORT = {
    "HC": "李录",
    "HH": "段永平",
}

SIGNAL_LABEL = {
    "NEW": "✨ 新买入 NEW",
    "INCREASED": "🔺 加仓 INCREASED",
    "REDUCED": "🔻 减仓 REDUCED",
    "SOLD": "❌ 清仓 SOLD",
    "NO_CHANGE": "🔵 持有 NO CHANGE",
}
SIGNAL_ORDER = ["NEW", "INCREASED", "NO_CHANGE", "REDUCED", "SOLD"]

DEFAULT_OBSIDIAN_DIR = "/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考/"

def resolve_obsidian_dir(custom_path=None):
    if custom_path and os.path.exists(custom_path):
        return custom_path
    candidates = [
        "/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考/",
        "/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/Investment/持仓参考/",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

# ── Static Sector Map for Theme Clustering ──────────────────────────────────
SECTOR_MAP = {
    "PDD": "中国电商", "BABA": "中国电商", "JD": "中国电商", "TME": "中国互联网",
    "GOOGL": "科技/AI", "GOOG": "科技/AI", "MSFT": "科技/AI", "NVDA": "半导体", "CRDO": "半导体",
    "AAPL": "科技硬件", "TSLA": "电动车", "PLTR": "AI软件", "SNOW": "云计算", "SNPS": "半导体EDA",
    "BRK.B": "综合控股", "OXY": "能源", "DIS": "媒体娱乐", "MCO": "金融/评级", "EWBC": "银行",
    "UNH": "医疗", "CRCL": "金融科技", "TEM": "医疗AI", "INOD": "AI数据", "CROX": "消费",
}

def sector_of(ticker):
    return SECTOR_MAP.get(ticker, "其他")

# ── Workspace & Path Discovery ──────────────────────────────────────────────
def find_project_root():
    """Discover project root by searching upwards for .git, .agents, or current directory."""
    current = os.path.abspath(os.path.dirname(__file__))
    while True:
        if os.path.exists(os.path.join(current, ".git")) or os.path.exists(os.path.join(current, ".agents")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.abspath(os.getcwd())

# ── Helper: Normalize Company Name ──────────────────────────────────────────
def norm_name(n):
    """Normalize company name for cross-source matching."""
    n = n.upper().strip()
    for s in [
        " INC", " CORP", " CORPORATION", " CO", " COMPANY", " LTD", " LLC", " LP", " L.P.", " N.V.",
        " PLC", " S.A.", " AG", " SE", " GROUP", " HOLDINGS", " HOLDING", " CL A", " CL C", " CL B",
        " - COMMON STOCK", " COM", " COMMON"
    ]:
        n = n.replace(s, "")
    n = re.sub(r'[.,\'\"\-]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

# ── Dataroma: Fetch Holdings & History ───────────────────────────────────────
def fetch_ticker_history(code, ticker):
    url = f"https://www.dataroma.com/m/hist/hist.php?f={code}&s={ticker}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        rows = re.findall(
            r"<tr>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td[^>]*>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>",
            resp.text
        )
        if len(rows) < 2:
            return None
        prev = rows[1]
        prev_shares = float(prev[1].replace(",", "")) if prev[1].strip() else 0
        prev_price = float(prev[5].replace("$", "").replace(",", "")) if prev[5].strip() else 0
        prev_pct = float(prev[2]) if prev[2].strip() else 0
        return {
            "period": prev[0].strip().replace("&nbsp;", " ").replace("&nbsp", " ").strip(),
            "shares": prev_shares,
            "value": prev_shares * prev_price,
            "price": prev_price,
            "pct": prev_pct
        }
    except Exception:
        return None

def detect_sold_position(code, ticker, company=""):
    """
    Probe a ticker's Dataroma history page to detect a 100% full exit (SOLD).
    Returns a SOLD holding dict if the current-quarter row shows 0 shares with a 'Sell' activity.
    """
    url = f"https://www.dataroma.com/m/hist/hist.php?f={code}&s={ticker}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        rows = re.findall(
            r"<tr>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td[^>]*>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>",
            resp.text
        )
        if len(rows) < 2:
            return None
        if not company:
            hm = re.search(r'<p id="p2">\s*Holding/activity history for.*?>\s*([^<(]+?)\s*(?:\([^)]+\))?\s*</a>', resp.text)
            if hm:
                company = hm.group(1).strip()
        cur = rows[0]
        cur_shares = float(cur[1].replace(",", "")) if cur[1].strip() else 0
        cur_act = cur[3].strip()
        prev = rows[1]
        prev_shares = float(prev[1].replace(",", "")) if prev[1].strip() else 0
        prev_price = float(prev[5].replace("$", "").replace(",", "")) if prev[5].strip() else 0
        prev_pct = float(prev[2]) if prev[2].strip() else 0
        prev_period = prev[0].strip().replace("&nbsp;", " ").replace("&nbsp", " ").strip()
        if cur_shares == 0 and "sell" in cur_act.lower():
            return {
                "ticker": ticker,
                "company": company,
                "name_norm": norm_name(company) if company else ticker,
                "pct": 0.0,
                "value": 0.0,
                "value_m": 0.0,
                "shares": 0,
                "price": 0.0,
                "signal": "SOLD",
                "activity": cur_act,
                "prev_shares": int(prev_shares),
                "prev_value": prev_shares * prev_price,
                "prev_value_m": round(prev_shares * prev_price / 1e6, 2),
                "prev_pct": prev_pct,
                "prev_price": round(prev_price, 2),
                "prev_period": prev_period,
                "shares_change": -int(prev_shares),
                "value_change_m": round(-prev_shares * prev_price / 1e6, 2),
                "pct_change": round(-prev_pct, 2),
            }
    except Exception:
        return None
    return None

def fetch_guru_holdings(code):
    """Fetch current quarter holdings from Dataroma for a given manager code."""
    url = f"https://www.dataroma.com/m/holdings.php?m={code}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 3000:
            return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

    period_match = re.search(r'Period:\s*<span>([^<]+)</span>', resp.text)
    period = period_match.group(1).replace("&nbsp;", " ").replace("&nbsp", " ").strip() if period_match else "Unknown"

    pdate_match = re.search(r'Portfolio date:\s*<span>([^<]+)</span>', resp.text)
    pdate = pdate_match.group(1).strip() if pdate_match else "Unknown"

    pval_match = re.search(r'Portfolio value:\s*<span>\$?([0-9,]+)</span>', resp.text)
    pval = float(pval_match.group(1).replace(",", "")) if pval_match else 0.0

    holdings = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.DOTALL):
        stock = re.search(r'/m/stock\.php\?sym=([A-Z.]+)"', row)
        if not stock:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 7:
            continue
        ticker = stock.group(1)
        company_match = re.search(r"<span>(.*?)</span>", row)
        company = company_match.group(1).strip() if company_match else ""
        try:
            pct = float(re.sub(r"<[^>]+>", "", tds[2]).strip())
            shares = float(re.sub(r"<[^>]+>", "", tds[4]).strip().replace(",", ""))
            value = float(re.sub(r"<[^>]+>", "", tds[6]).strip().replace("$", "").replace(",", ""))
        except (ValueError, IndexError):
            continue

        act_html = tds[3]
        act_text = re.sub(r"<[^>]+>", "", tds[3]).strip()
        at = act_text.lower()

        if 'class="green"' in act_html and "new" in at:
            signal = "NEW"
        elif 'class="green"' in act_html:
            signal = "INCREASED"
        elif 'class="red"' in act_html and "sold" in at:
            signal = "SOLD"
        elif 'class="red"' in act_html:
            signal = "REDUCED"
        elif "buy" in at or "new" in at:
            signal = "NEW"
        elif "sold" in at:
            signal = "SOLD"
        elif "reduce" in at:
            signal = "REDUCED"
        elif "add" in at:
            signal = "INCREASED"
        else:
            signal = "NO_CHANGE"

        holdings.append({
            "ticker": ticker,
            "company": company,
            "name_norm": norm_name(company),
            "pct": round(pct, 2),
            "value": value,
            "value_m": round(value / 1e6, 2),
            "shares": int(shares),
            "price": value / shares if shares > 0 else 0,
            "signal": signal,
            "activity": act_text,
        })

    holdings.sort(key=lambda x: x["pct"], reverse=True)

    # Q-1 historical data (parallel fetch)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fm = {ex.submit(fetch_ticker_history, code, h["ticker"]): h for h in holdings}
        for f in as_completed(fm):
            h = fm[f]
            p = f.result()
            if p and p["shares"] > 0:
                h.update(
                    prev_shares=int(p["shares"]),
                    prev_value=p["value"],
                    prev_value_m=round(p["value"] / 1e6, 2),
                    prev_pct=p["pct"],
                    prev_price=round(p["price"], 2),
                    prev_period=p["period"]
                )
            else:
                h.update(
                    prev_shares=0,
                    prev_value=0,
                    prev_value_m=0,
                    prev_pct=0,
                    prev_price=0,
                    prev_period="—"
                )
            h["shares_change"] = h["shares"] - h["prev_shares"]
            h["value_change_m"] = round(h["value_m"] - h["prev_value_m"], 2)
            h["pct_change"] = round(h["pct"] - h["prev_pct"], 2)
            h["weight_chg"] = round(h["pct"] - h["prev_pct"], 2)
            h["mult"] = round(h["pct"] / h["prev_pct"], 2) if h["prev_pct"] > 0 else (float("inf") if h["pct"] > 0 else 0.0)
            h["opp"] = opp_score(h)

    return {
        "period": period,
        "date": pdate,
        "portfolio_value": pval,
        "portfolio_value_m": round(pval / 1e6, 2),
        "num_positions": len(holdings),
        "holdings": holdings
    }

# ── SEC EDGAR 13F XML Fetcher ────────────────────────────────────────────────
def fetch_sec_13f(cik):
    """Fetch the latest 13F filing from SEC EDGAR and parse holdings."""
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = SESSION.get(url, headers=SEC_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])

        acc = None
        for i, f in enumerate(forms):
            if f == "13F-HR":
                acc = recent.get("accessionNumber", [])[i]
                break
        if not acc:
            return None

        acc_no_dash = acc.replace("-", "")
        cik_digits = str(int(cik))  # strip leading zeros for directory path
        base = f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{acc_no_dash}"
        filing_page = f"{base}/{acc}-index.html"
        r = SESSION.get(filing_page, headers=SEC_HEADERS, timeout=12)
        if r.status_code != 200:
            return None

        xml_files = re.findall(r'href="([^"]*(?:13fhciq|infotable)[^"]*\.xml)"', r.text, re.IGNORECASE)
        raw_xml = [f for f in xml_files if 'xslForm13F_X02' not in f]
        if raw_xml:
            xml_url = raw_xml[0].replace("&amp;", "&")
        elif xml_files:
            xml_url = xml_files[0].replace("&amp;", "&")
        else:
            xml_files = re.findall(r'href="([^"]*informationtable[^"]*\.xml)"', r.text, re.IGNORECASE)
            if not xml_files:
                return None
            xml_url = xml_files[0].replace("&amp;", "&")

        if xml_url.startswith("/"):
            xml_url = f"https://www.sec.gov{xml_url}"

        rx = SESSION.get(xml_url, headers=SEC_HEADERS, timeout=12)
        if rx.status_code != 200:
            return None

        # Parse with ElementTree or fallback regex
        try:
            root = ET.fromstring(rx.text)
            ns = {'ns1': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}
            tables = root.findall('.//ns1:infoTable', ns)
            holdings = []
            for tbl in tables:
                name_el = tbl.find('ns1:nameOfIssuer', ns)
                name = name_el.text if name_el is not None and name_el.text else ""
                cusip_el = tbl.find('ns1:cusip', ns)
                cusip = cusip_el.text if cusip_el is not None and cusip_el.text else ""
                val_el = tbl.find('ns1:value', ns)
                val_text = val_el.text if val_el is not None and val_el.text else "0"
                value_x1000 = int(val_text) if val_text and val_text.isdigit() else 0
                shares_el = tbl.find('ns1:shrsOrPrnAmt/ns1:sshPrnamt', ns)
                shares = int(shares_el.text) if shares_el is not None and shares_el.text and shares_el.text.isdigit() else 0
                putcall_el = tbl.find('ns1:putCall', ns)
                putcall = putcall_el.text if putcall_el is not None and putcall_el.text else ""
                holdings.append({
                    "name": name.strip(),
                    "name_norm": norm_name(name),
                    "cusip": cusip,
                    "value_x1000": value_x1000,
                    "value": value_x1000 * 1000,
                    "value_m": round(value_x1000 / 1000, 2),
                    "shares": shares,
                    "putCall": putcall,
                })
            return {"accession": acc, "holdings": holdings, "num_positions": len(holdings)}
        except ET.ParseError:
            tables = re.findall(r'<ns1:infoTable>(.*?)</ns1:infoTable>', rx.text, re.DOTALL)
            raw_holdings = []
            for tbl in tables:
                def xt(p):
                    m = re.search(p, tbl)
                    return m.group(1) if m else ""
                name = xt(r'<ns1:nameOfIssuer>([^<]+)')
                cusip = xt(r'<ns1:cusip>([^<]+)')
                val = xt(r'<ns1:value>([^<]+)')
                shr = xt(r'<ns1:sshPrnamt>([^<]+)')
                value_x1000 = int(val) if val.isdigit() else 0
                shares = int(shr) if shr.isdigit() else 0
                raw_holdings.append({
                    "name": name.strip(),
                    "name_norm": norm_name(name),
                    "cusip": cusip,
                    "value_x1000": value_x1000,
                    "value": value_x1000 * 1000,
                    "value_m": round(value_x1000 / 1000, 2),
                    "shares": shares,
                    "putCall": "",
                })
            return {"accession": acc, "holdings": raw_holdings, "num_positions": len(raw_holdings)}
    except Exception as e:
        return {"error": str(e)}

# ── yfinance Price & Cost-Window Check ───────────────────────────────────────
def fetch_yfinance_prices(tickers):
    """Fetch current prices for tickers via yfinance."""
    prices = {}
    if not tickers:
        return prices
    try:
        import yfinance as yf
        # Yahoo Finance expects '-' instead of '.' for share classes (e.g. BRK.B -> BRK-B)
        sym_map = {t: t.replace(".", "-") for t in tickers}
        inv_sym_map = {v: k for k, v in sym_map.items()}
        query_syms = list(sym_map.values())
        try:
            df = yf.download(query_syms, period="1d", progress=False, auto_adjust=False, threads=False)
            if df is not None and not df.empty and pd is not None:
                if isinstance(df.columns, pd.MultiIndex):
                    close = df["Close"]
                else:
                    close = df["Close"] if "Close" in df else df
                for q_sym in query_syms:
                    orig_ticker = inv_sym_map.get(q_sym, q_sym)
                    try:
                        series = close[q_sym] if isinstance(close, pd.DataFrame) and q_sym in close else close
                        val = series.dropna().iloc[-1] if hasattr(series, "dropna") and len(series.dropna()) else None
                        if val is not None and not (isinstance(val, float) and pd.isna(val)):
                            prices[orig_ticker] = round(float(val), 2)
                    except Exception:
                        pass
        except Exception:
            pass

        missing = [t for t in tickers if t not in prices]
        for ticker in missing:
            try:
                q_sym = sym_map.get(ticker, ticker)
                tk = yf.Ticker(q_sym)
                info = tk.info or {}
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                if price:
                    prices[ticker] = round(price, 2)
            except Exception:
                pass
    except ImportError:
        pass
    return prices

def cost_window(ticker, reported_price, yf_prices):
    """
    Cost-window note: compare current price to guru's reported filing price.
    Returns:
      🟢 现价$Y 比成本-X% -> current < reported (better entry price than guru)
      🟡 现价$Y 高成本+X% -> current > reported (chasing, caution)
      —   no price data
    """
    if ticker not in yf_prices or not reported_price:
        return "—"
    cur = yf_prices.get(ticker)
    diff = (cur - reported_price) / reported_price * 100
    if diff <= -5:
        return f"🟢 现价${cur} 比成本-{abs(diff):.0f}%"
    if diff >= 5:
        return f"🟡 现价${cur} 高成本+{diff:.0f}%"
    return f"≈ 现价${cur}"

def opp_score(h):
    """
    Opportunity intensity score (0-3):
    3 = NEW position (fresh conviction bet)
    2 = large increase (mult >= 2)
    1 = modest increase / held
    0 = reduced / sold (avoid / exit)
    """
    sig = h.get("signal")
    mult = h.get("mult", 0) or 0
    if sig == "NEW":
        return 3
    if sig == "INCREASED":
        return 2 if mult >= 2 else 1
    if sig == "NO_CHANGE":
        return 1
    if sig in ("REDUCED", "SOLD"):
        return 0
    return 1

# ── Cross-Validation ────────────────────────────────────────────────────────
def validate_holdings(dataroma_holdings, sec_holdings, yf_prices):
    """
    Cross-validate Dataroma against SEC 13F and yfinance.
    - issues: genuine anomalies worth ⚠️ (price moved >20% vs filing).
    - notes: informational ℹ️ (SEC share/value divergence due to reporting entities/ADR).
    """
    result = {}
    sec_lookup = {}
    if sec_holdings and "holdings" in sec_holdings:
        for s in sec_holdings["holdings"]:
            sec_lookup[s["name_norm"]] = s

    for h in dataroma_holdings:
        ticker = h["ticker"]
        issues, notes = [], []

        sec_match = sec_lookup.get(h["name_norm"])
        if not sec_match:
            for sn, sv in sec_lookup.items():
                if sn in h["name_norm"] or h["name_norm"] in sn:
                    sec_match = sv
                    break
        if sec_match:
            sec_val_m = sec_match["value_m"]
            if sec_val_m:
                diff_pct = abs(h["value_m"] - sec_val_m) / sec_val_m * 100
                if diff_pct > 5:
                    notes.append(f"SEC市值差{diff_pct:.0f}%（口径差异）")
            if sec_match["shares"] > 0 and h["shares"] > 0:
                shr_diff = abs(h["shares"] - sec_match["shares"]) / sec_match["shares"] * 100
                if shr_diff > 5:
                    notes.append(f"SEC股数差{shr_diff:.0f}%（口径差异）")
        else:
            notes.append("SEC该CIK无匹配持仓（可能由其他关联申报主体持有）")

        if ticker in yf_prices:
            yf_p = yf_prices[ticker]
            if h["price"] > 0:
                price_diff = abs(h["price"] - yf_p) / h["price"] * 100
                if price_diff > 20:
                    issues.append(f"现价${yf_p} vs 报告价${h['price']:.2f}")

        if issues or notes:
            result[ticker] = {"issues": issues, "notes": notes}

    return result

# ── Formatting Helpers ──────────────────────────────────────────────────────
def fmt_m(v): return f"${v:,.2f}M" if v else "$—"
def fmt_dm(v):
    if abs(v) < 0.01: return "—"
    return f"{'+' if v > 0 else ''}{v:,.2f}M"
def fmt_ds(v):
    if v == 0: return "—"
    return f"{'+' if v > 0 else ''}{v:,}"

# ── Markdown Report Generator ───────────────────────────────────────────────
def generate_markdown(all_data, sec_data, yf_prices, validation, active_guru_codes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lambda x: lines.append(x)

    L("# 📊 13F 名人持仓季度变动与机会审计报告")
    L("")
    L(f"**生成时间：** {now}")
    L(f"**数据来源：** [Dataroma](https://dataroma.com) 机构持仓 + [SEC EDGAR](https://sec.gov) 13F XML原始备案 + yfinance 现价")
    L("")
    L("---")
    L("")

    # Determine period label
    period_label = "本期 (Q) vs 上期 (Q-1)"
    for code in active_guru_codes:
        d = all_data.get(code)
        if d and "period" in d:
            pq = d.get("period", "")
            prev_q = ""
            for h in d.get("holdings", []):
                if h.get("prev_period") and h["prev_period"] != "—":
                    prev_q = h["prev_period"]
                    break
            if pq and prev_q:
                period_label = f"{pq} vs {prev_q}"
            elif pq:
                period_label = pq
            break

    L(f"> **📅 对比周期：{period_label}**".replace("&nbsp;", "").replace("&nbsp", ""))
    L("")

    # Data Freshness
    cutoff = ""
    for code in active_guru_codes:
        d = all_data.get(code)
        if d and d.get("date") and d["date"] != "Unknown":
            cutoff = d["date"]
            break
    fresh_line = "⚠️ 无法判定数据截止日"
    if cutoff:
        try:
            cut_dt = datetime.datetime.strptime(cutoff, "%d %b %Y")
            days = (datetime.datetime.now() - cut_dt).days
            stale = " 🔴 滞后较长" if days > 75 else (" 🟡 接近45天窗口" if days > 45 else " 🟢 较新")
            fresh_line = (f"📅 数据截止：{cutoff}（13F 季度末）｜ 距今天数：**{days} 天**{stale} "
                          f"｜ 13F 法定滞后约 45 天，当前价格/持仓可能已变化")
        except Exception:
            fresh_line = f"📅 数据截止：{cutoff}（13F 季度末）"
    L(f"> {fresh_line}")
    L("")
    L("---")
    L("")

    # Cross-guru overview table
    all_tickers = {}
    for code in active_guru_codes:
        data = all_data.get(code)
        if not data or "error" in data:
            continue
        for h in data["holdings"]:
            t = h["ticker"]
            if t not in all_tickers:
                all_tickers[t] = {"company": h["company"], "gurus": {}}
            sig_emoji = "✨" if h["signal"] == "NEW" else "🔺" if h["signal"] == "INCREASED" else \
                        "🔻" if h["signal"] == "REDUCED" else "❌" if h["signal"] == "SOLD" else "🔵"
            action_str = f"{sig_emoji} {h['activity']}" if h["activity"] else "🔵 持有"
            if h["signal"] in ("NEW", "INCREASED"):
                shares_str = f"{h['shares']:,}".rjust(10)
                val_str = f"${h['value_m']:.1f}M"
                detail = f"{action_str} {shares_str}股 ({val_str})"
            elif h["signal"] == "REDUCED":
                shares_str = f"{h['shares']:,}".rjust(10)
                val_str = f"${h['value_m']:.1f}M"
                detail = f"{action_str} → {shares_str}股 ({val_str})"
            else:
                detail = action_str

            vflags = validation.get(code, {}).get(t, {})
            if vflags.get("issues"):
                detail += " ⚠️"
            elif vflags.get("notes"):
                detail += " ℹ️"

            all_tickers[t]["gurus"][code] = detail

    def sort_key(item):
        t, v = item
        sigs = [g.get("signal", "") for code, g in
                [(c, next((x for x in (all_data.get(c, {})).get("holdings", []) if x["ticker"] == t), None))
                 for c in active_guru_codes] if g]
        priority = 1 if any(s in ("NEW", "INCREASED") for s in sigs) else 0
        return (priority, len(v["gurus"]))

    sorted_tickers = sorted(all_tickers.items(), key=sort_key, reverse=True)

    L("## 📋 全部持仓操作总览")
    L("")
    n_gurus = len([c for c in active_guru_codes if all_data.get(c) and "error" not in all_data.get(c)])
    total_positions = sum(d['num_positions'] for c, d in all_data.items() if c in active_guru_codes and d and 'error' not in d)
    L(f"**{period_label}**，追踪 {n_gurus} 家机构共 **{total_positions}** 个持仓标的。".replace("&nbsp;", "").replace("&nbsp", ""))
    L("")

    header_cols = ["标的"] + [GURU_SHORT.get(c, c) for c in active_guru_codes]
    L("| " + " | ".join(header_cols) + " |")
    L("|" + "|".join([":---"] + [":---" for _ in active_guru_codes]) + "|")

    for t, v in sorted_tickers:
        row = [f"**{t}** {v['company'][:20]}"]
        for code in active_guru_codes:
            row.append(v["gurus"].get(code, "—"))
        L("| " + " | ".join(row) + " |")

    L("")
    L("### 🎯 本季最强机会信号速览")
    L("")
    all_holdings = [x for c, d in all_data.items() if c in active_guru_codes and d and "error" not in d for x in d["holdings"]]
    new_pos = sorted([x for x in all_holdings if x["signal"] == "NEW"], key=lambda x: x["pct"], reverse=True)
    if new_pos:
        L(f"- ✨ **新买入（按权重）**：" + "、".join(f"{x['ticker']}({x['pct']:.1f}%)" for x in new_pos))

    # Convergence (>=2 gurus buying/adding)
    conv = {}
    for c, d in all_data.items():
        if c not in active_guru_codes or not d or "error" in d:
            continue
        for x in d["holdings"]:
            if x["signal"] in ("NEW", "INCREASED"):
                conv.setdefault(x["ticker"], []).append((c, x["signal"]))
    conv = {t: v for t, v in conv.items() if len(v) >= 2}
    if conv:
        parts = []
        for t, v in conv.items():
            seg = "/".join(f"{GURU_SHORT.get(c, c)}{'+' if sig=='NEW' else '↑'}" for c, sig in v)
            parts.append(f"{t}({seg})")
        L(f"- 🤝 **共振买入（≥2人同向加/新买）**：" + "、".join(parts))

    # Highest conviction multiplier (mult >= 2)
    big = sorted([x for c, d in all_data.items() if c in active_guru_codes and d and "error" not in d
                  for x in d["holdings"]
                  if x["signal"] == "INCREASED" and x["mult"] != float("inf") and x["mult"] >= 2],
                 key=lambda x: x["mult"], reverse=True)
    if big:
        parts = []
        for x in big:
            c = next((cc for cc in active_guru_codes
                      if any(hh["ticker"] == x["ticker"] and hh["signal"] == "INCREASED"
                             for hh in all_data[cc]["holdings"])), "?")
            parts.append(f"{x['ticker']}({x['mult']:.1f}×, {GURU_SHORT.get(c, c)})")
        L(f"- 💪 **最大决心加仓（仓位倍数≥2×）**：" + "、".join(parts))
    L("")
    L("---")
    L("")

    # Per-Guru Breakdown
    for code in active_guru_codes:
        info = TRACKED_GURUS[code]
        name = info["name"]
        cik_active = info["cik_active"]
        data = all_data.get(code)
        if not data or "error" in data:
            L(f"## ❌ {name}")
            L("")
            L(f"Error: {data.get('error', 'No data')}" if data else "Error: No data")
            L("")
            continue

        h = data["holdings"]
        q_label = data.get("period", "Q")
        L(f"## {name}")
        L("")
        L("| 指标 | 数值 |")
        L("|---|---|")
        L(f"| 组合总值 | ${data['portfolio_value_m']:,.2f}M |")
        L(f"| 持仓数量 | {data['num_positions']} |")
        L(f"| 报告期 | {q_label} ({data['date']}) |")

        sec_src = sec_data.get(code)
        if sec_src:
            if "error" in sec_src:
                L(f"| SEC交叉验证 | ⚠️ 解析错误: {sec_src['error']} |")
            if "holdings" in sec_src:
                match_count = 0
                for hh in h:
                    for s in sec_src["holdings"]:
                        if s["name_norm"] == hh["name_norm"] or s["name_norm"] in hh["name_norm"] or hh["name_norm"] in s["name_norm"]:
                            match_count += 1
                            break
                L(f"| SEC 13F交叉验证 | ✅ {match_count}/{len(h)} 匹配 (Accession: {sec_src.get('accession','')[:25]}...) |")
        elif cik_active:
            L("| SEC 13F验证 | ❌ 未找到最新13F-HR备案 |")
        L("")

        for sig in SIGNAL_ORDER:
            items = [x for x in h if x["signal"] == sig]
            if not items:
                continue

            if sig == "NO_CHANGE":
                L(f"### 🔵 持有 NO CHANGE ({len(items)} 只)")
                L("")
                names = "、".join(f"{x['ticker']}({x['pct']:.1f}%)" for x in items)
                L(f"🔵 持有不变：{names}")
                L("")
                continue

            L(f"### {SIGNAL_LABEL.get(sig, sig)} ({len(items)} 只)")
            L("")
            L("| 代码 | 公司 | 占比 | 权重Δ% | 仓位倍数 | 持股数 | 持股变化 | 操作 | 机会 | 成本窗口 |")
            L("|:---|:---|:---:|:---:|:---:|:------:|:--------:|:----:|:----:|:----:|")

            for x in items:
                ticker = x["ticker"]
                mult_val = x.get("mult", 0) or 0
                mult_str = "∞" if mult_val == float("inf") else f"{mult_val:.2f}×"
                if x.get("signal") == "SOLD":
                    opp_str = "低/规避"
                    activity_str = f"{x['activity']} ⏳45天前已卖"
                else:
                    opp_str = {3: "🔥高", 2: "中高", 1: "中", 0: "低/规避"}.get(x.get("opp", 1), "中")
                    activity_str = x["activity"]
                cw_str = cost_window(ticker, x.get("price", 0), yf_prices)

                L(f"| **{ticker}** | {x['company'][:28]} | {x['pct']:.2f}% | "
                  f"{x.get('weight_chg', 0):+.2f}% | {mult_str} | "
                  f"{x['shares']:,} | {fmt_ds(x['shares_change'])} | {activity_str} | {opp_str} | {cw_str} |")
            L("")

        total_val = sum(x["value_m"] for x in h)
        total_prev = sum(x["prev_value_m"] for x in h)
        new_v = sum(x["value_m"] for x in h if x["signal"] == "NEW")
        inc_v = sum(x["value_m"] for x in h if x["signal"] == "INCREASED")
        dec_v = sum(x["value_m"] for x in h if x["signal"] == "REDUCED")

        L("#### 📊 季度仓位变动汇总")
        L("")
        L(f"| 指标 | 本期 ({q_label}) | 前季 (Q-1) | 净变化 |")
        L("|---|---|---|---|")
        L(f"| 组合总值 | ${total_val:,.2f}M | ${total_prev:,.2f}M | {fmt_dm(total_val - total_prev)} |")
        L(f"| ✨ 新买入 | ${new_v:,.2f}M | $— | — |")
        L(f"| 🔺 加仓 | ${inc_v:,.2f}M | — | — |")
        L(f"| 🔻 减仓 | ${dec_v:,.2f}M | — | — |")
        L("")
        L("---")
        L("")

    # SEC Cross-validation summary
    L("## 🔍 数据源交叉验证汇总")
    L("")
    L("| 机构 | Dataroma | SEC EDGAR 13F | yfinance现价 | 验证结论 |")
    L("|---|---|---|---|---|")
    for code in active_guru_codes:
        info = TRACKED_GURUS[code]
        data = all_data.get(code)
        sec_s = sec_data.get(code)
        yf_count = sum(1 for h in (data.get("holdings", []) if data else []) if h["ticker"] in yf_prices)
        val = validation.get(code, {})
        issue_count = sum(len(v.get("issues", [])) for v in val.values())
        note_count = sum(len(v.get("notes", [])) for v in val.values())
        n_held = len(data.get("holdings", [])) if data else 0

        d_ok = f"✅ {n_held} 只标的"
        if sec_s and "holdings" in sec_s:
            s_ok = f"✅ {sec_s['num_positions']} 笔记录"
        elif sec_s and "error" in sec_s:
            s_ok = f"❌ 错误: {sec_s['error'][:25]}"
        elif info["cik_active"]:
            s_ok = "❌ 未找到 13F 备案"
        else:
            s_ok = "⚠️ CIK无近期13F"

        y_ok = f"✅ {yf_count}/{n_held} 价格已获取" if yf_count else "⚠️ 无现价数据"

        if issue_count:
            result = f"⚠️ {issue_count} 处价格大幅异动"
        elif note_count:
            result = f"ℹ️ {note_count} 处口径差异（正常）"
        elif sec_s and "holdings" in sec_s:
            result = "✅ 交叉核验一致"
        else:
            result = "✅ Dataroma 单源核验"

        L(f"| **{info['name'][:25]}** | {d_ok} | {s_ok} | {y_ok} | {result} |")

    L("")
    L("## 🔗 跨机构交叉信号（Convergence & Divergence）")
    L("")

    tk_holders = {}
    for code in active_guru_codes:
        info = TRACKED_GURUS[code]
        data = all_data.get(code)
        if not data or "error" in data:
            continue
        for x in data["holdings"]:
            t = x["ticker"]
            if t not in tk_holders:
                tk_holders[t] = {"company": x["company"], "holders": []}
            tk_holders[t]["holders"].append({
                "guru": info["name"],
                "pct": x["pct"],
                "signal": x["signal"],
                "vflags": validation.get(code, {}).get(t, {})
            })

    buy_side = ("NEW", "INCREASED")
    sell_side = ("REDUCED", "SOLD")
    sig_cn = {"NEW": "新买", "INCREASED": "加仓", "NO_CHANGE": "持有", "REDUCED": "减仓", "SOLD": "清仓"}

    resonance, divergence = [], []
    for t, v in tk_holders.items():
        if len(v["holders"]) < 2:
            continue
        sigs = [h["signal"] for h in v["holders"]]
        if all(s in buy_side for s in sigs):
            resonance.append((t, v))
        elif any(s in sell_side for s in sigs):
            divergence.append((t, v))

    if resonance:
        L("### 🤝 同向共振（多人同方向加仓/新买入）")
        L("")
        L("| 代码 | 公司 | 持有人数 | 详细动作 |")
        L("|:---|:---|:---:|:---|")
        for t, v in sorted(resonance, key=lambda kv: len(kv[1]["holders"]), reverse=True):
            details = "; ".join([
                f"{h['guru'][:18]}({h['pct']:.1f}%, {sig_cn.get(h['signal'], h['signal'])})" +
                (" ⚠️" if h['vflags'].get('issues') else (" ℹ️" if h['vflags'].get('notes') else ""))
                for h in v["holders"]
            ])
            L(f"| **{t}** | {v['company'][:25]} | {len(v['holders'])} | {details} |")
        L("")

    if divergence:
        L("### ⚖️ 分歧信号（一人看好加仓/持有，一人减仓/清仓）")
        L("")
        L("| 代码 | 公司 | 持有人数 | 详细动作 |")
        L("|:---|:---|:---:|:---|")
        for t, v in sorted(divergence, key=lambda kv: len(kv[1]["holders"]), reverse=True):
            details = "; ".join([
                f"{h['guru'][:18]}({h['pct']:.1f}%, {sig_cn.get(h['signal'], h['signal'])})" +
                (" ⚠️" if h['vflags'].get('issues') else (" ℹ️" if h['vflags'].get('notes') else ""))
                for h in v["holders"]
            ])
            L(f"| **{t}** | {v['company'][:25]} | {len(v['holders'])} | {details} |")
        L("")

    # Sector clustering
    L("### 🏭 行业主题聚类（跨机构布局）")
    L("")
    sector_map = {}
    for t, v in tk_holders.items():
        sec = sector_of(t)
        sector_map.setdefault(sec, []).append((t, v))
    for sec in sorted(sector_map, key=lambda s: -len(sector_map[s])):
        items = sector_map[sec]
        seg = "、".join(
            f"{t}[" + "/".join(
                f"{GURU_SHORT.get(h['guru'][:2], h['guru'][:4])}:{sig_cn.get(h['signal'], h['signal'])}"
                for h in v["holders"]
            ) + "]"
            for t, v in items
        )
        L(f"- **{sec}**：{seg}")
    L("")

    L("---")
    L("### ℹ️ 报告阅读与审计说明")
    L("")
    L("- **核心逻辑：** 聚焦聪明钱在自身组合内的下注决心（权重Δ%、倍数×），剔除个股市值等噪音指标。")
    L("- **成本窗口：** 🟢 标表示现价已低于大佬季度申报成本，通常具有克隆建仓的安全边际优势；🟡 标提示已有一定涨幅。")
    L("- **验证标记 ⚠️：** 仅当 yfinance 现价比申报价大幅波动超过 20% 时触发价格警示。")
    L("- **信息标记 ℹ️（口径差异）：** SEC 13F 股数/市值与 Dataroma 偏差通常源于申报实体拆分、ADR 与普通股折算或披露时点，属于正常口径差异。")
    L("- **免责声明：** 13F 数据法定滞后 45 天，仅用于历史行为学习与策略研究，不构成任何投资建议。")
    L("")

    return "\n".join(lines)

# ── State Management ────────────────────────────────────────────────────────
def load_state(state_file):
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    # Built-in seed default fallback
    return {
        "HC": ["AAPL", "BRK.B", "CROX", "EWBC", "GOOG", "GOOGL", "MCO", "PDD", "TME"],
        "HH": ["AAPL", "BABA", "BRK.B", "CRCL", "CRDO", "DIS", "GOOG", "INOD", "MSFT", "NVDA", "OXY", "PDD", "PLTR", "SNOW", "SNPS", "TEM", "TSLA", "UNH"]
    }

def save_state(state, state_file):
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

# ── Main Entrypoint ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="13F Celebrity Investor Portfolio Auditor (Gemini Native)")
    parser.add_argument("--gurus", type=str, default="", help="Comma-separated guru codes to audit (e.g. HC,HH). Default: all")
    parser.add_argument("--output-dir", type=str, default="", help="Directory to save generated markdown reports")
    parser.add_argument("--state-file", type=str, default="", help="Path to persistent guru tickers state JSON")
    parser.add_argument("--sync-obsidian", action="store_true", help="Sync latest report to Obsidian directory")
    parser.add_argument("--obsidian-dir", type=str, default=DEFAULT_OBSIDIAN_DIR, help="Obsidian target folder")
    parser.add_argument("--skip-sec", action="store_true", help="Skip SEC EDGAR 13F XML cross-validation")
    parser.add_argument("--skip-price", action="store_true", help="Skip yfinance current price check")
    parser.add_argument("--export-json", action="store_true", help="Also export raw audit data as JSON")
    args = parser.parse_args()

    project_root = find_project_root()
    out_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.join(project_root, "reports")
    os.makedirs(out_dir, exist_ok=True)

    state_file = os.path.abspath(args.state_file) if args.state_file else os.path.join(project_root, "data", ".guru_tickers_state.json")

    active_codes = [c.strip() for c in args.gurus.split(",") if c.strip() in TRACKED_GURUS] if args.gurus else list(TRACKED_GURUS.keys())

    all_data = {}
    sec_data = {}
    yf_prices = {}
    validation = {}

    print(f"🚀 [Gemini 13F Auditor] Running for {len(active_codes)} guru(s): {', '.join(active_codes)}")
    print(f"📁 Reports Directory: {out_dir}")
    print(f"💾 State Watchlist: {state_file}")

    # 1. Fetch Dataroma holdings & detect SOLD
    print(f"\n📡 Step 1: Fetching Dataroma holdings & historical data...")
    state = load_state(state_file)
    for code in active_codes:
        data = fetch_guru_holdings(code)
        all_data[code] = data
        if "error" not in data:
            print(f"  ✅ {TRACKED_GURUS[code]['name']}: {data['num_positions']} active positions")
            prev_tickers = set(state.get(code, []))
            cur_tickers = {h["ticker"] for h in data["holdings"]}
            missing = prev_tickers - cur_tickers
            sold = []
            for ticker in missing:
                det = detect_sold_position(code, ticker)
                if det:
                    sold.append(det)
                    print(f"  ❌ {GURU_SHORT.get(code, code)}: Detected SOLD position: {ticker} (was {det['prev_shares']:,} shares in Q-1)")
            if sold:
                data["holdings"].extend(sold)
                data["holdings"].sort(key=lambda x: x["pct"], reverse=True)
                data["num_positions"] += len(sold)
            state[code] = sorted(cur_tickers | {s["ticker"] for s in sold})
        else:
            print(f"  ❌ {GURU_SHORT.get(code, code)}: Error fetching holdings ({data['error']})")
    save_state(state, state_file)

    # 2. Fetch SEC EDGAR 13F XML
    if not args.skip_sec:
        print(f"\n📡 Step 2: Fetching SEC EDGAR 13F XML filings for cross-validation...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            fm = {}
            for code in active_codes:
                info = TRACKED_GURUS[code]
                if info["cik_active"]:
                    fm[ex.submit(fetch_sec_13f, info["cik"])] = code
            for f in as_completed(fm):
                code = fm[f]
                sec = f.result()
                sec_data[code] = sec
                if sec and "error" not in sec and "holdings" in sec:
                    print(f"  ✅ {GURU_SHORT.get(code, code)}: {sec['num_positions']} positions from SEC EDGAR")
                elif sec and "error" in sec:
                    print(f"  ⚠️ {GURU_SHORT.get(code, code)}: SEC - {sec['error'][:60]}")
                else:
                    print(f"  ⚠️ {GURU_SHORT.get(code, code)}: No SEC 13F found")
    else:
        print("\n⏩ Step 2: SEC validation skipped via --skip-sec")

    # 3. Fetch yfinance prices
    if not args.skip_price:
        all_tickers = set()
        for code in active_codes:
            data = all_data.get(code)
            if data and "holdings" in data:
                for h in data["holdings"]:
                    all_tickers.add(h["ticker"])
        print(f"\n📡 Step 3: Fetching market prices for {len(all_tickers)} tickers...")
        yf_prices = fetch_yfinance_prices(list(all_tickers))
        print(f"  ✅ Fetched {len(yf_prices)} current ticker quotes")
    else:
        print("\n⏩ Step 3: yfinance price check skipped via --skip-price")

    # 4. Cross-Validation
    print(f"\n🔍 Step 4: Cross-validating filings and calculating cost windows...")
    for code in active_codes:
        data = all_data.get(code)
        if data and "holdings" in data:
            validation[code] = validate_holdings(data["holdings"], sec_data.get(code), yf_prices)
            val = validation[code]
            issue_count = sum(len(v.get("issues", [])) for v in val.values())
            note_count = sum(len(v.get("notes", [])) for v in val.values())
            if issue_count:
                print(f"  ⚠️ {GURU_SHORT.get(code, code)}: {issue_count} price anomalies (>20% drift)")
            elif note_count:
                print(f"  ℹ️ {GURU_SHORT.get(code, code)}: {note_count} reporting standard discrepancies (normal)")
            else:
                print(f"  ✅ {GURU_SHORT.get(code, code)}: Clean validation")

    # 5. Generate Markdown Report
    print(f"\n📝 Step 5: Rendering Markdown opportunity report...")
    md = generate_markdown(all_data, sec_data, yf_prices, validation, active_codes)

    yyyymmdd = datetime.datetime.now().strftime("%Y%m%d")
    mmddyyyy = datetime.datetime.now().strftime("%m-%d-%Y")

    quarter = "Q"
    for code in active_codes:
        d = all_data.get(code)
        if d and d.get("period"):
            qm = re.search(r"(Q[1-4])", d["period"])
            if qm:
                quarter = qm.group(1)
                break

    # Latest snapshot name: celebrity_clone_mm-dd-yyyy_季度_Vn.md
    snap_prefix = f"celebrity_clone_{mmddyyyy}_{quarter}_V"
    existing_snap = [f for f in os.listdir(out_dir) if f.startswith(snap_prefix) and f.endswith(".md")]
    max_sv = 0
    for f in existing_snap:
        m = re.search(rf"{re.escape(snap_prefix)}(\d+)\.md$", f)
        if m:
            max_sv = max(max_sv, int(m.group(1)))
    snap_version = max_sv + 1
    latest_name = f"{snap_prefix}{snap_version}.md"

    # Timestamped archive copy
    archive_prefix = f"celebrity_clone策略对比_{yyyymmdd}_V"
    existing = [f for f in os.listdir(out_dir) if f.startswith(archive_prefix) and f.endswith(".md")]
    max_v = 0
    for f in existing:
        m = re.search(rf"{re.escape(archive_prefix)}(\d+)\.md$", f)
        if m:
            max_v = max(max_v, int(m.group(1)))
    version = max_v + 1
    archive_name = f"{archive_prefix}{version}.md"

    archive_path = os.path.join(out_dir, archive_name)
    latest_path = os.path.join(out_dir, latest_name)

    for p in [archive_path, latest_path]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)

    print(f"  ✅ Report saved: {latest_path}")
    print(f"  ✅ Archive saved: {archive_path}")

    if args.export_json:
        json_path = os.path.join(out_dir, f"celebrity_clone_{mmddyyyy}_{quarter}_V{snap_version}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.datetime.now().isoformat(),
                "period": quarter,
                "all_data": all_data,
                "sec_data": sec_data,
                "yf_prices": yf_prices,
                "validation": validation
            }, f, indent=2)
        print(f"  ✅ JSON exported: {json_path}")

    # 6. Obsidian Sync (Immutable rule: ONLY WRITE/OVERWRITE, NEVER DELETE)
    if args.sync_obsidian:
        print(f"\n🔄 Step 6: Syncing to Obsidian...")
        obsidian_dir = resolve_obsidian_dir(args.obsidian_dir)
        try:
            os.makedirs(obsidian_dir, exist_ok=True)
            target_latest = os.path.join(obsidian_dir, latest_name)
            target_archive = os.path.join(obsidian_dir, archive_name)
            shutil.copy2(latest_path, target_latest)
            shutil.copy2(archive_path, target_archive)
            print(f"  ✅ Synced to Obsidian (Overwrite-safe, zero deletions):")
            print(f"     -> {target_latest}")
            print(f"     -> {target_archive}")
        except Exception as e:
            print(f"  ⚠️ Obsidian sync notice: {e} (Check iCloud Drive permissions)")

    print("\n🎉 13F Signal Extraction Completed Successfully!")

if __name__ == "__main__":
    main()
