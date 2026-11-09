"""Integration results on original local bytes, not scored ground-truth accuracy."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--files-json',required=True);p.add_argument('--output',required=True);p.add_argument('--backend');a=p.parse_args()
    sys.path.insert(0,str(Path(a.backend).resolve() if a.backend else ROOT))
    from hs_assistant.extractor import AutoFillDraftManager
    records=json.loads(Path(a.files_json).read_text());files=[(r['name'],Path(r['path']).read_bytes())for r in records]
    draft=AutoFillDraftManager(None).create_draft(files)
    result={'scope':'original local PDF integration/development case; not independently labelled accuracy',
            'files':[{'name':n,'sha256':hashlib.sha256(data).hexdigest()}for n,data in files],
            'summary':draft['summary'],'extracted_case':draft['extracted_case'],
            'documents':[{'id':d['id'],'name':d['name'],'kind':d['kind'],'pages':len(d['pages'])}for d in draft['documents']],
            'skus':draft['skus'],'dossier_fields':draft['dossier_fields'],'warnings':draft.get('warnings',[])}
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result['summary'])
