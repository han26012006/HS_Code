"""Persistent case/SKU workflow. Human decisions are internal records, never auto-gold."""
from __future__ import annotations
import hashlib,json,sqlite3,threading,uuid,unicodedata
from datetime import datetime,timezone,date
from pathlib import Path

FIELDS={'name':'Tên và bản chất hàng','function':'Công dụng chính','material':'Vật liệu / thành phần','construction':'Cấu tạo / nguyên lý','manufacturing':'Quy trình sản xuất','specifications':'Thông số và kích thước','condition':'Trạng thái khi nhập khẩu','packaging':'Quy cách đóng gói'}
from .document_schema import PRODUCT_FIELDS
FIELDS.update({field: field.replace('_',' ').title() for field in PRODUCT_FIELDS if field not in FIELDS})
STATES={'draft','collecting','ready','in_review','approved','returned','archived'}

def now():return datetime.now(timezone.utc).isoformat()
def uid(prefix=''):return prefix+uuid.uuid4().hex[:16]
def encode(x):return json.dumps(x,ensure_ascii=False,default=str)
def decode(x,default=None):
    try:return json.loads(x)
    except (ValueError,TypeError):return default

def retention_for_case(case):
    registered=case.get('declaration_registered_date')
    until=None
    if registered:
        d=date.fromisoformat(registered)
        try:until=d.replace(year=d.year+5).isoformat()
        except ValueError:until=date(d.year+5,3,1).isoformat()
    return {'declaration_registered_date':registered,'minimum_reference_until':until,
            'status':'legal_hold' if case.get('legal_hold') else 'date_recorded' if until else 'declaration_date_required',
            'legal_hold':bool(case.get('legal_hold')),'automatic_deletion_enabled':False,
            'basis':'Luật Hải quan Điều 18(2)(đ); đối chiếu văn bản hợp nhất 54/VBHN-VPQH ngày 23/03/2026.',
            'note':'Mốc tham chiếu 5 năm từ ngày đăng ký tờ khai, không từ ngày AI phân tích. Nghĩa vụ kế toán, thuế, tranh chấp hoặc yêu cầu lưu khác có thể dài hơn; không tự xóa ở mốc này. Đối chiếu riêng NĐ169/2026 Điều 5 về thời hiệu xử phạt và việc nộp đủ thuế/tiền chậm nộp.'}

def person_key(value):return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())

class WorkspaceError(ValueError):pass
class ConflictError(WorkspaceError):pass

