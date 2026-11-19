"""
Companion keeps itself up to date: when it starts (installed copies only), it asks GitHub for the
latest release; if that's newer and has CompanionSetup.exe, it downloads the setup into
cache\\updates\\, checks its size and SHA-256 against what GitHub publishes, runs it silently with
/UPDATE and closes. The setup waits for Companion to close, installs over it (data\\ stays) and
starts it again. No internet, no answer or a bad download: Companion just starts as it is.
"""
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

API = "https://api.github.com/repos/Tura2/classic-companion/releases/latest"
ASSET = "CompanionSetup.exe"
TIMEOUT = 3          # seconds: an update check never holds up the start for long


@dataclass
class Update:
    version: str
    url: str
    size: int
    sha256: str | None


def version_tuple(text):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer(tag, current):
    a, b = version_tuple(tag), version_tuple(current)
    return bool(a and b and a > b)


def latest_release():
    r = requests.get(API, timeout=TIMEOUT, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    return r.json()


def find(get_release, current):
    """The update to install, or None (not newer, no setup in the release, or no answer)."""
    try:
        rel = get_release()
    except Exception:
        return None
    if not rel or rel.get("draft") or rel.get("prerelease") or not newer(rel.get("tag_name"), current):
        return None
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == ASSET), None)
    if not asset:
        return None
    digest = asset.get("digest") or ""
    return Update(version=".".join(map(str, version_tuple(rel["tag_name"]))), url=asset["browser_download_url"],
                  size=int(asset.get("size") or 0), sha256=digest[7:] if digest.startswith("sha256:") else None)


def fetch(url):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def download(update, folder, fetch=fetch):
    """The setup, saved only when its size and hash match the release."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    body = fetch(update.url)
    if update.size and len(body) != update.size:
        raise ValueError(f"the download is {len(body)} bytes, the release says {update.size}")
    if update.sha256 and hashlib.sha256(body).hexdigest() != update.sha256:
        raise ValueError("the download doesn't match the release's SHA-256")
    path = folder / f"CompanionSetup-{update.version}.exe"
    tmp = path.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(path)
    return path


def clean(folder, current):
    """Setups for this version or older aren't needed any more."""
    for p in Path(folder).glob("CompanionSetup-*.exe"):
        v = p.stem[len("CompanionSetup-"):]
        if not newer(v, current):
            try:
                p.unlink()
            except OSError:
                pass


def run_setup(path):
    """Start the setup on its own (it outlives Companion) and return; Companion then closes."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE"],
                     creationflags=flags, close_fds=True)
