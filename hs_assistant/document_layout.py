"""Page-local intermediate representation. Text offsets are exact, never inferred boxes.

PDF geometry comes only from Poppler bbox XML; plain text has bbox=None.
The same IR is used in draft extraction and in persisted document processing.
"""
from __future__ import annotations
import re
from functools import lru_cache
import subprocess
import shutil
import unicodedata
from xml.etree import ElementTree


def norm(value):
    return ' '.join(unicodedata.normalize('NFC', str(value)).split()).casefold()


# Semantic column aliases, independent of industry and SKU values.
COLUMNS = {
    'model': ('model', 'model no', 'sku', 'sku code', 'item code', 'product code', 'mã hàng', 'mã sản phẩm'),
    'part_number': ('part number', 'part no', 'art no', 'article no', 'item no', 'p/n', 'pn'),
    'name': ('description', 'goods description', 'description of goods', 'item description', 'product name', 'commodity', 'name of goods', 'tên hàng', 'mô tả hàng hóa'),
    'quantity': ('quantity', 'qty', 'số lượng'),
    'unit': ('unit', 'uom', 'đơn vị', 'đvt'),
    'unit_price': ('unit price', 'price/unit', 'u.price', 'đơn giá'),
    'amount': ('amount', 'line total', 'total amount', 'thành tiền', 'trị giá', 'total value'),
    'currency': ('currency', 'ccy', 'tiền tệ'),
    'gross_weight': ('gross weight', 'g.w.', 'gw', 'trọng lượng cả bì'),
    'net_weight': ('net weight', 'n.w.', 'nw', 'trọng lượng tịnh'),
    'packages': ('packages', 'cartons', 'no of packages', 'số kiện', 'no. of pkgs', 'no. of pkg.'),
    'origin': ('country of origin', 'origin', 'xuất xứ'),
    'material': ('material', 'composition', 'chất liệu', 'thành phần'),
    'specifications': ('specifications', 'technical specifications', 'power', 'voltage', 'frequency', 'size', 'dimensions', 'công suất', 'điện áp'),
    'declared_code': ('hs code', 'h.s. code', 'hs', 'mã hs'),
    'line_number': ('no', 'no.', 'item', 'line', 'stt'),
}


def column(value):
    label = norm(value).strip(' .:')
    return next((key for key, aliases in COLUMNS.items() if label in {norm(a).strip(' .:') for a in aliases}), None)


def cells(line):
    """Keep cell positions for source links, including empty delimited cells."""
    delimiter = r'\|' if '|' in line else (r'\t' if '\t' in line else r' {2,}')
    parts = []
    start = 0
    for match in re.finditer(delimiter, line):
        parts.append({'text': line[start:match.start()].strip(), 'start': start, 'end': match.start()})
        start = match.end()
    parts.append({'text': line[start:].strip(), 'start': start, 'end': len(line)})
    if delimiter == r' {2,}':
        parts=[p for p in parts if p['text']]
    return parts


@lru_cache(maxsize=1)
def _label_pattern():
    from .document_schema import PRODUCT_FIELDS,DOSSIER_FIELDS
    aliases=sorted({a.rstrip('.')for fields in (PRODUCT_FIELDS,DOSSIER_FIELDS)for values in fields.values()for a in values},key=len,reverse=True)
    return re.compile(r'(?<!\w)('+ '|'.join(re.escape(a).replace(r'\ ',r'\s+')for a in aliases)+r')\s*[:=]\s*',re.I)


