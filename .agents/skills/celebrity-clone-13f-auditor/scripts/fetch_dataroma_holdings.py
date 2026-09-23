#!/usr/bin/env python3
"""
Celebrity Clone 13F Signal Extraction & Value Radar Script (Gemini Native)
Tiered Guru Universe (Tier 1 / Tier 2 / Tier 3) + SQLite Time-Series + CFO-Check Pipeline.

Core Principles:
1. Conviction First: Weight Δ%, Position Multiplier, Multi-Quarter Building Accumulation.
2. Cost Window: Market price vs guru filing cost (🟢 Clone Edge / 🟡 Caution Chasing).
3. Institutional Consensus: Tier 1 + Tier 2 consensus resonance.
4. CFO-Check Bridge: Seamlessly feed Top conviction candidates into cfo-check for forensic audit.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import subprocess
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

# ── Tiered Guru Universe Configuration ──────────────────────────────────────
TRACKED_GURUS = {
    # ── Tier 1: 华人宗师与价值灯塔 (Core Pillars) ──
    "HC": {"name": "Li Lu - Himalaya Capital (李录)", "short": "李录", "tier": 1, "cik": "0001709323", "cik_active": True},
    "HH": {"name": "Duan Yongping - H&H International (段永平)", "short": "段永平", "tier": 1, "cik": "0001759760", "cik_active": True},
    "BRK": {"name": "Warren Buffett - Berkshire Hathaway (巴菲特)", "short": "巴菲特", "tier": 1, "cik": "0001067983", "cik_active": True},

    # ── Tier 2: 芒格门徒与深度复合大师 (Compounders & Deep Value) ──
    "PI": {"name": "Mohnish Pabrai - Pabrai Investments (帕布莱)", "short": "帕布莱", "tier": 2, "cik": "", "cik_active": False},
    "aq": {"name": "Guy Spier - Aquamarine Capital (盖伊·斯皮尔)", "short": "斯皮尔", "tier": 2, "cik": "", "cik_active": False},
    "SE": {"name": "Mason Hawkins - Southeastern (梅森·霍金斯)", "short": "霍金斯", "tier": 2, "cik": "0000720875", "cik_active": True},
    "FS": {"name": "Terry Smith - Fundsmith (特里·史密斯)", "short": "史密斯", "tier": 2, "cik": "", "cik_active": False},
    "MKL": {"name": "Thomas Gayner - Markel Group (汤姆·盖纳)", "short": "盖纳", "tier": 2, "cik": "0001096343", "cik_active": True},

    # ── Tier 3: 宏观逆向与特种机会 (Special Macro & Catalysts) ──
    "psc": {"name": "Bill Ackman - Pershing Square (阿克曼)", "short": "阿克曼", "tier": 3, "cik": "", "cik_active": False},
    "AM": {"name": "David Tepper - Appaloosa (泰珀)", "short": "泰珀", "tier": 3, "cik": "", "cik_active": False},
    "oc": {"name": "Howard Marks - Oaktree Capital (马克斯)", "short": "马克斯", "tier": 3, "cik": "", "cik_active": False},
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
    "BRK.B": "综合控股", "BRK.A": "综合控股", "OXY": "能源", "DIS": "媒体娱乐", "MCO": "金融/评级",
    "EWBC": "银行", "UNH": "医疗", "CRCL": "金融科技", "TEM": "医疗AI", "INOD": "AI数据", "CROX": "消费",
    "KO": "必选消费", "AXP": "金融/支付", "CVX": "能源", "KHC": "必选消费", "MCO": "金融评级",
    "BAC": "商业银行", "AMZN": "电商/云计算", "CNX": "能源", "MAT": "消费/玩具", "RYN": "林木资源",
    "HCC": "特种煤炭", "RIG": "深水钻井", "AMR": "冶金煤炭",
}

def sector_of(ticker):
    return SECTOR_MAP.get(ticker, "其他")

def find_project_root():
    current = os.path.abspath(os.path.dirname(__file__))
    while True:
        if os.path.exists(os.path.join(current, ".git")) or os.path.exists(os.path.join(current, ".agents")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.abspath(os.getcwd())

def norm_name(n):
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

# ── Dataroma Fetchers ───────────────────────────────────────────────────────
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
    url = f"https://www.dataroma.com/m/holdings.php?m={code}"
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 1000:
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
    if not cik:
        return None
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
        cik_digits = str(int(cik))
        base = f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{acc_no_dash}"
        filing_page = f"{base}/{acc}-index.html"
        r = SESSION.get(filing_page, headers=SEC_HEADERS, timeout=12)
        if r.status_code != 200:
            return None

        xml_files = re.findall(r'href="([^"]*\.xml)"', r.text, re.IGNORECASE)
        raw_xml = [f for f in xml_files if 'xslform' not in f.lower() and 'primary_doc' not in f.lower()]
        if not raw_xml:
            return None
        xml_url = raw_xml[0].replace("&amp;", "&")
        if xml_url.startswith("/"):
            xml_url = f"https://www.sec.gov{xml_url}"

        rx = SESSION.get(xml_url, headers=SEC_HEADERS, timeout=12)
        if rx.status_code != 200:
            return None

        def extract_child(elem, tag_name):
            for child in elem:
                if child.tag.endswith(tag_name):
                    return child.text or ""
            return ""

        holdings = []
        try:
            root = ET.fromstring(rx.text)
            tables = [e for e in root.iter() if e.tag.endswith("infoTable")]
            for tbl in tables:
                name = extract_child(tbl, "nameOfIssuer")
                cusip = extract_child(tbl, "cusip")
                val_text = extract_child(tbl, "value")
                value_x1000 = int(val_text) if val_text.isdigit() else 0
                shares_text = ""
                for child in tbl.iter():
                    if child.tag.endswith("sshPrnamt"):
                        shares_text = child.text or ""
                        break
                shares = int(shares_text) if shares_text.isdigit() else 0
                putcall = extract_child(tbl, "putCall")
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
        except Exception:
            return None
    except Exception as e:
        return {"error": str(e)}

# ── yfinance Price & Cost-Window Check ───────────────────────────────────────
def fetch_yfinance_prices(tickers):
    prices = {}
    if not tickers:
        return prices
    try:
        import yfinance as yf
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
    if ticker not in yf_prices or not reported_price:
        return "—"
    cur = yf_prices.get(ticker)
    diff = (cur - reported_price) / reported_price * 100
    if diff <= -5:
        return f"🟢 现价${cur} 比成本-{abs(diff):.0f}%"
    if diff >= 5:
        return f"🟡 现价${cur} 高成本+{diff:.0f}%"
    return f"≈ 现价${cur}"

def validate_holdings(dataroma_holdings, sec_holdings, yf_prices):
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
        elif sec_holdings:
            notes.append("SEC该CIK无直接匹配（或属独立子实体）")

        if ticker in yf_prices:
            yf_p = yf_prices[ticker]
            if h["price"] > 0:
                price_diff = abs(h["price"] - yf_p) / h["price"] * 100
                if price_diff > 20:
                    issues.append(f"现价${yf_p} vs 报告价${h['price']:.2f}")

        if issues or notes:
            result[ticker] = {"issues": issues, "notes": notes}

    return result

def fmt_m(v): return f"${v:,.2f}M" if v else "$—"
def fmt_dm(v):
    if abs(v) < 0.01: return "—"
    return f"{'+' if v > 0 else ''}{v:,.2f}M"
def fmt_ds(v):
    if v == 0: return "—"
    return f"{'+' if v > 0 else ''}{v:,}"

# ── SQLite Time-Series Ingestion ────────────────────────────────────────────
def record_to_sqlite(db_path, quarter, all_data):
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for code, data in all_data.items():
            if not data or "holdings" not in data:
                continue
            for h in data["holdings"]:
                pct_chg = h.get("pct_change", 0.0)
                shares_held = h.get("shares", 0)
                weight = h.get("pct", 0.0)
                price = h.get("price", 0.0)
                cur.execute("""
                INSERT INTO portfolio_history (quarter, guru_code, ticker, company_name, activity, shares_change, portfolio_pct_change, shares_held, portfolio_weight, reported_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (quarter, code, h["ticker"], h["company"], h["activity"], str(h.get("shares_change", 0)), pct_chg, shares_held, weight, price))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ── Markdown Report Generator ───────────────────────────────────────────────
