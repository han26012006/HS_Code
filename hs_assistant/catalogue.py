"""Search a versioned Vietnamese catalogue; rank is not a calibrated HS8 probability."""
from __future__ import annotations
import hashlib,json,os,re,threading,time,unicodedata
from pathlib import Path
import numpy as np

def fold(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s)) if unicodedata.category(c)!='Mn').replace('đ','d').replace('Đ','D').lower()
def tokens(s):return re.findall(r'[a-z0-9]+',fold(s))
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

class Catalogue:
    def __init__(self,path,notes_path):
        self.path=Path(path);self.rows=[json.loads(l) for l in self.path.read_text(encoding='utf-8').splitlines() if l.strip()];self.by_code={r['code']:r for r in self.rows};self.notes=json.loads(Path(notes_path).read_text(encoding='utf-8'));self._index=None;self.lock=threading.Lock();self.version=sha(path)[:12]
    def _ensure_index(self):
        if self._index is None:
            with self.lock:
                if self._index is None:
                    from sklearn.feature_extraction.text import CountVectorizer
                    from scipy import sparse
                    cv=CountVectorizer(analyzer=tokens);X=cv.fit_transform([r['path']+' '+r.get('path_en','') for r in self.rows]).tocoo().astype(np.float32);n=X.shape[0];lengths=np.asarray(X.tocsr().sum(1)).ravel();df=np.bincount(X.col,minlength=X.shape[1]);idf=np.log(1+(n-df+.5)/(df+.5));weights=idf[X.col]*X.data*2.5/(X.data+1.5*(.25+.75*lengths[X.row]/max(lengths.mean(),1)))
                    self._index=(cv,sparse.csr_matrix((weights,(X.row,X.col)),shape=X.shape))
    def search(self,q,limit=15,chapter=None):
        clean=re.sub(r'[.\s]','',str(q));indices=None
        if clean.isdigit() and len(clean)>=2:
            indices=[i for i,r in enumerate(self.rows) if r['code'].startswith(clean)]
            scores={i:1 for i in indices}
        elif q.strip():
            self._ensure_index();cv,W=self._index;sc=np.asarray((cv.transform([q])@W.T).toarray()).ravel();indices=np.argsort(-sc,kind='stable').tolist();scores=dict(enumerate(sc))
            indices=[i for i in indices if sc[i]>0]
        else:indices=list(range(len(self.rows)));scores={}
        if chapter:indices=[i for i in indices if self.rows[i]['chapter']==chapter]
        return [dict(self.rows[i],rank=j+1,retrieval_score=round(float(scores.get(i,0)),4),score_is_probability=False) for j,i in enumerate(indices[:limit])]
    def note_search(self,q,scope=None,limit=12):
        terms=set(tokens(q));rows=[x for x in self.notes if not scope or x['scope']==scope]
        for x in rows:
            x=dict(x);x['retrieval_hits']=sum(t in fold(x['text']+' '+x['title']) for t in terms)
        return sorted([dict(x,retrieval_hits=sum(t in fold(x['text']+' '+x['title']) for t in terms)) for x in rows],key=lambda x:-x['retrieval_hits'])[:limit]

