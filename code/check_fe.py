"""Consistency checks between a Math SDK game and its web-sdk app.
Usage (from math-sdk/): env/Scripts/python.exe ../tools/check_fe.py <game_folder> <app_folder>
Exits 1 and lists failures if any check fails."""
import io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
game, app = sys.argv[1], sys.argv[2]
PUB = os.path.join(HERE, "..", "math-sdk", "games", game, "library", "publish_files")
APP = os.path.join(HERE, "..", "web-sdk", "apps", app, "src", "game")


def read(name):
    with open(os.path.join(APP, name), encoding="utf-8") as f:
        return f.read()


def check_config_matches_math():
    cfg = read("config.ts")
    assert re.search(r"""["']?gameID["']?\s*:\s*["']%s["']""" % game, cfg), "config.ts gameID is not " + game
    modes = json.load(open(os.path.join(PUB, "index.json")))["modes"]
    for m in modes:
        assert re.search(r"""["']%s["']\s*:\s*\{""" % m["name"], cfg), f"config.ts missing bet mode {m['name']}"


def symbol_map_keys():
    c = read("constants.ts")
    block = c[c.index("SYMBOL_INFO_MAP"):]
    return set(re.findall(r"^	(\w+):\s*\{", block, re.M))


def check_symbols_mapped():
    cfg = read("config.ts")
    syms = (set(re.findall(r'"(\w+)":\s*\{\s*"paytable"', cfg)) | {"S"}) - {"M"}  # orbs: check_orbs_mapped
    missing = syms - symbol_map_keys()
    assert not missing, f"SYMBOL_INFO_MAP missing {sorted(missing)}"


def check_no_wild():
    c = read("constants.ts")
    board = c[c.index("INITIAL_BOARD"):c.index("BOARD_DIMENSIONS")]
    assert "'W'" not in board, "INITIAL_BOARD contains W"
    assert "W" not in symbol_map_keys(), "SYMBOL_INFO_MAP contains W"


def orb_values():
    gc = open(os.path.join(HERE, "..", "math-sdk", "games", game, "game_config.py"), encoding="utf-8").read()
    base = gc[gc.index("BASE_ORB_WEIGHTS = {"):].split("}", 1)[0]
    free = gc[gc.index("FREE_ORB_WEIGHTS = {"):].split("\n", 1)[0]
    return {int(v) for v in re.findall(r"(\d+):", base)} | {int(v) for v in re.findall(r"(\d+):", free.split("},", 1)[-1])}


def check_orbs_mapped():
    c = read("constants.ts")
    # each value (and bare padding "M") needs an entry in SYMBOL_INFO_MAP and MULTIPLIER_BACKGROUND_INFO_MAP
    # M_TAKEN_<v>: Board.svelte renames an orb to M_TAKEN after its value flies to the win counter
    keys = [f"{p}_{v}" for p in ("M", "M_TAKEN") for v in sorted(orb_values())] + ["M"]
    if not re.search(r"M_TAKEN\s*:", c):
        keys.append("M_TAKEN")  # bare padding orb renamed by Board.svelte
    missing = [k for k in keys if len(re.findall(r"\b%s\s*:" % k, c)) < 2]
    assert not missing, f"orb keys not in both symbol maps: {missing}"


def check_bet_modes_match_math():
    fe = dict(re.findall(r"mode:\s*'(\w+)',\s*costMultiplier:\s*([\d.]+)", read("betModes.ts")))
    math = {m["name"].upper(): float(m["cost"]) for m in json.load(open(os.path.join(PUB, "index.json")))["modes"]}
    assert {k: float(v) for k, v in fe.items()} == math, f"frontend modes {fe} != math {math}"
    layout = open(os.path.join(APP, "..", "routes", "+layout.svelte"), encoding="utf-8").read()
    assert "stateMeta.betModeMeta = getBetModeMeta()" in layout, "+layout.svelte does not install the bet mode meta"
    assert "http" not in read("betModes.ts"), "betModes.ts loads an external URL (Stake XSS rule)"


def book_event_types(limit=2000):
    """Event types in the first `limit` books of every mode (streamed: bonus books are GBs)."""
    import zstandard
    types = set()
    for m in json.load(open(os.path.join(PUB, "index.json")))["modes"]:
        with open(os.path.join(PUB, m["events"]), "rb") as f:
            for n, line in enumerate(io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(f), encoding="utf-8")):
                if n >= limit:
                    break
                types |= {e["type"] for e in json.loads(line)["events"]}
    return types


def check_all_events_handled():
    handled = set(re.findall(r"^\t(\w+): async", read("bookEventHandlerMap.ts"), re.M))
    missing = book_event_types() - handled
    assert not missing, f"no handler for book events {sorted(missing)} (each one logs a console error)"


