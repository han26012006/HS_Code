"""HS Workspace: local Python API + built web app. No pretrained model downloads on startup."""
from __future__ import annotations
import io,json,os,re,threading,zipfile
from contextlib import asynccontextmanager
from datetime import date,datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal
import pandas as pd
from fastapi import FastAPI,Depends,Header,HTTPException,UploadFile,File,Form,Query
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from hs_assistant.workspace import Workspace,WorkspaceError,ConflictError,FIELDS,encode,now,uid
from hs_assistant.documents import DocumentService,MAX_UPLOAD
from hs_assistant.catalogue import Catalogue,InferenceService
from hs_assistant.model_registry import find_artifacts
from hs_assistant.tax import TaxEngine,TaxError

ROOT=Path(__file__).resolve().parent
API_KEY=os.environ.get('HS_API_KEY')
state={}

def check_key(x_api_key:str|None=Header(default=None)):
    import hmac
    if API_KEY and (not x_api_key or not hmac.compare_digest(x_api_key,API_KEY)):raise HTTPException(401,'Cần khóa truy cập không gian làm việc.')

def jsonable(x):return json.loads(json.dumps(x,ensure_ascii=False,default=str,allow_nan=False))

@asynccontextmanager
async def lifespan(app):
    directory=Path(os.environ.get('HS_WORKSPACE',ROOT/'runtime'));directory.mkdir(parents=True,exist_ok=True)
    db=Workspace(directory/'workspace.sqlite');cat=Catalogue(ROOT/'data/catalogue.jsonl',ROOT/'data/legal_notes.json');docs=DocumentService(db,directory/'uploads');inference=InferenceService(cat,find_artifacts(ROOT),directory/'instruction')
    state.update(db=db,catalogue=cat,documents=docs,inference=inference,dir=directory,tax=TaxEngine(ROOT/'data/tax'));docs.resume()
    from hs_assistant.precedents import PrecedentLibrary
    state['precedents']=PrecedentLibrary(ROOT/'data/precedent_index.jsonl')
    from hs_assistant.audit_log import AuditLog
    state['project_knowledge']=None
    if os.environ.get('HS_PROJECT_KNOWLEDGE_DIR'):
        from hs_assistant.project_knowledge import ProjectKnowledge
        state['project_knowledge']=ProjectKnowledge(os.environ['HS_PROJECT_KNOWLEDGE_DIR'])
    state['log']=AuditLog(os.environ.get('HS_LOG',str(directory/'legacy_decisions.sqlite')))
    yield
    docs.close();state.clear()

app=FastAPI(title='HS Workspace — Trợ lý phân loại có kiểm chứng',version='2.2.0',lifespan=lifespan)
@app.exception_handler(ConflictError)
async def conflict_handler(request,e):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':str(e)},status_code=409)
@app.exception_handler(WorkspaceError)
async def workspace_handler(request,e):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':str(e)},status_code=422)
@app.exception_handler(KeyError)
async def missing_handler(request,e):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':'Không tìm thấy bản ghi.'},status_code=404)

class CaseIn(BaseModel):
    title:str=Field(min_length=3,max_length=250);owner:str=Field(min_length=2,max_length=100);trade_type:Literal['import','export']='import';classification_date:date=Field(default_factory=lambda:datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date());notes:str=Field(default='',max_length=4000)
    declaration_number:str=Field(default='',max_length=100);declaration_registered_date:date|None=None;legal_hold:bool=False
class SKUIn(BaseModel):
    sku_code:str=Field(min_length=1,max_length=80);name:str=Field(min_length=3,max_length=300);description:str=Field(default='',max_length=10000);declared_code:str|None=Field(default=None,max_length=30);product_family:Literal['general','steel','feed','laser','machine','electronic','chemical','food']='general'
class FactIn(BaseModel):
    field:str;value:str=Field(min_length=2,max_length=5000);document_id:str|None=None;page_number:int|None=Field(default=None,ge=1);quote:str=Field(default='',max_length=10000);status:Literal['verified','unverified','conflict']='unverified';reviewer:str|None=Field(default=None,max_length=100);source_kind:Literal['document','manual_declaration']='document'
