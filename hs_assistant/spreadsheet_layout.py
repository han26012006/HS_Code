"""Cell-based form extraction. Keep original coordinates and sheet quotes.

Supports label/value pairs and repeated product sections, including customs
forms. Does not interpret workbook formulas, macros, tariffs, or legal appendices.
"""
import re
from .document_layout import build_layout,norm
from .document_schema import label_field,hs_code

FORM_LABELS={'mô tả hàng hóa':'name','mã số hàng hóa':'declared_code','nước xuất xứ':'origin',
             'số lượng (1)':'quantity','đơn giá hóa đơn':'unit_price','trị giá hóa đơn':'amount'}


def sheet_page(sheet,number):
    lines=[f'[{sheet.title}]'];rows=[]
    for row in sheet.iter_rows():
        values=[{'cell':c.coordinate,'value':str(c.value).strip(),'column':c.column}for c in row if c.value is not None and str(c.value).strip()]
        if not values:continue
        text=' | '.join(f"{c['cell']}={c['value']}"for c in values)
        start=sum(len(s)+1 for s in lines)
        lines.append(text);rows.append({'values':values,'start':start,'end':start+len(text),'text':text})
    text='\n'.join(lines);layout=build_layout(text,number);relations=[];products=[]
    for i,row in enumerate(rows):
        values=row['values']
        for j,cell in enumerate(values):
            label=norm(cell['value']).strip(' :');field=label_field(label,True)
            if not field:continue
            next_cell=values[j+1]if j+1<len(values)else None
            if next_cell and (label_field(next_cell['value'],True) or norm(next_cell['value']) in FORM_LABELS):next_cell=None
            if next_cell and not re.search(r'\w',next_cell['value']):next_cell=None
            if field in {'invoice_number','bl_number','contract_number','certificate_number','declaration_number'} and next_cell and not re.search(r'\d',next_cell['value']):next_cell=None
            if field=='bl_number' and not next_cell:
                for following in rows[i+1:i+3]:
                    next_cell=next((c for c in following['values'] if cell['column']<=c['column']<=cell['column']+8 and re.fullmatch(r'[A-Za-z0-9./_-]{5,}',c['value']) and re.search(r'\d',c['value'])),None)
                    if next_cell:break
            # Role sections hold Name/Tên on a following row, not an adjacent role label.
            if not next_cell and field in {'exporter','importer','shipper','consignee'}:
                for following in rows[i+1:i+5]:
                    if any(label_field(c['value'],True)for c in following['values']):break
                    name_index=next((k for k,c in enumerate(following['values'])if norm(c['value'])in {'tên','name'}),None)
                    if name_index is not None and name_index+1<len(following['values']):
                        next_cell=following['values'][name_index+1];break
            if next_cell:
                end=next((r['end']for r in rows if next_cell in r['values']),row['end'])
                relations.append({'label':cell['value'],'value':next_cell['value'],'quote':text[row['start']:end],
                                  'start':row['start'],'end':end,'block_ids':[b['id']for b in layout['blocks']if row['start']<=b['start']<end],
                                  'source_cells':[cell['cell'],next_cell['cell']]})
        if any(norm(c['value'])=='mô tả hàng hóa'for c in values):
            name_index=next(j for j,c in enumerate(values)if norm(c['value'])=='mô tả hàng hóa')
            if name_index+1<len(values) and not label_field(values[name_index+1]['value'],True):products.append(i)
    if products:
        table={'id':'sheet_products','page':number,'header':[],'header_block_id':None,'rows':[],'method':'worksheet_label_value'}
        for k,index in enumerate(products):
            start=rows[max(0,index-1)]['start'];end=rows[products[k+1]-1]['start']if k+1<len(products)else len(text);fields=[]
            for row in rows:
                if not start<=row['start']<end:continue
                cells=row['values']
                for j,cell in enumerate(cells):
                    field=FORM_LABELS.get(norm(cell['value']))
                    if not field or j+1>=len(cells):continue
                    val=cells[j+1]
                    if norm(val['value'])in FORM_LABELS:continue
                    value=val['value']
                    if field=='declared_code' and not hs_code(value):continue
                    fields.append({'field':field,'text':value,'column':cell['column'],'header':cell['value'],
                                   'source_cells':[cell['cell'],val['cell']],'source_block_id':next((b['id']for b in layout['blocks']if b['start']==row['start']),None)})
                    if field=='quantity' and j+2<len(cells):
                        unit=cells[j+2]
                        if re.fullmatch(r'[A-Za-z]{1,6}',unit['value']):fields.append({'field':'unit','text':unit['value'],'column':unit['column'],'header':'Đơn vị trong dòng số lượng','source_cells':[unit['cell']],'source_block_id':None})
            if any(f['field']=='name'for f in fields):
                table['rows'].append({'id':f'sheet_products_r{k}','page':number,'start':start,'end':end,'quote':text[start:end],
                                      'block_ids':[b['id']for b in layout['blocks']if start<=b['start']<end],'cells':fields})
        layout['tables']=[table]
    layout['schema_fields']=list({field for row in rows for cell in row['values'] for field in [label_field(cell['value'],True),FORM_LABELS.get(norm(cell['value']))] if field})
    layout['key_values']=relations
    return {'number':number,'text':text,'method':'xlsx_cells','layout':layout,'sheet_name':sheet.title}
