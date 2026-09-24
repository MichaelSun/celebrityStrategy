#!/usr/bin/env python3
"""
Unit tests for P1 Optimizations:
1. SEC 13G/13D Early Warning Scanner (scripts/scan_sec_13g.py)
2. Automated Notification Dispatcher (scripts/send_notification.py)
"""

import os
import sqlite3
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestP1Optimizations(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_radar.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 1. SEC 13G Scanner Tests ──────────────────────────────────────────────
    def test_infer_ticker(self):
        """Test ticker inference from issuer company name."""
        from scripts.scan_sec_13g import _infer_ticker

        self.assertEqual(_infer_ticker("LENNAR CORPORATION"), "LEN")
        self.assertEqual(_infer_ticker("DELTA AIR LINES, INC."), "DAL")
        self.assertEqual(_infer_ticker("Berkshire Hathaway Inc."), "BRK.A")
        self.assertEqual(_infer_ticker("Occidental Petroleum Corp"), "OXY")
        self.assertEqual(_infer_ticker("EAST WEST BANCORP INC"), "EWBC")
        self.assertEqual(_infer_ticker("CROCS, INC."), "CROX")
        self.assertEqual(_infer_ticker("Unknown Company XYZ"), "")

    def test_13g_database_and_formatting(self):
        """Test 13G SQLite table creation, signal saving, and markdown rendering."""
        from scripts.scan_sec_13g import ensure_13g_table, format_13g_section, save_13g_signals

        conn = sqlite3.connect(self.db_path)
        ensure_13g_table(conn)
        conn.close()

        sample_signals = [
            {
                "filing_date": "2026-08-14",
                "form_type": "SCHEDULE 13G",
                "filer_name": "Warren Buffett - Berkshire Hathaway",
                "filer_cik": "0001067983",
                "subject_name": "LENNAR CORPORATION",
                "subject_ticker": "LEN",
                "accession_num": "0001193125-26-352904",
                "url": "https://www.sec.gov/Archives/edgar/data/1067983/000119312526352904/0001193125-26-352904-index.html",
                "ownership_pct": 6.2,
                "is_tracked_guru": 1,
                "tier": 1,
            },
            {
                "filing_date": "2026-08-14",
                "form_type": "SCHEDULE 13G/A",
                "filer_name": "Warren Buffett - Berkshire Hathaway",
                "filer_cik": "0001067983",
                "subject_name": "DELTA AIR LINES, INC.",
                "subject_ticker": "DAL",
                "accession_num": "0001193125-26-352910",
                "url": "https://www.sec.gov/Archives/edgar/data/1067983/000119312526352910/0001193125-26-352910-index.html",
                "ownership_pct": 8.7,
                "is_tracked_guru": 1,
                "tier": 1,
            },
        ]

        # Save to DB
        saved = save_13g_signals(self.db_path, sample_signals)
        self.assertEqual(saved, 2)

        # Verify DB query
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT subject_ticker, ownership_pct FROM sec_13g_signals ORDER BY filing_date DESC").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "LEN")
        self.assertEqual(rows[0][1], 6.2)
        conn.close()

        # Format markdown
        md = format_13g_section(sample_signals, top_n=5)
        self.assertIn("早期预警雷达", md)
        self.assertIn("LENNAR", md)
        self.assertIn("6.2%", md)
        self.assertIn("8.7%", md)
        self.assertIn("EDGAR 备案", md)

    # ── 2. Notification Dispatcher Tests ──────────────────────────────────────
    def test_notification_summary_extraction_and_formatting(self):
        """Test extracting summary from a report and building notification payload."""
        from scripts.send_notification import build_notification_text, extract_report_summary

        report_file = os.path.join(self.temp_dir.name, "celebrity_clone_test_report.md")
        sample_report = """# 📊 价值投资机构季度 13F 变动审计与机会雷达
> **📅 对比周期：Q2 2026 vs Q1 2026**
| **DHI** | 巴菲特 | $163.02 | $140.12 | 🟢 现价$140.12 比成本-14% | 🟢 显著成本优势，买入价比大师更便宜 |
本季度最高确信度与共振候选标的为：**`PDD, BRK.B, DHI, DIS`**。
"""
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(sample_report)

        summary = extract_report_summary(report_file, db_path=self.db_path)
        self.assertEqual(summary["date_period"], "Q2 2026 vs Q1 2026")
        self.assertIn("PDD", summary["top_candidates"])
        self.assertIn("DHI", summary["top_candidates"])
        self.assertIn("DHI", summary["cost_edges"])

        text = build_notification_text(summary)
        self.assertIn("CelebrityStrategy", text)
        self.assertIn("Q2 2026 vs Q1 2026", text)
        self.assertIn("PDD · BRK.B · DHI · DIS", text)
        self.assertIn("DHI", text)

    def test_notification_dispatch_dry_run(self):
        """Test dispatch_notifications in dry-run mode returns valid text without throwing."""
        from scripts.send_notification import dispatch_notifications

        text = dispatch_notifications(report_path=None, dry_run=True)
        self.assertIsInstance(text, str)
        self.assertIn("CelebrityStrategy", text)


if __name__ == "__main__":
    unittest.main()
