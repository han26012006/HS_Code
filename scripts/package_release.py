"""Build a portable source + web_dist ZIP, excluding secrets, runtime and model weights."""
from pathlib import Path
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parent.parent
ROOT_FILES={'api.py','app_streamlit.py','serve.py','track_mlflow.py','README.md','HUONG_DAN_CHAY.md','THIRD_PARTY_NOTICES.txt','Dockerfile','.dockerignore','.env.example','run_windows.bat','run_local.sh','package.json','package-lock.json'}
FOLDERS={'hs_assistant','frontend','web_dist','data','docs','tests','legacy','.github'}
SCRIPTS={'scripts/dev.mjs','scripts/package_release.py'}
def chosen():
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(ROOT);parts=rel.parts;name=rel.as_posix()
        if any(s in {'node_modules','runtime','__pycache__','.pytest_cache','.venv','.git'}for s in parts):continue
        if any(s.startswith('.')and not(i==0 and s in {'.github','.env.example','.dockerignore'})for i,s in enumerate(parts)):continue
        if p.suffix in {'.pyc','.log','.sqlite','.db','.partial'}or p.name=='.env':continue
        if (len(parts)==1 and (p.name in ROOT_FILES or p.name.startswith('requirements')and p.suffix=='.txt'))or parts[0]in FOLDERS or name in SCRIPTS:yield p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();target=Path(args.output).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    files=[p for p in chosen()if p.name!='RELEASE_MANIFEST.json'];hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
    manifest={'version':'2.2.0','release_date':'2026-11-02','application':'HS Workspace','jurisdiction':'VN','nomenclature':'AHTN2022','model_accuracy_newly_verified':False,'real_paid_api_calls_in_release_testing':0,'sha256':hashes}
    payload=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(ROOT/'RELEASE_MANIFEST.json').write_bytes(payload)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for p in files:z.write(p,'hs-assistant/'+p.relative_to(ROOT).as_posix())
        z.writestr('hs-assistant/RELEASE_MANIFEST.json',payload)
    with zipfile.ZipFile(target)as z:
        assert z.testzip() is None
        for name,digest in hashes.items():assert hashlib.sha256(z.read('hs-assistant/'+name)).hexdigest()==digest
    print(json.dumps({'zip':str(target),'files':len(files)+1,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
