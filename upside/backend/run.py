"""Build the Upside data files.

  python run.py --demo                 # synthetic data, no keys needed
  python run.py --out site/picks.json  # live: needs FINNHUB_API_KEY and MASSIVE_API_KEY

Writes, next to --out:
  picks.json      the top pick for Day / Week / Month (what the app opens on)
  stocks.json     a full scorecard for every scanned stock (instant search)
  reference.json  what the lookup service needs to score any other ticker

Optional: BARGO_API_KEY raises the congressional-trades quota (works without it).
Optional: ANTHROPIC_API_KEY makes Claude write each top pick's two-sentence thesis
from the signals and headlines; without it a template writes it.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from upside import cards, score, sources  # noqa: E402
from upside.universe import INFO, TICKERS  # noqa: E402


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="synthetic data, no API keys")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "site" / "picks.json"))
    ap.add_argument("--cache", default=str(Path(__file__).parent / "data" / "bars"))
    args = ap.parse_args()
    out_dir = Path(args.out).parent

    if args.demo:
        demo = sources.Demo()
        bars_src = fh = crowd_src = capitol_src = demo
    else:
        fk, mk = os.environ.get("FINNHUB_API_KEY"), os.environ.get("MASSIVE_API_KEY")
        if not (fk and mk):
            sys.exit("Set FINNHUB_API_KEY and MASSIVE_API_KEY (or use --demo).")
        fh, bars_src = sources.Finnhub(fk), sources.Massive(mk, Path(args.cache))
        crowd_src = sources.ApeWisdom()
        capitol_src = sources.Bargo(os.environ.get("BARGO_API_KEY"), Path(args.cache).parent / "congress.json")

    log(f"Loading price history for {len(TICKERS)} stocks...")
    # SPY (the S&P 500 ETF) isn't a pick; it's fetched alongside for market mood and beta.
    hist = bars_src.history(TICKERS)
    try:  # one call; the day-by-day cache only holds the scanned stocks
        spy = (bars_src.history(["SPY"])["SPY"] if args.demo else bars_src.ticker_history("SPY"))
    except Exception as e:
        log("Market data skipped:", e)
        spy = {"c": []}
    market = score.market_features(spy)
    log(f"Market mood: {market['label']} ({market['score']:.0f}/100). {market['summary']}")
    px = {t: score.price_features(hist[t], spy["c"]) for t in TICKERS}
    tickers = [t for t in TICKERS if px[t]]
    log(f"{len(tickers)} stocks have enough history.")

    earnings = {}
    try:
        earnings = fh.earnings_calendar()
    except Exception as e:
        log("Earnings calendar skipped:", e)

    # Reddit and Congress are extras: if either source is down, the run carries on without it.
    crowd, trades = {}, []
    try:
        crowd = crowd_src.mentions(tickers) if args.demo else crowd_src.mentions()
        log(f"Reddit: mention counts for {sum(1 for t in tickers if t in crowd)} of our stocks.")
    except Exception as e:
        log("Reddit skipped:", e)
    try:
        trades = capitol_src.trades(tickers) if args.demo else capitol_src.trades()
        log(f"Congress: {len(trades)} disclosed trades in the last 90 days.")
    except Exception as e:
        log("Congress trades skipped:", e)
    track = score.member_track_records(trades)
    by_ticker = {}
    for tr in trades:
        by_ticker.setdefault((tr.get("ticker") or "").upper(), []).append(tr)
    congress = {t: score.congress_features(v, track) for t, v in by_ticker.items() if t}

    feats = {}
    for i, t in enumerate(tickers, 1):
        try:
            items = fh.news(t, 7, INFO[t]["name"]) if args.demo else fh.news(t, 7)
            recs = fh.recommendations(t)
        except Exception as e:
            log(f"{t}: skipped ({e})")
            continue
        try:
            earn = score.earnings_features(fh.earnings_hist(t))
        except Exception:
            earn = score.earnings_features([])
        feats[t] = {"px": px[t], "news": score.news_features(items), "an": score.analyst_features(recs),
                    "reddit": score.reddit_features(crowd.get(t)),
                    "congress": congress.get(t) or score.congress_features([], track), "earn": earn}
        if i % 10 == 0:
            log(f"  scanned {i}/{len(tickers)}")

    ref = score.reference(feats)
    n = len(feats)
    ranked = {hz: score.rank(feats, hz, earnings, ref, market) for hz in score.HORIZONS}

    quotes = {}
    for t in feats:
        try:
            q = fh.quote(t, px[t]["last"], px[t]["prev"]) if args.demo else fh.quote(t)
        except Exception:
            q = {}
        price = q.get("c") or px[t]["last"]
        chg = q.get("dp") if q.get("dp") is not None else (px[t]["last"] / px[t]["prev"] - 1) * 100
        quotes[t] = (price, chg)

    def card(t, hz, pos, top=False, thesis=None, run=None):
        s = ranked[hz][pos]
        price, chg = quotes[t]
        return cards.build(t, INFO[t]["name"], INFO[t]["sector"], feats[t], s, hz, hist[t]["c"],
                           hist[t]["v"][-1], price, chg, pos + 1, n, run=run, thesis=thesis, top=top,
                           dates=hist[t].get("d"), market=market)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    mkt_public = {k: market.get(k) for k in ("score", "label", "summary", "r5", "r20", "dev50")}
    picks = {"generated_at": now, "disclaimer": cards.DISCLAIMER, "universe": n,
             "market": mkt_public, "horizons": {}}
    stocks = {"generated_at": now, "stocks": {t: {} for t in feats}}
    for hz in score.HORIZONS:
        for pos, s in enumerate(ranked[hz]):
            stocks["stocks"][s["t"]][hz] = card(s["t"], hz, pos)
        top = ranked[hz][0]
        t = top["t"]
        run = [[r["t"], INFO[r["t"]]["name"], round(r["up"] * 100, 1),
                [round(c, 2) for c in hist[r["t"]]["c"][-24:]]] for r in ranked[hz][1:4]]
        thesis = cards.claude_thesis(t, INFO[t]["name"], top, feats[t]["news"], hz, log, market)
        picks["horizons"][hz] = card(t, hz, 0, top=True, thesis=thesis, run=run)
        log(f"{hz:>5}: {t}  +{top['up'] * 100:.1f}%  score {top['score']:.0f}  conf {top['conf']:.0f}")

    # What the lookup service needs to score a ticker outside the scanned list the same way.
    reference = {
        "generated_at": now, "universe": n, "ref": ref, "earnings": earnings, "market": market,
        "scores": {hz: [round(r["score"], 3) for r in ranked[hz]] for hz in score.HORIZONS},
        "reddit": crowd,
        "congress": {t: {**c, "recent": [{k: x.get(k) for k in ("member", "chamber", "type", "amount_range",
                                                                "transaction_date")} for x in c["recent"]]}
                     for t, c in congress.items()},
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(picks, indent=1))
    (out_dir / "stocks.json").write_text(json.dumps(stocks, separators=(",", ":")))
    (out_dir / "reference.json").write_text(json.dumps(reference, separators=(",", ":")))
    log("Wrote", args.out, "+ stocks.json + reference.json")


if __name__ == "__main__":
    main()
