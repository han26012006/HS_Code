"""Schema-guided, page/layout-aware extraction and conservative entity matching."""
from __future__ import annotations
import hashlib
import re
from .document_layout import ensure_layout, norm
from .document_schema import PRODUCT_TYPES, TRADE_TYPES, PRODUCT_FIELDS, label_field, allowed, hs_code

PRODUCT=PRODUCT_TYPES
TRANSACTION=TRADE_TYPES
normalized=norm
MODEL=re.compile(r'\b(?:model|sku|part\s*(?:number|no\.?)|mã\s*(?:sản\s*phẩm|hàng))\s*[:=]?\s*([\w][\w./-]*)',re.I)


def role(doc):
    from .extractor import DocumentTypeDetector
    kind=DocumentTypeDetector.detect_type(doc)['kind']
    return 'legal_reference' if kind=='legal_reference' else ('product_evidence' if kind in PRODUCT else 'transaction_evidence' if kind in TRANSACTION else 'unknown')


def make_source(field,value,doc,page,quote,make_fact,**context):
    if not value or not quote or norm(quote) not in norm(page.get('text','')):
        return None
    fragments=context.get('value_fragments',[])
    assembled=bool(fragments) and all(norm(v) in norm(quote) for v in fragments) and norm(value)==norm(' '.join(fragments))
    if not assembled and norm(value) not in norm(quote) and not (field=='declared_code' and hs_code(value)==hs_code(value.replace('.','')) and value in quote.replace('.','')):
        return None
    fact=make_fact(field,value,doc['id'],doc.get('name',''),page['number'],quote)
    fact.update(field_name=field, source_document_id=doc['id'],source_page=page['number'],source_quote=quote,
                source_kind='document_extracted',extraction_status='extracted',source_valid=True,
                extraction_method=page.get('method','text')+':layout_schema',source_document_type=doc['_kind'],**context)
    return fact


def _section_spans(page):
    """Boundaries from item headings and repeated semantic identity fields.

    Works with name-before-model and model-before-name. Shared header facts are
    not copied into a product section or across pages.
    """
    layout=page['layout'];text=page['text']
    table_blocks={b for t in layout['tables'] for r in t['rows'] for b in r['block_ids']}|{t['header_block_id'] for t in layout['tables']}|{b for t in layout['tables'] for b in t.get('header_block_ids',[])}
    starts=[]; seen=set();last=0
    relation_by_block={r['block_ids'][0]:r for r in layout['key_values'] if label_field(r['label']) in {'name','model','part_number'}}
    explicit=list(re.finditer(r'(?im)^\s*(?:item|sản\s*phẩm|mặt\s*hàng)\s*\d+\s*[:.]',text))
    if explicit:
        positions=[m.start() for m in explicit]
        return [(start,positions[i+1] if i+1<len(positions) else len(text)) for i,start in enumerate(positions)]
    for block in layout['blocks']:
        if block['id'] in table_blocks:continue
        relation=relation_by_block.get(block['id'])
        field=label_field(relation['label']) if relation else None
        standalone=re.fullmatch(r'\s*([A-Z][A-Z0-9]+(?:[-/][A-Z0-9]+)+)\s*(?:\|[^\n]*)?',block['text'])
        if standalone:field='model'
        if field in {'name','model','part_number'}:
            if field in seen:
                starts.append(last);last=block['start'];seen=set()
            seen.add(field)
    starts.append(last)
    return [(start,starts[i+1] if i+1<len(starts) else len(text)) for i,start in enumerate(starts)]


