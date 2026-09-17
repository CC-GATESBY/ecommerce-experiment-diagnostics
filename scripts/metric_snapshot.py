"""Select exactly one completed immutable metric snapshot; never concatenate runs."""
import hashlib
import json
from pathlib import Path

TABLES=('dim_user_first_seen','agg_user_daily','agg_daily_metrics','agg_daily_dim','brand_mapping')


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def select_snapshot(root,run_path,*,scope_id,source_run):
    require(isinstance(run_path,(str,Path)),'exactly one run path required')
    require(not any(x in str(run_path) for x in ('*','?','[')),'wildcard snapshot selection forbidden')
    root=Path(root).resolve();run=Path(run_path);run=(root/run).resolve() if not run.is_absolute() else run.resolve()
    require(run.is_relative_to(root/'.local'),'snapshot must stay local')
    complete=run/'complete'
    require(complete.is_dir() and not (run/'staging').exists(),'snapshot is incomplete or ambiguous')
    proof=json.loads((complete/'validation.json').read_text());launch=json.loads((run/'launch.json').read_text())
    require(proof.get('status')==launch.get('status')=='passed' and proof.get('spark_stopped') is True,'unsuccessful snapshot')
    require(proof.get('checks') and all(x.get('pass') is True for x in proof['checks'].values()),'snapshot checks incomplete')
    lineage=proof['lineage']
    require(lineage['source_run']==source_run and lineage['metric_version']=='rees46-metrics-v1'
            and lineage['contract_version']=='rees46-events-v1.0.1' and lineage['date_policy_version']=='rees46-date-quality-v1','snapshot lineage mismatch')
    dates=proof['daily'];require(dates and all(r['scope_id']==scope_id for r in dates),'snapshot scope mismatch')
    files={};inventory={}
    for table in TABLES:
        folder=complete/'metrics'/table
        require(folder.is_dir() and (folder/'_SUCCESS').is_file(),'incomplete metric table '+table)
        paths=sorted(p for p in folder.iterdir() if p.suffix=='.parquet')
        require(paths and all(p.is_file() and not p.is_symlink() for p in paths),'invalid metric files')
        files[table]=[str(p) for p in paths]
        inventory.update({str(p):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in paths})
    return dict(run=run,files=files,inventory=inventory,proof=proof,lineage=lineage)
