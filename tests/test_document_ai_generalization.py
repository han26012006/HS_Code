import io
import json
import shutil
from pathlib import Path
import pytest
from hs_assistant.extractor import AutoFillDraftManager,DocumentTypeDetector,InformationExtractor,parse_file_bytes
from hs_assistant.workspace import Workspace
from hs_assistant.documents import DocumentService
from hs_assistant.document_layout import build_layout,ensure_layout
from hs_assistant.assisted_extraction import AssistedExtraction,AssistancePolicy

ROOT=Path(__file__).resolve().parents[1]


def mgr(tmp_path):return AutoFillDraftManager(Workspace(tmp_path/'workspace.db'))


def test_development_documents_classification_and_schema(tmp_path):
    cases=json.loads((ROOT/'tests/fixtures/document_ai/development.json').read_text())
    manager=mgr(tmp_path)
    for case in cases:
        docs=[{k:v for k,v in d.items() if not k.startswith('expected_')} for d in case['documents']]
        draft=manager.create_draft([],docs)
        assert [d['kind'] for d in draft['documents']]==[d['expected_kind'] for d in case['documents']],case['id']
        assert sorted(s['sku_code'] for s in draft['skus'])==sorted(p['identifier'] for p in case['products']),case['id']
        for sku in draft['skus']:
            for f in sku['facts']:
                doc=next(d for d in docs if d['id']==f['document_id']);page=next(p for p in doc['pages'] if p['number']==f['page_number'])
                assert f['quote'] in page['text']
                assert f['source_document_type']!='legal_reference'
                assert f['status']!='verified'


def test_wrapped_tables_and_header_relationships():
    text='COMMERCIAL INVOICE\nSKU | Description | Qty | Unit\nUNIT-9 | Electric | 12 | PCS\n       | actuator |    |    \n\nTechnical note: verify before use\n'
    layout=build_layout(text)
    table=layout['tables'][0]
    assert len(table['rows'])==1
    row=table['rows'][0]
    assert row['continuations'][1]['text']=='actuator'
    assert row['quote'] in text
    assert row['cells'][2]['header']=='Qty' and row['cells'][2]['field']=='quantity'
    assert all(b['bbox'] is None for b in layout['blocks'])


def test_model_name_order_and_multiple_tables(tmp_path):
    text='TECHNICAL SPECIFICATION\nProduct name: Motor\nModel: MC-10\nVoltage: 110 V\nProduct name: Motor\nModel: MC-20\nVoltage: 220 V\n'
    draft=mgr(tmp_path).create_draft([('x.txt',text.encode())])
    assert len(draft['skus'])==2
    assert draft['skus'][0]['name']==draft['skus'][1]['name']=='Motor'
    for sku in draft['skus']:
        specs=[f['value'] for f in sku['facts'] if f['field']=='specifications']
        assert specs==['110 V' if sku['sku_code']=='MC-10' else '220 V']


def test_composite_match_and_ambiguous_match(tmp_path):
    m=mgr(tmp_path)
    invoice=b'COMMERCIAL INVOICE\nInvoice No: I-20\nProduct name: Gear assembly\nQuantity: 12\nUnit: PCS\nSpecifications: Diameter 30 mm\n'
    packing=b'PACKING LIST\nProduct name: Gear assembly\nQuantity: 12\nUnit: PCS\nPackages: 2 boxes\n'
    d=m.create_draft([('a.txt',invoice),('b.txt',packing)])
    assert len(d['skus'])==1
    assert any('quantity_and_unit' in x['reasons'] for x in d['skus'][0]['matching'])
    # Two indistinguishable invoice rows must not both attach to one packing row.
    double=invoice+b'Product name: Gear assembly\nQuantity: 12\nUnit: PCS\nSpecifications: Diameter 30 mm\n'
    d=m.create_draft([('a.txt',double),('b.txt',packing)])
    assert len(d['skus'])==3
    assert any(x['status']=='needs_review' for s in d['skus'] for x in s['matching'])


