"""
Companion for MapleStory Classic World.

  Companion.exe  (or: python companion.py)

Opens a dashboard in your browser on this PC (localhost only).
Out of the box it only uses public game data and prices: it doesn't touch the game or your screen.
Screen reading and on-game drawing are optional and switched on in the Settings tab.

  --report     prices you've seen yourself, per item (needs screen reading)
  --refresh    re-download game data now
  --no-browser don't open the dashboard automatically
"""
import json
import queue
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cozy
from gamedata import JOBS, GameData

from paths import APP_DIR, RES_DIR, load_json, save_json

HERE = APP_DIR
PROFILE = HERE / "profile.json"
PORT = 8765

DEFAULT_PROFILE = {"job": "Beginner", "level": 10, "mesos": 80000, "acc": None, "skill_plan": {},
                   "current_map": None, "quests_done": [], "island": None,
                   # filled in by screen reading: what the game itself shows
                   "name": None, "skills_now": {}, "sp": None, "quests_active": []}


def load_profile():
    p = dict(DEFAULT_PROFILE)
    p.update(load_json(PROFILE, {}))
    return p


def save_profile(state):
    state["profile"]["rev"] = state["profile"].get("rev", 0) + 1   # lets the dashboard notice changes
    save_json(PROFILE, state["profile"])


def on_island(data, prof):
    return data.on_maple_island(int(prof["level"]), prof.get("current_map"), prof.get("island"))


def set_current(data, state, mid):
    """Record the map you're on and move the active route to it."""
    state["profile"]["current_map"] = mid
    save_profile(state)
    nav = state.get("nav")
    if nav:
        ids = [s["id"] for s in nav["steps"]]
        if mid in ids:
            nav["i"] = ids.index(mid)
        else:   # wandered off the route: re-plan from here
            steps = data.route(mid, nav["to"]["id"])
            if steps:
                if nav["steps"][-1].get("npc"):     # keep the NPC circled on the last map
                    steps[-1]["npc"] = nav["steps"][-1]["npc"]
                nav["steps"], nav["i"] = steps, 0
    state["queue"].put(("nav",))


def guide_plan(data, state):
    """The quest guide: where to go for the guided quest's next step. Hunt the quest's monsters
    where most of them live (quest items usually drop from those) until the Quest Helper shows every
    count done, then go back to the quest's NPC. Sets the route, which the route card on the game
    and the Go to tab show, with the quest's counts on top."""
    g = state.get("guide")
    if not g:
        return
    q = data.quest(g["id"])
    if not q or str(g["id"]) in {str(x) for x in state["profile"].get("quests_done", [])}:
        # gone, or finished: the Quest window's Completed tab, or Done in the dashboard, also ends
        # it when the "Quest Complete!" notice was missed
        state["guide"] = None
        if q and state.get("nav") and state["nav"].get("guide_to"):
            state["nav"] = None
            state["queue"].put(("nav",))
        return
    reqs = [r for r in q.get("requirements_list") or [] if r.get("type") in ("mob", "item") and r.get("count")]
    helper = next((h for h in (state.get("game") or {}).get("helper") or [] if h.get("id") == g["id"]), None)
    have = {n["what"]: n["have"] for n in (helper or {}).get("needs", [])}
    needs = [{"what": r["name"], "have": have.get(r["name"]), "need": r["count"], "kind": r["type"]} for r in reqs]
    left = [n for n in needs if n["have"] is None or n["have"] < n["need"]]
    target, npc = None, None
    turn_name = q["npc_name"]
    if left:
        mobs = [r for r in reqs if r["type"] == "mob"]
        hunt = next((r for r in mobs if r["name"] in {n["what"] for n in left}), mobs[0] if mobs else None)
        first = left[0]
        drops = data.drops.get(first["what"], []) if first["kind"] == "item" else []
        if first["kind"] == "item" and drops and not (hunt and hunt["name"] in {d["monster"] for d in drops}):
            # the item drops from a known monster: hunt that one where it lives
            hunt = {"name": drops[0]["monster"], "id": data.mob_ids.get(drops[0]["monster"])}
        where = data.mob_maps.get(hunt["id"]) if hunt else None
        target = where["map"] if where else None
        if first["kind"] == "mob":
            goal = f"Hunt {first['what']}"
        elif hunt:
            goal = f"Collect {first['what']} from {hunt['name']}"
        else:
            goal = f"Collect {first['what']}"
        if target is None:     # nothing to hunt for it: an item an NPC hands you, to deliver
            turn_name, _, npc = data.turn_in(q)
            target = npc["id"] if npc else None
            goal = f"Bring it to {turn_name}" if npc else goal
    else:
        turn_name, _, npc = data.turn_in(q)    # often someone other than who gave the quest
        target = npc["id"] if npc else None
        goal = f"Bring it to {turn_name}"
    info = {"id": g["id"], "name": q["name"], "goal": goal, "needs": needs, "done": not left,
            "tracked": helper is not None, "where": data.map_info(target) if target else None}
    g["info"] = info
    cur, nav = state["profile"].get("current_map"), state.get("nav")
    if target and cur in data.maps and (not nav or nav.get("guide_to") != target):
        steps = data.route(cur, target)
        if steps:
            if npc and npc["id"] == steps[-1]["id"]:
                steps[-1]["npc"] = {"x": npc["x"], "y": npc["y"], "name": turn_name}
            state["nav"] = {"steps": steps, "i": 0, "to": data.map_info(target), "guide_to": target}
    if state.get("nav") and state["nav"].get("guide_to") == target:
        state["nav"]["quest"] = info
    state["queue"].put(("nav",))


