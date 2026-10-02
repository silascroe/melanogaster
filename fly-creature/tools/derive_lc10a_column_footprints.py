"""Development-only export of upstream column distributions; no motor/reference fitting."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from derive_lc10a_registered_eyemap import EyeMap, EYE_BLOB_SHA, MED_BLOB_SHA

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"src/fly_creature/data"


def derive(annotations, weights, eye_file, med_file):
    map_path=DATA/"lc10a_registered_eyemap_hypothesis_v3.json"
    old=json.loads(map_path.read_text())
    cells={int(c["body_id"]): c for c in old["cells"]}
    eye=EyeMap(eye_file,med_file)
    sources={}
    for row in feather.read_table(annotations,columns=["bodyId","instance","assignedOlHex1","assignedOlHex2"]).to_pylist():
        instance=row["instance"] or ""
        side=instance[-1:]
        h1,h2=row["assignedOlHex1"],row["assignedOlHex2"]
        if not instance.endswith(("_L","_R")) or h1 is None or h2 is None:
            continue
        if not float(h1).is_integer() or not float(h2).is_integer():
            raise ValueError("Nonintegral source column")
        sources[int(row["bodyId"])]=(side,(int(h2)-19,int(h1)-18))
    upstream=defaultdict(list)
    reader=pa.ipc.RecordBatchFileReader(pa.memory_map(str(weights)))
    ids=np.array(sorted(cells),dtype=np.int64)
    for k in range(reader.num_record_batches):
        batch=reader.get_batch(k)
        post=batch.column(1).to_numpy()
        mask=np.isin(post,ids)
        if not mask.any():
            continue
        for pre,dst,count in zip(batch.column(0).to_numpy()[mask],post[mask],batch.column(2).to_numpy()[mask]):
            pre,dst,count=int(pre),int(dst),int(count)
            if count>0 and pre in sources and sources[pre][0]==cells[dst]["side"]:
                upstream[dst].append((sources[pre][1],count))
    result=[]
    for body_id,cell in sorted(cells.items()):
        links=upstream[body_id]
        if len(links)!=cell["upstream_mapped_edges"]:
            raise ValueError("Upstream selection differs from registered map")
        columns=[]
        if len(links)>=3:
            grouped=defaultdict(int)
            for coord,count in links:
                grouped[coord]+=count
            for coord,count in sorted(grouped.items()):
                angle,method,distance=eye.at(coord)
                if distance>2:
                    raise ValueError("Source column exceeds registered boundary limit")
                columns.append({"p":coord[0],"q":coord[1],"angle_deg":angle,
                                "contacts":count,"angle_method":method})
            angles=np.array([c["angle_deg"] for c in columns])
            counts=np.array([c["contacts"] for c in columns])
            mean=float(np.average(angles,weights=counts))
            spread=float(np.sqrt(np.average((angles-mean)**2,weights=counts)))
            if abs(mean-cell["preferred_eye_bearing_deg"])>5.1e-5 or abs(spread-cell["angle_spread_deg"])>5.1e-5:
                raise ValueError("Column moments do not reproduce registered map")
        else:
            mean=cell["preferred_abs_bearing_deg"]
            spread=None
        result.append({"body_id":body_id,"side":cell["side"],
            "method":"registered_columns" if columns else "unchanged_center_fallback",
            "fallback_center_deg":cell["preferred_abs_bearing_deg"],
            "mean_angle_deg":mean,"spread_deg":spread,
            "upstream_mapped_edges":len(links),"columns":columns})
    return {"schema_version":1,"status":"offline anatomical input hypothesis; not measured visual fields",
        "sources":{"registered_map_sha256":hashlib.sha256(map_path.read_bytes()).hexdigest(),
            "eye_map_git_blob_sha1":EYE_BLOB_SHA,"medulla_git_blob_sha1":MED_BLOB_SHA,
            "annotations_sha256":hashlib.sha256(Path(annotations).read_bytes()).hexdigest(),
            "weights_sha256":hashlib.sha256(Path(weights).read_bytes()).hexdigest()},
        "method":"Contact-weighted upstream column distributions; same registration/selection as v3; no downstream or behavioral fit",
        "cells":result}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations",type=Path,required=True)
    parser.add_argument("--weights",type=Path,required=True)
    parser.add_argument("--eye-file",type=Path,default=ROOT/"outputs/research/eyemap_T4/eyemap.RData")
    parser.add_argument("--med-file",type=Path,default=ROOT/"outputs/research/eyemap_T4/med_ixy.RData")
    parser.add_argument("--output",type=Path,default=DATA/"lc10a_column_footprints_v1.json")
    args=parser.parse_args()
    result=derive(args.annotations,args.weights,args.eye_file,args.med_file)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"cells":len(result["cells"]),"direct":sum(bool(c["columns"]) for c in result["cells"]),
                     "columns":sum(len(c["columns"]) for c in result["cells"])}))