def test_conflicting_same_model_preserved_and_no_hs_choice(tmp_path):
    m=mgr(tmp_path)
    a=b'COMMERCIAL INVOICE\nModel: MX-1\nProduct name: Motor\nPower: 1.5 kW\nHS Code: 8501.51.19\n'
    b=b'TECHNICAL DATASHEET\nModel: MX-1\nProduct name: Motor\nPower: 2.5 kW\n'
    draft=m.create_draft([('a.txt',a),('b.txt',b)])
    assert len(draft['skus'])==2
    assert all(s['identity_status']=='conflicting' for s in draft['skus'])
    assert any(r['status']=='conflict' for r in draft['reconciliations'])
    # Conflicting codes for a matching model: no automatically selected declared code.
    b=b'COMMERCIAL INVOICE\nModel: MX-1\nProduct name: Motor\nPower: 1.5 kW\nHS Code: 8501.52.29\n'
    draft=m.create_draft([('a.txt',a),('b.txt',b)])
    assert len(draft['skus'])==1 and draft['skus'][0]['declared_code'] is None
    assert draft['skus'][0]['field_states']['declared_code']=='conflicting'


def test_reconciliation_page_and_units(tmp_path):
    m=mgr(tmp_path)
    docs=[{'id':'invoice','name':'x','pages':[{'number':1,'text':'COMMERCIAL INVOICE\nInvoice No: IV-30\n'},{'number':3,'text':'Gross Weight: 2 kg\nModel: QZ-1\nProduct name: Valve\nQuantity: 12\nUnit: PCS\n'}]},
          {'id':'packing','name':'y','pages':[{'number':2,'text':'PACKING LIST\nInvoice No: IV-30\nGross Weight: 2000 g\nModel: QZ-1\nProduct name: Valve\nQuantity: 13\nUnit: PCS\n'}]}]
    d=m.create_draft([],docs)
    weight=next(r for r in d['reconciliations'] if r['field']=='gross_weight' and r.get('sku_id') is None)
    assert weight['status']=='match'
    assert {i['page'] for i in weight['items']}=={2,3}
    assert any(r['field']=='quantity' and r['status']=='conflict' for r in d['reconciliations'])
    assert any(r['status']=='missing' for r in d['reconciliations'])


def test_source_permissions_and_legal_mentions():
    assert DocumentTypeDetector.detect('Memo\nThis brochure mentions catalogue and invoice in prose.')['kind']=='other'
    assert DocumentTypeDetector.detect('COMMERCIAL INVOICE\nInvoice No: AA-25\nReference 31/2022/TT-BTC\nModel: HS-20\nProduct name: Sensor')['kind']=='commercial_invoice'
    text='BILL OF LADING\nB/L No: SHIP-12\nModel: S-1\nProduct name: Sensor\nFunction: This is not a technical certificate\nMaterial: Glass\n'
    docs=[{'id':'ship','name':'data','pages':[{'number':1,'text':text}]}]
    skus=InformationExtractor.extract_candidate_skus(docs)
    assert skus and not any(f['field'] in {'function','material'} for f in skus[0]['facts'])


