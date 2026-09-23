# Celebrity Cloning 13F Strategy (知名投资人持仓季度变动追踪)

本项目是基于 Gemini / Antigravity 原生 Skill 模式构建的 **13F 顶级投资人季度仓位变动与机会审计系统**。

## 🎯 核心目标与哲学

围绕**聪明钱的下注决心（Conviction）**与**克隆投资机会**，贯彻三大硬原则：
1. **剔除市值噪音**：只监控权重变化与仓位倍数，不展示个股市值。
2. **度量加仓力度**：通过 `权重Δ%`（本期占比 - 上期占比）与 `仓位倍数×`（本期占比 ÷ 上期占比，≥2× 为大幅加仓）捕捉大佬的最高信念标的。
3. **入场成本窗口**：将 yfinance 现价与大佬申报价格对比，标明 `🟢 现价比成本低`（更好的克隆买点）与 `🟡 现价高成本`（追高谨慎）。

---

## 📂 项目结构

```text
celebrityStrategy/
├── .agents/
│   └── skills/
│       └── celebrity-clone-13f-auditor/
│           ├── SKILL.md                 # Antigravity Skill 定义与执行指南
│           ├── scripts/
│           │   └── fetch_dataroma_holdings.py  # 核心抓取、交叉验证与报告生成脚本
│           └── references/              # 深入技术规范与说明文档
│               ├── dataroma-history-html.md
│               ├── dataroma-independent-verify.md
│               ├── dataroma-page-inventory.md
│               ├── dataroma-sold-detection.md
│               ├── sec-edgar-13f-xml.md
│               └── verify-removed-gurus.md
├── data/
│   └── .guru_tickers_state.json         # 持久化观察列表（用于清仓标的差分检测）
├── reports/                             # 生成的 13F 变动审计报告存档与最新快照
└── README.md
```

---

## 🚀 快速使用

### 1. 作为 Gemini / Antigravity Native Skill 触发

在与 Gemini / Antigravity 交互时，直接用自然语言提问即可自动触发：
- “帮我追踪一下李录和段永平本季度的 13F 持仓变动。”
- “分析知名投资人的最新建仓和大幅加仓机会，并生成对比报告。”
- “运行 13F 监控并同步发布到 Obsidian。”

### 2. 命令行手动执行

```bash
# 全量运行（包含 Dataroma、SEC 13F 交叉验证与现价对比）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py

# 同步输出到 Obsidian（遵循只写/覆盖、绝不删除的硬规则）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --sync-obsidian

# 仅检查李录（HC）或段永平（HH）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --gurus HC

# 导出 JSON 结构化数据
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --export-json
```

---

## 🔍 数据源与验证规范

- **主要持仓与变动信号：** [Dataroma](https://www.dataroma.com)（李录 `HC`、段永平 `HH`）
- **官方原始备案：** [SEC EDGAR](https://www.sec.gov) 13F-HR XML（原始数据一致性校验）
- **当前市场价格：** yfinance 实时行情与成本窗口测算
- **验证标记语义：**
  - `⚠️`：现价相比申报价变动 > 20%（真实价格大幅波动提示）
  - `ℹ️`：SEC EDGAR 与 Dataroma 存在股数/市值差异（多主体申报、ADR折算口径差异，属正常现象）
  - `✅`：数据源高度一致
