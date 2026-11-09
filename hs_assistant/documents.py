"""Page-preserving document ingestion. No implicit five-page OCR limit."""
from __future__ import annotations
import hashlib,io,json,mimetypes,os,re,shutil,subprocess,tempfile,threading,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .workspace import now,uid,WorkspaceError

SUPPORTED={'.pdf','.png','.jpg','.jpeg','.docx','.xlsx','.csv','.txt','.xls','.doc','.pptx'}
MIMES={'.xls':'application/vnd.ms-excel','.doc':'application/msword','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.csv':'text/csv','.txt':'text/plain'}
MAX_UPLOAD=int(os.environ.get('HS_MAX_UPLOAD_MB','128'))*1024**2
MAX_ARCHIVE_BYTES=512*1024**2

def command(args,timeout=180):
    env=dict(os.environ,OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
    if os.environ.get('HS_TESSDATA_PREFIX'):env['TESSDATA_PREFIX']=os.environ['HS_TESSDATA_PREFIX']
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout,env=env)
    if p.returncode:raise RuntimeError(Path(str(args[0])).name+': '+p.stderr[-400:])
    return p.stdout

class DocumentService:
    def __init__(self,workspace,root):
        self.db=workspace;self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='document-ocr');self.jobs=set();self.lock=threading.Lock()
    def _store(self,case_id,name,content,sku_id=None,archive=None,member=None,parsed_pages=None):
        name=Path(name.replace('\\','/')).name[:180];ext=Path(name).suffix.lower()
        if ext not in SUPPORTED:raise WorkspaceError('Định dạng chưa hỗ trợ: '+ext)
        if len(content)>MAX_UPLOAD:raise WorkspaceError('Tệp vượt giới hạn dung lượng đã cấu hình.')
        if ext=='.pdf' and not content.lstrip().startswith(b'%PDF'):raise WorkspaceError('Nội dung tệp không phải PDF hợp lệ.')
        if ext in {'.docx','.xlsx','.pptx'}:
            if not content.startswith(b'PK'):raise WorkspaceError('Nội dung tệp Office không đúng định dạng.')
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    if len(z.infolist())>10000 or sum(x.file_size for x in z.infolist())>MAX_ARCHIVE_BYTES:raise WorkspaceError('Tệp Office vượt giới hạn giải nén an toàn.')
            except zipfile.BadZipFile:raise WorkspaceError('Tệp Office không hợp lệ.')
        if sku_id and self.db.get_sku(sku_id)['case_id']!=case_id:raise WorkspaceError('SKU không thuộc hồ sơ này.')
        digest=hashlib.sha256(content).hexdigest();path=self.root/(digest+ext)
        if not path.exists():
            with tempfile.NamedTemporaryFile(dir=self.root,suffix='.partial',delete=False) as temp:
                temp.write(content);temporary=Path(temp.name)
            temporary.replace(path)
        with self.db.lock,self.db.connect() as c:
            old=c.execute('SELECT * FROM documents WHERE case_id=? AND sha256=?',(case_id,digest)).fetchone()
            if old:
                if old['sku_id'] is not None and old['sku_id'] != sku_id:
                    raise WorkspaceError('Tệp đã được gắn riêng cho SKU khác trong hồ sơ; lần tải này không đổi phạm vi sử dụng.')
                return self.db.public_document(dict(old)),False
            i=uid('doc_');c.execute('INSERT INTO documents(id,case_id,sku_id,name,mime,sha256,path,source_archive,member_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(i,case_id,sku_id,name,MIMES[ext],digest,str(path),archive,member,now()));self.db.event(c,case_id,sku_id,'document_uploaded','Người nhập',{'document_id':i,'name':name,'sha256':digest,'archive':archive,'member':member})
        if parsed_pages is not None:
            from .document_layout import ensure_layout
            from .extractor import DocumentTypeDetector
            from copy import deepcopy
            pages=deepcopy(parsed_pages);doc=ensure_layout({'id':i,'pages':pages})
            for page in pages:self._page(i,page['number'],page.get('text',''),page.get('method','text'),layout_override=page['layout'],warnings=page.get('warnings',[]))
            with self.db.connect() as c:
                c.execute("UPDATE documents SET status='needs_review',total_pages=?,kind=? WHERE id=?",(len(pages),DocumentTypeDetector.detect_type(doc)['kind'],i))
                self.db.event(c,case_id,sku_id,'document_extracted','Hệ thống',{'document_id':i,'pages':len(pages),'reused_draft_parse':True,'requires_review':True})
        else:self.schedule(i)
        return self.get(i),True
    def upload(self,case_id,name,content,sku_id=None,*,parsed_pages=None):
        self.db.get_case(case_id)
        if len(content)>MAX_UPLOAD:raise WorkspaceError(f'Tệp quá lớn; giới hạn {MAX_UPLOAD//1024**2} MB.')
        ext=Path(name).suffix.lower()
        if ext not in {'.zip','.rar'}:
            row,created=self._store(case_id,name,content,sku_id,parsed_pages=parsed_pages);return {'documents':[row],'added':int(created),'skipped':[]}
        docs=[];skipped=[];total=0;count=0
        def accept(member,data,is_link=False):
            nonlocal total,count
            count+=1
            normalized=member.replace('\\','/');parts=Path(normalized).parts
            if is_link or normalized.startswith('/') or '..' in parts or re.match(r'^[a-zA-Z]:',normalized):raise WorkspaceError('Tệp nén có đường dẫn hoặc liên kết không an toàn.')
            total+=len(data)
            if count>1000 or total>MAX_ARCHIVE_BYTES:raise WorkspaceError('Tệp nén vượt giới hạn số lượng hoặc dung lượng giải nén.')
            if Path(member).suffix.lower() not in SUPPORTED:
                skipped.append({'file':member,'reason':'Định dạng chưa hỗ trợ; không tự thực thi hoặc đọc tệp nén lồng nhau.'});return
            row,created=self._store(case_id,Path(member).name,data,sku_id,name,member)
            if created:docs.append(row)
        # Validate ZIP inventory before writing any member.
        if ext=='.zip':
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                items=[x for x in z.infolist() if not x.is_dir()]
                if len(items)>1000 or any(x.file_size>MAX_UPLOAD for x in items) or sum(x.file_size for x in items)>MAX_ARCHIVE_BYTES:raise WorkspaceError('Tệp nén vượt giới hạn giải nén.')
                for x in items:
                    parts=Path(x.filename.replace('\\','/')).parts
                    if '..' in parts or x.filename.startswith(('/','\\')) or re.match(r'^[a-zA-Z]:',x.filename) or ((x.external_attr>>16)&0o170000)==0o120000:raise WorkspaceError('Tệp nén có đường dẫn hoặc liên kết không an toàn.')
                for x in items:accept(x.filename,z.read(x))
        else:
            try:import libarchive
            except ImportError:raise WorkspaceError('Đọc RAR cần libarchive-c và thư viện libarchive. Bản Docker đã cài sẵn; có thể giải nén trên máy rồi tải tệp lên.')
            with tempfile.NamedTemporaryFile(suffix='.rar') as tmp:
                tmp.write(content);tmp.flush()
                with libarchive.file_reader(tmp.name) as archive:
                    for entry in archive:
                        if not entry.isfile:continue
                        if entry.size and entry.size>MAX_UPLOAD:raise WorkspaceError('Một tệp trong RAR vượt giới hạn dung lượng.')
                        blocks=[];size=0
                        for block in entry.get_blocks():
                            size+=len(block)
                            if size>MAX_UPLOAD:raise WorkspaceError('Tệp trong RAR vượt giới hạn khi đọc.')
                            blocks.append(block)
                        accept(entry.pathname,b''.join(blocks),getattr(entry,'issym',False))
        return {'documents':docs,'added':len(docs),'skipped':skipped}
    def get(self,i,private=False):
        with self.db.connect() as c:r=c.execute('SELECT * FROM documents WHERE id=?',(i,)).fetchone()
        if not r:raise KeyError(i)
        return dict(r) if private else self.db.public_document(dict(r))
    def pages(self,i):
        self.get(i)
        with self.db.connect() as c:
            result=[]
            for x in c.execute('SELECT p.*,l.layout_json FROM pages p LEFT JOIN page_layouts l ON p.document_id=l.document_id AND p.number=l.page_number WHERE p.document_id=? ORDER BY p.number',(i,)):
                page=dict(x); raw=page.pop('layout_json',None)
                from .document_layout import build_layout
                page['layout']=json.loads(raw) if raw else build_layout(page['text'],page['number'],i)
                result.append(page)
            from .document_layout import ensure_layout
            ensure_layout({'id':i,'pages':result})
            return result
    def schedule(self,i):
        with self.lock:
            if i in self.jobs:return
            self.jobs.add(i)
        def job():
            try:self.process(i)
            finally:
                with self.lock:self.jobs.discard(i)
        self.pool.submit(job)
    def retry(self,i):
        doc=self.get(i,True)
        with self.lock:
            if i in self.jobs:raise WorkspaceError('Chứng từ đang trích xuất; chờ hoàn tất trước khi chạy lại.')
            with self.db.lock,self.db.connect() as c:
                linked=[dict(r) for r in c.execute('SELECT * FROM skus WHERE id IN (SELECT sku_id FROM facts WHERE document_id=? UNION SELECT sku_id FROM evidence WHERE document_id=?)',(i,i))]
                c.execute("UPDATE facts SET status='unverified',reviewer=NULL,updated_at=? WHERE document_id=?",(now(),i))
                c.execute("UPDATE evidence SET lifecycle='not_checked',reviewer=NULL,verified_at=NULL WHERE document_id=?",(i,))
                for sku in linked:self.db._invalidate(c,sku,'Người nhập','Trích xuất lại chứng từ nguồn '+i)
                c.execute('DELETE FROM pages WHERE document_id=?',(i,));c.execute("UPDATE documents SET status='queued',processed_pages=0,error=NULL WHERE id=?",(i,))
                self.db.event(c,doc['case_id'],doc.get('sku_id'),'document_retry_requested','Người nhập',{'document_id':i,'linked_skus_requiring_review':len(linked)})
        self.schedule(i)
    def resume(self):
        with self.db.connect() as c:ids=[x[0] for x in c.execute("SELECT id FROM documents WHERE status IN ('queued','processing')")]
        for i in ids:self.schedule(i)
    def _page(self,i,number,text,method,confidence=None,geometry=None,layout_override=None,warnings=None,table_geometry=None):
        from .document_layout import build_layout
        layout=layout_override or build_layout(text,number,i,geometry,table_geometry)
        for warning in warnings or []:
            if warning not in layout['warnings']:layout['warnings'].append(warning)
        with self.db.connect() as c:
            c.execute('INSERT OR REPLACE INTO page_layouts VALUES(?,?,?)',(i,number,json.dumps(layout,ensure_ascii=False)))
            c.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,1)',(uid('pg_'),i,number,text,method,confidence));c.execute('UPDATE documents SET processed_pages=(SELECT count(*) FROM pages WHERE document_id=?) WHERE id=?',(i,i))
    def _ocr(self,path):
        from .ocr_layout import read_image
        result=read_image(path)
        return result['text'],result['method']
    def process(self,i):
        doc=self.get(i,True);path=Path(doc['path']);ext=path.suffix.lower()
        with self.db.connect() as c:c.execute("UPDATE documents SET status='processing',error=NULL WHERE id=?",(i,))
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=doc['sha256']:raise RuntimeError('Nội dung tệp không còn khớp SHA256 đã lưu.')
            if ext=='.pdf':
                from pypdf import PdfReader
                reader=PdfReader(path);n=len(reader.pages)
                if n>int(os.environ.get('HS_MAX_DOCUMENT_PAGES','500')):raise RuntimeError('PDF vượt giới hạn số trang được cấu hình; không có trang nào bị cắt âm thầm.')
                with self.db.connect() as c:c.execute('UPDATE documents SET total_pages=? WHERE id=?',(n,i))
                done={x['number'] for x in self.pages(i)}
                for page in range(1,n+1):
                    if page in done:continue
                    from .document_text import read_pdf_page
                    parsed=read_pdf_page(path,page,reader)
                    self._page(i,page,parsed['text'],parsed['method'],geometry=parsed['geometry'],warnings=parsed.get('warnings',[]),table_geometry=parsed.get('pdf_tables'))
            elif ext in {'.png','.jpg','.jpeg'}:
                from .ocr_layout import read_image
                ocr=read_image(path);self._page(i,1,ocr['text'],ocr['method'],geometry=ocr['geometry'],warnings=ocr.get('warnings',[]))
            elif ext=='.docx':
                from docx import Document
                docx=Document(path);text='\n'.join([p.text for p in docx.paragraphs]+[' | '.join(cell.text for cell in row.cells) for table in docx.tables for row in table.rows]);self._page(i,1,text,'docx_body_and_tables')
            elif ext=='.doc':
                raw=path.read_bytes()
                if raw.startswith(b'{\\rtf'):
                    from striprtf.striprtf import rtf_to_text
                    text=rtf_to_text(raw.decode('latin1'));method='rtf_text'
                else:
                    if not shutil.which('antiword'):raise RuntimeError('Đọc DOC cũ cần antiword; cài công cụ hoặc chuyển DOCX và giữ bản gốc.')
                    text=command(['antiword','-m','UTF-8.txt',path]);method='antiword'
                self._page(i,1,text,method)
            elif ext=='.pptx':
                from pptx import Presentation
                for index,slide in enumerate(Presentation(path).slides,1):self._page(i,index,'\n'.join(x.text for x in slide.shapes if hasattr(x,'text')),'pptx_slide')
            elif ext=='.xls':
                import xlrd
                from openpyxl.utils import get_column_letter
                wb=xlrd.open_workbook(path,on_demand=True)
                for index,sheet in enumerate(wb.sheets(),1):
                    if sheet.nrows*sheet.ncols>1000000:raise RuntimeError('Bảng XLS vượt giới hạn ô.')
                    lines=[' | '.join(f'{get_column_letter(j+1)}{k+1}={sheet.cell_value(k,j)}'for j in range(sheet.ncols)if sheet.cell_value(k,j)!='')for k in range(sheet.nrows)]
                    self._page(i,index,'\n'.join(lines),'xls_cells')
                wb.release_resources()
            elif ext=='.xlsx':
                from openpyxl import load_workbook
                wb=load_workbook(path,read_only=True,data_only=True,keep_links=False)
                cells_seen=0
                for index,sheet in enumerate(wb.worksheets,1):
                    from .spreadsheet_layout import sheet_page
                    if sheet.max_row*sheet.max_column>1000000:raise RuntimeError('Bảng vượt 1 triệu ô.')
                    page=sheet_page(sheet,index);self._page(i,index,page['text'],page['method'],layout_override=page['layout'])
                wb.close()
            else:
                b=path.read_bytes()
                try:text=b.decode('utf-8-sig')
                except UnicodeDecodeError:text=b.decode('cp1258')
                self._page(i,1,text,'text')
            pages=self.pages(i)
            from .extractor import DocumentTypeDetector
            kind=DocumentTypeDetector.detect_type({'pages':pages})['kind']
            with self.db.connect() as c:
                for page in pages:c.execute('INSERT OR REPLACE INTO page_layouts VALUES(?,?,?)',(i,page['number'],json.dumps(page['layout'],ensure_ascii=False)))
            with self.db.connect() as c:
                c.execute("UPDATE documents SET status='needs_review',total_pages=?,kind=? WHERE id=?",(len(pages),kind,i));self.db.event(c,doc['case_id'],doc.get('sku_id'),'document_extracted','Hệ thống',{'document_id':i,'pages':len(pages),'methods':list({p['method'] for p in pages}),'requires_review':True})
        except Exception as e:
            with self.db.connect() as c:c.execute("UPDATE documents SET status='error',error=? WHERE id=?",(str(e)[:700],i))
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
