"""Shared extraction schema and source permissions (not a commodity dictionary)."""
import re
from .document_layout import norm, COLUMNS

PRODUCT_TYPES={'technical_spec','product_catalogue','mill_test','certificate_of_quality'}
TRADE_TYPES={'commercial_invoice','packing_list','bill_of_lading','air_waybill','certificate_of_origin','sales_contract','customs_declaration'}
PRODUCT_FIELDS={
 'name':('product name','product','item','item description','description of goods','description','tên sản phẩm','tên hàng','tên hàng hóa','tên và bản chất hàng'),
 'model':('model','model no','mẫu máy','mã hiệu','sku','sku code','product code','item code','mã sản phẩm','mã hàng','kiểu máy'),
 'part_number':('part number','part no','p/n'),
 'function':('function','intended use','application','công dụng','công dụng chính','chức năng'),
 'construction':('construction','structure','cấu tạo','cấu tạo và nguyên lý','kết cấu'),
 'material':('material','composition','chất liệu','vật liệu','thành phần'),
 'specifications':('technical specifications','specifications','rated power','power consumption','power','voltage','frequency','dimensions','size','thông số kỹ thuật','thông số và kích thước','thông số','công suất','điện áp','tần số'),
 'manufacturing':('manufacturing','manufacturing process','quy trình sản xuất'),
 'condition':('condition','tình trạng'),
 'packaging':('packaging','đóng gói','quy cách đóng gói'),
 'origin':('country of origin','origin','xuất xứ','nước xuất xứ'),
 'quantity':('quantity','qty','số lượng'), 'unit':('unit','uom','đvt','đơn vị'),
 'unit_price':('unit price','đơn giá'), 'amount':('amount','line total','thành tiền'),
 'currency':('currency','ccy','tiền tệ'),
 'gross_weight':('gross weight','g.w.','gw','trọng lượng cả bì'),
 'net_weight':('net weight','n.w.','nw','trọng lượng tịnh'),
 'packages':('packages','cartons','số kiện'),
 'declared_code':('hs code','hs','mã hs','h.s. code','mã số hàng hóa'),
}
DOSSIER_FIELDS={
 'invoice_number':('invoice no','inv no','invoice number','invoice #','số hóa đơn','hđ số','no. & date of invoice','no & date of invoice'),
 'invoice_date':('invoice date','ngày hóa đơn'),
 'exporter':('seller','the seller','exporter','người xuất khẩu'),
 'importer':('buyer','the buyer','importer','người nhập khẩu'),
 'shipper':('shipper',), 'consignee':('consignee',),
 'contract_number':('contract no','contract number','số hợp đồng'),
 'bl_number':('b/l no','bl no','bill of lading no','awb no','air waybill no','số vận đơn'),
 'certificate_number':('certificate no','certificate number','số chứng nhận'),
 'declaration_number':('số tờ khai','tờ khai số','declaration number','declaration no'),
 'origin_country':('country of origin','xuất xứ'),
 'currency':('currency','ccy'), 'incoterms':('incoterms','trade terms','delivery terms'),
 'port_of_loading':('port of loading','cảng xếp','cảng đi'),
 'port_of_discharge':('port of discharge','cảng dỡ','cảng đến'),
 'total_value':('total amount','total value','grand total','tổng tiền','tổng trị giá'),
 'total_gross_weight':('total gross weight','gross weight','g.w.','gw','tổng trọng lượng'),
 'total_net_weight':('total net weight','net weight','n.w.','nw','trọng lượng tịnh'),
 'total_packages':('total packages','packages','số kiện'),
}
ALIASES={norm(a).rstrip('.'):f for f,aliases in PRODUCT_FIELDS.items() for a in aliases}
META_ALIASES={norm(a).rstrip('.'):f for f,aliases in DOSSIER_FIELDS.items() for a in aliases}
COMMON={'name','model','part_number','quantity','unit','packaging','packages','gross_weight','net_weight'}
PERMISSIONS={
 'commercial_invoice':set(PRODUCT_FIELDS)-{'manufacturing'},
 'customs_declaration':set(PRODUCT_FIELDS),
 'sales_contract':set(PRODUCT_FIELDS),
 'packing_list':COMMON|{'specifications','origin','material'},
 'bill_of_lading':COMMON,
 'air_waybill':COMMON,
 'certificate_of_origin':COMMON|{'origin','declared_code'},
 'certificate_of_quality':COMMON|{'material','specifications','condition','construction','origin'},
 'mill_test':COMMON|{'material','specifications','manufacturing','condition','origin'},
 'technical_spec':set(PRODUCT_FIELDS)-{'unit_price','amount','currency'},
 'product_catalogue':set(PRODUCT_FIELDS)-{'amount'},
}
META_PERMISSIONS={
 'invoice_number':TRADE_TYPES|{'certificate_of_quality'},
 'invoice_date':{'commercial_invoice','packing_list','certificate_of_origin'},
 'exporter':{'commercial_invoice','sales_contract','customs_declaration','certificate_of_origin'},
 'importer':{'commercial_invoice','sales_contract','customs_declaration','certificate_of_origin'},
 'shipper':{'bill_of_lading','air_waybill','packing_list','commercial_invoice'},
 'consignee':{'bill_of_lading','air_waybill','packing_list','commercial_invoice'},
 'contract_number':{'sales_contract','commercial_invoice','customs_declaration'},
 'bl_number':{'bill_of_lading','air_waybill','packing_list','commercial_invoice','customs_declaration'},
 'certificate_number':{'certificate_of_origin','certificate_of_quality','mill_test'},
 'declaration_number':{'customs_declaration'},
 'origin_country':{'certificate_of_origin','commercial_invoice','customs_declaration'},
}


def allowed(kind, field, metadata=False):
    if metadata:
        return kind in META_PERMISSIONS.get(field,TRADE_TYPES)
    return field in PERMISSIONS.get(kind,set())


def label_field(label, metadata=False):
    label=norm(label).rstrip(' .:#')
    label=re.sub(r'^[0-9①-⑳]+[.)\s]+','',label)
    return (META_ALIASES if metadata else ALIASES).get(label)


def hs_code(value):
    value=value.strip()
    if re.fullmatch(r'\d{4}(?:\.\d{2}){1,2}|\d{6}|\d{8}',value):
        return value.replace('.','')
    return None
