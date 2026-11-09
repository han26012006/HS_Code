"""Author synthetic labels before implementation; NOT independent real ground truth."""
import json, hashlib
from pathlib import Path


def doc(i, kind, text, products=(), fields=None, rows=0):
    return {'id':i,'name':'opaque-'+i+'.txt','pages':[{'number':1,'text':text,'method':'plain_text'}], 'expected_kind':kind,'expected_products':list(products),'expected_fields':fields or {},'expected_rows':rows}


def item(code, name, **fields):
    return {'identifier':code,'name':name,'fields':{'name':name,**fields}}


def case(i, split, docs, products):
    return {'id':i,'split':split,'annotation_status':'synthetic_author_labels','documents':docs,'products':products}

cases=[
 case('steel-trade','development',[
  doc('steel-inv','commercial_invoice','COMMERCIAL INVOICE\nInvoice No: IV-800\nInvoice Date: 2026-10-03\nSeller: Alloy Works Ltd\nBuyer: Metro Fabrication Ltd\nContract No: CT-800\nCurrency: USD\nPart Number | Description | Quantity | Unit | Unit Price | Amount | Material\nST-21 | Rolled steel sheet | 40 | PCS | 12.50 | 500.00 | Stainless steel\nST-22 | Rolled steel sheet | 60 | PCS | 15.00 | 900.00 | Stainless steel\n', ['ST-21','ST-22'], {'invoice_number':'IV-800','invoice_date':'2026-10-03','exporter':'Alloy Works Ltd','importer':'Metro Fabrication Ltd','contract_number':'CT-800'},2),
  doc('steel-pl','packing_list','PACKING LIST\nInvoice No: IV-800\nPart Number | Description | Quantity | Unit | Gross Weight | Net Weight | Packages\nST-21 | Rolled steel sheet | 40 | PCS | 25 kg | 23 kg | 2 cartons\nST-22 | Rolled steel sheet | 60 | PCS | 34 kg | 32 kg | 3 cartons\n',['ST-21','ST-22'],rows=2)
 ],[item('ST-21','Rolled steel sheet',quantity='40',unit='PCS',unit_price='12.50',amount='500.00',material='Stainless steel',gross_weight='25 kg',net_weight='23 kg',packages='2 cartons'),item('ST-22','Rolled steel sheet',quantity='60',unit='PCS',unit_price='15.00',amount='900.00',material='Stainless steel',gross_weight='34 kg',net_weight='32 kg',packages='3 cartons')]),
 case('chemical-certificates','development',[
  doc('chem-q','certificate_of_quality','CERTIFICATE OF QUALITY\nCertificate No: CQ-51\nModel: RES-51\nProduct name: Resin pellets\nComposition: Polypropylene\nTechnical specifications: Density 0.90 g/cm3\n',['RES-51']),
  doc('chem-d','technical_spec','TECHNICAL DATASHEET\nModel: RES-51\nProduct name: Resin pellets\nComposition: Polypropylene\nTechnical specifications: Density 0.90 g/cm3\nFunction: Injection moulding\n',['RES-51'])
 ],[item('RES-51','Resin pellets',material='Polypropylene',specifications='Density 0.90 g/cm3',function='Injection moulding')]),
 case('food-origin','development',[
  doc('food-inv','commercial_invoice','COMMERCIAL INVOICE\nInvoice No: FOOD-51\nModel: FD-51\nProduct name: Dried mango\nQuantity: 100\nUnit: KG\n',['FD-51'],{'invoice_number':'FOOD-51'}),
  doc('food-co','certificate_of_origin','CERTIFICATE OF ORIGIN\nCertificate No: CO-51\nInvoice No: FOOD-51\nModel: FD-51\nProduct name: Dried mango\nCountry of origin: Thailand\n',['FD-51'],{'invoice_number':'FOOD-51'})
 ],[item('FD-51','Dried mango',quantity='100',unit='KG',origin='Thailand')]),
 case('transport','development',[
  doc('bl','bill_of_lading','BILL OF LADING\nB/L No: OCEAN-96\nShipper: Textile Export Ltd\nConsignee: Textile Import Ltd\nPort of loading: Bangkok\nPort of discharge: Haiphong\nPackages: 20 cartons\n',[],{'bl_number':'OCEAN-96','shipper':'Textile Export Ltd','consignee':'Textile Import Ltd','port_of_loading':'Bangkok','port_of_discharge':'Haiphong','total_packages':'20 cartons'})
 ],[]),
 case('contract','development',[
  doc('ct','sales_contract','SALES CONTRACT\nContract No: CN-25\nSeller: Wood Export Ltd\nBuyer: Furniture Ltd\nSKU | Description | Quantity | Unit\nWOOD-7 | Oak board | 200 | M3\n',['WOOD-7'],{'contract_number':'CN-25','exporter':'Wood Export Ltd','importer':'Furniture Ltd'},1)
 ],[item('WOOD-7','Oak board',quantity='200',unit='M3')]),
 case('catalogue','development',[
  doc('cat','product_catalogue','PRODUCT CATALOGUE\nModel | Description | Voltage | Power\nPUMP-1 | Water pump | 230 V | 500 W\nPUMP-2 | Water pump | 230 V | 750 W\n',['PUMP-1','PUMP-2'],rows=2)
 ],[item('PUMP-1','Water pump',specifications=['230 V','500 W']),item('PUMP-2','Water pump',specifications=['230 V','750 W'])]),
 case('customs','development',[
  doc('decl','customs_declaration','CUSTOMS DECLARATION\nSố tờ khai: 123456789012\nModel: CP-2\nProduct name: Control panel\nHS Code: 8537.10.99\n',['CP-2'],{'declaration_number':'123456789012'})
 ],[item('CP-2','Control panel',declared_code='85371099')]),
 case('legal-negative','development',[
  doc('law','legal_reference','Danh mục hàng hóa xuất khẩu, nhập khẩu Việt Nam\nThông tư số 31/2022/TT-BTC\n8507.10.10 khởi động\n8516.31.00 Máy sấy tóc\n')
 ],[]),
 case('unknown-negative','development',[doc('unk','other','Memo\nWe discussed the invoice yesterday.\nNo shipment or product records attached.\n')],[]),
 case('single-signal-negative','development',[doc('amb','other','A note\nModel: A-1\nCatalogue is only mentioned here.\n')],[]),
 case('textile-shipment','reserved_synthetic',[
  doc('cloth-i','commercial_invoice','COMMERCIAL INVOICE\nInvoice No: TX-88\nCurrency: EUR\nItem Code\tGoods Description\tQty\tUOM\tUnit Price\tLine Total\nFAB-8\tWoven cotton fabric\t320\tM\t2.10\t672.00\nFAB-9\tWoven cotton fabric\t180\tM\t3.00\t540.00\n',['FAB-8','FAB-9'],{'invoice_number':'TX-88'},2),
  doc('cloth-p','packing_list','PACKING LIST\nInvoice No: TX-88\nItem Code\tGoods Description\tQty\tUOM\nFAB-8\tWoven cotton fabric\t320\tM\nFAB-9\tWoven cotton fabric\t180\tM\n',['FAB-8','FAB-9'],rows=2)
 ],[item('FAB-8','Woven cotton fabric',quantity='320',unit='M',unit_price='2.10',amount='672.00'),item('FAB-9','Woven cotton fabric',quantity='180',unit='M',unit_price='3.00',amount='540.00')]),
 case('optics','reserved_synthetic',[
  doc('opt-q','certificate_of_quality','CERTIFICATE OF QUALITY\nCertificate No: QO-26\nPart number: OPT-30\nProduct name: Optical lens\nMaterial: Glass\nTechnical specifications: Diameter 30 mm\n',['OPT-30']),
  doc('opt-d','technical_spec','TECHNICAL SPECIFICATION\nPart number: OPT-30\nProduct name: Optical lens\nMaterial: Glass\nTechnical specifications: Diameter 30 mm\nFunction: Focus light\n',['OPT-30'])
 ],[item('OPT-30','Optical lens',material='Glass',specifications='Diameter 30 mm',function='Focus light')]),
 case('air-shipment','reserved_synthetic',[doc('air','air_waybill','AIR WAYBILL\nAWB No: AIR-880\nShipper: Device Export Ltd\nConsignee: Laboratory Ltd\nAirport of departure: Hanoi\nAirport of destination: Tokyo\n',[],{'bl_number':'AIR-880','shipper':'Device Export Ltd','consignee':'Laboratory Ltd'})],[]),
 case('legal-en','reserved_synthetic',[doc('tariff','legal_reference','HARMONIZED TARIFF SCHEDULE\nChapter 85\n8516.31.00 Hair dryers\nSection XVI notes\n')],[]),
 case('unknown-ocr','reserved_synthetic',[doc('ocr','other','xx?? \ufffd\ufffd\nSKU? aa\n... 00l1')],[]),
]
root=Path('tests/fixtures/document_ai');root.mkdir(parents=True,exist_ok=True)
for split in ('development','reserved_synthetic'):
 p=root/(split+'.json');p.write_text(json.dumps([c for c in cases if c['split']==split],ensure_ascii=False,indent=2))
manifest={'dataset_version':1,'scope':'synthetic tests only; no independent real-world holdout yet','annotation_status':'authored, awaiting independent review','splits':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.json')}}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
