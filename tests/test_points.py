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


def skill(i, name):
    return {"id": i, "name": name, "max_level": 10, "passive": True, "all_level_stats": ["x"], "thumbnail": f"images/skills/{i}.png"}


def test_skill_tabs_beginner_first_then_the_jobs():
    g = object.__new__(gamedata.GameData)
    g.skills = {"beginner": [{"class_name": "Beginner", "job": "Beginner", "skills": [skill("0001000", "Three Snails")]}],
                "archer": [{"class_name": "Hunter", "job": "2nd Job", "skills": [skill("3101004", "Arrow Bomb")]},
                           {"class_name": "Archer", "job": "1st Job", "skills": [skill("3000001", "The Eye of Amazon")]}]}
    jobs = [s["job"] for s in g.skill_list("Hunter", with_beginner=True)]
    assert list(dict.fromkeys(jobs)) == ["Beginner", "Archer", "Hunter"]
    assert "Beginner" not in [s["job"] for s in g.skill_list("Hunter")]