def test_structured_fact_metadata_and_user_edit_survive_save(tmp_path):
    m=mgr(tmp_path);svc=DocumentService(m.db,tmp_path/'uploads')
    try:
        text=b'COMMERCIAL INVOICE\nInvoice No: TST-200\nSKU | Description | Qty | Unit | Unit Price | Amount | Country of Origin\nVK-5 | Valve | 10 | PCS | 5.00 | 50.00 | Italy\n'
        draft=m.create_draft([('opaque.txt',text)])
        reviewed=json.loads(json.dumps(draft['skus']))
        q=next(f for f in reviewed[0]['facts'] if f['field']=='quantity')
        q['value']='11';q['status']='verified';q['source_row_id']='spoofed'
        case=m.commit_draft(draft['draft_id'],{'skus':reviewed,'dossier_fields':{'invoice_number':{'value':'USER-EDIT'}}},svc)
        loaded=m.db.get_sku(case['skus'][0]['id'])
        quantity=next(f for f in loaded['facts'] if f['field']=='quantity')
        assert quantity['value']=='11' and quantity['value_origin']=='user_input' and quantity['status']=='unverified'
        assert quantity['source_row_id']!='spoofed' and quantity['source_header']=='Qty'
        assert quantity['original_value']=='10'
        assert quantity['source_document_id']==quantity['document_id']
        cf=next(f for f in case['extracted_fields'] if f['field']=='invoice_number')
        assert cf['value']=='USER-EDIT' and cf['value_origin']=='user_input' and cf['original_value']=='TST-200'
        page=svc.pages(case['documents'][0]['id'])[0]
        assert page['layout']['tables'][0]['rows'][0]['cells'][2]['text']=='10'
        assert next(f for f in loaded['facts'] if f['field']=='origin')['value']=='Italy'
    finally:svc.close()


def test_ai_guard_and_source_gate():
    class Provider:
        calls=0
        def estimate_cost(self,pages):return .01
        def suggest(self,pages,max_output_tokens):
            self.calls+=1
            return [{'field_name':'name','value':'Valve','source_document_id':'x','source_page':1,'source_quote':'Product: Valve','source_block_ids':['b0']},
                    {'field_name':'function','value':'Imagined use','source_document_id':'x','source_page':1,'source_quote':'Product: Valve','source_block_ids':['b0']}]
    provider=Provider();page={'number':1,'document_id':'x','text':'Product: Valve','layout':build_layout('Product: Valve')}
    assert AssistedExtraction(provider).extract([page],'technical_spec')['status']=='disabled'
    adapter=AssistedExtraction(provider,AssistancePolicy(enabled=True,allow_external_data=True,max_cost=.015))
    assert adapter.extract([page],'technical_spec')['status']=='authorization_required'
    assert provider.calls==0
    result=adapter.extract([page],'technical_spec',authorized=True)
    assert len(result['suggestions'])==1 and result['suggestions'][0]['status']=='unverified'
    assert result['rejected']
    assert adapter.extract([page],'technical_spec',authorized=True)['status']=='cost_budget_exceeded'
    assert provider.calls==1


def test_short_text_pdf_keeps_text_and_layout(tmp_path):
    from reportlab.pdfgen import canvas
    out=io.BytesIO();c=canvas.Canvas(out);c.drawString(40,750,'Invoice No: X-1');c.showPage();c.save()
    pages=parse_file_bytes('arbitrary.pdf',out.getvalue())
    assert pages[0]['method'] in {'pdf_text','pdftotext'}
    assert pages[0]['layout']['blocks']
    assert 'X-1' in pages[0]['text']


def test_same_document_table_continuation_keeps_header_source(tmp_path):
    docs=[{'id':'x','name':'x.pdf','pages':[{'number':1,'text':'COMMERCIAL INVOICE\nInvoice No: P-20\nSKU | Description | Quantity | Unit\nVALVE-1 | Valve | 20 | PCS\n'}, {'number':2,'text':'VALVE-2 | Valve | 30 | PCS\n'}]}]
    draft=mgr(tmp_path).create_draft([],docs)
    assert len(draft['skus'])==2
    s=next(s for s in draft['skus'] if s['sku_code']=='VALVE-2')
    assert all(f['page_number']==2 and f['source_header_page']==1 for f in s['facts'])
    assert all(f['extraction_status']=='needs_review' for f in s['facts'])


def test_labelled_quantity_with_unit_does_not_invent_missing_data(tmp_path):
    d=mgr(tmp_path).create_draft([('x.txt',b'COMMERCIAL INVOICE\nInvoice No: XX-1\nModel: X-1\nProduct name: Valve\nQuantity: 20 PCS\n')])
    q=next(f for f in d['skus'][0]['facts'] if f['field']=='quantity')
    assert q['value']=='20' and q['quote']=='Quantity: 20 PCS'
    assert d['skus'][0]['resolved_fields']['unit']=='PCS'


