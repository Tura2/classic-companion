"""Sell or keep remembers the items you hovered (or read off an inventory tab), the newest
sniper.HOVER_KEEP only, so the list never grows without end."""
import sniper

N = sniper.HOVER_KEEP


def test_hovered_keeps_the_newest():
    state = {}
    for i in range(N + 12):
        sniper.note_hovered(state, [{"name": f"Item {i}"}])
    assert len(state["hovered"]) == N and f"Item {N + 11}" in state["hovered"] and "Item 0" not in state["hovered"]


def test_hovering_again_keeps_an_old_item():
    state = {}
    for i in range(N):
        sniper.note_hovered(state, [{"name": f"Item {i}"}])
    sniper.note_hovered(state, [{"name": "Item 0"}])      # hovered again: now the newest
    sniper.note_hovered(state, [{"name": "New"}])
    assert "Item 0" in state["hovered"] and "Item 1" not in state["hovered"]
