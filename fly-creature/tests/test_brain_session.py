"""Game-level checks for the per-sense brain copies (whole_brain_protocol.md, last addendum)."""

import math

from fly_creature.brain_session import BrainSession

FLY = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
NO_OBJECT = {"x": 0.0, "z": -20.0, "radius": 0.45, "active": False}
NO_TARGET = {"active": False}
NO_SUGAR = {"active": False}
SUGAR_AT_MOUTH = {"x": 0.0, "z": -0.4, "radius": 0.22, "active": True}
TARGET_RIGHT = {"x": 3.0, "z": -3.0, "active": True}   # 45 degrees right
TARGET_LEFT = {"x": -3.0, "z": -3.0, "active": True}


def _frames(session, seconds, *, obj=NO_OBJECT, target=NO_TARGET, sugar=NO_SUGAR):
    out = []
    for _ in range(int(round(seconds / 0.05))):
        o = obj(len(out)) if callable(obj) else obj
        out.append(session.step({"dt_ms": 50.0, "fly": FLY, "object": o,
                                 "target": target, "sugar": sugar}))
    return out


def _approaching(frame: int) -> dict:
    # An object closing on the fly's head at 4 m/s, starting 3 m away.
    return {"x": 0.0, "z": -max(0.3, 3.0 - 4.0 * 0.05 * frame), "radius": 0.45, "active": True}


def _loom(session):
    return _frames(session, 0.3, obj=_approaching) + _frames(session, 2.0)


def test_g1_loom_jumps_then_settles():
    frames = _loom(BrainSession("intact"))
    assert any(f["jump"] for f in frames)
    assert sum(f["spikes"]["DNp01"] for f in frames[-20:]) == 0
    assert not any(f["feeding"] for f in frames)


def test_g2_turn_follows_target_side_without_feeding():
    session = BrainSession("intact")
    right = _frames(session, 3.0, target=TARGET_RIGHT)
    left = _frames(session, 3.0, target=TARGET_LEFT)
    mean_turn = lambda fs: sum(f["steering"]["turn_rate_rad_s"] for f in fs[-20:]) / 20
    assert mean_turn(right) > 0
    assert mean_turn(left) < 0
    assert not any(f["feeding"] for f in right + left)


def test_g3_taste_drives_feeding_then_stops():
    session = BrainSession("intact")
    contact = _frames(session, 2.0, sugar=SUGAR_AT_MOUTH)
    after = _frames(session, 2.0)
    assert contact[-1]["feeding"]
    assert not after[-1]["feeding"]


def test_g4_cut_wiring_gives_no_actions():
    frames = (_loom(BrainSession("disconnected"))
              + _frames(BrainSession("disconnected"), 3.0, target=TARGET_RIGHT)
              + _frames(BrainSession("disconnected"), 2.0, sugar=SUGAR_AT_MOUTH))
    assert not any(f["jump"] for f in frames)
    assert not any(f["feeding"] for f in frames)
    assert all(abs(f["steering"]["turn_rate_rad_s"]) < 0.05 for f in frames)
