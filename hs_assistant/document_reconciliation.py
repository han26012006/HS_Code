"""Evidence-based cross-document checks; never reconcile unrelated global text."""
from decimal import Decimal,InvalidOperation
import re
from .document_layout import norm

UNIT_ALIASES={'pcs':'pc','pieces':'pc','piece':'pc','units':'pc','unit':'pc','kg':'kg','kgm':'kg','kgs':'kg','g':'g','mt':'t','tons':'t','ton':'t','m':'m','m2':'m2','m3':'m3'}
NUMERIC_FACTS={'quantity','gross_weight','net_weight','total_gross_weight','total_net_weight','total_packages','packages','unit_price','amount'}


def comparable(value,unit=None):
    value=norm(value)
    # Recognize complete comma thousands groups, without changing source text.
    # Decimal commas and dot thousands notation remain subject to review.
    value=re.sub(r'^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?=\s*[a-z0-9]*$)',lambda m:m.group().replace(',',''),value)
    match=re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*([a-z0-9]+)?',value)
    if not match:return value
    try:number=Decimal(match.group(1))
    except InvalidOperation:return value
    unit=UNIT_ALIASES.get(norm(unit or match.group(2) or ''),norm(unit or match.group(2) or ''))
    if unit=='g':number/=1000;unit='kg'
    if unit=='t':number*=1000;unit='kg'
    return (number,unit)


def fact_value_key(fact):
    if fact['field'] in NUMERIC_FACTS:
        return comparable(fact['value'],fact.get('unit'))
    if fact['field']=='unit':
        value=norm(fact['value'])
        return UNIT_ALIASES.get(value,value)
    return norm(fact['value'])


def check(field,label,left,right,sku=None):
    def values(facts):
        return {comparable(f['value'],f.get('unit')) for f in facts}
    status='missing' if not left or not right else 'match' if values(left)==values(right) else 'conflict'
    if status=='conflict' and field in {'quantity','gross_weight','net_weight','total_gross_weight','total_net_weight','unit_price','amount'} and any(re.search(r'\d,\d',f['value']) for f in left+right):
        status='needs_review'
    return {'field':field,'label':label,'status':status,'sku_id':sku,'items':[
        {'source':f.get('document_name') or f.get('source_document_name'),'source_document_id':f.get('document_id') or f.get('source_document_id'),
         'value':f['value'],'page':f.get('page_number') or f.get('source_page'),'quote':f.get('quote') or f.get('source_quote') or f.get('source_excerpt')} for f in left+right],
         'description':{'missing':'Thiếu dữ liệu để đối chiếu.','match':'Các giá trị nguồn khớp nhau.','conflict':'Có mâu thuẫn; không tự chọn một giá trị.','needs_review':'Cần xác nhận định dạng số hoặc đơn vị trước khi kết luận mâu thuẫn.'}[status]}


def reconcile(docs,skus):
    from .extractor import DocumentTypeDetector,InformationExtractor
    kinds={d['id']:DocumentTypeDetector.detect_type(d)['kind'] for d in docs}
    metadata={d['id']:InformationExtractor.extract_dossier_fields([d]) for d in docs}
    results=[];seen=set()
    def add(result):
        key=(result['field'],result.get('sku_id'),tuple((x['source_document_id'],x['page'],x['value']) for x in result['items']))
        if key not in seen:seen.add(key);results.append(result)
    for sku in skus:
        for link in sku.get('matching',[]):
            if link['status']=='conflicting':
                add({'field':'power' if any('specification_w'==r for r in link['reasons']) else 'identity','label':sku.get('base_sku_code',sku['sku_code'])+' · Ghép sản phẩm','status':'conflict','sku_id':sku['id'],
                     'items':[],'description':'Cùng mã định danh nhưng thông số khác nhau; giữ riêng và cần người dùng xác nhận.','matching_candidate_id':link['candidate_id']})
        facts=sku['facts']
        for left_types,right_types,fields in [({'commercial_invoice'},{'packing_list'},('quantity','unit','gross_weight','net_weight','packages')),
                                             ({'commercial_invoice'},{'sales_contract'},('name','quantity','unit')),
                                             ({'commercial_invoice'},{'certificate_of_origin'},('origin',)),
                                             ({'certificate_of_quality','mill_test'},{'technical_spec'},('specifications','material')),
                                             ({'bill_of_lading','air_waybill'},{'packing_list'},('packages','gross_weight'))]:
            left_docs={x['document_id'] for x in sku['source_members'] if kinds.get(x['document_id']) in left_types}
            right_docs={x['document_id'] for x in sku['source_members'] if kinds.get(x['document_id']) in right_types}
            if not left_docs or not right_docs:continue
            for field in fields:
                left=[f for f in facts if f['field']==field and f['document_id'] in left_docs]
                right=[f for f in facts if f['field']==field and f['document_id'] in right_docs]
                # Quantity comparison uses the explicit unit on the same document/row.
                if field=='quantity':
                    def with_units(items):
                        return [{**f,'unit':next((u['value'] for u in facts if u['field']=='unit' and u['document_id']==f['document_id'] and u.get('source_row_id')==f.get('source_row_id')),None)} for f in items]
                    left,right=with_units(left),with_units(right)
                add(check(field,sku['sku_code']+' · '+field,left,right,sku['id']))
        for field in ('declared_code','quantity','origin'):
            conflicted=[f for f in facts if f['field']==field and f.get('extraction_status')=='conflicting']
            if conflicted:add(check(field,sku['sku_code']+' · '+field,conflicted[:1],conflicted[1:],sku['id']))
    # Shipment reference checks: all documents, exact provenance and actual pages.
    groups=[({'commercial_invoice'},{'packing_list'},('invoice_number','total_gross_weight','total_net_weight','total_packages')),
            ({'commercial_invoice'},{'sales_contract'},('contract_number',)),
            ({'commercial_invoice'},{'certificate_of_origin'},('invoice_number',)),
            ({'bill_of_lading','air_waybill'},{'packing_list'},('bl_number','total_gross_weight','total_packages'))]
    for lt,rt,fields in groups:
        left=[d for d in docs if kinds[d['id']] in lt];right=[d for d in docs if kinds[d['id']] in rt]
        for a in left:
            for b in right:
                # Multiple shipments need explicit linkage, not Cartesian assumptions.
                refs_a={metadata[a['id']].get(k,{}).get('value') for k in ('invoice_number','contract_number','bl_number')} - {None,''}
                refs_b={metadata[b['id']].get(k,{}).get('value') for k in ('invoice_number','contract_number','bl_number')} - {None,''}
                if (len(left)>1 or len(right)>1) and not refs_a&refs_b:continue
                for field in fields:
                    va=metadata[a['id']].get(field,{});vb=metadata[b['id']].get(field,{})
                    la=va.get('sources',[va]) if va.get('value') else []
                    rb=vb.get('sources',[vb]) if vb.get('value') else []
                    result=check('gross_weight' if field=='total_gross_weight' else field,field,la,rb)
                    result['document_pair']=[a['id'],b['id']]
                    add(result)
    return results
