"""Physical PDF cell boundaries + Poppler word evidence; no commodity-specific rules.

Optional pdfplumber is used only for ruled table geometry. Values come from the
same Poppler word layer as the page text, and must survive source validation.
"""
from __future__ import annotations
import re
from .document_layout import column,norm


def _label(text):
    text=re.sub(r'\([^)]*\)','',text)
    label=column(text)
    if label:return label
    compact=re.sub(r'[\s.\-:#]+','',norm(text))
    from .document_layout import COLUMNS
    return next((key for key,aliases in COLUMNS.items() if any(compact==re.sub(r'[\s.\-:#]+','',norm(a)) for a in aliases)),None)


def _content(box,words):
    if box is None:return '',[]
    selected=[w for w in words if box[0]-.5<=(w['bbox'][0]+w['bbox'][2])/2<=box[2]+.5 and box[1]-.5<=(w['bbox'][1]+w['bbox'][3])/2<=box[3]+.5 and w['bbox'][1]>=box[1]-1 and w['bbox'][3]<=box[3]+1]
    lines=[]
    for word in sorted(selected,key=lambda w:(w['bbox'][1],w['bbox'][0])):
        h=word['bbox'][3]-word['bbox'][1]
        line=next((line for line in lines if abs(line[0]['bbox'][1]-word['bbox'][1])<=max(2,h*.35)),None)
        if line is None:lines.append([word])
        else:line.append(word)
    fragments=[' '.join(w['text'] for w in sorted(line,key=lambda w:w['bbox'][0])) for line in lines]
    return ' '.join(fragments),fragments


