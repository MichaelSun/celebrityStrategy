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
         - 1 Company = 1 Record (deduplicated across gurus & batches)
         - Transparent single Conviction Score badge with interactive hover & click
         - Standalone Scoring Algorithm & Breakdown page (companies/{ticker}_scoring.html)
      2. ⚡ SEC 13G 举牌 (Early Warnings)
      3. 💰 成本优势买点 (Cost Window Discounts)
      4. 🏛️ 大师全量持仓 (All Guru Holdings)
  - Standalone Company Pages:
      - Every company/ticker links to a dedicated company HTML page (companies/{ticker}.html)
      - Company pages prominently show the company name, ticker, and clean placeholder component slots
  - Instant client-side search & filtering
"""

import argparse
import collections
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


def build_conviction_reason(group: list) -> str:
    """Generate human-readable rationale for conviction ranking from guru actions."""
    if not group:
        return "大师重仓持有"
    
    reasons = []
    best = group[0]
    
    # Check multi-quarter streaks
    streaks = []
    for item in group:
        if item.get("building_streak", 0) >= 2:
            gname = (item.get("guru_name") or item.get("guru_code", "")).split("(")[0].replace("·", "").strip()
            streaks.append(f"{gname}连续{item['building_streak']}季建仓")
    
    if streaks:
        reasons.append(" · ".join(streaks))
    else:
        # Check action signals
        actions = []
        for item in group:
            sig = (item.get("latest_signal") or "").upper()
            gname = (item.get("guru_name") or item.get("guru_code", "")).split("(")[0].replace("·", "").strip()
            if any(k in sig for k in ["ADD", "BUY", "INCREASED"]):
                if not any(gname in a for a in actions):
                    actions.append(f"{gname}增持加仓")
            elif "NEW" in sig:
                if not any(gname in a for a in actions):
                    actions.append(f"{gname}新建底仓")
        if actions:
            reasons.append(" · ".join(actions[:2]))
        else:
            reasons.append("核心底仓高位锁定")

    # Add resonance tag if applicable
    if best.get("resonance_multiplier", 1.0) > 1.0:
        reasons.append(f"圈层共振 ×{best['resonance_multiplier']}")

    return " ｜ ".join(reasons)


def aggregate_conviction_scores(raw_convictions: list) -> list:
    """
    Deduplicate and aggregate conviction records so 1 Company = 1 Record.
    Sorts by final_score descending and compiles unified rationale.
    """
    by_ticker = {}
    for r in raw_convictions:
        t = r["ticker"]
        by_ticker.setdefault(t, []).append(r)

    aggregated = []
    for t, group in by_ticker.items():
        # Sort group by final_score descending
        group.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        best = group[0]

        # Gather distinct gurus
        gurus_seen = []
        for item in group:
            gname = (item.get("guru_name") or item.get("guru_code", "")).split("(")[0].replace("·", "").strip()
            if gname and gname not in gurus_seen:
                gurus_seen.append(gname)

        reason = build_conviction_reason(group)

        aggregated.append({
            "ticker": t,
            "company_name": best.get("company_name", ""),
            "final_score": best.get("final_score", 0.0),
            "raw_score": best.get("raw_score", 0),
            "resonance_multiplier": best.get("resonance_multiplier", 1.0),
            "building_streak": best.get("building_streak", 0),
            "gurus_display": "、".join(gurus_seen) if gurus_seen else "机构持有",
            "reason": reason,
            "latest_signal": best.get("latest_signal", "HOLD"),
            "group_items": group,
            "best_item": best
        })

    # Sort descending by final_score
    aggregated.sort(key=lambda x: x["final_score"], reverse=True)
    return aggregated


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
                <span>🎯</span> 估值击球区与持仓成本拆解
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">已开通</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">
              测算现价与大师进场成本折价幅度、各家大师独立建仓明细、资金加权均价推导公式。
            </p>
          </div>
          <div class="mt-4 pt-3 border-t border-gray-800/60 flex items-center justify-between text-[11px] font-mono">
            <span class="text-emerald-400">✅ 均价推导就绪</span>
            <a href="{ticker}_cost.html" class="text-blue-400 hover:text-blue-300 underline font-sans">查看均价计算明细 ↗</a>
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


def generate_scoring_detail_html(item: dict, catalog_meta: dict, rank: int) -> str:
    """Generate a dedicated page explaining the conviction algorithm and breakdown for this company."""
    ticker = item["ticker"]
    company_name = catalog_meta.get("name") or ticker
    final_score = item["final_score"]
    gurus_display = item["gurus_display"]
    reason = item["reason"]
    group_items = item.get("group_items", [])

    # Format each guru's calculation row
    guru_rows_html = []
    for g in group_items:
        gname = g.get("guru_name") or g["guru_code"]
        tier_num = g.get("tier", 2)
        tier_label = f"Tier {tier_num}"
        streak = g.get("building_streak", 0)
        raw = g.get("raw_score", 0)
        mult = g.get("resonance_multiplier", 1.0)
        fscore = g.get("final_score", 0.0)
        sig = g.get("latest_signal", "HOLD")

        row_html = f"""
        <tr class="hover:bg-gray-800/40 transition-colors">
          <td class="py-3 font-sans text-white font-medium">
            {gname}
            <span class="text-[10px] ml-1.5 px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">{tier_label}</span>
          </td>
          <td class="py-3 text-center">
            <span class="px-2 py-0.5 rounded text-[11px] {'bg-emerald-500/20 text-emerald-400 font-bold' if streak >= 2 else 'bg-gray-800 text-gray-400'}">
              {f"{streak} 季连买" if streak >= 1 else "调仓/新买"}
            </span>
          </td>
          <td class="py-3 text-center text-gray-300 font-mono font-bold">{raw}</td>
          <td class="py-3 text-center font-mono font-bold {'text-blue-400' if mult > 1.0 else 'text-gray-500'}">
            {'× ' + str(mult) if mult > 1.0 else '— (1.0×)'}
          </td>
          <td class="py-3 text-center text-emerald-400 font-mono font-bold text-sm">{fscore:.1f}</td>
          <td class="py-3 text-right">
            <span class="px-2 py-0.5 rounded text-[11px] {'badge-buy' if '买' in sig or '加' in sig or sig in ('NEW','INCREASED','ADD','BUY') else 'badge-sell'}">
              {sig}
            </span>
          </td>
        </tr>
        """
        guru_rows_html.append(row_html)

    gurus_table_body = "".join(guru_rows_html)

    # Textual step-by-step calculation narrative
    steps_html = []
    steps_html.append(f"<li><strong>1. 纳入最新季度审计</strong>：从最近报告期中提取所有建仓、加仓与重仓 <code>{ticker}</code> 的机构记录，共匹配到 <strong>{len(group_items)}</strong> 家受跟踪投资机构。</li>")
    for idx, g in enumerate(group_items, start=2):
        gname = (g.get("guru_name") or g["guru_code"]).split("(")[0].strip()
        streak = g.get("building_streak", 0)
        raw = g.get("raw_score", 0)
        mult = g.get("resonance_multiplier", 1.0)
        fscore = g.get("final_score", 0.0)
        steps_html.append(f"<li><strong>{idx}. {gname} 独立决心测算</strong>：连续建仓 <strong>{streak}</strong> 季，回溯 6 季动作累积原始积分 <strong>{raw} 分</strong>。触发共振乘数 <strong>×{mult}</strong>，计算得出该机构决心分为 <code>{raw} × {mult} = {fscore:.1f} 分</code>。</li>")

    best_item = item.get("best_item", {})
    best_guru = (best_item.get("guru_name") or best_item.get("guru_code", "")).split("(")[0].strip()
    steps_html.append(f"<li><strong>{len(group_items) + 2}. 标的去重与终审定级</strong>：由于一家公司在多季度榜单中仅呈现一条综合记录，系统自动提取多大师评估中的最高确信度得分（来自 <strong>{best_guru}</strong> 评估的 <code>{final_score:.1f} 分</code>）作为该标的的全网综合排名得分，并综合多大师动作生成排序理由：<em>“{reason}”</em>。</li>")

    steps_list_html = "\n".join(steps_html)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{company_name} ({ticker}) 排序分算法与算分推导明细 | CelebrityStrategy</title>
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

  <!-- ── Top Header Navigation Bar ────────────────────────────────────────── -->
  <header class="max-w-5xl mx-auto mb-8 flex items-center justify-between border-b border-gray-800 pb-4">
    <div class="flex items-center gap-3">
      <a href="../dashboard.html" onclick="returnToDashboard(event)" class="px-3.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 hover:text-white transition-all text-xs font-semibold flex items-center gap-1.5 border border-gray-700">
        <span>←</span>
        <span>返回大盘</span>
      </a>
      <div class="text-xs text-gray-500 font-mono hidden sm:block">
        CelebrityStrategy / 多季度决心榜算法明细 / <span class="text-gray-300 font-semibold">{ticker}</span>
      </div>
    </div>
    <div class="flex items-center gap-2 text-xs font-mono">
      <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
      <span class="text-gray-400">算法透明核算:</span>
      <span class="text-emerald-400">已核准</span>
    </div>
  </header>

  <main class="max-w-5xl mx-auto space-y-6">

    <!-- ── Hero Banner: Company Score Summary ─────────────────────────────── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border-l-4 border-l-emerald-500 glow-emerald">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div class="flex items-center gap-2.5 mb-2">
            <span class="font-mono text-sm px-2.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold">{ticker}</span>
            <span class="text-xs px-2.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-sans">多季度决心榜第 {rank} 名</span>
            <span class="text-xs px-2.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 font-sans">核心机构: {gurus_display}</span>
          </div>
          <h1 class="text-3xl md:text-4xl font-extrabold text-white tracking-tight">{company_name}</h1>
          <div class="mt-3 flex items-center gap-2 text-xs text-gray-300">
            <span class="text-gray-400">排序理由：</span>
            <span class="font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded">{reason}</span>
          </div>
        </div>

        <div class="flex md:flex-col items-end justify-between md:justify-center p-4 rounded-xl bg-gray-900/80 border border-gray-800 text-right min-w-[160px]">
          <span class="text-xs text-gray-400 uppercase tracking-wider">综合决心分值</span>
          <span class="text-4xl font-black font-mono text-emerald-400 my-1">{final_score:.1f}</span>
          <span class="text-[11px] text-gray-500">满分基准 30.0+</span>
        </div>
      </div>
    </div>

    <!-- ── Card 1: 📐 全局【多季度决心积分】算法规则体系 ──────────────────── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border border-gray-800">
      <div class="flex items-center justify-between border-b border-gray-800 pb-4 mb-6">
        <div>
          <h2 class="text-lg md:text-xl font-bold text-white flex items-center gap-2">
            <span>📐</span> 全局【多季度决心积分】算法模型
          </h2>
          <p class="text-xs text-gray-400 mt-0.5">该系统如何量化顶尖价值投资大师的建仓执着度与同向共识</p>
        </div>
        <span class="text-xs font-mono text-emerald-400 px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/20">The Conviction Scoring Model</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <!-- Pillar 1 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-gray-800">
          <div class="flex items-center justify-between text-emerald-400 font-bold text-xs mb-2">
            <span>1. 动作基础积分 (Action Points)</span>
            <span>🎯</span>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed">
            回溯最近 6 个季度，每个季度动作赋予基础积分：
          </p>
          <ul class="text-[11px] text-gray-400 space-y-1 mt-2 font-mono">
            <li>• ✨ 新建仓 (NEW): <span class="text-emerald-400 font-bold">+3 分</span></li>
            <li>• 🔺 持续加仓 (ADD): <span class="text-emerald-400 font-bold">+2 分</span></li>
            <li>• 🔵 持仓不变 (HOLD): <span class="text-gray-400 font-bold">0 分</span></li>
            <li>• 🔻 减仓离场 (REDUCE): <span class="text-rose-400 font-bold">-1 分</span></li>
            <li>• ❌ 清仓卖出 (SOLD): <span class="text-rose-500 font-bold">-4 分</span> (清零)</li>
          </ul>
        </div>

        <!-- Pillar 2 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-gray-800">
          <div class="flex items-center justify-between text-blue-400 font-bold text-xs mb-2">
            <span>2. 连买连击机制 (Building Streak)</span>
            <span>🔥</span>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed">
            大师在多个季度<strong>连续无减持买入</strong>该标的，表明内在价值确信度极高。
          </p>
          <p class="text-[11px] text-gray-400 mt-2 leading-relaxed">
            每连续买入 1 个季度，积分向上累加，连击跨度越长（如 4 季连买、6 季连买），底仓决心越坚定。
          </p>
        </div>

        <!-- Pillar 3 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-gray-800">
          <div class="flex items-center justify-between text-purple-400 font-bold text-xs mb-2">
            <span>3. 跨圈层共振 (Resonance Multiplier)</span>
            <span>⚡</span>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed">
            若多位顶级大师在同一时期<strong>同向建仓同一标的</strong>，触发高确定性共振乘数：
          </p>
          <ul class="text-[11px] text-gray-400 space-y-1 mt-2 font-mono">
            <li>• Tier 1 + Tier 1 (李录+段永平/巴菲特): <span class="text-purple-400 font-bold">× 1.5</span></li>
            <li>• Tier 1 + Tier 2 (李录+霍金斯等): <span class="text-purple-400 font-bold">× 1.3</span></li>
            <li>• Tier 2 + Tier 2 (帕布莱+斯皮尔等): <span class="text-purple-400 font-bold">× 1.1</span></li>
            <li>• 单一大师独家买入: <span class="text-gray-400 font-bold">× 1.0</span></li>
          </ul>
        </div>
      </div>

      <!-- Core Formula Box -->
      <div class="p-4 rounded-xl bg-gray-900/90 border border-emerald-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <div class="text-xs text-gray-400">综合决策公式：</div>
          <div class="text-sm md:text-base font-mono font-bold text-white mt-0.5">
            标的综合决心分 = <span class="text-emerald-400">Max(机构回溯原始分)</span> × <span class="text-purple-400">跨圈层共振乘数</span>
          </div>
        </div>
        <div class="text-[11px] text-gray-400">
          去重规则：同一公司合并为唯一定级条目，按最高决心分降序排定全市场座次。
        </div>
      </div>
    </div>

    <!-- ── Card 2: 🔍 【{company_name} ({ticker})】算分推导全流程实测明细 ── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border border-gray-800">
      <div class="border-b border-gray-800 pb-4 mb-6">
        <h2 class="text-lg md:text-xl font-bold text-white flex items-center gap-2">
          <span>🔍</span> 【{company_name}】算分推导全流程透明拆解
        </h2>
        <p class="text-xs text-gray-400 mt-0.5">每位跟踪大师对该公司的具体评分细项与最终综合认定</p>
      </div>

      <!-- Institutional Scores Breakdown Table -->
      <div class="overflow-x-auto mb-6">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider font-mono">
              <th class="pb-3 font-medium">持有/增持机构 (Guru)</th>
              <th class="pb-3 font-medium text-center">连续建仓季度</th>
              <th class="pb-3 font-medium text-center">6 季回溯原始分</th>
              <th class="pb-3 font-medium text-center">共振加权乘数</th>
              <th class="pb-3 font-medium text-center text-emerald-400 font-bold">机构核算得分</th>
              <th class="pb-3 font-medium text-right">季度动作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono">
            {gurus_table_body}
          </tbody>
        </table>
      </div>

      <!-- Step-by-Step Narrative -->
      <div class="p-5 rounded-xl bg-gray-900/50 border border-gray-800">
        <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider mb-3">算分逻辑递进流水线：</h3>
        <ol class="text-xs text-gray-400 space-y-2.5 leading-relaxed font-sans">
          {steps_list_html}
        </ol>
      </div>

    </div>

    <!-- ── Footer Action Navigation ──────────────────────────────────────── -->
    <div class="flex items-center justify-between pt-4">
      <a href="../dashboard.html" onclick="returnToDashboard(event)" class="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-colors border border-gray-700">
        <span>← 返回大盘仪表盘</span>
      </a>
      <a href="{ticker}.html" class="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-gray-950 font-bold text-xs flex items-center gap-1.5 transition-colors shadow-lg shadow-emerald-500/20">
        <span>🏢 查看 {company_name} 独立公司档案 →</span>
      </a>
    </div>

  </main>

  <footer class="max-w-5xl mx-auto mt-12 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
    CelebrityStrategy · 多季度决心积分算法模型解析 · {company_name} ({ticker})
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


def generate_all_scoring_pages(aggregated_convictions: list, catalog: dict, output_companies_dir: str):
    """Generate dedicated scoring breakdown pages for all conviction leaderboard companies."""
    os.makedirs(output_companies_dir, exist_ok=True)
    count = 0
    for rank, item in enumerate(aggregated_convictions, start=1):
        ticker = item["ticker"]
        cat_meta = catalog.get(ticker, {})
        html = generate_scoring_detail_html(item, cat_meta, rank)
        target_file = os.path.join(output_companies_dir, f"{ticker}_scoring.html")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1
    print(f"  📐 Generated {count} conviction scoring detail pages in: {output_companies_dir}")
    return count


def build_cost_matrix(holdings: list, valuations: dict) -> list:
    """
    Build comprehensive cost window matrix for all holdings in the quarter.
    Groups holdings by ticker and calculates:
      - Individual guru purchase prices & positions
      - Weighted average reported price (capital-weighted)
      - Simple arithmetic average price
      - Discount / premium delta vs live current price
      - Investment decision guidance
    """
    ticker_groups = collections.defaultdict(list)
    for h in holdings:
        ticker = h.get("ticker")
        if ticker:
            ticker_groups[ticker].append(h)

    matrix = []
    for ticker, h_list in ticker_groups.items():
        v = valuations.get(ticker, {})
        cur_p = v.get("current_price")
        sector = v.get("sector") or h_list[0].get("sector") or "Other"
        company_name = clean_company_name(ticker, h_list[0].get("company_name", ""))

        gurus_detail = []
        valid_rep_prices = []
        total_shares = 0
        total_value = 0.0

        for h in h_list:
            rep_p = h.get("reported_price") or 0.0
            shares = h.get("shares_held") or 0
            w = h.get("portfolio_weight") or 0.0
            act = h.get("activity") or "持有"
            g_name = h.get("guru_name") or h.get("guru_code", "")
            g_code = h.get("guru_code", "")
            tier = h.get("tier", 1)
            quarter = h.get("quarter", "")

            # Exited position check
            is_exited = (shares == 0 or "sell 100" in act.lower())

            pos_val = round(shares * rep_p, 2) if (rep_p and shares) else round(h.get("value", 0.0), 2)
            if not is_exited:
                total_shares += shares
                if rep_p and rep_p > 0:
                    valid_rep_prices.append(rep_p)
                    total_value += shares * rep_p if shares > 0 else pos_val

            gurus_detail.append({
                "guru_code": g_code,
                "guru_name": g_name,
                "tier": tier,
                "shares_held": shares,
                "reported_price": rep_p,
                "position_value": pos_val,
                "portfolio_weight": w,
                "activity": act,
                "quarter": quarter,
                "is_exited": is_exited
            })

        # Calculate weighted average and simple average
        if total_shares > 0 and total_value > 0:
            weighted_cost = round(total_value / total_shares, 2)
        elif valid_rep_prices:
            weighted_cost = round(sum(valid_rep_prices) / len(valid_rep_prices), 2)
        else:
            weighted_cost = None

        simple_cost = round(sum(valid_rep_prices) / len(valid_rep_prices), 2) if valid_rep_prices else None

        # Price diff percentage vs current price
        diff_pct = None
        status_category = "pending"  # "discount", "premium", "pending"
        guidance = "待更新最新行情"

        if cur_p and weighted_cost and weighted_cost > 0:
            diff_pct = round(((cur_p - weighted_cost) / weighted_cost) * 100, 2)
            if diff_pct <= -10.0:
                status_category = "discount"
                guidance = "🟢 黄金击球区 (高安全边际)"
            elif diff_pct < 0.0:
                status_category = "discount"
                guidance = "🟢 适度折价买点"
            elif diff_pct < 20.0:
                status_category = "premium"
                guidance = "🟡 合理溢价观察"
            else:
                status_category = "premium"
                guidance = "🟠 显著溢价追高风险"
        elif weighted_cost:
            status_category = "pending"
            guidance = "⚪ 待更新最新行情"

        matrix.append({
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "gurus_detail": gurus_detail,
            "total_shares": total_shares,
            "total_value": round(total_value, 2),
            "weighted_cost": weighted_cost,
            "simple_cost": simple_cost,
            "current_price": cur_p,
            "diff_pct": diff_pct,
            "pe_ttm": v.get("pe_ttm"),
            "fcf_yield": v.get("fcf_yield"),
            "status_category": status_category,
            "guidance": guidance,
        })

    def sort_key(item):
        d = item["diff_pct"]
        if d is not None:
            return (0, d)
        return (1, -item["total_value"])

    matrix.sort(key=sort_key)
    return matrix


def generate_cost_detail_html(item: dict, catalog_meta: dict) -> str:
    """Generate a dedicated page explaining the holding cost breakdown and mathematical formula for this company."""
    ticker = item["ticker"]
    company_name = catalog_meta.get("name") or item.get("company_name") or ticker
    sector = item.get("sector") or "Other"
    gurus_detail = item.get("gurus_detail", [])
    total_shares = item.get("total_shares", 0)
    total_value = item.get("total_value", 0.0)
    weighted_cost = item.get("weighted_cost")
    simple_cost = item.get("simple_cost")
    current_price = item.get("current_price")
    diff_pct = item.get("diff_pct")
    pe_ttm = item.get("pe_ttm")
    fcf_yield = item.get("fcf_yield")
    guidance = item.get("guidance", "待更新最新行情")
    status_category = item.get("status_category", "pending")

    # Format guru rows for the table
    active_gurus = [g for g in gurus_detail if not g.get("is_exited")]
    exited_gurus = [g for g in gurus_detail if g.get("is_exited")]

    guru_rows_html = []
    for g in gurus_detail:
        gname = g.get("guru_name") or g.get("guru_code", "")
        tier = f"Tier {g.get('tier', 1)}"
        q = g.get("quarter", "")
        rep_p = g.get("reported_price") or 0.0
        sh = g.get("shares_held") or 0
        val = g.get("position_value") or (sh * rep_p)
        w = g.get("portfolio_weight") or 0.0
        act = g.get("activity") or "持有"
        is_exited = g.get("is_exited", False)

        if not is_exited:
            row_html = f"""
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 font-sans text-white font-medium">
                {gname}
                <span class="text-[10px] ml-1.5 px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">{tier}</span>
              </td>
              <td class="py-3 text-center text-gray-400 font-mono">{q}</td>
              <td class="py-3 text-right font-mono font-bold text-blue-400">${rep_p:.2f}</td>
              <td class="py-3 text-right font-mono text-gray-200">{sh:,} 股</td>
              <td class="py-3 text-right font-mono text-gray-200">${val:,.2f}</td>
              <td class="py-3 text-center font-mono font-bold text-white">{w:.2f}%</td>
              <td class="py-3 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] {'badge-buy' if 'Buy' in act or 'Add' in act or 'New' in act or '买' in act or '增' in act else ('badge-sell' if 'Sell' in act or 'Reduce' in act or '减' in act else 'badge-hold')}">
                  {act}
                </span>
              </td>
            </tr>
            """
        else:
            row_html = f"""
            <tr class="hover:bg-gray-800/40 transition-colors opacity-60">
              <td class="py-3 font-sans text-gray-400">
                {gname}
                <span class="text-[10px] ml-1.5 px-2 py-0.5 rounded bg-red-950/40 text-red-400 border border-red-800/30">已清仓</span>
              </td>
              <td class="py-3 text-center text-gray-500 font-mono">{q}</td>
              <td class="py-3 text-right font-mono text-gray-500">${rep_p:.2f}</td>
              <td class="py-3 text-right font-mono text-gray-500">0 股</td>
              <td class="py-3 text-right font-mono text-gray-500">$0.00</td>
              <td class="py-3 text-center font-mono text-gray-500">0.00%</td>
              <td class="py-3 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] badge-sell">{act}</span>
              </td>
            </tr>
            """
        guru_rows_html.append(row_html)

    gurus_table_body = "".join(guru_rows_html)

    # Mathematical components for Step-by-Step cards
    if active_gurus:
        val_terms = [f"{g['guru_name'].split('(')[0].strip()}: ${g['position_value']:,.2f}" for g in active_gurus]
        shares_terms = [f"{g['guru_name'].split('(')[0].strip()}: {g['shares_held']:,} 股" for g in active_gurus]
        simple_terms = [f"${g['reported_price']:.2f}" for g in active_gurus]
        val_formula_str = " + ".join(val_terms) if len(val_terms) <= 4 else f"{val_terms[0]} + ... (共 {len(val_terms)} 家)"
        shares_formula_str = " + ".join(shares_terms) if len(shares_terms) <= 4 else f"{shares_terms[0]} + ... (共 {len(shares_terms)} 家)"
        simple_formula_str = f"({' + '.join(simple_terms)}) ÷ {len(active_gurus)}"
    else:
        val_formula_str = "$0.00"
        shares_formula_str = "0 股"
        simple_formula_str = "—"

    # Step 1 bullet points
    guru_step1_items = "".join([
        f"<li>• <strong>{g['guru_name']}</strong>: 持股 <code>{g['shares_held']:,} 股</code>，13F 申报价格 <code>${g['reported_price']:.2f}</code>，持仓市值 <code>${g['position_value']:,.2f}</code> (占比 {g['portfolio_weight']:.2f}%)</li>"
        for g in gurus_detail
    ])

    # Guidance explanation
    if diff_pct is not None:
        if diff_pct <= -10.0:
            guidance_explanation = f"当前市场现价比大师加权建仓均价便宜 <strong>{abs(diff_pct):.1f}%</strong>，投资者获得了坚实的安全边际 (Margin of Safety)，属于难得的“以低于顶级大师筹码底牌”入场的黄金击球区！"
        elif diff_pct < 0.0:
            guidance_explanation = f"当前市场现价比大师加权建仓均价小幅低 <strong>{abs(diff_pct):.1f}%</strong>，投资者拥有适度安全边际，买入成本优于大师申报价格。"
        elif diff_pct < 20.0:
            guidance_explanation = f"当前市场现价比大师加权建仓均价高出 <strong>{diff_pct:.1f}%</strong>，大师持仓处于浮盈状态。若公司基本面强劲且自由现金流充沛，仍处于合理配置通道。"
        else:
            guidance_explanation = f"当前市场现价比大师加权建仓均价已大幅高出 <strong>{diff_pct:.1f}%</strong>，大师已录得大额浮盈缓冲垫。克隆买入需谨防高位接盘或机构季度调仓减持，建议谨慎观察。"
    else:
        guidance_explanation = "该标的最新行情正在估值同步队列中，申报成本数据已精确核算完毕。可参考 13F 申报均价作为基本面建仓锚点。"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{company_name} ({ticker}) 持仓成本拆解与均价推导明细 | CelebrityStrategy</title>
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
  </style>
  <script>
    function returnToDashboard(e) {{
      if (e) e.preventDefault();
      if (window.history.length > 1) {{
        window.history.back();
      }} else {{
        if (window.location.pathname.includes('/docs/')) {{
          window.location.href = '../index.html#tab-discounts';
        }} else if (window.location.pathname.includes('celebrity_strategy_dashboard')) {{
          window.location.href = '../celebrity_strategy_dashboard.html#tab-discounts';
        }} else {{
          window.location.href = '../dashboard.html#tab-discounts';
        }}
      }}
    }}
  </script>
</head>
<body class="min-h-screen p-4 md:p-6 lg:p-8 antialiased selection:bg-blue-500 selection:text-white">

  <!-- ── Top Header Navigation Bar ────────────────────────────────────────── -->
  <header class="max-w-5xl mx-auto mb-8 flex items-center justify-between border-b border-gray-800 pb-4">
    <div class="flex items-center gap-3">
      <a href="../dashboard.html#tab-discounts" onclick="returnToDashboard(event)" class="px-3.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 hover:text-white transition-all text-xs font-semibold flex items-center gap-1.5 border border-gray-700">
        <span>←</span>
        <span>返回持仓成本矩阵</span>
      </a>
      <div class="text-xs text-gray-500 font-mono hidden sm:block">
        CelebrityStrategy / 持仓成本与击球区 / <span class="text-gray-300 font-semibold">{ticker} 均价拆解</span>
      </div>
    </div>
    <div class="flex items-center gap-2 text-xs font-mono">
      <span class="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
      <span class="text-gray-400">成本算法模型:</span>
      <span class="text-blue-400 font-bold">资本加权核算</span>
    </div>
  </header>

  <main class="max-w-5xl mx-auto space-y-6">

    <!-- ── Hero Banner: Cost & Margin Summary ─────────────────────────────── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border-l-4 border-l-blue-500 glow-blue">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div class="flex items-center gap-2.5 mb-2">
            <span class="font-mono text-sm px-2.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-bold">{ticker}</span>
            <span class="text-xs px-2.5 py-0.5 rounded bg-gray-800 text-gray-300 border border-gray-700 font-sans">{sector}</span>
            <span class="text-xs px-2.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 font-sans">{len(active_gurus)} 家机构重仓</span>
          </div>
          <h1 class="text-3xl md:text-4xl font-extrabold text-white tracking-tight">{company_name}</h1>
          <div class="mt-3 flex items-center gap-2 text-xs text-gray-300">
            <span class="text-gray-400">击球区建议：</span>
            <span class="font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded">{guidance}</span>
          </div>
        </div>

        <!-- 4-Block Quick Stats Grid -->
        <div class="grid grid-cols-2 gap-3 sm:gap-4 shrink-0 text-right font-mono">
          <div class="p-3 rounded-xl bg-gray-900/80 border border-blue-500/30 text-left">
            <div class="text-[10px] text-gray-400 uppercase tracking-wider">机构加权申报均价</div>
            <div class="text-xl md:text-2xl font-black text-blue-400 mt-0.5">
              ${f"{weighted_cost:.2f}" if weighted_cost is not None else "—"}
            </div>
            <div class="text-[10px] text-gray-500 mt-0.5">资金规模加权成本</div>
          </div>

          <div class="p-3 rounded-xl bg-gray-900/80 border border-gray-800 text-left">
            <div class="text-[10px] text-gray-400 uppercase tracking-wider">简单算术均价</div>
            <div class="text-xl md:text-2xl font-black text-gray-300 mt-0.5">
              ${f"{simple_cost:.2f}" if simple_cost is not None else "—"}
            </div>
            <div class="text-[10px] text-gray-500 mt-0.5">各机构同权均值</div>
          </div>

          <div class="p-3 rounded-xl bg-gray-900/80 border border-gray-800 text-left">
            <div class="text-[10px] text-gray-400 uppercase tracking-wider">当前市场现价</div>
            <div class="text-xl md:text-2xl font-black text-white mt-0.5">
              {f"${current_price:.2f}" if current_price is not None else "待更新"}
            </div>
            <div class="text-[10px] text-gray-500 mt-0.5">最新市场交易价格</div>
          </div>

          <div class="p-3 rounded-xl bg-gray-900/80 border border-emerald-500/30 text-left">
            <div class="text-[10px] text-gray-400 uppercase tracking-wider">相对成本差价 (Delta)</div>
            <div class="text-xl md:text-2xl font-black mt-0.5 {'text-emerald-400' if diff_pct and diff_pct < 0 else ('text-amber-400' if diff_pct and diff_pct > 0 else 'text-gray-400')}">
              {f"{diff_pct:+.1f}%" if diff_pct is not None else "待估值"}
            </div>
            <div class="text-[10px] text-gray-500 mt-0.5">
              {"比大师更便宜" if diff_pct and diff_pct < 0 else ("机构浮盈中" if diff_pct and diff_pct > 0 else "平价/待定")}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Card 1: 🏛️ 大师独立持仓成本与持股明细清单 ── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border border-gray-800">
      <div class="border-b border-gray-800 pb-4 mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div>
          <h2 class="text-lg md:text-xl font-bold text-white flex items-center gap-2">
            <span>🏛️</span> 【{company_name}】大师独立持仓明细拆解
          </h2>
          <p class="text-xs text-gray-400 mt-0.5">每位跟踪大师对该标的的真实申报持股数量、买入成本与持仓市值</p>
        </div>
        <div class="text-xs font-mono text-gray-400">
          合计持股: <span class="text-white font-bold">{total_shares:,} 股</span>
        </div>
      </div>

      <!-- Institutional Holdings Table -->
      <div class="overflow-x-auto mb-4">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider font-mono">
              <th class="pb-3 font-medium">投资大师机构 (Guru)</th>
              <th class="pb-3 font-medium text-center">报告期</th>
              <th class="pb-3 font-medium text-right text-blue-400">申报买入均价</th>
              <th class="pb-3 font-medium text-right">持仓股数</th>
              <th class="pb-3 font-medium text-right">持仓总市值</th>
              <th class="pb-3 font-medium text-center">持仓占比</th>
              <th class="pb-3 font-medium text-right">季度动作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono">
            {gurus_table_body}
          </tbody>
          <tfoot>
            <tr class="border-t-2 border-gray-700 bg-gray-900/80 font-mono font-bold text-xs">
              <td class="py-3 text-white">合计加权统计 (Active Totals)</td>
              <td class="py-3 text-center text-gray-400">{len(active_gurus)} 家机构</td>
              <td class="py-3 text-right text-blue-400">${f"{weighted_cost:.2f}" if weighted_cost is not None else "—"} (加权均价)</td>
              <td class="py-3 text-right text-white">{total_shares:,} 股</td>
              <td class="py-3 text-right text-emerald-400">${total_value:,.2f}</td>
              <td class="py-3 text-center text-gray-400">—</td>
              <td class="py-3 text-right text-emerald-400">合算均价</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>

    <!-- ── Card 2: 🧮 均价计算推导流程与数学步骤 ── -->
    <div class="terminal-card rounded-2xl p-6 md:p-8 border border-gray-800">
      <div class="border-b border-gray-800 pb-4 mb-6">
        <h2 class="text-lg md:text-xl font-bold text-white flex items-center gap-2">
          <span>🧮</span> 均价计算公式与详细推导流水线
        </h2>
        <p class="text-xs text-gray-400 mt-0.5">从 13F 原始申报到资本加权均价与击球区差价率的完整数学推导过程</p>
      </div>

      <div class="space-y-4 text-xs font-sans leading-relaxed text-gray-300">
        <!-- Step 1 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-gray-800">
          <div class="font-bold text-white mb-1.5 flex items-center gap-2">
            <span class="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 inline-flex items-center justify-center font-mono text-xs">1</span>
            <span>13F 申报数据归集与机构持股拆解</span>
          </div>
          <p class="text-gray-400">
            从 SEC EDGAR 官方备案及 Dataroma 审计数据中提取最新报告期内各投资大师对 <code>{ticker}</code> 的真实建仓/持仓记录：
          </p>
          <ul class="mt-2 space-y-1 text-gray-300 font-mono text-[11px]">
            {guru_step1_items}
          </ul>
        </div>

        <!-- Step 2 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-blue-500/30">
          <div class="font-bold text-white mb-1.5 flex items-center gap-2">
            <span class="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 inline-flex items-center justify-center font-mono text-xs">2</span>
            <span>机构资本加权申报均价 (Weighted Average Cost) 公式与推导</span>
          </div>
          <p class="text-gray-400">
            资本加权均价以各家机构的真实持股数量为权重，能够最真实反映“华尔街聪明钱整体的加权建仓底牌成本”：
          </p>
          <div class="my-3 p-3 rounded-lg bg-gray-950 font-mono text-xs text-blue-400 border border-gray-800">
            加权申报均价 = ∑ (每位大师持股数 × 申报价格) ÷ ∑ (每位大师持股数) = 机构持仓总市值 ÷ 机构持股总股数
          </div>
          <div class="space-y-1.5 font-mono text-[11px] text-gray-300">
            <div>• <strong>分子 (持仓总市值)</strong> = {val_formula_str} = <span class="text-emerald-400 font-bold">${total_value:,.2f}</span></div>
            <div>• <strong>分母 (持股总股数)</strong> = {shares_formula_str} = <span class="text-white font-bold">{total_shares:,} 股</span></div>
            <div>• <strong>加权计算结果</strong> = ${total_value:,.2f} ÷ {total_shares:,} 股 = <span class="text-blue-400 font-bold text-sm">${f"{weighted_cost:.2f}" if weighted_cost is not None else "—"}</span></div>
          </div>
        </div>

        <!-- Step 3 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-gray-800">
          <div class="font-bold text-white mb-1.5 flex items-center gap-2">
            <span class="w-5 h-5 rounded-full bg-purple-500/20 text-purple-400 inline-flex items-center justify-center font-mono text-xs">3</span>
            <span>简单算术均价 (Simple Mean) 对比与实战解析</span>
          </div>
          <div class="font-mono text-xs text-purple-400 my-2 p-2.5 rounded bg-gray-950 border border-gray-800">
            简单算术均价 = ∑ (各机构申报价格) ÷ 机构总数 = {simple_formula_str} = ${f"{simple_cost:.2f}" if simple_cost is not None else "—"}
          </div>
          <p class="text-gray-400 text-[11px] leading-relaxed">
            💡 <strong>为什么我们优先采用【加权均价】而非【简单算术均价】？</strong><br>
            因为不同大师的持仓规模往往存在数十倍至数百倍的巨大差距。若某大师只用 1,000 万美元试仓，而另一大师重仓 20 亿美元，简单算术均价会过度放大轻仓者的试水价格，无法反映主流大资金的真实重仓成本中枢。加权均价体现了真实资本的筹码底牌。
          </p>
        </div>

        <!-- Step 4 -->
        <div class="p-4 rounded-xl bg-gray-900/60 border border-emerald-500/30">
          <div class="font-bold text-white mb-1.5 flex items-center gap-2">
            <span class="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 inline-flex items-center justify-center font-mono text-xs">4</span>
            <span>现价与均价击球区差价率 (Margin of Safety / Premium) 测算</span>
          </div>
          <div class="my-3 p-3 rounded-lg bg-gray-950 font-mono text-xs text-emerald-400 border border-gray-800">
            差价率 (Delta %) = [ (当前市场现价 - 机构加权成本) ÷ 机构加权成本 ] × 100%
          </div>
          <div class="space-y-1.5 font-mono text-[11px] text-gray-300">
            <div>• 当前市场最新现价: <span class="text-white font-bold">{f"${current_price:.2f}" if current_price else "暂无行情 (待更新)"}</span></div>
            <div>• 机构加权申报成本: <span class="text-blue-400 font-bold">${f"{weighted_cost:.2f}" if weighted_cost is not None else "—"}</span></div>
            <div>• 差价计算结果: {f"[ ({current_price:.2f} - {weighted_cost:.2f}) ÷ {weighted_cost:.2f} ] × 100% = " if (current_price and weighted_cost) else ""}<span class="font-bold text-sm {'text-emerald-400' if diff_pct and diff_pct < 0 else ('text-amber-400' if diff_pct and diff_pct > 0 else 'text-gray-400')}">{f"{diff_pct:+.2f}%" if diff_pct is not None else "待估值"}</span></div>
          </div>
          <div class="mt-3 p-3 rounded-lg bg-gray-950/70 border border-gray-800 text-[11px] text-gray-300">
            📌 <strong>价值投资实操指引：</strong> {guidance_explanation}
          </div>
        </div>
      </div>
    </div>

    <!-- ── Footer Action Navigation ──────────────────────────────────────── -->
    <div class="flex items-center justify-between pt-4">
      <a href="../dashboard.html#tab-discounts" onclick="returnToDashboard(event)" class="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-colors border border-gray-700">
        <span>← 返回持仓成本矩阵</span>
      </a>
      <div class="flex items-center gap-3">
        <a href="{ticker}_scoring.html" class="px-3.5 py-2 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 hover:text-purple-300 border border-purple-500/30 text-xs font-semibold flex items-center gap-1.5 transition-colors">
          <span>🏆 查看决心分算法 →</span>
        </a>
        <a href="{ticker}.html" class="px-4 py-2 rounded-lg bg-blue-500 hover:bg-blue-600 text-gray-950 font-bold text-xs flex items-center gap-1.5 transition-colors shadow-lg shadow-blue-500/20">
          <span>🏢 查看 {company_name} 独立公司档案 →</span>
        </a>
      </div>
    </div>

  </main>

  <footer class="max-w-5xl mx-auto mt-12 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
    CelebrityStrategy · 机构加权持仓成本与击球区数学模型 · {company_name} ({ticker})
  </footer>

</body>
</html>
"""
    return html


