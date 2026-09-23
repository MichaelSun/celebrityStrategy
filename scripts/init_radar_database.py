#!/usr/bin/env python3
"""
Initialize SQLite Time-Series Database for Institutional Value Radar
"""

import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "investor_radar.db")
HISTORY_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history_2025_2026.json")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Guru metadata table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guru_meta (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        firm TEXT NOT NULL,
        tier INTEGER NOT NULL, -- 1: Core Guru, 2: Deep Value / Compounder, 3: Special Macro
        weight_multiplier REAL DEFAULT 1.0,
        cik TEXT,
        style_tags TEXT,
        is_active INTEGER DEFAULT 1
    )
    """)

    # 2. Portfolio quarterly holding & activity history table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quarter TEXT NOT NULL,
        guru_code TEXT NOT NULL,
        ticker TEXT NOT NULL,
        company_name TEXT,
        activity TEXT,
        shares_change TEXT,
        portfolio_pct_change REAL,
        shares_held INTEGER DEFAULT 0,
        portfolio_weight REAL DEFAULT 0.0,
        reported_price REAL DEFAULT 0.0,
        FOREIGN KEY (guru_code) REFERENCES guru_meta(code)
    )
    """)

    # 3. Ticker valuation cache table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS valuation_cache (
        ticker TEXT PRIMARY KEY,
        current_price REAL,
        pe_ttm REAL,
        forward_pe REAL,
        fcf_yield REAL,
        market_cap_b REAL,
        week52_low REAL,
        week52_high REAL,
        sector TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Seed Guru Meta
    gurus = [
        ("HC", "李录 (Li Lu)", "Himalaya Capital Management", 1, 1.5, "0001709323", "华人价值宗师,高集中度,中国互联网与银行"),
        ("HH", "段永平 (Duan Yongping)", "H&H International Investment", 1, 1.5, "0001759760", "华人商业教父,高确定性消费/科技,期权战术"),
        ("BRK", "沃伦·巴菲特 (Warren Buffett)", "Berkshire Hathaway", 1, 1.5, "0001067983", "价值投资灯塔,垄断护城河,类现金与保险浮存金"),
        ("PI", "莫尼斯·帕布莱 (Mohnish Pabrai)", "Pabrai Investments", 2, 1.2, "", "芒格正统克隆,低估非对称赔率,烟蒂资产"),
        ("aq", "盖伊·斯皮尔 (Guy Spier)", "Aquamarine Capital", 2, 1.2, "", "价值信徒,永久复利,低换手率"),
        ("SE", "梅森·霍金斯 (Mason Hawkins)", "Southeastern Asset Management", 2, 1.0, "", "深价值先驱,专注内在价值大幅折扣"),
        ("FS", "特里·史密斯 (Terry Smith)", "Fundsmith", 2, 1.0, "", "高资本回报率(ROIC),极轻资产,优质跨国复合增长"),
        ("MKL", "汤姆·盖纳 (Thomas Gayner)", "Markel Group", 2, 1.0, "", "小伯克希尔模式,保险+产业投资"),
        ("psc", "比尔·阿克曼 (Bill Ackman)", "Pershing Square Capital", 3, 0.8, "", "积极主动对冲,精选极少数高壁垒品牌"),
        ("oc", "霍华德·马克斯 (Howard Marks)", "Oaktree Capital Management", 3, 0.8, "", "周期备忘录大师,困境资产重组,宏观风险风向标"),
        ("GLRE", "大卫·艾因霍恩 (David Einhorn)", "Greenlight Capital", 3, 0.8, "", "深度价值,多空双向,逆向投资"),
        ("AM", "大卫·泰珀 (David Tepper)", "Appaloosa Management", 3, 0.8, "", "宏观科技大波段,敢为人先重仓中国资产"),
    ]

    for g in gurus:
        cur.execute("""
        INSERT OR REPLACE INTO guru_meta (code, name, firm, tier, weight_multiplier, cik, style_tags, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, g)

    # Ingest 2025-2026 data from history_2025_2026.json
    if os.path.exists(HISTORY_JSON):
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            hist_data = json.load(f)
        for guru_code, qs in hist_data.items():
            for quarter, items in qs.items():
                for it in items:
                    pct_chg = 0.0
                    try:
                        pct_chg = float(it["portfolio_pct_change"]) if it["portfolio_pct_change"] else 0.0
                    except ValueError:
                        pass
                    cur.execute("""
                    INSERT INTO portfolio_history (quarter, guru_code, ticker, company_name, activity, shares_change, portfolio_pct_change)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (quarter, guru_code, it["ticker"], it["name"], it["activity"], it["shares_change"], pct_chg))

    conn.commit()
    conn.close()
    print(f"✅ SQLite Database initialized successfully: {DB_PATH}")

if __name__ == "__main__":
    init_db()
