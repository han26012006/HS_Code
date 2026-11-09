from pathlib import Path
import hashlib,json

def file_sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def validate_artifacts(art):
    art=Path(art);manifest=art/'pipeline_manifest.json'
    if art.name=='artifacts_v4' and not manifest.exists():raise ValueError('artifacts_v4 chưa hoàn tất: thiếu pipeline_manifest.json')
    if not manifest.exists():return {'edition':'legacy','verified_integrity':False,'source':'historical_project_artifacts'}
    value=json.loads(manifest.read_text())
    for name,digest in value['sha256'].items():
        p=(art/name).resolve()
        if not p.is_relative_to(art.resolve()) or not p.is_file() or file_sha(p)!=digest:raise ValueError('Artifact không khớp manifest: '+name)
    return {'edition':'v4','verified_integrity':True,'manifest_sha256':file_sha(manifest),'embedding_pooling':value.get('extra',{}).get('embedding_pooling','')}

def find_artifacts(root):
    import os
    if os.environ.get('HS_ART'):return Path(os.environ['HS_ART'])
    candidates=[]
    if os.environ.get('HS_BASE'):candidates+=[Path(os.environ['HS_BASE'])/'03_MoHinh/artifacts_v4',Path(os.environ['HS_BASE'])/'03_MoHinh/artifacts']
    candidates+=[Path(root)/'artifacts_v4',Path(root)/'artifacts']
    return next((x for x in candidates if (x/'ranker.joblib').is_file()),None)
