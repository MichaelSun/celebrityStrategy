#!/usr/bin/env python3
"""
P1 Optimization - Automated Notification Dispatcher
Extracts key insights from the latest quarterly report and SQLite database,
formatting an executive intelligence summary and sending it via Webhooks.

Supported Notification Channels:
  - Feishu / Lark Webhook
  - DingTalk Webhook
  - Telegram Bot API
  - Discord Webhook
  - Slack Webhook
  - GitHub Actions Step Summary (automatic in CI)
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from typing import Dict, List, Optional

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_latest_report(reports_dir: Optional[str] = None) -> Optional[str]:
    """Find the newest markdown report in the reports directory."""
    if not reports_dir:
        reports_dir = os.path.join(PROJECT_ROOT, "reports")
    if not os.path.exists(reports_dir):
        return None
    files = [
        f for f in os.listdir(reports_dir)
        if f.startswith("celebrity_clone_") and f.endswith(".md")
    ]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(os.path.join(reports_dir, f)), reverse=True)
    return os.path.join(reports_dir, files[0])


def extract_report_summary(report_path: str, db_path: Optional[str] = None) -> Dict:
    """Extract executive summary fields from report and database."""
    summary = {
        "report_file": os.path.basename(report_path) if report_path else "N/A",
        "date_period": "未知周期",
        "top_candidates": [],
        "streaks": [],
        "sec_13g_warnings": [],
        "cost_edges": [],
    }

    if report_path and os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract period
        m_period = re.search(r"\*\*📅 对比周期：(.*?)\*\*", content)
        if m_period:
            summary["date_period"] = m_period.group(1).strip()

        # Extract top candidates
        m_cand = re.search(r"本季度最高确信度与共振候选标的为：\*\*`([^`]+)`\*\*", content)
        if m_cand:
            summary["top_candidates"] = [x.strip() for x in m_cand.group(1).split(",") if x.strip()]

        # Extract cost advantage tickers
        for line in content.splitlines():
            if "比成本-" in line or "显著成本优势" in line:
                m_tick = re.search(r"\|\s*\*\*([A-Z.]+)\*\*", line)
                if m_tick:
                    summary["cost_edges"].append(m_tick.group(1))

    # Pull from SQLite database if available
    if not db_path:
        db_path = os.path.join(PROJECT_ROOT, "data", "investor_radar.db")

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # 1. Top Conviction Streaks
            rows = conn.execute("""
            SELECT ticker, guru_code, final_score, building_streak, resonance_multiplier
            FROM conviction_scores
            WHERE latest_signal != 'SOLD' AND final_score > 0
            ORDER BY final_score DESC LIMIT 5
            """).fetchall()
            for r in rows:
                summary["streaks"].append({
                    "ticker": r["ticker"],
                    "guru": r["guru_code"],
                    "score": r["final_score"],
                    "streak": r["building_streak"],
                    "mult": r["resonance_multiplier"]
                })

            # 2. Recent SEC 13G Early Warnings
            g_rows = conn.execute("""
            SELECT filing_date, form_type, filer_name, subject_ticker, subject_name, ownership_pct
            FROM sec_13g_signals
            ORDER BY filing_date DESC LIMIT 5
            """).fetchall()
            for r in g_rows:
                summary["sec_13g_warnings"].append({
                    "date": r["filing_date"],
                    "form": r["form_type"],
                    "filer": r["filer_name"],
                    "ticker": r["subject_ticker"] or "",
                    "subject": r["subject_name"] or "",
                    "pct": r["ownership_pct"] or 0.0
                })

            conn.close()
        except Exception:
            pass

    return summary


def build_notification_text(summary: Dict) -> str:
    """Format markdown message for webhook payload."""
    lines = []
    L = lines.append
    L("🏛️ **CelebrityStrategy 季度 13F & 13G 聪明钱雷达简报**")
    L("━" * 32)
    L(f"📅 **报告周期：** {summary.get('date_period', '最新季度')}")
    L(f"📄 **最新报告：** `{summary.get('report_file', '')}`")
    L("")

    cands = summary.get("top_candidates", [])
    if cands:
        L(f"🎯 **最高确定性候选标的：** `{' · '.join(cands)}`")
        L("")

    streaks = summary.get("streaks", [])
    if streaks:
        L("🏆 **多季度建仓积分榜（Top 5）：**")
        for s in streaks[:4]:
            streak_str = f"连买 {s['streak']} 季" if s["streak"] >= 2 else "新买/调仓"
            res_str = " (共振×1.5)" if s["mult"] > 1.0 else ""
            L(f"  • **{s['ticker']}** ({s['guru']}): 积分 **{s['score']:.1f}** [{streak_str}]{res_str}")
        L("")

    g_warns = summary.get("sec_13g_warnings", [])
    if g_warns:
        L("⚡ **SEC 13G/13D 提前举牌预警（突破 45 天滞后）：**")
        for g in g_warns[:3]:
            tick_str = f"**{g['ticker']}** " if g["ticker"] else ""
            pct_str = f"持股 {g['pct']:.1f}%" if g["pct"] > 0 else "5%+ 举牌"
            L(f"  • {g['date']} | `{g['form']}` | {tick_str}{g['subject'][:16]} | {pct_str} by {g['filer'][:16]}")
        L("")

    edges = summary.get("cost_edges", [])
    if edges:
        L(f"💰 **具备显著成本优势（比大师更便宜）：** `{' · '.join(edges)}`")
        L("")

    L("🔬 **下一步：** 建议移送后道 `cfo-check` 启动 ARV/EPV 财务法医现金流排雷。")
    return "\n".join(lines)


# ── Webhook Dispatchers ───────────────────────────────────────────────────────
def send_feishu_webhook(webhook_url: str, text: str) -> bool:
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🏛️ CelebrityStrategy 聪明钱雷达简报"},
                "template": "blue"
            },
            "elements": [
                {"tag": "markdown", "content": text}
            ]
        }
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Feishu webhook error: {e}")
        return False


def send_dingtalk_webhook(webhook_url: str, text: str) -> bool:
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "CelebrityStrategy 聪明钱雷达简报",
            "text": text
        }
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"DingTalk webhook error: {e}")
        return False


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def send_discord_webhook(webhook_url: str, text: str) -> bool:
    payload = {"content": text}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"Discord error: {e}")
        return False


def send_slack_webhook(webhook_url: str, text: str) -> bool:
    payload = {"text": text}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Slack error: {e}")
        return False


def append_github_step_summary(text: str):
    """Write report summary to GitHub Actions Step Summary markdown."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(text + "\n\n")
            print("✅ Appended notification summary to $GITHUB_STEP_SUMMARY")
        except Exception as e:
            print(f"Notice: unable to write GITHUB_STEP_SUMMARY: {e}")