def parse_tables(blocks,text,document_id,page_number):
    tables=[];used=set();active=None;pending=[]
    def attach(row,continuations):
        for block,parsed in continuations:
            row.setdefault('continuations',[]).extend({**c,'field':'name','header':next((h['text'] for h in active['header'] if h['field']=='name'),'Description'),'column':next((h['column'] for h in active['header'] if h['field']=='name'),0),'source_block_id':block['id']} for c in parsed if c['text'])
            row['block_ids'].append(block['id']);row['end']=block['end']
        row['quote']=text[row['start']:row['end']]
        if continuations:row['layout_status']='needs_review'
    def finish():
        nonlocal pending
        if active and active['rows'] and pending:attach(active['rows'][-1],pending)
        pending=[]
    for block in blocks:
        parsed=cells(block['text']);semantics=[column(c['text']) for c in parsed]
        header=len([x for x in semantics if x])>=2 and any(x in {'name','model','part_number'} for x in semantics)
        if header:
            finish()
            active={'id':f't{len(tables)}','document_id':document_id,'page':page_number,
                    'header':[{'text':c['text'],'field':sem,'column':i,'start':c['start'],'end':c['end']} for i,(c,sem) in enumerate(zip(parsed,semantics))],
                    'header_block_id':block['id'],'header_block_ids':[block['id']],'rows':[],'totals':[],'delimited':'|' in block['text'] or '\t' in block['text']}
            tables.append(active);used.add(block['id']);continue
        if not active:continue
        # Multi-line headers: NET / WEIGHT / (KGM), QUANTITY / (BAGS).
        if not active['rows'] and not pending and parsed and all(re.fullmatch(r'weight|net|gross|\([\w /³²]+\)',norm(c['text'])) for c in parsed):
            for cell in parsed:
                h=min(active['header'],key=lambda h:abs((h['start']+h['end'])/2-(cell['start']+cell['end'])/2))
                h['text']+=' '+cell['text']
                joined=re.sub(r'\([^)]*\)','',norm(h['text'])).strip()
                h['field']=column(joined)
                unit=re.fullmatch(r'\(([^)]+)\)',cell['text'])
                if unit:h['unit_hint']={'value':unit.group(1),'quote':cell['text'],'block_id':block['id']}
            active['header_block_ids'].append(block['id']);used.add(block['id']);continue
        if active['delimited']:
            if len(parsed)!=len(active['header']):finish();active=None;continue
            paired=list(zip(active['header'],parsed))
        else:
            paired=[]
            for cell in parsed:
                h=min(active['header'],key=lambda h:abs((h['start']+h['end'])/2-(cell['start']+cell['end'])/2))
                paired.append((h,cell))
        mapped={h['field']:c['text'] for h,c in paired if h['field'] and c['text']}
        if norm(mapped.get('name','')) in {'total','grand total','subtotal'}:
            finish();active['totals'].append({'quote':block['text'],'block_id':block['id'],'values':mapped});used.add(block['id']);active=None;continue
        if any(field in mapped and not re.match(r'^[0-9]',mapped[field]) for field in ('quantity','unit_price','amount','gross_weight','net_weight')):
            finish();active=None;continue
        has_values=any(mapped.get(f) for f in ('model','part_number','quantity','unit_price','amount','gross_weight','net_weight','specifications'))
        if not has_values and mapped and set(mapped)<={'name'}:
            if active['delimited'] and active['rows']:
                # Preserve all column slots for explicit wrapped delimited rows.
                row=active['rows'][-1];row.setdefault('continuations',[]).extend({**c,'field':h['field'],'header':h['text'],'column':h['column'],'source_block_id':block['id']} for h,c in paired)
                row['block_ids'].append(block['id']);row['end']=block['end'];row['quote']=text[row['start']:row['end']]
            else:pending.append((block,parsed))
            used.add(block['id']);continue
        if not has_values:finish();active=None;continue
        row={'id':f"{active['id']}r{len(active['rows'])}",'document_id':document_id,'page':page_number,
             'start':block['start'],'end':block['end'],'quote':block['text'],'block_ids':[block['id']],
             'cells':[{**c,'field':h['field'],'header':h['text'],'column':h['column'],'source_block_id':block['id'],'unit_hint':h.get('unit_hint')} for h,c in paired]}
        if pending:
            namecell=next((c for c in row['cells'] if c['field']=='name'),None)
            previous_names=[c['text'] for _,pcs in pending for c in pcs if c['text']]
            if namecell and previous_names:
                continuation={**namecell};namecell['text']=previous_names[0]
                row['continuations']=[{**namecell,'text':value} for value in previous_names[1:]]+[continuation]
            elif previous_names:
                row['cells'].append({'field':'name','header':'Description','column':0,'text':previous_names[0],'source_block_id':pending[0][0]['id']})
                row['continuations']=[{**row['cells'][-1],'text':value} for value in previous_names[1:]]
            row['start']=pending[0][0]['start'];row['block_ids']=[b['id'] for b,_ in pending]+row['block_ids'];pending=[]
            row['quote']=text[row['start']:row['end']];row['layout_status']='needs_review'
        active['rows'].append(row);used.add(block['id'])
    finish()
    return tables,used


