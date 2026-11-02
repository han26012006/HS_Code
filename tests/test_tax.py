from pathlib import Path
from decimal import Decimal
import io,pytest
from hs_assistant.tax import TaxEngine,TaxError,parse_rate,customs_value
ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(scope='module')
def engine():return TaxEngine(ROOT/'data/tax')
def payload(**extra):
 d=dict(code='85163100',classification_date='2026-11-01',trade_type='import',scheme='MFN',customs_value_vnd='100000000',duty_rate_percent='10',duty_rate_source='Synthetic test; not legal rate',vat_rate_percent='8',vat_source='Synthetic VAT test',additional_import_duties_vnd='3000000',excise_vnd='2000000',environmental_vnd='1000000',other_taxes_source='Synthetic additional tax arithmetic test',operator_checked=True,reviewer='Người kiểm thử');d.update(extra);return d

def test_decimal_and_vat_base(engine):
 r=engine.calculate(payload());assert Decimal(r['vat_base_vnd'])==116000000 and Decimal(r['vat_vnd'])==9280000 and Decimal(r['total_taxes_vnd'])==25280000
 assert r['current_rates_legally_certified']is False and r['used_to_choose_hs']is False

def test_context_dependent_star_and_ambiguous_rate():
 assert parse_rate('*')['kind']=='marker_requires_interpretation'and parse_rate('*/8/10')['kind']=='ambiguous'
 assert parse_rate('0')['kind']=='ad_valorem'and parse_rate('')['kind']=='missing'

def test_fta_and_rcep_need_checked_conditions(engine):
 with pytest.raises(TaxError):engine.calculate(payload(scheme='ATIGA'))
 e=dict(origin_country='TH',eligibility=dict(co_status='verified',origin_rule_checked=True,transport_rule_checked=True,schedule_checked=True))
 assert engine.calculate(payload(scheme='ATIGA',**e))['scheme']=='ATIGA'
 with pytest.raises(TaxError):engine.calculate(payload(scheme='RCEP',duty_rate_percent=None,**e))

def test_no_double_counting_freight_insurance():
 v=dict(invoice_amount='1000',freight='100',insurance='20',exchange_rate='25000',exchange_rate_source='SyntheticFX',reviewer='Người kiểm tra',customs_valuation_checked=True)
 a,_=customs_value(dict(valuation_mode='components',valuation=dict(v,freight_in_invoice=True,insurance_in_invoice=True)));b,_=customs_value(dict(valuation_mode='components',valuation=v));assert a==25000000 and b==28000000

def test_not_subject_and_export(engine):
 r=engine.calculate(payload(vat_treatment='not_subject',vat_rate_percent=None));assert Decimal(r['vat_vnd'])==0 and r['vat_treatment']=='not_subject'
 with pytest.raises(TaxError):engine.calculate(payload(trade_type='export'))
 r=engine.calculate(payload(trade_type='export',scheme='EXPORT',additional_import_duties_vnd=0,excise_vnd=0,environmental_vnd=0));assert r['vat_vnd']is None

def test_missing_sources_review_and_nan_block(engine):
 for change in [dict(operator_checked=False),dict(customs_value_vnd='NaN'),dict(vat_source=''),dict(other_taxes_source='')]:
  with pytest.raises(TaxError):engine.calculate(payload(**change))

def test_tax_api_revision_auth_exports_and_precision(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from openpyxl import load_workbook
 from pypdf import PdfReader
 import api
 monkeypatch.setenv('HS_WORKSPACE',str(tmp_path/'work'));monkeypatch.setenv('HS_ART',str(tmp_path/'missing'));monkeypatch.setattr(api,'API_KEY','tax-test')
 with TestClient(api.app)as c:
  assert c.get('/api/v2/tax/85163100?as_of=2026-11-01').status_code==401
  c.headers['X-API-Key']='tax-test';assert c.get('/api/v2/tax/85163100?as_of=bad-date').status_code==422
  assert c.get('/api/v2/tax/85163100?as_of=2026-11-01').status_code==200
  case=c.post('/api/v2/cases',json=dict(title='Hồ sơ thử thuế',owner='Người lập',classification_date='2026-11-01')).json();s=c.post('/api/v2/cases/'+case['id']+'/skus',json=dict(sku_code='A1',name='Máy sấy tóc')).json();body=payload(sku_id=s['id'],expected_revision=s['revision'])
  r=c.post('/api/v2/tax-scenarios',json=body);assert r.status_code==200,r.text;assert not r.json()['code_matches_approved_decision'];assert len(c.get('/api/v2/skus/'+s['id']+'/tax-scenarios').json())==1
  root='/api/v2/cases/'+case['id']+'/export/'
  assert len(c.get(root+'json').json()['tax_scenarios'])==1
  b=c.get(root+'xlsx');assert b.status_code==200,b.text[:100];w=load_workbook(io.BytesIO(b.content));assert w['Kich ban thue'].max_row==2;w.close()
  b=c.get(root+'pdf');assert b.status_code==200;assert'85163100'in''.join(p.extract_text()for p in PdfReader(io.BytesIO(b.content)).pages)
  body['expected_revision']=0;assert c.post('/api/v2/tax-scenarios',json=body).status_code==409
  body.update(sku_id=None,expected_revision=None,customs_value_vnd='1000000000000000.01');r=c.post('/api/v2/tax-scenarios',json=body);assert r.status_code==200,r.text;assert r.json()['customs_value_vnd']=='1000000000000000.01'
  q=c.get('/api/v2/quality').json();assert q['historical']['hs6_top1']<.5 and q['multilevel_experiment']['models_evaluated']==16