class FactReview(BaseModel):status:Literal['verified','unverified','conflict'];reviewer:str=Field(min_length=2,max_length=100)
class EvidenceIn(BaseModel):
    kind:Literal['tariff','chapter_note','section_note','ruling','technical','other'];title:str=Field(min_length=3,max_length=400);source_url:str=Field(default='',max_length=2000);document_id:str|None=None;page_number:int|None=Field(default=None,ge=1);quote:str=Field(min_length=5,max_length=15000);role:Literal['reference','supports','excludes','not_applicable','conflict']='reference';jurisdiction:str=Field(default='VN',max_length=20);nomenclature:str=Field(default='AHTN2022',max_length=40);effective_from:date|None=None;effective_to:date|None=None;lifecycle:Literal['not_checked','active','withdrawn','superseded']='not_checked';reviewer:str|None=Field(default=None,max_length=100)
    target_codes:list[str]=Field(default_factory=list,max_length=30)
class EvidenceReviewIn(BaseModel):
    role:Literal['reference','supports','excludes','not_applicable','conflict'];lifecycle:Literal['not_checked','active','withdrawn','superseded'];reviewer:str=Field(min_length=2,max_length=100);resolution_note:str=Field(min_length=10,max_length=4000);target_codes:list[str]=Field(default_factory=list,max_length=30)
class AnalyzeIn(BaseModel):
    engine:Literal['catalogue','model','qwen','openai']='catalogue'
    allow_paid_api:bool=False
class ReviewIn(BaseModel):
    code:str=Field(default='',max_length=8);reason:str=Field(min_length=5,max_length=8000);reviewer:str=Field(min_length=2,max_length=100);preparer:str=Field(min_length=2,max_length=100);evidence_ids:list[str]=Field(default_factory=list,max_length=100);expected_revision:int;action:Literal['approve','return']='approve'
    expected_analysis_id:str|None=Field(default=None,max_length=80);alternative_code:str=Field(default='',max_length=8);alternative_reason:str=Field(default='',max_length=4000);classification_basis_confirmed:bool=False
class CatalogItems(BaseModel):items:list[dict]=Field(min_length=2,max_length=5000);threshold:float=Field(default=.85,ge=.5,le=1.)
class EstimateItem(BaseModel):code:str=Field(pattern=r'^\d{8}$');import_rate:float=Field(ge=0,le=2000);vat_rate:float=Field(ge=0,le=100);excise_amount:float=Field(default=0,ge=0);environmental_amount:float=Field(default=0,ge=0)
class Estimate(BaseModel):customs_value:float=Field(gt=0);items:list[EstimateItem]=Field(min_length=1,max_length=10)

@app.get('/health')
def health():
    s=state['inference'].status();return {'status':'ok','version':'2.2.0','phien_ban_mo_hinh':s['catalogue_version'],'so_dong_nhan':s['catalogue_rows'],'model_artifacts_available':s['model_artifacts_available'],'authentication_required':bool(API_KEY),'automatic_hs8_acceptance_enabled':False}

@app.get('/api/v2/status',dependencies=[Depends(check_key)])
def status():return dict(state['inference'].status(),authentication_required=bool(API_KEY),identity_mode='shared_api_key' if API_KEY else 'local_operator_names_not_authenticated',workflow_version='2.2.0',jurisdiction='VN',nomenclature='AHTN2022')
@app.get('/api/v2/summary',dependencies=[Depends(check_key)])
def summary():return state['db'].summary()
@app.get('/api/v2/cases',dependencies=[Depends(check_key)])
def cases(q:str='',status:str|None=None):return state['db'].cases(q,status)
@app.post('/api/v2/cases',dependencies=[Depends(check_key)])
def create_case(inp:CaseIn):
    x=inp.model_dump(mode='json');return state['db'].create_case(**x)
@app.get('/api/v2/cases/{case_id}',dependencies=[Depends(check_key)])
def get_case(case_id:str):return state['db'].get_case(case_id)
@app.patch('/api/v2/cases/{case_id}',dependencies=[Depends(check_key)])
def edit_case(case_id:str,inp:CaseIn):
    x=inp.model_dump(mode='json');return state['db'].update_case(case_id,x,inp.owner)
