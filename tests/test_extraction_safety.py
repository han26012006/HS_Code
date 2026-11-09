import json
import sqlite3
from pathlib import Path
import pytest
from hs_assistant.extractor import AutoFillDraftManager, InformationExtractor, parse_file_bytes
from hs_assistant.workspace import Workspace
from hs_assistant.documents import DocumentService


def manager(tmp_path):
    return AutoFillDraftManager(Workspace(tmp_path/'db.sqlite'))


def tech(model, power):
    return f'TECHNICAL SPECIFICATION\nModel: {model}\nProduct name: Household dryer\nFunction: Dry hair\nConstruction: Fan and heater\nPower: {power} W\nVoltage: 220 V\n'


def test_pages_legal_order_and_identity(tmp_path):
    m=manager(tmp_path)
    docs=[{'id':'p','name':'random.pdf','pages':[{'number':i,'text':tech('AC-'+str(w),w)} for i,w in enumerate((1200,1600),1)]},
          {'id':'l','name':'spec.pdf','pages':[{'number':1,'text':'Danh mục hàng hóa xuất khẩu, nhập khẩu Việt Nam\n31/2022/TT-BTC\n8507.10.10 khởi động\n8516.31.00 Máy sấy khô tóc'}]}]
    a=m.create_draft([],docs);b=m.create_draft([],list(reversed(docs)))
    assert [s['sku_code'] for s in a['skus']]==[s['sku_code'] for s in b['skus']]==['AC-1200','AC-1600']
    assert a['extracted_case']['declaration_number']==''
    for i,s in enumerate(a['skus'],1):
        assert s['declared_code'] is None
        for f in s['facts']:
            assert f['document_id']=='p' and f['page_number']==i
            assert f['value'] in f['quote']
        assert not any(str(1600 if i==1 else 1200) in f['value'] for f in s['facts'])
    assert m.create_draft([],docs[1:])['skus']==[]


def test_invoice_packing_and_missing(tmp_path):
    m=manager(tmp_path)
    inv='COMMERCIAL INVOICE\nInvoice No: INV-001\nItem 1: Model AA-1 Dryer\nPower: 1200 W\nItem 2: Model AA-2 Dryer\nPower: 1600 W\n'
    pack='PACKING LIST\nModel: AA-1\nPackaging: Paper box\n'
    d=m.create_draft([('a.txt',inv.encode()),('b.txt',pack.encode())])
    assert len(d['skus'])==2
    assert len({f['document_id'] for f in d['skus'][0]['facts']})==2
    assert 'function' in d['skus'][0]['missing_fields']
    assert not m.create_draft([('broken.pdf',b'%PDF invalid')])['skus']


def test_commit_load_and_reject_wrong_source(tmp_path):
    m=manager(tmp_path);svc=DocumentService(m.db,tmp_path/'uploads')
    try:
        d=m.create_draft([('spec.txt',tech('AB-1',1200).encode())])
        s=d['skus'][0]
        bad=json.loads(json.dumps(s));bad['facts'][0]['page_number']=9
        with pytest.raises(ValueError):m.commit_draft(d['draft_id'],{'skus':[bad]},svc)
        assert m.db.summary()['cases']==0
        case=m.commit_draft(d['draft_id'],{'owner':'Tester','title':'Test case'},svc)
        facts=m.db.get_sku(case['skus'][0]['id'])['facts']
        assert facts and all(f['document_id'] and f['status']=='unverified' for f in facts)
    finally:svc.close()


def test_full_pdf_pages(tmp_path):
    from pypdf import PdfWriter
    import io
    writer=PdfWriter()
    for _ in range(7):writer.add_blank_page(width=100,height=100)
    out=io.BytesIO();writer.write(out)
    pages=parse_file_bytes('blank.pdf',out.getvalue())
    assert [p['number'] for p in pages]==list(range(1,8))


def test_invoice_table(tmp_path):
    draft=manager(tmp_path).create_draft([('invoice.txt',b'COMMERCIAL INVOICE\nSKU | Description | Power\nX-1 | Dryer | 1200 W\nX-2 | Dryer | 1600 W\n')])
    assert [s['sku_code'] for s in draft['skus']]==['X-1','X-2']
    assert all(f['value'] in f['quote'] for s in draft['skus'] for f in s['facts'])


def test_conflicting_transaction_values_are_not_first_match(tmp_path):
    m=manager(tmp_path)
    d=m.create_draft([('one.txt',b'COMMERCIAL INVOICE\nInvoice No: INV-111\n'),('two.txt',b'COMMERCIAL INVOICE\nInvoice No: INV-222\n')])
    assert d['dossier_fields']['invoice_number']['status']=='conflicting'
    assert d['extracted_case']['invoice_number']==''


def test_commit_failure_rolls_back_case(tmp_path):
    m=manager(tmp_path)
    svc=DocumentService(m.db,tmp_path/'uploads')
    d=m.create_draft([('spec.txt',tech('AB-2',1200).encode())])
    original=m.db.add_fact
    def fail(**kwargs):raise ValueError('Simulated persistence failure')
    m.db.add_fact=fail
    try:
        with pytest.raises(ValueError):m.commit_draft(d['draft_id'],{},svc)
        assert m.db.summary()['cases']==0
        assert m.get_draft(d['draft_id'])
    finally:
        m.db.add_fact=original
        svc.close()


def test_same_name_without_models_stays_separate_for_review(tmp_path):
    d=manager(tmp_path).create_draft([('spec.txt',b'TECHNICAL SPECIFICATION\nProduct name: Dryer\nPower: 1200 W\nProduct name: Dryer\nPower: 1600 W\n')])
    assert len(d['skus'])==2
    assert all(s['identity_status']=='needs_review' for s in d['skus'])
    for sku in d['skus']:
        assert len({f['value'] for f in sku['facts'] if f['field']=='specifications'})==1