# ── Main Entrypoint ──────────────────────────────────────────────────────────
def dispatch_notifications(report_path: Optional[str] = None, webhook_url: Optional[str] = None, dry_run: bool = False) -> str:
    """Extract summary, format text, and dispatch to configured webhooks."""
    if not report_path:
        report_path = find_latest_report()
    summary = extract_report_summary(report_path)
    text = build_notification_text(summary)

    # Always write to GitHub Actions Step Summary if in CI
    append_github_step_summary(text)

    if dry_run or not (webhook_url or os.getenv("WEBHOOK_URL") or os.getenv("FEISHU_WEBHOOK")):
        print("\n📢 [Dry-Run] Notification Message Preview:\n")
        print(text)
        return text

    # Try environment variables or CLI webhook
    url = webhook_url or os.getenv("WEBHOOK_URL") or os.getenv("FEISHU_WEBHOOK") or os.getenv("DINGTALK_WEBHOOK") or os.getenv("DISCORD_WEBHOOK") or os.getenv("SLACK_WEBHOOK")
    if not url:
        return text

    if "feishu" in url or "larksuite" in url:
        ok = send_feishu_webhook(url, text)
    elif "dingtalk" in url:
        ok = send_dingtalk_webhook(url, text)
    elif "discord.com" in url:
        ok = send_discord_webhook(url, text)
    else:
        ok = send_slack_webhook(url, text)

    status_str = "succeeded" if ok else "failed"
    print(f"📡 Webhook dispatch {status_str}: {url[:35]}...")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P1 Automated Radar Notification Dispatcher")
    parser.add_argument("--report", type=str, default="", help="Path to markdown report file")
    parser.add_argument("--webhook", type=str, default="", help="Webhook URL (Feishu, DingTalk, Discord, Slack)")
    parser.add_argument("--dry-run", action="store_true", help="Print notification preview without sending")
    args = parser.parse_args()

    rep = args.report if args.report else None
    dispatch_notifications(report_path=rep, webhook_url=args.webhook, dry_run=args.dry_run)
