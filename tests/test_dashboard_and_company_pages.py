#!/usr/bin/env python3
"""
Unit tests for Institutional HTML Dashboard and Standalone Company Pages.
"""

import os
import sqlite3
import tempfile
import unittest

from scripts.generate_html_dashboard import (
    clean_company_name,
    generate_company_html,
    generate_all_company_pages,
    generate_html,
    load_dashboard_data,
    build_company_catalog
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

    def test_generate_html_dashboard_modifications(self):
        data = load_dashboard_data(DB_PATH)
        html = generate_html(data)

        # Requirement 1: Downstream cfo-check guidance box MUST be removed completely
        self.assertNotIn("一键移送后道法医 `cfo-check` 深度排雷", html)
        self.assertNotIn("python3 scripts/bridge_to_cfo_check.py", html)

        # Requirement 2: All companies must link to their independent HTML pages
        self.assertIn('href="companies/PDD.html"', html)
        self.assertIn('href="companies/BRK.B.html"', html)
        self.assertIn('companies/${pt.ticker}.html', html)  # SVG scatter link


if __name__ == "__main__":
    unittest.main()
