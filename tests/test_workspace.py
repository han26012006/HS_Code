import io,json,zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('HS_WORKSPACE',str(tmp_path/'runtime'))
    monkeypatch.setenv('HS_ART',str(tmp_path/'no_model'))
    monkeypatch.delenv('HS_ENABLE_OPENAI',raising=False);monkeypatch.delenv('HS_ENABLE_QWEN',raising=False)
    import api
    monkeypatch.setattr(api,'API_KEY',None)
    with TestClient(api.app) as c:yield c

def dossier(c,family='general'):
    r=c.post('/api/v2/cases',json={'title':'Kiểm thử hồ sơ hàng','owner':'Người lập','classification_date':'2026-11-01'});assert r.status_code==200,r.text
    case=r.json();r=c.post('/api/v2/cases/'+case['id']+'/skus',json={'sku_code':'SKU-001','name':'Sản phẩm kỹ thuật','product_family':family});assert r.status_code==200,r.text
    return case,r.json()

def verify(c,sku,field,value):
    r=c.post('/api/v2/skus/'+sku['id']+'/facts',json={'field':field,'value':value,'source_kind':'manual_declaration','quote':'Biên bản xác nhận kỹ thuật với nhà sản xuất, đã kiểm tra thông số.','status':'verified','reviewer':'Người kiểm tra'});assert r.status_code==200,r.text
    return r.json()

def ready(c,sku):
    sku=verify(c,sku,'name','Máy sấy tóc cầm tay gia dụng, dùng điện')
    return verify(c,sku,'function','Sấy khô tóc bằng luồng không khí nóng, gia nhiệt điện trở')

def evidence(c,sku,**overrides):
    payload=dict(kind='tariff',title='Nguồn kiểm thử của chuyên gia',quote='Điều kiện dòng danh mục do người duyệt đối chiếu trong kiểm thử.',source_url='https://vanban.chinhphu.vn/',role='supports',jurisdiction='VN',nomenclature='AHTN2022',effective_from='2022-12-01',effective_to=None,lifecycle='active',reviewer='Người kiểm tra')
    payload.update(overrides);r=c.post('/api/v2/skus/'+sku['id']+'/evidence',json=payload);assert r.status_code==200,r.text
    return r.json()

def analyze(c,sku):
    r=c.post('/api/v2/skus/'+sku['id']+'/analyze',json={'engine':'catalogue'});assert r.status_code==200,r.text
    return r.json()

def approve(c,sku,**extra):
    payload={'code':'85163100','reason':'Đã đối chiếu bản chất, chức năng thiết kế và dòng danh mục áp dụng cho đúng SKU.','preparer':'Người lập','reviewer':'Người duyệt','expected_revision':sku['revision'],'evidence_ids':[e['id']for e in sku['evidence']]};payload.update(extra)
    return c.post('/api/v2/skus/'+sku['id']+'/review',json=payload)

def test_start_without_weights_and_no_silent_model_fallback(client):
    assert client.get('/health').json()['automatic_hs8_acceptance_enabled'] is False
    case,s=dossier(client);assert client.post('/api/v2/skus/'+s['id']+'/analyze',json={'engine':'catalogue'}).status_code==409
    s=ready(client,s)
    assert client.post('/api/v2/skus/'+s['id']+'/analyze',json={'engine':'model'}).status_code==409
    for e in ['openai','qwen']:
        assert client.post('/api/v2/skus/'+s['id']+'/analyze',json={'engine':e}).status_code==409
    s=analyze(client,s);assert s['analysis']['auto_accept'] is False
    assert s['analysis']['calibrated_hs8_confidence'] is None
    assert all(x['score_is_probability'] is False for x in s['analysis']['candidates'])
    assert s['analysis']['candidates']

def test_approval_then_fact_change_requires_new_review(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s)
    r=approve(client,s);assert r.status_code==200,r.text;assert r.json()['status']=='approved'
    oldrev=s['revision'];s=verify(client,s,'packaging','Đóng hộp riêng từng chiếc')
    assert s['decision'] is None and s['analysis'] is None
    assert approve(client,s,expected_revision=oldrev).status_code==409
    assert approve(client,s).status_code==422
    import api
    with api.state['db'].connect() as db:
        assert db.execute('SELECT superseded_at FROM decisions').fetchone()[0]

