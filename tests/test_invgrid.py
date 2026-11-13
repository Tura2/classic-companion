"""The inventory's open tab read slot by slot (invgrid): which tab is open, which item is in each
slot by its picture, and those items joining Sell or keep's list."""
import numpy as np
import pytest
from PIL import Image

from casekit import CASES

import gamedata
import invgrid
import sniper

TITLE = ("ITEM INVENTORY", 1011, 383, 113, 8)
ICONS = gamedata.CACHE / "icons"


def frame_with_tab(tab):
    f = Image.new("RGB", (1920, 1200), (200, 200, 200))
    x, y = TITLE[1] + invgrid.TABS[tab], TITLE[2] + invgrid.TAB_Y
    f.paste((220, 60, 70), (x - 20, y - 8, x + 20, y + 8))
    return f


@pytest.mark.parametrize("tab", ["Equip", "Use", "Etc", "Deco"])
def test_the_red_tab_is_the_open_one(tab):
    assert invgrid.open_tab(frame_with_tab(tab), TITLE, 1.0) == tab


def test_no_red_tab_no_tab():
    assert invgrid.open_tab(Image.new("RGB", (1920, 1200), (200, 200, 200)), TITLE, 1.0) is None


def test_thirty_slots_at_any_size():
    grid = Image.new("RGB", (round(56.25 * 4 + 50) * 2, round(53.2 * 5 + 50) * 2), tuple(int(v) for v in invgrid.BG))
    got = invgrid.slots(grid)
    assert [i for i, _ in got] == list(range(30))
    assert all(top.shape == (invgrid.SLOT - invgrid.BAND, invgrid.SLOT, 3) for _, top in got)


def test_an_empty_slot_is_nothing():
    bag = invgrid.Bag({}, lambda i: "", ICONS)
    assert bag.match(np.broadcast_to(invgrid.BG, (31, 50, 3)).copy(), "Etc") is None


def test_items_off_the_tab_join_sell_or_keep():
    state = {"hovered": {"Leather": {"ts": 1, "untradable": True}}}
    sniper.note_bag(state, [{"name": "Leather"}, {"name": "Wild Boar Tooth", "alt": "Fire Boar's Tooth"}])
    assert state["hovered"]["Leather"] == {"ts": 1, "untradable": True}      # the tooltip already said it
    tooth = state["hovered"]["Wild Boar Tooth"]
    assert tooth["bag"] and tooth["alt"] == "Fire Boar's Tooth"


def test_a_hover_settles_a_bag_item():
    state = {}
    sniper.note_bag(state, [{"name": "Wild Boar Tooth", "alt": "Fire Boar's Tooth"}])
    sniper.note_hovered(state, [{"name": "Wild Boar Tooth"}])
    assert "bag" not in state["hovered"]["Wild Boar Tooth"]


ETC = ["Bronze Ingot", "Horny Mushroom Cap", "Leaf", "Blue Dye", "Lupin's Banana", "Leather", "Animal Fur Bundle",
       "Fragment of Magic", "Charm of the Undead", "Stiff Feather", "Coconut", "Lupin Doll", "Lorang Claw", "Clang Claw",
       "Opal Ore", "Wild Boar Tooth", "Adamantium Ore", "Firewood", "Wild Boar Tooth", "Processed Wood", "Gold Ore",
       "Emerald Ore", "Bronze Ore", "Tree Branch", "Red Snail Shell", "Wild Boar Tooth", "Orihalcon Ore"]
USE = ["Bronze Arrows for Bows"] * 9 + ["Orange Potion", "Blue Potion", "Warrior Potion", "Dexterity Potion", "Lemon",
       "Sap of Ancient Tree", "Pet Food", "Return Scroll - Nearest Town", "Return Scroll to Lith Harbor",
       "Return Scroll to Ellinia", "Return Scroll to Perion", "Return Scroll to Henesys", "Return Scroll to Kerning City",
       "Return Scroll to Sleepywood", None, "Lemon", "Arrows for Bows", "Arrows for Crossbows"]


EQUIP = ["Cap of Memories", "White Undershirt", "Blue Jean Shorts", "Blue Jean Shorts", "Brown Cotton Shorts",
         "Red Knucklevest Pants", "Leather Sandals", "Blue Rubber Boots", "Old Raggedy Cape", "Pumpkin Basket", "Hand Axe",
         "Forked Dagger", "Beginner's War Bow", "Dark Master Sergeant", "Purple Steal Pants"]


@pytest.mark.skipif(not ICONS.exists() or not (CASES / "inventory_etc.png").exists(), reason="no cases or icons on this PC")
@pytest.mark.parametrize("case, tab, want", [("inventory_etc", "Etc", ETC), ("inventory_use", "Use", USE),
                                             ("inventory_equip", "Equip", EQUIP)])
def test_a_real_tab(game_reader, case, tab, want):
    frame = Image.open(CASES / f"{case}.png").convert("RGB")
    title = game_reader.titles.find(frame, 1.0, None, {"inventory"})["inventory"]
    assert invgrid.open_tab(frame, title, 1.0) == tab
    bag = invgrid.Bag(game_reader.data.bag_items, lambda i: "", ICONS)
    got = bag.read(frame.crop(invgrid.grid_box(title, 1.0)), tab)
    names = [g["name"] for g in got]
    assert len(names) == len(want)
    assert all(w is None or n == w for n, w in zip(names, want))     # None: two Chaos scrolls look the same
    teeth = [g for g in got if g["name"] == "Wild Boar Tooth"]
    assert all(g["alt"] == "Fire Boar's Tooth" for g in teeth)         # the same picture: both are said


@pytest.mark.skipif(not ICONS.exists() or not (CASES / "fm_quest_window.png").exists(), reason="no cases or icons on this PC")
def test_a_full_read_hands_over_the_tab(game_reader):
    seen = game_reader.read(Image.open(CASES / "fm_quest_window.png").convert("RGB"))
    inv = seen["inventory"]
    assert inv["tab"] == "Use" and inv["mesos"] == 385973
    got = invgrid.Bag(game_reader.data.bag_items, lambda i: "", ICONS).read(inv["grid"], "Use")
    names = [g["name"] for g in got]
    assert names.count("Return Scroll to Henesys") == 1 and "Green Malady's Candy" in names and "Elixir" in names


def test_icons_that_did_not_download_are_tried_again_later(tmp_path, monkeypatch):
    bag = invgrid.Bag({"Etc": [(4000000, "Snail Shell"), (4000001, "Blue Snail Shell")]}, lambda i: "", tmp_path)
    monkeypatch.setattr(bag, "_get", lambda iid: None)                    # offline
    assert bag.book("Etc") == [] and "Etc" in bag.retry
    monkeypatch.setattr(invgrid.time, "time", lambda: bag.retry["Etc"] + 1)
    asked = []
    monkeypatch.setattr(bag, "_get", lambda iid: asked.append(iid))
    bag.book("Etc")
    assert asked == [4000000, 4000001]                                      # after the wait: asked again
