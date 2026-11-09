"""Compatibility exports. Maintained dossier workflow lives in workspace_export."""
from __future__ import annotations
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

def dossier_pdf(res:dict,decision:dict|None=None)->bytes:
    from .workspace_export import case_pdf
    from .workspace import now
    candidates=[{'code':m['ma8'],'path':m.get('duong_dan',m.get('mo_ta',''))}for m in res.get('ma_de_xuat',[])]
    legacy_decision=('Người thao tác cũ ghi chọn '+str(decision.get('ma_chon'))+': '+str(decision.get('ly_do'))+'. Phiếu này chưa qua cổng duyệt SKU có căn cứ.') if decision else ''
    sku={'id':'legacy-sku','sku_code':'LEGACY-INPUT','name':'Mô tả từ API cũ','description':legacy_decision,'product_family':'general','revision':1,'status':'in_review','declared_code':None,'facts':[{'field':'name','value':res.get('dau_vao_an_danh',''),'status':'unverified','reviewer':None,'document_id':None,'page_number':None,'quote':'Đầu vào API cũ chưa có chứng từ xác minh.'}],'evidence':[],'decision':None,'analysis':{'engine_label':res.get('mo_hinh','Model lịch sử'),'engine': 'legacy','model_version':res.get('phien_ban_mo_hinh','unknown'),'input_hash':'Không có snapshot đầu vào có xác minh','candidates':candidates,'questions':[]}}
    case={'reference':str(res.get('ho_so_id','LEGACY')),'title':'Gợi ý HS8 từ API cũ - cần đối chiếu','owner':'Người yêu cầu','trade_type':'import','classification_date':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat(),'notes':'Điểm xếp hạng chưa phải xác suất đúng HS8. Chưa đối chiếu căn cứ, hiệu lực hoặc thuế suất.','skus':[sku],'documents':[],'events':[],'exported_at':now()}
    return case_pdf(case)

def audit_excel(df):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    wb=Workbook();ws=wb.active;ws.title='cap_can_doi_chieu';ws.append(list(df.columns))
    for row in df.itertuples(index=False,name=None):
        ws.append([None if v is None else str(v) for v in row])
        for c in ws[ws.max_row]:
            if isinstance(c.value,str):c.data_type='s'
    for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='24564D');c.alignment=Alignment(wrap_text=True)
    for i in range(1,ws.max_column+1):ws.column_dimensions[get_column_letter(i)].width=30
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;out=BytesIO();wb.save(out);return out.getvalue()
