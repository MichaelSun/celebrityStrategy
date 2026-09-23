# 独立核查某 guru 的持仓 / SOLD 状态（直接爬 Dataroma）

当报告结论（尤其是「清仓了几只」「某 guru 是否还在报告里」）需要**不依赖脚本 watchlist 逻辑**独立验证时，用本方法直接爬 Dataroma 原始页面交叉确认。本次（2026-08-16）用它确认了「李录 Q2 只清仓 MCO 一只」。

## 关键前提（省时坑）

- Dataroma 持仓页 `<head>` 里有「Viewing this page requires JavaScript to be enabled」，但**表格数据本身就在服务端返回的静态 HTML 里**。普通 `requests.get` + 正确 User-Agent 即可拿到，不需要 headless 浏览器。
- **必须带 Chrome UA**，否则返回近空页面（约 11KB，只有导航骨架）：
  ```python
  H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; Chrome/124.0.0.0 Safari/537.36'}
  ```
- 持仓页 href 用的是 `?m=HC`（机构），历史页用的是 `?f=HC&s=TICKER`（机构+标的）。注意 `f` 和 `m` 不同。

## 经实测可用的正则

### 1. 当前持仓表（本期 Q）

每行结构（已用 Li Lu 页实测）：
```html
<tr>
<td class="hist"><a href="/m/hist/hist.php?f=HC&s=GOOGL" title="...">≡</a></td>
<td class="stock"><a href="/m/stock.php?sym=GOOGL">GOOGL<span> - Alphabet Inc.</span></a></td>
<td>24.55</td>
<td class="red"> </td>            <!-- 活动列：red/green/无class；空=持有不变 -->
<td>2,543,300</td>               <!-- 持股数 -->
<td>$357.37</td>                 <!-- 申报价 -->
<td>$908,899,000</td>            <!-- 市值 -->
...
</tr>
```

```python
rows = re.findall(
    r'<td class="hist"><a href="/m/hist/hist\.php\?f=HC&s=([^"]+)".*?</a></td>\s*'
    r'<td class="stock"><a[^>]*>([^<]+)<span>([^<]*)</span></a></td>\s*'
    r'<td>([\d.]+)</td>\s*'                      # 占比
    r'<td class="(?:red|green|blue|)">([^<]*)</td>\s*'  # 活动（class 可为空）
    r'<td>([\d,]+)</td>',                        # 持股数
    html, re.S)
# groups: (ticker, sym, company, pct, activity_text, shares)
# activity_text 例: '' (持有) | 'Add 133.53%' | 'Reduce 6.38%' | 'New' | 'Sold'
```

> 活动列 class 有时完全没有（持有不变时），所以 class 组要用 `(?:red|green|blue|)` 允许空串，否则整行匹配失败。

### 2. 历史页（取 Q-1 股数 + 判 SOLD）

```python
h = requests.get(f"https://www.dataroma.com/m/hist/hist.php?f=HC&s={ticker}", headers=H).text
r = re.findall(
    r'<tr>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*'
    r'<td[^>]*>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>',
    h)
# r[0] = 最新季(本期)  r[1] = 上一季(Q-1)
q2_shares = r[0][1].replace(',', '')
q1_shares = r[1][1].replace(',', '')
activity_latest = r[0][5].strip()      # 末列：如 'Sell 100.00%' 或 '$289.36'(价)
is_sold = ('sell' in activity_latest.lower()) or (q2_shares == '0')
```

> 历史页第一行是**最新季**，第二行才是 **Q-1**。清仓标的在本期持仓表消失，但历史页第一行仍显示 `Sell 100.00%` + 0 股。

## 三重确认 SOLD 的流程（推荐）

1. **watchlist 差集**：`Q1_seen_tickers − Q2_current_tickers` → 消失标的
2. **历史页直查**：对每个消失（及可疑）标的，拉历史页，看最新行是否 `Sell 100%` / 0 股
3. **活表层计数**：本期持仓表实际行数 vs watchlist 数，差集应只含清仓标的

三者一致 → 结论可靠。本次三者均指向「李录仅 MCO 清仓一只」。

## 为什么不直接信脚本

脚本的 SOLD 检测依赖 `workspace/.guru_tickers_state.json`（上一轮 ticker 集合）。若首次运行或状态文件被清，会漏报清仓。独立爬页能绕过该状态，作审计用途。
