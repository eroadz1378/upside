"""Data sources.

Finnhub  (finnhub.io)  - live quotes, company news, analyst ratings, earnings calendar
Massive  (massive.com, formerly Polygon.io) - daily price bars for the whole market

Both have free keys for development. Their free plans are for personal,
non-commercial use; a public App Store app needs their paid/business plans.
"""
import datetime as dt
import json
import os
import random
import time
from pathlib import Path

import requests


class RateLimiter:
    def __init__(self, per_minute: int):
        self.gap = 60.0 / per_minute
        self.last = 0.0

    def wait(self):
        delay = self.last + self.gap - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()


def _get(session, limiter, url, params, tries=4):
    for attempt in range(tries):
        limiter.wait()
        r = session.get(url, params=params, timeout=20)
        if r.status_code == 429:  # rate limited: back off and retry
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Rate limited too many times: {url}")


class Finnhub:
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, key: str, per_minute: int = 55):
        self.key, self.s, self.lim = key, requests.Session(), RateLimiter(per_minute)

    def _q(self, path, **params):
        return _get(self.s, self.lim, self.BASE + path, {**params, "token": self.key})

    def quote(self, sym):
        return self._q("/quote", symbol=sym)

    def news(self, sym, days=7):
        today = dt.date.today()
        return self._q("/company-news", symbol=sym,
                       **{"from": str(today - dt.timedelta(days=days)), "to": str(today)}) or []

    def recommendations(self, sym):
        return self._q("/stock/recommendation", symbol=sym) or []

    def profile(self, sym):
        return self._q("/stock/profile2", symbol=sym) or {}

    def earnings_calendar(self, days_ahead=35):
        today = dt.date.today()
        data = self._q("/calendar/earnings",
                       **{"from": str(today), "to": str(today + dt.timedelta(days=days_ahead))})
        return {e["symbol"]: e["date"] for e in data.get("earningsCalendar", [])}


class Massive:
    """Daily bars via the 'grouped daily' endpoint: the whole market in one call per day.
    Results are cached on disk so each run only downloads days it hasn't seen."""
    BASE = "https://api.polygon.io"  # api.massive.com serves the same API

    def __init__(self, key: str, cache_dir: Path, per_minute: int = 5):
        self.key, self.s, self.lim = key, requests.Session(), RateLimiter(per_minute)
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def day(self, date: dt.date, tickers):
        f = self.cache / f"{date}.json"
        if f.exists():
            return json.loads(f.read_text())
        data = _get(self.s, self.lim,
                    f"{self.BASE}/v2/aggs/grouped/locale/us/market/stocks/{date}",
                    {"adjusted": "true", "apiKey": self.key})
        want = set(tickers)
        rows = {r["T"]: {"c": r["c"], "v": r["v"]} for r in data.get("results", []) or [] if r["T"] in want}
        if date < dt.date.today():  # only cache finished days (holidays cache as empty)
            f.write_text(json.dumps(rows))
        return rows

    def ticker_history(self, sym, calendar_days=110):
        """One stock's daily bars in a single call (used by the lookup service)."""
        end, start = dt.date.today(), dt.date.today() - dt.timedelta(days=calendar_days)
        data = _get(self.s, self.lim, f"{self.BASE}/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}",
                    {"adjusted": "true", "sort": "asc", "limit": 500, "apiKey": self.key})
        rows = data.get("results") or []
        return {"c": [r["c"] for r in rows], "v": [r["v"] for r in rows]}

    def history(self, tickers, trading_days=70):
        """{ticker: {"c": [closes...], "v": [volumes...]}} oldest -> newest."""
        out = {t: {"c": [], "v": []} for t in tickers}
        days, d = [], dt.date.today() - dt.timedelta(days=1)
        while len(days) < trading_days and d > dt.date.today() - dt.timedelta(days=trading_days * 2):
            if d.weekday() < 5:
                rows = self.day(d, tickers)
                if rows:
                    days.append(rows)
            d -= dt.timedelta(days=1)
        for rows in reversed(days):
            for t in tickers:
                if t in rows:
                    out[t]["c"].append(rows[t]["c"])
                    out[t]["v"].append(rows[t]["v"])
        return out


# ---------- Demo mode: synthetic data so the pipeline runs without keys ----------
_DEMO_NEWS = [
    "{n} shares surge after analyst upgrade", "{n} beats earnings estimates, raises outlook",
    "{n} wins multi-year contract with major customer", "{n} expands buyback program",
    "{n} faces regulatory probe over pricing", "{n} warns of slower growth next quarter",
    "{n} holds annual investor day", "{n} announces leadership change",
    "{n} stock slips as sector cools", "{n} launches new product line",
]


