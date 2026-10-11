from fly_creature.brain_session import BrainSession

FLY = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
NO_OBJECT = {"x": 0.0, "z": -20.0, "radius": 0.45, "active": False}
NO_TARGET = {"active": False}
SUGAR_AT_MOUTH = {"x": 0.0, "z": -0.4, "radius": 0.22, "active": True}


def _run(session: BrainSession, sugar: dict, frames: int = 16) -> list[dict]:
    payload = {"dt_ms": 50.0, "fly": FLY, "object": NO_OBJECT, "target": NO_TARGET, "sugar": sugar}
    return [session.step(payload) for _ in range(frames)]


def test_sugar_contact_drives_feeding_through_mn9():
    frames = _run(BrainSession("intact"), SUGAR_AT_MOUTH)
    assert frames[-1]["taste"]["contact"]
    assert frames[-1]["feeding"]
    assert sum(f["spikes"]["MN9"] for f in frames) > 0


def test_no_sugar_no_feeding():
    frames = _run(BrainSession("intact"), {"active": False})
    assert not any(f["feeding"] for f in frames)
    assert sum(f["spikes"]["MN9"] for f in frames) == 0


def test_cut_wiring_tastes_but_does_not_feed():
    frames = _run(BrainSession("disconnected"), SUGAR_AT_MOUTH)
    assert sum(f["spikes"]["LB3"] for f in frames) > 0
    assert not any(f["feeding"] for f in frames)
