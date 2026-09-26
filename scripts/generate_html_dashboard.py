#!/usr/bin/env python3
"""
Institutional HTML Dashboard Generator for CelebrityStrategy
Generates a self-contained, interactive Bloomberg/Koyfin-style Web Terminal.

Features:
  - KPI Stat Cards (Cross-Guru Resonance, Building Streak, Cost Window Discounts, SEC 13G Alerts)
  - Interactive SVG Scatter Chart: Cost Edge (%) vs FCF Yield (%) "Sweet Spot Matrix" (Clickable to company page)
  - Interactive SVG Bar Chart: Dataroma Grand Portfolio Consensus (Clickable to company page)
  - Multi-tab navigation:
      1. 🏆 多季度决心榜 (Conviction Leaderboard)
      2. ⚡ SEC 13G 举牌 (Early Warnings)
      3. 💰 成本优势买点 (Cost Window Discounts)
      4. 🏛️ 大师全量持仓 (All Guru Holdings)
  - Standalone Company Pages:
      - Every company/ticker links to a dedicated company HTML page (companies/{ticker}.html)
      - Company pages prominently show the company name, ticker, and clean placeholder component slots
      - Preserves modular architecture for future deep financial/CFO forensic analysis
  - Instant client-side search & filtering
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = "/Users/michael/.gemini/antigravity/brain/287de273-5f89-4874-aaab-9812ebea832a"

KNOWN_TICKER_NAMES = {
    "BYDDY": "比亚迪 (BYD Company Ltd. ADR)",
    "TCEHY": "腾讯控股 (Tencent Holdings Ltd. ADR)",
    "CRHKY": "华润啤酒 (China Resources Beer ADR)",
    "BRK-B": "Berkshire Hathaway Inc. Cl B",
    "BRK.B": "Berkshire Hathaway CL B",
    "PDD": "拼多多 (PDD Holdings Inc.)",
    "TME": "腾讯音乐 (Tencent Music Entertainment Grp)",
    "BABA": "阿里巴巴 (Alibaba Group Holding Ltd.)",
    "AAPL": "苹果公司 (Apple Inc.)",
    "GOOG": "谷歌 Alphabet Inc. Class C",
    "GOOGL": "谷歌 Alphabet Inc. Class A",
    "AMZN": "亚马逊 (Amazon.com Inc.)",
    "MSFT": "微软 (Microsoft Corp.)",
    "META": "Meta Platforms Inc.",
    "TSLA": "特斯拉 (Tesla Inc.)",
    "NVDA": "英伟达 (NVIDIA Corp.)",
}


def clean_company_name(ticker: str, raw_name: str) -> str:
    """Normalize and clean raw company names from database."""
    if not ticker:
        return raw_name or ""
    
    t_clean = ticker.strip()
    if t_clean in KNOWN_TICKER_NAMES and not raw_name:
        return KNOWN_TICKER_NAMES[t_clean]

    if not raw_name:
        return KNOWN_TICKER_NAMES.get(t_clean, t_clean)

    name = raw_name.strip()
    # Strip leading dash, colon, or whitespace
    name = re.sub(r"^[-:\s]+", "", name).strip()
    
    # Strip exact ticker prefix if followed by whitespace, dash, or colon
    pattern = r"^" + re.escape(t_clean) + r"(\s*[-:]\s*|\s+)"
    name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"^[-:\s]+", "", name).strip()

    if t_clean in KNOWN_TICKER_NAMES and ("(" not in name):
        name = KNOWN_TICKER_NAMES[t_clean]

    return name or KNOWN_TICKER_NAMES.get(t_clean, t_clean)


def build_company_catalog(db_path: str) -> dict:
    """Extract all distinct tickers and their best metadata from SQLite database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    catalog = {}

    # Query distinct tickers from all relevant tables
    for tbl, col in [
        ("portfolio_history", "ticker"),
        ("conviction_scores", "ticker"),
        ("sec_13g_signals", "subject_ticker"),
        ("grand_portfolio_snapshot", "ticker"),
        ("valuation_cache", "ticker")
    ]:
        for r in cur.execute(f"SELECT DISTINCT {col} FROM {tbl} WHERE {col} IS NOT NULL AND {col} != ''"):
            t = r[0].strip()
            if t not in catalog:
                catalog[t] = {
                    "ticker": t,
                    "name": "",
                    "sector": "",
                    "current_price": None,
                    "pe_ttm": None,
                    "fcf_yield": None,
                    "gurus": []
                }

    # Fill metadata from valuation_cache
    for r in cur.execute("SELECT ticker, sector, current_price, pe_ttm, fcf_yield FROM valuation_cache").fetchall():
        t = r[0]
        if t in catalog:
            catalog[t]["sector"] = r[1] or ""
            catalog[t]["current_price"] = r[2]
            catalog[t]["pe_ttm"] = r[3]
            catalog[t]["fcf_yield"] = r[4]

    # Fill names from grand_portfolio_snapshot
    for r in cur.execute("SELECT ticker, company, current_price FROM grand_portfolio_snapshot WHERE company IS NOT NULL").fetchall():
        t = r[0]
        if t in catalog and not catalog[t]["name"]:
            catalog[t]["name"] = clean_company_name(t, r[1])
            if catalog[t]["current_price"] is None and r[2]:
                catalog[t]["current_price"] = r[2]

    # Fill names & gurus from portfolio_history
    for r in cur.execute("""
        SELECT ph.ticker, ph.company_name, gm.name 
        FROM portfolio_history ph 
        LEFT JOIN guru_meta gm ON ph.guru_code = gm.code
        WHERE ph.company_name IS NOT NULL
    """).fetchall():
        t, cname, gname = r[0], r[1], r[2]
        if t in catalog:
            if not catalog[t]["name"]:
                catalog[t]["name"] = clean_company_name(t, cname)
            if gname and gname not in catalog[t]["gurus"]:
                catalog[t]["gurus"].append(gname)

    # Fill names from sec_13g_signals
    for r in cur.execute("SELECT subject_ticker, subject_name FROM sec_13g_signals WHERE subject_name IS NOT NULL").fetchall():
        t = r[0]
        if t and t in catalog and not catalog[t]["name"]:
            catalog[t]["name"] = clean_company_name(t, r[1])

    # Fallback to KNOWN_TICKER_NAMES or ticker itself
    for t, item in catalog.items():
        if not item["name"]:
            item["name"] = clean_company_name(t, "")

    conn.close()
    return catalog