def _local_candidates(doc,make_fact):
    results=[]
    for page in doc['pages']:
        from .extractor import DocumentTypeDetector
        if DocumentTypeDetector.detect_type({'pages':[page]})['kind']=='legal_reference':continue
        layout=page['layout']; covered={b for t in layout['tables'] for r in t['rows'] for b in r['block_ids']}|{t['header_block_id'] for t in layout['tables']}|{b for t in layout['tables'] for b in t.get('header_block_ids',[])}
        for table in layout['tables']:
            for row in table['rows']:
                facts=[]
                cell_candidates=[]
                for original_cell in row['cells']:
                    fragments=original_cell.get('value_fragments',[])
                    prefix=[];embedded=[]
                    if original_cell['field']=='name' and fragments:
                        for fragment in fragments:
                            match=re.match(r'^([^:]{2,50}):\s*(.+)$',fragment)
                            field=label_field(match.group(1)) if match else None
                            if match and not field:
                                from .pdf_tables import _label
                                field=_label(match.group(1))
                            if match and field and field!='name':embedded.append({**original_cell,'field':field,'text':match.group(2),'header':match.group(1),'value_fragments':[match.group(2)]})
                            else:prefix.append(fragment)
                    if embedded:
                        if prefix:cell_candidates.append({**original_cell,'text':' '.join(prefix),'value_fragments':prefix})
                        cell_candidates.extend(embedded)
                    else:cell_candidates.append(original_cell)
                for original_cell in cell_candidates:
                    cell=dict(original_cell)
                    fragments=cell.get('value_fragments',[cell['text']])+[c['text'] for c in row.get('continuations',[]) if c['field']==cell['field'] and c['text']]
                    if len(fragments)>1:cell['text']=' '.join(fragments)
                    field=cell['field']
                    if not field or field=='line_number' or not allowed(doc['_kind'],field):continue
                    value=cell['text']
                    if field=='declared_code':value=hs_code(value)
                    fact=make_source(field,value,doc,page,row['quote'],make_fact,
                                     source_table_id=table['id'],source_row_id=row['id'],source_column=cell['column'],
                                     source_cells=cell.get('source_cells'),source_cell_bbox=cell.get('bbox'),source_header=cell['header'],source_header_page=table.get('header_source_page',page['number']),value_fragments=fragments if len(fragments)>1 else [],source_block_ids=row['block_ids'],source_span=[row['start'],row['end']])
                    if fact:
                        if cell.get('header_unit'):
                            fact['unit']=cell['header_unit'];fact['source_unit_quote']=cell.get('unit_quote','')
                        if cell.get('unit_hint'):fact['unit']=cell['unit_hint']['value'];fact['source_unit_quote']=cell['unit_hint']['quote']
                        if table.get('continuation') or row.get('layout_status')=='needs_review':fact['extraction_status']='needs_review'
                        facts.append(fact)
                if allowed(doc['_kind'],'origin') and not any(f['field']=='origin' for f in facts):
                    for block in layout['blocks']:
                        if block['id'] not in row['block_ids']:continue
                        match=re.search(r'\bmade\s+in\s+([^.;\n|]+)\s*$',block['text'],re.I)
                        if match:
                            f=make_source('origin',match.group(1).strip(),doc,page,block['text'].strip(),make_fact,source_block_ids=[block['id']],source_table_id=table['id'],source_row_id=row['id'],source_scope='explicit_origin_statement')
                            if f:facts.append(f)
                for original_cell in row['cells']:
                    unit=original_cell.get('header_unit');quote=original_cell.get('unit_quote')
                    if unit and quote and original_cell['field']=='quantity' and not any(f['field']=='unit' for f in facts):
                        f=make_source('unit',unit,doc,page,quote,make_fact,source_scope='table_header',source_row_id=row['id'],source_table_id=table['id'])
                        if f:facts.append(f)
                    currency=(unit or '').split('/')[0].strip()
                    if currency in {'USD','EUR','JPY','VND','CNY','GBP','SGD'} and quote and allowed(doc['_kind'],'currency') and not any(f['field']=='currency'for f in facts):
                        f=make_source('currency',currency,doc,page,quote,make_fact,source_scope='table_header',source_row_id=row['id'],source_table_id=table['id'])
                        if f:facts.append(f)
                for header_cell in table['header']:
                    if header_cell.get('unit_hint') and header_cell['field']=='quantity':
                        hint=header_cell['unit_hint']
                        f=make_source('unit',hint['value'],doc,page,hint['quote'],make_fact,source_block_ids=[hint['block_id']],source_scope='table_header',source_table_id=table['id'],source_row_id=row['id'])
                        if f:facts.append(f)
                for relation in layout['key_values']:
                    if label_field(relation['label'])=='currency' and allowed(doc['_kind'],'currency'):
                        f=make_source('currency',relation['value'],doc,page,relation['quote'],make_fact,source_block_ids=relation['block_ids'],source_scope='document_header',source_table_id=table['id'],source_row_id=row['id'])
                        if f:facts.append(f)
                if any(f['field'] in {'name','model','part_number'} for f in facts):results.append(_candidate(doc,page,facts,row['id']))
        for start,end in _section_spans(page):
            facts=[]
            for relation in layout['key_values']:
                if not (start<=relation['start'] and relation['end']<=end) or any(b in covered for b in relation['block_ids']):continue
                field=label_field(relation['label'])
                if not field or not allowed(doc['_kind'],field):continue
                if layout['tables'] and field=='name' and norm(relation['label']) in {'description','description of goods','commodity'}:
                    first=next((b['text'] for b in layout['blocks'] if b['id']==relation['block_ids'][0]),'')
                    if ':' not in first and '=' not in first:continue
                value=relation['value']
                if field in {'model','part_number'}:
                    match=re.match(r'([\w][\w./-]*)',value)
                    value=match.group(1) if match else ''
                if field=='declared_code':value=hs_code(value)
                fact=make_source(field,value,doc,page,relation['quote'],make_fact,source_block_ids=relation['block_ids'],source_span=[relation['start'],relation['end']],source_header=relation['label'])
                if fact:facts.append(fact)
            section='\n'.join(b['text'] for b in layout['blocks'] if b['id'] not in covered and start<=b['start']<end)
            # Inline item descriptions/identifiers remain bounded to the item.
            item=re.search(r'(?im)^\s*item\s*\d*\s*:\s*([^\n]+)',section)
            if item and not any(f['field']=='name' for f in facts):
                f=make_source('name',item.group(1).strip(),doc,page,item.group(0).strip(),make_fact,source_span=[start,end])
                if f:facts.append(f)
            if not any(f['field'] in {'model','part_number'} for f in facts):
                model=MODEL.search(section)
                if not model and doc['_kind'] in PRODUCT:model=re.search(r'(?m)^\s*([A-Z][A-Z0-9]+(?:[-/][A-Z0-9]+)+)\s*(?:\||$)',section)
                if model:
                    f=make_source('model',model.group(1),doc,page,model.group(0).strip(),make_fact,source_span=[start,end])
                    if f:facts.append(f)
            if not any(f['field']=='specifications' for f in facts) and allowed(doc['_kind'],'specifications'):
                for block in layout['blocks']:
                    if block['id'] not in covered and start<=block['start']<end and re.search(r'\b\d+(?:[.,]\d+)?\s*(?:W|V|Hz|mm|nm)\b',block['text'],re.I):
                        f=make_source('specifications',block['text'].strip(),doc,page,block['text'].strip(),make_fact,source_block_ids=[block['id']],source_span=[block['start'],block['end']])
                        if f:facts.append(f)
            if any(f['field'] in {'name','model','part_number'} for f in facts):
                results.append(_candidate(doc,page,facts,f's{start}'))
    return results


