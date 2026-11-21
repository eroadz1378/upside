"""Headline sentiment: VADER plus finance-specific words it doesn't know."""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FINANCE_WORDS = {
    "upgrade": 2.0, "upgrades": 2.0, "upgraded": 2.0, "beat": 1.5, "beats": 1.5,
    "raises": 1.2, "raised": 1.0, "record": 1.0, "surge": 1.8, "surges": 1.8,
    "soar": 2.0, "soars": 2.0, "rally": 1.5, "rallies": 1.5, "outperform": 1.8,
    "buyback": 1.2, "approval": 1.5, "approved": 1.5, "wins": 1.3, "expands": 1.0,
    "downgrade": -2.0, "downgrades": -2.0, "downgraded": -2.0, "miss": -1.5,
    "misses": -1.5, "cuts": -1.2, "plunge": -2.2, "plunges": -2.2, "lawsuit": -1.5,
    "probe": -1.5, "recall": -1.5, "layoffs": -1.2, "underperform": -1.8,
    "slump": -1.8, "tumbles": -2.0, "warns": -1.5, "delay": -1.0, "delays": -1.0,
    "investigation": -1.5, "antitrust": -1.2, "halts": -1.5,
}

_an = SentimentIntensityAnalyzer()
_an.lexicon.update(FINANCE_WORDS)


def score(text: str) -> float:
    """-1 (very negative) .. +1 (very positive)."""
    return _an.polarity_scores(text or "")["compound"]


def tone(s: float) -> str:
    return "u" if s > 0.15 else "d" if s < -0.15 else "n"
