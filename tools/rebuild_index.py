#!/usr/bin/env python3
import csv,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]; columns="public_measurement_id measurement_uuid date environment_group environment_type country region city location_visibility laeq_db_a lafmax_db_a duration_seconds quality_classification attribution_mode app_version record_path".split(); rows=[]
for path in root.glob("measurements/*/*/SPL-*/measurement.json"):
 d=json.loads(path.read_text());i=d["identity"];m=d["measurement"];e=d["environment"];l=d["public_location"];s=d["sound_level"]
 rows.append(dict(zip(columns,[i["public_measurement_id"],i["measurement_uuid"],m["completed_at_utc"][:10],e["group_id"],e["type_id"],l.get("country_name"),l.get("region"),l.get("city"),l["visibility"],s["laeq_db_a"],s["lafmax_db_a"],m["duration_seconds"],d["measurement_quality"]["classification"],d["attribution"]["mode"],d["software"]["application_version"],str(path.relative_to(root))])))
with (root/"data/measurements.csv").open("w",newline="") as f:w=csv.DictWriter(f,fieldnames=columns,lineterminator="\n");w.writeheader();w.writerows(sorted(rows,key=lambda r:r["public_measurement_id"]))