def check_padding_symbols_mapped():
    # Padding symbols (above/below the grid) come from the reel strips without a multiplier value.
    cfg = json.load(open(os.path.join(HERE, "..", "math-sdk", "games", game, "library", "configs", f"config_fe_{game}.json")))
    names = {cell["name"] for reels in cfg["paddingReels"].values() for col in reels for cell in col}
    missing = names - symbol_map_keys() - {k for k in names if re.search(r"\b%s\s*:" % k, read("constants.ts"))}
    assert not missing, f"padding symbols with no SYMBOL_INFO_MAP entry: {sorted(missing)}"


def check_no_external_loads():
    # Stake XSS rule: the build is static files only, nothing fetched from other servers.
    html = open(os.path.join(APP, "..", "app.html"), encoding="utf-8").read()
    bad = re.findall(r"""(?:href|src)=["']https?://[^"']+""", html)
    assert not bad, f"app.html loads external resources: {bad}"


def check_resume_restores_running_mult():
    utils, handlers = read("utils.ts"), read("bookEventHandlerMap.ts")
    keep = utils[utils.index("BOOK_EVENT_TYPES_TO_RESERVE_FOR_SNAPSHOT"):].split("];", 1)[0]
    assert "'boardMultiplierInfo'" in keep, "resume snapshot drops boardMultiplierInfo (running multiplier resets to 1x)"
    # every custom bonus-state event the math emits must survive a resume (CRAZY NIGHT x10 start)
    assert "'runningMultStart'" in keep, "resume snapshot drops runningMultStart (CRAZY NIGHT resumes at 1x, wrong title)"
    snap = handlers[handlers.index("createBonusSnapshot:"):]
    assert "runningMult" in snap, "createBonusSnapshot does not restore the running multiplier"


def check_free_spin_gametype_kept():
    # reveal events say 'freegame' but the app checks 'freeSpins'; overwriting breaks bonus background and music
    h = read("bookEventHandlerMap.ts")
    reveal = h[h.index("\treveal: async"):h.index("\twinInfo: async")]
    assert "stateGame.gameType = bookEvent.gameType;" not in reveal.replace("if (stateGame.gameType !== 'freeSpins') stateGame.gameType = bookEvent.gameType;", ""), \
        "reveal overwrites stateGame.gameType during free spins"


SAMPLE_ASSET_DIRS = ["assets/fonts/goldFont/", "assets/fonts/silverFont/", "assets/fonts/purpleFont/", "assets/audio/sounds.json"]  # grows as each sample asset group is replaced


def check_no_sample_assets():
    a = read("assets.ts")
    used = [d for d in SAMPLE_ASSET_DIRS if d in a]
    assert not used, f"assets.ts still loads sample assets: {used}"


def check_engine_guidelines():
    """Engine approval guidelines that are easy to regress (see the Studio review prompt)."""
    layout = open(os.path.join(APP, "..", "routes", "+layout.svelte"), encoding="utf-8").read()
    assert "LoaderStakeEngine" not in layout, "[275] the Stake Engine loader is shown"
    static = os.path.join(APP, "..", "..", "static")
    assert not os.path.exists(os.path.join(static, "stake-engine-loader.gif")), "[275] stake-engine-loader.gif shipped"
    html = open(os.path.join(APP, "..", "app.html"), encoding="utf-8").read()
    assert "user-scalable=no" in html and "maximum-scale=1" in html, "[223] viewport allows double-tap zoom"
    rules = open(os.path.join(APP, "..", "components", "GameRules.svelte"), encoding="utf-8").read()
    assert "Stake Engine" not in rules, "[77] disclaimer says Stake (restricted in social mode)"
    for control in ("STOP", "EXIT", "SETTINGS", "SOUND", "INFO", "AUTO SPIN", "TURBO", "MENU"):
        assert control in rules, f"[235] rules do not explain the {control} control"


CHECKS = [check_engine_guidelines, check_no_sample_assets, check_no_external_loads, check_resume_restores_running_mult, check_free_spin_gametype_kept,
          check_padding_symbols_mapped, check_config_matches_math, check_symbols_mapped, check_no_wild, check_orbs_mapped, check_bet_modes_match_math,
          check_all_events_handled]

if __name__ == "__main__":
    failed = []
    for check in CHECKS:
        try:
            check()
            print("PASS", check.__name__)
        except (AssertionError, FileNotFoundError) as e:
            failed.append(check.__name__)
            print("FAIL", check.__name__, "-", e)
    sys.exit(1 if failed else 0)
