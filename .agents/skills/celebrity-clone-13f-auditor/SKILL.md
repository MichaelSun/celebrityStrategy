---
name: celebrity-clone-13f-auditor
description: >-
  Audits and monitors 13F quarterly portfolio changes of top value investors (Li Lu, Duan Yongping) via Dataroma, SEC EDGAR 13F XML, and yfinance.
  Detects position movements (NEW, INCREASED, REDUCED, SOLD), calculates conviction metrics (Weight Δ%, Position Multiplier ×), provides cost-window cloning edges (current price vs guru entry cost), and optionally syncs reports to Obsidian.
  Use when the user asks to monitor famous investor holdings, track 13F quarterly changes, clone celebrity guru moves, or generate 13F opportunity reports.
---

# 13F 名人持仓季度变动与机会审计

## 概览与定位

本 Skill 专用于追踪顶级价值投资机构（如**李录 - 喜马拉雅资本**、**段永平 - H&H International**）的最新 13F 季度持仓变动，输出结构化的**机会发现与克隆信号报告**。

> ⚠️ **核心定位：** 只做**持仓变动与建仓决心（Conviction）监控**，不做估值与买卖推荐。

---

## 报告设计哲学（机会优先，剔除噪音）

围绕“发现可克隆投资机会”的核心目的，严格遵循以下三大原则：

1. **不展示个股市值类指标**：报告度量的是“投资大佬在自身投资组合里把某只标的的**权重/决心**增加了多少”，而非股票自身市值变动。`市值` 与 `市值变化` 已作为噪音剔除。
2. **权重 Δ% 与仓位倍数 × 决定决心**：
   - `权重Δ%` = 本期占比 - 上季占比。
   - `仓位倍数` = 本期占比 ÷ 上季占比（倍数 ≥ 2× 视为重大加仓下注）。
3. **现价定位为“入场成本窗口”，非警告**：
   - `现价 < 申报价` (🟢)：表示当前市价比大佬季度成本更低，克隆者享有更好的入场安全边际。
   - `现价 >> 申报价` (🟡)：表示已有显著涨幅，追高需谨慎。

---

## 触发场景（When to Use）

- 用户要求追踪/检查李录、段永平等知名投资人的季度持仓变动或 13F 报告
- 用户要求寻找顶级投资人近期的建仓、大幅加仓或清仓信号
- 用户要求生成 13F 信号报告并输出到工作区或同步到 Obsidian

---

## 追踪机构配置

| 投资人 | 机构名称 | Dataroma 机构代码 | SEC EDGAR CIK | 交叉验证状态 |
|:---|:---|:---:|:---:|:---:|
| **李录** | Himalaya Capital Management | `HC` | `0001709323` | ✅ 活跃 13F-HR |
| **段永平** | H&H International Investment | `HH` | `0001759760` | ✅ 活跃 13F-HR |

> 💡 **增删 Guru 规则：** 如需新增或移除机构，请同步调整脚本中的 `TRACKED_GURUS`、`GURU_SHORT` 及相关映射，确保不存在残留键或引用。详见 [verify-removed-gurus.md](./references/verify-removed-gurus.md)。

---

## 核心工作流与执行

### 1. 执行脚本生成信号报告

在工作区直接运行 Python 脚本：

```bash
# 全量运行（自动拉取 Dataroma + SEC EDGAR + yfinance 现价，并生成报告）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py

# 常用选项：
# 同步报告到 Obsidian
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --sync-obsidian

# 仅指定特定投资人（HC: 李录, HH: 段永平）
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --gurus HC

# 导出原始 JSON 数据供进一步量化
python3 .agents/skills/celebrity-clone-13f-auditor/scripts/fetch_dataroma_holdings.py --export-json
```

### 2. 信号分类标准

