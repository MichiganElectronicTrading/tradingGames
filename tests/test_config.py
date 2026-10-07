import pytest

from mtt_games.games.card.config import EASY, HARD, MEDIUM, PRESETS, CardConfig


@pytest.mark.parametrize("cfg", [EASY, MEDIUM, HARD])
def test_presets_are_valid(cfg):
    cfg.validate()
    assert cfg.errors() == []


def test_preset_table_values():
    assert (EASY.n_cards_min, EASY.face_up_max, EASY.timer_s, EASY.spread, EASY.sizing) == (3, 1, 60, 4, "fixed")
    assert (MEDIUM.n_cards_max, MEDIUM.face_up_max, MEDIUM.timer_s, MEDIUM.sizing) == (5, 2, 30, "choose")
    assert (HARD.n_cards_min, HARD.n_cards_max, HARD.face_up_min, HARD.face_up_max) == (6, 8, 1, 3)
    assert HARD.mid_round_flip and HARD.stale_quotes and HARD.event_freq == 1.0 and len(HARD.enabled_events) == 5
    assert all(p.budget == 500 for p in PRESETS.values())


@pytest.mark.parametrize(
    "changes",
    [
        dict(face_up_max=4),  # face_up_max > n_cards_min (3)
        dict(n_cards_min=1),
        dict(n_cards_max=11),
        dict(n_cards_min=5, n_cards_max=4),
        dict(face_up_min=2, face_up_max=1),
        dict(face_up_min=-1),
        dict(rounds=0),
        dict(rounds=21),
        dict(timer_s=4),
        dict(timer_s=121),
        dict(spread=0),
        dict(spread=9),
        dict(budget=0),
        dict(quote_noise_sd=-1.0),
        dict(sizing="all-in"),
        dict(event_freq=0.5, enabled_events=("face_ten",)),
        dict(event_freq=1.0, enabled_events=()),
        dict(event_freq=1.0, enabled_events=("bogus",)),
        dict(stale_quotes=True),  # stale quotes without the flip
        dict(seed="abc"),
    ],
)
def test_bad_combos_rejected(changes):
    cfg = EASY.replace(**changes)
    assert cfg.errors()
    with pytest.raises(ValueError):
        cfg.validate()


def test_boundary_values_accepted():
    CardConfig(n_cards_min=2, n_cards_max=10, face_up_min=0, face_up_max=2, rounds=20, timer_s=5, spread=8).validate()
    CardConfig(n_cards_min=10, n_cards_max=10, face_up_max=10, rounds=1, timer_s=120, spread=1).validate()


def test_round_trip_dict():
    assert CardConfig.from_dict(HARD.to_dict()) == HARD
