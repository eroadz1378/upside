"""Turns raw data into features, scores every stock per horizon, and ranks them.

Each signal is converted to a percentile (0-100) across the universe, so a score
of 80 means "better than 80% of the stocks scanned today". Horizons weight the
signals differently: news and volume matter most for tomorrow, analyst trends
matter most for the month ahead.
"""
import bisect
import math
import re
import statistics as st
import time

from . import sentiment

# Politician trades are disclosed up to 45 days late, so they get little weight
# for tomorrow and more for the month. Reddit attention is the reverse.
HORIZONS = {
    "day":   {"days": 1,  "label": "by close tomorrow",   "weights": {"news": .28, "analyst": .04, "momentum": .20, "technicals": .12, "volume": .16, "reddit": .15, "congress": .05}},
    "week":  {"days": 5,  "label": "over 5 trading days", "weights": {"news": .20, "analyst": .16, "momentum": .20, "technicals": .16, "volume": .08, "reddit": .10, "congress": .10}},
    "month": {"days": 21, "label": "over the next month", "weights": {"news": .12, "analyst": .28, "momentum": .20, "technicals": .16, "volume": .04, "reddit": .05, "congress": .15}},
}
SIGNAL_LABELS = {"news": "News sentiment", "analyst": "Analyst ratings", "momentum": "Momentum",
                 "technicals": "Technicals", "volume": "Volume", "reddit": "Reddit buzz",
                 "congress": "Politician trades"}


def _ret(c, n):
    return c[-1] / c[-1 - n] - 1 if len(c) > n else None


def _rsi(c, n=14):
    if len(c) <= n:
        return None
    gains = [max(c[i] - c[i - 1], 0) for i in range(len(c) - n, len(c))]
    losses = [max(c[i - 1] - c[i], 0) for i in range(len(c) - n, len(c))]
    ag, al = sum(gains) / n, sum(losses) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def price_features(bars):
    c, v = bars["c"], bars["v"]
    if len(c) < 25:
        return None
    rets = [c[i] / c[i - 1] - 1 for i in range(len(c) - 20, len(c))]
    ma20 = st.mean(c[-20:])
    ma50 = st.mean(c[-50:]) if len(c) >= 50 else ma20
    rsi = _rsi(c)
    return {
        "r1": _ret(c, 1), "r5": _ret(c, 5), "r20": _ret(c, 20), "r50": _ret(c, 50),
        "vol": st.pstdev(rets) or 0.01,
        "vol_surge": v[-1] / (st.mean(v[-21:-1]) or 1),
        "trend": (c[-1] / ma20 - 1) + (ma20 / ma50 - 1),
        "breakout": 1.0 if c[-1] >= max(c[-20:]) else 0.0,
        # healthy strength scores best; overbought (RSI > 75) gets marked down
        "rsi_fit": None if rsi is None else -abs(rsi - 62),
        "last": c[-1], "prev": c[-2],
    }


def news_features(items, now=None):
    now = now or time.time()
    scored, seen = [], set()
    for it in items:
        key = (it.get("headline") or "").strip().lower()[:80]
        if not key or key in seen:
            continue  # wires repeat the same story
        seen.add(key)
        s = sentiment.score(it.get("headline", ""))
        age_h = max((now - it.get("datetime", now)) / 3600, 0)
        scored.append((s, age_h, it))
    day = [s for s, a, _ in scored if a <= 24]
    week = [s for s, a, _ in scored]
    # recency-weighted average: a story from 2 hours ago counts more than one from 6 days ago
    w = [(s, math.exp(-a / 48)) for s, a, _ in scored]
    tw = sum(x for _, x in w) or 1
    return {
        "sent_1d": st.mean(day) if day else 0.0,
        "sent_7d": sum(s * x for s, x in w) / tw if w else 0.0,
        "buzz": len(week),
        "top": sorted(scored, key=lambda x: (x[1] > 72, -abs(x[0])))[:3],
    }


