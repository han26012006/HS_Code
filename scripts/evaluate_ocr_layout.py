"""Paired synthetic scan experiment using existing Tesseract, not real holdout."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from hs_assistant.ocr_layout import read_image
from hs_assistant.document_layout import build_layout

out=ROOT/'scratch/ocr_layout_evaluation';out.mkdir(parents=True,exist_ok=True)
font=ImageFont.truetype(str(ROOT/'hs_assistant/fonts/DejaVuSans.ttf'),24)
image=Image.new('RGB',(1500,500),'white');draw=ImageDraw.Draw(image)
draw.text((35,25),'COMMERCIAL INVOICE',fill='black',font=font)
draw.text((35,80),'Invoice No: SCAN-92',fill='black',font=font)
columns=[35,300,960,1240]
rows=[['SKU','Description','Qty','Unit'],['MECH-8','Mechanical coupling','24','PCS'],['CHEM-9','Polymer granules','80','KG']]
for row_index,row in enumerate(rows):
 for x,value in zip(columns,row):draw.text((x,160+row_index*65),value,fill='black',font=font)
path=out/'synthetic_invoice.png';image.save(path)
results={}
for enabled in (False,True):
 result=read_image(path,layout_enabled=enabled);layout=build_layout(result['text'],geometry=result['geometry'])
 identifiers=[c['text'] for table in layout['tables'] for row in table['rows'] for c in row['cells'] if c['field']=='model']
 results['tsv_layout' if enabled else 'plain_text']={'recognized_text':result['text'],'word_boxes':len(result['geometry']),'expected_row_identifiers':['MECH-8','CHEM-9'],'extracted_row_identifiers':identifiers,'row_identifiers_correct':len(set(identifiers)&{'MECH-8','CHEM-9'})}
report={'scope':'one generated clean English scan; not real-world OCR accuracy','engine':'existing Tesseract, psm 6','default_enabled':False,'results':results}
(out/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