| 信号分类 | 标识 | 判定规则 | 机会强度评分 |
|:---|:---:|:---|:---:|
| **NEW** | ✨ 新买入 | Dataroma 标记 New/Buy，或前季持股为 0 | 🔥 高 (3分) |
| **INCREASED** | 🔺 加仓 | Dataroma 标记 Add，持股数显著增加 | 仓位倍数≥2×: 中高(2分) / 普通加仓: 中(1分) |
| **NO_CHANGE** | 🔵 持有不变 | 持股数未变，占比随市价自然浮动 | 中 (1分，行内折叠收起) |
| **REDUCED** | 🔻 减仓 | Dataroma 标记 Reduce，持股数减少 | 规避 (0分) |
| **SOLD** | ❌ 清仓 | 标的消失且历史页确认 Sell 100% | 规避 (0分，标注⏳45天前已卖) |

### 3. 清仓检测机制（SOLD Recovery）

Dataroma 的本期持仓页面在标的彻底清仓后**不再展示该股票**。
本 Skill 采用**持久化 Watchlist 差分机制**：
- 状态记录于 `data/.guru_tickers_state.json`。
- 每轮提取：`本轮消失的标的 = 历史观察列表 - 本期活动标的`。
- 对消失标的自动穿透请求 Dataroma 历史页 (`/m/hist/hist.php?f={CODE}&s={TICKER}`)，核验末尾记录是否为 0 股且包含 "Sell"。
- 详见 [dataroma-sold-detection.md](./references/dataroma-sold-detection.md)。

---

## 验证标记语义规范

报告中每只标的尾部标记具有明确口径定义：

- **⚠️ 真实价格异动**：仅在 `yfinance 现价相比申报价变动 > 20%` 时触发，提示当前已发生显著价格变化。
- **ℹ️ 口径差异（正常现象）**：SEC EDGAR 13F XML 申报的股数/市值与 Dataroma 存在偏差（由于多家境外申报主体拆分、ADR 与普通股折算比率或时点差异所致），**非脚本或数据错误**。
- **✅**：完全匹配一致。

---

## 输出与命名规范

生成的报告保存于 `reports/` 目录下：
1. **最新版本快照**：`reports/celebrity_clone_mm-dd-yyyy_季度_Vn.md`（同日同季度运行自动递增版本号 V1, V2...）
2. **时间戳历史归档**：`reports/celebrity_clone策略对比_YYYYMMDD_Vn.md`

### 报告核心板块结构
1. **对比周期与数据新鲜度**：标明 13F 季度截止日、距今天数（🟢≤45天 / 🟡46-75天 / 🔴>75天）及法定滞后说明。
2. **全部持仓操作总览**：多位投资人持仓交叉总览。
3. **🎯 本季最强机会信号速览**：新买入排名、🤝 同向共振买入、💪 最大决心加仓（倍数≥2×）。
4. **机构独立持仓板块**：按信号分组展示；🔵 持有不变标的紧凑折叠为单行展示。
5. **🔍 数据源交叉验证汇总**：Dataroma、SEC 13F 与 yfinance 状态表。
6. **🔗 跨机构交叉信号**：
   - 🤝 同向共振（多人共同加仓/新建仓）
   - ⚖️ 分歧信号（一人看好增持、一人减持/清仓）
   - 🏭 行业主题聚类（中国电商、科技AI、半导体等跨机构聚合）

---

## Obsidian 同步规则（严格遵循）

**同步目标目录：**
`/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考/`

> 🔴 **永久硬规则（不可违背）：**
> **只能向该目录写入或覆盖文件，永远不得删除其中的任何历史文件！**
> 当用户指示同步发布到 Obsidian 时，使用 `--sync-obsidian` 参数或 Python `shutil.copy2` 安全写入。

---

## 深入参考文档

- [Dataroma 页面结构与 URL 指南](./references/dataroma-page-inventory.md)
- [Dataroma 历史页面与 Q-1 提取细节](./references/dataroma-history-html.md)
- [清仓检测（SOLD）机制与 Watchlist 维护](./references/dataroma-sold-detection.md)
- [SEC EDGAR 13F XML 解析与命名空间规范](./references/sec-edgar-13f-xml.md)
- [已移除 Guru 残留核查与词边界脚本](./references/verify-removed-gurus.md)
- [Dataroma 独立直接抓取验证流程](./references/dataroma-independent-verify.md)