QUESTIONS={
 'steel':[('specifications','Chiều rộng, chiều dày thực tế của từng SKU là bao nhiêu? Giữ đúng đơn vị và ngưỡng trong mô tả phân nhóm.'),('material','Thành phần hợp kim và trạng thái không gỉ có được chứng minh bằng chứng thư cho đúng lô hàng?'),('manufacturing','Hàng được cán nóng hay cán nguội? Có gia công thêm, tráng hoặc phủ bề mặt không?')],
 'feed':[('material','Thành phần và tỷ lệ từng nguyên liệu, đối tượng vật nuôi và mục đích sử dụng là gì?'),('manufacturing','Nguyên liệu được tạo thành bởi quá trình sản xuất nào; là phụ phẩm hay chế phẩm phối trộn?'),('packaging','Quy cách đóng gói bán lẻ hay nguyên liệu số lượng lớn?')],
 'laser':[('construction','Cơ chế tác động là quang sinh học, nhiệt hay cơ chế khác? Cần tài liệu nhà sản xuất.'),('specifications','Loại nguồn phát, bước sóng, công suất và cấu hình hệ thống là gì?'),('function','Công dụng thiết kế cụ thể là chẩn đoán, điều trị, thẩm mỹ hay gia công? Phân loại thiết bị y tế không tự quyết định HS.')],
 'chemical':[('material','Có thành phần hóa học, tỷ lệ và chứng thư phân tích của đúng sản phẩm không?'),('function','Hàng là một hợp chất riêng biệt hay chế phẩm, công dụng chính là gì?'),('manufacturing','Có pha trộn, biến tính hoặc xử lý khác sau sản xuất không?')],
 'machine':[('construction','Hàng là máy hoàn chỉnh, bộ phận hay tổ hợp? Chức năng chính và nguyên lý hoạt động là gì?'),('specifications','Công suất, điện áp, năng suất hoặc thông số phân biệt nào được ghi trên datasheet?')],
 'electronic':[('construction','Chức năng chính, mức độ hoàn chỉnh và thiết bị sử dụng kèm là gì?'),('specifications','Có thông số điện áp, công suất hoặc tần số phù hợp với mô tả phân nhóm không?')],
 'food':[('material','Thành phần và tỷ lệ đường, chất béo, thịt, sữa hoặc nguyên liệu quyết định là gì?'),('manufacturing','Đã chế biến bằng cách nào, ở trạng thái và dạng đóng gói nào?')]
}