@app.delete('/api/v2/cases/{case_id}',dependencies=[Depends(check_key)])
def delete_case(case_id:str):return state['db'].delete_case(case_id)
@app.post('/api/v2/cases/{case_id}/skus',dependencies=[Depends(check_key)])
def add_sku(case_id:str,inp:SKUIn):return state['db'].add_sku(case_id,**inp.model_dump())
@app.delete('/api/v2/skus/{sku_id}',dependencies=[Depends(check_key)])
def delete_sku(sku_id:str):return state['db'].delete_sku(sku_id)
@app.get('/api/v2/skus/{sku_id}',dependencies=[Depends(check_key)])
def get_sku(sku_id:str):return state['db'].get_sku(sku_id)
@app.patch('/api/v2/skus/{sku_id}',dependencies=[Depends(check_key)])
def edit_sku(sku_id:str,inp:SKUIn):return state['db'].update_sku(sku_id,inp.model_dump())
@app.post('/api/v2/skus/{sku_id}/facts',dependencies=[Depends(check_key)])
def fact(sku_id:str,inp:FactIn):
    from hs_assistant.catalogue import fold
    if re.search(r'(?:\bhs(?:\s*code)?|ma\s*(?:hs|so)|thuoc\s*nhom|phan\s*nhom)\s*[:.\-]?\s*\d[\d .]{3,18}',fold(inp.value)):raise HTTPException(422,'Thuộc tính sản phẩm không chứa mã/kết luận HS; lưu nội dung đó trong mục căn cứ hoặc mã đang khai.')
    return state['db'].add_fact(sku_id,**inp.model_dump())
@app.patch('/api/v2/skus/{sku_id}/facts/{fact_id}',dependencies=[Depends(check_key)])
def fact_review(sku_id:str,fact_id:str,inp:FactReview):return state['db'].update_fact(sku_id,fact_id,inp.status,inp.reviewer)
@app.delete('/api/v2/skus/{sku_id}/facts/{fact_id}',dependencies=[Depends(check_key)])
def delete_fact(sku_id:str,fact_id:str):return state['db'].delete_fact(sku_id,fact_id)
@app.post('/api/v2/skus/{sku_id}/evidence',dependencies=[Depends(check_key)])
def add_evidence(sku_id:str,inp:EvidenceIn):
    data=inp.model_dump()
    for k in ['effective_from','effective_to']:data[k]=str(data[k]) if data[k] else None
    if data['effective_from'] and data['effective_to'] and data['effective_from']>data['effective_to']:raise HTTPException(422,'Khoảng hiệu lực không hợp lệ.')
    validate_target_codes(data['target_codes'])
    return state['db'].add_evidence(sku_id,data)
def validate_target_codes(codes):
    if any(not re.fullmatch(r'(?:\d{2}|\d{4}|\d{6}|\d{8})',x)or not any(c.startswith(x)for c in state['catalogue'].by_code)for x in codes):raise HTTPException(422,'Phạm vi căn cứ phải là mã 2/4/6/8 số có trong danh mục đã nạp.')
@app.patch('/api/v2/skus/{sku_id}/evidence/{evidence_id}',dependencies=[Depends(check_key)])
def review_evidence(sku_id:str,evidence_id:str,inp:EvidenceReviewIn):
    validate_target_codes(inp.target_codes);return state['db'].review_evidence(sku_id,evidence_id,**inp.model_dump())
@app.delete('/api/v2/skus/{sku_id}/evidence/{evidence_id}',dependencies=[Depends(check_key)])
def delete_evidence(sku_id:str,evidence_id:str):return state['db'].delete_evidence(sku_id,evidence_id)
@app.post('/api/v2/skus/{sku_id}/analyze',dependencies=[Depends(check_key)])
def analyze(sku_id:str,inp:AnalyzeIn):
    sku=state['db'].get_sku(sku_id)
    try:result=state['inference'].analyze(sku,inp.engine,inp.allow_paid_api)
    except ValueError as e:raise HTTPException(409,str(e))
    result['base_revision']=sku['revision'];return state['db'].save_analysis(sku_id,result)
@app.post('/api/v2/skus/{sku_id}/review',dependencies=[Depends(check_key)])
def review(sku_id:str,inp:ReviewIn):
    from hs_assistant.archival import source_context
    return state['db'].review(sku_id,**inp.model_dump(),catalogue=state['catalogue'].by_code,source_context=source_context(ROOT,state['catalogue'].version))

@app.get('/api/v2/decisions/{decision_id}/snapshot',dependencies=[Depends(check_key)])
def decision_snapshot(decision_id:str):return state['db'].snapshot(decision_id)

@app.get('/api/v2/audit-integrity',dependencies=[Depends(check_key)])
def audit_integrity():return state['db'].verify_events()

@app.get('/api/v2/legal-status',dependencies=[Depends(check_key)])
def legal_status(as_of:date):
    from hs_assistant.legal import dated_registry
    return dated_registry(json.loads((ROOT/'data/legal_sources.json').read_text()),as_of.isoformat())