def build_layout(text, page_number=1, document_id=None, geometry=None, table_geometry=None):
    blocks = []
    offset = 0
    for index, raw in enumerate(text.splitlines(keepends=True)):
        value = raw.rstrip('\r\n\f')
        if value.strip():
            blocks.append({'id': f'b{index}', 'text': value, 'start': offset, 'end': offset+len(value),
                           'document_id': document_id, 'page': page_number, 'bbox': None})
        offset += len(raw)
    tables = []
    active = None
    key_values = []
    used = set()
    tables,used=parse_tables(blocks,text,document_id,page_number)
    if table_geometry:
        tables=table_geometry
        used={b for t in tables for r in t['rows'] for b in r['block_ids']}
        # Table headers cannot become name/value relations in a narrative fallback.
        for table in tables:
            first=min(r['start'] for r in table['rows'])
            used.update(b['id'] for b in blocks if b['end']<first and any(norm(h['text']).replace(' ','') in norm(b['text']).replace(' ','') for h in table['header'] if h['text']))
    for index,block in enumerate(blocks):
        parsed=cells(block['text'])
        for cell_index,cell in enumerate(parsed):
            labelled=list(_label_pattern().finditer(cell['text']))
            if len(labelled)>1:
                for index,label in enumerate(labelled):
                    stop=labelled[index+1].start()if index+1<len(labelled)else len(cell['text'])
                    value=cell['text'][label.end():stop].strip()
                    if value:key_values.append({'label':label.group(1),'value':value,'quote':cell['text'][label.start():stop].strip(),'block_ids':[block['id']],'start':block['start']+cell['start']+label.start(),'end':block['start']+cell['start']+stop})
                continue
            match=re.match(r'^\s*([^:=|]{2,70})\s*[:=]\s*(.*?)\s*$',cell['text'])
            if not match:
                from .document_schema import label_field
                label=cell['text'].rstrip(' :.')
                if label_field(label,True) and cell_index+1<len(parsed):
                    right=parsed[cell_index+1]
                    if not label_field(right['text'],True) and not label_field(right['text']):
                        key_values.append({'label':label,'value':right['text'],'quote':block['text'][cell['start']:right['end']], 'block_ids':[block['id']],'start':block['start']+cell['start'],'end':block['start']+right['end']})
                        continue
            if not match:
                # Common document labels use a full stop or a gap, not a colon.
                match=re.match(r'^\s*((?:invoice|inv|contract|b/l|bl|awb)\s*(?:no|number)\.?|date|no\.)\s+(.+?)\s*$',cell['text'],re.I)
            if not match:continue
            label=match.group(1).strip();value=match.group(2).strip()
            if value:
                key_values.append({'label':label,'value':value,'quote':cell['text'],'block_ids':[block['id']], 'start':block['start']+cell['start'],'end':block['start']+cell['end']})
            elif index+1<len(blocks):
                following=blocks[index+1];next_cells=cells(following['text'])
                if not next_cells:continue
                center=(cell['start']+cell['end'])/2
                chosen=min(next_cells,key=lambda c:abs((c['start']+c['end'])/2-center))
                # Header/value column association is explicit; mark alignment review.
                key_values.append({'label':label,'value':chosen['text'],
                                   'quote':text[block['start']:following['end']].strip(),
                                   'block_ids':[block['id'],following['id']], 'start':block['start'],'end':following['end'],'layout_status':'needs_review'})
    # Label-only heading relations are candidates; schema authorizes labels later.
    for i, block in enumerate(blocks[:-1]):
        following=blocks[i+1]
        if block['id'] not in used and following['id'] not in used and ':' not in block['text'] and '=' not in block['text'] and len(block['text'].strip()) < 70:
            key_values.append({'label':block['text'].strip(),'value':following['text'].strip(),
                               'quote':text[block['start']:following['end']].strip(),
                               'block_ids':[block['id'],following['id']], 'start':block['start'],'end':following['end']})
    from .document_schema import label_field
    schema_fields=list({f for b in blocks for c in cells(b['text']) for f in (label_field(c['text'].strip(' :.'),True),label_field(c['text'].strip(' :.'))) if f})
    return {'schema_fields':schema_fields,'version':1,'document_id':document_id,'page':page_number,'blocks':blocks,'tables':tables,
            'key_values':key_values,'geometry':geometry or [],'geometry_status':'available' if geometry else 'not_available',
            'warnings':([{'stage':'layout','status':'needs_review','message':'Ô gộp dùng chung nhiều dòng; không tự gán giá trị chung cho một SKU.'}] if any(t.get('shared_cells')for t in tables)else []) if text.strip() else [{'stage':'text_extraction','status':'missing','message':'No readable text on page'}]}


