"""Portable dossier exports. Preserve provenance; internal approvals are never gold."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from .workspace import FIELDS

STATUS={'draft':'Mới tạo','collecting':'Đang bổ sung','in_review':'Chờ đối chiếu','approved':'Đã duyệt nội bộ','returned':'Yêu cầu bổ sung','verified':'Đã kiểm tra','unverified':'Chưa kiểm tra','conflict':'Mâu thuẫn'}

def case_pdf(case):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    font=Path(__file__).parent/'fonts'
    for name,file in [('HSRegular','DejaVuSans.ttf'),('HSBold','DejaVuSans-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(font/file)))
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=57,bottomMargin=48,title=case['reference']+' - Hồ sơ phân loại',author='HS Workspace')
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='HSBody',fontName='HSRegular',fontSize=8,leading=13,textColor=colors.HexColor('#455b65'),spaceAfter=7,wordWrap='CJK'))
    styles.add(ParagraphStyle(name='HSSmall',parent=styles['HSBody'],fontSize=6.7,leading=10,textColor=colors.HexColor('#829198')))
    styles.add(ParagraphStyle(name='HSTitle',parent=styles['HSBody'],fontName='HSBold',fontSize=19,leading=26,spaceAfter=14,textColor=colors.HexColor('#193f44')))
    styles.add(ParagraphStyle(name='HSHead',parent=styles['HSBody'],fontName='HSBold',fontSize=11,leading=16,spaceBefore=15,spaceAfter=9,keepWithNext=True,textColor=colors.HexColor('#216955')))
    def p(text,style='HSBody'):return Paragraph(escape(str(text or '—')).replace('\n','<br/>'),styles[style])
    story=[p('HỒ SƠ PHÂN LOẠI NỘI BỘ','HSSmall'),p(case['title'],'HSTitle'),p(f"{case['reference']} | {'Nhập khẩu' if case['trade_type']=='import' else 'Xuất khẩu'} | Ngày phân loại: {case['classification_date']}"),p('Phạm vi: Việt Nam / AHTN 2022. Người phụ trách: '+case['owner'])]
    if case.get('is_demo'):story.append(p('HỒ SƠ MẪU - Chưa thẩm định mã. Không dùng trực tiếp để khai báo.'))
    story.extend([p('Quyết định trong tài liệu này là bản ghi nội bộ, không thay thế kết luận Hải quan. Trạng thái đã duyệt không tự tạo nhãn gold.'),p(case.get('notes',''),'HSSmall')])
    retention=case.get('retention',{})
    story.extend([p('Thông tin lưu giữ hồ sơ','HSHead'),p('Số tờ khai: '+(case.get('declaration_number')or'Chưa ghi')+' | Ngày đăng ký: '+(case.get('declaration_registered_date')or'Chưa ghi')),p('Mốc lưu tham chiếu: '+(retention.get('minimum_reference_until')or'Chưa đủ ngày đăng ký tờ khai')+' | Tiếp tục giữ do kiểm tra/tranh chấp: '+('Có'if retention.get('legal_hold')else'Chưa ghi nhận')),p(retention.get('note',''),'HSSmall')])
    for index,sku in enumerate(case['skus'],1):
        story.extend([p(f"{index:02d}. {sku['sku_code']} - {sku['name']}",'HSHead'),p(f"Phiên bản {sku['revision']} | {STATUS.get(sku['status'],sku['status'])}",'HSSmall')])
        if sku.get('declared_code'):story.append(p('Mã đang khai / quan sát, chưa phải nhãn đúng: '+sku['declared_code']))
        if sku.get('description'):story.append(p(sku['description']))
        decision=sku.get('decision')
        story.append(p('Quyết định hiện tại','HSHead'))
        if decision:
            story.extend([p('HS8: '+decision['code']),p(decision['reason']),p(f"Người lập: {decision['preparer']} | Người duyệt: {decision['reviewer']} | {decision['created_at']}",'HSSmall'),p('ID căn cứ: '+', '.join(decision['evidence_ids']),'HSSmall')])
        else:story.append(p('Chưa có quyết định nội bộ còn hiệu lực.'))
        story.append(p('Thuộc tính và nguồn trích','HSHead'))
        for f in sku['facts']:
            story.extend([p(FIELDS.get(f['field'],f['field'])+' - '+STATUS.get(f['status'],f['status'])),p(f['value']),p(f"Người kiểm tra: {f.get('reviewer') or 'Chưa có'} | Chứng từ: {f.get('document_id') or 'Xác nhận trực tiếp'} | Trang/đơn vị: {f.get('page_number') or '—'}",'HSSmall'),p(f['quote'],'HSSmall'),Spacer(1,5)])
        if not sku['evidence']:story.extend([p('Căn cứ phân loại','HSHead'),p('Chưa ghi nhận căn cứ.')])
        for ei,e in enumerate(sku['evidence']):
            block=[p('Căn cứ phân loại','HSHead')]if ei==0 else[]
            block.extend([p(e['title']),p(f"{e['kind']} | Vai trò: {e['role']} | {e['jurisdiction']} / {e['nomenclature']} | {e['lifecycle']}",'HSSmall'),p(f"Hiệu lực: {e.get('effective_from') or 'Chưa ghi'} đến {e.get('effective_to') or 'Chưa ghi'} | Người đối chiếu: {e.get('reviewer') or 'Chưa có'}",'HSSmall'),p(e['quote']),p(e.get('source_url') or f"Chứng từ {e.get('document_id') or 'Chưa ghi'} - trang/đơn vị {e.get('page_number') or '—'}",'HSSmall'),p('ID: '+e['id'],'HSSmall')])
            story.append(KeepTogether(block))
        a=sku.get('analysis')
        if a:
            story.extend([p('Kết quả truy hồi / model để đối chiếu','HSHead'),p(f"{a['engine_label']} | Phiên bản: {a['model_version']} | SHA256 đầu vào: {a['input_hash']}",'HSSmall'),p('Thứ hạng không phải xác suất đúng HS8. Chưa cho phép tự động chốt mã.')])
            # A readable decision summary; JSON/XLSX retain every retrieved row.
            shortlist=[];seen=set()
            for r in a['candidates']:
                if r['heading']not in seen:shortlist.append(r);seen.add(r['heading'])
                if len(shortlist)==3:break
            if decision and not any(r['code']==decision['code']for r in shortlist):
                chosen=next((r for r in a['candidates']if r['code']==decision['code']),None)
                if chosen:shortlist.append(chosen)
            story.append(p(f"Tóm tắt {len(shortlist)}/{len(a['candidates'])} dòng truy hồi, ưu tiên các nhóm khác nhau và mã được duyệt. Danh sách đầy đủ được giữ trong JSON/XLSX/ZIP.",'HSSmall'))
            for i,r in enumerate(shortlist,1):story.append(p(f"{i}. {r['code']} - {r['path']}"))
            for q in a.get('questions',[]):story.append(p('Cần đối chiếu: '+q['question']))
    if case.get('comparisons'):
        story.extend([p('So sánh hệ quả đã lưu','HSHead'),p('Đây là các kịch bản người dùng đối chiếu. Không phải xác suất bị kiểm tra hoặc khuyến nghị chọn mã có thuế thấp.')])
        for comp in case['comparisons']:
            story.append(p(f"{comp['id']} | SKU {comp.get('sku_id')} bản {comp['sku_revision']} | {'Dữ liệu/phân tích đã thay đổi'if comp.get('stale')else'Trùng phiên bản hiện tại'} | {comp['reviewer']}",'HSSmall'))
            for row in comp['rows']:story.extend([p(f"{row['code']} | {row['scheme']} | Thuế XNK kịch bản: {row['duty_vnd']if row['duty_vnd']is not None else'Chưa xác định'} VND | {row['policy_label']}"),p('Căn cứ thuế: '+row['duty_rate_source']+' | Chính sách: '+row['policy_source'],'HSSmall')])
            story.append(p(comp['scope'],'HSSmall'))
    if case.get('decision_snapshots'):
        for fi,frozen in enumerate(case['decision_snapshots']):
            block=[p('Bản chụp quyết định tại thời điểm duyệt','HSHead')]if fi==0 else[]
            block.append(p(f"{frozen['decision_id']} | SHA256: {frozen.get('snapshot_sha256','Chưa có bản chụp ở phiên bản cũ')}",'HSSmall'))
            decision=frozen.get('snapshot',{}).get('decision',{})
            if frozen.get('snapshot',{}).get('source_capture_warnings'):block.append(p('Còn căn cứ chỉ có đoạn trích/URL, chưa có bản gốc liên kết trong hồ sơ; cần đối chiếu nguyên bản.','HSSmall'))
            if decision:block.extend([p('Mã tại lúc duyệt: '+decision['code']+' | '+decision['reason']),p('Mã khác đã loại: '+decision['alternative_code']+' | '+decision['alternative_reason']),p('Người lập: '+decision['preparer']+' | Người duyệt: '+decision['reviewer']+' | '+decision['created_at'],'HSSmall')])
            story.append(KeepTogether(block))
        story.append(p('Bản chụp đầy đủ nằm trong JSON/ZIP. Hash không phải chữ ký số hoặc dấu thời gian độc lập; tên người duyệt chưa được xác minh danh tính.','HSSmall'))
    story.append(p('Danh sách chứng từ','HSHead'))
    if not case.get('documents'):story.append(p('Chưa có bản gốc chứng từ trong hồ sơ. Đoạn trích hoặc URL chưa thay thế việc kiểm tra nguyên bản.'))
    for d in case.get('documents',[]):
        story.extend([p(d['name']),p(f"ID: {d['id']} | {d['processed_pages']}/{d['total_pages']} trang/đơn vị | {d['status']} | SHA256 {d['sha256']}",'HSSmall')])
        if d.get('source_archive'):story.append(p(f"Gói nguồn: {d['source_archive']} / {d.get('member_path','')}",'HSSmall'))
    if case.get('tax_scenarios'):
        story.append(p('Kịch bản thuế theo đầu vào đối chiếu','HSHead'))
        story.append(p('Chưa chứng nhận mức thuế hiện hành. Mỗi kịch bản gắn với phiên bản SKU tại thời điểm lưu.'))
        for t in case['tax_scenarios']:
            story.extend([p(f"{t['code']} | {t['scheme']} | {t['classification_date']} | SKU rev {t.get('sku_revision','—')}"),p(f"Thuế XNK: {t['import_or_export_duty_vnd']} VND | VAT: {t.get('vat_vnd') or 'Chưa xác định'} | Tổng: {t['total_taxes_vnd']} VND"),p(f"Đối chiếu: {t['reviewer']} | Căn cứ XNK: {t.get('duty_rate_source','')} | VAT: {t.get('vat_source','')}",'HSSmall')])
    story.append(p('Nhật ký gần nhất','HSHead'))
    for e in case.get('events',[]):story.append(p(f"{e['created_at']} | {e['action']} | {e['actor']} | {e['payload']}",'HSSmall'))
    def page(canvas,doc):
        canvas.saveState();canvas.setFont('HSBold',8);canvas.setFillColor(colors.HexColor('#346b60'));canvas.drawString(44,A4[1]-33,'HS WORKSPACE');canvas.setStrokeColor(colors.HexColor('#dfe9e5'));canvas.line(44,A4[1]-42,A4[0]-44,A4[1]-42);canvas.setFont('HSRegular',6.5);canvas.setFillColor(colors.HexColor('#879a9c'));canvas.drawString(44,30,case['reference']+' | '+case.get('exported_at',''));canvas.drawRightString(A4[0]-44,30,'Trang '+str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page);return out.getvalue()

def case_excel(case):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    import math,re
    from datetime import date,datetime
    wb=Workbook();wb.remove(wb.active)
    def literal(v):
        # All human-authored identifiers and text remain literal cells, never formulas.
        if isinstance(v,(dict,list)):from .workspace import encode;v=encode(v)
        if isinstance(v,str):return v.replace('\x00','')
        return v
    def sheet(name,headers,rows,widths=None):
        ws=wb.create_sheet(name);ws.append(headers)
        for row in rows:
            ws.append([literal(v) for v in row])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value,str):cell.data_type='s'
        for c in ws[1]:c.font=Font(name='Aptos',bold=True,color='FFFFFF',size=10);c.fill=PatternFill('solid',fgColor='24564D');c.alignment=Alignment(vertical='center',wrap_text=True)
        ws.row_dimensions[1].height=30;ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for i,h in enumerate(headers,1):ws.column_dimensions[get_column_letter(i)].width=(widths[i-1] if widths and i<=len(widths) else 26)
        for row in ws.iter_rows(min_row=2):
            for c in row:c.font=Font(name='Aptos',size=10,color='435762');c.alignment=Alignment(vertical='top',wrap_text=True)
            lines=1
            for c in row:
                width=ws.column_dimensions[c.column_letter].width
                text=str(c.value or '')
                lines=max(lines,sum(max(1,math.ceil(len(line)/(width*1.05))) for line in text.split('\n')))
                header=headers[c.column-1].lower()
                if isinstance(c.value,str) and ('hiệu lực' in header or 'ngày' in header) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',c.value):c.value=date.fromisoformat(c.value);c.number_format='dd/mm/yyyy'
            ws.row_dimensions[row[0].row].height=min(409,max(32,15*lines+10))
        ws.sheet_view.showGridLines=False
        return ws
    sheet('Ho so',['Trường','Giá trị'],[['Số hồ sơ',case['reference']],['Tên hồ sơ',case['title']],['Người phụ trách',case['owner']],['Ngày phân loại',case['classification_date']],['Số tờ khai',case.get('declaration_number')],['Ngày đăng ký tờ khai',case.get('declaration_registered_date')],['Mốc lưu tham chiếu',(case.get('retention')or{}).get('minimum_reference_until')],['Giữ do kiểm tra/tranh chấp',bool(case.get('legal_hold'))],['Phạm vi','VN / AHTN2022'],['Loại tài liệu','Hồ sơ nội bộ, không phải kết luận Hải quan'],['Nhãn huấn luyện gold','Không tự động tạo từ quyết định nội bộ'],['Thời điểm xuất',case.get('exported_at','')]], [29,100])
    sheet('SKU',['ID SKU','Mã SKU','Tên hàng','Nhóm hàng','Phiên bản','Trạng thái','Mã quan sát (chưa xác minh)','Mã duyệt nội bộ','Lập luận','Người lập','Người duyệt'],[[s['id'],s['sku_code'],s['name'],s['product_family'],s['revision'],STATUS.get(s['status'],s['status']),s.get('declared_code'),(s.get('decision')or{}).get('code'),(s.get('decision')or{}).get('reason'),(s.get('decision')or{}).get('preparer'),(s.get('decision')or{}).get('reviewer')]for s in case['skus']], [25,22,45,18,14,23,25,22,70,24,24])
    sheet('Thuoc tinh',['Mã SKU','ID thuộc tính','Thuộc tính','Giá trị','Trạng thái','Người kiểm tra','ID chứng từ','Trang / đơn vị','Trích đoạn','Loại nguồn'],[[s['sku_code'],f['id'],FIELDS.get(f['field'],f['field']),f['value'],STATUS.get(f['status'],f['status']),f['reviewer'],f['document_id'],f['page_number'],f['quote'],f['source_kind']]for s in case['skus']for f in s['facts']], [20,25,29,65,23,25,25,16,90,25])
    sheet('Can cu',['Mã SKU','ID căn cứ','Tên nguồn','Loại','Vai trò','Quốc gia','Phiên bản','Hiệu lực từ','Hiệu lực đến','Trạng thái nguồn','Người đối chiếu','Trích đoạn','URL','ID chứng từ','Trang / đơn vị'],[[s['sku_code'],e['id'],e['title'],e['kind'],e['role'],e['jurisdiction'],e['nomenclature'],e['effective_from'],e['effective_to'],e['lifecycle'],e['reviewer'],e['quote'],e['source_url'],e['document_id'],e['page_number']]for s in case['skus']for e in s['evidence']], [20,25,45,22,20,15,22,19,19,22,25,90,65,25,16])
    sheet('Ung vien HS',['Mã SKU','Phiên bản SKU','Engine','Phiên bản model','Thứ hạng','HS8','Cấu trúc danh mục','Xác suất đúng HS8','SHA256 đầu vào'],[[s['sku_code'],s['revision'],s['analysis']['engine'],s['analysis']['model_version'],i,r['code'],r['path'],'Chưa hiệu chuẩn',s['analysis']['input_hash']]for s in case['skus']if s.get('analysis')for i,r in enumerate(s['analysis']['candidates'],1)], [20,18,25,35,15,18,100,25,70])
    sheet('Chung tu',['ID','Tên tệp','SHA256','Trang / đơn vị đã xử lý','Tổng trang / đơn vị','Trạng thái','Gói nguồn','Đường dẫn trong gói'],[[d['id'],d['name'],d['sha256'],d['processed_pages'],d['total_pages'],d['status'],d.get('source_archive'),d.get('member_path')]for d in case.get('documents',[])], [25,55,70,24,24,23,50,65])
    sheet('Nhat ky',['ID','Thời gian UTC','Hành động','Người thao tác','ID SKU','Nội dung','Hash sự kiện'],[[e['id'],e['created_at'],e['action'],e['actor'],e['sku_id'],e['payload'],e['event_hash']]for e in case.get('events',[])], [15,33,30,25,25,110,70])
    sheet('Lich su duyet',['ID quyết định','ID SKU','Phiên bản SKU','HS8','Lập luận','Người lập','Người duyệt','Ngày phân loại','Thời điểm lưu UTC','Thời điểm thay thế UTC','ID căn cứ'],[[d['id'],d['sku_id'],d['sku_revision'],d['code'],d['reason'],d['preparer'],d['reviewer'],d['classification_date'],d['created_at'],d['superseded_at'],d['evidence_ids']]for d in case.get('decision_history',[])], [25,25,18,18,90,25,25,20,33,33,70])
    sheet('Kich ban thue',['ID','ID SKU','Phiên bản SKU','HS8','Ngày giao dịch','Luồng','Chế độ','Trị giá VND','Thuế XNK VND','VAT VND','Tổng thuế VND','Người đối chiếu','Căn cứ thuế XNK','Căn cứ VAT','Chứng nhận mức thuế hiện hành'],[[t.get('id'),t.get('linked_sku'),t.get('sku_revision'),t['code'],t['classification_date'],t['trade_type'],t['scheme'],t['customs_value_vnd'],t['import_or_export_duty_vnd'],t.get('vat_vnd'),t['total_taxes_vnd'],t['reviewer'],t.get('duty_rate_source'),t.get('vat_source'),'Chưa chứng nhận']for t in case.get('tax_scenarios',[])],[25,25,18,18,20,18,20,25,25,25,25,25,65,65,32])
    sheet('So sanh he qua',['ID so sánh','ID SKU','Phiên bản SKU','Ngày giao dịch','HS8','Chế độ','Thuế XNK kịch bản VND','Chính sách đã đối chiếu','Căn cứ chính sách','Căn cứ thuế','Thuộc tính phân biệt','Người đối chiếu','Đã cũ'],[[comp['id'],comp.get('sku_id'),comp['sku_revision'],comp['classification_date'],r['code'],r['scheme'],r['duty_vnd'],r['policy_label'],r['policy_source'],r['duty_rate_source'],r['distinguishing_attributes'],comp['reviewer'],bool(comp.get('stale'))]for comp in case.get('comparisons',[])for r in comp['rows']],[25,25,18,20,18,20,28,55,70,70,70,25,18])
    sheet('Ban chup quyet dinh',['ID quyết định','SHA256 bản chụp','Khớp hash','Mã khác đã loại','Lý do loại','Có chữ ký số','Có bản gốc mọi căn cứ'],[[f['decision_id'],f.get('snapshot_sha256'),f.get('integrity_matches'),f.get('snapshot',{}).get('decision',{}).get('alternative_code'),f.get('snapshot',{}).get('decision',{}).get('alternative_reason'),False,False if not f.get('snapshot')else not bool(f['snapshot'].get('source_capture_warnings'))]for f in case.get('decision_snapshots',[])],[25,75,18,20,100,22,28])
    stream=BytesIO();wb.save(stream);return stream.getvalue()