@app.post('/api/v2/cases/{case_id}/documents',dependencies=[Depends(check_key)])
async def documents(case_id:str,files:list[UploadFile]=File(...),sku_id:str|None=Form(default=None)):
    if len(files)>30:raise HTTPException(422,'Tối đa 30 tệp mỗi lượt.')
    result={'documents':[],'added':0,'skipped':[]}
    for f in files:
        content=await f.read(MAX_UPLOAD+1)
        try:r=state['documents'].upload(case_id,f.filename or 'document',content,sku_id)
        except (WorkspaceError,zipfile.BadZipFile) as e:raise HTTPException(422,str(e))
        result['documents']+=r['documents'];result['added']+=r['added'];result['skipped']+=r['skipped']
    return result
@app.get('/api/v2/documents/{document_id}',dependencies=[Depends(check_key)])
def document(document_id:str):return dict(state['documents'].get(document_id),pages=state['documents'].pages(document_id))
@app.get('/api/v2/documents/{document_id}/file',dependencies=[Depends(check_key)])
def document_file(document_id:str):
    d=state['documents'].get(document_id,True);return FileResponse(d['path'],media_type=d['mime'],filename=d['name'],content_disposition_type='inline' if d['mime'] in {'application/pdf','image/png','image/jpeg'} else 'attachment',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
@app.post('/api/v2/documents/{document_id}/retry',dependencies=[Depends(check_key)])
def retry_document(document_id:str):state['documents'].retry(document_id);return {'status':'queued'}
@app.delete('/api/v2/documents/{document_id}',dependencies=[Depends(check_key)])
def delete_document(document_id:str):return state['db'].delete_document(document_id)

@app.get('/api/v2/catalogue',dependencies=[Depends(check_key)])
def catalogue(q:str='',chapter:str|None=None,limit:int=20):return {'rows':state['catalogue'].search(q,max(1,min(limit,100)),chapter),'total_catalogue':len(state['catalogue'].rows),'score_is_probability':False}
@app.get('/api/v2/catalogue/{code}',dependencies=[Depends(check_key)])
def catalogue_row(code:str):
    row=state['catalogue'].by_code.get(code)
    if not row:raise HTTPException(404,'Không có mã HS8 này trong danh mục đã nạp.')
    siblings=[x for x in state['catalogue'].rows if x['code'][:6]==code[:6]];return dict(row,siblings=siblings,notes=state['catalogue'].note_search('',scope=row['chapter'],limit=5))
@app.get('/api/v2/knowledge',dependencies=[Depends(check_key)])
def knowledge(q:str='',scope:str|None=None):return {'notes':state['catalogue'].note_search(q,scope),'legal_sources':json.loads((ROOT/'data/legal_sources.json').read_text()),'applicability_requires_review':True}

@app.get('/api/v2/precedents',dependencies=[Depends(check_key)])
def precedents(q:str=Query(default='',max_length=15000),as_of:date|None=None,heading:str|None=None,limit:int=8):
    if heading and not re.fullmatch(r'\d{4}',heading):raise HTTPException(422,'Nhóm HS phải đủ 4 chữ số.')
    day=(as_of or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()).isoformat()
    library=state['precedents']
    return {'rows':library.search(q,day,[heading]if heading else None,max(1,min(limit,12))),
            'corpus_version':library.version,'default_split':'train','all_source_records':len(library.rows),
            'current_applicability_certified':False,'retrieval_is_classification':False}

@app.get('/api/v2/legal-document/{source_id}',dependencies=[Depends(check_key)])
def legal_document(source_id:str):
    sources=json.loads((ROOT/'data/legal_sources.json').read_text())['rules']
    record=next((x for x in sources if x['id'].replace('/','_')==source_id),None)
    if not record or not record.get('packaged_official_pdf'):raise HTTPException(404,'Chưa đóng gói bản ký của nguồn này.')
    path=ROOT/'data/legal_documents'/record['local_file']
    from hs_assistant.catalogue import sha
    if sha(path)!=record['sha256']:raise HTTPException(409,'Bản PDF không còn khớp nguồn đã lưu.')
    return FileResponse(path,media_type='application/pdf',filename=record['local_file'],headers={'Cache-Control':'no-store'})

@app.post('/api/v2/catalog-audit',dependencies=[Depends(check_key)])
def catalog_audit(inp:CatalogItems):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from hs_assistant.catalogue import fold
    items=inp.items
    for i,x in enumerate(items):
        if not str(x.get('description','')).strip():raise HTTPException(422,f'Dòng {i+1} thiếu mô tả.')
    X=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=150000).fit_transform([fold(str(x['description'])) for x in items]);pairs=[];capped=False
    for start in range(0,len(items),128):
        matrix=(X[start:start+128]@X.T).toarray()
        for local,row in enumerate(matrix):
            a=start+local
            for b in ((row>=inp.threshold).nonzero()[0]):
                if b<=a or str(items[a].get('code',''))==str(items[b].get('code','')):continue
                pairs.append({'id_a':str(items[a].get('id',a+1)),'description_a':items[a]['description'],'code_a':str(items[a].get('code','')),'id_b':str(items[b].get('id',b+1)),'description_b':items[b]['description'],'code_b':str(items[b].get('code','')),'similarity':round(float(row[b]),4),'status':'review_required_not_proven_error'})
                if len(pairs)>=10000:capped=True;break
            if capped:break
        if capped:break
    invalid=[{'row':i+1,'code':str(x.get('code',''))} for i,x in enumerate(items) if str(x.get('code','')) not in state['catalogue'].by_code]
    return {'items':len(items),'pairs':sorted(pairs,key=lambda x:-x['similarity']),'invalid_or_unmapped_codes':invalid,'pair_limit_reached':capped,'automatic_code_changes':0,'similarity_proves_error':False}