def generate_markdown(all_data, sec_data, yf_prices, validation, active_guru_codes, db_path=""):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lambda x: lines.append(x)

    L("# 📊 价值投资机构季度 13F 变动审计与机会雷达")
    L("")
    L(f"**审计生成时间：** {now}  ")
    L(f"**数据源支持：** Dataroma 机构持仓 + SEC EDGAR 13F-HR XML 官方备案 + yfinance 现价")
    L(f"**监控大师圈层：** {len(active_guru_codes)} 位顶级价值投资人")
    L("")
    L("---")
    L("")

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

    # 1. Cross-Guru Matrix
    all_tickers = {}
    for code in active_guru_codes:
        data = all_data.get(code)
        if not data or "error" in data:
            continue
        short_name = TRACKED_GURUS[code]["short"]
        for h in data["holdings"]:
            t = h["ticker"]
            if t not in all_tickers:
                all_tickers[t] = {"company": h["company"], "gurus": {}, "signals": {}}
            sig_emoji = "✨" if h["signal"] == "NEW" else "🔺" if h["signal"] == "INCREASED" else \
                        "🔻" if h["signal"] == "REDUCED" else "❌" if h["signal"] == "SOLD" else "🔵"
            action_str = f"{sig_emoji} {h['activity']}" if h["activity"] else "🔵 持有"
            all_tickers[t]["gurus"][code] = action_str
            all_tickers[t]["signals"][code] = h["signal"]

    def sort_key(item):
        t, v = item
        sigs = list(v["signals"].values())
        score = 0
        if "NEW" in sigs: score += 10
        if "INCREASED" in sigs: score += 5
        score += len(v["gurus"])
        return score

    sorted_tickers = sorted(all_tickers.items(), key=sort_key, reverse=True)

    L("## 📋 一、全部机构持仓变动总览")
    L("")
    n_gurus = len([c for c in active_guru_codes if all_data.get(c) and "error" not in all_data.get(c)])
    total_positions = sum(d['num_positions'] for c, d in all_data.items() if c in active_guru_codes and d and 'error' not in d)
    L(f"**{period_label}**，追踪 **{n_gurus}** 家机构共 **{total_positions}** 笔持仓记录。")
    L("")

    header_cols = ["标的代码 & 公司"] + [TRACKED_GURUS[c]["short"] for c in active_guru_codes]
    L("| " + " | ".join(header_cols) + " |")
    L("|" + "|".join([":---"] + [":---:" for _ in active_guru_codes]) + "|")

    for t, v in sorted_tickers:
        row = [f"**{t}** {v['company'][:18]}"]
        for code in active_guru_codes:
            row.append(v["gurus"].get(code, "—"))
        L("| " + " | ".join(row) + " |")

    L("")
    L("---")
    L("")

    # 2. Top Conviction Candidates & Resonance Radar
    L("## 🎯 二、聪明钱核心机会雷达（Conviction & Consensus Radar）")
    L("")

    all_holdings = [x for c, d in all_data.items() if c in active_guru_codes and d and "error" not in d for x in d["holdings"]]
    new_pos = sorted([x for x in all_holdings if x["signal"] == "NEW"], key=lambda x: x["pct"], reverse=True)
    if new_pos:
        L("### ✨ 1. 本季新建仓（按组合权重排序）")
        for x in new_pos:
            g_short = next((TRACKED_GURUS[c]["short"] for c in active_guru_codes if any(hh["ticker"] == x["ticker"] and hh["signal"] == "NEW" for hh in all_data[c]["holdings"])), "?")
            L(f"- **{x['ticker']}** ({x['company'][:25]})：{g_short} 新建仓 **{x['pct']:.2f}%** 权重（持股 {x['shares']:,} 股，约 ${x['value_m']:.1f}M）")
        L("")

    conv = {}
    for c, d in all_data.items():
        if c not in active_guru_codes or not d or "error" in d:
            continue
        for x in d["holdings"]:
            if x["signal"] in ("NEW", "INCREASED"):
                conv.setdefault(x["ticker"], []).append((c, x["signal"]))
    conv = {t: v for t, v in conv.items() if len(v) >= 2}
    if conv:
        L(r"### 🤝 2. 大师圈层同向共振（$\ge 2$ 位独立大师同买）")
        for t, v in conv.items():
            comp = all_tickers.get(t, {}).get("company", "")
            seg = " + ".join(f"{TRACKED_GURUS[c]['short']}({ '新买' if sig=='NEW' else '加仓' })" for c, sig in v)
            L(f"- **{t}** ({comp[:25]})：{seg}")
        L("")

    big = sorted([x for c, d in all_data.items() if c in active_guru_codes and d and "error" not in d
                  for x in d["holdings"]
                  if x["signal"] == "INCREASED" and x["mult"] != float("inf") and x["mult"] >= 1.5],
                 key=lambda x: x["mult"], reverse=True)
    if big:
        L(r"### 💪 3. 最高决心加仓（仓位倍数 $\ge 1.5\times$）")
        for x in big:
            c = next((cc for cc in active_guru_codes
                      if any(hh["ticker"] == x["ticker"] and hh["signal"] == "INCREASED"
                             for hh in all_data[cc]["holdings"])), "?")
            L(f"- **{x['ticker']}**：{TRACKED_GURUS[c]['short']} 仓位放大至 **{x['mult']:.2f}×**（权重增加 {x['weight_chg']:+.2f}%，达到 {x['pct']:.2f}%）")
        L("")

    L("---")
    L("")

    # 3. Cost Window Matrix
    L("## 💰 三、入场成本窗口分析（Cost Window Matrix）")
    L("")
    L("| 标的代码 | 核心机构与动作 | 机构申报成本估算 | 当前市场现价 | 成本窗口评级 | 克隆实战建议 |")
    L("|:---|:---|:---:|:---:|:---:|:---|")

    priority_tickers = []
    if conv: priority_tickers.extend(list(conv.keys()))
    if new_pos: priority_tickers.extend([x["ticker"] for x in new_pos])
    if big: priority_tickers.extend([x["ticker"] for x in big])
    priority_tickers = list(dict.fromkeys(priority_tickers))

    for t in priority_tickers:
        comp = all_tickers.get(t, {}).get("company", "")
        # Find who acted on t
        actors = []
        rep_price = 0.0
        for c in active_guru_codes:
            for hh in (all_data.get(c, {}).get("holdings", [])):
                if hh["ticker"] == t and hh["signal"] in ("NEW", "INCREASED"):
                    actors.append(f"{TRACKED_GURUS[c]['short']}({hh['signal']})")
                    if hh.get("price"): rep_price = hh["price"]
        cur_p = yf_prices.get(t, 0.0)
        cw = cost_window(t, rep_price, yf_prices)
        advice = "待观察"
        if "比成本-" in cw:
            advice = "🟢 显著成本优势，买入价比大师更便宜"
        elif "高成本+" in cw:
            advice = "🟡 已有涨幅，追高需谨慎"
        else:
            advice = "⚪ 处于平价建仓窗口"

        actor_str = "、".join(actors) if actors else "持有"
        rep_p_str = f"${rep_price:.2f}" if rep_price else "—"
        cur_p_str = f"${cur_p:.2f}" if cur_p else "—"
        L(f"| **{t}** | {actor_str} | {rep_p_str} | {cur_p_str} | {cw} | {advice} |")

    L("")
    L("---")
    L("")

    # 4. Detailed Breakdown per Guru
    L("## 🏛️ 四、各机构明细持仓与季度变动")
    L("")
    for code in active_guru_codes:
        info = TRACKED_GURUS[code]
        data = all_data.get(code)
        if not data or "error" in data:
            continue
        h = data["holdings"]
        q_label = data.get("period", "Q")
        L(f"### 📌 {info['name']}")
        L(f"- **总资产规模：** ${data['portfolio_value_m']:,.2f}M ｜ **持仓标的数：** {data['num_positions']} ｜ **报告期：** {q_label} ({data['date']})")
        L("")

        for sig in SIGNAL_ORDER:
            items = [x for x in h if x["signal"] == sig]
            if not items:
                continue

            if sig == "NO_CHANGE":
                names = "、".join(f"{x['ticker']}({x['pct']:.1f}%)" for x in items)
                L(f"- 🔵 **持有不变 ({len(items)} 只)：** {names}")
                L("")
                continue

            L(f"#### {SIGNAL_LABEL.get(sig, sig)} ({len(items)} 只)")
            L("| 代码 | 公司 | 占比 | 权重Δ% | 仓位倍数 | 持股数 | 持股变动 | 成本窗口 |")
            L("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
            for x in items:
                mult_val = x.get("mult", 0) or 0
                mult_str = "∞" if mult_val == float("inf") else f"{mult_val:.2f}×"
                cw_str = cost_window(x["ticker"], x.get("price", 0), yf_prices)
                L(f"| **{x['ticker']}** | {x['company'][:25]} | {x['pct']:.2f}% | {x.get('weight_chg', 0):+.2f}% | {mult_str} | {x['shares']:,} | {fmt_ds(x.get('shares_change', 0))} | {cw_str} |")
            L("")
        L("---")
        L("")

    # 5. Off-13F Assets Integration
    off_13f_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "data", "off_13f_holdings.yaml")
    if not os.path.exists(off_13f_path):
        off_13f_path = os.path.join(find_project_root(), "data", "off_13f_holdings.yaml")

    if os.path.exists(off_13f_path):
        try:
            import yaml
            with open(off_13f_path, "r", encoding="utf-8") as f:
                off_data = yaml.safe_load(f)
            if off_data and "gurus" in off_data:
                L("## 🌏 五、非 13F 离岸核心资产特别追踪（港股 / A 股版图）")
                L("")
                L("> 💡 **特别说明：** 13F 仅覆盖美股申报。李录与段永平有大量超额收益来源于港股与中国 A 股本土资产，以下为两位大师公开确认的非美股底仓：")
                L("")
                for g_code, g_info in off_data["gurus"].items():
                    L(f"### 📍 {g_info['name']}")
                    for it in g_info.get("holdings", []):
                        L(f"- **{it['ticker']} {it['name']}** ({it['exchange']})")
                        L(f"  - **投资逻辑：** {it['thesis']}")
                        L(f"  - **仓位特点：** {it['weight_note']}")
                L("")
                L("---")
                L("")
        except Exception:
            pass

    # 6. CFO-Check Pipeline Recommendation
    L("## 🔬 六、FCF Check (`cfo-check`) 深度排雷候选名单")
    L("")
    top_candidates = priority_tickers[:4] if priority_tickers else ["PDD", "BRK.B"]
    cand_str = ", ".join(top_candidates)
    L(f"前道聪明钱雷达已完成筛选，本季度最高确信度与共振候选标的为：**`{cand_str}`**。")
    L("")
    L("建议下一步直接启动后道法医 `cfo-check` 进行深度自由现金流造血穿透与 ARV/EPV 护城河检验：")
    L("```bash")
    L(f"python3 scripts/bridge_to_cfo_check.py --tickers {','.join(top_candidates)}")
    L("```")
    L("")

    return "\n".join(lines), top_candidates

