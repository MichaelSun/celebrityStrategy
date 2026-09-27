/**
 * Cloudflare Worker: 0-Cost Live Quotes Edge Proxy
 * CelebrityStrategy Dynamic Market Data Engine
 *
 * Features:
 *   - 100% Free on Cloudflare Workers Free Tier (100,000 req/day)
 *   - Auto Edge Caching (60 seconds) to prevent upstream rate limiting
 *   - Universal CORS support for GitHub Pages (Access-Control-Allow-Origin: *)
 *   - Supports US Stocks and HK/ADR proxies
 *
 * Deployment:
 *   1. Paste into Cloudflare Dashboard -> Workers & Pages -> Create Worker
 *   2. Click "Save and Deploy"
 *   3. Free URL: https://quotes-proxy.<your-subdomain>.workers.dev/api/quotes?symbols=PDD,BRK-B,NVDA
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Handle CORS Preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    if (url.pathname !== "/api/quotes") {
      return new Response(JSON.stringify({ error: "Endpoint not found. Use /api/quotes?symbols=PDD,NVDA" }), {
        status: 404,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    const symbolsParam = url.searchParams.get("symbols") || "";
    const symbols = symbolsParam
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0)
      .slice(0, 50); // limit to 50 tickers per batch

    if (symbols.length === 0) {
      return new Response(JSON.stringify({ error: "Missing 'symbols' query parameter" }), {
        status: 400,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // 2. Query Cloudflare Edge Cache
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), request);
    let cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) {
      return cachedResponse;
    }

    // 3. Batch Fetch Quotes from Yahoo Finance Chart/Quote Endpoint
    const results = {};
    const fetchPromises = symbols.map(async (sym) => {
      // Map ticker if needed (e.g. BRK.B -> BRK-B)
      const querySym = sym.replace(".", "-");
      const yfUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(querySym)}?interval=1d&range=1d`;

      try {
        const resp = await fetch(yfUrl, {
          headers: {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          },
        });
        if (resp.ok) {
          const data = await resp.json();
          const meta = data?.chart?.result?.[0]?.meta;
          if (meta) {
            const curPrice = meta.regularMarketPrice ?? meta.previousClose;
            const prevClose = meta.previousClose ?? curPrice;
            const changePct = prevClose > 0 ? ((curPrice - prevClose) / prevClose) * 100 : 0;
            results[sym] = {
              price: Math.round(curPrice * 100) / 100,
              change_pct: Math.round(changePct * 100) / 100,
              currency: meta.currency || "USD",
              time: meta.regularMarketTime || Math.floor(Date.now() / 1000),
            };
          }
        }
      } catch (err) {
        // Fallback silently if individual ticker fails
      }
    });

    await Promise.all(fetchPromises);

    // 4. Build Response with Edge Cache (60s)
    const responsePayload = JSON.stringify({
      timestamp: new Date().toISOString(),
      count: Object.keys(results).length,
      quotes: results,
    });

    const response = new Response(responsePayload, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60, s-maxage=60", // 60 seconds edge cache
      },
    });

    // Save to edge cache in background
    ctx.waitUntil(cache.put(cacheKey, response.clone()));

    return response;
  },
};
