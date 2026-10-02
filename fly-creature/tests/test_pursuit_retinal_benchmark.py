import csv
import math

import numpy as np

from fly_creature.pursuit_retinal_benchmark import (CAP, HOLD, N, streams, table, trial)
from fly_creature.pursuit_motion_diagnostic import model
from fly_creature.pursuit_controller import ActivitySteeringSession


def test_frozen_streams_mirror_hold_and_sweep_speed():
    paths = streams()
    assert len(paths) == 22
    for name, values in paths.items():
        assert len(values) == N and np.isfinite(values).all()
        assert np.array_equal(values[:HOLD], np.full(HOLD, values[0]))
        if not name.endswith('_mirror'):
            assert np.array_equal(paths[name+'_mirror'], -values)
    for speed in (25, 75):
        delta = np.diff(paths[f'sweep_{speed}'][HOLD:])/.01
        # Corner-straddling intervals have smaller magnitude.
        assert np.max(np.abs(delta)) <= speed+1e-9
        assert np.mean(np.isclose(np.abs(delta), speed)) > .98


def test_bridge_removed_no_turn_and_exact_queue_timestamps(tmp_path):
    zero = np.zeros((3, 361, 7))
    path = np.full(N, 60.)
    removed = trial(path, zero)
    assert removed['mean_abs_error_deg'] == 60.
    assert removed['settling_s'] is None
    trace = tmp_path/'trace.csv'
    trial(path, None, proportional=True, trace=trace)
    with trace.open() as f:
        rows = list(csv.DictReader(f))
    assert float(rows[20]['delivered_origin_ms']) == 0
    assert float(rows[19]['delivered_deg_s']) == 0
    assert float(rows[HOLD-1]['applied_deg_s']) == 0
    assert float(rows[HOLD]['applied_deg_s']) == CAP
    for tick in range(HOLD, N):
        assert float(rows[tick]['delivered_origin_ms']) == tick*10-200
        assert float(rows[tick]['applied_deg_s']) == float(rows[tick-1]['delivered_deg_s'])


def test_lookup_matches_live_controller_in_rotation_world(tmp_path):
    adapter = model()
    lookup = table(adapter)
    path = streams()['smooth_chirp']
    trace = tmp_path/'comparison.csv'
    trial(path, lookup, trace=trace)
    with trace.open() as f:
        rows = list(csv.DictReader(f))
    session = ActivitySteeringSession()
    for row in rows:
        heading = math.radians(float(row['heading_deg']))
        angle = math.radians(float(row['world_deg']))
        result = session.step({'x': 0., 'z': 0., 'heading_rad': heading},
            {'x': 6.*math.sin(angle), 'z': -6.*math.cos(angle), 'active': True}, 10)
        assert abs(math.degrees(result['turn_rate_rad_s'])-float(row['delivered_deg_s'])) < 1e-9
