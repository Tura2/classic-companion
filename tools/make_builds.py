"""Usage: python tools/make_builds.py <class guides folder> builds.json cache/skills.json

Build companion/builds.json: the SP order from each class guide's SP allocation table.

Each guide's first table with a "Level | Spend | Running ..." header is the main plan. Every row is
expanded into single points, in order, each with the level it's meant for and the skill level it
brings that skill to. Skill names are matched to the game data's names for that job.
"""
import json, re, sys
from pathlib import Path
from rapidfuzz import fuzz, process

GUIDES, OUT, SKILLS = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
JOBS = {"warrior": ("Warrior", "warrior"), "fighter": ("Fighter", "warrior"), "page": ("Page", "warrior"),
        "spearman": ("Spearman", "warrior"), "magician": ("Magician", "magician"), "fp-wizard": ("F/P Wizard", "magician"),
        "il-wizard": ("I/L Wizard", "magician"), "cleric": ("Cleric", "magician"), "bowman": ("Archer", "archer"),
        "hunter": ("Hunter", "archer"), "crossbowman": ("Crossbowman", "archer"), "thief": ("Rogue", "rogue"),
        "assassin": ("Assassin", "rogue"), "bandit": ("Bandit", "rogue")}
skills = json.loads(SKILLS.read_text("utf-8"))
# Bandit's first table spends SP, resets and spends again; its no-reset plan reads as one run
AFTER = {"bandit": "(no Reset)"}
ALIAS = {"eye": "the eye of amazon", "pkb": "power knockback", "mg": "magic guard", "fa": "final attack"}


def table(md, after=None):
    """Rows of the first SP plan table (after a heading containing `after`, if given): header
    Level(s) | Spend | Running ... or Levels | Spend SP on | Result."""
    if after and after in md:
        md = md[md.index(after):]
    lines = md.split("\n")
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if (len(cells) >= 3 and cells[0].lower().startswith("level") and cells[1].lower().startswith("spend")
                and cells[2].lower().startswith(("running", "result"))):
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return rows
    return []


builds = {}
for slug, (job, fam) in JOBS.items():
    md = (GUIDES / f"{slug}-class-guide.md").read_text("utf-8")
    group = next(g for g in skills[fam] if g["class_name"] == job)
    names = [s["name"] for s in group["skills"]]
    steps, totals, table_rows = [], {}, []
    rows = table(md, AFTER.get(slug))
    # full names the table uses, so a bare "Booster" or "Mastery" means the one this build raises
    full = {hit[0] for _, spend, *_ in rows for name, _ in re.findall(r"([A-Za-z][A-Za-z' :/.\-]*?)\s*\+(\d+)", spend)
            if (hit := process.extractOne(name.strip(), names, scorer=fuzz.ratio, score_cutoff=90))}
    for lv_cell, spend, *_ in rows:
        m = re.match(r"(\d+)(?:\s*[-–]\s*(\d+))?", lv_cell)
        if not m:
            continue
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        items = []
        for name, n in re.findall(r"([A-Za-z][A-Za-z' :/.\-]*?)\s*\+(\d+)", spend):
            key = ALIAS.get(name.strip().lower(), name.strip())
            generic = [n for n in full if key.lower() in n.lower()] if len(key.split()) <= 2 else []
            hit = (generic[0],) if len(generic) == 1 else process.extractOne(key, names, scorer=fuzz.WRatio, score_cutoff=70)
            if not hit:
                print(f"  {slug}: no skill for {name!r} in {names}")
                continue
            items.extend([hit[0]] * int(n))
        per_level = max(1, round(len(items) / (hi - lo + 1)))
        for k, skill in enumerate(items):
            totals[skill] = totals.get(skill, 0) + 1
            steps.append([min(hi, lo + k // per_level), skill, totals[skill]])
        spend = {}
        for skill in items:
            spend[skill] = spend.get(skill, 0) + 1
        if spend:     # the guide's own row: these levels, what goes where, and the totals after
            table_rows.append({"lo": lo, "hi": hi, "spend": [[k, v] for k, v in spend.items()], "after": dict(totals)})
    maxes = {x["name"]: x.get("max_level") for x in group["skills"]}
    over = {k: v for k, v in totals.items() if maxes.get(k) and v > maxes[k]}
    if over:
        print(f"  {slug}: past max level {over}")
    builds[job] = {"source": f"meowdb.com/msclassic/guides/{slug}-class-guide", "steps": steps, "rows": table_rows,
                   "end": totals, "to_level": steps[-1][0] if steps else None}
    print(f"{job:12} {len(steps):3} SP, ends at level {builds[job]['to_level']}: {totals}")
OUT.write_text(json.dumps(builds, indent=1), "utf-8")
