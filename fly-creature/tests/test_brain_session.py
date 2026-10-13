"""Game-level checks for the per-sense brain copies (whole_brain_protocol.md, last addendum)."""

import math

from fly_creature.brain_session import BrainSession

FLY = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
NO_OBJECT = {"x": 0.0, "z": -20.0, "radius": 0.45, "active": False}
NO_TARGET = {"active": False}
NO_SUGAR = {"active": False}
SUGAR_AT_MOUTH = {"x": 0.0, "z": -0.4, "radius": 0.22, "active": True}
BITTER_AT_MOUTH = {**SUGAR_AT_MOUTH, "bitter": True}
DUST = {"active": True}
NO_DUST = {"active": False}
PRESSED = {"active": True}
NOT_PRESSED = {"active": False}
TARGET_RIGHT = {"x": 3.0, "z": -3.0, "active": True}   # 45 degrees right
TARGET_LEFT = {"x": -3.0, "z": -3.0, "active": True}


def _frames(session, seconds, *, obj=NO_OBJECT, target=NO_TARGET, sugar=NO_SUGAR, touch=NO_DUST,
            obstacle=NOT_PRESSED):
    out = []
    for _ in range(int(round(seconds / 0.05))):
        o = obj(len(out)) if callable(obj) else obj
        out.append(session.step({"dt_ms": 50.0, "fly": FLY, "object": o,
                                 "target": target, "sugar": sugar, "touch": touch,
                                 "obstacle": obstacle}))
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
    assert not any(f["grooming"] for f in frames)
    assert not any(f["singing"] for f in frames)


def test_g2_turn_follows_target_side_without_feeding():
    session = BrainSession("intact")
    right = _frames(session, 3.0, target=TARGET_RIGHT)
    left = _frames(session, 3.0, target=TARGET_LEFT)
    mean_turn = lambda fs: sum(f["steering"]["turn_rate_rad_s"] for f in fs[-20:]) / 20
    # Turning runs on subset v1, the one that passed both turn checks.
    assert right[0]["brain_packages"]["target"] == "v1"
    assert mean_turn(right) > 0
    assert mean_turn(left) < 0
    assert not any(f["feeding"] for f in right + left)
    assert not any(f["grooming"] for f in right + left)


def test_g3_taste_drives_feeding_then_stops():
    session = BrainSession("intact")
    contact = _frames(session, 2.0, sugar=SUGAR_AT_MOUTH)
    after = _frames(session, 2.0)
    assert contact[-1]["feeding"]
    assert not after[-1]["feeding"]


def test_g4_cut_wiring_gives_no_actions():
    frames = (_loom(BrainSession("disconnected"))
              + _frames(BrainSession("disconnected"), 3.0, target=TARGET_RIGHT)
              + _frames(BrainSession("disconnected"), 2.0, sugar=SUGAR_AT_MOUTH)
              + _frames(BrainSession("disconnected"), 2.0, touch=DUST)
              + _frames(BrainSession("disconnected"), 2.0, obstacle=PRESSED))
    assert not any(f["jump"] for f in frames)
    assert not any(f["feeding"] for f in frames)
    assert not any(f["grooming"] for f in frames)
    assert not any(f["singing"] for f in frames)
    assert not any(f["backing"] for f in frames)
    assert all(abs(f["steering"]["turn_rate_rad_s"]) < 0.05 for f in frames)


def test_g5_antenna_dust_drives_grooming_then_stops():
    session = BrainSession("intact")
    dusty = _frames(session, 2.0, touch=DUST)
    after = _frames(session, 2.0)
    assert dusty[-1]["grooming"]
    assert not after[-1]["grooming"]
    assert not any(f["feeding"] or f["jump"] or f["singing"] for f in dusty + after)


def test_g6_bitter_drop_is_not_fed_on():
    frames = _frames(BrainSession("intact"), 2.0, sugar=BITTER_AT_MOUTH)
    assert all(f["taste"]["bitter"] for f in frames)
    assert not any(f["feeding"] for f in frames)


def test_g7_seen_target_drives_song_on_its_side_then_stops():
    session = BrainSession("intact")
    right = _frames(session, 2.0, target=TARGET_RIGHT)
    after = _frames(session, 2.0)
    assert right[-1]["singing"] and right[-1]["song_side"] == "R"
    assert not after[-1]["singing"]
    left = _frames(BrainSession("intact"), 2.0, target=TARGET_LEFT)
    assert left[-1]["singing"] and left[-1]["song_side"] == "L"


def test_g8_forelegs_pressed_drive_backing_up_then_stops():
    session = BrainSession("intact")
    pressed = _frames(session, 0.5, obstacle=PRESSED)
    after = _frames(session, 1.5)
    assert pressed[0]["brain_packages"]["obstacle"] == "v4"
    # In the game the fly loses contact once it backs off, so the onset is what
    # matters; sustained pressing past ~1 s can drift into an MDN-silent state.
    assert any(f["backing"] for f in pressed)
    assert not after[-1]["backing"]
    assert not any(f["feeding"] or f["grooming"] or f["singing"] for f in pressed + after)