@pytest.mark.parametrize('change',[{'jurisdiction':'US'},{'nomenclature':'HTSUS2026'},{'lifecycle':'withdrawn'},{'lifecycle':'superseded'},{'effective_from':'2027-01-01'},{'effective_to':'2026-01-01','effective_from':'2022-01-01'},{'effective_from':None},{'source_url':''},{'role':'reference'},{'role':'excludes'}])
def test_unusable_legal_evidence_blocks_approval(client,change):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s,**change);s=analyze(client,s)
    assert approve(client,s).status_code==422

def test_review_identity_conflicts_and_required_fields(client):
    case,s=dossier(client,'steel');s=ready(client,s);s=evidence(client,s);s=analyze(client,s)
    assert approve(client,s).status_code==422
    s=verify(client,s,'material','Thép không gỉ 310S');s=verify(client,s,'specifications','Chiều dày 2,95 mm; chiều rộng 1552 mm');s=analyze(client,s)
    assert approve(client,s,reviewer='Người lập').status_code==422
    f=next(x for x in s['facts'] if x['field']=='material');r=client.patch('/api/v2/skus/'+s['id']+'/facts/'+f['id'],json={'status':'conflict','reviewer':'Người kiểm tra'});s=analyze(client,r.json())
    assert approve(client,s).status_code==422

def test_rerun_and_return_supersede_decision(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s);s=approve(client,s).json();s=analyze(client,s)
    assert s['decision'] is None
    s=approve(client,s).json();r=approve(client,s,action='return',reason='Cần bổ sung hồ sơ nguyên lý sản xuất.')
    assert r.status_code==200 and r.json()['decision'] is None and r.json()['status']=='returned'

def test_date_revision_and_concurrent_analysis_guard(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s);s=approve(client,s).json()
    client.patch('/api/v2/cases/'+case['id'],json={'title':case['title'],'owner':case['owner'],'classification_date':'2026-10-01'})
    n=client.get('/api/v2/skus/'+s['id']).json();assert n['analysis'] is None and n['decision'] is None
    import api
    with pytest.raises(ValueError,match='đổi'):
        api.state['db'].save_analysis(s['id'],dict(s['analysis'],base_revision=s['revision']))

def test_codes_are_not_verified_facts_or_gold(client):
    case,s=dossier(client);r=client.post('/api/v2/skus/'+s['id']+'/facts',json={'field':'name','value':'Máy sấy tóc, mã HS 85163100','source_kind':'manual_declaration','quote':'Nhà sản xuất xác nhận.'});assert r.status_code==422
    other=client.post('/api/v2/cases/'+case['id']+'/skus',json={'sku_code':'B','name':'Mặt hàng thứ hai','declared_code':'01012100'}).json()
    assert not other['facts'] and not other['decision'] and other['analysis'] is None
    assert client.get('/api/v2/summary').json()['user_corrections_are_gold'] is False


def test_archive_paths_dedup_and_page_quote_cross_case(client):
    case,s=dossier(client);bad=io.BytesIO()
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../evil.txt','Không được ghi ra ngoài.')
    assert client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('bad.zip',bad.getvalue())}).status_code==422
    zbuf=io.BytesIO()
    with zipfile.ZipFile(zbuf,'w') as z:z.writestr('catalogue/technical.txt','Công dụng kỹ thuật: sấy khô tóc bằng điện trở.');z.writestr('ignore.exe','x')
    r=client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('docs.zip',zbuf.getvalue())}).json();assert r['added']==1 and len(r['skipped'])==1
    d=r['documents'][0];import api
    api.state['documents'].close();pages=api.state['documents'].pages(d['id']);assert len(pages)==1
    assert 'path' not in client.get('/api/v2/documents/'+d['id']).json()
    r=client.post('/api/v2/skus/'+s['id']+'/facts',json={'field':'function','value':'Sấy khô tóc','source_kind':'document','document_id':d['id'],'page_number':1,'quote':'Công dụng kỹ thuật','status':'verified','reviewer':'Người kiểm tra'});assert r.status_code==200
    other,osku=dossier(client)
    r=client.post('/api/v2/skus/'+osku['id']+'/facts',json={'field':'function','value':'Sấy khô tóc','document_id':d['id'],'page_number':1,'quote':'Công dụng kỹ thuật'});assert r.status_code==422


