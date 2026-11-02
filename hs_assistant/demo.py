"""Source-backed sample records, isolated by is_demo; no sample is expert gold."""
from pathlib import Path
import json
from .workspace import uid,now

def seed(state):
    db=state['db'];cat=state['catalogue']
    with db.lock:
        existing=[x for x in db.cases() if x['is_demo']]
        if existing:return {'cases':existing,'created':0}
        path=Path(__file__).resolve().parent.parent/'data/demo_evidence.json';sources=json.loads(path.read_text())
        details={
         'B45_STEEL_310S':('Thép không gỉ cán nguội 310S','STEEL-310S-295','steel',[('name','Thép không gỉ cán nguội, dạng tấm'),('function','Nguyên liệu thép tấm dùng trong sản xuất'),('material','Thép không gỉ 310S; cần đối chiếu thành phần theo đúng lô'),('specifications','Chiều dày 2,95 mm; cần xác minh thứ tự chiều dài / chiều rộng 9032 × 1552 mm')]),
         'B45_LASER_FJ200':('Thiết bị laser FJ200','LASER-FJ200','laser',[('name','Thiết bị sử dụng nguồn diode laser FJ200'),('function','Cần đối chiếu công dụng thiết kế và cơ chế quang sinh học trong tài liệu nhà sản xuất'),('specifications','Tài liệu đề cập bước sóng 660/980 nm; kiểm lại bản gốc trước khi dùng')]),
        }
        output=[]
        for source in sources:
            if source['case_id'] not in details:continue
            title,code,family,facts=details[source['case_id']]
            case=db.create_case(title,'Nhóm 8',classification_date='2026-11-01',notes='HỒ SƠ MINH HỌA từ bản trích xuất chứng từ dự án. Các thuộc tính và mã chưa được thẩm định; không dùng trực tiếp để khai báo.',is_demo=True)
            sku=db.add_sku(case['id'],code,title,product_family=family,declared_code=source['observed_codes'][0] if source['observed_codes'] else None)
            header='BẢN TRÍCH XUẤT THAM KHẢO — CHƯA THAY THẾ CHỨNG TỪ GỐC\n'+source['archive']+'\n'+source['member']+'\nSHA256 chứng từ gốc: '+source['original_source_sha256']+'\n\n'
            document,_=state['documents']._store(case['id'],Path(source['member']).stem+'_ban_trich_xuat.txt',(header+source['text']).encode(),sku['id'],source['archive'],source['member'])
            for field,value in facts:db.add_fact(sku['id'],field,value,source_kind='manual_declaration',quote='Gợi ý biên soạn để kiểm tra từ hồ sơ mẫu; cần đối chiếu đúng tài liệu gốc.',status='unverified')
            output.append(db.get_case(case['id']))
        return {'cases':output,'created':len(output)}
