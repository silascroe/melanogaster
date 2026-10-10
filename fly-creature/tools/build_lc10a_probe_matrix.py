"""Build stimulus specifications, not simulated LC10a responses (stdlib only)."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    rows = []

    def add(name, family, *, width=15., height=15., speed=75., center=60.,
            contrast=-1., shape="rectangle", present=True, surround="uniform",
            surround_speed=0., state="unspecified", role="diagnostic", source="synthetic"):
        duration = 60./abs(speed) if speed else .8
        for eye, sign in (("R", 1), ("L", -1)):
            rows.append(dict(probe_id=name+"_"+eye, family=family, eye=eye,
                             target_present=present, shape=shape,
                             width_deg=width, height_deg=height,
                             center_azimuth_deg=sign*center, center_elevation_deg=0.,
                             azimuth_velocity_deg_s=sign*speed,
                             weber_contrast=contrast, surround=surround,
                             surround_velocity_deg_s=sign*surround_speed,
                             surround_period_deg=30. if surround!="uniform" else 0.,
                             surround_phase_deg=0.,
                             surround_weber_amplitude=.5 if surround!="uniform" else 0.,
                             state=state, onset_s=1., visible_duration_s=duration,
                             dt_s=.002, geometry_source=source, check_role=role))

    add("absent", "null", present=False, speed=0., role="consistency")
    add("zero_contrast", "null", contrast=0., role="consistency")
    for width in (5.,15.,30.,60.):
        add(f"width_{width:g}", "width", width=width, speed=100.,
            role="qualitative_size", source="Schretter2025-inspired_not_matched")
    for height in (5.,15.,30.,60.):
        add(f"height_{height:g}", "height", height=height, speed=100.,
            role="qualitative_size", source="Schretter2025-inspired_not_matched")
    for size in (10.,25.):
        for direction in (-1,1):
            for state in ("unstimulated", "P1_stimulated"):
                add(f"dot{size:g}_dir{direction}_{state}", "direction_state",
                    width=size,height=size,shape="disc",speed=75.*direction,state=state,
                    role="qualitative_direction_state",source="HindmarshSten2021-inspired_not_matched")
    for velocity in (0.,75.,-75.):
        add(f"surround_{velocity:g}", "surround",surround="square_grating",
            surround_speed=velocity,role="hypothesis")
    for contrast in (-1.,-.5,-.25,1.):
        add(f"contrast_{contrast:g}", "contrast",contrast=contrast,role="hypothesis")
    add("stationary_object", "stationary",speed=0.,role="hypothesis")
    for speed in (25.,75.):
        for direction in (-1,1):
            for center in (15.,65.):
                # Paper geometry only; native archive timing is never replaced.
                name = f"bar_{speed:g}_{direction}_{center:g}"
                add(name,"aotu_bar",width=11.25,height=60.,speed=speed*direction,
                    center=center,role="paper_geometry_archive_association_unverified",
                    source="Collie2026_main_bar")
                for row in rows[-2:]:row["visible_duration_s"] = 22.5/speed
    protected = ["src/fly_creature/pursuit_activity.py",
                 "src/fly_creature/pursuit_step4.py",
                 "src/fly_creature/pursuit_delay_diagnostic.py",
                 "src/fly_creature/pursuit_controller.py",
                 "src/fly_creature/data/visual_steering_v1.json",
                 "src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json"]
    contract = dict(schema_version=1, status="stimulus contract; no neural candidate or physiological fit",
                    coordinate_system="body azimuth positive right, elevation positive up; left mirror explicit",
                    sample_recipe="visible on [onset,onset+duration); az=center+velocity*(t-onset-duration/2)",
                    trial_duration_s=3.,
                    synthetic_panel=dict(azimuth_bounds_deg=[-165,165],elevation_bounds_deg=[-30,30],
                                         pixel_pitch_deg=1.875,dt_s=.002,
                                         elevation_origin_status="synthetic panel-centered convention"),
                    contrast_definition="(target_luminance-background_luminance)/background_luminance; background=1",
                    surround_definition="0.5-amplitude square-wave Weber contrast, 30-degree period; target occludes it",
                    state_status="metadata only, not a fitted multiplier; no equivalence to quiet/running",
                    output_contract="one dimensionless hypothesized activity per sorted LC10a body ID plus map provenance; no spikes/s",
                    mapped_cells=164,fallback_cells=111,per_neuron_elevation_map=False,
                    response_evaluation="not_run",probes=len(rows),
                    protected_sha256={p:digest(ROOT/p) for p in protected},
                    contract_doc_sha256=digest(ROOT/"docs/lc10a_sensor_contract.md"),
                    source_note_sha256=digest(ROOT/"docs/lc10a_sensor_source_refresh.md"),
                    builder_sha256=digest(Path(__file__)))
    return rows,contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    args = parser.parse_args()
    rows,contract = build()
    assert len({r["probe_id"] for r in rows})==len(rows)
    for r in rows:
        assert r["width_deg"]>0 and r["height_deg"]>0 and r["weber_contrast"]>=-1
        half_travel = abs(r["azimuth_velocity_deg_s"])*r["visible_duration_s"]/2
        assert abs(r["center_azimuth_deg"])+half_travel+r["width_deg"]/2<=165
        assert abs(r["center_elevation_deg"])+r["height_deg"]/2<=30
    visual_map = json.loads((ROOT/"src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json").read_text())
    cells = visual_map["cells"]
    assert len(cells)==275 and len({c["body_id"] for c in cells})==275
    assert sum(c["angle_source"]=="upstream registered columns" for c in cells)==164
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with (args.output_dir/"probes.csv").open("w",encoding="utf-8",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
    contract["probe_csv_sha256"] = digest(args.output_dir/"probes.csv")
    (args.output_dir/"contract.json").write_text(json.dumps(contract,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(dict(probes=len(rows),geometry_checks="passed",map_coverage="164 mapped / 111 fallback",
                         response_evaluation="not_run"),indent=2))


if __name__=="__main__":main()
