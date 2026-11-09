"""Conservative semantic extraction, independent of PDF/OCR engines.

Only explicit labels and bounded item sections supply facts. Unknown identities
stay separate until a reviewer can link them; legal references never supply facts.
"""
import hashlib
import re
import unicodedata

PRODUCT = {'technical_spec', 'product_catalogue', 'mill_test'}
TRANSACTION = {'commercial_invoice', 'packing_list', 'bill_of_lading',
               'air_waybill', 'customs_declaration', 'sales_contract', 'certificate_of_origin'}


def role(doc):
    from .extractor import DocumentTypeDetector
    kind = DocumentTypeDetector.detect_type(doc)['kind']
    return 'legal_reference' if kind == 'legal_reference' else ('product_evidence' if kind in PRODUCT else ('transaction_evidence' if kind in TRANSACTION else 'unknown'))


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).split()).casefold()


MODEL = re.compile(r'\b(?:model|sku|part\s*(?:number|no\.?)|mã\s*(?:sản\s*phẩm|hàng)|kiểu\s*máy)\s*[:=\-]?\s*([A-Z0-9][A-Z0-9._/-]*\d[A-Z0-9._/-]*|[A-Z0-9]+-?[A-Z0-9]*)', re.I)
ITEM = re.compile(r'(?im)^\s*(?:item|sản\s*phẩm|mặt\s*hàng)\s*\d+\s*[:.]')
LABELS = {
    'name': r'tên\s*(?:và\s*bản\s*chất\s*hàng|sản\s*phẩm|hàng(?:\s*hóa)?)|product(?:\s*name)?|item(?:\s*description)?|description(?:\s*of\s*goods)?',
    'function': r'công\s*dụng(?:\s*chính)?|chức\s*năng|function|intended\s*use|application',
    'construction': r'cấu\s*tạo(?:\s*và\s*nguyên\s*lý)?|kết\s*cấu|construction|structure',
    'material': r'chất\s*liệu|vật\s*liệu|thành\s*phần|material|composition',
    'specifications': r'thông\s*số(?:\s*(?:kỹ\s*thuật|và\s*kích\s*thước))?|rated\s*power|power(?:\s*consumption)?|công\s*suất|điện\s*áp|tần\s*số|voltage|frequency',
    'packaging': r'quy\s*cách\s*đóng\s*gói|đóng\s*gói|packaging',
    'manufacturing': r'quy\s*trình\s*sản\s*xuất|manufacturing',
    'condition': r'tình\s*trạng|condition',
    'origin': r'xuất\s*xứ|country\s*of\s*origin',
}


def segments(text):
    items = list(ITEM.finditer(text))
    anchors = items if items else list(MODEL.finditer(text))
    if not anchors:
        anchors = list(re.finditer(r'(?im)^\s*(?:product\s*name|tên\s*(?:sản\s*phẩm|hàng))\s*[:=]', text))
    if len(anchors) <= 1:
        return [text]
    starts = [text.rfind('\n', 0, m.start()) + 1 for m in anchors]
    starts = sorted(set(starts))
    return [text[start:(starts[i+1] if i+1 < len(starts) else len(text))] for i, start in enumerate(starts)]