def pdf_geometry(path, page):
    """Use existing Poppler, no OCR engine/model download or network access."""
    if not shutil.which('pdftotext'): return []
    try:
        result=subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-bbox-layout',str(path),'-'],capture_output=True,text=True,timeout=20)
        if result.returncode: return []
        root=ElementTree.fromstring(result.stdout)
        return [{'text':e.text or '', 'bbox':[float(e.attrib[k]) for k in ('xMin','yMin','xMax','yMax')]}
                for e in root.iter() if e.tag.rsplit('}',1)[-1]=='word']
    except (ValueError,ElementTree.ParseError,subprocess.SubprocessError,OSError):
        return []


def ensure_layout(doc):
    previous=None
    for page in doc.get('pages', []):
        number=page.get('number') or page.get('page_number',1)
        page['number']=number
        layout=page.get('layout')
        if not isinstance(layout,dict) or layout.get('version') != 1:
            layout=build_layout(page.get('text',''), number,geometry=page.get('geometry'),table_geometry=page.get('pdf_tables'))
        # Carry a header only across adjacent pages of the SAME document, and
        # only for rows structurally compatible with that header. Flag review.
        if not layout['tables'] and previous and previous['page']==number-1 and previous['tables']:
            prior=previous['tables'][-1]
            header=prior['header']; rows=[]
            for block in layout['blocks']:
                parsed=cells(block['text'])
                if len(parsed)!=len(header) or len(parsed)<3:continue
                mapped={h['field']:c['text'] for h,c in zip(header,parsed) if h['field'] and c['text']}
                if not any(mapped.get(f) for f in ('model','part_number','name')):continue
                if 'quantity' in mapped and not re.fullmatch(r'[0-9.,]+(?:\s+\w+)?',mapped['quantity']):continue
                rows.append({'id':f't0r{len(rows)}','document_id':doc['id'],'page':number,
                             'quote':page['text'][block['start']:block['end']], 'start':block['start'],'end':block['end'], 'block_ids':[block['id']],
                             'cells':[{**c,'field':h['field'],'column':h['column'],'header':h['text'],'source_block_id':block['id']} for h,c in zip(header,parsed)]})
            if rows:
                layout['tables']=[{'id':'t0','document_id':doc['id'],'page':number,'header':header,
                                   'header_block_id':None,'header_source_page':prior.get('header_source_page',previous['page']),
                                   'continuation':True,'rows':rows}]
                layout['warnings'].append({'stage':'layout','status':'needs_review','message':'Table header continued from previous page; verify column alignment'})
        layout['document_id']=doc['id'];layout['page']=number
        for block in layout['blocks']:
            block.update(document_id=doc['id'],page=number)
        for table in layout['tables']:
            table.update(document_id=doc['id'],page=number)
            for row in table['rows']:row.update(document_id=doc['id'],page=number)
        page['layout']=layout
        previous=layout
    return doc
