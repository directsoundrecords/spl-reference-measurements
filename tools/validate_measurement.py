#!/usr/bin/env python3
import hashlib,json,math,re,sys
from pathlib import Path
try:
 from jsonschema import Draft202012Validator,FormatChecker
except ImportError:Draft202012Validator=None
root=Path(__file__).resolve().parents[1]; errors=[]; records=list(root.glob("measurements/*/*/SPL-*/measurement.json")); uuids=set(); ids=set(); tax=json.loads((root/"taxonomy/environments.v1.json").read_text()); pairs={(g["group_id"],t["type_id"]) for g in tax["groups"] for t in g["types"]}; schema=json.loads((root/"schemas/measurement.schema.json").read_text()); validator=Draft202012Validator(schema,format_checker=FormatChecker()) if Draft202012Validator else None
for path in records:
 try:d=json.loads(path.read_text())
 except Exception as e:errors.append(f"{path}: {e}");continue
 text=json.dumps(d).lower(); ident=d.get("identity",{}); mid=ident.get("public_measurement_id"); uid=ident.get("measurement_uuid","")
 if validator:
  for issue in validator.iter_errors(d):errors.append(f"{path}: schema: {issue.message}")
 if mid!=path.parent.name or not re.fullmatch(r"SPL-\d{4}-\d{6}",str(mid)):errors.append(f"{path}: public ID/path mismatch")
 if uid in uuids:errors.append(f"duplicate UUID {uid}")
 uuids.add(uid)
 if mid in ids:errors.append(f"duplicate public ID {mid}")
 ids.add(mid)
 if any(x in text for x in ['"latitude"','"longitude"','"coordinates"','"project_id"','"project_name"']):errors.append(f"{path}: prohibited private field")
 e=d.get("environment",{});
 if (e.get("group_id"),e.get("type_id")) not in pairs or e.get("taxonomy_version")!="1":errors.append(f"{path}: invalid environment")
 for key in ["laeq_db_a","lafmax_db_a"]:
  v=d.get("sound_level",{}).get(key)
  if not isinstance(v,(int,float)) or not math.isfinite(v):errors.append(f"{path}: invalid {key}")
 if d.get("measurement",{}).get("duration_seconds",0)<=0:errors.append(f"{path}: invalid duration")
 photo=d.get("photo",{}); photo_path=path.parent/"photo.jpg"
 if bool(photo.get("included"))!=photo_path.exists():errors.append(f"{path}: photo declaration mismatch")
 if photo_path.exists():
  if hashlib.sha256(photo_path.read_bytes()).hexdigest()!=photo.get("sha256"):errors.append(f"{path}: photo hash mismatch")
  try:
   from PIL import Image
   with Image.open(photo_path) as image:
    if image.getexif() or any(k in image.info for k in ("exif","xmp","iptc")):errors.append(f"{path}: photo metadata prohibited")
  except Exception as e:errors.append(f"{path}: unreadable photo: {e}")
 registry=root/"registry/uuid"/uid[:2]/f"{uid}.json"
 if not registry.exists():errors.append(f"{path}: registry missing")
allowed={"README.md","measurement.json","photo.jpg"}
for directory in root.glob("measurements/*/*/SPL-*"):
 if set(p.name for p in directory.iterdir())-allowed:errors.append(f"{directory}: unexpected file")
if errors:print("\n".join(errors),file=sys.stderr);sys.exit(1)
print(f"Validated {len(records)} measurement records")
