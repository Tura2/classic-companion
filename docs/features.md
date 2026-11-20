# What each tab does

Everything here works without screen reading: public game data and market prices only. Set your job, level and mesos at the top of the dashboard.


- **Now**: while you grind, three cards:
  - **Grind**: EXP an hour, time to level, kills to level, grinding time, a chart of EXP per
    minute over the whole session (with the game's tombstone where you died), and your 5 best
    maps by EXP an hour in your last 5 levels. "All maps" opens every one, with kills and mesos
    an hour. "History" lists your past sessions, 8 to a page, newest first; click one to open it
    in full, with its chart, loot, kills and deaths (sessions from before this update show their
    totals only). In a party (the game's "Bonus EXP for PARTY" lines) the card says so and shows
    EXP to level instead of kills, since your EXP comes in shares; party maps are marked apart
    from solo ones in your best maps.
  - **This session**: how far the EXP bar moved (across a level-up too), deaths, the loot, and
    the mesos.
  - **This map**: its monsters (level, HP, EXP) with your kills, and "Worth picking up" for
    everything they drop, most valuable first. What each item is worth shows when you hover it,
    not on the page.

  A death (an EXP drop of up to 10% of the level, seen twice) counts in EXP an hour, the time to
  level, the chart, the session and the map logs. In a town, Now switches by itself: the town's
  map and its people take most of the space, beside the last session and your best maps. The
  game's pickup lines in the bottom-right corner aren't read yet: kills are worked out from your
  EXP, mesos from your mesos when the inventory is open, and Now says loot isn't read.
- **Train**: maps for your level, ranked by EXP per HP and spawns, with ACC needed.
- **Quests**: what you can take now, where the NPC stands, what to kill and where, items you
  can buy instead of farming, and rewards with their market value. Tap Done to unlock chains.
- **Go to**: where you are (its monsters, or in a town the people there: tap one to see them on the
  map), quick picks (towns, maps to train, recent places), and routes between maps on the real map
  picture with the game's own portals drawn and labelled, the one to take in a red ring.
  A route is the quickest way, not the fewest portals: it counts the walk across each map (from
  the portal you came out of to the next one, climbing counted double) and takes a Regular Cab
  between Henesys, Ellinia, Perion, Kerning City and Lith Harbor when that's shorter.
  Tap "I went through" after each portal. The picture opens zoomed on the circled portal or NPC;
  drag it, zoom with the wheel or +/-, or see the whole map. Each map's picture is downloaded once,
  shrunk to 4096 px on its longest side and kept in `cache/maps/`, and a route's maps are fetched
  ahead one at a time, so each step's map is there when you reach it.
- **Gear**: Classic's Equipment Inventory with the best item for your job and level in each slot;
  hover one for the game's tooltip (requirements in red when you're short, jobs, stats, upgrade
  slots, snipe and usual prices). The whole set's cost beside your mesos.
- **Skills**: a skill window with a tab per job you have; your next 3 skill points; what each skill
  does at level 1 and at max, your plan, and where your next SP and AP
  go. The SP order comes from the class guide for each job (`builds.json`, made by
  `tools/make_builds.py`); AP goes into your secondary stat while a weapon you'll want soon needs
  it, otherwise into your main stat.
- **Quest guide**: pick a quest and tap Guide me in game. Each quest shows the game's own "what to
  do" text, and the guide lays it out step by step: take the quest, each monster to hunt (its level,
  HP and ACC needed, at the nearest map with plenty of it) and item to collect (what drops it, how
  often, about how many kills, or what it costs to buy), anyone to see on the way, and who to bring
  it back to: the wiki's turn-in NPC; else, for a quest that gives you something to deliver or has
  nothing to collect, the last NPC its text sends you to; else whoever gave it. A step is done when the game's Quest Helper shows its count reached, or when you tick
  it, so it works without screen reading too. The route strip by the mini map says what to do now
  and takes you where the step happens.

[Back to the README](../README.md)
