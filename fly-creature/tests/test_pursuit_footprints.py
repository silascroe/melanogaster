from copy import deepcopy
import json

import numpy as np
import pytest

from fly_creature.pursuit_footprints import load_footprints, visual_response, footprint_adapter
from fly_creature.pursuit_motion_diagnostic import model


def test_packaged_footprints_cover_cells_and_preserve_weighted_moments():
    rows=load_footprints();base=model()
    assert len(rows)==275
    assert sum(bool(c['columns']) for c in rows)==164
    assert sum(len(c['columns']) for c in rows)==979
    for cell in rows:
        if cell['columns']:
            a=np.array([c['angle_deg'] for c in cell['columns']])
            w=np.array([c['contacts'] for c in cell['columns']])
            mean=np.average(a,weights=w)
            assert abs(mean-cell['mean_angle_deg'])<1e-10
            assert abs(np.sqrt(np.average((a-mean)**2,weights=w))-cell['spread_deg'])<1e-10
    assert set(c['body_id'] for c in rows)==set(base.projection.body_ids)


def test_mixture_equals_explicit_column_sum_and_fallback_is_unchanged():
    base=model();rows=load_footprints();angles=np.array([-105.,0.,30.,105.])
    visual,direct=visual_response(base.projection,rows,angles)
    index={c['body_id']:c for c in rows}
    for i,body in enumerate(base.projection.body_ids):
        c=index[int(body)];sign=1 if c['side']=='R' else -1
        if c['columns']:
            total=sum(x['contacts'] for x in c['columns'])
            expected=sum(x['contacts']/total*np.exp(-.5*((angles-x['angle_deg']*sign)/18.)**2)
                         for x in c['columns'])
        else:
            expected=np.exp(-.5*((angles-c['fallback_center_deg']*sign)/18.)**2)
        expected*=np.clip(.5+angles*sign/15.,0.,1.)
        assert np.allclose(visual[:,i],expected,rtol=0,atol=1e-14)
    assert np.isfinite(visual).all() and visual.min()>=0 and visual.max()<=1
    assert direct.sum()==164


def test_zero_spread_recentered_candidate_reproduces_baseline():
    base=model();rows=deepcopy(load_footprints())
    for cell in rows:
        for column in cell['columns']:
            column['angle_deg']=cell['mean_angle_deg']
    candidate,_,_=footprint_adapter(base,rows,'recentered_footprint')
    assert np.allclose(candidate.response,base.response,rtol=0,atol=1e-10)
    assert candidate.peaks is base.peaks
    assert candidate.edge_scales is base.edge_scales
    assert np.array_equal(candidate.output_edges,base.output_edges)
    assert candidate.lookups is base.lookups


def test_invalid_footprint_counts_and_means_are_rejected(tmp_path):
    rows=load_footprints();direct=next(c for c in rows if c['columns'])
    path=tmp_path/'bad.json'
    direct['columns'][0]['contacts']=-1
    path.write_text(json.dumps({'schema_version':1,'cells':rows}))
    with pytest.raises(ValueError,match='contact count'):
        load_footprints(path)
    direct['columns'][0]['contacts']=1
    direct['mean_angle_deg']+=1
    path.write_text(json.dumps({'schema_version':1,'cells':rows}))
    with pytest.raises(ValueError,match='mean mismatch'):
        load_footprints(path)