SETTINGS = ["screen_reading", "draw_overlay", "consent", "label_side", "row_tolerance", "name_match_min",
            "price_is_per_bundle", "sound", "auto_interval", "ocr_scale", "nav_corner", "game_title",
            "setup_done"]
DEFAULT_SETTINGS = {"screen_reading": False, "draw_overlay": False, "consent": False, "label_side": "right",
                    "row_tolerance": 14, "name_match_min": 84, "price_is_per_bundle": False, "sound": True,
                    "auto_interval": 2.0, "ocr_scale": 3, "nav_corner": "top-right", "game_title": "MapleStory",
                    "setup_done": False}
RANGES = {"row_tolerance": (4, 60), "name_match_min": (50, 100), "auto_interval": (2.0, 10.0), "ocr_scale": (1, 6)}
CHOICES = {"label_side": ("right", "left", "inside"), "nav_corner": ("top-right", "bottom-right", "bottom-left", "top-left")}


def clean_setting(k, v):
    """The value to store for setting k, or None to ignore it. Keeps scans slow whatever is sent."""
    default = DEFAULT_SETTINGS[k]
    if isinstance(default, bool):
        return v if isinstance(v, bool) else None
    if k in RANGES:
        lo, hi = RANGES[k]
        try:
            return type(default)(min(hi, max(lo, float(v))))
        except (TypeError, ValueError):
            return None
    if k in CHOICES:
        return v if v in CHOICES[k] else None
    v = str(v).strip()[:80]       # game_title
    return v or None


