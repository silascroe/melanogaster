from dataclasses import replace

import numpy as np

from fly_creature.pursuit_motion_diagnostic import model
from fly_creature.pursuit_response_diagnostic import decompose, pairs, probes
from fly_creature.pursuit_retinal_benchmark import table


def test_contributions_reconstruct_actual_activity_and_signs():
    base=model()
    for b in range(-120,121,4):
        for motion in (-1,0,1):
            row=decompose(base,b,motion)
            actual=base.activity_at(b,motion)
            assert np.allclose(row['dn_unclipped'],actual['dn'],rtol=0,atol=1e-14)
            assert abs(sum(row['signal_contributions'])-actual['signal'])<1e-14
            assert not row['dn_clipped']
            expected=base.response[b+180].copy()
            for i,(kind,side) in enumerate(zip(base.projection.aotu_types,base.projection.aotu_sides)):
                if kind=='AOTU019' and ((side=='R' and motion<0) or (side=='L' and motion>0)):
                    expected[i]*=.66
            assert np.array_equal(row['suppressed_contacts'],expected)


def test_probes_change_only_declared_stage_and_do_not_mutate_baseline():
    base=model()
    response=base.response.copy();edges=base.output_edges.copy()
    candidates=probes(base)
    assert np.array_equal(candidates['input_symmetry'].adapter.output_edges,edges)
    assert np.array_equal(candidates['output_symmetry'].adapter.response,response)
    assert np.array_equal(candidates['canonical_output'].adapter.response,response)
    assert np.array_equal(candidates['canonical_output'].adapter.output_edges,np.sign(edges))
    for name in ('channel_normalization','linear_activation','dn_quantization'):
        assert candidates[name].adapter is base
    for candidate in candidates.values():
        candidate.activity_at(105,-1)
    assert np.array_equal(base.response,response) and np.array_equal(base.output_edges,edges)
    assert len(pairs(base))==2


def test_symmetrized_input_and_output_restore_exact_mirror_identity():
    base=model();candidates=probes(base)
    combined=replace(base,response=candidates['input_symmetry'].adapter.response,
                     output_edges=candidates['output_symmetry'].adapter.output_edges)
    lookup=table(combined)[:,60:301,0]
    assert np.max(np.abs(lookup+lookup[::-1,::-1]))<1e-14
    # Constant gain cannot eliminate unequal-shaped mirror curves.
    baseline=table(base)[:,60:301,0]
    assert np.max(np.abs(baseline+baseline[::-1,::-1]))>.2


def test_linear_probe_is_normalized_input_with_recorded_output_edges():
    base=model();candidate=probes(base)['linear_activation']
    row=decompose(base,105,-1)
    activity=np.clip(row['normalized_contacts'],0,1)
    dn=activity@base.output_edges
    actual=candidate.activity_at(105,-1)
    assert np.allclose(actual['aotu'],activity,rtol=0,atol=1e-14)
    assert np.allclose(actual['dn'],dn,rtol=0,atol=1e-14)
