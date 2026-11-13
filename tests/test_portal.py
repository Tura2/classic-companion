"""The game's portal sprite: frames lined up on their origins, and nothing breaks when it can't be had."""
from PIL import Image

import gamedata


def test_frames_line_up_on_their_origins():
    a, b = Image.new("RGBA", (87, 182)), Image.new("RGBA", (85, 256))
    frames, anchor = gamedata.compose_frames([(a, (43, 173)), (b, (41, 248))])
    assert anchor == (43, 248) and {f.size for f in frames} == {(87, 257)}


def test_portal_sprite_none_when_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)

    def offline(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(gamedata.requests, "get", offline)
    assert object.__new__(gamedata.GameData).portal_sprite() is None


def test_portal_sprite_built_once_and_kept(tmp_path, monkeypatch):
    import base64
    import io
    buf = io.BytesIO()
    Image.new("RGBA", (10, 20), (0, 0, 255, 255)).save(buf, "PNG")
    png = base64.b64encode(buf.getvalue()).decode()

    class R:
        def __init__(self, url):
            self.url = url
        def raise_for_status(self):
            pass
        def json(self):
            return {"value": {"x": 5, "y": 18}} if self.url.endswith("/origin") else {"value": png}
    calls = []
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)
    monkeypatch.setattr(gamedata.requests, "get", lambda url, **k: calls.append(url) or R(url))
    g = object.__new__(gamedata.GameData)
    path = g.portal_sprite()
    assert path and path.exists() and gamedata.portal_meta() == {"anchor": [5, 18], "size": [10, 20]}
    n = len(calls)
    assert g.portal_sprite() == path and len(calls) == n            # the second time: from disk


def test_a_failed_download_isnt_retried_at_once(tmp_path, monkeypatch):
    calls = []

    def offline(*a, **k):
        calls.append(1)
        raise OSError("offline")
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)
    monkeypatch.setattr(gamedata.requests, "get", offline)
    g = object.__new__(gamedata.GameData)
    assert g.portal_sprite() is None and g.portal_sprite() is None
    assert len(calls) == 1            # the second ask in a row doesn't go to the network again


def _png():
    import base64
    import io
    buf = io.BytesIO()
    Image.new("RGBA", (40, 43), (150, 150, 150, 255)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_tomb_is_kept_once(tmp_path, monkeypatch):
    png = _png()

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": png}
    calls = []
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)
    monkeypatch.setattr(gamedata.requests, "get", lambda url, **k: calls.append(url) or R())
    g = object.__new__(gamedata.GameData)
    path = g.tomb_sprite()
    assert path and path.exists() and Image.open(path).size == (40, 43)
    assert calls == [gamedata.TOMB_URL]
    assert g.tomb_sprite() == path and len(calls) == 1               # the second time: from disk


def test_tomb_offline_waits_before_trying_again(tmp_path, monkeypatch):
    calls = []

    def offline(*a, **k):
        calls.append(1)
        raise OSError("offline")
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)
    monkeypatch.setattr(gamedata.requests, "get", offline)
    g = object.__new__(gamedata.GameData)
    assert g.tomb_sprite() is None and g.tomb_sprite() is None
    assert len(calls) == 1