# ── Main Entrypoint ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="13F Institutional Value Radar (Phase 1)")
    parser.add_argument("--tier", type=str, default="1", help="Guru Tiers to audit (e.g. '1' or '1,2'). Default: 1")
    parser.add_argument("--gurus", type=str, default="", help="Comma-separated guru codes to audit. Overrides --tier")
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
    db_path = os.path.join(project_root, "data", "investor_radar.db")

    # Resolve active gurus
    if args.gurus:
        active_codes = [c.strip() for c in args.gurus.split(",") if c.strip() in TRACKED_GURUS]
    else:
        req_tiers = [int(t.strip()) for t in args.tier.split(",") if t.strip().isdigit()]
        active_codes = [c for c, info in TRACKED_GURUS.items() if info["tier"] in req_tiers]

    all_data = {}
    sec_data = {}
    yf_prices = {}
    validation = {}

    print(f"🚀 [Institutional Value Radar Phase 1] Active Gurus: {', '.join(active_codes)}")
    print(f"📁 Reports Directory: {out_dir}")
    print(f"💾 SQLite DB: {db_path}")

    # 1. Fetch Dataroma
    print(f"\n📡 Step 1: Fetching holdings & historical data from Dataroma...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        fm = {ex.submit(fetch_guru_holdings, code): code for code in active_codes}
        for f in as_completed(fm):
            code = fm[f]
            data = f.result()
            all_data[code] = data
            if "error" not in data:
                print(f"  ✅ {TRACKED_GURUS[code]['short']}: {data['num_positions']} holdings (${data['portfolio_value_m']:,.1f}M)")
            else:
                print(f"  ❌ {TRACKED_GURUS[code]['short']}: Error ({data['error']})")

    # 2. Fetch SEC EDGAR 13F XML
    if not args.skip_sec:
        print(f"\n📡 Step 2: Fetching SEC EDGAR 13F XML filings...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            fm = {}
            for code in active_codes:
                info = TRACKED_GURUS[code]
                if info.get("cik_active") and info.get("cik"):
                    fm[ex.submit(fetch_sec_13f, info["cik"])] = code
            for f in as_completed(fm):
                code = fm[f]
                sec = f.result()
                sec_data[code] = sec
                if sec and "error" not in sec and "holdings" in sec:
                    print(f"  ✅ {TRACKED_GURUS[code]['short']}: {sec['num_positions']} positions from SEC")
                else:
                    print(f"  ⚠️ {TRACKED_GURUS[code]['short']}: No direct SEC 13F parsed")
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
        print(f"\n📡 Step 3: Fetching market prices for {len(all_tickers)} unique tickers...")
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

    # 5. Record to SQLite Time-Series DB
    quarter = "Q2 2026"
    for code in active_codes:
        d = all_data.get(code)
        if d and d.get("period"):
            quarter = d["period"]
            break
    print(f"\n💾 Step 5: Ingesting into SQLite time-series database ({db_path})...")
    record_to_sqlite(db_path, quarter, all_data)
    print("  ✅ Time-series snapshots stored in SQLite")

    # 6. Generate Markdown Report
    print(f"\n📝 Step 6: Rendering Value Radar opportunity report...")
    md, top_candidates = generate_markdown(all_data, sec_data, yf_prices, validation, active_codes, db_path)

    yyyymmdd = datetime.datetime.now().strftime("%Y%m%d")
    mmddyyyy = datetime.datetime.now().strftime("%m-%d-%Y")

    snap_prefix = f"celebrity_clone_{mmddyyyy}_Q2_V"
    existing_snap = [f for f in os.listdir(out_dir) if f.startswith(snap_prefix) and f.endswith(".md")]
    max_sv = 0
    for f in existing_snap:
        m = re.search(rf"{re.escape(snap_prefix)}(\d+)\.md$", f)
        if m: max_sv = max(max_sv, int(m.group(1)))
    snap_version = max_sv + 1
    latest_name = f"{snap_prefix}{snap_version}.md"

    archive_prefix = f"celebrity_clone策略对比_{yyyymmdd}_V"
    existing = [f for f in os.listdir(out_dir) if f.startswith(archive_prefix) and f.endswith(".md")]
    max_v = 0
    for f in existing:
        m = re.search(rf"{re.escape(archive_prefix)}(\d+)\.md$", f)
        if m: max_v = max(max_v, int(m.group(1)))
    version = max_v + 1
    archive_name = f"{archive_prefix}{version}.md"

    archive_path = os.path.join(out_dir, archive_name)
    latest_path = os.path.join(out_dir, latest_name)

    for p in [archive_path, latest_path]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)

    print(f"  ✅ Report saved: {latest_path}")
    print(f"  ✅ Archive saved: {archive_path}")

    # 7. Obsidian Sync
    if args.sync_obsidian:
        print(f"\n🔄 Step 7: Syncing to Obsidian...")
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
            print(f"  ⚠️ Obsidian sync notice: {e}")

    print("\n🎉 Institutional Value Radar (Phase 1) Completed Successfully!")
    print(f"👉 Next Step: Run CFO-Check on Top Candidates: {', '.join(top_candidates)}")

if __name__ == "__main__":
    main()
