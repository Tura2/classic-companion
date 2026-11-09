"""Skills: the next three single skill points from the class guide, and the job tabs."""
import gamedata


def test_next_three_points_are_single_steps():
    steps = [(34, "Bow Booster", 5), (34, "Soul Arrow: Bow", 1)] + [(34, "Bow Mastery", t) for t in range(6, 21)]
    now = {"Bow Booster": 4, "Soul Arrow: Bow": 0, "Bow Mastery": 5}
    assert gamedata.single_points(steps, now) == [
        {"skill": "Bow Booster", "from": 4, "to": 5, "level": 34},
        {"skill": "Soul Arrow: Bow", "from": 0, "to": 1, "level": 34},
        {"skill": "Bow Mastery", "from": 5, "to": 6, "level": 34}]


def test_a_jump_in_the_guide_still_gives_single_points():
    steps = [(31, "Arrow Bomb", 3), (33, "Bow Booster", 1)]
    assert [(p["skill"], p["from"], p["to"]) for p in gamedata.single_points(steps, {"Arrow Bomb": 1})] == [
        ("Arrow Bomb", 1, 2), ("Arrow Bomb", 2, 3), ("Bow Booster", 0, 1)]
