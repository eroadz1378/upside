"""On-demand ticker lookup: GET /api/lookup?t=TSLA

Deploys free on Vercel (see README). Keeps your API keys on the server.
Environment variables: FINNHUB_API_KEY, MASSIVE_API_KEY, and REFERENCE_URL
(the reference.json published by the GitHub workflow).
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from upside import lookup as lk, sources  # noqa: E402

_ref = {"at": 0.0, "data": None}
_results = {}  # short cache so repeated searches don't burn API calls


def reference():
    if _ref["data"] is None or time.time() - _ref["at"] > 600:
        r = requests.get(os.environ["REFERENCE_URL"], timeout=15)
        r.raise_for_status()
        _ref["data"], _ref["at"] = r.json(), time.time()
    return _ref["data"]


def run(raw):
    t = lk.clean(raw)
    hit = _results.get(t)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    fh = sources.Finnhub(os.environ["FINNHUB_API_KEY"])
    massive = sources.Massive(os.environ["MASSIVE_API_KEY"], Path("/tmp/bars"))
    data = lk.lookup(t, reference(), fh, massive)
    _results[t] = (time.time(), data)
    return data


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", os.environ.get("ALLOW_ORIGIN", "*"))
        self.send_header("Cache-Control", "public, max-age=120")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", os.environ.get("ALLOW_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET")
        self.end_headers()

    def do_GET(self):
        t = parse_qs(urlparse(self.path).query).get("t", [""])[0]
        try:
            self._send(200, run(t))
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except lk.NotFound as e:
            self._send(404, {"error": str(e)})
        except Exception:
            self._send(502, {"error": "The data service is busy. Try again in a minute."})