@app.post('/api/v2/catalog-import',dependencies=[Depends(check_key)])
async def catalog_import(file:UploadFile=File(...)):
    content=await file.read(MAX_UPLOAD+1)
    if len(content)>MAX_UPLOAD:raise HTTPException(422,'Tệp quá lớn.')
    try:
        if (file.filename or '').lower().endswith('.csv'):df=pd.read_csv(io.BytesIO(content),dtype=str,keep_default_na=False)
        elif (file.filename or '').lower().endswith('.xlsx'):df=pd.read_excel(io.BytesIO(content),dtype=str,keep_default_na=False)
        else:raise HTTPException(422,'Chọn CSV hoặc XLSX.')
    except HTTPException:raise
    except Exception:raise HTTPException(422,'Không đọc được bảng dữ liệu. Kiểm tra định dạng CSV UTF-8 hoặc XLSX hợp lệ.')
    if len(df)<2:raise HTTPException(422,'Cần ít nhất 2 dòng để so sánh danh mục.')
    if len(df)>5000:raise HTTPException(422,'Tối đa 5.000 dòng mỗi lượt rà soát.')
    return {'columns':list(df.columns),'rows':df.fillna('').to_dict(orient='records')}

@app.post('/api/v2/estimate',dependencies=[Depends(check_key)])
def estimate_manual(inp:Estimate):
    out=[]
    for x in inp.items:
        if x.code not in state['catalogue'].by_code:raise HTTPException(422,'Mã không có trong danh mục đã nạp: '+x.code)
        duty=inp.customs_value*x.import_rate/100;vat_base=inp.customs_value+duty+x.excise_amount+x.environmental_amount;vat=vat_base*x.vat_rate/100
        out.append(dict(x.model_dump(),customs_value=inp.customs_value,import_duty=duty,vat_base=vat_base,vat=vat,total=duty+vat+x.excise_amount+x.environmental_amount))
    return {'rows':out,'assumptions':'Thuế suất và các khoản khác do người dùng nhập; không phải mức thuế hiện hành được xác minh. Chưa bao gồm mọi biện pháp hoặc tình huống pháp lý.','penalty_estimated':False,'used_to_choose_code':False}

class TaxScenarioIn(BaseModel):
    code:str=Field(pattern=r'^\d{8}$');classification_date:date
    trade_type:Literal['import','export']='import';scheme:str=Field(default='MFN',max_length=40)
    valuation_mode:Literal['entered_customs_value','components']='entered_customs_value'
    customs_value_vnd:Decimal=Field(default=0,ge=0,allow_inf_nan=False);valuation:dict=Field(default_factory=dict)
    origin_country:str=Field(default='',max_length=100);eligibility:dict=Field(default_factory=dict)
    duty_rate_percent:Decimal|None=Field(default=None,ge=0,le=2000,allow_inf_nan=False);duty_rate_source:str=Field(default='',max_length=2000)
    vat_treatment:Literal['taxable','not_subject']='taxable';vat_rate_percent:Decimal|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)
    vat_source:str=Field(default='',max_length=2000);other_taxes_source:str=Field(default='',max_length=4000)
    additional_import_duties_vnd:Decimal=Field(default=0,ge=0,allow_inf_nan=False);excise_vnd:Decimal=Field(default=0,ge=0,allow_inf_nan=False);environmental_vnd:Decimal=Field(default=0,ge=0,allow_inf_nan=False)
    reviewer:str=Field(min_length=2,max_length=100);operator_checked:bool=False
    sku_id:str|None=Field(default=None,max_length=80);expected_revision:int|None=None

