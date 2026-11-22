"""Score any ticker on demand, the same way as the scanned stocks.

Uses the latest reference.json from the twice-daily run (the scanned stocks'
values for every signal, plus Reddit and Congress data), then fetches this one
ticker's prices, news, analyst ratings, earnings history and quote. About 6 API calls per lookup.
"""
import re

from . import cards, score
from .universe import INFO

TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class NotFound(Exception):
    pass


def clean(raw):
    t = (raw or "").strip().upper().lstrip("$")
    if not TICKER.match(t):
        raise ValueError("Enter a ticker symbol like AAPL or BRK.B")
    return t


def lookup(ticker, ref, fh, massive):
    t = clean(ticker)
    bars = massive.ticker_history(t)
    q = fh.quote(t)
    if len(bars["c"]) < 25 or not q.get("c"):
        raise NotFound(f"No recent trading data for {t}. Check the symbol; only US-listed stocks are covered.")
    market = ref.get("market") or {}
    px = score.price_features(bars, market.get("spy_c"))
    prof = {}
    try:
        prof = fh.profile(t)
    except Exception:
        pass
    name = INFO.get(t, {}).get("name") or prof.get("name") or t
    sector = INFO.get(t, {}).get("sector") or prof.get("finnhubIndustry") or ""

    feats = {
        "px": px,
        "news": score.news_features(fh.news(t, 7)),
        "an": score.analyst_features(fh.recommendations(t)),
        "reddit": score.reddit_features(ref.get("reddit", {}).get(t)),
        "congress": ref.get("congress", {}).get(t) or score.congress_features([], {}),
    }
    try:
        feats["earn"] = score.earnings_features(fh.earnings_hist(t))
    except Exception:
        feats["earn"] = score.earnings_features([])
    price, chg = q["c"], q.get("dp") or 0.0
    scanned = t in INFO
    n = ref["universe"]
    out = {"ticker": t, "scanned": scanned, "reference_at": ref.get("generated_at"), "horizons": {},
           "market": {k: market.get(k) for k in ("score", "label", "summary", "r5", "r20", "dev50")} if market else None}
    for hz in score.HORIZONS:
        s = score.score_one(feats, ref["ref"], hz, ref.get("earnings", {}).get(t), market)
        # Rank against the latest run's scores (a scanned stock's own earlier score is in
        # that list, but only strictly higher scores count, so it isn't counted twice).
        rank = score.rank_among(s["score"], [{"score": x} for x in ref["scores"][hz]])
        out["horizons"][hz] = cards.build(t, name, sector, feats, s, hz, bars["c"], bars["v"][-1],
                                          price, chg, min(rank, n) if scanned else rank, n,
                                          scanned=scanned, dates=bars.get("d"), market=market)
    out["disclaimer"] = cards.DISCLAIMER
    return out
