"""Connect Discord and the Settings card's status, through companion.py's own functions."""
import companion
import discord_link

SERVER = {"url": "https://reports.example/api/report", "key": "k3y"}


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._body = code, body or {}

    def json(self):
        return self._body


def state_with_box(tmp_path):
    box = discord_link.Outbox(tmp_path / "outbox.json", lambda: None, lambda *a, **k: Resp(), lambda s: {})
    box.setup = SERVER
    return {"profile": {"name": "Hero1"}, "save_cfg": None, "outbox": box}


def test_status_wants_connect_again_for_an_old_link(tmp_path):
    st = companion.discord_status(state_with_box(tmp_path), {"discord_id": "123", "discord_name": "Tura", "discord_enabled": True},
                                  8765, fetch=lambda: None)
    assert st["setup"] is True and st["linked"] is False and st["relink"] is True


def test_status_of_a_linked_player(tmp_path):
    cfg = {"discord_id": "123", "discord_name": "Tura", "discord_card": "v1.123.1.s", "discord_enabled": True,
           "discord_post_sales": True, "discord_post_grind": True, "discord_post_drops": False}
    st = companion.discord_status(state_with_box(tmp_path), cfg, 8765, fetch=lambda: {"client_id": "999", "on": True})
    assert st["linked"] is True and st["relink"] is False
    assert st["post_sales"] is True and st["post_grind"] is True and st["post_drops"] is False
    assert "client_id=999" in st["authorize"]


def test_link_unreachable_keeps_nothing(tmp_path):
    def down(*a, **k):
        raise OSError("no internet")
    cfg = {}
    code, body = companion.link_discord(state_with_box(tmp_path), cfg, "tok", post=down)
    assert code == 502 and "Couldn't reach" in body["error"]
    assert "discord_card" not in cfg and "discord_id" not in cfg


def test_link_keeps_the_card_and_says_hello(tmp_path):
    st = state_with_box(tmp_path)
    cfg = {}
    code, body = companion.link_discord(st, cfg, "tok", post=lambda *a, **k: Resp(200, {"id": "123", "name": "Tura", "card": "v1.123.1.s"}))
    assert code == 200 and body == {"name": "Tura"}
    assert cfg["discord_card"] == "v1.123.1.s" and cfg["discord_id"] == "123" and cfg["discord_enabled"] is True
    assert cfg["discord_post_sales"] is True and not cfg.get("discord_post_grind") and not cfg.get("discord_post_drops")
    assert [(e["kind"], e["item"]) for e in st["outbox"].queue] == [("notice", {"what": "connected"})]
