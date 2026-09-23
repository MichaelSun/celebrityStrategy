# Contributing to CelebrityStrategy 🚀

Thank you for considering contributing to **CelebrityStrategy**! This project aims to bring institutional-grade discipline, multi-quarter conviction tracking, and cost-window cloning edges to value investors worldwide.

---

## 🏛️ Core Philosophy

1. **Circle of Competence First**: We do not follow momentum or short-term traders. We track verified deep value investors with 20+ year compounding track records.
2. **Conviction Over Volume**: A one-off trade is noise; persistent 2–4 quarter accumulation is signal.
3. **Upstream / Downstream Separation**:
   - Upstream **`celebrityStrategy`** is the **Idea Hunter** (capturing 13F filings, off-13F assets, cost windows).
   - Downstream **`cfo-check`** ([GitHub Repo](https://github.com/MichaelSun/cfo-check)) is the **Forensic Valuation & Veto Gate** (Cash Flow quality, Altman Z-Score, Beneish M-Score, Owner Earnings).
   - Never couple valuation logic into `celebrityStrategy`; pass tickers downstream via `scripts/bridge_to_cfo_check.py`.

---

## 🧭 How to Add a New Guru

To expand the monitored universe:

1. **Find the Guru's Dataroma Identifier & SEC CIK**:
   - Dataroma code: Check URL on `dataroma.com` (e.g., `HC` for Himalaya Capital / Li Lu, `HH` for H&H International / Duan Yongping).
   - SEC EDGAR CIK: Check SEC 13F filing entity.
2. **Assign Circle Tier**:
   - **Tier 1 (Core Role Models)**: Long-term owners (e.g., Li Lu, Duan Yongping, Warren Buffett).
   - **Tier 2 (High Conviction Value Masters)**: Concentrated value specialists (e.g., Pabrai, Spier, Hawkins, Smith).
   - **Tier 3 (Institutional Whales / Macro-Value)**: Broader macro-aware managers (e.g., Ackman, Tepper, Marks).
3. **Register in Database Initialization**:
   - Add the guru tuple in `scripts/init_radar_database.py` inside `GURUS_TO_MONITOR`.
4. **Register in Antigravity Skill**:
   - Update `.agents/skills/celebrity-clone-13f-auditor/SKILL.md` to keep documentation consistent.

---

## 🌏 How to Add Off-13F Assets (HK / A-Share)

Many great investors hold significant non-US equities that are invisible in SEC 13F reports (e.g., Li Lu's BYD in Hong Kong, Duan Yongping's Kweichow Moutai in Shanghai).

Add or update entries in `data/off_13f_holdings.yaml`:

```yaml
- manager: "Li Lu (Himalaya Capital)"
  ticker: "1211.HK"
  company: "BYD Company Limited"
  market: "HKEX"
  status: "Active Core Holding"
  first_bought_year: 2002
  initial_thesis: "Unrivaled battery chemistry engineering and operational discipline."
  notes: "Li Lu personally introduced BYD to Charlie Munger and Berkshire Hathaway in 2008."
```

---

## 🧪 Development & Testing

1. **Clone the repository**:
   ```bash
   git clone https://github.com/MichaelSun/celebrityStrategy.git
   cd celebrityStrategy
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run Unit Tests**:
   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```

4. **Test the CFO-Check Bridge** (Dry-run):
   ```bash
   python scripts/bridge_to_cfo_check.py --dry-run
   ```

---

## 🛡️ Pull Request Guidelines

- Ensure all existing unit tests pass.
- Write unit tests for any new parser, converter, or database migration.
- Keep commits descriptive (e.g., `feat: add Terry Smith Fundsmith 13F tracking`, `fix: handle fractional share splits in cost-window`).
- We look forward to your pull requests!
