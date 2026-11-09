"""Reproduce cohort counts and compare the frozen v2 retrieval on matched bridge queries."""
import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter
import pandas as pd
from threadpoolctl import threadpool_limits
from hs_assistant.catalogue import Catalogue
from hs_assistant.precedents import PrecedentLibrary
from hs_assistant.retrieval_experiment import RetrievalExperiment, SELECTED_RECIPE

parser=argparse.ArgumentParser(description=__doc__)
for name in ('app','artifact','bridge','output'):
    parser.add_argument('--'+name,required=True,type=Path)
args=parser.parse_args()
data=args.app/'data'
artifact=args.artifact/'precedents.parquet'
manifest=json.loads((args.artifact/'pipeline_manifest.json').read_text())['sha256']
digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
if manifest['precedents.parquet']!=digest:
    raise ValueError('Artifact checksum mismatch')
protocol=json.loads((args.bridge/'protocol_before_fit.json').read_text())
if protocol['input_sha256']['precedents.parquet']!=digest:
    raise ValueError('The bridge belongs to a different snapshot')
cases=pd.read_parquet(artifact)
library=PrecedentLibrary(data/'precedent_index.jsonl')
cat=Catalogue(data/'catalogue.jsonl',data/'legal_notes.json')
engine=RetrievalExperiment(cat,library)
train=cases[cases.split.eq('train')]
info={'catalogue_codes':len(cat.by_code),'cohorts':{}}
for split,cohort in cases.groupby('split'):
    info['cohorts'][split] = {
        'n':len(cohort), 'distinct_hs8':cohort.hs8.nunique(), 'distinct_known_org_groups':cohort.nhom_dn.nunique(),
        'org_groups_missing':int(cohort.nhom_dn.isna().sum()),
        'from':str(cohort.ngay.min()), 'to':str(cohort.ngay.max()),
        'in_train_org_group_count':int(cohort.nhom_dn.dropna().isin(train.nhom_dn.dropna()).sum()) if split!='train' else None,
        'label_status':cohort.label_status.value_counts().to_dict(),
    }
info['train_codes_with_one_notice']=int((train.hs8.value_counts()==1).sum())
info['train_codes_in_catalogue']=len(set(train.hs8)&set(cat.by_code))
info['seen_by_prior_cutoff']='test and validation both follow latest train date'
pool=args.bridge/'queries_NO_GOLD.jsonl'
pairs=Counter()
metrics={k:Counter() for k in ('07_hybrid','guided_v1','guided_v2','union_07_and_v2_oracle_not_deployable')}
gold=json.loads((pool.parent/'valid_gold_NOT_MODEL_INPUT.json').read_text())
with threadpool_limits(limits=4), pool.open() as stream:
    rows=[json.loads(line) for line in stream if line.strip()]
    assert set(gold)=={r['case_id'] for r in rows}
    for row in rows:
        key=row['case_id'];ref=gold[key];notice=cases.iloc[int(key)]
        assert row['split']==notice.split=='valid' and ref==notice.hs8
        day=pd.Timestamp(notice.ngay).date().isoformat()
        channels,_=engine.experiment_channels(row['query'],day)
        v1=engine.rank(channels,'guided_v1')[:30]
        v2=engine.rank(channels,SELECTED_RECIPE)[:30]
        baseline=row['codes'][:30]
        pairs['v2_only']+=ref in v2 and ref not in baseline
        pairs['07_only']+=ref in baseline and ref not in v2
        for mode,p in [('07_hybrid',baseline),('guided_v1',v1),('guided_v2',v2)]:
            c=metrics[mode]
            c['n']+=1
            c['recall30']+=ref in p
            c['top1']+=p[:1]==[ref]
            c['hs4_top3']+=ref[:4] in list(dict.fromkeys(code[:4] for code in p))[:3]
            c['unseen_recall30']+=ref not in set(train.hs8) and ref in p
        metrics['union_07_and_v2_oracle_not_deployable']['hits']+=ref in baseline or ref in v2
info['validation_clean_bridge']=metrics
info['paired_recall_07_vs_guided_v2']=pairs
with args.output.open('x',encoding='utf-8') as f:
    json.dump(info,f,ensure_ascii=False,indent=2)
print(json.dumps(info,ensure_ascii=False,indent=2))
