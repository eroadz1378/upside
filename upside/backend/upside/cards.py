"""Builds the scorecard the app shows, from scored features. Used by the twice-daily
run (top picks + every scanned stock) and by the on-demand ticker lookup."""
import os
import time

import requests

from . import score, sentiment

DISCLAIMER = ("Model forecasts from public news, Reddit mentions, congressional trade disclosures, "
              "analyst ratings and price data. "
              "For information only; not investment advice. Prices may be delayed.")
HIST_LEN = {"day": 20, "week": 40, "month": 60}


def fmt_vol(v):
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}K"


def ago(ts):
    h = (time.time() - ts) / 3600
    return f"{max(int(h * 60), 1)}m ago" if h < 1 else f"{int(h)}h ago" if h < 24 else f"{int(h / 24)}d ago"


def template_thesis(name, s, nf, rank, n, top, scanned=True):
    order = sorted(s["sig"].items(), key=lambda kv: -kv[1])
    (k1, v1), (k2, v2) = order[0], order[1]
    (kl, vl) = order[-1]
    lead = (f"{name} scores highest of the {n} stocks scanned" if top
            else f"{name} ranks #{rank} of the {n} stocks scanned" if scanned
            else f"{name} isn't on the scan list; scored against it, it would rank #{rank} of {n + 1}")
    text = (f"{lead}, led by {score.SIGNAL_LABELS[k1].lower()} ({v1:.0f}/100) and "
            f"{score.SIGNAL_LABELS[k2].lower()} ({v2:.0f}/100).")
    if not top and vl < 35:
        text += f" Weakest: {score.SIGNAL_LABELS[kl].lower()} ({vl:.0f}/100)."
    if nf["top"]:
        text += f" Latest: {nf['top'][0][2]['headline'].rstrip('.')}."
    if s.get("earnings"):
        text += f" Earnings are due {s['earnings']}, which can move the stock sharply either way."
    return text


def claude_thesis(t, name, s, nf, horizon, log=print):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    heads = "\n".join(f"- {x[2]['headline']}" for x in nf["top"])
    sig = ", ".join(f"{score.SIGNAL_LABELS[k]} {v:.0f}/100" for k, v in s["sig"].items())
    prompt = (f"Write two plain sentences (max 45 words) explaining why a quantitative model ranks "
              f"{name} ({t}) as the top {horizon}-horizon pick. Signals (percentiles): {sig}. "
              f"Recent headlines:\n{heads}\nNo hype, no promises, no advice; state what the data shows.")
    try:
        resp = requests.post("https://api.anthropic.com/v1/messages", timeout=40, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": 160,
                  "messages": [{"role": "user", "content": prompt}]})
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:  # never let the write-up break the run
        log("Claude thesis skipped:", e)
        return None


def build(t, name, sector, f, s, hz, closes, last_volume, price, chg, rank, n,
          run=None, thesis=None, top=False, scanned=True):
    closes = closes[-HIST_LEN[hz]:]
    return {
        "tk": t, "nm": name, "sector": sector or "",
        "price": round(price, 2), "chg": round(chg, 2), "up": round(s["up"] * 100, 1),
        "target": round(price * (1 + s["up"]), 2), "conf": round(s["conf"]),
        "risk": s["risk"], "vol": fmt_vol(last_volume), "horizon": score.HORIZONS[hz]["label"],
        "unit": "daily", "hist": [round(c, 2) for c in closes[:-1]] + [round(price, 2)],
        "thesis": thesis or template_thesis(name, s, f["news"], rank, n, top, scanned),
        "earnings": s.get("earnings"), "rank": rank, "of": n if scanned else n + 1, "scanned": scanned,
        "sig": [[score.SIGNAL_LABELS[k], round(v)] for k, v in s["sig"].items()],
        "news": [[sentiment.tone(sc), it["headline"], f"{it.get('source', '')} · {ago(it['datetime'])}", it.get("url", "")]
                 for sc, _, it in f["news"]["top"]],
        "crowd": {"mentions": f["reddit"]["mentions"], "m24": f["reddit"]["m24"]},
        "capitol": {"buys": f["congress"]["buys"], "sells": f["congress"]["sells"],
                    "members": f["congress"]["members"],
                    "recent": [[x.get("member", ""), x.get("chamber", ""), (x.get("type") or "").lower(),
                                x.get("amount_range", ""), x.get("transaction_date", "")]
                               for x in f["congress"]["recent"]]},
        "run": run or [],
    }