def _candidate(doc,page,facts,local_id):
    extra=[]
    for fact in facts:
        if fact['field']=='quantity':
            match=re.fullmatch(r'([0-9]+(?:[.,][0-9]+)*)\s+([A-Za-z][A-Za-z0-9²³]*)',fact['value'])
            if match:
                fact['raw_value']=fact['value'];fact['value']=match.group(1)
                if not any(f['field']=='unit' for f in facts):
                    extra.append({**fact,'id':fact['id']+'_unit','field':'unit','field_name':'unit','value':match.group(2),'extraction_method':fact['extraction_method']+':explicit_unit_split'})
    facts=facts+extra
    values=lambda field:list(dict.fromkeys(f['value'] for f in facts if f['field']==field))
    identity={k:values(k) for k in ('model','part_number') if values(k)}
    fingerprint=doc.get('sha256') or hashlib.sha256(page['text'].encode()).hexdigest()
    key=f"{fingerprint}:{page['number']}:{local_id}"
    return {'id':'cand_'+hashlib.sha256(key.encode()).hexdigest()[:12], 'identifiers':identity,
            'sku_code':next(iter(identity.get('model',[]) or identity.get('part_number',[])), 'cand_'+hashlib.sha256(key.encode()).hexdigest()[:12]),
            'name':next(iter(values('name')),''),'description':next(iter(values('name')),''),
            'facts':facts,'source_document_id':doc['id'],'source_page':page['number'],'product_family':'general',
            'declared_code':None,'status':'needs_review','identity_status':'explicit_identifier' if identity else 'needs_review',
            'matching':[],'source_members':[{'document_id':doc['id'],'page':page['number'],'local_id':local_id}]}


