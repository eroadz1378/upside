# Upside

A stock-picking app that scans the market, scores 61 large US stocks on news, analysts, price action, Reddit buzz and politicians' trades, and shows one top pick each for the next day, week and month.

```
app/index.html            the app (dark, phone-first, Day / Week / Month tabs, ticker search)
backend/run.py            builds picks.json, stocks.json and reference.json
backend/upside/score.py   signals, weights and ranking (the "brain")
backend/upside/cards.py   turns scores into the scorecard the app shows
backend/upside/lookup.py  scores any single ticker on demand
api/lookup.py + vercel.json  the lookup service (free on Vercel)
backend/upside/sources.py data feeds: Finnhub, Massive (formerly Polygon.io), ApeWisdom (Reddit), Bargo (Congress)
backend/upside/universe.py  which stocks are scanned (edit freely)
.github/workflows/picks.yml runs it every weekday and publishes it
```

## How a pick is made

1. **Prices.** About 70 days of daily prices for every stock, from Massive.
2. **News.** Each stock's headlines from the last 7 days, from Finnhub. Each headline is scored positive or negative, and recent stories count more.
3. **Analysts.** Finnhub's buy/hold/sell counts: the current balance and how it changed over the last 3 months.
4. **Reddit.** ApeWisdom's mention counts across Reddit's stock communities (r/wallstreetbets, r/stocks and others), today versus yesterday. Rising attention scores well. If a stock is already a top-5 Reddit name and mentions have more than tripled, it's marked down, because peak hype often comes right before a drop. This measures how much people are talking, not whether they're positive.
5. **Politicians.** Bargo's feed of House and Senate STOCK Act trade disclosures from the last 90 days. Net buying is weighted by trade size (log-scaled) and by each member's past hit rate (0.5x–1.5x). Members can disclose up to 45 days after trading, so this signal carries little weight for Day and the most for Month.
6. **Seven signals**, each a percentile against the other stocks (80 = better than 80% of them): news sentiment, analyst ratings, momentum, technicals (trend, RSI, breakout), unusual volume, Reddit buzz and politician trades.

| Weight | News | Analysts | Momentum | Technicals | Volume | Reddit | Congress |
|---|---|---|---|---|---|---|---|
| Day | 28% | 4% | 20% | 12% | 16% | 15% | 5% |
| Week | 20% | 16% | 20% | 16% | 8% | 10% | 10% |
| Month | 12% | 28% | 20% | 16% | 4% | 5% | 15% |

Change these in `HORIZONS` in `score.py`.
7. **Pick.** The highest composite score wins. "Model upside" scales how far above average the score is by the stock's own volatility. Confidence rises when the signals agree and drops when earnings fall inside the window.
8. **Write-up.** Optional: with an Anthropic API key, Claude writes the two-sentence "why". Otherwise a template does.

## Ticker search

Type any symbol in the search box to get the same scorecard as the top picks: chart, model upside for each tab, all seven signals, Reddit and Congress activity, headlines, and where it ranks.

- **The 61 scanned stocks** work as soon as the GitHub workflow runs: every run publishes a full scorecard for each one (`stocks.json`).
- **Any other US ticker** needs the small lookup service below. It fetches that stock's prices, news, analyst ratings and quote, then scores it against the latest scan (`reference.json`), so its numbers are comparable. It shows as "#15 of 62", meaning the scan list plus this stock.

### Switch on lookups for any ticker (Vercel, about 10 minutes)

1. Sign in at vercel.com with GitHub → **Add New → Project** → import this repo. Framework preset: **Other**.
2. Add **environment variables**: `FINNHUB_API_KEY`, `MASSIVE_API_KEY`, and `REFERENCE_URL` = `https://<you>.github.io/<repo>/reference.json`.
3. Click **Deploy**. Test it: `https://<project>.vercel.app/api/lookup?t=TSLA` should return JSON.
4. In `app/index.html`, add this just above the main `<script>`:

