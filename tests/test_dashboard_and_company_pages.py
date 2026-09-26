#!/usr/bin/env python3
"""
Unit tests for Institutional HTML Dashboard, Standalone Company Pages,
and Conviction Score Aggregation / Scoring Breakdown Pages.
"""

import collections
import os
import sqlite3
import tempfile
import unittest

from scripts.generate_html_dashboard import (
    aggregate_conviction_scores,
    build_company_catalog,
    clean_company_name,
    generate_all_company_pages,
    generate_all_scoring_pages,
    generate_company_html,
    generate_html,
    generate_scoring_detail_html,
    load_dashboard_data,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "investor_radar.db")


class TestDashboardAndCompanyPages(unittest.TestCase):

    def test_clean_company_name(self):
        self.assertEqual(clean_company_name("AAPL", "Apple Inc."), "苹果公司 (Apple Inc.)")
        self.assertEqual(clean_company_name("TME", "TME - Tencent Music Entertainment Grp"), "腾讯音乐 (Tencent Music Entertainment Grp)")
        self.assertEqual(clean_company_name("PDD", "PDD - Pinduoduo Inc."), "拼多多 (PDD Holdings Inc.)")
        self.assertEqual(clean_company_name("LEN", "Lennar Corp."), "Lennar Corp.")
        self.assertEqual(clean_company_name("DAL", "Delta Air Lines Inc."), "Delta Air Lines Inc.")
        self.assertEqual(clean_company_name("BYDDY", ""), "比亚迪 (BYD Company Ltd. ADR)")

    def test_generate_company_html(self):
        meta = {
            "name": "腾讯音乐 (Tencent Music Entertainment Grp)",
            "sector": "Communication Services",
            "current_price": 8.34,
            "pe_ttm": 9.5,
            "fcf_yield": 53.2,
            "gurus": ["李录 (Li Lu)"]
        }
        html = generate_company_html("TME", meta)
        
        # Verify essential requirements
        self.assertIn("腾讯音乐 (Tencent Music Entertainment Grp)", html)
        self.assertIn("TME", html)
        self.assertIn("返回大盘", html)
        self.assertIn("13F 大师持仓变动与持股轨迹", html)
        self.assertIn("CFO 财务法医与财务排雷", html)
        self.assertIn("估值击球区与安全边际", html)
        self.assertIn("商业模式与护城河备忘录", html)

    def test_generate_all_company_pages_in_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            count = generate_all_company_pages(DB_PATH, tmpdir)
            self.assertGreater(count, 200)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "TME.html")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "PDD.html")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "AAPL.html")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "BRK.B.html")))

            # Check content of generated TME.html
            with open(os.path.join(tmpdir, "TME.html"), "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("腾讯音乐", content)

    def test_conviction_aggregation_and_deduplication(self):
        """Test that conviction scores are properly aggregated so 1 Company = 1 Record."""
        raw_items = [
            {"ticker": "PDD", "guru_code": "HH", "guru_name": "段永平", "raw_score": 17, "resonance_multiplier": 1.5, "final_score": 25.5, "building_streak": 2, "latest_signal": "INCREASED"},
            {"ticker": "PDD", "guru_code": "HC", "guru_name": "李录", "raw_score": 13, "resonance_multiplier": 1.5, "final_score": 19.5, "building_streak": 6, "latest_signal": "INCREASED"},
            {"ticker": "BRK.B", "guru_code": "HH", "guru_name": "段永平", "raw_score": 15, "resonance_multiplier": 1.5, "final_score": 22.5, "building_streak": 0, "latest_signal": "INCREASED"},
            {"ticker": "BRK.B", "guru_code": "HC", "guru_name": "李录", "raw_score": 10, "resonance_multiplier": 1.5, "final_score": 15.0, "building_streak": 5, "latest_signal": "INCREASED"},
            {"ticker": "DHI", "guru_code": "BRK", "guru_name": "沃伦·巴菲特", "raw_score": 12, "resonance_multiplier": 1.0, "final_score": 12.0, "building_streak": 4, "latest_signal": "NEW"},
        ]
        aggregated = aggregate_conviction_scores(raw_items)
        self.assertEqual(len(aggregated), 3)  # Only 3 unique companies: PDD, BRK.B, DHI
        self.assertEqual(aggregated[0]["ticker"], "PDD")
        self.assertEqual(aggregated[0]["final_score"], 25.5)
        self.assertIn("段永平", aggregated[0]["gurus_display"])
        self.assertIn("李录", aggregated[0]["gurus_display"])
        self.assertIn("连续", aggregated[0]["reason"])
        self.assertIn("建仓", aggregated[0]["reason"])

        self.assertEqual(aggregated[1]["ticker"], "BRK.B")
        self.assertEqual(aggregated[1]["final_score"], 22.5)

        self.assertEqual(aggregated[2]["ticker"], "DHI")
        self.assertEqual(aggregated[2]["final_score"], 12.0)

    def test_generate_scoring_detail_html(self):
        """Test generating dedicated scoring breakdown page for a company."""
        item = {
            "ticker": "PDD",
            "company_name": "拼多多 (PDD Holdings Inc.)",
            "final_score": 25.5,
            "raw_score": 17,
            "gurus_display": "段永平、李录",
            "reason": "段永平连续2季建仓 · 李录连续6季建仓 ｜ 圈层共振 ×1.5",
            "latest_signal": "INCREASED",
            "group_items": [
                {"guru_name": "段永平 (Duan Yongping)", "guru_code": "HH", "tier": 1, "building_streak": 2, "raw_score": 17, "resonance_multiplier": 1.5, "final_score": 25.5, "latest_signal": "INCREASED"},
                {"guru_name": "李录 (Li Lu)", "guru_code": "HC", "tier": 1, "building_streak": 6, "raw_score": 13, "resonance_multiplier": 1.5, "final_score": 19.5, "latest_signal": "INCREASED"}
            ],
            "best_item": {"guru_name": "段永平 (Duan Yongping)", "guru_code": "HH"}
        }
        catalog_meta = {"name": "拼多多 (PDD Holdings Inc.)"}
        html = generate_scoring_detail_html(item, catalog_meta, 1)

        # Requirements check
        self.assertIn("拼多多 (PDD Holdings Inc.)", html)
        self.assertIn("25.5", html)
        self.assertIn("全局【多季度决心积分】算法模型", html)
        self.assertIn("跨圈层共振", html)
        self.assertIn("段永平", html)
        self.assertIn("李录", html)
        self.assertIn("返回大盘", html)

    def test_generate_html_dashboard_modifications(self):
        data = load_dashboard_data(DB_PATH)
        html = generate_html(data)

        # Requirement 1: Downstream cfo-check guidance box MUST be removed completely
        self.assertNotIn("一键移送后道法医 `cfo-check` 深度排雷", html)
        self.assertNotIn("python3 scripts/bridge_to_cfo_check.py", html)

        # Requirement 2: All companies must link to their independent HTML pages
        self.assertIn('href="companies/PDD.html"', html)
        self.assertIn('href="companies/BRK.B.html"', html)

        # Requirement 3: Conviction scores must link to scoring breakdown pages
        self.assertIn('href="companies/PDD_scoring.html"', html)
        self.assertIn('href="companies/BRK.B_scoring.html"', html)

        # Requirement 4: Ensure no duplicate rows in convictions
        conv_tickers = [c["ticker"] for c in data["convictions"]]
        counter = collections.Counter(conv_tickers)
        duplicates = [t for t, count in counter.items() if count > 1]
        self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main()
