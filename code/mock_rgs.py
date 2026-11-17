"""Local fake Stake RGS: serves a game's publish_files (index.json, books, lookup tables) to the frontend.

Usage (from math-sdk/):
    env/Scripts/python.exe ../tools/mock_rgs.py <game_folder> [port]
Then open the game with: ?sessionID=local&rgs_url=localhost:<port>&lang=en&device=desktop

ponytail: one player, one session, in-memory wallet. Real RGS handles many sessions + persistence.
"""
import csv, io, json, os, random, ssl, subprocess, sys, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import zstandard

M = 1_000_000  # API money unit: 1_000_000 = $1
HERE = os.path.dirname(os.path.abspath(__file__))
game = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8443
pub = os.path.join(HERE, "..", "math-sdk", "games", game, "library", "publish_files")

# --- load math -----------------------------------------------------------------------------
# Books decompress to GBs, so never hold them in RAM: unpack once to a temp file (outside OneDrive)
# and keep only {id: byte offset}. Each play reads one line from disk.
CACHE = os.path.join(tempfile.gettempdir(), "stake_mock_rgs")
os.makedirs(CACHE, exist_ok=True)


def unpack(zst_path, out_path):
    """Stream-decompress books to out_path; return {id: (offset, payoutMultiplier)}."""
    index = {}
    with open(zst_path, "rb") as f, open(out_path, "wb") as out:
        for line in io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(f)):
            if not line.strip():
                continue
            b = json.loads(line)
            index[b["id"]] = (out.tell(), b["payoutMultiplier"])
            out.write(line if line.endswith(b"\n") else line + b"\n")
    return index


def read_book(mode, sim):
    with open(mode["path"], "rb") as f:
        f.seek(mode["index"][sim][0])
        return json.loads(f.readline())


modes = {}
for m in json.load(open(os.path.join(pub, "index.json")))["modes"]:
    path = os.path.join(CACHE, f"{game}_{m['name']}.jsonl")
    index = unpack(os.path.join(pub, m["events"]), path)
    rows = [tuple(map(int, r)) for r in csv.reader(open(os.path.join(pub, m["weights"])))]
    for sim, _, pay in rows:  # RGS verifies this hash-match on upload too
        assert index[sim][1] == pay, f"{m['name']}: book {sim} payout mismatch"
    modes[m["name"].upper()] = {"cost": m["cost"], "ids": [r[0] for r in rows], "w": [r[1] for r in rows],
                                "path": path, "index": index, "bet": 0, "won": 0, "n": 0}
    print(f"loaded {m['name']}: {len(rows)} books, cost {m['cost']}x")

BET_LEVELS = [100_000, 200_000, 400_000, 600_000, 800_000, 1_000_000, 2_000_000, 5_000_000,
              10_000_000, 20_000_000, 50_000_000, 100_000_000, 1_000_000_000]
wallet = {"balance": 100_000 * M, "round": None, "bet_id": 0}


def bal():
    return {"amount": wallet["balance"], "currency": wallet.get("currency", "USD")}


def play(body):
    mode_key = str(body.get("mode", "BASE")).upper()
    amount = int(body.get("amount", 0))
    if mode_key not in modes or amount not in BET_LEVELS + [1_200_000, 1_500_000]:  # + the "short" test range
        return 400, {"error": "ERR_VAL", "message": f"bad mode/amount {mode_key} {amount}"}
    if wallet["round"] and wallet["round"]["active"]:
        return 400, {"error": "ERR_VAL", "message": "round still active, call end-round"}
    mode = modes[mode_key]
    cost = int(amount * mode["cost"])
    if cost > wallet["balance"]:
        return 400, {"error": "ERR_IPB", "message": "Insufficient player balance."}
    sim = random.choices(mode["ids"], weights=mode["w"])[0]
    force = os.environ.get("MOCK_FORCE", "")  # testing only, e.g. MOCK_FORCE=BONUS:1234 replays that book
    if force.split(":")[0] == mode_key:
        sim = int(force.split(":")[1])
    book = read_book(mode, sim)
    payout = amount * book["payoutMultiplier"] // 100
    wallet["balance"] -= cost
    wallet["bet_id"] += 1
    wallet["round"] = {"betID": wallet["bet_id"], "amount": amount, "payout": payout,
                       "payoutMultiplier": book["payoutMultiplier"] / 100, "costMultiplier": mode["cost"],
                       "active": payout > 0, "state": book["events"], "mode": mode_key, "event": None}
    mode["bet"] += cost; mode["won"] += payout; mode["n"] += 1
    print(f"#{wallet['bet_id']} {mode_key} sim={sim} bet=${cost/M:.2f} win=${payout/M:.2f} "
          f"({book['payoutMultiplier']/100}x) | session RTP {mode['won']/mode['bet']:.1%} over {mode['n']} rounds")
    return 200, {"balance": bal(), "round": wallet["round"]}


