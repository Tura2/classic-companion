"""Quest lines: the Quest window lists a line's name ("Caretaker's Ledger") for the step you're on."""
import sniper


def test_first_step_not_done():
    assert sniper.current_step(["10213", "10214"], set()) == "10213"
    assert sniper.current_step(["10213", "10214"], {"10213"}) == "10214"


def test_whole_line_done():
    assert sniper.current_step(["1"], {"1"}) is None


def test_line_with_a_quest_already_going_adds_nothing():
    # "Maple World's Unique Fun: Omok" is six Omok sets you choose from: you're on the 6th
    assert sniper.line_step(["80002", "80003", "80007"], set(), {"80007"}) is None
    assert sniper.line_step(["80002", "80003", "80007"], set(), set()) == "80002"