def test_auth_all_private_data_and_files(client,monkeypatch):
    import api
    monkeypatch.setattr(api,'API_KEY','local-test-key')
    for p in ['/api/v2/status','/api/v2/cases','/api/v2/catalogue','/api/v2/documents/example/file','/api/v2/knowledge','/api/v2/quality']:
        assert client.get(p).status_code==401
    assert client.get('/health').status_code==200
    assert client.get('/api/v2/cases',headers={'X-API-Key':'local-test-key'}).status_code==200


def test_catalogue_leading_zero_batch_and_literal_exports(client,tmp_path):
    assert client.get('/api/v2/catalogue?q=01012100').json()['rows'][0]['code']=='01012100'
    r=client.post('/api/v2/catalog-import',files={'file':('items.csv','sku,description,code\nA,Ngựa giống thuần chủng,01012100\nB,Ngựa giống thuần chủng,01012900'.encode())});assert r.status_code==200
    data=r.json();assert data['rows'][0]['code']=='01012100'
    rr=client.post('/api/v2/catalog-audit',json={'items':[{'id':'A','description':'máy sấy tóc','code':'85163100'},{'id':'B','description':'máy sấy tóc','code':'00000000'}]});assert rr.status_code==200
    assert len(rr.json()['pairs'])==1 and len(rr.json()['invalid_or_unmapped_codes'])==1 and rr.json()['automatic_code_changes']==0
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s)
    r=client.get('/api/v2/cases/'+case['id']+'/export/xlsx');assert r.status_code==200,r.text
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(r.content));assert wb['SKU']['B2'].value=='SKU-001';assert wb['Ung vien HS']['F2'].data_type=='s'
    assert len(wb.sheetnames)>=7 and wb['Thuoc tinh'].freeze_panes=='A2'
    r=client.get('/api/v2/cases/'+case['id']+'/export/pdf');assert r.status_code==200,r.text
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(r.content));assert len(pdf.pages)>0 and 'SKU-001' in ''.join(p.extract_text() for p in pdf.pages)
    r=client.get('/api/v2/cases/'+case['id']+'/export/json');assert r.json()['approved_decisions_are_training_gold'] is False


def test_export_formula_injection_literal_cells(client):
    case,s=dossier(client)
    s=verify(client,s,'name','=HYPERLINK("https://example.com","x")')
    r=client.get('/api/v2/cases/'+case['id']+'/export/xlsx')
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(r.content),data_only=False);assert wb['Thuoc tinh']['D2'].data_type=='s'
    assert wb['Thuoc tinh']['D2'].value.startswith('=HYPERLINK')


def test_every_pdf_page_is_retained(client,tmp_path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf=io.BytesIO();p=canvas.Canvas(buf,pagesize=A4)
    for i in range(7):
        for j in range(8):p.drawString(40,760-j*25,f'PAGE {i+1} - Technical specification. This page contains product details and dimensions for review.')
        p.showPage()
    p.save();case,s=dossier(client)
    r=client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('seven.pdf',buf.getvalue(),'application/pdf')});assert r.status_code==200
    import api
    api.state['documents'].close();d=client.get('/api/v2/documents/'+r.json()['documents'][0]['id']).json()
    assert d['total_pages']==7 and len(d['pages'])==7 and 'PAGE 7' in d['pages'][6]['text']
    assert all(x['review_required']==1 for x in d['pages'])


def test_instruction_validator_rejects_fabricated_citation():
    from hs_assistant.instruction_protocol import validate_response
    tariff={'85163100':{'path':'Máy sấy tóc'}};q={'query':'Máy sấy tóc dùng điện','codes':['85163100']}
    payload={'status':'suggestion','hs8':'85163100','alternatives':[],'goods_quote':'Máy sấy tóc','tariff_quote':'Máy sấy tóc','missing_attributes':[]}
    assert validate_response(json.dumps(payload),q,tariff)['accepted']
    payload['tariff_quote']='Căn cứ không có trong danh mục';assert not validate_response(json.dumps(payload),q,tariff)['accepted']
    payload['status']='needs_information';payload['hs8']=None;payload['missing_attributes']=['Thành phần vật liệu?'];assert validate_response(json.dumps(payload),q,tariff)['status']=='needs_information'


