"""Workflow regression tests; synthetic rates and labels are not legal evidence."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
from test_workspace import client, dossier, ready, evidence, analyze, approve, verify


def compare_body(s, **extra):
    d = {'expected_revision': s['revision'], 'expected_analysis_id': s['analysis_id'],
         'customs_value_vnd': '100000000.01', 'reviewer': 'Người kiểm thử',
         'candidates': [{'code': '85163100'}, {'code': '85163200'}]}
    d.update(extra); return d


def test_unknown_policies_and_missing_rates_stay_unknown(client):
    case,s=dossier(client);s=ready(client,s);s=analyze(client,s)
    r=client.post('/api/v2/skus/'+s['id']+'/comparisons',json=compare_body(s))
    assert r.status_code==200,r.text
    d=r.json();assert all(x['duty_vnd'] is None and x['policy_status']=='unknown'for x in d['rows'])
    assert d['pairs'][0]['policy_differs'] is None and d['audit_probability'] is None
    assert d['recommended_hs_code'] is None and not d['tax_cost_used_to_rank_codes']
    assert 'total_taxes_vnd' not in d['rows'][0]


def test_compared_duty_is_decimal_and_input_order_not_cheapest(client):
    case,s=dossier(client);s=ready(client,s);s=analyze(client,s);body=compare_body(s)
    for row,rate in zip(body['candidates'],['20','10']):
        row.update(duty_rate_percent=rate,rate_checked=True,duty_rate_source='Synthetic arithmetic fixture, not a legal rate')
    r=client.post('/api/v2/skus/'+s['id']+'/comparisons',json=body);assert r.status_code==200,r.text
    d=r.json();assert [x['code']for x in d['rows']]==['85163100','85163200']
    assert d['pairs'][0]['duty_difference_b_minus_a_vnd']=='-10000000.00'
    history=client.get('/api/v2/skus/'+s['id']+'/comparisons').json();assert len(history)==1 and not history[0]['stale']
    client.post('/api/v2/skus/'+s['id']+'/analyze',json={'engine':'catalogue'})
    assert client.get('/api/v2/skus/'+s['id']+'/comparisons').json()[0]['stale']
    assert client.post('/api/v2/skus/'+s['id']+'/comparisons',json=body).status_code==409


@pytest.mark.parametrize('change',[
    {'duty_rate_percent':'0'},
    {'duty_rate_percent':'5','rate_checked':True},
    {'policy_status':'none_identified'},
    {'policy_status':'prohibited','policy_checked':True,'policy_source':'source'},
    {'scheme':'ATIGA','duty_rate_percent':'0','rate_checked':True,'duty_rate_source':'Synthetic'},
])
def test_unchecked_legal_assertions_cannot_be_laundered(client,change):
    case,s=dossier(client);s=ready(client,s);s=analyze(client,s);body=compare_body(s);body['candidates'][0].update(change)
    assert client.post('/api/v2/skus/'+s['id']+'/comparisons',json=body).status_code==422


def test_fta_requires_all_conditions_and_origin(client):
    case,s=dossier(client);s=ready(client,s);s=analyze(client,s);body=compare_body(s)
    body['origin_country']='TH'
    body['candidates'][0].update(scheme='ATIGA',duty_rate_percent='0',duty_rate_source='Synthetic',rate_checked=True,
                               eligibility={'co_status':'verified','origin_rule_checked':True,'transport_rule_checked':True,'schedule_checked':True})
    r=client.post('/api/v2/skus/'+s['id']+'/comparisons',json=body);assert r.status_code==200,r.text
    assert r.json()['rows'][0]['fta_eligibility']=='operator_checked'
    body['candidates'][0]['eligibility']['transport_rule_checked']=False
    assert client.post('/api/v2/skus/'+s['id']+'/comparisons',json=body).status_code==422


def test_approval_requires_independent_alternative_and_code_scoped_source(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s,target_codes=['0101']);s=analyze(client,s)
    assert approve(client,s).status_code==422
    s=evidence(client,s);s=analyze(client,s)
    assert approve(client,s,classification_basis_confirmed=False).status_code==422
    assert approve(client,s,alternative_code='85163100').status_code==422
    assert approve(client,s,alternative_reason='Loại vì AI').status_code==422
    assert approve(client,s).status_code==200


def test_unselected_conflict_blocks_until_resolution_logged(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=evidence(client,s,role='conflict');s=analyze(client,s)
    good=[e['id']for e in s['evidence']if e['role']=='supports']
    assert approve(client,s,evidence_ids=good).status_code==422
    conflict=next(e for e in s['evidence']if e['role']=='conflict')
    r=client.patch('/api/v2/skus/'+s['id']+'/evidence/'+conflict['id'],json={'role':'not_applicable','lifecycle':'active','reviewer':'Người đối chiếu','resolution_note':'Nguồn nói về sản phẩm khác về cơ chế, đã kiểm tra nguyên bản.','target_codes':[]})
    assert r.status_code==200,r.text;s=analyze(client,r.json())
    assert approve(client,s,evidence_ids=good).status_code==200
    assert any(e['action']=='evidence_reviewed'for e in client.get('/api/v2/cases/'+case['id']).json()['events'])


def test_source_less_fact_cannot_be_promoted_later(client):
    case,s=dossier(client)
    r=client.post('/api/v2/skus/'+s['id']+'/facts',json={'field':'name','value':'Máy sấy tóc','quote':'Tự ghi, không có nguồn hoặc xác nhận trực tiếp.','status':'unverified'})
    assert r.status_code==200;f=r.json()['facts'][0]
    r=client.patch('/api/v2/skus/'+s['id']+'/facts/'+f['id'],json={'status':'verified','reviewer':'Người kiểm tra'})
    assert r.status_code==422


def test_frozen_decision_survives_fact_changes_and_detects_tampering(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s);r=approve(client,s);assert r.status_code==200,r.text
    sid=r.json()['decision']['id'];snap=client.get('/api/v2/decisions/'+sid+'/snapshot').json()
    assert snap['integrity_matches'] and not snap['snapshot']['identity_verified']
    assert snap['snapshot']['decision']['alternative_reason'] and snap['snapshot']['source_context']['files']
    old=snap['snapshot_sha256'];s=verify(client,r.json(),'condition','Hàng mới, đóng hộp')
    assert s['decision'] is None
    assert client.get('/api/v2/decisions/'+sid+'/snapshot').json()['snapshot_sha256']==old
    import api
    with api.state['db'].connect()as db:db.execute("UPDATE decision_snapshots SET snapshot_json='{}' WHERE decision_id=?",(sid,))
    assert not client.get('/api/v2/decisions/'+sid+'/snapshot').json()['integrity_matches']
    assert client.get('/api/v2/cases/'+case['id']+'/export/zip').status_code==409


def test_retention_uses_declaration_date_and_trade_change_invalidates(client):
    case,s=dossier(client);s=ready(client,s);s=evidence(client,s);s=analyze(client,s);s=approve(client,s).json()
    p={'title':case['title'],'owner':case['owner'],'classification_date':case['classification_date'],
       'declaration_number':'TEST-001','declaration_registered_date':'2024-02-29','legal_hold':True}
    r=client.patch('/api/v2/cases/'+case['id'],json=p);assert r.status_code==200,r.text
    assert r.json()['retention']['minimum_reference_until']=='2029-03-01'
    assert r.json()['retention']['status']=='legal_hold'
    assert client.get('/api/v2/skus/'+s['id']).json()['decision'] is None
    s=analyze(client,client.get('/api/v2/skus/'+s['id']).json());s=approve(client,s).json()
    p.update(trade_type='export');client.patch('/api/v2/cases/'+case['id'],json=p)
    assert client.get('/api/v2/skus/'+s['id']).json()['analysis'] is None


def test_archive_contains_original_bytes_and_hash_manifest(client):
    case,s=dossier(client);content='Nguồn kỹ thuật mẫu để kiểm thử bảo toàn tệp.'.encode()
    r=client.post('/api/v2/cases/'+case['id']+'/documents',files={'files':('technical.txt',content,'text/plain')});assert r.status_code==200
    import api
    api.state['documents'].close()
    r=client.get('/api/v2/cases/'+case['id']+'/export/zip');assert r.status_code==200,r.text[:100]
    with zipfile.ZipFile(io.BytesIO(r.content))as z:
        m=json.loads(z.read('MANIFEST.json'));assert not m['digital_signature']
        for name,h in m['file_hashes'].items():assert hashlib.sha256(z.read(name)).hexdigest()==h
        documents=[n for n in z.namelist()if n.startswith('documents/')];assert len(documents)==1 and z.read(documents[0])==content
        assert json.loads(z.read('dossier.json'))['retention']['status']=='declaration_date_required'
    with api.state['db'].connect()as db:path=Path(db.execute('SELECT path FROM documents').fetchone()[0])
    path.write_bytes(b'changed')
    assert client.get('/api/v2/cases/'+case['id']+'/export/zip').status_code==422


def test_registry_dates_and_event_integrity(client):
    d=client.get('/api/v2/legal-status?as_of=2026-11-02').json();status={x['id']:x['status_on_date']for x in d['sources']}
    assert status['11/2026/QH16']=='not_yet_effective' and status['128/2020/ND-CP']=='no_longer_effective'
    assert status['169/2026/ND-CP']=='in_recorded_effective_period' and not d['covers_all_amendments']
    dossier(client);assert client.get('/api/v2/audit-integrity').json()['integrity_matches']
    import api
    with api.state['db'].connect()as db:db.execute("UPDATE events SET actor='changed' WHERE id=1")
    assert not client.get('/api/v2/audit-integrity').json()['integrity_matches']


def test_precedent_retrieval_filters_future_and_evaluation_examples(client):
    r=client.get('/api/v2/precedents',params={'q':'thép không gỉ','as_of':'2026-11-02'});assert r.status_code==200,r.text
    d=r.json();assert d['rows'] and not d['retrieval_is_classification']
    assert all(x['split']=='train'and x['notice_date']<='2026-11-02'and not x['legal_applicability_verified']for x in d['rows'])
    assert any(x['more_than_three_years_old']for x in d['rows'])
    assert client.get('/api/v2/precedents',params={'q':'thép','as_of':'2000-01-01'}).json()['rows']==[]


def test_chapter98_preserves_variants_and_never_uses_reference_as_unit(client):
    import api
    engine=api.state['tax'];assert all(not c.startswith('98')for c in engine.rows)
    code=next(c for c,r in engine.special.items()if len(r)>1)
    d=engine.lookup(code,'2026-11-02');assert d['rates']=={} and len(d['variants'])>1
    assert all(r['unit']is None and 'reference_code_observation'in r for r in d['variants'])
    r=client.post('/api/v2/tax-scenarios',json={'code':code,'classification_date':'2026-11-02','reviewer':'Người kiểm thử','operator_checked':True,'customs_value_vnd':'100000000','duty_rate_percent':'0','duty_rate_source':'Synthetic','vat_rate_percent':'10','vat_source':'Synthetic'})
    assert r.status_code==422


def test_new_private_endpoints_require_key(client,monkeypatch):
    import api
    monkeypatch.setattr(api,'API_KEY','test-support-key')
    for path in ['/api/v2/precedents?q=test','/api/v2/legal-status?as_of=2026-11-02','/api/v2/audit-integrity','/api/v2/skus/x/comparisons','/api/v2/decisions/x/snapshot']:
        assert client.get(path).status_code==401


def test_additive_migration_preserves_existing_case_and_facts(tmp_path):
    from hs_assistant.workspace import Workspace
    path=tmp_path/'workspace.sqlite';db=Workspace(path);case=db.create_case('Hồ sơ từ bản cũ','Người lập')
    with db.connect()as c:
        for column in ['declaration_number','declaration_registered_date','legal_hold']:c.execute('ALTER TABLE cases DROP COLUMN '+column)
        for column in ['target_codes_json','resolution_note']:c.execute('ALTER TABLE evidence DROP COLUMN '+column)
        c.execute('DROP TABLE comparisons');c.execute('DROP TABLE decision_snapshots')
    migrated=Workspace(path);same=migrated.get_case(case['id'])
    assert same['reference']==case['reference'] and same['retention']['status']=='declaration_date_required'
    assert not same['legal_hold']


def test_analysis_groups_are_distinct_and_incomplete_facts_abstain(client):
    case,s=dossier(client,'steel');s=ready(client,s);s=analyze(client,s);a=s['analysis']
    assert a['decision_support_state']=='needs_information'
    heads=[r['heading']for r in a['heading_candidates']]
    assert 0<len(heads)<=3 and len(heads)==len(set(heads))
    assert not a['candidate_ranking_is_legal_conclusion'] and not a['auto_accept']
