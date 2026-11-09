"""Opt-in notebook-07 challengers; no automatic model promotion or API fallback."""
import hashlib,json,os,threading,time
from pathlib import Path
from .instruction_protocol import LocalRunner,OpenAIRunner,validate_response,dump,digest,MODEL,REVISION,VERSION,MAX_INPUT,SYSTEM

class InstructionAdapter:
    def __init__(self,catalogue,out):
        self.catalogue=catalogue;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True);self.runners={};self.lock=threading.RLock()
    def status(self):
        return {'qwen_enabled':os.environ.get('HS_ENABLE_QWEN')=='1','openai_enabled':os.environ.get('HS_ENABLE_OPENAI')=='1' and bool(os.environ.get('OPENAI_API_KEY')),'openai_model':'gpt-5.4-mini-2026-03-17','api_max_calls':int(os.environ.get('HS_API_MAX_CALLS','12')),'api_max_usd_estimate':float(os.environ.get('HS_API_MAX_USD','.5')),'challenger_validation_passed':False}
    def rerank(self,query,engine,allow_paid_api=False):
        config=self.status()
        if engine=='qwen' and not config['qwen_enabled']:raise ValueError('Nhánh Qwen đang tắt. Cần GPU, trọng số đã cache và HS_ENABLE_QWEN=1.')
        if engine=='openai' and (not config['openai_enabled'] or not allow_paid_api):raise ValueError('Nhánh OpenAI cần cấu hình trên máy chủ và xác nhận gửi thuộc tính ra API ở từng lượt. Không phát sinh yêu cầu trả phí.')
        pool=self.catalogue.search(query,200)
        if not pool:return [],{'status':'no_candidates','accepted':False,'paid_api_calls':0}
        row={'query':query,'codes':[x['code'] for x in pool]}
        version=MODEL+'@'+REVISION if engine=='qwen' else config['openai_model']
        identity={'prompt_sha256':digest(SYSTEM),'protocol':VERSION,'catalogue':self.catalogue.version,'model':version,'query':query,'codes':row['codes']}
        key=digest(identity);row['case_id']=key
        folder=self.out/engine;folder.mkdir(parents=True,exist_ok=True);cache=folder/(key+'.json')
        with self.lock:
            if cache.exists():result=json.loads(cache.read_text());result['reused_cached_response']=True
            else:
                runner=self.runners.get(engine)
                if runner is None:
                    runner=LocalRunner(folder,256) if engine=='qwen' else OpenAIRunner(folder,version,config['api_max_calls'],config['api_max_usd_estimate']);self.runners[engine]=runner
                n=runner.preflight(row,self.catalogue.by_code);limit=MAX_INPUT if engine=='qwen' else 120000
                if n>limit:result={'accepted':False,'status':'context_budget_exceeded','input_tokens':n,'paid_api_calls':0}
                else:
                    raw,usage=runner.call(row,self.catalogue.by_code);result=dict(validate_response(raw,row,self.catalogue.by_code),usage=usage,raw_output=raw,input_tokens=n)
                result.update(protocol=VERSION,model=version,candidate_count=len(pool),candidate_codes=row['codes'],query_sha256=hashlib.sha256(query.encode()).hexdigest(),reused_cached_response=False,notes_in_prompt=False)
                dump(cache,result)
        if result.get('accepted'):
            parsed=result['parsed'];order=list(dict.fromkeys([parsed['hs8']]+parsed['alternatives']+row['codes']));lookup={r['code']:r for r in pool};pool=[lookup[x] for x in order]
        return [dict(x,rank=i+1) for i,x in enumerate(pool[:10])],result
