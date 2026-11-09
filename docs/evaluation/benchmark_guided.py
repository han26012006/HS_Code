"""Replay packaged retrieval on a checksum-verified provisional snapshot."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from hs_assistant.catalogue import Catalogue
from hs_assistant.guided_retrieval import GuidedRetrieval, CHANNELS
from hs_assistant.precedents import PrecedentLibrary

RECIPES = {
    "catalogue_bm25": ({CHANNELS[0]: 1}, False),
    "catalogue_char": ({CHANNELS[1]: 1}, False),
    "prior_char": ({CHANNELS[2]: 1}, False),
    "catalogue_fusion": (dict.fromkeys(CHANNELS[:2], 1), False),
    "fusion_equal": (dict.fromkeys(CHANNELS, 1), False),
    "fusion_prior2": (dict(dict.fromkeys(CHANNELS, 1), prior_char=2), False),
    "fusion_equal_hs6": (dict.fromkeys(CHANNELS, 1), True),
    "fusion_prior2_hs6": (dict(dict.fromkeys(CHANNELS, 1), prior_char=2), True),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(guided, rows, recipes):
    results = {key: dict(n=len(rows), hs4_top1=0, hs4_top3=0, hs8_top1=0,
                         recall30=0, recall200=0) for key in recipes}
    for row in rows.itertuples():
        if pd.isna(row.ngay):
            raise ValueError("Historical replay requires a case date")
        day = pd.Timestamp(row.ngay).date().isoformat()
        channels, _ = guided.channels(row.input_text, day)
        gold = row.hs8
        for key, (weights, expand) in recipes.items():
            pool = guided.combine(channels, weights, expand)
            heads = list(dict.fromkeys(code[:4] for code in pool))
            r = results[key]
            r["hs4_top1"] += heads[:1] == [gold[:4]]
            r["hs4_top3"] += gold[:4] in heads[:3]
            r["hs8_top1"] += pool[:1] == [gold]
            r["recall30"] += gold in pool[:30]
            r["recall200"] += gold in pool[:200]
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("app", "artifact", "output"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    art, app, out = args.artifact, args.app, args.output
    manifest_path = art / "pipeline_manifest.json"
    manifest = json.loads(manifest_path.read_text())["sha256"]
    data = art / "precedents.parquet"
    if sha(data) != manifest[data.name]:
        raise ValueError("Precedent rows do not match the manifest")
    cases = pd.read_parquet(data)
    train = cases[cases.split.eq("train")]
    cat = Catalogue(app / "data/catalogue.jsonl", app / "data/legal_notes.json")
    priors = PrecedentLibrary(app / "data/precedent_index.jsonl")
    if {r["source_name"] for r in priors.rows} != set(train.file) or any(r["split"] != "train" for r in priors.rows):
        raise ValueError("Serving reference index does not match this snapshot's training cases")
    out.mkdir(parents=True, exist_ok=False)

    def dump(name, values):
        (out / (name + ".json")).write_text(json.dumps(values, indent=2) + "\n")

    dump("PROTOCOL", {"recipes": RECIPES, "manifest_sha256": sha(manifest_path), "catalogue_sha256": sha(cat.path),
        "precedents_sha256": priors.version, "labels_provisional": True, "test_previously_seen": True,
        "input_scope": "archived descriptions, not verified fact UI payloads", "selection":
        "Protect BM25 HS4 and HS8 Top1; maximize Recall@200, then HS4 Top3, then HS8 Top1"})
    guided = GuidedRetrieval(cat, priors)
    valid = evaluate(guided, cases[cases.split.eq("valid")], RECIPES)
    ref = valid["catalogue_bm25"]
    safe = [name for name,m in valid.items() if m["hs4_top1"] >= ref["hs4_top1"] and m["hs8_top1"] >= ref["hs8_top1"]]
    selected = max(safe, key=lambda k: (valid[k]["recall200"], valid[k]["hs4_top3"], valid[k]["hs8_top1"]))
    dump("SELECTION", {"selected": selected, "metrics": valid, "test_used_for_selection": False})
    test = evaluate(guided, cases[cases.split.eq("test")],
                    {k:RECIPES[k] for k in ("catalogue_bm25", selected)})
    dump("HISTORICAL", test)
    print(json.dumps({"selected":selected,"historical":test}, indent=2))


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()
