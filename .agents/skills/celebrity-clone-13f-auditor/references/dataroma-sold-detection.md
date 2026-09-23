# Dataroma 清仓检测实现细节（SOLD signal recovery）

## 问题背景

Dataroma 的「当前持仓页」`/m/holdings.php?m=CODE` 在标的清仓后 **不再列出该股票**。因此纯靠解析当前持仓表，会**静默遗漏 SOLD 信号**（如李录在 Q2 2026 清空 Moody's MCO，持仓表直接消失，若只扫当前表会以为"无变化"）。

## 解决机制：持久化 watchlist 差分

脚本维护 `data/.guru_tickers_state.json`，结构：

```json
{"HC": ["AAPL","BRK.B","CROX","EWBC","GOOG","GOOGL","MCO","PDD","TME"],
 "HH": ["AAPL","BABA","BRK.B", ...]}
```

每轮运行：

1. 解析当前持仓表，得到 `cur_tickers`
2. 读 `state[code]` 作为 `prev_tickers`（首轮为空）
3. `missing = prev_tickers - cur_tickers` → 这些就是"上期有、本期消失"的标的
4. 对每个 `missing` ticker 调 `detect_sold_position(code, ticker)`

## detect_sold_position 逻辑

请求历史页 `/m/hist/hist.php?f=CODE&s=TICKER`，正则抓表格行：

```
<tr><td>{Period}</td><td>{Shares}</td><td>{%}</td><td>{Activity}</td><td>{%chg}</td><td>{Price}</td></tr>
```

- `rows[0]` = 当前季度；`rows[1]` = 上季度（Q-1）
- 判据：`cur_shares == 0` 且 `cur_activity` 含 "sell"（不区分大小写）→ 判定 ❌ SOLD
- 同时回填：上季股数、上季市值（=上季股数×上季价）、上季占比，供 Q-vs-Q-1 对比
- 公司名：从页面 `<p id="p2">...<a>COMPANY NAME (TICKER)</a></p>` 标题提取（清仓股已从当前表消失，需自行补名）

返回 dict 带 `signal: "SOLD"`，并入 `data["holdings"]` 并重新按占比排序、`num_positions += 1`。

## 关键陷阱

- **首轮状态为空**：新环境或刚删除 state 文件后，首轮 `prev_tickers` 为空，不会报任何 SOLD。必须**至少跑过一轮**后，watchlist 才有历史可比。若想立即验证，可手动 seed state（见下）。
- **seed 示例**（验证用）：
  ```python
  import json, pathlib
  sf = pathlib.Path("data/.guru_tickers_state.json")
  json.dump({"HC": ["GOOGL","GOOG","EWBC","CROX","TME","AAPL","MCO","BRK.B","PDD"],
             "HH": [/* 已知当前持仓 */]}, sf.open("w"))
  ```
- **SOLD ≠ 减仓**：`class="red" + "Reduce"` 是减仓（仍在表中）；只有完全消失 + 历史页 0 股 + Sell 才是清仓。
- 该机制**只补"消失的持仓"**，不会误把"从未持有"的 ticker 当 SOLD——`missing` 来自历史 watchlist，天然排除从未见过的标的。
