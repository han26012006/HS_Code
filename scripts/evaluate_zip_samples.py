"""Run exact original source bytes, opaque names, on a frozen selected corpus."""
import argparse,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--selection',required=True);p.add_argument('--backend');p.add_argument('--output',required=True);a=p.parse_args()
sys.path.insert(0,str(Path(a.backend).resolve()if a.backend else ROOT))
from hs_assistant.extractor import AutoFillDraftManager
selection=json.loads(Path(a.selection).read_text());results=[]
for record in selection:
 try:
  manager=AutoFillDraftManager(None);d=manager.create_draft([('source'+record['ext'],Path(record['path']).read_bytes())])
  results.append({'sha256':record['sha256'],'name':record['name'],'group':record['group'],'split':record['split'],
                  'kind':d['documents'][0]['kind'],'skus':d['skus'],'dossier_fields':d['dossier_fields'],
                  'page_methods':[p.get('method')for p in d['documents'][0]['pages']], 'warnings':d.get('warnings',[]),
                  'pages':[{'number':p['number'],'text':p['text']}for p in d['documents'][0]['pages']]})
 except Exception as exc:results.append({'sha256':record['sha256'],'error':str(exc),'skus':[],'dossier_fields':{}})
 Path(a.output).write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(record['sha256'][:8],results[-1].get('kind'),len(results[-1]['skus']),flush=True)