def make_handler(data, state, cfg):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def trusted(self):
            """Only the dashboard itself may use the API: other web pages you visit could otherwise
            reach this port and, say, switch screen reading on (Host check also stops DNS rebinding)."""
            port = self.server.server_address[1]
            ok = {f"localhost:{port}", f"127.0.0.1:{port}"}
            if self.headers.get("Host", "") not in ok:
                return False
            origin = self.headers.get("Origin")
            if self.command == "POST":
                # a JSON content type can't be sent cross-site without a preflight, which we never answer
                if origin is not None and origin.removeprefix("http://") not in ok:
                    return False
                return (self.headers.get("Content-Type") or "").startswith("application/json")
            return origin is None or origin.removeprefix("http://") in ok

        def send(self, code, body, ctype="application/json"):
            if isinstance(body, bytes):
                raw = body
            else:
                for attempt in range(3):
                    try:    # the screen reader may be adding to these dicts at this very moment
                        raw = json.dumps(body).encode("utf-8")
                        break
                    except RuntimeError:
                        if attempt == 2:
                            raise
                        time.sleep(0.02)
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: C901
            if not self.trusted():
                return self.send(403, {"error": "forbidden"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            prof = state["profile"]
            try:
                if url.path == "/":
                    return self.send(200, (RES_DIR / "web" / "index.html").read_bytes(), "text/html")
                if url.path == "/api/state":
                    return self.send(200, {"profile": prof, "jobs": list(JOBS), "live": state["live"],
                                           "game": state.get("game") or {}, "has_frame": bool(state.get("frame")),
                                           "deals": state["deals"], "overlay": state["overlay"],
                                           "screen": {"reading": bool(cfg.get("screen_reading")) and state["overlay"],
                                                      "drawing": bool(cfg.get("draw_overlay")) and state["overlay"]},
                                           "prices": data.market.updated, "nav": state["nav"],
                                           "cozy": {"updated": data.market.cozy.updated, "stale": data.market.cozy.stale,
                                                    "items": len(data.market.cozy.items)},
                                           "guide": (state.get("guide") or {}).get("info"),
                                           "on_island": on_island(data, prof),
                                           "current": data.map_info(prof["current_map"]) if prof.get("current_map") else None})
                if url.path == "/api/train":
                    return self.send(200, data.train(int(q.get("level", prof["level"])), prof.get("acc"), on_island(data, prof)))
                if url.path == "/api/gear":
                    return self.send(200, data.gear(prof["job"], int(prof["level"])))
                if url.path == "/api/skills":
                    now = prof.get("skills_now") or {}
                    return self.send(200, {"skills": data.skill_list(prof["job"]), "plan": prof.get("skill_plan", {}),
                                           "now": now, "sp": prof.get("sp"),
                                           "next": data.next_points(prof["job"], int(prof["level"]), now, prof.get("stats"))})
                if url.path == "/api/frame.jpg":     # the latest look at the game, for the Live tab
                    if not state.get("frame") or not cfg.get("screen_reading"):
                        return self.send(404, {"error": "no picture yet"})
                    return self.send(200, state["frame"], "image/jpeg")
                if url.path == "/api/seen":          # items you've passed in player shops
                    import sniper
                    return self.send(200, sniper.seen_items(data.market, data.item_img))
                if url.path == "/api/settings":
                    return self.send(200, {**{k: cfg.get(k) for k in SETTINGS}, "screen_available": state["overlay"],
                                           "areas": {"region": bool(cfg.get("region"))},
                                           "game_found": state.get("game_found"),
                                           "game_size": state.get("game_size") if state.get("game_found") else None,
                                           "capture": (state.get("live") or {}).get("capture", "off"),
                                           "capture_error": (state.get("live") or {}).get("capture_error", "")})
                if url.path == "/api/maps":
                    return self.send(200, data.find_maps(q.get("q", "")))
                if url.path == "/api/layout":
                    return self.send(200, data.layout(int(q["id"])))
                if url.path == "/api/nav":
                    return self.send(200, state["nav"])
                if url.path == "/api/quests":
                    helper = (state.get("game") or {}).get("helper") or []
                    active = [h.get("id") for h in helper] + [a.get("id") for a in prof.get("quests_active", [])]
                    return self.send(200, data.quests(int(prof["level"]), prof["job"], prof.get("quests_done", []),
                                                      on_island(data, prof), active))
                self.send(404, {"error": "not found"})
            except Exception as e:
                self.send(500, {"error": str(e)})

        def do_POST(self):
            if not self.trusted():
                return self.send(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                return self.post(urlparse(self.path).path, body)
            except (KeyError, TypeError, ValueError) as e:
                return self.send(400, {"error": f"Bad request: {e}"})
            except Exception as e:
                return self.send(500, {"error": str(e)})

        def post(self, path, body):  # noqa: C901
            if path == "/api/profile":
                prof = state["profile"]
                if body.get("job") in JOBS:
                    prof["job"] = body["job"]
                if "level" in body:
                    prof["level"] = min(200, max(1, int(body["level"])))
                if "mesos" in body:
                    prof["mesos"] = max(0, int(body["mesos"]))
                if "acc" in body:
                    prof["acc"] = int(body["acc"]) if str(body["acc"]).strip() not in ("", "None") else None
                if "island" in body and body["island"] in (True, False, None):
                    prof["island"] = body["island"]
                if isinstance(body.get("skill_plan"), dict):
                    prof["skill_plan"] = {k: max(0, int(v)) for k, v in body["skill_plan"].items()}
                save_profile(state)
                return self.send(200, prof)
            if path == "/api/settings":
                for k, v in body.items():
                    if k in SETTINGS and (v := clean_setting(k, v)) is not None:
                        cfg[k] = v
                refused = False
                if not cfg.get("consent"):
                    refused = cfg.get("screen_reading") and body.get("screen_reading") is True
                    cfg["screen_reading"] = False
                if not cfg.get("screen_reading"):
                    cfg["draw_overlay"] = False
                if state["save_cfg"]:
                    state["save_cfg"](cfg)
                state["queue"].put(("settings",))
                if refused:
                    return self.send(400, {"error": "Confirm the risk notice first."})
                return self.send(200, {k: cfg.get(k) for k in SETTINGS})
            if path == "/api/here":            # "I'm on this map"
                mid = int(body["id"])
                if mid not in data.maps:
                    return self.send(400, {"error": "Unknown map."})
                set_current(data, state, mid)
                return self.send(200, state["nav"] or {})
            if path == "/api/quest_done":
                done = set(str(x) for x in state["profile"].get("quests_done", []))
                (done.add if body.get("done", True) else done.discard)(str(body["id"]))
                state["profile"]["quests_done"] = sorted(done)
                save_profile(state)
                return self.send(200, {"ok": True})
            if path == "/api/nav":
                start, goal = int(body.get("from") or state["profile"].get("current_map") or 0), int(body["to"])
                if start not in data.maps:
                    return self.send(400, {"error": "Set where you are first, under Go to → Change where you are."})
                steps = data.route(start, goal)
                if not steps:
                    return self.send(404, {"error": "No walking route between these maps. You may need a taxi, boat or quest portal."})
                if body.get("npc_id") is not None:
                    place = data.npc_place(int(body["npc_id"]))
                    if place and place["id"] == steps[-1]["id"]:
                        steps[-1]["npc"] = {"x": place["x"], "y": place["y"], "name": body.get("npc_name", "")}
                state["nav"] = {"steps": steps, "i": 0, "to": data.map_info(goal)}
                state["guide"] = None          # a route you picked replaces the quest guide
                set_current(data, state, start)
                return self.send(200, state["nav"])
            if path == "/api/nav/step":
                if state["nav"]:
                    state["nav"]["i"] = max(0, min(len(state["nav"]["steps"]) - 1, int(body["i"])))
                    state["profile"]["current_map"] = state["nav"]["steps"][state["nav"]["i"]]["id"]
                    save_profile(state)
                    state["queue"].put(("nav",))
                return self.send(200, state["nav"] or {})
            if path == "/api/nav/stop":
                state["nav"], state["guide"] = None, None
                state["queue"].put(("nav",))
                return self.send(200, {})
            if path == "/api/guide":           # guide me through a quest in the game
                if body.get("stop") or not data.quest(body.get("id")):
                    state["guide"] = None
                    if state.get("nav") and state["nav"].get("guide_to"):
                        state["nav"] = None
                    state["queue"].put(("nav",))
                    return self.send(200, {})
                if not state["profile"].get("current_map"):
                    return self.send(400, {"error": "Set where you are first, under Go to → Change where you are."})
                state["guide"] = {"id": str(body["id"])}
                if state.get("nav"):
                    state["nav"].pop("guide_to", None)
                guide_plan(data, state)
                return self.send(200, state["guide"].get("info") or {})
            if path in ("/api/scan", "/api/auto", "/api/select", "/api/toggle", "/api/nav_corner"):
                if not state["overlay"] or not cfg.get("screen_reading"):
                    return self.send(409, {"error": "Screen reading is off. Turn it on in Settings."})
                state["queue"].put((path.rsplit("/", 1)[1],))
                return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})

    return Handler


class Server(ThreadingHTTPServer):
    # Python's HTTP server asks for SO_REUSEADDR, which on Windows lets a second copy bind a port
    # the first still holds, and then requests land on either copy
    allow_reuse_address = sys.platform != "win32"


def start_server(handler):
    for port in range(PORT, PORT + 10):
        try:
            return Server(("127.0.0.1", port), handler), port   # this PC only
        except OSError:
            continue
    raise SystemExit(f"Ports {PORT}-{PORT + 9} are all busy. Close other copies of Companion.")


def main():
    if "--report" in sys.argv:
        from sniper import report
        report()
        return

    print("Companion: loading game data and prices...")
    data = GameData(force="--refresh" in sys.argv)
    # Cozy Market's prices: brought up to date now and kept that way, in the background
    threading.Thread(target=cozy.keep_fresh, args=(data,), daemon=True).start()

    try:   # screen features need Windows + Tk; the dashboard works without them
        import sniper
        cfg = sniper.load_config()
        screen_ok = sys.platform == "win32"
    except Exception as e:
        print("Screen features unavailable:", e)
        sniper, cfg, screen_ok = None, dict(DEFAULT_SETTINGS), False

    state = {"profile": load_profile(), "queue": queue.Queue(), "auto": False,
             "live": {"rows": [], "note": "Screen reading is off", "auto": False, "region": False},
             "deals": [], "overlay": screen_ok, "nav": None,
             "save_cfg": sniper.save_config if sniper else None}
    state["set_current"] = lambda mid: set_current(data, state, mid)
    state["save_profile"] = lambda: save_profile(state)
    state["guide_tick"] = lambda: guide_plan(data, state)     # the screen reader calls it after each look

    server, port = start_server(make_handler(data, state, cfg))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local = f"http://localhost:{port}"
    print(f"\nDashboard: {local}\nClose this window to quit.\n")
    if "--no-browser" not in sys.argv:
        webbrowser.open(local)

    if not screen_ok:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    try:
        app = sniper.App(data, state, cfg)
    except Exception as e:      # no on-game windows (Tk failed): the dashboard still works
        print("Screen features unavailable:", e)
        state["overlay"] = False
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    app.run()
    server.shutdown()


if __name__ == "__main__":
    main()
