#!/usr/bin/env python3
"""
Unit tests for CelebrityStrategy Radar
Tests SQLite schema, ticker normalization, cost-window logic, off-13F YAML integrity, and bridge functions.
"""

import os
import sqlite3
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def normalize_yfinance_ticker(ticker: str) -> str:
    """Helper to convert dots to dashes for Yahoo Finance share classes (e.g. BRK.B -> BRK-B)"""
    return ticker.replace(".", "-")

def calculate_cloning_edge(current_price: float, entry_min: float, entry_max: float) -> dict:
    """Calculate whether current price offers an edge over guru's estimated purchase window"""
    avg_cost = (entry_min + entry_max) / 2.0
    diff_pct = ((current_price - avg_cost) / avg_cost) * 100.0
    if current_price < entry_min:
        status = "BETTER_THAN_GURU"
    elif current_price <= entry_max:
        status = "WITHIN_GURU_WINDOW"
    else:
        status = "PREMIUM_TO_GURU"
    return {
        "status": status,
        "diff_pct": round(diff_pct, 2),
        "cheaper": current_price < avg_cost
    }

class TestCelebrityRadar(unittest.TestCase):

    def test_ticker_normalization(self):
        """Test Yahoo Finance ticker translation"""
        self.assertEqual(normalize_yfinance_ticker("BRK.B"), "BRK-B")
        self.assertEqual(normalize_yfinance_ticker("BF.B"), "BF-B")
        self.assertEqual(normalize_yfinance_ticker("PDD"), "PDD")
        self.assertEqual(normalize_yfinance_ticker("GOOGL"), "GOOGL")

    def test_cloning_edge_calculation(self):
        """Test cost-window edge evaluation"""
        # Scenario 1: Retail investor buys cheaper than guru (Better than guru)
        edge_cheap = calculate_cloning_edge(current_price=95.0, entry_min=100.0, entry_max=120.0)
        self.assertEqual(edge_cheap["status"], "BETTER_THAN_GURU")
        self.assertTrue(edge_cheap["cheaper"])
        self.assertLess(edge_cheap["diff_pct"], 0)

        # Scenario 2: Within guru entry window
        edge_mid = calculate_cloning_edge(current_price=110.0, entry_min=100.0, entry_max=120.0)
        self.assertEqual(edge_mid["status"], "WITHIN_GURU_WINDOW")

        # Scenario 3: Chasing rally (Premium to guru)
        edge_high = calculate_cloning_edge(current_price=150.0, entry_min=100.0, entry_max=120.0)
        self.assertEqual(edge_high["status"], "PREMIUM_TO_GURU")
        self.assertFalse(edge_high["cheaper"])
        self.assertGreater(edge_high["diff_pct"], 0)

    def test_off_13f_yaml_integrity(self):
        """Test that off-13F holdings file exists and contains valid records"""
        yaml_path = os.path.join(PROJECT_ROOT, "data", "off_13f_holdings.yaml")
        self.assertTrue(os.path.exists(yaml_path), f"File missing: {yaml_path}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("gurus", data)
        self.assertIn("HC", data["gurus"])
        self.assertIn("HH", data["gurus"])
        
        hc_tickers = [h["ticker"] for h in data["gurus"]["HC"]["holdings"]]
        hh_tickers = [h["ticker"] for h in data["gurus"]["HH"]["holdings"]]
        self.assertIn("1211.HK", hc_tickers)   # Li Lu's BYD
        self.assertIn("1658.HK", hc_tickers)   # Li Lu's Postal Savings
        self.assertIn("0700.HK", hh_tickers)   # Duan Yongping's Tencent
        self.assertIn("600519.SH", hh_tickers) # Duan Yongping's Moutai

    def test_sqlite_in_memory_radar(self):
        """Test database table schema and queries in memory"""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        # Create schema
        cursor.execute("""
            CREATE TABLE gurus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                tier INTEGER NOT NULL,
                cik TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guru_code TEXT NOT NULL,
                quarter TEXT NOT NULL,
                ticker TEXT NOT NULL,
                shares INTEGER NOT NULL,
                pct_portfolio REAL NOT NULL,
                action TEXT
            )
        """)

        # Insert test gurus
        cursor.execute("INSERT INTO gurus (code, name, tier, cik) VALUES ('HC', 'Li Lu', 1, '0001479475')")
        cursor.execute("INSERT INTO gurus (code, name, tier, cik) VALUES ('HH', 'Duan Yongping', 1, '0001767073')")

        # Insert holdings across 2 quarters
        cursor.execute("INSERT INTO holdings (guru_code, quarter, ticker, shares, pct_portfolio, action) VALUES ('HC', '2026-Q1', 'GOOGL', 1000, 20.0, 'HOLD')")
        cursor.execute("INSERT INTO holdings (guru_code, quarter, ticker, shares, pct_portfolio, action) VALUES ('HC', '2026-Q2', 'GOOGL', 1500, 25.0, 'INCREASED')")
        conn.commit()

        # Verify query
        cursor.execute("SELECT shares, action FROM holdings WHERE guru_code = 'HC' AND quarter = '2026-Q2' AND ticker = 'GOOGL'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1500)
        self.assertEqual(row[1], 'INCREASED')
        conn.close()

    def test_bridge_candidate_extraction(self):
        """Test candidate extraction from audit reports or fallback"""
        from scripts.bridge_to_cfo_check import extract_candidates_from_report
        # Test fallback when path is None or nonexistent
        fallback = extract_candidates_from_report(None)
        self.assertIsInstance(fallback, list)
        self.assertGreater(len(fallback), 0)

    def test_bridge_path_resolution(self):
        """Test cfo-check repository path resolver"""
        from scripts.bridge_to_cfo_check import find_cfo_check_root
        # Testing custom dir that doesn't exist
        self.assertIsNone(find_cfo_check_root("/nonexistent_path_xyz"))
        # If sibling exists, it should resolve to an existing path or return None
        res = find_cfo_check_root()
        if res:
            self.assertTrue(os.path.exists(res))

if __name__ == "__main__":
    unittest.main()
