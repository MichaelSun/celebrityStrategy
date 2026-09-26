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
    build_cost_matrix,
    clean_company_name,
    generate_all_company_pages,
    generate_all_cost_pages,
    generate_all_scoring_pages,
    generate_company_html,
    generate_cost_detail_html,
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
        self.assertEqual(clean_company_name("LEN", "Lennar Corp."), "莱纳建筑 (Lennar Corporation)")
        self.assertEqual(clean_company_name("DAL", "Delta Air Lines Inc."), "达美航空 (Delta Air Lines, Inc.)")
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
        self.assertIn("估值击球区与持仓成本拆解", html)
        self.assertIn("TME_cost.html", html)
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

        # Requirement 5: Cost matrix links to {ticker}_cost.html and contains pagination
        self.assertIn('href="companies/DHI_cost.html"', html)
        self.assertIn('id="tab-discounts"', html)
        self.assertIn('id="costPageNumbers"', html)
        self.assertIn('id="btnCostPrev"', html)
        self.assertIn('id="btnCostNext"', html)
        self.assertIn('filterCostTable', html)
        self.assertIn('renderCostTable', html)

        # Requirement 6: Tab 4 (Holdings tab) must be removed completely (only 3 tabs remain)
        self.assertNotIn('id="tab-holdings"', html)
        self.assertNotIn('btn-holdings', html)
        self.assertNotIn('🏛️ 大师全量持仓', html)
        self.assertIn('btn-conviction', html)
        self.assertIn('btn-sec13g', html)
        self.assertIn('btn-discounts', html)

        # Requirement 7: SEC 13G tab must include educational guide banner explaining signaling & Denominator Paradox
        self.assertIn("SEC Schedule 13G / 13D 举牌法定内涵与主力信号解读指引", html)
        self.assertIn("巨头市值分母悖论", html)
        self.assertIn("Rule 13d-1", html)

        # Requirement 8: SEC 13G ownership % must be clearly defined and table must have company links & pagination
        self.assertIn("持股占总股本比 (5%+ 举牌线)", html)
        self.assertIn("占发行在外总普通股本比例", html)
        self.assertIn('id="tab-sec13g"', html)
        self.assertIn('id="sec13gPageNumbers"', html)
        self.assertIn('id="btnSecPrev"', html)
        self.assertIn('id="btnSecNext"', html)
        self.assertIn('renderSec13gTable', html)
        self.assertIn('href="companies/DAL.html"', html)
        self.assertIn('href="companies/LEN.html"', html)
        self.assertIn('href="companies/HGTY.html"', html)

    def test_build_cost_matrix_multi_guru_and_discount_premium(self):
        """Test build_cost_matrix calculations: capital-weighted price, individual breakdown, discount/premium."""
        holdings = [
            # PDD held by 2 gurus
            {"ticker": "PDD", "company_name": "PDD Holdings", "guru_code": "HC", "guru_name": "李录 (Li Lu)", "tier": 1, "shares_held": 1000000, "reported_price": 70.0, "portfolio_weight": 20.0, "activity": "Add 10%", "quarter": "Q2 2026"},
            {"ticker": "PDD", "company_name": "PDD Holdings", "guru_code": "HH", "guru_name": "段永平 (Duan Yongping)", "tier": 1, "shares_held": 3000000, "reported_price": 90.0, "portfolio_weight": 10.0, "activity": "Add 5%", "quarter": "Q2 2026"},
            # DHI held by 1 guru (discount)
            {"ticker": "DHI", "company_name": "D.R. Horton", "guru_code": "BRK", "guru_name": "沃伦·巴菲特", "tier": 1, "shares_held": 5000, "reported_price": 160.0, "portfolio_weight": 0.5, "activity": "Buy", "quarter": "Q2 2026"},
            # AAPL held by 1 guru (premium)
            {"ticker": "AAPL", "company_name": "Apple", "guru_code": "BRK", "guru_name": "沃伦·巴菲特", "tier": 1, "shares_held": 10000000, "reported_price": 250.0, "portfolio_weight": 30.0, "activity": "Hold", "quarter": "Q2 2026"},
            # Exited position
            {"ticker": "AAPL", "company_name": "Apple", "guru_code": "HC", "guru_name": "李录", "tier": 1, "shares_held": 0, "reported_price": 0.0, "portfolio_weight": 0.0, "activity": "Sell 100.00%", "quarter": "Q2 2026"},
        ]
        valuations = {
            "PDD": {"current_price": 85.0, "sector": "Consumer Cyclical", "pe_ttm": 12.0, "fcf_yield": 8.5},
            "DHI": {"current_price": 140.0, "sector": "Real Estate", "pe_ttm": 10.5, "fcf_yield": 6.0},  # 140 < 160 (discount)
            "AAPL": {"current_price": 300.0, "sector": "Technology", "pe_ttm": 32.0, "fcf_yield": 3.0},   # 300 > 250 (premium)
        }

        matrix = build_cost_matrix(holdings, valuations)
        matrix_by_ticker = {m["ticker"]: m for m in matrix}

        # Check PDD:
        # Total shares = 1M + 3M = 4M
        # Total value = 1M*70 + 3M*90 = 70M + 270M = 340M
        # Weighted cost = 340M / 4M = 85.0
        pdd = matrix_by_ticker["PDD"]
        self.assertEqual(pdd["total_shares"], 4000000)
        self.assertEqual(pdd["weighted_cost"], 85.0)
        self.assertEqual(pdd["simple_cost"], 80.0)  # (70 + 90) / 2
        self.assertEqual(pdd["diff_pct"], 0.0)      # current 85.0 vs cost 85.0
        self.assertEqual(len(pdd["gurus_detail"]), 2)

        # Check DHI: discount
        dhi = matrix_by_ticker["DHI"]
        self.assertEqual(dhi["weighted_cost"], 160.0)
        self.assertEqual(dhi["status_category"], "discount")
        self.assertLess(dhi["diff_pct"], 0.0)

        # Check AAPL: premium and exited guru handled
        aapl = matrix_by_ticker["AAPL"]
        self.assertEqual(aapl["weighted_cost"], 250.0)
        self.assertEqual(aapl["status_category"], "premium")
        self.assertGreater(aapl["diff_pct"], 0.0)
        self.assertEqual(len(aapl["gurus_detail"]), 2)
        exited = [g for g in aapl["gurus_detail"] if g["is_exited"]]
        self.assertEqual(len(exited), 1)
        self.assertEqual(exited[0]["guru_code"], "HC")

    def test_generate_cost_detail_html(self):
        """Test generating dedicated cost breakdown page for a company."""
        item = {
            "ticker": "PDD",
            "company_name": "拼多多 (PDD Holdings Inc.)",
            "sector": "Consumer Cyclical",
            "total_shares": 4000000,
            "total_value": 340000000.0,
            "weighted_cost": 85.0,
            "simple_cost": 80.0,
            "current_price": 76.5,  # 10% discount
            "diff_pct": -10.0,
            "pe_ttm": 12.0,
            "fcf_yield": 9.2,
            "status_category": "discount",
            "guidance": "🟢 黄金击球区 (高安全边际)",
            "gurus_detail": [
                {"guru_name": "李录 (Li Lu)", "guru_code": "HC", "tier": 1, "shares_held": 1000000, "reported_price": 70.0, "position_value": 70000000.0, "portfolio_weight": 20.0, "activity": "Add 10%", "quarter": "Q2 2026", "is_exited": False},
                {"guru_name": "段永平 (Duan Yongping)", "guru_code": "HH", "tier": 1, "shares_held": 3000000, "reported_price": 90.0, "position_value": 270000000.0, "portfolio_weight": 10.0, "activity": "Add 5%", "quarter": "Q2 2026", "is_exited": False},
            ]
        }
        catalog_meta = {"name": "拼多多 (PDD Holdings Inc.)"}
        html = generate_cost_detail_html(item, catalog_meta)

        # Core assertions
        self.assertIn("拼多多 (PDD Holdings Inc.)", html)
        self.assertIn("$85.00", html)   # Weighted cost
        self.assertIn("$80.00", html)   # Simple cost
        self.assertIn("$76.50", html)   # Current price
        self.assertIn("-10.0%", html)   # Delta
        self.assertIn("加权申报均价", html)
        self.assertIn("李录", html)
        self.assertIn("段永平", html)
        self.assertIn("返回持仓成本矩阵", html)
        self.assertIn("PDD.html", html)

    def test_generate_all_cost_pages_in_temp_dir(self):
        """Test generating all cost pages into a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = load_dashboard_data(DB_PATH)
            catalog = build_company_catalog(DB_PATH)
            cost_matrix = build_cost_matrix(data["holdings"], data["valuations"])
            count = generate_all_cost_pages(cost_matrix, catalog, tmpdir)
            self.assertGreater(count, 200)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "PDD_cost.html")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "AAPL_cost.html")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "DHI_cost.html")))


if __name__ == "__main__":
    unittest.main()

