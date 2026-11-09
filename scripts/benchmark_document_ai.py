"""Repeatable evaluator. Synthetic splits never imply real-world accuracy.

Run baseline in separate process with --backend scratch/document_ai_before.
No network, no AI calls. Null metrics mean no labelled denominator.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def ratio(a,b):return round(a/b,6) if b else None


def evaluate(fixtures, backend=None):
    sys.path.insert(0,str(Path(backend).resolve() if backend else ROOT))
    from hs_assistant.extractor import AutoFillDraftManager
    cases=json.loads(Path(fixtures).read_text());details=[]
    gold_tables=json.loads((ROOT/'tests/fixtures/document_ai/table_gold.json').read_text())['documents']
    counts=dict(class_correct=0,documents=0,field_tp=0,field_fp=0,field_fn=0,id_correct=0,id_total=0,
                sku_tp=0,sku_fp=0,sku_fn=0,citations_correct=0,citations_total=0,unsupported=0,
                rows_correct=0,rows_total=0,rows_exact=0,rows_predicted=0,pair_tp=0,pair_fp=0,pair_fn=0,matching_cases_correct=0,matching_cases_total=0,coverage_hits=0,coverage_total=0)
    for case in cases:
        docs=[{k:v for k,v in d.items() if not k.startswith('expected_')} for d in case['documents']]
        draft=AutoFillDraftManager(None).create_draft([],docs)
        expected_docs={d['id']:d for d in case['documents']}
        expected_products={p['identifier']:p for p in case['products']}
        evaluation_ids={}
        for sku in draft['skus']:
            members=sku.get('source_members') or [{'document_id':f['document_id'],'page':f['page_number'],'local_id':'s0'} for f in sku.get('facts',[])]
            actual_members={(m['document_id'],m['page'],m['local_id']) for m in members}
            matching=[p['identifier'] for p in case['products'] if p.get('members') and actual_members=={(m['document_id'],m['page'],m['local_id']) for m in p['members']}]
            evaluation_ids[sku['id']]=matching[0] if len(matching)==1 else sku['sku_code']
        actual_products={evaluation_ids[s['id']]:s for s in draft['skus']}
        counts['sku_tp']+=len(set(expected_products)&set(actual_products));counts['sku_fp']+=len(set(actual_products)-set(expected_products));counts['sku_fn']+=len(set(expected_products)-set(actual_products))
        exp=set();pred=set();expected_pairs=set();actual_pairs=set()
        for d in draft['documents']:
            target=expected_docs[d['id']];counts['documents']+=1
            counts['class_correct']+=int(d['kind']==target['expected_kind'])
            for field,value in target.get('expected_fields',{}).items():
                # Metadata labels include source identity, not only a global final value.
                exp.add(('document',d['id'],field,value))
                counts['id_total']+=1
                candidate=draft['dossier_fields'].get(field,{})
                candidates=candidate.get('sources',candidate.get('alternatives',[candidate]))
                counts['id_correct']+=int(any(c.get('value')==value and c.get('source_document_id')==d['id'] for c in candidates))
            expected_ids=target.get('expected_products',[])
            for identity in expected_ids:expected_pairs.add((d['id'],identity))
            expected_rows=target.get('expected_rows',0)
            if expected_rows:
                actual_rows=[r for p in d['pages'] for t in p.get('layout',{}).get('tables',[]) for r in t['rows']]
                # Exact set of labelled column values, not just row count.
                row_ids=[]
                for row in actual_rows:
                    code=next((c['text'] for c in row['cells'] if c['field'] in ('model','part_number')),None)
                    if code:row_ids.append(code)
                counts['rows_predicted']+=len(actual_rows)
                def flattened(row):
                    return sorted((field,value) for field,values in row.items() for value in (values if isinstance(values,list) else [values]))
                expected_sets=[flattened(row) for row in gold_tables.get(d['id'],[])]
                for row in actual_rows:
                    actual=sorted((c['field'],c['text']) for c in row['cells'] if c['field'] and c['field']!='line_number')
                    if actual in expected_sets:
                        counts['rows_exact']+=1;expected_sets.remove(actual)
                counts['rows_total']+=expected_rows
                counts['rows_correct']+=len(set(row_ids)&set(expected_ids))
        for field,candidate in draft['dossier_fields'].items():
            for f in candidate.get('sources',candidate.get('alternatives',[candidate])):
                if f.get('value') and field in expected_docs.get(f.get('source_document_id'),{}).get('expected_fields',{}):
                    pred.add(('document',f.get('source_document_id'),field,f['value']))
        for identifier,p in expected_products.items():
            for field,values in p['fields'].items():
                for value in values if isinstance(values,list) else [values]:exp.add(('product',identifier,field,value))
            if not p.get('identifier_is_gold'):
                if identifier in actual_products:
                    counts['id_total']+=1;counts['id_correct']+=1
                else:counts['id_total']+=1
        for s in draft['skus']:
            all_facts=list({(f.get('field'),f.get('value'),f.get('document_id'),f.get('page_number'),f.get('quote')):f for f in s.get('facts',[])+s.get('declared_code_sources',[])+s.get('origin_sources',[])}.values())
            for f in all_facts:
                field=f['field'];value=f['value'];identity=evaluation_ids[s['id']]
                # Only score fields explicitly in the annotation schema for this case;
                # extra predictions of scored fields are false positives.
                scored_fields={k for p in case['products'] for k in p['fields']}
                if field in scored_fields:pred.add(('product',identity,field,value))
                doc_id=f.get('document_id') or f.get('source_document_id');page_no=f.get('page_number') or f.get('source_page')
                actual_pairs.add((doc_id,identity));counts['citations_total']+=1
                source=next((p['text'] for d in docs if d['id']==doc_id for p in d['pages'] if p['number']==page_no),None)
                quote=f.get('quote') or f.get('source_quote','')
                from unicodedata import normalize
                n=lambda x:' '.join(normalize('NFC',str(x)).split()).casefold()
                fragments=f.get('value_fragments',[])
                assembled=bool(fragments) and all(n(v) in n(quote) for v in fragments) and n(value)==n(' '.join(fragments))
                supported=source is not None and bool(quote) and n(quote) in n(source) and (assembled or n(value) in n(quote) or (field=='declared_code' and value in quote.replace('.','')))
                identity_supported=identity in expected_docs.get(doc_id,{}).get('expected_products',[])
                counts['citations_correct']+=int(supported and identity_supported)
                counts['unsupported']+=int(not supported)
        counts['field_tp']+=len(exp&pred);counts['field_fp']+=len(pred-exp);counts['field_fn']+=len(exp-pred)
        counts['coverage_hits']+=len(exp&pred);counts['coverage_total']+=len(exp)
        counts['matching_cases_total']+=1;counts['matching_cases_correct']+=int(expected_pairs==actual_pairs)
        counts['pair_tp']+=len(expected_pairs&actual_pairs);counts['pair_fp']+=len(actual_pairs-expected_pairs);counts['pair_fn']+=len(expected_pairs-actual_pairs)
        details.append({'case_id':case['id'],'expected_skus':list(expected_products),'actual_skus':list(actual_products),'missing_fields':sorted(exp-pred),'unexpected_fields':sorted(pred-exp)})
    p=ratio(counts['field_tp'],counts['field_tp']+counts['field_fp']);r=ratio(counts['field_tp'],counts['field_tp']+counts['field_fn'])
    metrics={'document_classification_accuracy':ratio(counts['class_correct'],counts['documents']),
             'field_precision':p,'field_recall':r,'field_f1':round(2*p*r/(p+r),6) if p is not None and r is not None and p+r else 0,
             'identifier_exact_match':ratio(counts['id_correct'],counts['id_total']),
             'table_row_exact_recall':ratio(counts['rows_exact'],counts['rows_total']),
             'table_row_exact_precision':ratio(counts['rows_exact'],counts['rows_predicted']),
             'table_row_identity_accuracy':ratio(counts['rows_correct'],counts['rows_total']),
             'sku_precision':ratio(counts['sku_tp'],counts['sku_tp']+counts['sku_fp']), 'sku_recall':ratio(counts['sku_tp'],counts['sku_tp']+counts['sku_fn']),
             'cross_document_matching_case_accuracy':ratio(counts['matching_cases_correct'],counts['matching_cases_total']),
             'cross_document_membership_jaccard':ratio(counts['pair_tp'],counts['pair_tp']+counts['pair_fp']+counts['pair_fn']),
             'citation_correctness':ratio(counts['citations_correct'],counts['citations_total']),
             'unsupported_value_rate':ratio(counts['unsupported'],counts['citations_total']),
             'autofill_coverage':ratio(counts['coverage_hits'],counts['coverage_total'])}
    return {'dataset':str(fixtures),'dataset_sha256':hashlib.sha256(Path(fixtures).read_bytes()).hexdigest(),
            'table_gold_sha256':hashlib.sha256((ROOT/'tests/fixtures/document_ai/table_gold.json').read_bytes()).hexdigest(),
            'evaluator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'synthetic author-labelled; no independent reviewed real holdout; field scores cover explicitly annotated document/product fields','metrics':metrics,'counts':counts,'details':details}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fixtures',required=True);parser.add_argument('--backend');parser.add_argument('--output',required=True)
    args=parser.parse_args();result=evaluate(args.fixtures,args.backend);Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result['metrics'],indent=2))
