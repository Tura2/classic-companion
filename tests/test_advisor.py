"""Sell or keep: a verdict per item, from the profile, the game data and the market. Never a made-up price."""
from types import SimpleNamespace

import advisor

JANE = {"id": "10002", "name": "Jane and the Mushroom", "level_min": 20,
        "requirements_list": [{"type": "item", "name": "Blue Mushroom Cap", "count": 15}]}
LATER = {"id": "2", "name": "Later Quest", "level_min": 38,
         "requirements_list": [{"type": "item", "name": "Fire Boar's Tooth", "count": 30}]}
FAR = {"id": "3", "name": "Far Quest", "level_min": 70,
       "requirements_list": [{"type": "item", "name": "Iron Ore", "count": 5}]}


def data(npc=None, gear=()):
    npc = npc or {}
    return SimpleNamespace(quest_list=[JANE, LATER, FAR], npc_price=lambda n: npc.get(n),
                           gear=lambda job, level: {"slots": [{"slot": "Hat", "now": [{"name": g} for g in gear], "soon": []}]},
                           equip_names={"Blue Bamboo Hat", "Bazlud"},
                           item_ids={"Arrows for Bows": 2060000, "Subi Throwing-Stars": 2070000, "Red Potion": 2000000,
                                     "Leather": 4000049})


def market(items=None, cozy=None):
    cozy = cozy or {}
    return SimpleNamespace(items=items or {}, cozy=SimpleNamespace(get=lambda n: cozy.get(n)))


def prof(**kw):
    return {"job": "Hunter", "level": 32, "quests_active": [], "quests_done": [], "starred": [], **kw}


def test_starred_is_kept():
    v = advisor.verdict("Iron Ore", 5, prof(starred=["Iron Ore"]), data(), market())
    assert v == {"verdict": "keep", "why": "You starred it", "price": None}


def test_quest_in_progress_keeps_it():
    v = advisor.verdict("Blue Mushroom Cap", 4, prof(quests_active=[{"id": "10002", "name": "Jane and the Mushroom"}]),
                        data(), market())
    assert v["verdict"] == "keep" and v["why"] == "Jane and the Mushroom: need 15, have 4"


def test_quest_within_ten_levels_keeps_it():
    v = advisor.verdict("Fire Boar's Tooth", 3, prof(), data(), market())
    assert v["verdict"] == "keep" and v["why"] == "For Later Quest at level 38"
    far = advisor.verdict("Iron Ore", 3, prof(), data(npc={"Iron Ore": 20}), market())
    assert far["verdict"] != "keep"          # level 70 is too far off


def test_gear_you_will_wear_is_kept():
    v = advisor.verdict("Blue Bamboo Hat", 1, prof(), data(gear=["Blue Bamboo Hat"]), market())
    assert v["verdict"] == "keep" and "wear" in v["why"]


def test_npc_pays_nearly_as_much_sell_to_npc():
    m = market({"Opal Ore": {"p": 200, "st": 0.9, "vol": 400}})
    v = advisor.verdict("Opal Ore", 10, prof(), data(npc={"Opal Ore": 160}), m)
    assert v == {"verdict": "npc", "why": "An NPC pays 160 each (1,600 for 10)", "price": 160}


def test_liquid_and_worth_more_sell_on_fm_after_the_fee():
    m = market({"Iron Ore": {"p": 300, "st": 0.88, "vol": 900}}, {"Iron Ore": {"price": 320}})
    v = advisor.verdict("Iron Ore", 10, prof(), data(npc={"Iron Ore": 20}), m)
    assert v["verdict"] == "fm" and v["price"] == 300
    assert v["why"] == "Sells fast at about 300 each (291 after the 3% fee)"


def test_not_liquid_with_an_npc_price_goes_to_npc():
    m = market({"Odd Thing": {"p": 5000, "st": 0.1, "vol": 2}})
    v = advisor.verdict("Odd Thing", 1, prof(), data(npc={"Odd Thing": 900}), m)
    assert v["verdict"] == "npc"


def test_equip_on_fm_says_check_its_stats():
    m = market({"Bazlud": {"p": 25000, "st": 0.7, "vol": 40}})
    v = advisor.verdict("Bazlud", 1, prof(), data(npc={"Bazlud": 4500}), m)
    assert v["verdict"] == "fm" and v["why"].endswith("Check its stats: scrolled or high stats sell for more.")


def test_no_data_says_so():
    v = advisor.verdict("Mystery", 1, prof(), data(), market())
    assert v == {"verdict": "unknown", "why": "No market data. Check it yourself.", "price": None}


def test_untradable_goes_to_npc_or_drop():
    v = advisor.verdict("Quest Thing", 1, prof(), data(npc={"Quest Thing": 5}), market(), untradable=True)
    assert v["verdict"] == "npc"
    v = advisor.verdict("Quest Thing", 1, prof(), data(), market(), untradable=True)
    assert v["verdict"] == "drop"


def test_fm_price_but_no_npc_price_says_so():
    m = market({"Rare Etc": {"p": 50000, "st": 0.2, "vol": 3}})
    v = advisor.verdict("Rare Etc", 1, prof(), data(), m)
    assert v["verdict"] == "fm" and "Sells slowly" in v["why"] and "NPC price unknown" in v["why"]


# live, 2026-11-07: a Hunter's "Arrows for Bows" came out "SELL ON FM ~0.5"
def test_your_own_ammo_is_kept():
    v = advisor.verdict("Arrows for Bows", None, prof(), data(), market({"Arrows for Bows": {"p": 0.5, "vol": 900, "st": 1}}))
    assert v["verdict"] == "keep" and "arrows" in v["why"]


def test_someone_elses_ammo_is_not_kept_for_you():
    v = advisor.verdict("Subi Throwing-Stars", None, prof(), data(), market({"Subi Throwing-Stars": {"p": 300, "vol": 50, "st": 1}}))
    assert v["verdict"] == "fm"


def test_potions_are_kept():
    assert advisor.verdict("Red Potion", 30, prof(), data(), market({"Red Potion": {"p": 20}}))["verdict"] == "keep"


def test_under_a_meso_after_the_fee_is_no_fm_sale():
    v = advisor.verdict("Leather", None, prof(job="Magician"), data(), market({"Leather": {"p": 0.5, "vol": 900, "st": 1}}))
    assert v["verdict"] == "unknown" and advisor.short(v) is None