def test_user_confirms_uncertain_match_and_can_save(tmp_path):
    m=mgr(tmp_path);svc=DocumentService(m.db,tmp_path/'uploads')
    try:
        a=b'COMMERCIAL INVOICE\nInvoice No: A-20\nProduct name: Mechanical coupling\nQuantity: 12\nUnit: PCS\n'
        b=b'PACKING LIST\nProduct name: Mechanical coupling\nPackages: 2 boxes\n'
        d=m.create_draft([('a.txt',a),('b.txt',b)]);assert len(d['skus'])==2
        target,source=d['skus']
        updated=m.update_draft(d['draft_id'],{'match_confirmations':[{'target_sku_id':target['id'],'source_sku_id':source['id'],'confirmed':True}]})
        assert len(updated['skus'])==1 and updated['skus'][0]['identity_status']=='user_confirmed_match'
        saved=m.commit_draft(d['draft_id'],{},svc)
        assert len(saved['skus'])==1
        assert any(e['action']=='product_matching_confirmed' for e in saved['events'])
        assert len({f['document_id'] for f in m.db.get_sku(saved['skus'][0]['id'])['facts']})==2
    finally:svc.close()


def test_multiline_fixed_width_header_and_total_not_a_product(tmp_path):
    text=('PACKING LIST\nInvoice No: ML-30\n'
          'NAME OF GOODS                     QUANTITY      NET          GROSS\n'
          '                                  (BAGS)        WEIGHT       WEIGHT\n'
          '                                                (KGM)        (KGM)\n'
          'Ceramic pellets for\n'
          'industrial use                    50            1000         1020\n'
          'TOTAL                             50            1000         1020\n')
    d=mgr(tmp_path).create_draft([('x.txt',text.encode())])
    assert len(d['skus'])==1
    s=d['skus'][0];assert s['name']=='Ceramic pellets for industrial use'
    assert s['resolved_fields']['quantity']=='50' and s['resolved_fields']['unit']=='BAGS'
    assert s['resolved_fields']['net_weight']=='1000' and s['resolved_fields']['gross_weight']=='1020'
    assert s['field_states']['name']=='needs_review'


def test_non_electrical_measurement_conflicts_are_not_merged(tmp_path):
    a=b'TECHNICAL DATASHEET\nModel: RES-99\nProduct name: Resin\nSpecifications: Density 0.90 g/cm3\n'
    b=b'CERTIFICATE OF QUALITY\nCertificate No: CQ-90\nModel: RES-99\nProduct name: Resin\nSpecifications: Density 1.20 g/cm3\n'
    d=mgr(tmp_path).create_draft([('a.txt',a),('b.txt',b)])
    assert len(d['skus'])==2 and all(s['identity_status']=='conflicting' for s in d['skus'])


def test_real_annotations_require_review_and_block_split_leakage():
    import importlib.util
    spec=importlib.util.spec_from_file_location('annotation_tools',ROOT/'scripts/document_ai_annotations.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    record={'document_id':'d','source_sha256':'identical-bytes','case_id':'shipment','pages':[{'number':1,'text':'Product: Valve'}],
            'annotation_status':'pending','ground_truth':{'fields':[]}}
    assert module.validate([record])
    from copy import deepcopy
    record.update(annotation_status='reviewed',reviewer='reviewer-a',second_reviewer='reviewer-b',ground_truth={'document_kind':'technical_spec','group_id':'shipment-a','template_family':'family-a','split':'development','fields':[]})
    other=deepcopy(record);other['document_id']='e';other['ground_truth'].update(split='holdout',group_id='shipment-b')
    assert any('leakage' in e for e in module.validate([record,other]))