class Workspace:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.init()
    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');return c
    def init(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,title TEXT NOT NULL,trade_type TEXT NOT NULL,classification_date TEXT NOT NULL,jurisdiction TEXT NOT NULL DEFAULT 'VN',nomenclature TEXT NOT NULL DEFAULT 'AHTN2022',owner TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',notes TEXT NOT NULL DEFAULT '',is_demo INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skus(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id),sku_code TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',declared_code TEXT,product_family TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'draft',revision INTEGER NOT NULL DEFAULT 1,analysis_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id),sku_id TEXT REFERENCES skus(id),name TEXT NOT NULL,mime TEXT NOT NULL,sha256 TEXT NOT NULL,path TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'other',status TEXT NOT NULL DEFAULT 'queued',total_pages INTEGER NOT NULL DEFAULT 0,processed_pages INTEGER NOT NULL DEFAULT 0,error TEXT,source_archive TEXT,member_path TEXT,created_at TEXT NOT NULL,UNIQUE(case_id,sha256));
            CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),number INTEGER NOT NULL,text TEXT NOT NULL,method TEXT NOT NULL,confidence REAL,review_required INTEGER NOT NULL DEFAULT 1,UNIQUE(document_id,number));
            CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),field TEXT NOT NULL,value TEXT NOT NULL,document_id TEXT REFERENCES documents(id),page_number INTEGER,quote TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'unverified',reviewer TEXT,source_kind TEXT NOT NULL DEFAULT 'document',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),kind TEXT NOT NULL,title TEXT NOT NULL,source_url TEXT NOT NULL DEFAULT '',document_id TEXT REFERENCES documents(id),page_number INTEGER,quote TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'reference',jurisdiction TEXT NOT NULL DEFAULT 'VN',nomenclature TEXT NOT NULL DEFAULT 'AHTN2022',effective_from TEXT,effective_to TEXT,lifecycle TEXT NOT NULL DEFAULT 'not_checked',reviewer TEXT,verified_at TEXT,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),sku_revision INTEGER NOT NULL,input_hash TEXT NOT NULL,engine TEXT NOT NULL,model_version TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),sku_revision INTEGER NOT NULL,code TEXT NOT NULL,reason TEXT NOT NULL,reviewer TEXT NOT NULL,preparer TEXT NOT NULL,evidence_ids TEXT NOT NULL,classification_date TEXT NOT NULL,review_type TEXT NOT NULL DEFAULT 'internal_review',created_at TEXT NOT NULL,superseded_at TEXT);
            CREATE TABLE IF NOT EXISTS tax_scenarios(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),sku_revision INTEGER NOT NULL,input_json TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT,sku_id TEXT,action TEXT NOT NULL,actor TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS comparisons(id TEXT PRIMARY KEY,sku_id TEXT NOT NULL REFERENCES skus(id),sku_revision INTEGER NOT NULL,analysis_id TEXT,input_json TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decision_snapshots(decision_id TEXT PRIMARY KEY REFERENCES decisions(id),snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
            ''')
            c.executescript("""
            CREATE TABLE IF NOT EXISTS page_layouts(document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,page_number INTEGER NOT NULL,layout_json TEXT NOT NULL,PRIMARY KEY(document_id,page_number));
            CREATE TABLE IF NOT EXISTS fact_sources(fact_id TEXT PRIMARY KEY REFERENCES facts(id) ON DELETE CASCADE,provenance_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS case_extracted_fields(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,field TEXT NOT NULL,value TEXT NOT NULL,document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,page_number INTEGER,quote TEXT NOT NULL,status TEXT NOT NULL,provenance_json TEXT NOT NULL);
            """)
            # Additive migration: never rebuild or discard an existing workspace.
            for table,columns in {'cases':{'declaration_number':"TEXT NOT NULL DEFAULT ''",'declaration_registered_date':'TEXT','legal_hold':'INTEGER NOT NULL DEFAULT 0'},'evidence':{'target_codes_json':"TEXT NOT NULL DEFAULT '[]'",'resolution_note':"TEXT NOT NULL DEFAULT ''"}}.items():
                present={r['name']for r in c.execute('PRAGMA table_info('+table+')')}
                for column,definition in columns.items():
                    if column not in present:c.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+definition)
    def event(self,c,case_id,sku_id,action,actor,payload):
        prior=c.execute('SELECT event_hash FROM events ORDER BY id DESC LIMIT 1').fetchone();prev=prior[0] if prior else 'GENESIS';stamp=now();body=encode({'case':case_id,'sku':sku_id,'action':action,'actor':actor,'payload':payload,'at':stamp})
        digest=hashlib.sha256((prev+body).encode()).hexdigest()
        c.execute('INSERT INTO events(case_id,sku_id,action,actor,payload,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)',(case_id,sku_id,action,actor,encode(payload),stamp,prev,digest))
    def create_case(self,title,owner,trade_type='import',classification_date=None,notes='',is_demo=False,declaration_number='',declaration_registered_date=None,legal_hold=False):
        if not title.strip() or not owner.strip():raise WorkspaceError('Cần tên hồ sơ và người phụ trách.')
        stamp=now();i=uid('case_');reference='HS-'+datetime.now().strftime('%Y%m')+'-'+uuid.uuid4().hex[:8].upper()
        with self.lock,self.connect() as c:
            c.execute('INSERT INTO cases(id,reference,title,trade_type,classification_date,owner,notes,is_demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(i,reference,title.strip(),trade_type,classification_date or stamp[:10],owner.strip(),notes,int(is_demo),stamp,stamp));self.event(c,i,None,'case_created',owner,{'reference':reference,'title':title})
            c.execute('UPDATE cases SET declaration_number=?,declaration_registered_date=?,legal_hold=? WHERE id=?',(declaration_number,declaration_registered_date,int(legal_hold),i))
        return self.get_case(i)
    def cases(self,query='',status=None):
        with self.connect() as c:
            rows=c.execute('''SELECT c.*,(SELECT count(*) FROM skus s WHERE s.case_id=c.id) sku_count,(SELECT count(*) FROM documents d WHERE d.case_id=c.id) document_count,(SELECT count(*) FROM skus s WHERE s.case_id=c.id AND s.status='approved') approved_skus FROM cases c ORDER BY c.updated_at DESC''').fetchall()
        data=[dict(x) for x in rows]
        return [x for x in data if (not query or query.casefold() in (x['title']+' '+x['reference']).casefold()) and (not status or x['status']==status)]
    def get_case(self,i):
        with self.connect() as c:
            r=c.execute('SELECT * FROM cases WHERE id=?',(i,)).fetchone()
            if not r:raise KeyError(i)
            d=dict(r);d['skus']=[dict(x) for x in c.execute('SELECT * FROM skus WHERE case_id=? ORDER BY created_at',(i,))];d['documents']=[self.public_document(dict(x)) for x in c.execute('SELECT * FROM documents WHERE case_id=? ORDER BY created_at DESC',(i,))];d['events']=[self.public_event(dict(x)) for x in c.execute('SELECT * FROM events WHERE case_id=? ORDER BY id DESC LIMIT 60',(i,))]
            for s in d['skus']:
                s['fact_count']=c.execute('SELECT count(*) FROM facts WHERE sku_id=?',(s['id'],)).fetchone()[0];s['verified_facts']=c.execute("SELECT count(*) FROM facts WHERE sku_id=? AND status='verified'",(s['id'],)).fetchone()[0]
            d['extracted_fields']=[{**decode(r['provenance_json'],{}),**{k:r[k] for k in r.keys() if k!='provenance_json'}} for r in c.execute('SELECT * FROM case_extracted_fields WHERE case_id=? ORDER BY field,id',(i,))]
            d['retention']=retention_for_case(d);return d
    @staticmethod
    def public_document(d):d.pop('path',None);return d
    @staticmethod
    def public_event(d):d['payload']=decode(d['payload'],{});return d
    @staticmethod
    def public_evidence(d):d['target_codes']=decode(d.pop('target_codes_json','[]'),[]);return d
    def save_extracted_fields(self,case_id,fields,document_mapping):
        with self.lock,self.connect() as c:
            for field,candidate in fields.items():
                for fact in candidate.get('sources',candidate.get('alternatives',[candidate])):
                    value=fact.get('value','')
                    if not value:continue
                    original_doc=fact.get('source_document_id')
                    doc_id=document_mapping.get(original_doc)
                    if not doc_id:raise WorkspaceError('Thiếu chứng từ gốc cho thông tin hồ sơ.')
                    page=c.execute('SELECT text FROM pages WHERE document_id=? AND number=?',(doc_id,fact.get('source_page'))).fetchone()
                    quote=fact.get('source_quote') or fact.get('source_excerpt','')
                    from .document_layout import norm
                    if not page or not quote or norm(quote) not in norm(page['text']):raise WorkspaceError('Thông tin hồ sơ sai trích dẫn nguồn.')
                    status='conflict' if candidate.get('status')=='conflicting' else 'unverified'
                    provenance={**fact,'source_document_id':doc_id,'value_origin':fact.get('source_kind','document_extracted')}
                    duplicate=c.execute('SELECT id FROM case_extracted_fields WHERE case_id=? AND field=? AND value=? AND document_id=? AND page_number=? AND quote=?',(case_id,field,value,doc_id,fact['source_page'],quote)).fetchone()
                    if duplicate:
                        if status=='conflict':c.execute("UPDATE case_extracted_fields SET status='conflict' WHERE id=?",(duplicate['id'],))
                        continue
                    c.execute('INSERT INTO case_extracted_fields VALUES(?,?,?,?,?,?,?,?,?)',(uid('cf_'),case_id,field,value,doc_id,fact['source_page'],quote,status,encode(provenance)))

    def add_sku(self,case_id,sku_code,name,description='',declared_code=None,product_family=''):
        self.get_case(case_id);stamp=now();i=uid('sku_')
        with self.lock,self.connect() as c:
            c.execute('INSERT INTO skus(id,case_id,sku_code,name,description,declared_code,product_family,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(i,case_id,sku_code.strip(),name.strip(),description,declared_code,product_family,stamp,stamp));self.event(c,case_id,i,'sku_created','Người lập hồ sơ',{'sku_code':sku_code,'name':name});self._case_status(c,case_id)
        return self.get_sku(i)
    def _invalidate(self,c,sku,actor,reason):
        stamp=now();c.execute("UPDATE skus SET revision=revision+1,status='collecting',analysis_id=NULL,updated_at=? WHERE id=?",(stamp,sku['id']));c.execute('UPDATE decisions SET superseded_at=? WHERE sku_id=? AND superseded_at IS NULL',(stamp,sku['id']));self.event(c,sku['case_id'],sku['id'],'evidence_changed',actor,{'reason':reason,'prior_revision':sku['revision']});self._case_status(c,sku['case_id'])
    def _case_status(self,c,case_id):
        states=[x[0] for x in c.execute('SELECT status FROM skus WHERE case_id=?',(case_id,))]
        status='approved' if states and all(x=='approved' for x in states) else ('in_review' if 'in_review' in states else ('collecting' if states else 'draft'))
        c.execute('UPDATE cases SET status=?,updated_at=? WHERE id=?',(status,now(),case_id))
    def get_sku(self,i):
        with self.connect() as c:
            r=c.execute('SELECT * FROM skus WHERE id=?',(i,)).fetchone()
            if not r:raise KeyError(i)
            d=dict(r)
            d['facts'] = self._sku_records(c, 'facts', d, 'ASC')
            d['evidence'] = [self.public_evidence(row) for row in self._sku_records(c, 'evidence', d, 'DESC')]
            analysis=c.execute('SELECT * FROM analyses WHERE id=?',(d.get('analysis_id'),)).fetchone()
            d['analysis']=decode(analysis['result_json']) if analysis else None
            decision=c.execute('SELECT * FROM decisions WHERE sku_id=? AND superseded_at IS NULL ORDER BY created_at DESC LIMIT 1',(i,)).fetchone()
            d['decision']=dict(decision) if decision else None
            if d['decision']:d['decision']['evidence_ids']=decode(d['decision']['evidence_ids'],[])
            if d['decision']:
                frozen=c.execute('SELECT snapshot_sha256,created_at FROM decision_snapshots WHERE decision_id=?',(d['decision']['id'],)).fetchone()
                d['decision']['snapshot']=dict(frozen)if frozen else None
            d['readiness']=self.readiness(d);return d
    @staticmethod
    def _sku_records(connection, table, sku, order):
        rows = connection.execute(f'''
            SELECT record.*,
                   CASE WHEN record.document_id IS NOT NULL AND
                     (document.id IS NULL OR document.case_id != ? OR
                       (document.sku_id IS NOT NULL AND document.sku_id != ?))
                   THEN 1 ELSE 0 END AS document_scope_mismatch
            FROM {table} AS record LEFT JOIN documents AS document ON document.id=record.document_id
            WHERE record.sku_id=? ORDER BY record.created_at {order}
        ''', (sku['case_id'], sku['id'], sku['id']))
        result=[dict(row) for row in rows]
        if table=='facts':
            for record in result:
                source=connection.execute('SELECT provenance_json FROM fact_sources WHERE fact_id=?',(record['id'],)).fetchone()
                if source:
                    metadata=decode(source[0],{})
                    record.update({k:v for k,v in metadata.items() if k not in record})
        return result

    @staticmethod
    def _require_scoped_document(connection, document_id, sku):
        doc = connection.execute('SELECT case_id,sku_id FROM documents WHERE id=?',(document_id,)).fetchone()
        if not doc or doc['case_id'] != sku['case_id'] or doc['sku_id'] not in (None,sku['id']):
            raise WorkspaceError('Chứng từ không thuộc SKU này hoặc không phải chứng từ dùng chung của hồ sơ.')

    @staticmethod
    def readiness(sku):
        conflict_fields={f['field'] for f in sku['facts'] if f['status']=='conflict'}
        verified={f['field'] for f in sku['facts'] if f['status']=='verified' and f['field'] not in conflict_fields and not f.get('document_scope_mismatch')}
        required={'name','function'}
        if sku.get('product_family') in {'steel','feed','chemical'}:required|={'material','specifications'}
        if sku.get('product_family') in {'steel','feed'}:required|={'manufacturing'}
        if sku.get('product_family') in {'machine','laser','electronic'}:required|={'construction','specifications'}
        if sku.get('product_family')=='food':required|={'material','manufacturing'}
        missing=sorted(required-verified);unverified=[f['id'] for f in sku['facts'] if f['status']!='verified' or f.get('document_scope_mismatch')]
        return {'verified_fields':sorted(verified),'required_fields':sorted(required),'missing_fields':missing,'unverified_fact_ids':unverified,'can_analyze':{'name','function'}<=verified and not conflict_fields,'conflicting_fields':sorted(conflict_fields),'human_review_required':True}
    def add_fact(self,sku_id,field,value,document_id=None,page_number=None,quote='',status='unverified',reviewer=None,source_kind='document',provenance=None):
        if field not in FIELDS:raise WorkspaceError('Thuộc tính không hợp lệ.')
        if status not in {'verified','unverified','conflict'}:raise WorkspaceError('Trạng thái thuộc tính không hợp lệ.')
        if not value.strip():raise WorkspaceError('Giá trị thuộc tính không được để trống.')
        sku=self.get_sku(sku_id);stamp=now();i=uid('fact_')
        with self.lock,self.connect() as c:
            if document_id:
                self._require_scoped_document(c, document_id, sku)
                kind=c.execute('SELECT kind FROM documents WHERE id=?',(document_id,)).fetchone()[0]
                if kind=='legal_reference':raise WorkspaceError('Tài liệu pháp lý không cung cấp thuộc tính thực tế của sản phẩm.')
                page=c.execute('SELECT text FROM pages WHERE document_id=? AND number=?',(document_id,page_number)).fetchone()
                from .document_layout import norm
                if page:
                    from .extractor import DocumentTypeDetector
                    if DocumentTypeDetector.detect(page['text'])['kind']=='legal_reference':raise WorkspaceError('Trang pháp lý không cung cấp thuộc tính sản phẩm.')
                if not page or not quote.strip() or norm(quote) not in norm(page['text']):raise WorkspaceError('Trích đoạn phải có trên đúng trang chứng từ được chọn.')
            if status=='verified' and (not reviewer or (not document_id and source_kind!='manual_declaration')):raise WorkspaceError('Cần người xác minh và nguồn chứng từ hoặc xác nhận trực tiếp.')
            if source_kind=='manual_declaration' and status=='verified' and len(quote.strip())<10:raise WorkspaceError('Ghi căn cứ xác nhận trực tiếp trước khi đánh dấu đã kiểm tra.')
            c.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(i,sku_id,field,value.strip(),document_id,page_number,quote,status,reviewer,source_kind,stamp,stamp));self._invalidate(c,sku,reviewer or 'Người nhập','Thêm thuộc tính '+field)
            if provenance:
                source={**provenance,'sku_id':sku_id,'source_document_id':document_id,'source_page':page_number,'source_quote':quote,'value_origin':provenance.get('source_kind','document_extracted')}
                c.execute('INSERT INTO fact_sources VALUES(?,?)',(i,encode(source)))
        return self.get_sku(sku_id)
    def update_fact(self,sku_id,fact_id,status,reviewer):
        sku=self.get_sku(sku_id)
        if status not in {'verified','unverified','conflict'}:raise WorkspaceError('Trạng thái không hợp lệ.')
        with self.lock,self.connect() as c:
            f=c.execute('SELECT * FROM facts WHERE id=? AND sku_id=?',(fact_id,sku_id)).fetchone()
            if not f:raise KeyError(fact_id)
            if status=='verified':
                if not reviewer.strip() or not f['quote'].strip():raise WorkspaceError('Cần người kiểm tra và trích đoạn nguồn.')
                if f['document_id']:
                    self._require_scoped_document(c, f['document_id'], sku)
                    p=c.execute('SELECT text FROM pages WHERE document_id=? AND number=?',(f['document_id'],f['page_number'])).fetchone()
                    if not p or f['quote'].strip()not in p['text']:raise WorkspaceError('Trích đoạn không còn có trên đúng trang; ghi lại thuộc tính với nguồn hiện tại.')
                elif f['source_kind']!='manual_declaration' or len(f['quote'].strip())<10:raise WorkspaceError('Thuộc tính thiếu chứng từ không được nâng thành đã xác minh; ghi xác nhận trực tiếp có căn cứ.')
            c.execute('UPDATE facts SET status=?,reviewer=?,updated_at=? WHERE id=?',(status,reviewer,now(),fact_id));self._invalidate(c,sku,reviewer,'Cập nhật xác minh thuộc tính')
        return self.get_sku(sku_id)

    def delete_fact(self,sku_id,fact_id):
        sku=self.get_sku(sku_id)
        with self.lock,self.connect() as c:
            f=c.execute('SELECT * FROM facts WHERE id=? AND sku_id=?',(fact_id,sku_id)).fetchone()
            if not f:raise KeyError(fact_id)
            c.execute('DELETE FROM facts WHERE id=? AND sku_id=?',(fact_id,sku_id))
            self._invalidate(c,sku,'Người dùng','Xóa thuộc tính '+f['field'])
        return self.get_sku(sku_id)

    def delete_evidence(self,sku_id,evidence_id):
        sku=self.get_sku(sku_id)
        with self.lock,self.connect() as c:
            ev=c.execute('SELECT * FROM evidence WHERE id=? AND sku_id=?',(evidence_id,sku_id)).fetchone()
            if not ev:raise KeyError(evidence_id)
            c.execute('DELETE FROM evidence WHERE id=? AND sku_id=?',(evidence_id,sku_id))
            self._invalidate(c,sku,'Người dùng','Xóa căn cứ '+ev['title'])
        return self.get_sku(sku_id)

    def delete_sku(self,sku_id):
        with self.lock,self.connect() as c:
            sku=c.execute('SELECT * FROM skus WHERE id=?',(sku_id,)).fetchone()
            if not sku:raise KeyError(sku_id)
            case_id=sku['case_id']
            dec_ids=[r[0] for r in c.execute('SELECT id FROM decisions WHERE sku_id=?',(sku_id,)).fetchall()]
            for did in dec_ids:c.execute('DELETE FROM decision_snapshots WHERE decision_id=?',(did,))
            c.execute('DELETE FROM decisions WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM tax_scenarios WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM comparisons WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM analyses WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM facts WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM evidence WHERE sku_id=?',(sku_id,))
            c.execute('UPDATE documents SET sku_id=NULL WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM skus WHERE id=?',(sku_id,))
            self.event(c,case_id,sku_id,'sku_deleted','Người dùng',{'sku_code':sku['sku_code'],'name':sku['name']})
            self._case_status(c,case_id)
        return {'deleted':True,'case_id':case_id}

    def delete_case(self,case_id):
        with self.lock,self.connect() as c:
            cs=c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not cs:raise KeyError(case_id)
            skus=c.execute('SELECT id FROM skus WHERE case_id=?',(case_id,)).fetchall()
            for s in skus:
                sku_id=s[0]
                c.execute('DELETE FROM facts WHERE sku_id=?',(sku_id,))
                c.execute('DELETE FROM evidence WHERE sku_id=?',(sku_id,))
            docs=c.execute('SELECT id,path FROM documents WHERE case_id=?',(case_id,)).fetchall()
            for doc in docs:
                c.execute('DELETE FROM pages WHERE document_id=?',(doc['id'],))
                try:
                    p=Path(doc['path'])
                    if p.exists():p.unlink(missing_ok=True)
                except Exception:pass
            c.execute('DELETE FROM documents WHERE case_id=?',(case_id,))
            for s in skus:
                sku_id=s[0]
                dec_ids=[r[0] for r in c.execute('SELECT id FROM decisions WHERE sku_id=?',(sku_id,)).fetchall()]
                for did in dec_ids:c.execute('DELETE FROM decision_snapshots WHERE decision_id=?',(did,))
                c.execute('DELETE FROM decisions WHERE sku_id=?',(sku_id,))
                c.execute('DELETE FROM tax_scenarios WHERE sku_id=?',(sku_id,))
                c.execute('DELETE FROM comparisons WHERE sku_id=?',(sku_id,))
                c.execute('DELETE FROM analyses WHERE sku_id=?',(sku_id,))
            c.execute('DELETE FROM skus WHERE case_id=?',(case_id,))
            c.execute('DELETE FROM events WHERE case_id=?',(case_id,))
            c.execute('DELETE FROM cases WHERE id=?',(case_id,))
        return {'deleted':True,'id':case_id}

    def delete_document(self,document_id):
        with self.lock,self.connect() as c:
            doc=c.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
            if not doc:raise KeyError(document_id)
            c.execute('UPDATE facts SET document_id=NULL WHERE document_id=?',(document_id,))
            c.execute('UPDATE evidence SET document_id=NULL WHERE document_id=?',(document_id,))
            c.execute('DELETE FROM pages WHERE document_id=?',(document_id,))
            c.execute('DELETE FROM documents WHERE id=?',(document_id,))
            try:
                p=Path(doc['path'])
                if p.exists():p.unlink(missing_ok=True)
            except Exception:pass
            self.event(c,doc['case_id'],doc['sku_id'],'document_deleted','Người dùng',{'name':doc['name'],'document_id':document_id})
        return {'deleted':True,'id':document_id}

    def add_evidence(self,sku_id,data):
        sku=self.get_sku(sku_id);i=uid('ev_');stamp=now()
        if data['kind'] not in {'tariff','chapter_note','section_note','ruling','technical','other'}:raise WorkspaceError('Loại căn cứ không hợp lệ.')
        if data['role'] not in {'reference','supports','excludes','not_applicable','conflict'}:raise WorkspaceError('Vai trò căn cứ không hợp lệ.')
        if data.get('source_url') and not data['source_url'].startswith(('https://','http://')):raise WorkspaceError('Đường dẫn nguồn phải dùng http/https.')
        if data.get('lifecycle') not in {'not_checked','active','withdrawn','superseded'}:raise WorkspaceError('Trạng thái hiệu lực không hợp lệ.')
        if data.get('document_id'):
            with self.connect() as c:
                self._require_scoped_document(c, data['document_id'], sku)
                p=c.execute('SELECT text FROM pages WHERE document_id=? AND number=?',(data['document_id'],data.get('page_number'))).fetchone()
            if not p or data['quote'] not in p['text']:raise WorkspaceError('Căn cứ phải trích từ đúng trang trong hồ sơ.')
        if data.get('reviewer') and data.get('lifecycle')=='not_checked':raise WorkspaceError('Kiểm tra trạng thái nguồn trước khi đánh dấu căn cứ đã đối chiếu.')
        with self.lock,self.connect() as c:
            c.execute('INSERT INTO evidence(id,sku_id,kind,title,source_url,document_id,page_number,quote,role,jurisdiction,nomenclature,effective_from,effective_to,lifecycle,reviewer,verified_at,created_at,target_codes_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,sku_id,data['kind'],data['title'],data.get('source_url',''),data.get('document_id'),data.get('page_number'),data['quote'],data['role'],data.get('jurisdiction','VN'),data.get('nomenclature','AHTN2022'),data.get('effective_from'),data.get('effective_to'),data.get('lifecycle','not_checked'),data.get('reviewer'),stamp if data.get('reviewer') else None,stamp,encode(data.get('target_codes',[]))));self._invalidate(c,sku,data.get('reviewer') or 'Người nhập','Bổ sung căn cứ')
        return self.get_sku(sku_id)
    def review_evidence(self,sku_id,evidence_id,role,lifecycle,reviewer,resolution_note,target_codes):
        sku=self.get_sku(sku_id)
        if role not in {'reference','supports','excludes','not_applicable','conflict'}or lifecycle not in {'not_checked','active','withdrawn','superseded'}:raise WorkspaceError('Trạng thái căn cứ không hợp lệ.')
        if not reviewer.strip()or len(resolution_note.strip())<10:raise WorkspaceError('Ghi người đối chiếu và lý do cập nhật căn cứ.')
        with self.lock,self.connect()as c:
            old=c.execute('SELECT * FROM evidence WHERE id=? AND sku_id=?',(evidence_id,sku_id)).fetchone()
            if not old:raise KeyError(evidence_id)
            if role in {'supports','excludes'} and old['document_id']:
                self._require_scoped_document(c, old['document_id'], sku)
            c.execute('UPDATE evidence SET role=?,lifecycle=?,reviewer=?,verified_at=?,resolution_note=?,target_codes_json=? WHERE id=?',(role,lifecycle,reviewer,now(),resolution_note,encode(target_codes),evidence_id))
            self.event(c,sku['case_id'],sku_id,'evidence_reviewed',reviewer,{'evidence_id':evidence_id,'prior_role':old['role'],'prior_lifecycle':old['lifecycle'],'role':role,'lifecycle':lifecycle,'reason':resolution_note})
            self._invalidate(c,sku,reviewer,'Đối chiếu lại vai trò/hiệu lực căn cứ')
        return self.get_sku(sku_id)
    def save_analysis(self,sku_id,result):
        sku=self.get_sku(sku_id)
        if result.get('base_revision',sku['revision'])!=sku['revision']:raise ConflictError('Thuộc tính đã đổi trong lúc phân tích; cần chạy lại.')
        i=uid('ana_');result=dict(result,analysis_id=i,sku_revision=sku['revision']);stamp=now()
        with self.lock,self.connect() as c:
            if c.execute('SELECT revision FROM skus WHERE id=?',(sku_id,)).fetchone()[0]!=sku['revision']:raise ConflictError('Hồ sơ vừa thay đổi; kết quả cũ không được áp dụng.')
            c.execute('UPDATE decisions SET superseded_at=? WHERE sku_id=? AND superseded_at IS NULL',(stamp,sku_id));c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?,?)',(i,sku_id,sku['revision'],result['input_hash'],result['engine'],result['model_version'],encode(result),stamp));c.execute("UPDATE skus SET analysis_id=?,status='in_review',updated_at=? WHERE id=?",(i,stamp,sku_id));self.event(c,sku['case_id'],sku_id,'analysis_completed','Hệ thống',{'engine':result['engine'],'model_version':result['model_version'],'candidates':[x['code'] for x in result['candidates']],'manual_candidate_codes':result.get('manual_candidate_codes',[]),'revision':sku['revision']});self._case_status(c,sku['case_id'])
        return self.get_sku(sku_id)
    def review(self,sku_id,code,reason,reviewer,preparer,evidence_ids,expected_revision,catalogue,action='approve',alternative_code='',alternative_reason='',classification_basis_confirmed=False,source_context=None,expected_analysis_id=None):
        sku=self.get_sku(sku_id)
        if sku['revision']!=expected_revision:raise ConflictError('Hồ sơ đã thay đổi. Đọc lại thuộc tính và kết quả trước khi duyệt.')
        if not reviewer.strip() or not preparer.strip():raise WorkspaceError('Cần tên người lập và người duyệt.')
        if action=='return':
            with self.lock,self.connect() as c:
                c.execute('UPDATE decisions SET superseded_at=? WHERE sku_id=? AND superseded_at IS NULL',(now(),sku_id));c.execute("UPDATE skus SET status='returned',updated_at=? WHERE id=?",(now(),sku_id));self.event(c,sku['case_id'],sku_id,'returned',reviewer,{'reason':reason});self._case_status(c,sku['case_id'])
            return self.get_sku(sku_id)
        if person_key(reviewer)==person_key(preparer):raise WorkspaceError('Người duyệt cần khác người lập để có đối chiếu độc lập.')
        if code not in catalogue:raise WorkspaceError('Mã phải là HS8 trong danh mục Việt Nam đã nạp.')
        if len(reason.strip())<30:raise WorkspaceError('Ghi lý do phân loại tối thiểu 30 ký tự, gồm tiêu chí phân biệt và căn cứ.')
        if sku['readiness']['missing_fields'] or any(f['status']=='conflict' for f in sku['facts']):raise WorkspaceError('Còn thuộc tính bắt buộc chưa kiểm tra hoặc đang mâu thuẫn.')
        if not sku['analysis'] or sku['analysis']['sku_revision']!=sku['revision']:raise WorkspaceError('Cần phân tích lại sau thay đổi dữ liệu.')
        if expected_analysis_id and expected_analysis_id!=sku['analysis_id']:raise ConflictError('Kết quả phân tích đã thay đổi; mở lại trước khi duyệt.')
        alternatives={r['code']for r in sku['analysis']['candidates']if r['code']!=code}
        if not classification_basis_confirmed:raise WorkspaceError('Xác nhận đã đối chiếu bản chất hàng và căn cứ phân loại, độc lập với lợi ích thuế.')
        if alternatives and (alternative_code not in alternatives or len(alternative_reason.strip())<20):raise WorkspaceError('Chọn một mã khác trong danh sách và ghi tiêu chí/căn cứ loại trừ trước khi duyệt.')
        evidence={x['id']:x for x in sku['evidence']};chosen=[evidence.get(i) for i in evidence_ids]
        if not chosen or any(x is None for x in chosen):raise WorkspaceError('Chọn căn cứ thuộc đúng SKU này.')
        case=self.get_case(sku['case_id']);day=case['classification_date']
        from .legal import AHTN2022_START
        if day < AHTN2022_START:raise WorkspaceError('Danh mục AHTN 2022 không áp dụng cho ngày phân loại trước 30/12/2022.')
        applicable=[]
        for e in chosen:
            if e.get('document_scope_mismatch'):
                if e['role'] in {'supports','excludes'}:
                    raise WorkspaceError('Căn cứ trích từ chứng từ của SKU khác. Ghi lại căn cứ theo đúng SKU trước khi duyệt.')
                continue
            if e['jurisdiction']!='VN' or e['nomenclature']!='AHTN2022':continue
            if e['lifecycle']!='active' or not e['reviewer'] or e['role'] not in {'supports','excludes'}:continue
            if not e['effective_from'] or not (e['source_url'] or e['document_id']):continue
            if e['effective_from'] and day<e['effective_from']:continue
            if e['effective_to'] and day>e['effective_to']:continue
            applicable.append(e)
        if any(e['role']=='conflict' for e in sku['evidence']):raise WorkspaceError('Hồ sơ còn căn cứ mâu thuẫn; phải ghi nhận xử lý, không được chỉ bỏ chọn căn cứ đó.')
        if any(e['role'] in {'supports','excludes'} and e not in applicable for e in chosen):raise WorkspaceError('Có căn cứ được chọn chưa đạt yêu cầu về hiệu lực, vai trò hoặc phạm vi.')
        if not any(e['kind'] in {'tariff','chapter_note','section_note','ruling'} and e['role']=='supports' and any(code.startswith(t)for t in e.get('target_codes',[])) for e in applicable):raise WorkspaceError('Cần căn cứ phân loại hỗ trợ đúng mã/phạm vi đã chọn, được đối chiếu về quốc gia, phiên bản và hiệu lực.')
        stamp=now();i=uid('dec_')
        with self.lock,self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # Optimistic check repeated inside the write transaction.
            live=c.execute('SELECT revision,analysis_id FROM skus WHERE id=?',(sku_id,)).fetchone()
            if live['revision']!=expected_revision or live['analysis_id']!=sku['analysis_id']:raise ConflictError('Hồ sơ hoặc phân tích vừa thay đổi; quyết định chưa được lưu.')
            c.execute('UPDATE decisions SET superseded_at=? WHERE sku_id=? AND superseded_at IS NULL',(stamp,sku_id));c.execute('INSERT INTO decisions(id,sku_id,sku_revision,code,reason,reviewer,preparer,evidence_ids,classification_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(i,sku_id,sku['revision'],code,reason,reviewer,preparer,encode(evidence_ids),day,stamp));c.execute("UPDATE skus SET status='approved',updated_at=? WHERE id=?",(stamp,sku_id))
            documents=[]
            for row in c.execute('SELECT * FROM documents WHERE case_id=?',(sku['case_id'],)).fetchall():
                doc=self.public_document(dict(row));doc['pages']=[dict(p)for p in c.execute('SELECT * FROM pages WHERE document_id=? ORDER BY number',(doc['id'],))];documents.append(doc)
            comparisons=[decode(r[0])for r in c.execute('SELECT result_json FROM comparisons WHERE sku_id=? AND sku_revision=? AND analysis_id=? ORDER BY created_at',(sku_id,sku['revision'],sku['analysis_id']))]
            case_meta={k:v for k,v in case.items()if k not in {'skus','documents','events'}}
            decision={'id':i,'code':code,'reason':reason,'reviewer':reviewer,'preparer':preparer,'evidence_ids':evidence_ids,'classification_date':day,'created_at':stamp,'alternative_code':alternative_code,'alternative_reason':alternative_reason,'classification_basis_confirmed':True}
            snapshot={'schema_version':'decision-snapshot-1','decision':decision,'case':case_meta,'sku':{k:v for k,v in sku.items()if k not in {'decision','readiness'}},'selected_catalogue_row':catalogue[code],'alternative_catalogue_row':catalogue.get(alternative_code),'selected_evidence':chosen,'documents':documents,'comparisons':comparisons,'source_context':source_context or{},'retention':retention_for_case(case),'identity_verified':False,'digital_signature':False,'approved_decisions_are_training_gold':False,'source_capture_warnings':[e['id']for e in chosen if not e.get('document_id')]}
            serialized=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(serialized.encode()).hexdigest()
            c.execute('INSERT INTO decision_snapshots VALUES(?,?,?,?)',(i,serialized,digest,stamp))
            self.event(c,sku['case_id'],sku_id,'decision_approved',reviewer,{'code':code,'reason':reason,'evidence_ids':evidence_ids,'revision':sku['revision'],'snapshot_sha256':digest,'alternative_code':alternative_code,'review_type':'internal_review_not_customs_ruling','expert_gold':False});self._case_status(c,sku['case_id'])
        return self.get_sku(sku_id)
    def save_comparison(self,sku_id,expected_revision,expected_analysis_id,data,result):
        sku=self.get_sku(sku_id);i=uid('cmp_');stamp=now()
        with self.lock,self.connect()as c:
            c.execute('BEGIN IMMEDIATE');live=c.execute('SELECT revision,analysis_id FROM skus WHERE id=?',(sku_id,)).fetchone()
            if live['revision']!=expected_revision or live['analysis_id']!=expected_analysis_id:raise ConflictError('SKU hoặc phân tích đã thay đổi; cần so sánh lại.')
            result=dict(result,id=i,created_at=stamp)
            c.execute('INSERT INTO comparisons VALUES(?,?,?,?,?,?,?)',(i,sku_id,expected_revision,expected_analysis_id,encode(data),encode(result),stamp))
            self.event(c,sku['case_id'],sku_id,'consequences_compared',data['reviewer'],{'comparison_id':i,'codes':[r['code']for r in result['rows']],'sku_revision':expected_revision})
        return result
    def comparisons(self,sku_id):
        sku=self.get_sku(sku_id)
        with self.connect()as c:rows=c.execute('SELECT * FROM comparisons WHERE sku_id=? ORDER BY created_at DESC',(sku_id,)).fetchall()
        return [dict(decode(r['result_json']),stale=r['sku_revision']!=sku['revision']or r['analysis_id']!=sku['analysis_id'])for r in rows]
    def snapshot(self,decision_id):
        with self.connect()as c:row=c.execute('SELECT * FROM decision_snapshots WHERE decision_id=?',(decision_id,)).fetchone()
        if not row:raise KeyError(decision_id)
        valid=hashlib.sha256(row['snapshot_json'].encode()).hexdigest()==row['snapshot_sha256']
        return {'decision_id':decision_id,'snapshot_sha256':row['snapshot_sha256'],'integrity_matches':valid,'snapshot':decode(row['snapshot_json']),'tamper_proof_against_administrator':False}
    def verify_events(self):
        previous='GENESIS';errors=[]
        with self.connect()as c:rows=c.execute('SELECT * FROM events ORDER BY id').fetchall()
        for r in rows:
            body=encode({'case':r['case_id'],'sku':r['sku_id'],'action':r['action'],'actor':r['actor'],'payload':decode(r['payload']),'at':r['created_at']})
            expected=hashlib.sha256((previous+body).encode()).hexdigest()
            if r['previous_hash']!=previous or r['event_hash']!=expected:errors.append(r['id'])
            previous=r['event_hash']
        return {'events_checked':len(rows),'integrity_matches':not errors,'invalid_event_ids':errors,'last_hash':previous,'trusted_external_anchor':False,'tamper_proof_against_administrator':False}
    def summary(self):
        with self.connect() as c:
            cases=c.execute('SELECT count(*) FROM cases').fetchone()[0];skus=c.execute('SELECT count(*) FROM skus').fetchone()[0];approved=c.execute("SELECT count(*) FROM skus WHERE status='approved'").fetchone()[0];docs=c.execute('SELECT count(*) FROM documents').fetchone()[0];unverified=c.execute("SELECT count(*) FROM facts WHERE status!='verified'").fetchone()[0];processing=c.execute("SELECT count(*) FROM documents WHERE status IN ('queued','processing')").fetchone()[0];analyses=[decode(x[0],{}) for x in c.execute('SELECT result_json FROM analyses')];events=[self.public_event(dict(x)) for x in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 10')]
        return {'cases':cases,'skus':skus,'approved':approved,'documents':docs,'unverified_facts':unverified,'processing_documents':processing,'analyses':len(analyses),'events':events,'automatic_hs8_acceptance_enabled':False,'user_corrections_are_gold':False}

    def update_sku(self,i,values,actor='Người nhập'):
        sku=self.get_sku(i);allowed={'sku_code','name','description','declared_code','product_family'}
        values={k:v for k,v in values.items() if k in allowed}
        if not values:return sku
        with self.lock,self.connect() as c:
            c.execute('UPDATE skus SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[i]);self._invalidate(c,sku,actor,'Sửa thông tin SKU')
        return self.get_sku(i)
    def update_case(self,i,values,actor='Người nhập'):
        case=self.get_case(i);allowed={'title','owner','notes','classification_date','trade_type','declaration_number','declaration_registered_date','legal_hold'};values={k:v for k,v in values.items() if k in allowed and case.get(k)!=v}
        if not values:return self.get_case(i)
        with self.lock,self.connect() as c:
            c.execute('UPDATE cases SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[i])
            if {'classification_date','trade_type','declaration_number','declaration_registered_date'}&values.keys():
                for row in c.execute('SELECT * FROM skus WHERE case_id=?',(i,)).fetchall():self._invalidate(c,dict(row),actor,'Đổi ngày, luồng XNK hoặc thông tin tờ khai')
            self.event(c,i,None,'case_updated',actor,values)
        return self.get_case(i)