class ComparisonCandidateIn(BaseModel):
    code:str=Field(pattern=r'^\d{8}$');scheme:str=Field(default='MFN',max_length=40)
    duty_rate_percent:Decimal|None=Field(default=None,ge=0,le=2000,allow_inf_nan=False)
    duty_rate_source:str=Field(default='',max_length=2000);rate_checked:bool=False
    policy_status:Literal['unknown','none_identified','requirement_identified','prohibited']='unknown'
    policy_source:str=Field(default='',max_length=2000);policy_note:str=Field(default='',max_length=4000);policy_checked:bool=False
    distinguishing_attributes:str=Field(default='',max_length=4000);eligibility:dict=Field(default_factory=dict)
class ComparisonIn(BaseModel):
    expected_revision:int;expected_analysis_id:str|None=None
    customs_value_vnd:Decimal|None=Field(default=None,gt=0,allow_inf_nan=False)
    origin_country:str=Field(default='',max_length=100);reviewer:str=Field(min_length=2,max_length=100)
    candidates:list[ComparisonCandidateIn]=Field(min_length=2,max_length=3)

@app.post('/api/v2/skus/{sku_id}/comparisons',dependencies=[Depends(check_key)])
def comparison(sku_id:str,inp:ComparisonIn):
    from hs_assistant.comparison import compare_candidates
    sku=state['db'].get_sku(sku_id);case=state['db'].get_case(sku['case_id'])
    if inp.expected_revision!=sku['revision']or inp.expected_analysis_id!=sku['analysis_id']:raise ConflictError('SKU hoặc kết quả phân tích đã đổi; mở lại trước khi so sánh.')
    data=inp.model_dump(mode='json')
    try:result=compare_candidates(data,sku,case,state['catalogue'].by_code,state['tax'])
    except (TaxError,ValueError,TypeError)as e:raise HTTPException(422,str(e))
    return state['db'].save_comparison(sku_id,inp.expected_revision,inp.expected_analysis_id,data,result)

@app.get('/api/v2/skus/{sku_id}/comparisons',dependencies=[Depends(check_key)])
def comparison_history(sku_id:str):return state['db'].comparisons(sku_id)

@app.get('/api/v2/tax/{code}',dependencies=[Depends(check_key)])
def tax_lookup(code:str,as_of:date):
    if not re.fullmatch(r'\d{8}',code):raise HTTPException(422,'Mã HS8 phải đủ 8 chữ số.')
    try:return state['tax'].lookup(code,as_of.isoformat())
    except TaxError as e:raise HTTPException(422,str(e))

@app.post('/api/v2/tax-scenarios',dependencies=[Depends(check_key)])
def tax_scenario(inp:TaxScenarioIn):
    data=inp.model_dump();data['classification_date']=inp.classification_date.isoformat();sku=None
    if inp.sku_id:
        sku=state['db'].get_sku(inp.sku_id);case=state['db'].get_case(sku['case_id'])
        if inp.expected_revision!=sku['revision']:raise HTTPException(409,'SKU đã thay đổi; mở lại trước khi tính thuế.')
        if case['trade_type']!=inp.trade_type or case['classification_date']!=data['classification_date']:raise HTTPException(409,'Ngày và luồng XNK phải khớp hồ sơ liên kết.')
    try:result=state['tax'].calculate(data)
    except (TaxError,ValueError,TypeError) as e:raise HTTPException(422,str(e))
    if sku:
        with state['db'].lock,state['db'].connect() as c:
            row=c.execute('SELECT revision FROM skus WHERE id=?',(sku['id'],)).fetchone()
            if row[0]!=inp.expected_revision:raise HTTPException(409,'SKU vừa thay đổi; tính lại kịch bản.')
            result.update(id=uid('tax_'),created_at=now(),linked_sku=sku['id'],sku_revision=sku['revision'],code_matches_approved_decision=bool(sku['decision'] and sku['decision']['code']==inp.code))
            c.execute('INSERT INTO tax_scenarios VALUES(?,?,?,?,?,?)',(result['id'],sku['id'],sku['revision'],encode(data),encode(result),result['created_at']))
            state['db'].event(c,sku['case_id'],sku['id'],'tax_scenario_created',inp.reviewer,{'id':result['id'],'code':inp.code,'sku_revision':sku['revision'],'current_rates_legally_certified':False})
    return result

