---
name: celebrity-clone-13f-auditor
description: >-
  Audits and monitors 13F quarterly portfolio changes of top value investors across tiered circles (Tier 1: Li Lu, Duan Yongping, Warren Buffett; Tier 2: Mohnish Pabrai, Guy Spier, Mason Hawkins) via Dataroma, SEC EDGAR 13F XML, and yfinance.
  Detects position movements (NEW, INCREASED, REDUCED, SOLD), multi-quarter building conviction, cost-window cloning edges (current price vs guru entry cost), integrates off-13F HK/A-share assets, ingests into SQLite time-series DB, and bridges Top candidates to cfo-check.
  Use when the user asks to monitor famous investor holdings, track 13F quarterly changes, clone celebrity guru moves, or generate value investing opportunity reports.
---

# 价值投资机构季度 13F 变动审计与机会雷达 (Phase 1 升级版)

## 概览与定位

本 Skill 专用于追踪全球顶尖价值投资机构与宗师（**李录、段永平、沃伦·巴菲特、莫尼斯·帕布莱、梅森·霍金斯等**）的最新 13F 季度持仓变动与历史时序演变，输出结构化的**机会发现与克隆信号报告**，并作为前道聪明钱雷达为后道财务法医系统（`cfo-check`）输送高确定性标的。

---

## 报告设计哲学（机会优先，两道漏斗）

1. **不搞粗糙劣质的自制估值**：估值与财务法医彻底交由专业的 `cfo-check` 引擎（格林沃尔德 EPV/ARV + 反向 DCF + 现金流失血一票否决）。
2. **前道雷达专注三大行为学信号**：
   - **下注决心（Conviction）**：仓位倍数 $\ge 1.5\times$、新建仓组合占比、跨季度连续增持（Building Position）。
   - **圈层共振（Resonance）**：多位正统价值大师同买、跨 Tier 圈层共振。
   - **成本优势窗口（Cost Edge）**：现价 vs 大师买入成本（🟢 安全边际买点 / 🟡 追高谨慎）。
3. **两阶段无缝管道**：前道雷达提炼出当季 Top 3~5 标的，一键移送后道 `cfo-check` 进行深度排雷。

---

## 追踪机构三圈层体系（Tiered Universe）

| 圈层 | 机构 / 投资人 | 跟踪代号 | 风格定位 | CIK 验证 |
|:---|:---|:---:|:---|:---:|
| **Tier 1: 核心基石** | **李录** (Himalaya Capital)<br>**段永平** (H&H International)<br>**沃伦·巴菲特** (Berkshire Hathaway) | `HC`<br>`HH`<br>`BRK` | 华人商业宗师 + 价值投资灯塔；最深厚的护城河与跨国商业飞轮 | ✅ 活跃 13F-HR |
| **Tier 2: 芒格门徒与品质复利** | **Mohnish Pabrai** (帕布莱)<br>**Guy Spier** (盖伊·斯皮尔)<br>**Mason Hawkins** (梅森·霍金斯)<br>**Terry Smith** (特里·史密斯)<br>**Thomas Gayner** (汤姆·盖纳) | `PI`<br>`aq`<br>`SE`<br>`FS`<br>`MKL` | 正统克隆法则、非对称赔率、高资本回报率（ROIC） | ✅ 按需匹配 |
| **Tier 3: 宏观逆向与特种机会** | **Bill Ackman** (阿克曼)<br>**David Tepper** (泰珀)<br>**Howard Marks** (霍华德·马克斯) | `psc`<br>`AM`<br>`oc` | 周期极点判断、困境重组、宏观大波段 | ✅ 按需匹配 |

---

## 核心工作流与命令行执行

```bash
# 1. 默认运行 Tier 1 核心三巨头（李录、段永平、巴菲特），自动同步 Obsidian 并入库 SQLite
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --tier 1 --sync-obsidian

# 2. 扩展至 Tier 1 + Tier 2（包含帕布莱、斯皮尔、梅森·霍金斯全景共振）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --tier 1,2 --sync-obsidian

# 3. 指定特定投资人代码
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --gurus HC,HH,BRK,SE

# 4. [Phase 2] 抓取 Dataroma 全市场信号（Grand Portfolio 共识热力图 + All Activity 实时流水 + 历史仓位回填）
python3 scripts/fetch_global_signals.py --backfill HC,HH,BRK

# 5. [Phase 2] 计算多季度决心积累积分榜（Building Conviction Streak & Resonance Multipliers）
python3 scripts/conviction_scorer.py --quarters 6 --top 20

# 6. [Phase 2] 刷新基本面估值快照（PE TTM, Forward PE, FCF Yield, 市值, 52W范围）
python3 scripts/refresh_valuation_cache.py

# 7. 🔀 一键启动后道 FCF Check (cfo-check) 深度排雷流水线
# 自动抓取最新 13F 报告筛选出的 Top 候选标的（如 PDD, BRK.B, TSLA, CRDO）移送 cfo-check：
python3 scripts/bridge_to_cfo_check.py --mode screen
```

---

## 核心数据架构与资产版图

1. **时序数据库：** `data/investor_radar.db`（SQLite 存储历史快照与变动流水）。
2. **非 13F 离岸核心资产外挂：** `data/off_13f_holdings.yaml`（跟踪李录比亚迪/邮储银行、段永平腾讯/茅台/泡泡玛特）。
3. **Obsidian 安全同步目录：**
   `/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考/`
   *(严格执行只写/覆盖、绝不删除历史文件的永久硬规则)*