def analyst_features(recs):
    def net(r):
        tot = sum(r.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")) or 1
        return (2 * r.get("strongBuy", 0) + r.get("buy", 0) - r.get("sell", 0) - 2 * r.get("strongSell", 0)) / tot
    if not recs:
        return {"rating": None, "revision": None}
    now = net(recs[0])
    past = net(recs[min(3, len(recs) - 1)])
    return {"rating": now, "revision": now - past}


def reddit_features(row):
    """Rising attention scores well; a stock that is already the most-talked-about
    name with a huge spike is marked down, since peak hype often precedes a fade."""
    if not row or row["mentions"] < 5:
        return {"growth": None, "mentions": row["mentions"] if row else 0, "m24": row["m24"] if row else 0}
    growth = math.log((row["mentions"] + 5) / (row["m24"] + 5))
    if row["rank"] and row["rank"] <= 5 and row["mentions"] > 3 * (row["m24"] + 5):
        growth -= 1.0
    return {"growth": growth, "mentions": row["mentions"], "m24": row["m24"]}


def _amount_mid(rng):
    """'$15,001 - $50,000' -> 32,500; 'Over $50,000,000' -> 50,000,000."""
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", rng or "")]
    return sum(nums) / len(nums) if nums else 8000.0


def member_track_records(trades):
    """Each member's hit rate on past trades (Bargo's 'outcome' field), shrunk toward 50%."""
    rec = {}
    for t in trades:
        m, o = t.get("member_slug") or t.get("member"), t.get("outcome")
        if o in ("winner", "loser"):
            w, n = rec.get(m, (0, 0))
            rec[m] = (w + (o == "winner"), n + 1)
    return {m: (w + 2) / (n + 4) for m, (w, n) in rec.items()}


def congress_features(trades, track):
    """Net dollar-weighted buying by members of Congress over ~90 days. Members whose
    past trades did well count more (0.5x to 1.5x). Size is log-scaled so one huge
    trade doesn't swamp many small ones."""
    if not trades:
        return {"net": None, "buys": 0, "sells": 0, "members": 0, "recent": []}
    net, buys, sells, who = 0.0, 0, 0, set()
    for t in trades:
        kind = (t.get("type") or "").lower()
        sign = 1 if kind.startswith("purchase") or kind == "buy" else -1 if kind.startswith("sale") or kind == "sell" else 0
        if not sign:
            continue
        m = t.get("member_slug") or t.get("member")
        weight = 0.5 + track.get(m, 0.5)
        net += sign * math.log10(_amount_mid(t.get("amount_range")) + 10) * weight
        buys += sign > 0
        sells += sign < 0
        who.add(m)
    recent = sorted(trades, key=lambda t: t.get("transaction_date") or "", reverse=True)[:3]
    return {"net": net, "buys": buys, "sells": sells, "members": len(who), "recent": recent}


# Raw inputs behind each signal. A stock is scored by where each input sits among
# the scanned stocks' values, so any ticker (scanned or not) can be scored the same way.
SUBS = {
    "sent_1d": lambda f: f["news"]["sent_1d"], "sent_7d": lambda f: f["news"]["sent_7d"],
    "buzz": lambda f: f["news"]["buzz"],
    "r1": lambda f: f["px"]["r1"], "r5": lambda f: f["px"]["r5"],
    "r20": lambda f: f["px"]["r20"], "r50": lambda f: f["px"]["r50"],
    "trend": lambda f: f["px"]["trend"], "rsi_fit": lambda f: f["px"]["rsi_fit"],
    "breakout": lambda f: f["px"]["breakout"], "vol_surge": lambda f: f["px"]["vol_surge"],
    "vol": lambda f: f["px"]["vol"],
    "rating": lambda f: f["an"]["rating"], "revision": lambda f: f["an"]["revision"],
    "reddit": lambda f: f["reddit"]["growth"], "congress": lambda f: f["congress"]["net"],
}


def reference(feats):
    """Sorted values of every raw input across the scanned stocks."""
    return {k: sorted(v for v in (fn(f) for f in feats.values()) if v is not None) for k, fn in SUBS.items()}


def _pct(ref, key, v):
    """Percentile (0-100) of v among the reference values; missing data sits at 50."""
    vals = ref.get(key) or []
    if v is None or not vals:
        return 50.0
    below = bisect.bisect_left(vals, v)
    equal = bisect.bisect_right(vals, v) - below
    return 100.0 * (below + 0.5 * equal) / len(vals)


def _blend(*pairs):
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw


def score_one(f, ref, horizon, earnings_date=None):
    hz = HORIZONS[horizon]
    P = lambda k: _pct(ref, k, SUBS[k](f))
    news = _blend((P("sent_1d"), 1), (P("sent_7d"), 1), (P("buzz"), .4))
    if horizon != "day":
        news = _blend((news, 1), (P("sent_7d"), 1))
    m_short, m_long = {"day": ("r1", "r5"), "week": ("r5", "r20"), "month": ("r20", "r50")}[horizon]
    sig = {
        "news": news,
        "analyst": _blend((P("rating"), 1), (P("revision"), 1.2)),
        "momentum": _blend((P(m_short), 1), (P(m_long), 1)),
        "technicals": _blend((P("trend"), 1), (P("rsi_fit"), 1), (P("breakout"), .5)),
        "volume": P("vol_surge"), "reddit": P("reddit"), "congress": P("congress"),
    }
    comp = sum(sig[k] * w for k, w in hz["weights"].items())
    vol = f["px"]["vol"]
    # Expected move = how far the composite sits above average, scaled by the stock's
    # own volatility over the horizon. A strong score on a calm stock gives a modest target.
    edge = (comp - 50) / 50
    up = edge * vol * math.sqrt(hz["days"]) * 1.25
    agree = sum(1 for v in sig.values() if v >= 60) / len(sig)
    conf = 35 + 45 * agree + 10 * max(edge, 0)
    if earnings_date and hz["days"] >= 5:
        conf -= 8  # earnings inside the window: bigger move either way
    q = _pct(ref, "vol", vol) / 100
    risk = "Low" if q < .33 else "Medium" if q < .75 else "High"
    return {"score": comp, "sig": sig, "up": up, "conf": max(min(conf, 88), 20), "vol": vol,
            "risk": risk, "earnings": earnings_date}


def rank(feats, horizon, earnings=None, ref=None):
    """Score every scanned stock; best composite first. Ranking is on the score (quality
    of evidence), not raw upside, so the most volatile stock doesn't win by default."""
    earnings = earnings or {}
    ref = ref or reference(feats)
    results = [{"t": t, **score_one(f, ref, horizon, earnings.get(t))} for t, f in feats.items()]
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def rank_among(score, ranked):
    """Where a score would place among already-ranked stocks (1 = best)."""
    return 1 + sum(1 for r in ranked if r["score"] > score)