class Demo:
    def __init__(self, seed=7):
        self.r = random.Random(seed)

    def history(self, tickers, trading_days=70):
        out = {}
        for t in tickers:
            p, drift, vol = self.r.uniform(30, 900), self.r.gauss(0.0006, 0.0015), self.r.uniform(0.008, 0.03)
            c, v, base = [], [], self.r.uniform(2e6, 8e7)
            for _ in range(trading_days):
                p *= 1 + self.r.gauss(drift, vol)
                c.append(round(p, 2))
                v.append(int(base * self.r.uniform(0.6, 1.6)))
            out[t] = {"c": c, "v": v}
        return out

    def quote(self, sym, last=None, prev=None):
        return {"c": last, "pc": prev, "dp": (last / prev - 1) * 100 if last and prev else 0}

    def news(self, sym, days=7, name=None):
        now = time.time()
        return [{"headline": self.r.choice(_DEMO_NEWS).format(n=name or sym),
                 "datetime": now - self.r.uniform(0, days * 86400),
                 "source": self.r.choice(["Reuters", "MarketWatch", "Benzinga", "Company release"]),
                 "url": ""} for _ in range(self.r.randint(1, 8))]

    def recommendations(self, sym):
        out = []
        for _ in range(4):
            out.append({k: self.r.randint(0, 25) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")})
        return out

    def earnings_calendar(self, days_ahead=35):
        return {}


class ApeWisdom:
    """Reddit mention counts (r/wallstreetbets, r/stocks, r/investing and more) from apewisdom.io.
    Free, no key. Gives attention (mentions, upvotes, change vs 24h ago), not tone."""
    BASE = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{}"

    def __init__(self, pages=5):
        self.pages, self.s, self.lim = pages, requests.Session(), RateLimiter(20)

    def mentions(self):
        out = {}
        for p in range(1, self.pages + 1):
            data = _get(self.s, self.lim, self.BASE.format(p), {})
            for r in data.get("results", []):
                out[r["ticker"]] = {"mentions": int(r.get("mentions") or 0),
                                    "m24": int(r.get("mentions_24h_ago") or 0),
                                    "rank": int(r.get("rank") or 0), "upvotes": int(r.get("upvotes") or 0)}
            if p >= int(data.get("pages", p)):
                break
        return out


class Bargo:
    """Congressional stock trades (STOCK Act filings, House + Senate) from bargo.ai.
    Free key: 100 requests / 1,000 rows a day, last 3 months. Their terms require a
    visible credit linking to Bargo wherever the data is shown, and no raw redistribution.
    Trades are cached on disk; each run only asks for recently disclosed ones."""
    BASE = "https://www.bargo.ai/free-apis/congress/v1/trades"

    def __init__(self, key, cache_file: Path, max_pages=2):
        self.key, self.cache, self.max_pages = key, Path(cache_file), max_pages
        self.s, self.lim = requests.Session(), RateLimiter(20)
        if key:
            self.s.headers["Authorization"] = f"Bearer {key}"

    def trades(self, days=90):
        cached = json.loads(self.cache.read_text()) if self.cache.exists() else []
        cutoff = str(dt.date.today() - dt.timedelta(days=days))
        latest = max((t.get("disclosure_date") or "" for t in cached), default="")
        since = max(cutoff, str(dt.date.fromisoformat(latest) - dt.timedelta(days=3))) if latest else cutoff
        new = []
        for page in range(self.max_pages):
            data = _get(self.s, self.lim, self.BASE, {"from": since, "limit": 250 if self.key else 100, "page": page})
            rows = data.get("trades") or data.get("data") or data.get("results") or []
            new += rows
            if len(rows) < (250 if self.key else 100):
                break
        seen, merged = set(), []
        for t in new + cached:
            k = (t.get("member_slug") or t.get("member"), t.get("ticker"), t.get("type"),
                 t.get("transaction_date"), t.get("amount_range"))
            if k in seen or (t.get("transaction_date") or "") < cutoff:
                continue
            seen.add(k)
            merged.append(t)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps(merged))
        return merged


def _demo_crowd(self, tickers):
    out = {}
    for t in tickers:
        if self.r.random() < 0.85:
            m24 = self.r.randint(3, 300)
            out[t] = {"mentions": max(0, int(m24 * self.r.uniform(0.4, 2.6))), "m24": m24,
                      "rank": self.r.randint(1, 400), "upvotes": self.r.randint(10, 3000)}
    return out


def _demo_trades(self, tickers):
    members = ["Rep. A. Rivera", "Sen. M. Chen", "Rep. J. Okafor", "Sen. L. Novak", "Rep. D. Walsh", "Rep. K. Patel"]
    ranges = ["$1,001 - $15,000", "$15,001 - $50,000", "$50,001 - $100,000", "$100,001 - $250,000"]
    out = []
    for _ in range(140):
        d = dt.date.today() - dt.timedelta(days=self.r.randint(5, 85))
        out.append({"member": self.r.choice(members), "chamber": self.r.choice(["House", "Senate"]),
                    "ticker": self.r.choice(tickers), "type": self.r.choice(["purchase", "purchase", "sale"]),
                    "amount_range": self.r.choice(ranges), "transaction_date": str(d),
                    "disclosure_date": str(d + dt.timedelta(days=self.r.randint(5, 40))),
                    "outcome": self.r.choice(["winner", "loser", "winner"])})
    return out


Demo.mentions = _demo_crowd
Demo.trades = _demo_trades