def test_paid_branch_requires_consent_and_reuses_cached_response(client,monkeypatch):
    import hs_assistant.instruction_adapter as adapter
    monkeypatch.setenv('HS_ENABLE_OPENAI','1');monkeypatch.setenv('OPENAI_API_KEY','dummy-not-a-real-secret')
    class FakeRunner:
        calls=0
        def __init__(self,*args):pass
        def preflight(self,*args):return 2000
        def call(self,row,tariff):
            type(self).calls+=1;code=row['codes'][0]
            return json.dumps({'status':'suggestion','hs8':code,'alternatives':[],'goods_quote':row['query'][:40],'tariff_quote':tariff[code]['path'][:40],'missing_attributes':[]}),{'paid_api_calls':1,'actual_usd':0.01}
    monkeypatch.setattr(adapter,'OpenAIRunner',FakeRunner)
    case,s=dossier(client);s=ready(client,s)
    url='/api/v2/skus/'+s['id']+'/analyze'
    assert client.post(url,json={'engine':'openai'}).status_code==409 and FakeRunner.calls==0
    for i in range(2):
        r=client.post(url,json={'engine':'openai','allow_paid_api':True});assert r.status_code==200,r.text
    assert FakeRunner.calls==1 and r.json()['analysis']['instruction_result']['reused_cached_response']
    assert r.json()['analysis']['auto_accept'] is False


def test_actual_image_ocr_still_requires_human_review(client,tmp_path):
    import shutil
    if not shutil.which('tesseract'):pytest.skip('OCR engine not installed')
    from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype(str(Path(__file__).parents[1]/'hs_assistant/fonts/DejaVuSans.ttf'),34)
    img=Image.new('RGB',(1500,600),'white');draw=ImageDraw.Draw(img)
    for i,t in enumerate(['TECHNICAL SPECIFICATION','Cold rolled stainless steel sheet','Thickness 2.95 mm','Width 1552 mm','Alloy grade 310S']):draw.text((70,60+i*85),t,fill='black',font=font)
    b=io.BytesIO();img.save(b,format='PNG');case,s=dossier(client)
    r=client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('scan.png',b.getvalue(),'image/png')});assert r.status_code==200
    import api
    api.state['documents'].close();doc=client.get('/api/v2/documents/'+r.json()['documents'][0]['id']).json()
    assert doc['status']=='needs_review',doc.get('error')
    assert '2.95' in doc['pages'][0]['text'] and '1552' in doc['pages'][0]['text']
    assert doc['pages'][0]['review_required']==1


def test_packaged_official_pdf_hash_and_access_gate(client,monkeypatch):
    import api,hashlib
    source=client.get('/api/v2/knowledge').json()['legal_sources']['rules'][0]
    r=client.get('/api/v2/legal-document/'+source['id'].replace('/','_'))
    assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==source['sha256']
    monkeypatch.setattr(api,'API_KEY','test-gate')
    assert client.get('/api/v2/legal-document/'+source['id'].replace('/','_')).status_code==401


def test_ocr_retry_invalidates_dependent_facts_and_analysis(client):
    import time
    case,s=dossier(client);s=ready(client,s)
    r=client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('technical.txt','Công dụng: sấy khô tóc bằng điện trở.'.encode(),'text/plain')});doc=r.json()['documents'][0]
    for _ in range(100):
        d=client.get('/api/v2/documents/'+doc['id']).json()
        if d['status'] not in ['queued','processing']:break
        time.sleep(.01)
    r=client.post('/api/v2/skus/'+s['id']+'/facts',json={'field':'function','value':'Sấy khô tóc bằng điện trở','document_id':doc['id'],'page_number':1,'quote':'Công dụng: sấy khô tóc bằng điện trở.','status':'verified','reviewer':'Người kiểm tra'});assert r.status_code==200
    s=analyze(client,r.json());r=client.post('/api/v2/documents/'+doc['id']+'/retry');assert r.status_code==200,r.text
    s=client.get('/api/v2/skus/'+s['id']).json()
    assert s['analysis'] is None and all(f['status']=='unverified'for f in s['facts']if f['document_id']==doc['id'])