class InferenceService:
    def __init__(self,catalogue,artifact_path=None,instruction_out=None):
        self.catalogue=catalogue;self.artifact=Path(artifact_path) if artifact_path else None;self.assistant=None;self.model_error=None;self.lock=threading.RLock()
        from .instruction_adapter import InstructionAdapter
        self.instruction=InstructionAdapter(catalogue,instruction_out or Path('runtime/instruction'))
    def status(self):
        available=bool(self.artifact and (self.artifact/'ranker.joblib').is_file())
        return dict(self.instruction.status(),**{'catalogue_rows':len(self.catalogue.rows),'catalogue_version':self.catalogue.version,'model_artifacts_available':available,'model_loaded':self.assistant is not None,'model_error':self.model_error,'automatic_hs8_acceptance_enabled':False,'default_engine':'catalogue','score_is_probability':False,'artifact_version':'v4' if self.artifact and (self.artifact/'pipeline_manifest.json').exists() else ('legacy' if available else 'not_loaded')})
    def analyze(self,sku,engine='catalogue',allow_paid_api=False):
        facts=[f for f in sku['facts'] if f['status']=='verified'];fields={f['field'] for f in facts}
        if not {'name','function'}<=fields:raise ValueError('Xác minh tên/bản chất hàng và công dụng trước khi lấy gợi ý. Nội dung OCR chưa kiểm tra không tự đi vào model.')
        query='\n'.join(f"{f['field']}: {f['value']}" for f in facts)
        # Explicit HS references are not product attributes.
        query=re.sub(r'(?i)(?:HS(?:\s*code)?|mã\s*(?:HS|số))\s*[:.\-]?\s*\d[\d .]{3,18}','[MÃ ĐÃ TÁCH]',query)
        start=time.monotonic();warnings=[];legacy=None;llm=None
        if engine=='model':
            if not self.status()['model_artifacts_available']:raise ValueError('Chưa có artifact model. Đặt HS_ART trỏ tới artifact đã hoàn tất; tra cứu danh mục vẫn dùng được.')
            with self.lock:
                try:
                    if self.assistant is None:
                        from .core import HSAssistant
                        self.assistant=HSAssistant(str(self.artifact),precedent_splits=('train',))
                    legacy=self.assistant.classify(query,k=10)
                except Exception as e:
                    self.model_error=type(e).__name__+': '+str(e)[:300]
                    raise ValueError('Không chạy được model đã cấu hình. Xem trạng thái vận hành; không tự đổi engine hoặc cắt dữ liệu.') from e
            candidates=[dict(self.catalogue.by_code[x['ma8']],rank=i+1,model_score=x['xac_suat'],score_is_probability=False) for i,x in enumerate(legacy['ma_de_xuat']) if x['ma8'] in self.catalogue.by_code]
            model_version=legacy['phien_ban_mo_hinh'];warnings.append('Điểm xếp hạng và độ tin cậy HS4 không phải xác suất đúng HS8.')
        elif engine in {'qwen','openai'}:
            try:candidates,llm=self.instruction.rerank(query,engine,allow_paid_api)
            except Exception as e:raise ValueError(str(e)[:700]) from e
            model_version=llm.get('model',engine);warnings.append('Model chỉ dẫn thử nghiệm của notebook 07; chưa vượt kiểm thử HS8 độc lập. Chú giải và GRI chưa được áp dụng đầy đủ trong prompt hiện tại.')
            if not llm.get('accepted'):warnings.append('Model chưa đưa ra gợi ý hợp lệ: '+llm['status']+'. Các dòng bên dưới vẫn là truy hồi BM25 để chuyên gia kiểm tra.')
        else:
            candidates=self.catalogue.search(query,limit=10);model_version=self.catalogue.version;warnings.append('Đối chứng BM25 trên danh mục; chưa áp dụng đầy đủ GRI, chú giải hoặc suy luận phân loại.')
        questions=[]
        if llm:
            for missing in llm.get('parsed',{}).get('missing_attributes',[]):questions.append({'field':'llm_requested','question':missing,'status':'missing'})
        for field,text in QUESTIONS.get(sku.get('product_family'),[('material','Vật liệu/thành phần, trạng thái hàng và thông số nào phân biệt các dòng đang xem?'),('construction','Có tài liệu về cấu tạo và công dụng thiết kế không?')]):
            if field not in fields:questions.append({'field':field,'question':text,'status':'missing'})
        if any(f['status']=='conflict' for f in sku['facts']):warnings.append('Có thuộc tính đang mâu thuẫn; chưa thể duyệt mã.')
        if not candidates:warnings.append('Không truy hồi được dòng phù hợp; cần tra cứu bổ sung hoặc chuyển chuyên gia.')
        if candidates:
            questions.append({'field':'candidate_conditions','question':'Đối chiếu các điều kiện khác nhau trong mô tả các dòng cùng cấp; không mặc định chọn “Loại khác”.','status':'review','options':[{'code':x['code'],'condition':x['path']} for x in candidates[:3]]})
        return {'engine':engine,'instruction_result':llm,'engine_label':{'model':'Model của dự án','qwen':'Qwen 4B · thử nghiệm 07','openai':'OpenAI · thử nghiệm 07','catalogue':'Tra cứu danh mục · BM25'}.get(engine,engine),'model_version':model_version,'input_hash':hashlib.sha256(query.encode()).hexdigest(),'input_text':query,'input_fact_ids':[f['id'] for f in facts],'candidates':candidates,'questions':questions,'warnings':warnings,'human_review_required':True,'calibrated_hs8_confidence':None,'auto_accept':False,'elapsed_ms':int((time.monotonic()-start)*1000),'source_notes':[{'id':x['id'],'title':x['title'],'scope':x['scope'],'kind':x['kind'],'text':x['text'],'verified_applicability':False} for x in self.catalogue.notes if candidates and x['scope']==candidates[0]['chapter']][:2],'precedent_references':legacy.get('tien_le_gan_nhat',[]) if legacy else []}