@app.get('/api/v2/skus/{sku_id}/tax-scenarios',dependencies=[Depends(check_key)])
def tax_history(sku_id:str):
    sku=state['db'].get_sku(sku_id)
    with state['db'].connect() as c:rows=c.execute('SELECT result_json,sku_revision FROM tax_scenarios WHERE sku_id=? ORDER BY created_at DESC',(sku_id,)).fetchall()
    return [dict(json.loads(r['result_json']),stale=r['sku_revision']!=sku['revision'])for r in rows]

@app.get('/api/v2/project-knowledge',dependencies=[Depends(check_key)])
def project_knowledge(q:str='',limit:int=12):
    engine=state.get('project_knowledge')
    return {'enabled':engine is not None,'rows':engine.search(q,limit)if engine else [],'local_source_only':True,'legal_applicability_verified':False}

@app.get('/api/v2/quality',dependencies=[Depends(check_key)])
def quality():
    s=state['db'].summary();metrics={'label':'M0 · bộ kiểm thử lịch sử của dự án','n':109,'correct':32,'hs8_top1':32/109,'dataset':'legacy notices, labels provisional','independent_test':False,'applies_to_current_runtime':False,'source':'Báo cáo kiểm toán dữ liệu dự án 01/11/2026'}
    if state['inference'].artifact and (state['inference'].artifact/'metrics.json').exists():
        metrics['runtime_metrics_available']=True
    multi=json.loads((ROOT/'data/multilevel_experiment.json').read_text());metrics.update(multi['historical_test']);metrics['correct']=metrics['hs8_correct']
    return {'multilevel_experiment':{'models_evaluated':multi['models_evaluated'],'selected':multi['selected'],'production_ready':False},'operations':s,'historical':metrics,'production_auto_classification_ready':False,'target_hs8_top1':.8,'reason':'Chưa có cohort độc lập và calibration HS8 đủ điều kiện phát hành tự động.','approval_rate_is_accuracy':False,'model_registry':state['inference'].status()}