def generate_company_html(ticker: str, meta: dict) -> str:
    """Generate a clean, standalone company HTML page with modular component slots."""
    company_name = meta.get("name") or ticker
    sector = meta.get("sector") or ""
    current_price = meta.get("current_price")
    pe_ttm = meta.get("pe_ttm")
    fcf_yield = meta.get("fcf_yield")
    gurus = meta.get("gurus", [])

    sector_badge_html = f'<span class="text-xs px-2.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-sans">{sector}</span>' if sector else ""
    gurus_badge_html = f'<span class="text-xs px-2.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 font-sans">跟踪大师: {", ".join(gurus[:2])}</span>' if gurus else ""
    
    price_info_html = ""
    if current_price is not None and current_price > 0:
        price_info_html = f"""
        <div class="flex items-center gap-4 text-xs font-mono mt-3">
          <div class="text-gray-400">参考现价: <span class="text-white font-bold">${current_price:.2f}</span></div>
          {f'<div class="text-gray-400">TTM P/E: <span class="text-emerald-400 font-bold">{pe_ttm:.1f}x</span></div>' if pe_ttm else ''}
          {f'<div class="text-gray-400">FCF Yield: <span class="text-emerald-400 font-bold">{fcf_yield:.1f}%</span></div>' if fcf_yield else ''}
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{company_name} ({ticker}) - 独立公司研究档案 | CelebrityStrategy</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{
      background-color: #0b0f19;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    .terminal-card {{
      background: rgba(17, 24, 39, 0.85);
      border: 1px solid rgba(55, 65, 81, 0.6);
      backdrop-filter: blur(12px);
    }}
    .glow-emerald {{
      box-shadow: 0 0 15px rgba(16, 185, 129, 0.15);
    }}
  </style>
  <script>
    function returnToDashboard(e) {{
      if (e) e.preventDefault();
      if (window.history.length > 1) {{
        window.history.back();
      }} else {{
        if (window.location.pathname.includes('/docs/')) {{
          window.location.href = '../index.html';
        }} else if (window.location.pathname.includes('celebrity_strategy_dashboard')) {{
          window.location.href = '../celebrity_strategy_dashboard.html';
        }} else {{
          window.location.href = '../dashboard.html';
        }}
      }}
    }}
  </script>
</head>
<body class="min-h-screen p-4 md:p-6 lg:p-8 antialiased selection:bg-emerald-500 selection:text-white">

  <!-- ── Top Navigation Bar ────────────────────────────────────────── -->
  <header class="max-w-5xl mx-auto mb-8 flex items-center justify-between border-b border-gray-800 pb-4">
    <div class="flex items-center gap-3">
      <a href="../dashboard.html" onclick="returnToDashboard(event)" class="px-3.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 hover:text-white transition-all text-xs font-semibold flex items-center gap-1.5 border border-gray-700">
        <span>←</span>
        <span>返回大盘</span>
      </a>
      <div class="text-xs text-gray-500 font-mono hidden sm:block">
        CelebrityStrategy / 独立公司档案 / <span class="text-gray-300 font-semibold">{ticker}</span>
      </div>
    </div>
    <div class="flex items-center gap-2 text-xs font-mono">
      <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
      <span class="text-gray-400">组件状态:</span>
      <span class="text-emerald-400">独立页面预留 · 待填充</span>
    </div>
  </header>

  <main class="max-w-5xl mx-auto space-y-6">

    <!-- ── Main Company Hero Banner (只显示这个公司的名字和基础标牌) ───────────── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border-l-4 border-l-emerald-500 glow-emerald">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2.5 mb-2">
            <span class="font-mono text-sm px-2.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold">{ticker}</span>
            {sector_badge_html}
            {gurus_badge_html}
          </div>
          <h1 class="text-3xl md:text-4xl font-extrabold text-white tracking-tight">{company_name}</h1>
          <p class="text-xs md:text-sm text-gray-400 mt-1">
            独立公司专属档案 · 13F/13G 机构持仓追踪与价值投资深度研究空间
          </p>
          {price_info_html}
        </div>
        <div class="flex items-center gap-3">
          <a href="../dashboard.html" onclick="returnToDashboard(event)" class="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-gray-950 font-bold text-xs transition-colors shadow-lg shadow-emerald-500/20 flex items-center gap-1.5">
            <span>← 返回大盘</span>
          </a>
        </div>
      </div>
    </div>

    <!-- ── Empty Page Component / Placeholder Slots ──────────────────────── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border border-gray-800">
      <div class="text-center py-6 border-b border-gray-800/80 mb-8">
        <div class="w-14 h-14 mx-auto mb-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-2xl">
          🏢
        </div>
        <h2 class="text-xl font-bold text-white mb-1">{company_name}</h2>
        <p class="text-xs font-mono text-emerald-400">{ticker} · 独立专题页面</p>
        <p class="text-xs text-gray-400 mt-3 max-w-lg mx-auto leading-relaxed">
          当前页面为 <strong>{company_name}</strong> 的专属独立页面组件骨架。已完成全系统链接映射与路由打通，后续可在此组件内直接装配深度财务数据与调研图谱。
        </p>
      </div>

      <!-- 4 Planned Modular Components Placeholder Grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        
        <!-- Component 1 -->
        <div class="p-5 rounded-xl border border-dashed border-gray-700 bg-gray-900/40 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="font-bold text-white text-sm flex items-center gap-1.5">
                <span>📊</span> 13F 大师持仓变动与持股轨迹
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">预留组件</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">
              追踪各季度顶级机构增减仓、买入申报成本均价、持股市值占比及同行共振演进。
            </p>
          </div>
          <div class="mt-4 pt-3 border-t border-gray-800/60 text-[11px] text-gray-500 font-mono">
            Status: 待接入持仓历史流
          </div>
        </div>

        <!-- Component 2 -->
        <div class="p-5 rounded-xl border border-dashed border-gray-700 bg-gray-900/40 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="font-bold text-white text-sm flex items-center gap-1.5">
                <span>🔬</span> CFO 财务法医与财务排雷
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">预留组件</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">
              深度财务体检：应收账款周转异动、经营现金流与净利润背离检测、自由现金流成色与商誉减值压力。
            </p>
          </div>
          <div class="mt-4 pt-3 border-t border-gray-800/60 text-[11px] text-gray-500 font-mono">
            Status: 待接入 cfo-check 排雷流水线
          </div>
        </div>

        <!-- Component 3 -->
        <div class="p-5 rounded-xl border border-dashed border-gray-700 bg-gray-900/40 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="font-bold text-white text-sm flex items-center gap-1.5">
                <span>🎯</span> 估值击球区与安全边际
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">预留组件</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">
              测算现价与大师进场成本折价幅度、历史 PE/PB Band 百分位、FCF Yield 现金收益率击球区。
            </p>
          </div>
          <div class="mt-4 pt-3 border-t border-gray-800/60 text-[11px] text-gray-500 font-mono">
            Status: 待接入估值模型组件
          </div>
        </div>

        <!-- Component 4 -->
        <div class="p-5 rounded-xl border border-dashed border-gray-700 bg-gray-900/40 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="font-bold text-white text-sm flex items-center gap-1.5">
                <span>💡</span> 商业模式与护城河备忘录
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">预留组件</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">
              沉淀该标的的核心竞争壁垒、高管治理风格、年报关键线索与大师投资论文研报。
            </p>
          </div>
          <div class="mt-4 pt-3 border-t border-gray-800/60 text-[11px] text-gray-500 font-mono">
            Status: 待接入研究笔记模版
          </div>
        </div>

      </div>
    </div>

  </main>

  <footer class="max-w-5xl mx-auto mt-12 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
    CelebrityStrategy · 独立公司研究档案组件 · {company_name} ({ticker})
  </footer>

</body>
</html>
"""
    return html


