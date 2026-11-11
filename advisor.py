"""
Sell or keep: one verdict per item in your inventory, from data only (no screen reading needed).

  verdict(name, count, profile, data, market) -> {"verdict", "why", "price"}

verdict is "keep", "npc" (sell to an NPC), "fm" (sell on the Free Market), "drop" (untradable and
no NPC buys it) or "unknown". price is per item, or None. Rules, first match wins: you starred it;
a quest you have going needs it; a one-time quest you can take within LEVELS_AHEAD levels (its earlier
quests done) needs it; gear
you'll wear; untradable; then the NPC price against the Free Market's (after its 3% fee). Nothing
is guessed: a price no source gives is said to be unknown.
"""
# ---- thresholds
LEVELS_AHEAD = 10       # keep items for quests you can take this many levels from now
FM_FEE = 0.03           # the game takes 3% of every player-shop sale
NPC_IS_ENOUGH = 0.8     # an NPC paying this share of the FM price (after fee) wins: no hassle, no wait
LIQUID_VOL = 10         # sales on the last full day...
LIQUID_ST = 0.5         # ...and the share of listings that sell, for "sells fast"

fmt = "{:,}".format

# ammo by item id range (OSMS ids), and the jobs that shoot it
AMMO = [((2060000, 2060999), "arrows", ("Bowman", "Hunter", "Ranger", "Bow Master")),
        ((2061000, 2061999), "arrows", ("Bowman", "Crossbowman", "Sniper", "Marksman")),
        ((2070000, 2070999), "throwing stars", ("Thief", "Assassin", "Hermit", "Night Lord")),
        ((2330000, 2330999), "bullets", ("Pirate", "Gunslinger", "Outlaw", "Corsair"))]
POTIONS = (2000000, 2002999)    # HP and MP potions


def _quest_need(name, q):
    for r in q.get("requirements_list") or []:
        if r.get("type") == "item" and r.get("name") == name:
            return r.get("count") or 1
    return None


def _rotating(q):
    """A weekly board quest, one of a pool picked each week: only worth keeping for once it's in your log."""
    rot = q.get("rotation") or {}
    return bool(rot) and rot.get("one_time") is False


def _earlier_done(q, done):
    """Every quest this one needs finished first is done."""
    return all(str(r.get("id")) in done for r in q.get("requirements_list") or []
               if r.get("type") == "quest" and r.get("state") == 2)


def _fm_price(name, market):
    """The conservative Free Market price: the lower of MSC's median and Cozy's, or None."""
    prices = [p for p in ((market.items.get(name) or {}).get("p"), (market.cozy.get(name) or {}).get("price")) if p]
    return min(prices) if prices else None


def _wears(name, profile, data):
    try:
        g = data.gear(profile.get("job") or "Beginner", int(profile.get("level") or 1))
    except Exception:
        return False
    return any(e.get("name") == name for s in g.get("slots", []) for e in s.get("now", []) + s.get("soon", []))


def short(v):
    """The verdict in a few words, for the strip under the game's item tooltip; None: nothing to add."""
    if not v or v["verdict"] == "unknown":
        return None
    if v["verdict"] == "keep":
        why = v["why"] if len(v["why"]) <= 44 else v["why"][:43] + "…"
        return f"KEEP · {why}"
    if v["verdict"] == "npc":
        return f"SELL TO NPC {fmt(v['price'])}"
    if v["verdict"] == "drop":
        return "DROP IT"
    return f"SELL ON FM ~{fmt(v['price'])} · {'fast' if v['why'].startswith('Sells fast') else 'slow'}"


def _npc_why(npc, count, known):
    return f"An NPC pays {fmt(npc)} each" + (f" ({fmt(npc * count)} for {count})" if known and count > 1 else "")


def verdict(name, count, profile, data, market, untradable=False):
    """count: how many you have, or None when unknown (an item hovered, not counted)."""
    known = count is not None
    count = max(1, int(count or 1))
    keep = lambda why: {"verdict": "keep", "why": why, "price": None}
    if name in (profile.get("starred") or []):
        return keep("You starred it")
    by_id = {str(q.get("id")): q for q in data.quest_list}
    done = set(map(str, profile.get("quests_done") or []))
    active = [str(a.get("id")) for a in profile.get("quests_active") or [] if a.get("id")]
    for qid in active:
        q = by_id.get(qid)
        need = q and _quest_need(name, q)
        if need:
            return {**keep(f"{q['name']}: need {need}" + (f", have {count}" if known else "")), "quest_id": str(q["id"])}
    level = int(profile.get("level") or 1)
    soon = [q for q in data.quest_list if str(q.get("id")) not in done and str(q.get("id")) not in active
            and (q.get("level_min") or 0) <= level + LEVELS_AHEAD and _quest_need(name, q)
            and not _rotating(q) and _earlier_done(q, done)]
    if soon:
        q = min(soon, key=lambda q: q.get("level_min") or 0)
        return {**keep(f"For {q['name']} at level {q.get('level_min') or 1}"), "quest_id": str(q["id"])}
    if _wears(name, profile, data):
        return keep("Gear you'll wear, now or soon")
    iid = (getattr(data, "item_ids", None) or {}).get(name)
    job = profile.get("job") or ""
    for (lo, hi), what, jobs in AMMO:
        if iid and lo <= iid <= hi and job in jobs:
            return keep(f"Your {what}: you shoot these")
    if iid and POTIONS[0] <= iid <= POTIONS[1]:
        return keep("Potions: you drink these")
    npc = data.npc_price(name)
    if untradable:
        if npc:
            return {"verdict": "npc", "why": f"Untradable. An NPC pays {fmt(npc)} each", "price": npc}
        return {"verdict": "drop", "why": "Untradable, and no NPC buys it", "price": None}
    fm = _fm_price(name, market)
    if fm is None:
        if npc:
            return {"verdict": "npc", "why": _npc_why(npc, count, known), "price": npc}
        return {"verdict": "unknown", "why": "No market data. Check it yourself.", "price": None}
    net = round(fm * (1 - FM_FEE))
    if net < 1:
        if npc:
            return {"verdict": "npc", "why": _npc_why(npc, count, known), "price": npc}
        return {"verdict": "unknown", "why": f"Worth under 1 meso each on the FM ({fm}): not worth a shop slot",
                "price": fm}
    m = market.items.get(name) or {}
    liquid = (m.get("vol") or 0) >= LIQUID_VOL and (m.get("st") or 0) >= LIQUID_ST
    if npc and (npc >= NPC_IS_ENOUGH * net or not liquid):
        return {"verdict": "npc", "why": _npc_why(npc, count, known), "price": npc}
    why = f"{'Sells fast' if liquid else 'Sells slowly'} at about {fmt(fm)} each ({fmt(net)} after the 3% fee)"
    if not npc:
        why += ". NPC price unknown"
    if name in getattr(data, "equip_names", ()):
        why += ". Check its stats: scrolled or high stats sell for more."
    return {"verdict": "fm", "why": why, "price": fm}