@app.get('/api/v2/cases/{case_id}/export/{kind}',dependencies=[Depends(check_key)])
def export_case(case_id:str,kind:Literal['json','pdf','xlsx','zip']):
    case=state['db'].get_case(case_id);case['skus']=[state['db'].get_sku(x['id']) for x in case['skus']];case['exported_at']=now();
    with state['db'].connect() as c:
        case['events']=[state['db'].public_event(dict(x)) for x in c.execute('SELECT * FROM events WHERE case_id=? ORDER BY id',(case_id,))]
        case['analysis_history']=[dict(x, result=json.loads(x['result_json'])) for x in [dict(r) for r in c.execute('SELECT a.* FROM analyses a JOIN skus s ON s.id=a.sku_id WHERE s.case_id=? ORDER BY a.created_at',(case_id,))]]
        case['decision_history']=[dict(r) for r in c.execute('SELECT d.* FROM decisions d JOIN skus s ON s.id=d.sku_id WHERE s.case_id=? ORDER BY d.created_at',(case_id,))]
    with state['db'].connect() as c:case['tax_scenarios']=[json.loads(r[0])for r in c.execute('SELECT t.result_json FROM tax_scenarios t JOIN skus s ON s.id=t.sku_id WHERE s.case_id=? ORDER BY t.created_at',(case_id,))]
    with state['db'].connect()as c:
        decision_ids=[r[0]for r in c.execute('SELECT d.id FROM decisions d JOIN skus s ON s.id=d.sku_id WHERE s.case_id=? ORDER BY d.created_at',(case_id,))]
    case['decision_snapshots']=[]
    for i in decision_ids:
        try:case['decision_snapshots'].append(state['db'].snapshot(i))
        except KeyError:case['decision_snapshots'].append({'decision_id':i,'status':'legacy_decision_without_frozen_snapshot'})
    case['comparisons']=[dict(row,sku_id=s['id'])for s in case['skus']for row in state['db'].comparisons(s['id'])]
    case['document_type']='internal_classification_dossier_not_customs_ruling';case['approved_decisions_are_training_gold']=False
    if kind=='zip':
        from hs_assistant.archival import build_case_archive
        from starlette.background import BackgroundTask
        import shutil
        if any(s.get('integrity_matches')is False for s in case['decision_snapshots']):raise ConflictError('Bản chụp quyết định không khớp SHA256; cần kiểm tra trước khi xuất.')
        archive,directory=build_case_archive(case,state['db'],ROOT)
        return FileResponse(archive,media_type='application/zip',filename=archive.name,background=BackgroundTask(shutil.rmtree,directory,ignore_errors=True))
    if kind=='json':return Response(encode(case),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{case["reference"]}.json"'})
    from hs_assistant.workspace_export import case_pdf,case_excel
    data=case_pdf(case) if kind=='pdf' else case_excel(case)
    return Response(data,media_type='application/pdf' if kind=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{case["reference"]}.{kind}"'})

@app.post('/api/v2/demo',dependencies=[Depends(check_key)])
def seed_demo():
    from hs_assistant.demo import seed
    return seed(state)

# Compatibility endpoints: explicit-text legacy calls are never SKU approval.
class ClassifyIn(BaseModel):mo_ta:str=Field(min_length=20,max_length=50000);k:int=Field(default=3,ge=1,le=10)
class DecisionIn(BaseModel):ho_so_id:str;ma_chon:str=Field(pattern=r'^\d{8}$');ly_do:str=Field(min_length=5,max_length=2000);nguoi_khai:str|None=None
@app.post('/classify',dependencies=[Depends(check_key)],deprecated=True)
def legacy_classify(inp:ClassifyIn):
    service=state['inference']
    if not service.status()['model_artifacts_available']:raise HTTPException(409,'Chưa cấu hình model. Dùng luồng SKU ở /api/v2 hoặc đặt HS_ART.')
    try:
        with service.lock:
            if service.assistant is None:
                from hs_assistant.core import HSAssistant
                service.assistant=HSAssistant(str(service.artifact),precedent_splits=('train',))
            res=service.assistant.classify(inp.mo_ta,inp.k)
        state['log'].log_classification(res);return res
    except Exception as e:raise HTTPException(409,'Không thể nạp model: '+str(e)[:300])
@app.post('/decision',dependencies=[Depends(check_key)],deprecated=True)
def legacy_decision(inp:DecisionIn):
    if inp.ma_chon not in state['catalogue'].by_code:raise HTTPException(422,'Mã không thuộc danh mục Việt Nam đã nạp.')
    r=state['log'].log_decision(inp.ho_so_id,inp.ma_chon,inp.ly_do,inp.nguoi_khai)
    if r is None:raise HTTPException(404,'Không tìm thấy phiếu.')
    return dict(r,review_type='legacy_internal_record_without_sku_evidence_gate',expert_gold=False)

class LegacyAuditIn(BaseModel):
    items:list[dict]=Field(min_length=2,max_length=5000)
    nguong:float=Field(default=.85,ge=.5,le=1.)
@app.post('/audit',dependencies=[Depends(check_key)],deprecated=True)
def legacy_audit(inp:LegacyAuditIn):
    r=catalog_audit(CatalogItems(items=[{'id':x.get('id',str(i+1)),'description':x.get('mo_ta',''),'code':x.get('ma_hs','')}for i,x in enumerate(inp.items)],threshold=inp.nguong))
    return {'so_cap_lech':len(r['pairs']),'cap_lech':[{'id_A':x['id_a'],'id_B':x['id_b'],'ma_A':x['code_a'],'ma_B':x['code_b'],'tuong_dong':x['similarity'],'can_kiem_tra':True}for x in r['pairs']],'similarity_proves_error':False}
@app.post('/estimate',dependencies=[Depends(check_key)],deprecated=True)
def legacy_estimate():
    raise HTTPException(410,'Cách ước tính thuế/phạt tự động cũ đã dừng vì nguồn thuế chưa đủ kiểm chứng. Dùng /api/v2/estimate với thuế suất do người dùng đối chiếu nhập vào.')

web=ROOT/'web_dist'
if web.exists():app.mount('/assets',StaticFiles(directory=web/'assets'),name='assets')
@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith(('api/','assets/')):raise HTTPException(404,'Không tìm thấy tài nguyên.')
    if not (web/'index.html').exists():return Response('Frontend chưa build. Chạy npm install && npm run build.',status_code=503)
    return FileResponse(web/'index.html',headers={'Cache-Control':'no-cache'})