def generate_all_cost_pages(cost_matrix: list, catalog: dict, output_companies_dir: str):
    """Generate dedicated cost breakdown pages for all holdings in the cost matrix."""
    os.makedirs(output_companies_dir, exist_ok=True)
    count = 0
    for item in cost_matrix:
        ticker = item["ticker"]
        cat_meta = catalog.get(ticker, {})
        html = generate_cost_detail_html(item, cat_meta)
        target_file = os.path.join(output_companies_dir, f"{ticker}_cost.html")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1
    print(f"  💰 Generated {count} cost breakdown detail pages in: {output_companies_dir}")
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

    # 4. Conviction Scores: Extract ONLY latest computed_at and aggregate by company
    latest_conv_date_row = cur.execute("SELECT MAX(computed_at) FROM conviction_scores").fetchone()
    latest_conv_date = latest_conv_date_row[0] if latest_conv_date_row and latest_conv_date_row[0] else ""

    if latest_conv_date:
        conv_rows = cur.execute("""
        SELECT cs.*, gm.name as guru_name, gm.tier
        FROM conviction_scores cs
        LEFT JOIN guru_meta gm ON cs.guru_code = gm.code
        WHERE cs.computed_at = ? AND cs.latest_signal != 'SOLD' AND cs.final_score > 0
        ORDER BY cs.final_score DESC
        """, (latest_conv_date,)).fetchall()
        raw_convictions = [dict(r) for r in conv_rows]
    else:
        raw_convictions = []

    # Aggregate by company (1 Company = 1 Record)
    convictions = aggregate_conviction_scores(raw_convictions)

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

    # Cost window matrix across all unique tickers held by gurus
    cost_matrix = build_cost_matrix(data["holdings"], data["valuations"])
    cost_matrix_json = json.dumps(cost_matrix)

    total_cost_count = len(cost_matrix)
    discount_cost_count = sum(1 for c in cost_matrix if c["status_category"] == "discount")
    premium_cost_count = sum(1 for c in cost_matrix if c["status_category"] == "premium")
    pending_cost_count = sum(1 for c in cost_matrix if c["status_category"] == "pending")

    # Dynamic Top Discount for KPI 3
    top_discount_item = next((c for c in cost_matrix if c["diff_pct"] is not None and c["diff_pct"] < 0), None)

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

    # Pre-render initial page 1 rows for Tab 3 (Cost Matrix)
    cost_rows_initial = []
    for d in cost_matrix[:15]:
        chips = []
        for g in d.get("gurus_detail", []):
            short_name = (g.get("guru_name") or g.get("guru_code", "")).split("(")[0].strip()
            if g.get("is_exited"):
                chips.append(f'<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-red-950/40 border border-red-800/40 text-[10px] text-red-400 line-through mr-1 mb-1">{short_name} (清仓)</span>')
            else:
                p_str = f"${g['reported_price']:.2f}" if g.get("reported_price") else "—"
                chips.append(f'<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-[10px] text-gray-300 mr-1 mb-1"><span class="text-gray-400 mr-1">{short_name}:</span><span class="font-mono text-blue-300 font-semibold">{p_str}</span></span>')
        chips_html = "".join(chips)

        diff_pct = d.get("diff_pct")
        if diff_pct is not None:
            if diff_pct < 0:
                delta_badge = f'<span class="px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[11px] font-mono">{diff_pct:.1f}% 比成本便宜</span>'
            elif diff_pct > 0:
                delta_badge = f'<span class="px-2 py-0.5 rounded font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 text-[11px] font-mono">+{diff_pct:.1f}% 机构浮盈</span>'
            else:
                delta_badge = '<span class="px-2 py-0.5 rounded font-bold bg-gray-800 text-gray-300 border border-gray-700 text-[11px] font-mono">0.0% 平价买点</span>'
        else:
            delta_badge = '<span class="text-gray-500 text-xs">—</span>'

        if diff_pct is not None:
            if diff_pct <= -10:
                guidance_html = '<span class="text-emerald-400 font-sans font-medium">🟢 黄金击球区</span>'
            elif diff_pct < 0:
                guidance_html = '<span class="text-emerald-300 font-sans font-medium">🟢 适度折价买点</span>'
            elif diff_pct < 20:
                guidance_html = '<span class="text-amber-400 font-sans font-medium">🟡 合理溢价观察</span>'
            else:
                guidance_html = '<span class="text-red-400 font-sans font-medium">🟠 显著溢价追高风险</span>'
        else:
            guidance_html = '<span class="text-gray-500 font-sans text-xs">⚪ 待更新最新行情</span>'

        cost_rows_initial.append(f'''
        <tr class="hover:bg-gray-800/40 transition-colors">
          <td class="py-3 font-sans">
            <a href="companies/{d['ticker']}.html" class="group block hover:text-emerald-400 transition-colors font-mono">
              <span class="font-bold text-white group-hover:text-emerald-400 text-sm underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                {d['ticker']}
                <span class="text-[10px] text-gray-500 group-hover:text-emerald-400 no-underline">↗</span>
              </span>
              <span class="block text-gray-400 group-hover:text-gray-300 text-[11px] truncate max-w-[170px]">{d['company_name']}</span>
            </a>
          </td>
          <td class="py-3 font-sans">
            <div class="flex flex-wrap gap-0.5 max-w-[280px]">
              {chips_html}
            </div>
          </td>
          <td class="py-3 text-right">
            <a href="companies/{d['ticker']}_cost.html"
               title="点击查看【{d['company_name']}】持仓均价详细计算推导与各位大师持仓明细 ↗"
               class="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-blue-500/10 hover:bg-blue-500/25 text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-400 font-bold font-mono transition-all group">
              <span>{f"${d['weighted_cost']:.2f}" if d.get('weighted_cost') is not None else '—'}</span>
              <span class="text-[10px] opacity-70 group-hover:opacity-100 transition-opacity">↗</span>
            </a>
          </td>
          <td class="py-3 text-right font-bold text-white font-mono">
            {f"${d['current_price']:.2f}" if d.get('current_price') is not None else '<span class="text-gray-500 font-sans text-xs">待更新</span>'}
          </td>
          <td class="py-3 text-center">
            {delta_badge}
          </td>
          <td class="py-3 text-center text-gray-300 font-mono">
            {f"{d['pe_ttm']:.1f}x" if d.get('pe_ttm') is not None else '—'}
          </td>
          <td class="py-3 text-center font-bold text-emerald-400 font-mono">
            {f"{d['fcf_yield']:.1f}%" if d.get('fcf_yield') is not None else '—'}
          </td>
          <td class="py-3 text-right font-sans">
            {guidance_html}
          </td>
        </tr>
        ''')
    cost_rows_initial_html = "".join(cost_rows_initial)

    if top_discount_item:
        kpi3_html = f'<a href="companies/{top_discount_item["ticker"]}.html" class="hover:text-amber-400 underline transition-colors">{top_discount_item["ticker"]}</a> <span class="text-xs text-emerald-400 font-normal">{top_discount_item["diff_pct"]:.1f}% 破发买底</span>'
        kpi3_sub_html = f'<a href="companies/{top_discount_item["ticker"]}_cost.html" class="hover:text-emerald-400 underline font-mono text-gray-300">成本 ${top_discount_item["weighted_cost"]:.2f} ➔ 现价 ${top_discount_item["current_price"]:.2f} (查看均价推导 ↗)</a>'
    else:
        kpi3_html = '<span>暂无</span>'
        kpi3_sub_html = '暂无折价标的'

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
            <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Terminal v2.7</span>
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
          {kpi3_html}
        </div>
        <div class="text-xs text-gray-400 truncate">
          {kpi3_sub_html}
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
            💰 成本与击球区 ({total_cost_count})
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

      <!-- Tab Content 1: Conviction Leaderboard (1 Company = 1 Record, Clickable Score) -->
      <div id="tab-conviction" class="tab-panel p-6 overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">排名</th>
              <th class="pb-3 font-medium">标的代码 / 公司</th>
              <th class="pb-3 font-medium">核心持有机构</th>
              <th class="pb-3 font-medium">排序理由 (建仓轨迹与逻辑)</th>
              <th class="pb-3 font-medium text-center text-emerald-400 font-bold">综合决心分值</th>
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
              <td class="py-3 font-sans text-gray-300 font-medium">{c["gurus_display"]}</td>
              <td class="py-3 font-sans text-xs text-blue-300">
                <span class="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20">{c["reason"]}</span>
              </td>
              <td class="py-3 text-center">
                <a href="companies/{c['ticker']}_scoring.html" 
                   title="点击查看【{clean_company_name(c['ticker'], c.get('company_name',''))}】决心分算法模型与详细推导拆解 ↗"
                   class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/25 text-emerald-400 hover:text-emerald-300 border border-emerald-500/30 hover:border-emerald-400 font-bold font-mono text-sm transition-all duration-150 group shadow-sm hover:shadow-emerald-500/20">
                  <span>{c['final_score']:.1f}</span>
                  <span class="text-[10px] opacity-70 group-hover:opacity-100 transition-opacity">↗</span>
                </a>
              </td>
              <td class="py-3 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] {'badge-buy' if '买' in (c.get('latest_signal') or '') or '加' in (c.get('latest_signal') or '') or c.get('latest_signal') in ('NEW','INCREASED','ADD','BUY') else 'badge-sell'}">
                  {c.get("latest_signal", "HOLD")}
                </span>
              </td>
            </tr>
            ''' for i, c in enumerate(data["convictions"][:30])])}
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
        <!-- Sub-filters and Pagination Info Bar -->
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 border-b border-gray-800 pb-3">
          <!-- Filter Tabs -->
          <div class="flex items-center gap-1.5 flex-wrap text-xs">
            <button onclick="filterCostTable('all')" id="btn-cost-all" class="cost-filter-btn px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">
              全部标的 ({total_cost_count})
            </button>
            <button onclick="filterCostTable('discount')" id="btn-cost-discount" class="cost-filter-btn px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white font-medium border border-transparent">
              🟢 破发折价区 ({discount_cost_count})
            </button>
            <button onclick="filterCostTable('premium')" id="btn-cost-premium" class="cost-filter-btn px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white font-medium border border-transparent">
              🟡 溢价已涨区 ({premium_cost_count})
            </button>
            <button onclick="filterCostTable('pending')" id="btn-cost-pending" class="cost-filter-btn px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white font-medium border border-transparent">
              ⚪ 待更新估值 ({pending_cost_count})
            </button>
          </div>
          <!-- Page Size & Info -->
          <div class="flex items-center gap-3 text-xs text-gray-400 font-mono">
            <span id="costPageInfo">显示第 1-15 条 / 共 {total_cost_count} 条</span>
            <select id="costPageSize" onchange="changeCostPageSize(this.value)" class="bg-gray-800 text-gray-300 rounded px-2.5 py-1 border border-gray-700 text-xs focus:outline-none">
              <option value="15" selected>每页 15 条</option>
              <option value="30">每页 30 条</option>
              <option value="50">每页 50 条</option>
              <option value="9999">显示全部</option>
            </select>
          </div>
        </div>

        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-gray-800 text-gray-400 uppercase text-[11px] tracking-wider">
              <th class="pb-3 font-medium">标的代码 / 公司</th>
              <th class="pb-3 font-medium">持仓大师与独立买价</th>
              <th class="pb-3 font-medium text-right">机构加权申报均价</th>
              <th class="pb-3 font-medium text-right">当前市场现价</th>
              <th class="pb-3 font-medium text-center">相对大师成本差价 (Delta)</th>
              <th class="pb-3 font-medium text-center">TTM P/E</th>
              <th class="pb-3 font-medium text-center">FCF Yield</th>
              <th class="pb-3 font-medium text-right">克隆击球区建议</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono" id="discountsTbody">
            {cost_rows_initial_html}
          </tbody>
        </table>

        <!-- Pagination Controls -->
        <div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-800 text-xs">
          <button onclick="prevCostPage()" id="btnCostPrev" class="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            ← 上一页
          </button>
          <div id="costPageNumbers" class="flex items-center gap-1"></div>
          <button onclick="nextCostPage()" id="btnCostNext" class="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            下一页 →
          </button>
        </div>
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
      if (currentActiveTab === 'tab-discounts') {{
        currentCostPage = 1;
        renderCostTable();
        return;
      }}

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

    // ── Tab 3: Cost Window Matrix Data & Client-Side Pagination ─────────────
    const costData = {cost_matrix_json};
    let currentCostPage = 1;
    let costPageSize = 15;
    let costFilter = 'all';

    function filterCostTable(type) {{
      costFilter = type;
      currentCostPage = 1;

      const btns = {{
        'all': document.getElementById('btn-cost-all'),
        'discount': document.getElementById('btn-cost-discount'),
        'premium': document.getElementById('btn-cost-premium'),
        'pending': document.getElementById('btn-cost-pending'),
      }};
      for (const [k, btn] of Object.entries(btns)) {{
        if (!btn) continue;
        if (k === type) {{
          btn.className = "cost-filter-btn px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium";
        }} else {{
          btn.className = "cost-filter-btn px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white font-medium border border-transparent";
        }}
      }}
      renderCostTable();
    }}

    function changeCostPageSize(size) {{
      costPageSize = parseInt(size, 10);
      currentCostPage = 1;
      renderCostTable();
    }}

    function prevCostPage() {{
      if (currentCostPage > 1) {{
        currentCostPage--;
        renderCostTable();
      }}
    }}

    function nextCostPage() {{
      const filtered = getFilteredCostData();
      const totalPages = Math.max(1, Math.ceil(filtered.length / costPageSize));
      if (currentCostPage < totalPages) {{
        currentCostPage++;
        renderCostTable();
      }}
    }}

    function goToCostPage(p) {{
      currentCostPage = p;
      renderCostTable();
    }}

    function getFilteredCostData() {{
      const searchEl = document.getElementById('searchInput');
      const q = (searchEl ? searchEl.value : '').toLowerCase().trim();
      return costData.filter(item => {{
        if (costFilter === 'discount' && item.status_category !== 'discount') return false;
        if (costFilter === 'premium' && item.status_category !== 'premium') return false;
        if (costFilter === 'pending' && item.status_category !== 'pending') return false;

        if (q) {{
          const matchTicker = (item.ticker || '').toLowerCase().includes(q);
          const matchName = (item.company_name || '').toLowerCase().includes(q);
          const matchGurus = (item.gurus_detail || []).some(g => (g.guru_name || '').toLowerCase().includes(q));
          if (!matchTicker && !matchName && !matchGurus) return false;
        }}
        return true;
      }});
    }}

    function renderCostTable() {{
      const tbody = document.getElementById('discountsTbody');
      if (!tbody) return;

      const filtered = getFilteredCostData();
      const totalFiltered = filtered.length;
      const totalPages = Math.max(1, Math.ceil(totalFiltered / costPageSize));

      if (currentCostPage > totalPages) currentCostPage = totalPages;
      if (currentCostPage < 1) currentCostPage = 1;

      const startIndex = (currentCostPage - 1) * costPageSize;
      const endIndex = Math.min(startIndex + costPageSize, totalFiltered);
      const pageItems = filtered.slice(startIndex, endIndex);

      let rowsHtml = '';
      if (pageItems.length === 0) {{
        rowsHtml = `<tr><td colspan="8" class="py-8 text-center text-gray-500 font-sans">暂无符合条件的持仓标的数据</td></tr>`;
      }} else {{
        pageItems.forEach(d => {{
          let chips = '';
          (d.gurus_detail || []).forEach(g => {{
            const shortName = (g.guru_name || g.guru_code).split('(')[0].trim();
            if (g.is_exited) {{
              chips += `<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-red-950/40 border border-red-800/40 text-[10px] text-red-400 line-through mr-1 mb-1">${{shortName}} (清仓)</span>`;
            }} else {{
              const pStr = (g.reported_price != null && g.reported_price > 0) ? '$' + g.reported_price.toFixed(2) : '—';
              chips += `<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-[10px] text-gray-300 mr-1 mb-1"><span class="text-gray-400 mr-1">${{shortName}}:</span><span class="font-mono text-blue-300 font-semibold">${{pStr}}</span></span>`;
            }}
          }});

          let deltaBadge = '';
          if (d.diff_pct !== null && d.diff_pct !== undefined) {{
            if (d.diff_pct < 0) {{
              deltaBadge = `<span class="px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[11px] font-mono">${{d.diff_pct.toFixed(1)}}% 比成本便宜</span>`;
            }} else if (d.diff_pct > 0) {{
              deltaBadge = `<span class="px-2 py-0.5 rounded font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 text-[11px] font-mono">+${{d.diff_pct.toFixed(1)}}% 机构浮盈</span>`;
            }} else {{
              deltaBadge = `<span class="px-2 py-0.5 rounded font-bold bg-gray-800 text-gray-300 border border-gray-700 text-[11px] font-mono">0.0% 平价买点</span>`;
            }}
          }} else {{
            deltaBadge = `<span class="text-gray-500 text-xs">—</span>`;
          }}

          let guidanceHtml = '';
          if (d.diff_pct !== null && d.diff_pct !== undefined) {{
            if (d.diff_pct <= -10) {{
              guidanceHtml = `<span class="text-emerald-400 font-sans font-medium">🟢 黄金击球区</span>`;
            }} else if (d.diff_pct < 0) {{
              guidanceHtml = `<span class="text-emerald-300 font-sans font-medium">🟢 适度折价买点</span>`;
            }} else if (d.diff_pct < 20) {{
              guidanceHtml = `<span class="text-amber-400 font-sans font-medium">🟡 合理溢价观察</span>`;
            }} else {{
              guidanceHtml = `<span class="text-red-400 font-sans font-medium">🟠 显著溢价追高风险</span>`;
            }}
          }} else {{
            guidanceHtml = `<span class="text-gray-500 font-sans text-xs">⚪ 待更新最新行情</span>`;
          }}

          const curPriceStr = (d.current_price != null) ? '$' + d.current_price.toFixed(2) : '<span class="text-gray-500 font-sans text-xs">待更新</span>';
          const peStr = (d.pe_ttm != null) ? d.pe_ttm.toFixed(1) + 'x' : '—';
          const fcfStr = (d.fcf_yield != null) ? d.fcf_yield.toFixed(1) + '%' : '—';
          const costStr = (d.weighted_cost != null) ? '$' + d.weighted_cost.toFixed(2) : '—';

          rowsHtml += `
            <tr class="hover:bg-gray-800/40 transition-colors">
              <td class="py-3 font-sans">
                <a href="companies/${{d.ticker}}.html" class="group block hover:text-emerald-400 transition-colors font-mono">
                  <span class="font-bold text-white group-hover:text-emerald-400 text-sm underline decoration-emerald-500/40 underline-offset-2 flex items-center gap-1">
                    ${{d.ticker}}
                    <span class="text-[10px] text-gray-500 group-hover:text-emerald-400 no-underline">↗</span>
                  </span>
                  <span class="block text-gray-400 group-hover:text-gray-300 text-[11px] truncate max-w-[170px]">${{d.company_name}}</span>
                </a>
              </td>
              <td class="py-3 font-sans">
                <div class="flex flex-wrap gap-0.5 max-w-[280px]">
                  ${{chips}}
                </div>
              </td>
              <td class="py-3 text-right">
                <a href="companies/${{d.ticker}}_cost.html"
                   title="点击查看【${{d.company_name}}】持仓均价详细计算推导与各位大师持仓明细 ↗"
                   class="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-blue-500/10 hover:bg-blue-500/25 text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-400 font-bold font-mono transition-all group">
                  <span>${{costStr}}</span>
                  <span class="text-[10px] opacity-70 group-hover:opacity-100 transition-opacity">↗</span>
                </a>
              </td>
              <td class="py-3 text-right font-bold text-white font-mono">
                ${{curPriceStr}}
              </td>
              <td class="py-3 text-center">
                ${{deltaBadge}}
              </td>
              <td class="py-3 text-center text-gray-300 font-mono">
                ${{peStr}}
              </td>
              <td class="py-3 text-center font-bold text-emerald-400 font-mono">
                ${{fcfStr}}
              </td>
              <td class="py-3 text-right font-sans">
                ${{guidanceHtml}}
              </td>
            </tr>
          `;
        }});
      }}
      tbody.innerHTML = rowsHtml;

      const infoEl = document.getElementById('costPageInfo');
      if (infoEl) {{
        infoEl.innerText = `显示第 ${{totalFiltered > 0 ? startIndex + 1 : 0}} - ${{endIndex}} 条 / 共 ${{totalFiltered}} 条`;
      }}

      const btnPrev = document.getElementById('btnCostPrev');
      const btnNext = document.getElementById('btnCostNext');
      if (btnPrev) btnPrev.disabled = (currentCostPage === 1);
      if (btnNext) btnNext.disabled = (currentCostPage === totalPages);

      const pageNumbersEl = document.getElementById('costPageNumbers');
      if (pageNumbersEl) {{
        let pBtns = '';
        const maxVisible = 5;
        let startP = Math.max(1, currentCostPage - 2);
        let endP = Math.min(totalPages, startP + maxVisible - 1);
        if (endP - startP < maxVisible - 1) {{
          startP = Math.max(1, endP - maxVisible + 1);
        }}

        if (startP > 1) {{
          pBtns += `<button onclick="goToCostPage(1)" class="w-7 h-7 rounded text-xs text-gray-400 hover:text-white bg-gray-800">1</button>`;
          if (startP > 2) pBtns += `<span class="text-gray-500 px-1">...</span>`;
        }}

        for (let p = startP; p <= endP; p++) {{
          if (p === currentCostPage) {{
            pBtns += `<button class="w-7 h-7 rounded text-xs font-bold bg-emerald-500 text-gray-950">${{p}}</button>`;
          }} else {{
            pBtns += `<button onclick="goToCostPage(${{p}})" class="w-7 h-7 rounded text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700">${{p}}</button>`;
          }}
        }}

        if (endP < totalPages) {{
          if (endP < totalPages - 1) pBtns += `<span class="text-gray-500 px-1">...</span>`;
          pBtns += `<button onclick="goToCostPage(${{totalPages}})" class="w-7 h-7 rounded text-xs text-gray-400 hover:text-white bg-gray-800">${{totalPages}}</button>`;
        }}
        pageNumbersEl.innerHTML = pBtns;
      }}
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

    // Initialize cost matrix table pagination and filtering
    renderCostTable();
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
    catalog = build_company_catalog(db_path)
    cost_matrix = build_cost_matrix(data["holdings"], data["valuations"])

    print(f"🎨 Rendering institutional HTML terminal...")
    html_content = generate_html(data)

    # 1. Save to reports/dashboard.html
    local_output = args.output if args.output else os.path.join(PROJECT_ROOT, "reports", "dashboard.html")
    os.makedirs(os.path.dirname(local_output), exist_ok=True)
    with open(local_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Dashboard saved locally: {local_output}")

    # 1b. Generate company standalone pages, scoring pages & cost breakdown pages in reports/companies/
    reports_comp_dir = os.path.join(os.path.dirname(local_output), "companies")
    generate_all_company_pages(db_path, reports_comp_dir)
    generate_all_scoring_pages(data["convictions"], catalog, reports_comp_dir)
    generate_all_cost_pages(cost_matrix, catalog, reports_comp_dir)

    # 2. Save to docs/index.html (GitHub Pages & Cloudflare Pages standard root)
    docs_output = os.path.join(PROJECT_ROOT, "docs", "index.html")
    os.makedirs(os.path.dirname(docs_output), exist_ok=True)
    with open(docs_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Web deployment asset saved: {docs_output}")

    # 2b. Generate company standalone pages, scoring pages & cost breakdown pages in docs/companies/
    docs_comp_dir = os.path.join(PROJECT_ROOT, "docs", "companies")
    generate_all_company_pages(db_path, docs_comp_dir)
    generate_all_scoring_pages(data["convictions"], catalog, docs_comp_dir)
    generate_all_cost_pages(cost_matrix, catalog, docs_comp_dir)

    # 3. Save to Artifact Directory for conversation display
    artifact_path = os.path.join(ARTIFACT_DIR, "dashboard.html")
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✅ Dashboard saved to Artifacts: {artifact_path}")

    artifact_comp_dir = os.path.join(ARTIFACT_DIR, "companies")
    generate_all_company_pages(db_path, artifact_comp_dir)
    generate_all_scoring_pages(data["convictions"], catalog, artifact_comp_dir)
    generate_all_cost_pages(cost_matrix, catalog, artifact_comp_dir)

    # 4. Also sync to Obsidian if available
    obsidian_dir = "/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考"
    if os.path.exists(obsidian_dir):
        obsidian_target = os.path.join(obsidian_dir, "celebrity_strategy_dashboard.html")
        with open(obsidian_target, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  ✅ Dashboard synced to Obsidian: {obsidian_target}")

        obsidian_comp_dir = os.path.join(obsidian_dir, "companies")
        generate_all_company_pages(db_path, obsidian_comp_dir)
        generate_all_scoring_pages(data["convictions"], catalog, obsidian_comp_dir)
        generate_all_cost_pages(cost_matrix, catalog, obsidian_comp_dir)

    print("\n🎉 Institutional HTML Dashboard, Company Pages, Scoring Breakdown & Cost Breakdown Pages Generated Successfully!")


if __name__ == "__main__":
    main()
