"""Content/structure classification. Rule evidence is not a probability."""
import re
from .document_layout import norm, build_layout
from .document_schema import label_field

TITLES={
 'commercial_invoice':r'(?:(?:commercial|customs)\s+)?invoice|hóa\s*đơn\s*thương\s*mại',
 'packing_list':r'packing\s*list|bảng\s*kê\s*đóng\s*gói|phiếu\s*đóng\s*gói',
 'bill_of_lading':r'bill\s*of\s*lading|vận\s*đơn\s*đường\s*biển',
 'air_waybill':r'air\s*waybill|vận\s*đơn\s*hàng\s*không',
 'certificate_of_origin':r'certificate\s*of\s*origin|chứng\s*nhận\s*xuất\s*xứ',
 'certificate_of_quality':r'certificate\s*of\s*quality|quality\s*certificate|chứng\s*nhận\s*chất\s*lượng',
 'mill_test':r'mill\s*test(?:\s*certificate)?|inspection\s*certificate',
 'sales_contract':r'sales\s*contract|purchase\s*agreement|hợp\s*đồng\s*mua\s*bán',
 'technical_spec':r'technical\s*(?:specifications?|datasheet|spec)|(?:technical\s*)?data\s*sheet|user\s*manual|sổ\s*tay\s*hướng\s*dẫn\s*sử\s*dụng|hồ\s*sơ\s*kỹ\s*thuật(?:\s+[^:]{0,60})?|thông\s*số\s*kỹ\s*thuật',
 'product_catalogue':r'product\s*catalog(?:ue)?|product\s*guide|catalog(?:ue)?|brochure',
 'customs_declaration':r'customs\s*declaration|(?:bản xác nhận nội dung )?tờ\s*khai\s*hàng\s*hóa\s*(?:nhập|xuất)\s*khẩu(?:\s*.*)?',
}
STRUCTURAL={
 'commercial_invoice':{'invoice_number','unit_price','total_value'},
 'packing_list':{'gross_weight','net_weight','packages','packaging','total_packages','total_gross_weight'},
 'bill_of_lading':{'bl_number','port_of_loading','port_of_discharge'},
 'air_waybill':{'bl_number'}, 'certificate_of_origin':{'certificate_number','origin','origin_country'},
 'certificate_of_quality':{'certificate_number','material','specifications'},
 'sales_contract':{'contract_number','exporter','importer'},
 'technical_spec':{'model','part_number','function','specifications','construction'},
 'product_catalogue':{'model','part_number','name','specifications'},
 'mill_test':{'material','specifications','certificate_number'},
 'customs_declaration':{'declaration_number','declared_code'},
}


def classify_pages(pages, labels):
    evidence=[]; features=set(); titles=set(); legal_titles=[]; legal_structure=False
    for page_index,page in enumerate(pages):
        text=page.get('text',''); text_for_titles=re.sub(r'\b[A-Z]{1,3}\d+=','',text) if page.get('method','').startswith('xlsx') else text
        layout=page.get('layout') or build_layout(text,page.get('number',1))
        features.update(layout.get('schema_fields',[]))
        for relation in layout['key_values']:
            for metadata in (False,True):
                field=label_field(relation['label'],metadata)
                if field:features.add(field)
        for table in layout['tables']:
            features.update(h['field'] for h in table['header'] if h['field'])
            features.update(c['field']for r in table['rows']for c in r['cells']if c.get('field'))
        lines=[line.strip() for line in text_for_titles.splitlines() if line.strip()]
        # Formal headings, not words mentioned in a sentence or filename.
        for line_index,line in enumerate(lines[:12]):
            for kind,pattern in TITLES.items():
                if re.fullmatch(r'(?:'+pattern+r')(?:\s*(?:&|/|–|-)\s*packing list)?(?:\s*\([^)]*\))?(?:\s+date\s*:?.*)?',norm(line),re.I):
                    titles.add(kind);evidence.append({'kind':kind,'page':page.get('number',1),'quote':line,'signal':'heading','position':[page_index,line_index]})
            if re.search(r'^(?:danh\s*mục\s*hàng\s*hóa\s*xuất\s*khẩu|harmonized\s*(?:tariff|system)|thông\s*tư(?:\s*(?:số|ban hành))?|nghị\s*định(?:\s*số)?|quyết\s*định(?:\s*số)?|chú\s*giải\s*(?:HS|phân|chương))',norm(line),re.I):
                legal_titles.append({'page':page.get('number',1),'quote':line,'signal':'legal_heading','position':[page_index,line_index]})
        if re.search(r'\b\d+/\d{4}/(?:TT|NĐ)|\b\d{4}\.\d{2}\.\d{2}\b|\bchapter\s+\d+|\bsection\s+[IVX]+|điều\s+\d+',text,re.I):legal_structure=True
    first_legal=min((e['position'] for e in legal_titles),default=[float('inf'),0])
    first_business=min((e['position'] for e in evidence),default=[float('inf'),0])
    if legal_titles and legal_structure and first_legal<first_business:
        return _result('legal_reference',legal_titles,labels)
    eligible=[kind for kind in titles if features & STRUCTURAL.get(kind,set()) or ('name' in features and len(features)>1) or (kind=='packing_list' and len(features & {'invoice_number','shipper','consignee','port_of_loading','port_of_discharge'})>=2)]
    if not eligible:
        # No heading: require at least two document-specific fields, not one keyword.
        eligible=[k for k,keys in STRUCTURAL.items() if len(features & keys)>=2]
    if not eligible:return _result('other',evidence,labels)
    ranked=sorted(eligible,key=lambda k:(-len(features & STRUCTURAL.get(k,set())),k))
    best=ranked[0]
    return {**_result(best,[e for e in evidence if e.get('kind')==best]+[{'signal':'schema_fields','fields':sorted(features)}],labels),
            'alternatives':ranked[1:], 'classification_status':'needs_review' if len(ranked)>1 else 'supported'}


def _result(kind,evidence,labels):
    return {'kind':kind,'type':kind,'role':'legal_reference' if kind=='legal_reference' else 'unknown' if kind=='other' else None,
            'confidence':None,'signals':evidence,'status':'needs_review','label':labels.get(kind,kind),
            'classification_status':'unknown' if kind=='other' else 'supported'}
