"""Dated tariff evidence + explicit operator-checked scenarios, never HS-by-lowest-tax."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from datetime import date,datetime
import argparse,hashlib,json,re
VERSION='tax-v5.3-chapter98-separated'
SCHEMES={'K':'ordinary','N':'MFN','Q':'VAT','T':'ACFTA','W':'ATIGA','Z':'AJCEP','AC':'VJEPA','AF':'AKFTA','AI':'AANZFTA','AL':'AIFTA','AO':'VKFTA','AR':'VCFTA','AU':'VN-EAEU','AX':'CPTPP','BA':'AHKFTA','BD':'VNCU','BG':'EVFTA','BJ':'UKVFTA','BM':'VN-LAO','BP':'VN-CAM','BS':'VIFTA','BV':'RCEP','CG':'EXCISE','CJ':'EXPORT','CM':'EXPORT_CPTPP','CP':'EXPORT_EVFTA','CS':'EXPORT_UKVFTA','CV':'ENVIRONMENT'}
def text(v):return v.isoformat()if isinstance(v,(date,datetime))else str(v).strip()if v is not None else''
def parse_rate(raw):
 s=text(raw).replace('\n',' ').strip();c=s.replace('%','').replace(' ','')
 if not s:return {'kind':'missing','raw':s}
 if c=='*':return {'kind':'marker_requires_interpretation','raw':s,'meaning_depends_on_schedule':True}
 if c.upper()in {'KCT','KHÔNGCHỊUTHUẾ','KHONGCHIUTHUE'}:return {'kind':'not_subject','raw':s}
 if re.fullmatch(r'\d+(?:[.,]\d+)?',c):return {'kind':'ad_valorem','percent':float(c.replace(',','.')),'raw':s}
 if '/'in c and all(x=='*'or re.fullmatch(r'\d+(?:[.,]\d+)?',x)for x in c.split('/')):return {'kind':'ambiguous','raw':s,'options':[parse_rate(x)for x in c.split('/')]}
 return {'kind':'specific_or_mixed'if re.search(r'USD|VND|VNĐ|đồng|dong',s,re.I)else'conditional_or_unparsed','raw':s,'manual_review_required':True}
def code_of(cell):
 v=cell.value
 if isinstance(v,str):s=re.sub(r'[.\s]','',v)
 elif isinstance(v,(int,float))and v==int(v)and re.fullmatch('0{8}',cell.number_format or''):s=f'{int(v):08d}'
 else:return None
 return s if re.fullmatch(r'\d{8}',s)else None

def build_snapshot(workbook,out):
 from openpyxl import load_workbook
 from openpyxl.utils import column_index_from_string as ci,get_column_letter as letter
 out=Path(out);out.mkdir(parents=True,exist_ok=True);w=load_workbook(workbook,read_only=True,data_only=True,keep_links=False);s=w['BT2026'];seen=set();problems=[];count=0;h=hashlib.sha256(Path(workbook).read_bytes()).hexdigest();rcep_headers={letter(k):[]for k in range(ci('BV'),ci('CF')+1)}
 for row in s.iter_rows(min_row=3,max_row=6):
  for k in range(ci('BV'),ci('CF')+1):rcep_headers[letter(k)].append(text(row[k-1].value))
 special=[]
 with(out/'tax_snapshot.jsonl').open('w')as f:
  for n,row in enumerate(s.iter_rows(min_row=7),7):
   if len(row)<6:continue
   code=code_of(row[5])
   if not code:continue
   if code in seen and not code.startswith('98'):problems.append({'row':n,'code':code,'error':'duplicate_code'});continue
   rates={}
   for col,scheme in SCHEMES.items():
    j=ci(col)-1;rates[scheme]={'rate':parse_rate(row[j].value),'source_cell':f'{col}{n}','legal_reference':text(row[j+1].value)if scheme!='RCEP'else'','effective_from_observed':text(row[j+2].value)if scheme!='RCEP'else'','legally_verified_current':False}
   rates['RCEP']['rate']={'kind':'conditional_country_schedule','raw':'RCEP: chọn biểu theo nước xuất xứ; không tự dùng cột đầu','country_cells':{f'{letter(k)}{n}':text(row[k-1].value)for k in range(ci('BV'),ci('CF')+1)},'country_header_rows_3_to_6':rcep_headers}
   record={'code':code,'description':text(row[6].value),'unit':None if code.startswith('98')else text(row[8].value),'snapshot_date':'2026-04-05','source_sheet':'BT2026','source_row':n,'source_sha256':h,'rates':rates,'goods_policy_observation':text(row[102].value)if len(row)>102 else'','vat_reduction_observation':text(row[103].value)if len(row)>103 else'','is_ground_truth_hs_label':False}
   if code.startswith('98'):
    record.update(record_type='chapter98_conditional_reference',reference_code_observation=text(row[8].value),reference_code_source_cell=f'I{n}',requires_special_regime_review=True)
    special.append(record);continue
   seen.add(code);f.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');count+=1
 (out/'chapter98_snapshot.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))for r in special)+'\n')
 sheets=[];aux=[]
 for ws in w:
  last=0;nonempty=0;lines=[]
  for n,row in enumerate(ws.iter_rows(),1):
   last=n;vals=[f'{letter(j)}: {text(c.value)}'for j,c in enumerate(row,1)if c.value is not None]
   if vals:nonempty+=1
   if vals and ws.title in {'6QT','PL1','PL2','DB','MT','MOI','BANG','HT'}:lines.append({'row':n,'text':' | '.join(vals)})
  sheets.append({'sheet':ws.title,'rows_read':last,'nonempty_rows':nonempty})
  if lines:aux.append({'sheet':ws.title,'source_sha256':h,'rows':lines,'applicability_requires_review':True})
 w.close();(out/'tariff_auxiliary.json').write_text(json.dumps(aux,ensure_ascii=False,separators=(',',':')));receipt={'version':VERSION,'workbook_sha256':h,'snapshot_date':'2026-04-05','rows_hs8':count,'chapter98_rows_retained':len(special),'chapter98_unique_codes':len({r['code']for r in special}),'chapter98_unit_column_is_reference':True,'schemes':list(SCHEMES.values()),'sheets':sheets,'problems':problems,'all_rates_recertified_current':False,'star_marker':'context dependent, never globally treated as tax exemption','tax_cost_used_for_classification':False};(out/'TAX_SOURCE_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({'tariff_codes':count,'chapter98_rows':len(special),'sheets_read':len(sheets),'problems':len(problems)}));return receipt
class TaxError(ValueError):pass
def amount(v,name):
 try:x=Decimal(str(v))
 except(InvalidOperation,TypeError,ValueError):raise TaxError(name+' không phải số hợp lệ.')
 if not x.is_finite()or x<0:raise TaxError(name+' phải hữu hạn và không âm.')
 return x

def customs_value(d):
 mode=d.get('valuation_mode','entered_customs_value')
 if mode=='entered_customs_value':return amount(d.get('customs_value_vnd',0),'Trị giá tính thuế'),{'mode':mode,'currency':'VND','already_adjusted_by_operator':True}
 if mode!='components':raise TaxError('Chọn cách nhập trị giá.')
 v=d.get('valuation',{});fx=amount(v.get('exchange_rate',0),'Tỷ giá hải quan')
 if not fx or not all(v.get(k)for k in ['reviewer','exchange_rate_source','customs_valuation_checked']):raise TaxError('Cần người đối chiếu, tỷ giá hải quan có nguồn và xác nhận phương pháp trị giá.')
 total=amount(v.get('invoice_amount',0),'Hóa đơn')+(Decimal(0)if v.get('freight_in_invoice')else amount(v.get('freight',0),'Cước'))+(Decimal(0)if v.get('insurance_in_invoice')else amount(v.get('insurance',0),'Bảo hiểm'))+amount(v.get('other_additions',0),'Điều chỉnh cộng')-amount(v.get('deductions',0),'Điều chỉnh trừ')
 if total<=0:raise TaxError('Trị giá sau điều chỉnh phải dương.')
 return total*fx,{'mode':mode,'currency':v.get('currency'),'exchange_rate':str(fx),'source':v['exchange_rate_source'],'incoterm':v.get('incoterm'),'freight_added':not v.get('freight_in_invoice'),'insurance_added':not v.get('insurance_in_invoice'),'operator_checked':True}
class TaxEngine:
 def __init__(self,root):
  self.root=Path(root);self.rows={r['code']:r for r in map(json.loads,(self.root/'tax_snapshot.jsonl').read_text().splitlines())};self.sources=json.loads((self.root/'TAX_LEGAL_REGISTRY.json').read_text())if(self.root/'TAX_LEGAL_REGISTRY.json').exists()else[]
  self.special={}
  special_path=self.root/'chapter98_snapshot.jsonl'
  if special_path.exists():
   for line in special_path.read_text().splitlines():
    if line.strip():
     row=json.loads(line);self.special.setdefault(row['code'],[]).append(row)
 def lookup(self,code,as_of):
  date.fromisoformat(as_of)
  if code in self.special:
   variants=self.special[code]
   return {'code':code,'description':'Mã Chương 98 có điều kiện/phạm vi riêng','record_type':'chapter98_conditional_reference','as_of':as_of,'snapshot_date':'2026-04-05','source_sha256':variants[0]['source_sha256'],'source_sheet':'BT2026','source_row':None,'rates':{},'variants':variants,'requires_special_regime_review':True,'goods_policy_observation':'Cột I là mã tham chiếu quan sát trong workbook, không phải đơn vị tính. Không tự chuyển đổi sang mã thông thường hoặc tự chọn mức thuế.','vat_reduction_observation':'','official_references':self.sources,'automatic_current_rate_certified':False,'warnings':['Giữ mọi dòng nguồn của cùng mã Chương 98. Cần đối chiếu điều kiện pháp lý và mã thông thường tương ứng; chức năng tính hiện chưa hỗ trợ.']}
  if code not in self.rows:raise TaxError('Mã chưa có trong snapshot thuế đã nạp.')
  warnings=['Biểu tổng hợp ngày 05/04/2026; chưa xác nhận toàn bộ mức thuế hiện hành.','Thuế không được dùng để quyết định mã HS.']
  if as_of!='2026-04-05':warnings.append('Ngày giao dịch khác ngày snapshot: đối chiếu văn bản và thời kỳ áp dụng tương ứng.')
  if code.startswith('27')and'2026-10-01'<=as_of<='2026-12-31':warnings.append('Kiểm tra đúng phạm vi chính sách xăng dầu NQ43/2026 và các văn bản được dẫn chiếu; không tự coi mọi sắc thuế đều0.')
  return dict(self.rows[code],as_of=as_of,warnings=warnings,official_references=self.sources,automatic_current_rate_certified=False)
 def calculate(self,d):
  code=str(d.get('code',''));day=d.get('classification_date');look=self.lookup(code,day);scheme=d.get('scheme','MFN');trade=d.get('trade_type','import')
  if code.startswith('98')or look.get('requires_special_regime_review'):raise TaxError('Chương 98 cần xác định điều kiện và mã tham chiếu từng dòng; chưa hỗ trợ tự tính từ dòng đầu hoặc mức thấp nhất.')
  if trade not in {'import','export'}or scheme not in look['rates']or scheme in {'VAT','EXCISE','ENVIRONMENT'}:raise TaxError('Chọn đúng luồng và chế độ thuế XNK.')
  if(trade=='export')!=scheme.startswith('EXPORT'):raise TaxError('Chế độ thuế không khớp luồng XNK.')
  e=d.get('eligibility',{})
  if scheme not in {'MFN','ordinary','EXPORT'}and(not d.get('origin_country')or e.get('co_status')!='verified'or not all(e.get(k)for k in ['origin_rule_checked','transport_rule_checked','schedule_checked'])):raise TaxError('FTA cần xuất xứ, chứng từ được xác minh và đối chiếu quy tắc xuất xứ/vận chuyển/biểu cam kết.')
  if not d.get('operator_checked')or not str(d.get('reviewer','')).strip():raise TaxError('Cần người đối chiếu và xác nhận các giả định.')
  raw=look['rates'][scheme]['rate'];rate=d.get('duty_rate_percent')
  if rate is None:
   if raw['kind']!='ad_valorem':raise TaxError('Ô thuế không phải tỷ lệ phần trăm đơn nhất; đối chiếu điều kiện/thuế tuyệt đối/hỗn hợp. Không tự chọn mức thấp nhất.')
   rate=raw['percent']
  elif not str(d.get('duty_rate_source','')).strip():raise TaxError('Cần căn cứ mức thuế ghi đè.')
  rate=amount(rate,'Thuế suất XNK')
  if rate>2000:raise TaxError('Kiểm tra đơn vị phần trăm thuế XNK.')
  value,valuation=customs_value(d)
  if value<=0:raise TaxError('Trị giá tính thuế phải dương.')
  duty=value*rate/100;additional=amount(d.get('additional_import_duties_vnd',0),'Thuế NK bổ sung');excise=amount(d.get('excise_vnd',0),'TTĐB');environment=amount(d.get('environmental_vnd',0),'BVMT')
  if trade=='export'and(additional or excise or environment):raise TaxError('Không nhập khoản thuế nhập khẩu vào kịch bản xuất khẩu.')
  if(additional or excise or environment)and not str(d.get('other_taxes_source','')).strip():raise TaxError('Cần căn cứ các khoản NK bổ sung/TTĐB/BVMT đã nhập.')
  vat_base=value+duty+additional+excise+environment;vat=None;vat_rate=None;vat_status='not_evaluated_for_export'
  if trade=='import':
   vat_status=d.get('vat_treatment','taxable')
   if vat_status=='not_subject':vat=Decimal(0)
   elif vat_status=='taxable':
    if d.get('vat_rate_percent')is None:raise TaxError('Nhập mức VAT đã đối chiếu; không tự lấy mức thấp nhất của ô nhiều mức.')
    vat_rate=amount(d['vat_rate_percent'],'VAT')
    if vat_rate>100:raise TaxError('VAT không hợp lệ.')
    vat=vat_base*vat_rate/100
   else:raise TaxError('Chọn cách xử lý VAT.')
   if not str(d.get('vat_source','')).strip():raise TaxError('Cần căn cứ VAT hoặc diện không chịu VAT.')
  total=duty+(additional+excise+environment+(vat or 0)if trade=='import'else 0)
  def val(x):return str(x.quantize(Decimal('.01')))if x is not None else None
  return {'code':code,'classification_date':day,'trade_type':trade,'scheme':scheme,'customs_value_vnd':val(value),'duty_rate_percent':str(rate),'import_or_export_duty_vnd':val(duty),'additional_import_duties_vnd':val(additional),'excise_vnd':val(excise),'environmental_vnd':val(environment),'vat_base_vnd':val(vat_base)if trade=='import'else None,'vat_rate_percent':str(vat_rate)if vat_rate is not None else None,'vat_treatment':vat_status,'vat_vnd':val(vat),'total_taxes_vnd':val(total),'valuation':valuation,'reviewer':d['reviewer'],'duty_rate_source':d.get('duty_rate_source')or look['rates'][scheme]['legal_reference'],'vat_source':d.get('vat_source'),'other_taxes_source':d.get('other_taxes_source'),'origin_country':d.get('origin_country'),'eligibility_checks':e,'result_type':'operator_checked_scenario','current_rates_legally_certified':False,'source_snapshot_sha256':look['source_sha256'],'source_sheet':look['source_sheet'],'source_row':look['source_row'],'duty_source_cell':look['rates'][scheme]['source_cell'],'warnings':look['warnings'],'penalty_estimated':False,'used_to_choose_hs':False,'vat_base_reference':'181/2025/ND-CP Article5(2); review later amendments and special regimes','assumptions':'Standard ad valorem scenario; other tax amounts entered and verified by operator; quotas/exemptions/specific/mixed taxes not automatically determined'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workbook',required=True);p.add_argument('--output',required=True);a=p.parse_args();build_snapshot(a.workbook,a.output)