def end_round(_):
    r = wallet["round"]
    if r and r["active"]:
        wallet["balance"] += r["payout"]
        r["active"] = False
    return 200, {"balance": bal()}


def event(body):
    if wallet["round"]:
        wallet["round"]["event"] = body.get("event")
    return 200, {"event": body.get("event")}


def authenticate(b):
    """Test hooks in the sessionID (mock only): "cur-JPY" answers in that currency,
    "short" sends a short bet range (1.00-2.00, default 1.50) like an Engine reviewer does."""
    sid = str(b.get("sessionID", ""))
    wallet["currency"] = sid.split("cur-")[1].split("-")[0].upper() if "cur-" in sid else "USD"
    levels = [1_000_000, 1_200_000, 1_500_000, 2_000_000] if "short" in sid else BET_LEVELS
    default = 1_500_000 if "short" in sid else 1_000_000
    return 200, {
        "balance": bal(),
        "round": wallet["round"] if wallet["round"] and wallet["round"]["active"] else None,
        "config": {"gameID": game, "minBet": levels[0], "maxBet": levels[-1], "stepBet": 100_000,
                   "defaultBetLevel": default, "betLevels": levels, "betModes": {},
                   "jurisdiction": {"socialCasino": False, "disabledFullscreen": False, "disabledTurbo": False,
                                    "disabledSuperTurbo": False, "disabledAutoplay": False,
                                    "disabledSlamstop": False, "disabledSpacebar": False,
                                    "disabledBuyFeature": False, "displayNetPosition": False,
                                    "displayRTP": False, "displaySessionTimer": False,
                                    "minimumRoundDuration": 0}},
        "meta": None}


ROUTES = {
    "/wallet/authenticate": authenticate,
    "/wallet/balance": lambda b: (200, {"balance": bal()}),
    "/wallet/play": play,
    "/wallet/end-round": end_round,
    "/bet/event": event,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        for h, v in (("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Headers", "*"),
                     ("Access-Control-Allow-Methods", "GET, POST, OPTIONS")):
            self.send_header(h, v)
        self.end_headers()

    def do_GET(self):  # lets you open https://localhost:<port> once to accept the dev certificate
        if self.path.startswith("/bet/replay/"):  # /bet/replay/<game>/<version>/<mode>/<event>: one book, played back
            parts = self.path.split("?")[0].strip("/").split("/")
            mode_key, sim = parts[-2].upper(), parts[-1]
            if mode_key not in modes or not sim.isdigit() or int(sim) not in modes[mode_key]["index"]:
                return self._send(404, {"error": "ERR_VAL", "message": f"no book {mode_key}/{sim}"})
            book = read_book(modes[mode_key], int(sim))
            return self._send(200, {"payoutMultiplier": book["payoutMultiplier"] / 100,
                                    "costMultiplier": modes[mode_key]["cost"], "state": book["events"]})
        if self.path.split("?")[0] == "/reset":  # refill the fake wallet (optional ?amount=1000000), reload the game tab
            from urllib.parse import parse_qs, urlparse
            dollars = int(float(parse_qs(urlparse(self.path).query).get("amount", ["100000"])[0]))
            wallet.update(balance=dollars * M, round=None)
            print(f"--- wallet reset to ${dollars:,} ---")
        self._send(200, {"ok": True, "game": game, "balance": bal(), "reset": "https://localhost:8443/reset"})

    def do_POST(self):
        route = ROUTES.get(self.path)
        if not route:
            return self._send(404, {"error": "ERR_VAL", "message": f"unknown route {self.path}"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self._send(*route(body))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    # The SDK always calls https://<rgs_url>, so we need TLS. Self-signed cert, made once.
    cert, key = os.path.join(HERE, "dev_cert.pem"), os.path.join(HERE, "dev_key.pem")
    if not os.path.exists(cert):
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825",
                        "-keyout", key, "-out", cert, "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"mock RGS for {game} on https://localhost:{port}")
    srv.serve_forever()
