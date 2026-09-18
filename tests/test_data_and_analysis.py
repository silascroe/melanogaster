import pyarrow as pa
import pyarrow.feather as feather

from flytest.analysis import select_local_network
from flytest.data import (
    ANNOTATION_FILENAME,
    NEUROTRANSMITTER_FILENAME,
    WEIGHTS_FILENAME,
    MaleCNSPaths,
    body_ids_for_type,
    weight_statistics,
)


def _write_fixture_release(tmp_path):
    data_dir = tmp_path / "male-cns-v1.0"
    data_dir.mkdir()
    feather.write_feather(
        pa.table(
            {
                "bodyId": [1, 2, 3],
                "type": ["Seed", "Neighbor", "GlialThing"],
                "instance": ["Seed_L", "Neighbor_L", "GlialThing"],
                "status": ["Traced", "Traced", "Glia"],
                "superclass": ["vnc_intrinsic", "vnc_intrinsic", None],
                "class": [None, None, None],
                "somaSide": ["L", "L", None],
            }
        ),
        data_dir / ANNOTATION_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body": [1, 2, 3],
                "cell_type": ["Seed", "Neighbor", None],
                "predicted_nt": ["acetylcholine", "gaba", "unclear"],
                "predicted_nt_confidence": [0.9, 0.8, 0.1],
                "consensus_nt": ["acetylcholine", "gaba", "unclear"],
                "total_nt_predictions": [10, 10, 10],
            }
        ),
        data_dir / NEUROTRANSMITTER_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body_pre": [1, 2, 1, 3],
                "body_post": [2, 1, 3, 1],
                "weight": [5, 4, 9, 8],
            }
        ),
        data_dir / WEIGHTS_FILENAME,
    )
    return MaleCNSPaths(data_dir)


def test_fixture_stats_and_traced_selection(tmp_path) -> None:
    paths = _write_fixture_release(tmp_path)
    assert body_ids_for_type(paths, "Seed") == [1]

    stats = weight_statistics(paths)
    assert stats["raw"]["rows"] == 4
    assert stats["filtered"]["rows"] == 2
    assert stats["filtered"]["sum_weight"] == 9

    network = select_local_network(paths, [1], neighbor_limit=1, min_weight=1)
    assert [node.body_id for node in network.nodes] == [1, 2]
    assert len(network.edges) == 2
    assert network.edges[0].sign in (-1.0, 1.0)
