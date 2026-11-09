"""Sell or keep remembers the items you hovered, the newest 48 only, so the list never grows without end."""
import sniper


def test_hovered_keeps_the_newest_48():
    state = {}
    for i in range(60):
        sniper.note_hovered(state, [{"name": f"Item {i}"}])
    assert len(state["hovered"]) == 48 and "Item 59" in state["hovered"] and "Item 0" not in state["hovered"]


def test_hovering_again_keeps_an_old_item():
    state = {}
    for i in range(48):
        sniper.note_hovered(state, [{"name": f"Item {i}"}])
    sniper.note_hovered(state, [{"name": "Item 0"}])      # hovered again: now the newest
    sniper.note_hovered(state, [{"name": "New"}])
    assert "Item 0" in state["hovered"] and "Item 1" not in state["hovered"]