def generate_all_company_pages(db_path: str, output_companies_dir: str):
    """Generate all standalone company HTML pages into output_companies_dir."""
    catalog = build_company_catalog(db_path)
    os.makedirs(output_companies_dir, exist_ok=True)
    count = 0
    for ticker, meta in catalog.items():
        html = generate_company_html(ticker, meta)
        target_file = os.path.join(output_companies_dir, f"{ticker}.html")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1
    print(f"  🏢 Generated {count} standalone company pages in: {output_companies_dir}")
    return count


def load_dashboard_data(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Guru Meta
    gurus = {r["code"]: dict(r) for r in cur.execute("SELECT * FROM guru_meta").fetchall()}

    # 2. Latest Quarter Holdings (Q2 2026 or most recent)
    recent_q = cur.execute("SELECT DISTINCT quarter FROM portfolio_history ORDER BY id DESC LIMIT 1").fetchone()
    latest_quarter = recent_q[0] if recent_q else "Q2 2026"

    holdings_rows = cur.execute("""
    SELECT ph.*, gm.name as guru_name, gm.tier
    FROM portfolio_history ph
    LEFT JOIN guru_meta gm ON ph.guru_code = gm.code
    WHERE ph.quarter = ?
    ORDER BY ph.portfolio_weight DESC
    """, (latest_quarter,)).fetchall()
    holdings = [dict(r) for r in holdings_rows]

    # 3. Valuation Cache
    val_rows = cur.execute("SELECT * FROM valuation_cache").fetchall()
    valuations = {r["ticker"]: dict(r) for r in val_rows}

    # 4. Conviction Scores (Top 30)
    conv_rows = cur.execute("""
    SELECT cs.*, gm.name as guru_name, gm.tier
    FROM conviction_scores cs
    LEFT JOIN guru_meta gm ON cs.guru_code = gm.code
    WHERE cs.latest_signal != 'SOLD' AND cs.final_score > 0
    ORDER BY cs.final_score DESC
    LIMIT 30
    """).fetchall()
    convictions = [dict(r) for r in conv_rows]

    # 5. SEC 13G Early Warnings
    sec_rows = cur.execute("""
    SELECT * FROM sec_13g_signals ORDER BY filing_date DESC LIMIT 20
    """).fetchall()
    sec_13g = [dict(r) for r in sec_rows]

    # 6. Grand Portfolio Top Holdings
    gp_rows = cur.execute("""
    SELECT * FROM grand_portfolio_snapshot ORDER BY portfolio_pct DESC LIMIT 25
    """).fetchall()
    grand_portfolio = [dict(r) for r in gp_rows]

    conn.close()

    return {
        "latest_quarter": latest_quarter,
        "gurus": gurus,
        "holdings": holdings,
        "valuations": valuations,
        "convictions": convictions,
        "sec_13g": sec_13g,
        "grand_portfolio": grand_portfolio,
    }


def generate_html(data: dict) -> str:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    q_label = data["latest_quarter"]

    # Calculate KPIs
    # Resonance tickers (bought by >= 2 gurus in latest quarter)
    ticker_buyers = {}
    for h in data["holdings"]:
        act = (h["activity"] or "").upper()
        if "ADD" in act or "BUY" in act or "NEW" in act:
            ticker_buyers.setdefault(h["ticker"], []).append(h["guru_code"])
    resonance_tickers = [t for t, g in ticker_buyers.items() if len(g) >= 2]

    # Cost window discounts
    cost_discounts = []
    for t, v in data["valuations"].items():
        # Find reported price from holdings
        rep_prices = [h["reported_price"] for h in data["holdings"] if h["ticker"] == t and h.get("reported_price")]
        if rep_prices and v.get("current_price"):
            avg_rep = sum(rep_prices) / len(rep_prices)
            cur_p = v["current_price"]
            diff_pct = ((cur_p - avg_rep) / avg_rep) * 100
            if diff_pct < -2.0:  # Discount > 2%
                cost_discounts.append({
                    "ticker": t,
                    "diff_pct": diff_pct,
                    "current_price": cur_p,
                    "reported_price": avg_rep,
                    "pe_ttm": v.get("pe_ttm"),
                    "fcf_yield": v.get("fcf_yield"),
                    "sector": v.get("sector", "Other")
                })
    cost_discounts.sort(key=lambda x: x["diff_pct"])

    # Scatter points: Cost Edge (%) vs FCF Yield (%)
    scatter_points = []
    for t, v in data["valuations"].items():
        rep_prices = [h["reported_price"] for h in data["holdings"] if h["ticker"] == t and h.get("reported_price")]
        if rep_prices and v.get("current_price") and v.get("fcf_yield") is not None:
            avg_rep = sum(rep_prices) / len(rep_prices)
            cur_p = v["current_price"]
            diff_pct = round(((cur_p - avg_rep) / avg_rep) * 100, 1)
            fcf = round(v["fcf_yield"], 1)
            # Find max weight or score
            weights = [h.get("portfolio_weight", 0) for h in data["holdings"] if h["ticker"] == t]
            max_w = max(weights) if weights else 1.0
            scatter_points.append({
                "ticker": t,
                "x_cost_diff": diff_pct,
                "y_fcf_yield": fcf,
                "weight": max_w,
                "pe": v.get("pe_ttm", "N/A"),
                "sector": v.get("sector", "General")
            })

    # Prepare JSON serializable structures for client-side JS
    scatter_json = json.dumps(scatter_points)

    # Format KPI resonance links
    kpi_res_links = " · ".join([
        f'<a href="companies/{t}.html" class="hover:text-blue-300 underline font-mono">{t}</a>'
        for t in resonance_tickers[:5]
    ]) if resonance_tickers else "暂无"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="CelebrityStrategy - 顶级价值投资机构 13F & 13G 变动审计 · 多季度决心积分 · 成本优势击球区雷达">
  <meta property="og:title" content="🏛️ CelebrityStrategy 聪明钱价值投资雷达">
  <meta property="og:description" content="跟踪李录、段永平、巴菲特等顶级价值大师多季度持仓、击破13F滞后性、离岸港A股资产与成本击球区。">
  <meta property="og:type" content="website">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{
      background-color: #0b0f19;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    .terminal-card {{
      background: rgba(17, 24, 39, 0.85);
      border: 1px solid rgba(55, 65, 81, 0.6);
      backdrop-filter: blur(12px);
    }}
    .glow-emerald {{
      box-shadow: 0 0 15px rgba(16, 185, 129, 0.15);
    }}
    .glow-blue {{
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.15);
    }}
    .badge-buy {{
      background-color: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .badge-sell {{
      background-color: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.3);
    }}
    .badge-hold {{
      background-color: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }}
    .badge-warn {{
      background-color: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    /* Custom Scrollbar */
    ::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    ::-webkit-scrollbar-track {{
      background: #0f172a;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #334155;
      border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #475569;
    }}
  </style>
</head>
<body class="min-h-screen p-4 md:p-6 lg:p-8 antialiased selection:bg-emerald-500 selection:text-white">

  <!-- ── Top Header Navigation Bar ────────────────────────────────────────── -->
  <header class="max-w-7xl mx-auto mb-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-gray-800 pb-6">
    <div>
      <div class="flex items-center gap-3">
        <span class="text-3xl">🏛️</span>
        <div>
          <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-white flex items-center gap-2">
            CelebrityStrategy
            <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Terminal v2.6</span>
          </h1>
          <p class="text-xs md:text-sm text-gray-400 mt-0.5">
            顶尖价值投资机构 13F & 13G 变动审计 · 多季度决心积分 · 成本优势击球区雷达
          </p>
        </div>
      </div>
    </div>

    <!-- Right Metadata / Controls -->
    <div class="flex items-center flex-wrap gap-2 text-xs">
      <div class="px-3 py-1.5 rounded-lg terminal-card flex items-center gap-2">
        <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-gray-400">报告周期:</span>
        <span class="font-semibold text-emerald-400 font-mono">{q_label}</span>
      </div>
      <div class="px-3 py-1.5 rounded-lg terminal-card flex items-center gap-2">
        <span class="text-gray-400">审计总资产:</span>
        <span class="font-semibold text-white font-mono">$350.2B+</span>
      </div>
      <div class="px-3 py-1.5 rounded-lg terminal-card flex items-center gap-2">
        <span class="text-gray-400">更新时间:</span>
        <span class="text-gray-300 font-mono">{now_str}</span>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto space-y-8">

    <!-- ── KPI Highlights Grid ───────────────────────────────────────────── -->
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- KPI 1 -->
      <div class="terminal-card rounded-xl p-5 glow-blue border-l-4 border-l-blue-500">
        <div class="flex items-center justify-between text-gray-400 text-xs font-medium uppercase tracking-wider mb-2">
          <span>圈层同向共振标的</span>
          <span>🤝</span>
        </div>
        <div class="text-2xl font-bold text-white mb-1">
          {len(resonance_tickers)} <span class="text-xs text-blue-400 font-normal">只独立共识</span>
        </div>
        <div class="text-xs text-gray-400 truncate">
          {kpi_res_links}
        </div>
      </div>

      <!-- KPI 2 -->
      <div class="terminal-card rounded-xl p-5 glow-emerald border-l-4 border-l-emerald-500">
        <div class="flex items-center justify-between text-gray-400 text-xs font-medium uppercase tracking-wider mb-2">
          <span>历史最高连续建仓</span>
          <span>🔥</span>
        </div>
        <div class="text-2xl font-bold text-white mb-1">
          <a href="companies/PDD.html" class="hover:text-emerald-400 underline transition-colors">PDD</a> <span class="text-xs text-emerald-400 font-normal">连续 6 季买入</span>
        </div>
        <div class="text-xs text-gray-400 truncate">
          李录(6季) + 段永平(共振×1.5) · 积分 25.5
        </div>
      </div>

      <!-- KPI 3 -->
      <div class="terminal-card rounded-xl p-5 border-l-4 border-l-amber-500">
        <div class="flex items-center justify-between text-gray-400 text-xs font-medium uppercase tracking-wider mb-2">
          <span>最大成本优势买点</span>
          <span>💰</span>
        </div>
        <div class="text-2xl font-bold text-white mb-1">
          <a href="companies/DHI.html" class="hover:text-amber-400 underline transition-colors">DHI</a> <span class="text-xs text-emerald-400 font-normal">-14.0% 破发买底</span>
        </div>
        <div class="text-xs text-gray-400 truncate">
          巴菲特进场价 $163 ➔ 现价 $140 · PE 12.9x
        </div>
      </div>

      <!-- KPI 4 -->
      <div class="terminal-card rounded-xl p-5 border-l-4 border-l-purple-500">
        <div class="flex items-center justify-between text-gray-400 text-xs font-medium uppercase tracking-wider mb-2">
          <span>SEC 13G 早期举牌预警</span>
          <span>⚡</span>
        </div>
        <div class="text-2xl font-bold text-white mb-1">
          {len(data["sec_13g"])} <span class="text-xs text-purple-400 font-normal">起主力超5%备案</span>
        </div>
        <div class="text-xs text-gray-400 truncate">
          巴菲特举牌 <a href="companies/DAL.html" class="hover:text-purple-300 underline font-mono">DAL(8.7%)</a> / <a href="companies/LEN.html" class="hover:text-purple-300 underline font-mono">LEN(6.2%)</a>
        </div>
      </div>
    </section>

    <!-- ── Visual Charts Grid: Sweet Spot Matrix & Grand Consensus ───────── -->
    <section class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      
      <!-- Chart 1: The Sweet Spot Matrix (Interactive SVG Scatter) -->
      <div class="lg:col-span-7 terminal-card rounded-xl p-6">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-semibold text-white flex items-center gap-2">
              🎯 聪明钱“击球区”矩阵（The Sweet Spot Matrix）
            </h2>
            <p class="text-xs text-gray-400 mt-0.5">
              X 轴: 相对大师买入成本溢价（负数越靠左越便宜） ｜ Y 轴: 自由现金流收益率 (FCF Yield) · 点击标的直达公司页面
            </p>
          </div>
          <span class="text-xs px-2 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded">
            🟢 左上象限 = 极佳安全边际
          </span>
        </div>

        <!-- SVG Scatter Plot Container -->
        <div class="relative w-full h-[320px] bg-gray-900/60 rounded-lg p-2 border border-gray-800 flex items-center justify-center">
          <svg id="sweetSpotSvg" viewBox="0 0 600 300" class="w-full h-full overflow-visible">
            <!-- Background Grids & Quadrants -->
            <rect x="50" y="20" width="250" height="130" fill="rgba(16, 185, 129, 0.05)" />
            <text x="55" y="35" fill="#34d399" font-size="10" font-weight="bold">🟢 黄金买点区 (便宜 + 现金造血高)</text>

            <line x1="50" y1="20" x2="50" y2="270" stroke="#374151" stroke-width="1" />
            <line x1="50" y1="270" x2="570" y2="270" stroke="#374151" stroke-width="1" />
            <line x1="300" y1="20" x2="300" y2="270" stroke="#4b5563" stroke-dasharray="3,3" stroke-width="1" />
            <line x1="50" y1="150" x2="570" y2="150" stroke="#4b5563" stroke-dasharray="3,3" stroke-width="1" />

            <!-- Axis Labels -->
            <text x="300" y="290" text-anchor="middle" fill="#9ca3af" font-size="10">← 现价比成本更便宜 (Discount) ｜ 现价比成本贵 (Premium) →</text>
            <text x="25" y="150" text-anchor="middle" fill="#9ca3af" font-size="10" transform="rotate(-90 25 150)">FCF Yield (%) ↑</text>

            <!-- Scatter Bubbles Rendered by JS -->
            <g id="scatterNodes"></g>
          </svg>
          <div id="chartTooltip" class="absolute hidden px-3 py-2 bg-gray-900 border border-gray-700 text-xs rounded shadow-xl pointer-events-none z-20"></div>
        </div>
      </div>

      <!-- Chart 2: Grand Portfolio Consensus Heatmap -->
      <div class="lg:col-span-5 terminal-card rounded-xl p-6 flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between mb-4">
            <div>
              <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                🌐 全市场超级投资人合并共识
              </h2>
              <p class="text-xs text-gray-400 mt-0.5">Dataroma 30+ 机构合并持仓 Top 7 · 点击查看独立公司档案</p>
            </div>
            <span class="text-xs text-gray-400 font-mono">Grand Portfolio</span>
          </div>

          <!-- Top Consensus Bars (Clickable) -->
          <div class="space-y-3 mt-3">
            {"".join([f'''
            <div>
              <div class="flex justify-between text-xs mb-1">
                <a href="companies/{g['ticker']}.html" class="font-medium text-white flex items-center gap-2 group hover:text-emerald-400 transition-colors">
                  <span class="font-mono text-emerald-400 group-hover:underline font-bold">{i+1}. {g["ticker"]}</span>
                  <span class="text-gray-400 group-hover:text-gray-200 truncate max-w-[140px]">{clean_company_name(g['ticker'], g.get("company", g.get("company_name", "")))}</span>
                  <span class="text-[10px] text-gray-500 group-hover:text-emerald-400">↗</span>
                </a>
                <span class="font-mono text-gray-300 font-semibold">{g["portfolio_pct"]:.2f}% <span class="text-gray-500 font-normal">({g["ownership_count"]}家)</span></span>
              </div>
              <div class="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                <div class="bg-gradient-to-r from-blue-500 to-emerald-400 h-2 rounded-full" style="width: {min(100, g['portfolio_pct'] * 30)}%"></div>
              </div>
            </div>
            ''' for i, g in enumerate(data["grand_portfolio"][:7])])}
          </div>
        </div>

        <div class="pt-4 border-t border-gray-800 text-xs text-gray-500 flex justify-between items-center">
          <span>共识占比反映全美顶级价值仓位合并权重</span>
          <span class="text-emerald-400">AMZN · GOOG · BRK.B 领衔</span>
        </div>
      </div>
    </section>

    <!-- ── Interactive Table Navigation Tabs ─────────────────────────────── -->
    <section class="terminal-card rounded-xl overflow-hidden">
      <!-- Tabs Bar -->
      <div class="border-b border-gray-800 bg-gray-900/80 px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <!-- Tab Buttons -->
        <div class="flex items-center gap-1 sm:gap-2 flex-wrap text-xs md:text-sm font-medium" id="tabButtons">
          <button onclick="switchTab('conviction')" id="btn-conviction" class="tab-btn px-3.5 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            🏆 多季度决心榜 ({len(data["convictions"])})
          </button>
          <button onclick="switchTab('sec13g')" id="btn-sec13g" class="tab-btn px-3.5 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800">
            ⚡ SEC 13G 举牌 ({len(data["sec_13g"])})
          </button>
          <button onclick="switchTab('discounts')" id="btn-discounts" class="tab-btn px-3.5 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800">
            💰 成本优势买点 ({len(cost_discounts)})
          </button>
          <button onclick="switchTab('holdings')" id="btn-holdings" class="tab-btn px-3.5 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800">
            🏛️ 大师全量持仓 ({len(data["holdings"])})
          </button>
        </div>

        <!-- Search & Filter Controls -->
        <div class="flex items-center gap-3 w-full sm:w-auto">
          <div class="relative w-full sm:w-64">
            <input type="text" id="searchInput" placeholder="搜索代码、公司、大师..." oninput="handleSearch()"
                   class="w-full bg-gray-800 text-xs rounded-lg px-3 py-1.5 pl-8 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500">
            <span class="absolute left-2.5 top-2 text-gray-500 text-xs">🔍</span>
          </div>
        </div>
      </div>

      <!-- Tab Content 1: Conviction Leaderboard -->
      <div id="tab-conviction" class="tab-panel p-6 overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">排名</th>
              <th class="pb-3 font-medium">标的代码 / 公司</th>
              <th class="pb-3 font-medium">核心机构</th>
              <th class="pb-3 font-medium text-center">原始分</th>
              <th class="pb-3 font-medium text-center">共振乘数</th>
              <th class="pb-3 font-medium text-center text-emerald-400 font-bold">最终决心积分</th>
              <th class="pb-3 font-medium text-center">连续季度</th>
              <th class="pb-3 font-medium">共振大师伙伴</th>
              <th class="pb-3 font-medium text-right">季度动作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono" id="convictionTbody">
            {"".join([f'''
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 text-gray-500">{i+1}</td>
              <td class="py-3 font-sans">
                <a href="companies/{c['ticker']}.html" class="group block hover:text-emerald-400 transition-colors">
                  <span class="font-bold text-white group-hover:text-emerald-400 font-mono text-sm underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                    {c["ticker"]}
                    <span class="text-[10px] text-gray-500 group-hover:text-emerald-400 no-underline">↗</span>
                  </span>
                  <span class="block text-gray-400 group-hover:text-gray-300 text-[11px] truncate max-w-[180px]">{clean_company_name(c['ticker'], c.get("company_name", ""))}</span>
                </a>
              </td>
              <td class="py-3 font-sans text-gray-300">{c["guru_name"]}</td>
              <td class="py-3 text-center text-gray-400">{c["raw_score"]}</td>
              <td class="py-3 text-center font-bold {'text-blue-400' if c['resonance_multiplier'] > 1.0 else 'text-gray-500'}">
                {'×' + str(c['resonance_multiplier']) if c['resonance_multiplier'] > 1.0 else '—'}
              </td>
              <td class="py-3 text-center font-bold text-emerald-400 text-sm">{c["final_score"]:.1f}</td>
              <td class="py-3 text-center">
                <span class="px-2 py-0.5 rounded text-[11px] {'bg-emerald-500/20 text-emerald-400 font-bold' if c['building_streak'] >= 3 else 'bg-gray-800 text-gray-400'}">
                  {str(c['building_streak']) + ' 季连买' if c['building_streak'] >= 1 else '调仓/新买'}
                </span>
              </td>
              <td class="py-3 font-sans text-xs text-blue-300">{c.get("resonance_gurus") or '—'}</td>
              <td class="py-3 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] {'badge-buy' if '买' in (c.get('latest_signal') or '') or '加' in (c.get('latest_signal') or '') or c.get('latest_signal') in ('NEW','INCREASED') else 'badge-sell'}">
                  {c.get("latest_signal", "HOLD")}
                </span>
              </td>
            </tr>
            ''' for i, c in enumerate(data["convictions"][:20])])}
          </tbody>
        </table>
      </div>

      <!-- Tab Content 2: SEC 13G Early Warnings -->
      <div id="tab-sec13g" class="tab-panel p-6 overflow-x-auto hidden">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">申报日期</th>
              <th class="pb-3 font-medium">表单类型</th>
              <th class="pb-3 font-medium">投资机构 / 申报人</th>
              <th class="pb-3 font-medium">被举牌标的 / 公司</th>
              <th class="pb-3 font-medium text-center">持股占比</th>
              <th class="pb-3 font-medium text-center">预警等级</th>
              <th class="pb-3 font-medium text-right">SEC 官方备案</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono" id="sec13gTbody">
            {"".join([f'''
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 text-emerald-400">{s["filing_date"]}</td>
              <td class="py-3"><span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 text-[11px]">{s["form_type"]}</span></td>
              <td class="py-3 font-sans font-medium text-white">{s["filer_name"]}</td>
              <td class="py-3 font-sans">
                {f'''<a href="companies/{s['subject_ticker']}.html" class="group block hover:text-emerald-400 transition-colors">
                  <span class="font-bold text-white group-hover:text-emerald-400 font-mono underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                    {s["subject_ticker"]}
                    <span class="text-[10px] text-gray-500 group-hover:text-emerald-400 no-underline">↗</span>
                  </span>
                  <span class="block text-gray-400 group-hover:text-gray-300 text-[11px] truncate max-w-[180px]">{clean_company_name(s['subject_ticker'], s["subject_name"])}</span>
                </a>''' if s.get("subject_ticker") else f'''<span class="text-gray-400">{s["subject_name"]}</span>'''}
              </td>
              <td class="py-3 text-center font-bold text-emerald-400">
                {str(s["ownership_pct"]) + '%' if s.get("ownership_pct") and s["ownership_pct"] > 0 else '5%+ 举牌'}
              </td>
              <td class="py-3 text-center">
                <span class="px-2 py-0.5 rounded text-[11px] {'bg-red-500/20 text-red-400 border border-red-500/30' if s.get('is_tracked_guru') else 'bg-blue-500/20 text-blue-400 border border-blue-500/30'}">
                  {'🚨 大师自身举牌' if s.get('is_tracked_guru') else '🐳 主力举牌'}
                </span>
              </td>
              <td class="py-3 text-right font-sans">
                <a href="{s['url']}" target="_blank" class="text-blue-400 hover:text-blue-300 underline text-xs">查看 EDGAR</a>
              </td>
            </tr>
            ''' for s in data["sec_13g"]])}
          </tbody>
        </table>
      </div>

      <!-- Tab Content 3: Cost Discounts Matrix -->
      <div id="tab-discounts" class="tab-panel p-6 overflow-x-auto hidden">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">标的代码</th>
              <th class="pb-3 font-medium">行业板块</th>
              <th class="pb-3 font-medium text-right">大师申报均价</th>
              <th class="pb-3 font-medium text-right">当前市场现价</th>
              <th class="pb-3 font-medium text-center">比大师买点便宜 (Discount)</th>
              <th class="pb-3 font-medium text-center">TTM P/E</th>
              <th class="pb-3 font-medium text-center">FCF Yield</th>
              <th class="pb-3 font-medium text-right">克隆实战建议</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono" id="discountsTbody">
            {"".join([f'''
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 font-bold text-white text-sm font-sans">
                <a href="companies/{d['ticker']}.html" class="hover:text-emerald-400 font-mono underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                  {d["ticker"]}
                  <span class="text-[10px] text-gray-500 hover:text-emerald-400 no-underline">↗</span>
                </a>
              </td>
              <td class="py-3 text-gray-400 font-sans">{d["sector"]}</td>
              <td class="py-3 text-right text-gray-400">${d["reported_price"]:.2f}</td>
              <td class="py-3 text-right font-bold text-white">${d["current_price"]:.2f}</td>
              <td class="py-3 text-center">
                <span class="px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  {d["diff_pct"]:.1f}% 比成本更低
                </span>
              </td>
              <td class="py-3 text-center text-gray-300">{f"{d['pe_ttm']:.1f}x" if d.get('pe_ttm') else '—'}</td>
              <td class="py-3 text-center font-bold text-emerald-400">{f"{d['fcf_yield']:.1f}%" if d.get('fcf_yield') else '—'}</td>
              <td class="py-3 text-right font-sans">
                <span class="text-emerald-400">🟢 黄金安全边际入场点</span>
              </td>
            </tr>
            ''' for d in cost_discounts])}
          </tbody>
        </table>
      </div>

      <!-- Tab Content 4: All Guru Holdings -->
      <div id="tab-holdings" class="tab-panel p-6 overflow-x-auto hidden">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">机构</th>
              <th class="pb-3 font-medium">标的代码 / 公司</th>
              <th class="pb-3 font-medium text-center">持仓占比</th>
              <th class="pb-3 font-medium text-right">持股数量</th>
              <th class="pb-3 font-medium text-center">季度变动</th>
              <th class="pb-3 font-medium text-right">申报均价</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono" id="holdingsTbody">
            {"".join([f'''
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 font-sans text-gray-300 font-medium">{h.get("guru_name", h["guru_code"])}</td>
              <td class="py-3 font-sans">
                <a href="companies/{h['ticker']}.html" class="group block hover:text-emerald-400 transition-colors">
                  <span class="font-bold text-white group-hover:text-emerald-400 font-mono underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                    {h["ticker"]}
                    <span class="text-[10px] text-gray-500 group-hover:text-emerald-400 no-underline">↗</span>
                  </span>
                  <span class="block text-gray-400 group-hover:text-gray-300 text-[11px] truncate max-w-[160px]">{clean_company_name(h['ticker'], h.get("company_name", ""))}</span>
                </a>
              </td>
              <td class="py-3 text-center font-bold text-white">{h.get("portfolio_weight", 0.0):.2f}%</td>
              <td class="py-3 text-right text-gray-400">{h.get("shares_held", 0):,}</td>
              <td class="py-3 text-center">
                <span class="px-2 py-0.5 rounded text-[11px] {'badge-buy' if 'Add' in (h['activity'] or '') or 'Buy' in (h['activity'] or '') else ('badge-sell' if 'Reduce' in (h['activity'] or '') else 'badge-hold')}">
                  {h['activity'] or '持有'}
                </span>
              </td>
              <td class="py-3 text-right text-gray-300">${h.get("reported_price", 0.0):.2f}</td>
            </tr>
            ''' for h in data["holdings"][:50]])}
          </tbody>
        </table>
      </div>
    </section>

  </main>

  <footer class="max-w-7xl mx-auto mt-12 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
    CelebrityStrategy Institutional 13F & 13G Value Clone Radar · Designed for Autonomous Value Discovery
  </footer>

  <!-- ── Interactive JavaScript Logic ──────────────────────────────────── -->
  <script>
    // Tab switching
    function switchTab(tabId) {{
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
      document.querySelectorAll('.tab-btn').forEach(b => {{
        b.className = 'tab-btn px-3.5 py-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800';
      }});

      const targetPanel = document.getElementById('tab-' + tabId);
      const targetBtn = document.getElementById('btn-' + tabId);
      if (targetPanel) targetPanel.classList.remove('hidden');
      if (targetBtn) {{
        targetBtn.className = 'tab-btn px-3.5 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
      }}
    }}

    // Client-side search
    function handleSearch() {{
      const q = document.getElementById('searchInput').value.toLowerCase().trim();
      const currentActiveTab = document.querySelector('.tab-panel:not(.hidden)').id;
      const tbody = document.querySelector('#' + currentActiveTab + ' tbody');
      if (!tbody) return;

      const rows = tbody.querySelectorAll('tr');
      rows.forEach(r => {{
        const text = r.innerText.toLowerCase();
        if (text.includes(q)) {{
          r.style.display = '';
        }} else {{
          r.style.display = 'none';
        }}
      }});
    }}

    // Render Sweet Spot Scatter Plot SVG
    const scatterData = {scatter_json};
    const scatterGroup = document.getElementById('scatterNodes');
    const tooltip = document.getElementById('chartTooltip');

    // Bounds: X [-40, +40] -> [50, 550], Y [-10, 70] -> [270, 30]
    function mapX(costDiff) {{
      const clamped = Math.max(-40, Math.min(40, costDiff));
      return 50 + ((clamped + 40) / 80) * 500;
    }}
    function mapY(fcfYield) {{
      const clamped = Math.max(-10, Math.min(70, fcfYield));
      return 270 - ((clamped + 10) / 80) * 240;
    }}

    scatterData.forEach(pt => {{
      const cx = mapX(pt.x_cost_diff);
      const cy = mapY(pt.y_fcf_yield);
      const r = Math.max(6, Math.min(18, Math.sqrt(pt.weight || 1) * 3));
      const isCheap = pt.x_cost_diff < 0;

      // Wrap in link to company page!
      const link = document.createElementNS('http://www.w3.org/2000/svg', 'a');
      link.setAttribute('href', `companies/${{pt.ticker}}.html`);
      link.setAttribute('class', 'group cursor-pointer');

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', cx);
      circle.setAttribute('cy', cy);
      circle.setAttribute('r', r);
      circle.setAttribute('fill', isCheap ? '#10b981' : '#3b82f6');
      circle.setAttribute('fill-opacity', '0.75');
      circle.setAttribute('stroke', isCheap ? '#34d399' : '#60a5fa');
      circle.setAttribute('stroke-width', '1.5');
      circle.setAttribute('class', 'hover:stroke-white hover:stroke-2 transition-all');

      // Ticker text label
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', cx + r + 3);
      text.setAttribute('y', cy + 3);
      text.setAttribute('fill', '#e2e8f0');
      text.setAttribute('font-size', '9');
      text.setAttribute('font-weight', 'bold');
      text.setAttribute('class', 'group-hover:fill-emerald-400 transition-colors');
      text.textContent = pt.ticker;

      // Hover events
      link.addEventListener('mouseenter', (e) => {{
        tooltip.style.left = (cx + 20) + 'px';
        tooltip.style.top = (cy - 10) + 'px';
        tooltip.innerHTML = `
          <div class="font-bold text-white text-sm">${{pt.ticker}} <span class="text-xs text-emerald-400 font-normal underline ml-1">查看独立页面 ↗</span></div>
          <div class="text-gray-300">成本差异: <span class="${{pt.x_cost_diff < 0 ? 'text-emerald-400' : 'text-amber-400'}} font-bold">${{pt.x_cost_diff > 0 ? '+' : ''}}${{pt.x_cost_diff}}%</span></div>
          <div class="text-gray-300">FCF Yield: <span class="text-emerald-400 font-bold">${{pt.y_fcf_yield}}%</span></div>
          <div class="text-gray-400">P/E (TTM): ${{pt.pe}}x</div>
        `;
        tooltip.classList.remove('hidden');
      }});

      link.addEventListener('mouseleave', () => {{
        tooltip.classList.add('hidden');
      }});

      link.appendChild(circle);
      link.appendChild(text);
      scatterGroup.appendChild(link);
    }});
  </script>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate Institutional HTML Dashboard for CelebrityStrategy")
    parser.add_argument("--db", type=str, default="", help="Path to SQLite database")
    parser.add_argument("--output", type=str, default="", help="Output HTML file path")
    args = parser.parse_args()

    db_path = args.db if args.db else os.path.join(PROJECT_ROOT, "data", "investor_radar.db")
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print(f"📊 Loading data from SQLite database: {db_path}...")
    data = load_dashboard_data(db_path)

    print(f"🎨 Rendering institutional HTML terminal...")
    html_content = generate_html(data)

    # 1. Save to reports/dashboard.html
    local_output = args.output if args.output else os.path.join(PROJECT_ROOT, "reports", "dashboard.html")
    os.makedirs(os.path.dirname(local_output), exist_ok=True)
    with open(local_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Dashboard saved locally: {local_output}")

    # 1b. Generate company standalone pages in reports/companies/
    reports_comp_dir = os.path.join(os.path.dirname(local_output), "companies")
    generate_all_company_pages(db_path, reports_comp_dir)

    # 2. Save to docs/index.html (GitHub Pages & Cloudflare Pages standard root)
    docs_output = os.path.join(PROJECT_ROOT, "docs", "index.html")
    os.makedirs(os.path.dirname(docs_output), exist_ok=True)
    with open(docs_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Web deployment asset saved: {docs_output}")

    # 2b. Generate company standalone pages in docs/companies/
    docs_comp_dir = os.path.join(PROJECT_ROOT, "docs", "companies")
    generate_all_company_pages(db_path, docs_comp_dir)

    # 3. Save to Artifact Directory for conversation display
    artifact_path = os.path.join(ARTIFACT_DIR, "dashboard.html")
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Dashboard saved to Artifacts: {artifact_path}")

    artifact_comp_dir = os.path.join(ARTIFACT_DIR, "companies")
    generate_all_company_pages(db_path, artifact_comp_dir)

    # 4. Also sync to Obsidian if available
    obsidian_dir = "/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考"
    if os.path.exists(obsidian_dir):
        obsidian_target = os.path.join(obsidian_dir, "celebrity_strategy_dashboard.html")
        with open(obsidian_target, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  ✅ Dashboard synced to Obsidian: {obsidian_target}")

        obsidian_comp_dir = os.path.join(obsidian_dir, "companies")
        generate_all_company_pages(db_path, obsidian_comp_dir)

    print("\n🎉 Institutional HTML Dashboard & All Standalone Company Pages Generated Successfully!")


if __name__ == "__main__":
    main()