def test_operator_sku_alias_preserves_model_and_incremental_match(tmp_path):
    m=mgr(tmp_path);svc=DocumentService(m.db,tmp_path/'uploads')
    try:
        d=m.create_draft([('spec.txt',b'TECHNICAL DATASHEET\nModel: SOURCE-80\nProduct name: Valve\nSpecifications: Diameter 40 mm\n')])
        reviewed=json.loads(json.dumps(d['skus']));reviewed[0]['sku_code']='OPERATOR-ALIAS'
        saved=m.commit_draft(d['draft_id'],{'skus':reviewed},svc)
        result=m.extract_for_case(saved['id'],svc)
        assert result['skus'][0]['existing_sku_id']==saved['skus'][0]['id']
        loaded=m.db.get_sku(saved['skus'][0]['id'])
        assert next(f for f in loaded['facts'] if f['field']=='model')['value']=='SOURCE-80'
    finally:svc.close()


def test_additive_migration_keeps_existing_case_and_facts(tmp_path):
    db=Workspace(tmp_path/'old.db');case=db.create_case('Existing manual dossier','Operator');sku=db.add_sku(case['id'],'OLD-1','Existing product')
    db.add_fact(sku['id'],'name','Existing product',quote='Manual input',source_kind='manual_declaration')
    with db.connect() as conn:
        conn.execute('DROP TABLE fact_sources');conn.execute('DROP TABLE page_layouts');conn.execute('DROP TABLE case_extracted_fields')
    reopened=Workspace(tmp_path/'old.db')
    assert reopened.get_case(case['id'])['title']=='Existing manual dossier'
    assert reopened.get_sku(sku['id'])['facts'][0]['value']=='Existing product'


def test_pdf_page_limit_is_an_explicit_error(monkeypatch):
    from pypdf import PdfWriter
    from hs_assistant.extractor import DocumentPageLimitError
    writer=PdfWriter()
    for _ in range(3):writer.add_blank_page(width=100,height=100)
    data=io.BytesIO();writer.write(data)
    monkeypatch.setenv('HS_MAX_DOCUMENT_PAGES','2')
    with pytest.raises(DocumentPageLimitError,match='không cắt trang'):
        parse_file_bytes('x.pdf',data.getvalue())


def test_incremental_apply_is_idempotent_and_keeps_metadata(tmp_path):
    m=mgr(tmp_path);svc=DocumentService(m.db,tmp_path/'uploads')
    try:
        d=m.create_draft([('invoice.txt',b'COMMERCIAL INVOICE\nInvoice No: ID-88\nModel: PART-88\nProduct name: Valve\nQuantity: 20\nUnit: PCS\n')])
        case=m.commit_draft(d['draft_id'],{},svc);candidate=m.extract_for_case(case['id'],svc)
        m.apply_to_case(case['id'],candidate)
        first=m.db.get_sku(case['skus'][0]['id']);metadata_count=len(m.db.get_case(case['id'])['extracted_fields'])
        m.apply_to_case(case['id'],candidate)
        assert len(m.db.get_sku(case['skus'][0]['id'])['facts'])==len(first['facts'])
        assert len(m.db.get_case(case['id'])['extracted_fields'])==metadata_count
    finally:svc.close()


def test_legal_heading_dominates_embedded_invoice_and_appendix_is_isolated(tmp_path):
    legal='Thông tư số 31/2022/TT-BTC\nDanh mục hàng hóa xuất khẩu, nhập khẩu Việt Nam\n8507.10.10\nCOMMERCIAL INVOICE\nInvoice No: EXAMPLE-1\nModel: LAW-1\nProduct name: Legal example\n'
    assert DocumentTypeDetector.detect(legal)['kind']=='legal_reference'
    docs=[{'id':'mixed','name':'unknown.pdf','pages':[{'number':1,'text':'TECHNICAL DATASHEET\nModel: MAIN-1\nProduct name: Valve\nSpecifications: Diameter 40 mm\n'},{'number':2,'text':legal}]}]
    d=mgr(tmp_path).create_draft([],docs)
    assert [s['sku_code']for s in d['skus']]==['MAIN-1']
    assert not d['dossier_fields']
