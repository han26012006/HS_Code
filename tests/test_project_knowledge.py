import json,io
from hs_assistant.project_knowledge import build_index,ProjectKnowledge
from hs_assistant.documents import DocumentService
from hs_assistant.workspace import Workspace

def test_search_provenance_and_unverified_role(tmp_path):
 (tmp_path/'knowledge_chunks.jsonl').write_text(json.dumps(dict(id='a',document_sha256='sha1',source_name='Nguồn kiểm thử',unit=2,unit_kind='sheet',sheet='Thông số',roles=['technical_evidence'],text='Nhôm có độ dày3mm. Dữ liệu giả lập kiểm thử.'),ensure_ascii=False)+'\n')
 r=build_index(tmp_path);assert r['indexed_chunks']==1
 rows=ProjectKnowledge(tmp_path).search('nhom');assert rows[0]['document_sha256']=='sha1'and rows[0]['unit']==2 and rows[0]['sheet']=='Thông số'and not rows[0]['score_is_probability']
 assert ProjectKnowledge(tmp_path).search('xyznonexistent')==[]

def test_rtf_doc_and_pptx(tmp_path):
 from pptx import Presentation
 from pptx.util import Inches
 db=Workspace(tmp_path/'workspace.sqlite');case=db.create_case('Hồ sơ kiểm thử','Người lập');service=DocumentService(db,tmp_path/'uploads')
 try:
  r=service.upload(case['id'],'invoice.doc',b'{\\rtf1\\ansi Invoice technical description12mm}');service.close();assert'12mm'in service.pages(r['documents'][0]['id'])[0]['text']
  service=DocumentService(db,tmp_path/'uploads');p=Presentation();sl=p.slides.add_slide(p.slide_layouts[6]);sl.shapes.add_textbox(Inches(1),Inches(1),Inches(6),Inches(1)).text='Manufacturing technical evidence';b=io.BytesIO();p.save(b);r=service.upload(case['id'],'technical.pptx',b.getvalue());service.close();assert'Manufacturing'in service.pages(r['documents'][0]['id'])[0]['text']
 finally:service.close()