def _vals(candidate,field):return {norm(f['value']) for f in candidate['facts'] if f['field']==field}


def important_specs(candidate):
    """Compare explicit measurements, including non-electrical commodities.

    Only fixed physical unit conversions are normalized; raw evidence is retained.
    Unrecognized free-text specifications remain reviewable rather than inferred.
    """
    from decimal import Decimal,InvalidOperation
    conversions={'kw':('w',Decimal(1000)),'w':('w',Decimal(1)),
                 'kv':('v',Decimal(1000)),'v':('v',Decimal(1)),
                 'cm':('mm',Decimal(10)),'mm':('mm',Decimal(1)),
                 'khz':('hz',Decimal(1000)),'hz':('hz',Decimal(1))}
    result={}
    pattern=r'(?<![\w.])(\d+(?:[.,]\d+)?(?:\s*[-–/]\s*\d+(?:[.,]\d+)?)?)\s*([A-Za-zµ%°][A-Za-z0-9µ%°/^²³.-]*)'
    for fact in candidate['facts']:
        if fact['field']!='specifications':continue
        for number,unit in re.findall(pattern,fact['value']):
            unit=unit.rstrip('.').casefold();canonical,multiplier=conversions.get(unit,(unit,Decimal(1)))
            try:value=str((Decimal(number.replace(',','.'))*multiplier).normalize())
            except InvalidOperation:value=norm(number).replace(' ','')
            result.setdefault(canonical,set()).add(value)
    return result


def _relation(a,b):
    shared_ids=False
    for field in ('model','part_number'):
        va={norm(v) for v in a['identifiers'].get(field,[])};vb={norm(v) for v in b['identifiers'].get(field,[])}
        if va and vb:
            if not va&vb:return 'different',['different_'+field]
            shared_ids=True
    if {norm(v) for values in a['identifiers'].values() for v in values} & {norm(v) for values in b['identifiers'].values() for v in values}:
        shared_ids=True
    sa=important_specs(a);sb=important_specs(b)
    conflicts=[unit for unit in sa.keys() & sb.keys() if sa[unit]!=sb[unit]]
    if conflicts:return ('conflicting' if shared_ids else 'different'),['specification_'+u for u in conflicts]
    if shared_ids:
        if _vals(a,'specifications') and _vals(b,'specifications') and not sa and not sb and _vals(a,'specifications')!=_vals(b,'specifications'):
            return 'needs_review',['explicit_identifier','uncomparable_specifications']
        return 'match',['explicit_identifier']
    same_name=bool(_vals(a,'name')&_vals(b,'name'))
    strong=[]
    if same_name:strong.append('name')
    if sa and sb and sa==sb:strong.append('specifications')
    if _vals(a,'quantity') and _vals(a,'quantity')==_vals(b,'quantity') and _vals(a,'unit') and _vals(a,'unit')==_vals(b,'unit'):strong.append('quantity_and_unit')
    if same_name and len(strong)>=2:return 'candidate',strong
    if same_name:return 'needs_review',strong
    return 'different',[]


def _merge(target,candidate,reasons):
    target['source_members']+=candidate['source_members'];target['matching'].append({'status':'matched','reasons':reasons,'source_candidate_id':candidate['id']})
    for key,values in candidate['identifiers'].items():target['identifiers'][key]=list(dict.fromkeys(target['identifiers'].get(key,[])+values))
    target['facts']+=candidate['facts']
    if not target['name']:target['name']=candidate['name'];target['description']=candidate['description']
    if target['sku_code'].startswith('cand_') and not candidate['sku_code'].startswith('cand_'):target['sku_code']=candidate['sku_code']


