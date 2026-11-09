from pathlib import Path
from collections import Counter
import argparse, hashlib, json
import pandas as pd
from threadpoolctl import threadpool_limits
from hs_assistant.catalogue import Catalogue
from hs_assistant.precedents import PrecedentLibrary
from hs_assistant.retrieval_experiment import RetrievalExperiment, RECIPES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score(cohort, rankings, seen):
    results = {}
    for recipe, pools in rankings.items():
        c = Counter()
        for key, code, pool in zip(cohort.index, cohort.hs8, pools, strict=True):
            c["n"] += 1
            c["hs8_top1"] += pool[:1] == [code]
            c["recall30"] += code in pool[:30]
            c["recall200"] += code in pool[:200]
            c["hs4_top3"] += code[:4] in list(dict.fromkeys(k[:4] for k in pool))[:3]
            c["unseen_n"] += code not in seen
            c["unseen_recall30"] += code not in seen and code in pool[:30]
        results[recipe] = dict(c)
    return results


def main():
    p = argparse.ArgumentParser()
    for key in ("app", "artifact", "output"):
        p.add_argument("--"+key, required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    manifest = a.artifact/"pipeline_manifest.json"
    data = a.artifact/"precedents.parquet"
    if sha(data) != json.loads(manifest.read_text())["sha256"][data.name]:
        raise ValueError("Artifact hash mismatch")
    d = pd.read_parquet(data)
    train = d[d.split.eq("train")]
    cat = Catalogue(a.app/"data/catalogue.jsonl",a.app/"data/legal_notes.json")
    prior = PrecedentLibrary(a.app/"data/precedent_index.jsonl")
    if {r["source_name"] for r in prior.rows} != set(train.file):
        raise ValueError("Training corpus mismatch")
    engine = RetrievalExperiment(cat,prior)
    def save(name,obj):
        (a.output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
    def evaluate(split, recipes):
        cohort = d[d.split.eq(split)]
        rankings = {name:[] for name in recipes}
        rankings["bm25"]=[]
        for r in cohort.itertuples():
            channels, _ = engine.experiment_channels(r.input_text, pd.Timestamp(r.ngay).date().isoformat())
            for name in recipes:
                rankings[name].append(engine.rank(channels,name))
            rankings["bm25"].append(channels["catalogue_bm25"])
        return score(cohort,rankings,set(train.hs8))
    save("protocol.json",{
        "input_scope":"archived descriptions, not app verified fields",
        "recipes":RECIPES,"source_sha256":sha(Path(__file__)),
        "experiment_sha256":sha(a.app/"hs_assistant/retrieval_experiment.py"),
        "manifest_sha256":sha(manifest),"index_sha256":prior.version,"catalogue_sha256":sha(cat.path),
        "selection":"Improve Recall@30 by at least 2 cases; preserve HS8 Top1 and HS4 Top3 against guided_v1. Maximize Recall@30.",
        "test_used_for_selection":False,"labels_provisional":True,"test_seen_before_study":True,
    })
    valid = evaluate("valid",RECIPES)
    control = valid["guided_v1"]
    eligible = [k for k in RECIPES if k != "guided_v1" and valid[k]["recall30"] >= control["recall30"] + 2
                and all(valid[k][m] >= control[m] for m in ("hs8_top1","hs4_top3"))]
    selected = max(eligible,key=lambda k:(valid[k]["recall30"],valid[k]["hs4_top3"],valid[k]["hs8_top1"])) if eligible else "guided_v1"
    save("selection.json",{"selected":selected,"validation":valid})
    print("validation",json.dumps(valid),"selected",selected,flush=True)
    test = evaluate("test",dict.fromkeys(["guided_v1",selected]))
    save("historical.json",test)
    print("historical",json.dumps(test),flush=True)


if __name__=="__main__":
    with threadpool_limits(limits=4):
        main()
