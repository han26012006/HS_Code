"""Prepare real-source review queue and validate independently reviewed annotations.

No file or extracted text is sent to an external service. Groups must be assigned
by reviewers BEFORE a real development/holdout split can be scored.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hs_assistant.document_layout import norm


def export_queue(database,output):
    conn=sqlite3.connect('file:'+str(Path(database).resolve())+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    records=[]
    exposed={r['sha256'] for r in json.loads((ROOT/'tests/fixtures/document_ai/real_development_exposure.json').read_text())}
    for d in conn.execute('SELECT id,case_id,name,sha256,path,kind FROM documents ORDER BY id'):
        pages=[dict(p) for p in conn.execute('SELECT number,text,method FROM pages WHERE document_id=? ORDER BY number',(d['id'],))]
        records.append({'document_id':d['id'],'source_sha256':d['sha256'],'source_available':Path(d['path']).exists(),
                        'development_exposure':d['sha256'] in exposed,'name':d['name'],'case_id':d['case_id'],'pages':pages,'annotation_status':'pending',
                        'ground_truth':{'document_kind':None,'group_id':None,'template_family':None,'split':None,'products':[],'fields':[],'table_rows':[],'matching_links':[]},
                        'reviewer':None,'second_reviewer':None,'note':'Assign shipment/template/product-family group before splitting; a missing original PDF cannot validate OCR quality.'})
    conn.close();Path(output).write_text(json.dumps(records,ensure_ascii=False,indent=2));return len(records)


def validate(records):
    errors=[];groups={};fingerprints={};templates={};shipments={}
    for record in records:
        if record['annotation_status']!='reviewed':errors.append(f"{record['document_id']}: not independently reviewed");continue
        truth=record['ground_truth'];reviewers={record.get('reviewer'),record.get('second_reviewer')}-{None,''}
        if len(reviewers)<2:errors.append(f"{record['document_id']}: two independent reviewers required")
        if not truth.get('document_kind') or not truth.get('group_id') or truth.get('split') not in {'development','holdout'}:errors.append(f"{record['document_id']}: incomplete classification/group/split")
        if record.get('development_exposure') and truth.get('split')=='holdout':errors.append(f"{record['document_id']}: exposed development document cannot be real holdout")
        previous=groups.setdefault(truth.get('group_id'),truth.get('split'))
        if previous!=truth.get('split'):errors.append(f"{truth['group_id']}: group leakage across splits")
        for key,registry in ((record.get('source_sha256'),fingerprints),(record.get('case_id'),shipments),(truth.get('template_family'),templates)):
            if key and registry.setdefault(key,truth.get('split'))!=truth.get('split'):errors.append(f'{key}: duplicate/template/shipment leakage across splits')
        if not truth.get('template_family'):errors.append(f"{record['document_id']}: template family required")
        for field in truth.get('fields',[]):
            page=next((p for p in record['pages'] if p['number']==field.get('source_page')),None)
            quote=field.get('source_quote','');value=str(field.get('value',''))
            if not page or not quote or norm(quote) not in norm(page['text']) or norm(value) not in norm(quote):errors.append(f"{record['document_id']}: invalid field citation {field.get('field_name')}")
            if field.get('source_document_id')!=record['document_id']:errors.append(f"{record['document_id']}: mismatched document ID")
    return errors


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database');parser.add_argument('--output');parser.add_argument('--validate')
    args=parser.parse_args()
    if args.validate:
        errors=validate(json.loads(Path(args.validate).read_text()));print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False,indent=2));sys.exit(bool(errors))
    print({'queued':export_queue(args.database,args.output)})