def extract(docs, make_fact):
    entities = {}
    for doc in sorted(docs, key=lambda d: (d.get('sha256', ''), d.get('name', ''))):
        if role(doc) not in {'product_evidence', 'transaction_evidence'}:
            continue
        for page in doc.get('pages', []):
            text = page.get('text', '')
            table_rows = []
            header = None
            for line in text.splitlines():
                cells = [c.strip() for c in re.split(r'\s*\|\s*|\t|\s{2,}', line.strip())]
                if len(cells) > 1 and any(re.fullmatch(r'sku|model|part number', c, re.I) for c in cells):
                    header = [c.casefold() for c in cells]
                elif header and len(cells) == len(header):
                    table_rows.append((line, dict(zip(header, cells))))
            sections = [(s, None) for s in segments(text)] if not table_rows else table_rows
            for index, (section, row) in enumerate(sections):
                model = MODEL.search(section) or re.search(r'(?m)^\s*([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+)\s*(?:\||$)', section)
                values = []
                for field, labels in LABELS.items():
                    for match in re.finditer(r'(?im)^\s*(?:' + labels + r')[ \t]*(?:[:=][ \t]*|\n\s*)([^\n|]+)', section):
                        values.append((field, match.group(1).strip(), match.group(0).strip()))
                if row:
                    for column, value in row.items():
                        field = 'name' if column in {'description', 'product name', 'item description'} else ('specifications' if column in {'power', 'voltage', 'specifications'} else None)
                        if field and value: values.append((field, value, section.strip()))
                    row_code = next((row[k] for k in ('sku', 'model', 'part number') if row.get(k)), None)
                else:
                    row_code = None
                if not model and not row_code and not any(f == 'name' for f, _, _ in values):
                    continue
                code = row_code or (model.group(1).strip('.,') if model else None)
                key = code.casefold() if code else f"{doc['id']}:{page.get('number', 1)}:{index}"
                sku = entities.get(key)
                if sku is None:
                    identifier = 'cand_' + hashlib.sha256(key.encode()).hexdigest()[:12]
                    name = next((v for f, v, _ in values if f == 'name'), '')
                    # An item line itself is explicit description evidence.
                    if not name:
                        item = re.search(r'(?im)^\s*item\s*\d*\s*:\s*([^\n]+)', section)
                        if item:
                            name = item.group(1).strip()
                            values.append(('name', name, item.group(0).strip()))
                    sku = dict(id=identifier, sku_code=code or identifier, name=name,
                               description=name, product_family='general', declared_code=None,
                               facts=[], source_document_id=doc['id'], source_page=page.get('number', 1),
                               status='needs_review', identity_status='explicit_model' if code else 'needs_review')
                    entities[key] = sku
                # Inline numerical ratings remain exact evidence, without invented descriptions.
                if not any(f == 'specifications' for f, _, _ in values):
                    for line in section.splitlines():
                        if re.search(r'\b\d+(?:[.,]\d+)?\s*(?:W|V|Hz|mm|nm)\b', line, re.I):
                            values.append(('specifications', line.strip(), line.strip()))
                hs = re.search(r'(?:HS\s*(?:code)?|mã\s*HS)\s*[:=]\s*(\d{4}\.?\d{2}\.?\d{2})\b', section, re.I)
                if hs:
                    values.append(('declared_code', hs.group(1), hs.group(0)))
                for field, value, quote in values:
                    if normalized(value) not in normalized(quote) or normalized(quote) not in normalized(section):
                        continue
                    fact = make_fact(field, value, doc['id'], doc['name'], page.get('number', 1), quote)
                    fact.update(field_name=field, sku_id=sku['id'], source_document_id=doc['id'],
                                source_page=page.get('number', 1), source_quote=quote,
                                source_kind='document_extracted', extraction_status='extracted', source_valid=True,
                                extraction_method=page.get('method', 'text') + ':explicit_section')
                    if field == 'origin':
                        sku.setdefault('origin_sources', []).append(fact)
                        continue
                    if field == 'declared_code':
                        fact['value'] = value.replace('.', '')
                        sku['declared_code'] = fact['value']
                        sku.setdefault('declared_code_sources', []).append(fact)
                        continue
                    if not any(f['field'] == field and f['value'] == value and f['document_id'] == doc['id'] and f['page_number'] == fact['page_number'] for f in sku['facts']):
                        sku['facts'].append(fact)
                    if field == 'name' and not sku['name']:
                        sku['name'] = value
    for sku in entities.values():
        for field in LABELS:
            facts = [f for f in sku['facts'] if f['field'] == field]
            if field != 'specifications' and len({normalized(f['value']) for f in facts}) > 1:
                for fact in facts:
                    fact.update(status='conflict', extraction_status='conflicting')
        spec_facts = [f for f in sku['facts'] if f['field'] == 'specifications']
        for unit in ('W', 'V', 'Hz'):
            amounts = {m.group(1).replace(',', '.') for f in spec_facts for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*' + unit + r'\b', f['value'], re.I)}
            if len(amounts) > 1:
                for fact in spec_facts:
                    fact.update(status='conflict', extraction_status='conflicting')
        sku['missing_fields'] = [f for f in ('name', 'function', 'construction', 'specifications') if not any(x['field'] == f for x in sku['facts'])]
    return sorted(entities.values(), key=lambda s: s['sku_code'].casefold())
