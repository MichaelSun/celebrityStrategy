#!/usr/bin/env python3
"""
Unit tests for Phase 2 components:
1. Building Conviction Scorer (scores, streak, resonance multipliers)
2. Global Signal Fetcher (tables, grand portfolio parsing)
3. Valuation Cache (table schema, metrics formatting)
"""

import os
import sqlite3
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPhase2Features(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.cur = self.conn.cursor()
        # Create minimal test schema
        self.cur.execute("""
        CREATE TABLE portfolio_history (
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
            reported_price REAL DEFAULT 0.0
        )
        """)

    def tearDown(self):
        self.conn.close()

    def test_conviction_scoring_rules(self):
        """Test the scoring logic for different activity types."""
        from scripts.conviction_scorer import _classify_activity, SCORE_MAP

        self.assertEqual(_classify_activity("Buy"), "NEW")
        self.assertEqual(_classify_activity("New"), "NEW")
        self.assertEqual(_classify_activity("Add 133.53%"), "INCREASED")
        self.assertEqual(_classify_activity("Reduce -25%"), "REDUCE")
        self.assertEqual(_classify_activity("Sell -100.00%"), "SOLD")
        self.assertEqual(_classify_activity(""), "NO_CHANGE")

        self.assertEqual(SCORE_MAP["NEW"], 3)
        self.assertEqual(SCORE_MAP["INCREASED"], 2)
        self.assertEqual(SCORE_MAP["REDUCE"], -1)
        self.assertEqual(SCORE_MAP["SOLD"], -4)

    def test_conviction_streak_and_resonance(self):
        """Test that consecutive buys increase streak and resonance boosts score."""
        from scripts.conviction_scorer import compute_conviction_scores, ensure_conviction_table

        # Insert 3 quarters of continuous buying for HH (PDD)
        # and 1 quarter of buying for HC (PDD) in latest quarter -> resonance!
        self.cur.execute("INSERT INTO portfolio_history (quarter, guru_code, ticker, activity, portfolio_weight) VALUES ('Q4 2025', 'HH', 'PDD', 'Add 34%', 5.0)")
        self.cur.execute("INSERT INTO portfolio_history (quarter, guru_code, ticker, activity, portfolio_weight) VALUES ('Q1 2026', 'HH', 'PDD', 'Add 71%', 8.0)")
        self.cur.execute("INSERT INTO portfolio_history (quarter, guru_code, ticker, activity, portfolio_weight) VALUES ('Q2 2026', 'HH', 'PDD', 'Add 26%', 10.0)")

        # HC also buys in Q2 2026
        self.cur.execute("INSERT INTO portfolio_history (quarter, guru_code, ticker, activity, portfolio_weight) VALUES ('Q2 2026', 'HC', 'PDD', 'Add 133%', 22.0)")
        self.conn.commit()

        # Write to a temp db file to test compute_conviction_scores
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        try:
            temp_conn = sqlite3.connect(temp_db)
            self.conn.backup(temp_conn)
            temp_conn.close()

            leaderboard = compute_conviction_scores(temp_db, rolling_quarters=4)
            self.assertGreater(len(leaderboard), 0)

            hh_pdd = next((s for s in leaderboard if s["guru_code"] == "HH" and s["ticker"] == "PDD"), None)
            hc_pdd = next((s for s in leaderboard if s["guru_code"] == "HC" and s["ticker"] == "PDD"), None)

            self.assertIsNotNone(hh_pdd)
            self.assertIsNotNone(hc_pdd)

            # HH streak should be 3 quarters
            self.assertEqual(hh_pdd["building_streak"], 3)
            # Resonance multiplier between HC (Tier 1) and HH (Tier 1) should be 1.5
            self.assertEqual(hh_pdd["resonance_multiplier"], 1.5)
            self.assertEqual(hc_pdd["resonance_multiplier"], 1.5)
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

    def test_global_signals_schema(self):
        """Test grand_portfolio_snapshot and global_activity_signals schemas."""
        from scripts.fetch_global_signals import ensure_phase2_tables

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        try:
            ensure_phase2_tables(temp_db)
            conn = sqlite3.connect(temp_db)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            self.assertIn("grand_portfolio_snapshot", tables)
            self.assertIn("global_activity_signals", tables)
            conn.close()
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

    def test_valuation_cache_format(self):
        """Test formatting of valuation section from valuation_cache."""
        from scripts.refresh_valuation_cache import format_valuation_section

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        try:
            conn = sqlite3.connect(temp_db)
            conn.execute("""
            CREATE TABLE valuation_cache (
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
            conn.execute("""
            INSERT INTO valuation_cache (ticker, current_price, pe_ttm, forward_pe, fcf_yield, market_cap_b, sector)
            VALUES ('PDD', 79.04, 8.5, 6.4, 66.3, 112.3, 'Consumer Cyclical')
            """)
            conn.commit()
            conn.close()

            md = format_valuation_section(temp_db, tickers=["PDD"])
            self.assertIn("PDD", md)
            self.assertIn("8.5", md)
            self.assertIn("66.3%", md)
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)


if __name__ == "__main__":
    unittest.main()
