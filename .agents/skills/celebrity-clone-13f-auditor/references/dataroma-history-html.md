# Dataroma History Page Structure

## Per-ticker history: `/m/hist/hist.php?f={CODE}&s={TICKER}`

Used for Q vs Q-1 comparison of shares, price, and portfolio %.

### HTML table structure

```html
<table id="grid">
  <thead>
    <tr>
      <td class="period">Period</td>
      <td class="shares">Shares</td>
      <td class="pct">% of Portfolio</td>
      <td class="act">Activity</td>
      <td class="a_pct">% Change to Portfolio</td>
      <td class="price">Reported Price</td>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>2026  Q1</td>         <!-- current -->
      <td>2,543,300</td>
      <td>22.85</td>
      <td class="sell"> </td>
      <td></td>
      <td>$287.56</td>
    </tr>
    <tr>
      <td>2025  Q4</td>         <!-- Q-1 target -->
      <td>2,543,300</td>
      <td>22.31</td>
      <td class="sell"> </td>
      <td></td>
      <td>$313.00</td>
    </tr>
  </tbody>
</table>
```

### Parsing regex

```python
rows = re.findall(
    r"<tr>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td[^>]*>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>",
    resp.text,
)
# rows[0] = current Q, rows[1] = Q-1, rows[2] = Q-2, ...
prev = rows[1]
prev_period = prev[0].strip()   # "2025 &nbsp Q4"
prev_shares = prev[1].replace(",", "")
prev_pct = prev[2]
prev_price = prev[5].replace("$", "").replace(",", "")
```

### Edge cases

| Case | What happens | How to handle |
|---|---|---|
| **New position** | Only 1 row in history (current Q only) | `len(rows) < 2` → treat as NEW |
| **Sold position** | Not in current holdings page, so never fetched | N/A |
| **&nbsp; in period** | "2025 &nbsp Q4" | Strip `&nbsp;` / `&nbsp` |
| **Activity with colspan** | Some old filings have merged cells | Skip rows where `len(tds) != 6` |
| **Stock split** | Share count changes between quarters | Dataroma shows adjusted shares, no action needed |
| **Empty cells** | " " or "" in activity/change columns | Treat as no activity |
