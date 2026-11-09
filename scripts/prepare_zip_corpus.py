"""Local read-only source inventory and frozen shipment-group split; no document instructions executed."""
import concurrent.futures,hashlib,io,json,subprocess,unicodedata,zipfile
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'scratch/zip_corpus';OUT.mkdir(parents=True,exist_ok=True)
def name(s):
 try:s=s.encode('cp437').decode('utf8')
 except (UnicodeError,LookupError):pass
 return unicodedata.normalize('NFC',s)
archive=Path('/Users/hanna/Downloads/20 BỘ CHỨNG TỪ 2.zip');records=[]
with zipfile.ZipFile(archive) as z:
 for member in z.infolist():
  parts=Path(name(member.filename)).parts
  if member.is_dir() or '__MACOSX' in parts or any(p.startswith('.') for p in parts):continue
  group=parts[1] if len(parts)>2 else '_root';ext=Path(parts[-1]).suffix.lower()
  record={'member':name(member.filename),'group':group,'name':parts[-1],'size':member.file_size,'ext':ext,'depth':len(parts)}
  # Inventory every member; extract only source-doc candidates, not large presentation decks.
  if len(parts)>=4 and ext in {'.pdf','.xlsx','.docx','.png','.jpg'} and member.file_size<13000000:
   data=z.read(member);sha=hashlib.sha256(data).hexdigest();path=OUT/(sha+ext)
   if not path.exists():path.write_bytes(data)
   record.update(sha256=sha,path=str(path),candidate=True)
  records.append(record)
known=set()
exposure=ROOT/'tests/fixtures/document_ai/real_development_exposure.json'
if exposure.exists():known={r['sha256'] for r in json.loads(exposure.read_text())}
exposed={r['group'] for r in records if r.get('sha256') in known}
groups=sorted({r['group'] for r in records},key=lambda x:hashlib.sha256(x.encode()).hexdigest())
reserved=set([g for g in groups if g not in exposed][:4])
for record in records:record['split']='reserved_real' if record['group'] in reserved else 'development_real'
manifest={'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(records),'groups':groups,'reserved_groups':sorted(reserved),'known_exposed_groups':sorted(exposed),'note':'Split fixed before content inspection; original archive labels are grouping metadata only, never extractor features.','records':records}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
def cache(record):
 if not record.get('candidate') or record['ext']!='.pdf':return None
 output=OUT/(record['sha256']+'.text.json')
 if output.exists():return json.loads(output.read_text())
 try:
  reader=PdfReader(record['path']);count=len(reader.pages)
  p=subprocess.run(['/opt/homebrew/bin/pdftotext','-layout',record['path'],'-'],capture_output=True,text=True,timeout=60)
  texts=p.stdout.split('\f');texts=texts[:count]
  while len(texts)<count:texts.append('')
  result={'sha256':record['sha256'],'pages':[{'number':i+1,'text':t,'method':'pdftotext'}for i,t in enumerate(texts)],'total_pages':count,'needs_ocr':sum(not t.strip() for t in texts)}
 except Exception as e:result={'sha256':record['sha256'],'error':str(e),'pages':[]}
 output.write_text(json.dumps(result,ensure_ascii=False));return result
unique={r['sha256']:r for r in records if r.get('candidate') and r['ext']=='.pdf'}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(cache,unique.values()))
print(json.dumps({'files':len(records),'groups':len(groups),'source_candidates':sum(r.get('candidate',False)for r in records),'unique_pdf_sources':len(unique),'pages':sum(r.get('total_pages',0)for r in results),'ocr_pages':sum(r.get('needs_ocr',0)for r in results),'reserved_groups':sorted(reserved)},ensure_ascii=False,indent=2))
