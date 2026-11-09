import json
from pathlib import Path
import pytest
from hs_assistant.extractor import AutoFillDraftManager,parse_file_bytes,InformationExtractor
from hs_assistant.workspace import Workspace
from hs_assistant.documents import DocumentService
from hs_assistant.field_validation import usable_metadata

FIX=Path(__file__).parent/'fixtures/zip_accuracy'


def draft(name):
    return AutoFillDraftManager(None).create_draft([('unrelated'+Path(name).suffix,(FIX/name).read_bytes())])


def test_real_two_page_invoice_keeps_46_lines_and_excludes_total():
    d=draft('01a89645.pdf');assert len(d['skus'])==46
    assert d['extracted_case']['invoice_number']=='VN-INV-ST11'
    by_code={s['sku_code']:s for s in d['skus']}
    for code,quantity,amount,page in [('3385A','180','216.00',1),('88017A','40','48.00',1),('333-5','192','153.60',2)]:
        s=by_code[code];facts={f['field']:f for f in s['facts']}
        assert facts['quantity']['value']==quantity and facts['amount']['value']==amount
        assert facts['quantity']['page_number']==page
        assert facts['part_number']['source_cell_bbox']
        assert facts['quantity']['source_header_page']==1
    assert not any(s['sku_code'].lower().startswith('total')for s in d['skus'])


def test_real_computer_variants_and_shared_weights_are_not_cross_assigned():
    d=draft('254374c4.pdf');assert len(d['skus'])==9
    assert sum('mainboard' in s['sku_code']for s in d['skus'])==4
    ram=next(s for s in d['skus']if s['name']=='HEOVSE BRAND RAM')
    ssd=next(s for s in d['skus']if s['name']=='HEOVSE BRAND SSD')
    for s,q in ((ram,'150'),(ssd,'300')):
        assert next(f['value']for f in s['facts']if f['field']=='quantity')==q
        assert not any(f['field']in {'packages','net_weight','gross_weight'}for f in s['facts'])
    assert any('Ô gộp' in w['message']for w in d['warnings'])


def test_actual_customs_workbook_cells_and_missing_declaration():
    d=draft('28862cb2.xlsx');assert d['documents'][0]['kind']=='customs_declaration'
    assert len(d['skus'])==1 and d['extracted_case']['declaration_number']==''
    s=d['skus'][0];facts={f['field']:f for f in s['facts']}
    assert s['declared_code']=='03063120'
    assert facts['quantity']['value']=='1.000' and facts['unit']['value']=='KGM'
    assert facts['name']['source_cells']==['C144','G144']
    assert d['dossier_fields']['bl_number']['value']=='060424SZLY21910025'
    assert d['dossier_fields']['importer']['value']=='CÔNG TY TNHH TIẾP VẬN TÂN NGUYÊN'


def test_actual_scanned_pdf_with_tiny_date_overlay_runs_ocr():
    pages=parse_file_bytes('opaque.pdf',(FIX/'d3c1f369.pdf').read_bytes())
    assert pages[0]['method'].startswith('ocr_')
    assert 'FOLDER GLUER' in pages[0]['text'] and len(pages[0]['text'])>500
    assert any('Sparse text overlay' in w['message']for w in pages[0]['warnings'])


def test_header_words_and_shipping_container_ids_are_not_facts():
    assert not usable_metadata('currency','Declared value')
    assert not usable_metadata('shipper','Page')
    assert not usable_metadata('importer','Mã 0101162092')
    text='BILL OF LADING\nB/L No: TEST-100\nPort of loading: Singapore\nABCD1234567/SEAL009/40HC\nWXYZ2345678/SEAL010/40HC\n'
    docs=[{'id':'d','name':'arbitrary','pages':[{'number':1,'text':text}]}]
    assert InformationExtractor.extract_candidate_skus(docs)==[]


def test_geometry_provenance_survives_save_and_reload(tmp_path):
    db=Workspace(tmp_path/'workspace.db');manager=AutoFillDraftManager(db);service=DocumentService(db,tmp_path/'uploads')
    try:
        d=manager.create_draft([('opaque.pdf',(FIX/'254374c4.pdf').read_bytes())])
        case=manager.commit_draft(d['draft_id'],{'title':'Real table regression'},service)
        assert len(case['skus'])==9
        for sku in case['skus']:
            loaded=db.get_sku(sku['id'])
            assert all(f['source_document_id']==f['document_id']for f in loaded['facts'])
            assert all(f['status']=='unverified'for f in loaded['facts'])
            assert any(f.get('source_cell_bbox')for f in loaded['facts'])
    finally:service.close()