def extract(docs,make_fact):
    from .extractor import DocumentTypeDetector
    locals=[]
    for original in sorted(docs,key=lambda d:d['id']):
        doc=ensure_layout(original);doc['_kind']=DocumentTypeDetector.detect_type(doc)['kind']
        if doc['_kind'] not in PRODUCT|TRANSACTION:continue
        locals+=_local_candidates(doc,make_fact)
    # Pass 1: explicit identifiers. Do not merge conflicting specifications.
    entities=[]
    for candidate in locals:
        links=[(entity,*_relation(entity,candidate)) for entity in entities]
        matches=[(e,reasons) for e,status,reasons in links if status=='match']
        if len(matches)==1:
            _merge(matches[0][0],candidate,matches[0][1]);continue
        for entity,status,reasons in links:
            if status in {'conflicting','needs_review'}:
                link={'status':status,'reasons':reasons,'candidate_id':candidate['id']}
                entity['matching'].append(link);candidate['matching'].append({**link,'candidate_id':entity['id']})
        entities.append(candidate)
    # Pass 2: one-to-one composite matching across documents only. Ambiguity stays explicit.
    candidates={}
    for i,a in enumerate(entities):
        for j,b in enumerate(entities):
            if i>=j or {x['document_id'] for x in a['source_members']}&{x['document_id'] for x in b['source_members']}:continue
            status,reasons=_relation(a,b)
            if status=='candidate':
                candidates.setdefault(i,[]).append((j,reasons));candidates.setdefault(j,[]).append((i,reasons))
            elif status=='needs_review':
                a['matching'].append({'status':'needs_review','candidate_id':b['id'],'reasons':reasons})
                b['matching'].append({'status':'needs_review','candidate_id':a['id'],'reasons':reasons})
    removed=set()
    for i,links in candidates.items():
        if i in removed:continue
        if len(links)==1:
            j,reasons=links[0]
            if j not in removed and len(candidates.get(j,[]))==1:
                _merge(entities[i],entities[j],reasons);removed.add(j);continue
        entities[i]['matching'].extend({'status':'needs_review','candidate_id':entities[j]['id'],'reasons':r} for j,r in links)
    results=[e for i,e in enumerate(entities) if i not in removed]
    duplicate_codes={e['sku_code'] for e in results if sum(x['sku_code']==e['sku_code'] for x in results)>1}
    for sku in results:
        if sku['sku_code'] in duplicate_codes:
            sku['base_sku_code']=sku['sku_code'];sku['sku_code']+='~'+sku['id'][5:11];sku['identity_status']='conflicting' if any(x['status']=='conflicting' for x in sku['matching']) else 'needs_review'
        unique=[]
        for fact in sku['facts']:
            fact['sku_id']=sku['id']
            if not any(all(f.get(k)==fact.get(k) for k in ('field','value','document_id','page_number','quote')) for f in unique):unique.append(fact)
        sku['facts']=unique
        for field in PRODUCT_FIELDS:
            facts=[f for f in unique if f['field']==field]
            # Quantities/prices/weights may refer to different shipments; keep conflict scoped to this batch.
            if field!='specifications' and len({norm(f['value']) for f in facts})>1:
                for fact in facts:fact.update(status='conflict',extraction_status='conflicting')
        sku['resolved_fields']={field:next(iter(values)) if len(values)==1 else None for field in PRODUCT_FIELDS for values in [{f['value'] for f in unique if f['field']==field}]}
        if sku['resolved_fields'].get('name') is None:sku['name']=''
        declared=[f for f in unique if f['field']=='declared_code']
        codes={f['value'] for f in declared}
        sku['declared_code']=next(iter(codes)) if len(codes)==1 else None
        sku['declared_code_sources']=declared
        sku['origin_sources']=[f for f in unique if f['field']=='origin']
        sku['missing_fields']=[field for field in ('name','function','construction','specifications') if not any(f['field']==field for f in unique)]
        sku['field_states']={field:('missing' if not any(f['field']==field for f in unique) else 'conflicting' if any(f['field']==field and f['status']=='conflict' for f in unique) else 'needs_review' if any(f['field']==field and f.get('extraction_status')=='needs_review' for f in unique) else 'extracted') for field in PRODUCT_FIELDS}
    return sorted(results,key=lambda s:(s['sku_code'].casefold(),s['id']))
