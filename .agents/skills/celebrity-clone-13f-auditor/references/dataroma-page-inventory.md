# Dataroma Page Inventory

## URL patterns for crawlers

All pages require `User-Agent` header. No API key needed. Rate limit: ~10 req/s safe.

### Per-manager pages

| Page | URL | Data provided | Columns |
|---|---|---|---|
| **Holdings** | `/m/holdings.php?m={CODE}` | Current quarter positions (primary source) | Hist, Stock(Ticker/Name), %Portf, Activity, Shares, Price, Value, Current Price, +/- reported, 52W Low/High |
| **Activity** | `/m/m_activity.php?m={CODE}&typ=a` | All activities (buys + sells history) | Stock, Activity, Share Change, % Change to Portfolio |
| **Buys only** | `/m/m_activity.php?m={CODE}&typ=b` | Buy/add activities only | Same as Activity |
| **Sells only** | `/m/m_activity.php?m={CODE}&typ=s` | Sell/reduce activities only | Same as Activity |
| **Portfolio History** | `/m/hist/p_hist.php?f={CODE}` | Top 20 holdings per quarter history | Quarter-by-quarter ticker grid (no share counts) |
| **Ticker History** | `/m/hist/hist.php?f={CODE}&s={TICKER}` | Full quarterly history for ONE ticker | Period, Shares, %Portf, Activity, %Change, Price |

### Global pages

| Page | URL | Data provided |
|---|---|---|
| **All Activity** | `/m/allact.php?typ=a` | Recent buy/sell activity across ALL superinvestors |
| **Grand Portfolio** | `/m/g/portfolio.php` | Aggregate of all tracked gurus' combined holdings |
| **Managers** | `/m/managers.php` | List of all tracked superinvestors with codes |
| **Stock Page** | `/m/stock.php?sym={TICKER}` | Single stock page: which gurus hold it, price history, articles |

### Manager codes for the 4 tracked gurus

| Guru | Code | Name on page |
|---|---|---|
| Li Lu | `HC` | Li Lu - Himalaya Capital Management |
| Mohnish Pabrai | `PI` | Mohnish Pabrai - Pabrai Investments |
| Guy Spier | `aq` | Guy Spier - Aquamarine Capital |
| Duan Yongping | `HH` | Duan Yongping - H&H International Investment |

### Holdings page column structure

```
0: <td class="hist">    — history link (≡)
1: <td class="stock">   — ticker + company name
2: <td>                 — % of portfolio (float)
3: <td class="green|red|plain"> — activity text
4: <td>                 — shares (int with commas)
5: <td>                 — reported price ($X.XX)
6: <td>                 — position value ($X,XXX,XXX)
7: <td class="gap">     — empty spacer
8: <td class="quote">   — current price
9: <td class="green2|red2"> — +/- from reported price (%)
10: <td>                — 52-week low
11: <td>                — 52-week high
```

### Crawl performance notes

- Holdings page: ~8-15KB, ~0.5s per request
- Ticker history page: ~5-10KB, ~0.5s per request
- Portfolio history page: ~15-25KB, ~1s per request
- 4 holdings pages + ~43 ticker history pages = ~47 requests total, ~25s sequential or ~5s with 10 concurrent workers