```html
<script>window.UPSIDE_LOOKUP="https://<project>.vercel.app/api/lookup"</script>
```

Each lookup uses about 5 data calls, and results are cached for 5 minutes. The free Massive plan allows 5 calls a minute, so on free keys expect roughly one new lookup per minute across all users. Vercel's free Hobby plan is for non-commercial use; a public app needs Vercel Pro.

## Try it now (no keys)

```bash
pip install -r backend/requirements.txt
python backend/run.py --demo          # writes site/picks.json from made-up data
cp app/index.html site/
python -m http.server -d site 8000    # open http://localhost:8000, search any of the 61 tickers
```

## Go live (about 20 minutes, free to start)

1. **Get keys.** finnhub.io → free API key. massive.com → free API key. bargo.ai/free-apis/dash → free key (optional, but it raises the daily quota from 100 to 1,000 trades). Reddit data from ApeWisdom needs no key. Optional: console.anthropic.com for the write-ups.
2. **Make a GitHub repo** and upload this folder.
3. **Add secrets:** Settings → Secrets and variables → Actions → add `FINNHUB_API_KEY`, `MASSIVE_API_KEY` and, optionally, `BARGO_API_KEY` and `ANTHROPIC_API_KEY`.
4. **Turn on Pages:** Settings → Pages → Source: **GitHub Actions**.
5. **Run it:** Actions → "Build and publish picks" → Run workflow. The first run downloads price history slowly (the free Massive plan allows 5 calls a minute), so expect about 20 minutes. Later runs take about 3.
6. Your app is now live at `https://<you>.github.io/<repo>/`, and the data is at `.../picks.json`. It refreshes every weekday before the open and after the close.

## Put it on the iPhone (Capacitor)

You need a Mac with Xcode and an Apple Developer account ($99/yr).

```bash
npm init -y
npm i @capacitor/core @capacitor/cli @capacitor/ios
npx cap init Upside com.yourname.upside --web-dir app
```

In `app/index.html`, add these lines just above the main `<script>`, so the installed app pulls the live picks and can search:

```html
<script>
window.UPSIDE_API="https://<you>.github.io/<repo>/picks.json"
window.UPSIDE_LOOKUP="https://<project>.vercel.app/api/lookup"
</script>
```

Then run:

```bash
npx cap add ios
npx cap open ios      # in Xcode: set your Team, app icon, then Product → Archive → upload
```

Apple reviews finance apps closely, so add a few native touches (a widget or push alerts help). The wrapped site alone can be rejected as "just a website".

## Before you go public: read this

- **Data licences.** Free Finnhub and Massive plans are for personal, non-commercial use. A public or paid App Store app needs their commercial/business plans. Ask each provider for a quote that allows "display in a consumer app".
- **Reddit.** Reddit's own API is non-commercial only and no longer accepts new requests, which is why this uses ApeWisdom. ApeWisdom doesn't publish commercial terms, so email them before launch. Paid alternatives with stated licensing include AltIndex and SentiSense.
- **Congress.** Bargo's terms require a visible credit linking to Bargo wherever its data appears (the app does this) and forbid redistributing the raw records. Check their Terms of Use for commercial use, or switch to a paid feed such as Quiver Quantitative. Disclosures can lag trades by up to 45 days; the app says so.
- **Search load.** Every lookup for an unscanned ticker spends data calls. Paid data plans raise the limits; you can also widen the scan list in `universe.py` so more searches are instant.
- **App Store review.** Keep the in-app disclaimer, add a privacy policy URL, and describe picks as model forecasts, never guaranteed returns. If you charge for picks or give personalised advice, talk to a securities lawyer first; that can bring in investment-adviser rules.
- **Honesty about accuracy.** Before marketing results, log each day's picks and measure how they actually did against the S&P 500 over a few months. The scoring weights are reasonable starting points, not proven.