def extract_pdf_tables(path,number,words,text,context=None):
    try:import pdfplumber
    except ImportError:return []
    if not words:return []
    context=context if context is not None else {}
    from .document_layout import build_layout
    blocks=build_layout(text,number)['blocks'];result=[]
    with pdfplumber.open(path,pages=[number]) as pdf:
        page=pdf.pages[0]
        if len(page.edges)<4:return []
        for physical in page.find_tables():
            raw=[]
            for row in physical.rows:
                raw.append([{'text':_content(box,words)[0],'fragments':_content(box,words)[1],'bbox':box} for box in row.cells])
            header_index=next((i for i,row in enumerate(raw) if sum(bool(_label(c['text'])) for c in row)>=2 and any(_label(c['text']) in {'name','model','part_number'} for c in row)),None)
            continuation=False
            if header_index is None:
                previous=context.get('previous')
                if not previous or previous['page']!=number-1 or not raw or len(raw[0])!=len(previous['header']):continue
                if any(c['bbox'] and h.get('bbox') and (abs(c['bbox'][0]-h['bbox'][0])>3 or abs(c['bbox'][2]-h['bbox'][2])>3) for c,h in zip(raw[0],previous['header'])):continue
                header_index=-1;continuation=True
            header=[{'text':c['text'],'field':_label(c['text']),'column':i,'bbox':c['bbox']}for i,c in enumerate(raw[header_index])]
            if continuation:header=[dict(h)for h in context['previous']['header']]
            # Hierarchical headers may place NET/GROSS below a spanning parent.
            body=header_index+1
            while body<len(raw):
                row=raw[body]
                numeric=any(re.fullmatch(r'\d[\d,. ]*',c['text']) for c in row if c['text'])
                if numeric:break
                recognized=[_label(c['text']) for c in row]
                if any(recognized):
                    for h,c,field in zip(header,row,recognized):
                        if field:h.update(text=c['text'],field=field)
                        elif h['field']=='quantity' and c['text'] in {'PCS','PC','KG','KGM','SET','BAGS','CTN'}:h['unit_literal']=c['text']
                # Non-numeric subheadings are retained as header, never merchandise.
                body+=1
            if body==len(raw):continue
            # Empty ruled currency column can be identified by explicit ISO values.
            for j,h in enumerate(header):
                values=[r[j]['text'] for r in raw[body:] if j<len(r) and r[j]['text']]
                if not h['field'] and values and all(v in {'USD','EUR','JPY','VND','CNY','GBP','SGD'} for v in values):h['field']='currency'
            table={'id':f'g{len(result)}','page':number,'header':header,'header_block_id':None,'header_block_ids':[],
                   'rows':[],'totals':[],'continuation':continuation,'header_source_page':context['previous']['header_source_page'] if continuation else number,'bbox':list(physical.bbox),'method':'pdf_ruled_cells','shared_cells':[]}
            boundaries={c['bbox'][1] for row in raw[body+1:] for c in row if c['bbox']}
            for word in words:
                x=(word['bbox'][0]+word['bbox'][2])/2
                if physical.bbox[0]<=x<=physical.bbox[2] and any(word['bbox'][1]+1<y<word['bbox'][3]-1 for y in boundaries):
                    table['shared_cells'].append({'field':'unassigned','text':word['text'],'bbox':word['bbox']})
            for index in range(body,len(raw)):
                row=raw[index]
                mapped={h['field']:c['text'] for h,c in zip(header,row) if h['field'] and c['text']}
                if any(norm(c['text']) in {'total','subtotal','grand total'} for c in row) or (sum(bool(c['text']) for c in row)<=2 and any(re.match(r'^(?:grand |sub)?total\b',norm(c['text']))for c in row)):
                    table['totals'].append({'values':mapped});break
                if not any(mapped.get(f) for f in ('name','model','part_number')):continue
                if not any(re.search(r'\d',mapped.get(f,'')) for f in ('quantity','amount','unit_price','net_weight','gross_weight','model','part_number')):continue
                y0=min(c['bbox'][1]for c in row if c['bbox']);y1=min(c['bbox'][3]for c in row if c['bbox'] and abs(c['bbox'][1]-y0)<1)
                # A source quote covers original full text lines intersecting the row.
                rowwords=[w for w in words if y0-.5<=(w['bbox'][1]+w['bbox'][3])/2<=y1+.5]
                line_fragments=_content((0,y0, float(page.width),y1),rowwords)[1]
                matched=[b for b in blocks if any(norm(f) in norm(b['text']) or (norm(b['text']) in norm(f) and len(norm(b['text']))>2) for f in line_fragments)]
                # Match by individual cell fragments if full lines differ in spacing.
                if not matched:
                    fragments=[f for c in row for f in c['fragments']]
                    matched=[b for b in blocks if any(norm(f) in norm(b['text'])for f in fragments if len(norm(f))>2)]
                if not matched:continue
                start=min(b['start']for b in matched);end=max(b['end']for b in matched)
                record={'id':f"{table['id']}r{len(table['rows'])}",'page':number,'start':start,'end':end,'quote':text[start:end],
                        'block_ids':[b['id']for b in matched],'bbox':[physical.bbox[0],y0,physical.bbox[2],y1],'cells':[]}
                for h,c in zip(header,row):
                    if not c['text'] or not h['field']:continue
                    box=c['bbox']
                    # Merged value cells spanning more than one physical row are
                    # unassigned, rather than copied into the first SKU's weight.
                    if box and (box[3]>y1+1 or any(box==other[h['column']]['bbox'] for other in raw[index+1:] if h['column']<len(other))):
                        table['shared_cells'].append({'field':h['field'],'text':c['text'],'bbox':list(box)});continue
                    value=c['text'];fragments=c['fragments']
                    if not all(norm(f) in norm(record['quote']) for f in fragments):continue
                    cell={'field':h['field'],'text':value,'column':h['column'],'header':h['text'],'bbox':list(box),'value_fragments':fragments,'source_block_id':matched[0]['id']}
                    if h.get('unit_literal'):
                        cell['header_unit']=h['unit_literal'];cell['unit_quote']=h['unit_literal']
                    unit=re.search(r'\(([^)]+)\)',h['text'])
                    if unit:
                        literal=unit.group(1).strip();pattern=r'\(\s*'+r'\s*'.join(re.escape(token) for token in literal.split())+r'\s*\)'
                        match=re.search(pattern,text)
                        if match:cell['header_unit']=literal;cell['unit_quote']=match.group(0)
                    record['cells'].append(cell)
                if record['cells']:table['rows'].append(record)
            if table['rows']:
                header_fragments=[f for row in raw[max(0,header_index):body] for c in row for f in c['fragments']]
                first=min(r['start']for r in table['rows'])
                table['header_block_ids']=[b['id']for b in blocks if b['end']<=first and any(len(norm(f))>=4 and norm(f) in norm(b['text']) for f in header_fragments)]
                result.append(table)
                context['previous']={'page':number,'header_source_page':table['header_source_page'],'header':header}
    return result
