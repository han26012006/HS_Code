"""Offline controlled reranking on the same HS8 candidates as M0."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

K = 200
SEED = 20261104
MODELS = (
    "m0", "pairwise_hs8", "pairwise_hierarchy", "hist_gradient",
    "pairwise_plus_m0", "hierarchy_plus_m0",
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def read_split(root, manifest, split, cases, bundle):
    path = root / f"features_{split}.npz"
    if digest(path) != manifest[path.name]:
        raise ValueError(f"Checksum mismatch for {path.name}")
    with np.load(path, allow_pickle=False) as raw:
        all_features, ids, codes, labels = (raw[n] for n in ("X", "qi", "cand", "y"))
    if (not np.array_equal(np.unique(ids), np.flatnonzero(cases.split.eq(split)))
            or not np.isfinite(all_features).all()
            or np.any(labels != (codes == cases.hs8.to_numpy()[ids]))):
        raise ValueError(f"Invalid candidate coverage or labels: {split}")
    scores = bundle["ranker"].decision_function(bundle["scaler"].transform(all_features[:, bundle["FEAT_IDX"]]))
    result = {}
    for key in np.unique(ids):
        local = np.flatnonzero(ids == key)
        order = local[np.argsort(-scores[local], kind="stable")[:K]]
        if len(set(codes[local])) != len(local):
            raise ValueError(f"Duplicate HS8 for case {key}")
        result[int(key)] = (codes[order], all_features[order])
    return result


def pairs(rows, targets, *, hierarchical):
    rng = np.random.default_rng(SEED)
    diffs, weights = [], []
    for key, (codes, X) in rows.items():
        gold = targets[key]
        if hierarchical:
            grades = np.array([3 if c == gold else 2 if c[:6] == gold[:6] else 1 if c[:4] == gold[:4] else 0 for c in codes])
        else:
            grades = (codes == gold).astype(int)
        case_pairs = []
        for grade in np.unique(grades)[1:]:
            positives = np.flatnonzero(grades == grade)[:8]
            pool = np.flatnonzero(grades < grade)
            negatives = np.unique(np.r_[pool[:24], rng.choice(pool, min(len(pool), 16), replace=False)])
            for pos in positives:
                case_pairs.extend(X[pos] - X[negatives])
        if case_pairs:
            diffs.extend(case_pairs)
            weights.extend([1 / len(case_pairs)] * len(case_pairs))
    diffs = np.asarray(diffs)
    y = np.repeat([1, 0], len(diffs))
    w = np.tile(weights, 2)
    return np.vstack((diffs, -diffs)), y, w / w.mean()


def fit(rows, cases):
    scaler = StandardScaler().fit(np.concatenate([X for _, X in rows.values()]))
    targets = cases.hs8.to_numpy()
    pair_models = []
    for hierarchical in (False, True):
        scaled = {key: (c, scaler.transform(X)) for key, (c, X) in rows.items()}
        X, y, w = pairs(scaled, targets, hierarchical=hierarchical)
        pair_models.append(LogisticRegression(C=0.3, max_iter=400).fit(X, y, sample_weight=w))
    Xs, ys, ws = [], [], []
    for key, (codes, X) in rows.items():
        y = codes == targets[key]
        if not y.any():
            continue
        Xs.append(X)
        ys.append(y)
        ws.append(np.where(y, 0.5 / y.sum(), 0.5 / (~y).sum()))
    w = np.concatenate(ws)
    boost = HistGradientBoostingClassifier(max_iter=140, max_leaf_nodes=7, min_samples_leaf=25,
                                           l2_regularization=4.0, random_state=SEED)
    boost.fit(np.concatenate(Xs), np.concatenate(ys), sample_weight=w / w.mean())
    return scaler, *pair_models, boost


def rank(rows, trained, names):
    scaler, exact, hierarchy, boost = trained
    rankings = {name: {} for name in names}
    for key, (codes, X) in rows.items():
        norm = scaler.transform(X)
        scores = {
            "pairwise_hs8": exact.decision_function(norm),
            "pairwise_hierarchy": hierarchy.decision_function(norm),
            "hist_gradient": boost.decision_function(X),
        }
        order = {name: np.argsort(-value, kind="stable") for name, value in scores.items()}
        order["m0"] = np.arange(len(codes))
        for alias, base in (("pairwise_plus_m0", "pairwise_hs8"), ("hierarchy_plus_m0", "pairwise_hierarchy")):
            other_rank = np.argsort(order[base])
            order[alias] = np.argsort(-(1/(20+order["m0"])+1/(20+other_rank)), kind="stable")
        for name in names:
            rankings[name][key] = codes[order[name]].tolist()
    return rankings


def metric(pred, cases, seen, known_org, strict_ids):
    def measure(ids):
        n = len(ids)
        top1 = hs6 = hs4 = recall30 = recall200 = 0
        for i in ids:
            gold, codes = cases.at[i, "hs8"], pred[i]
            top1 += codes[0] == gold
            hs6 += codes[0][:6] == gold[:6]
            hs4 += gold[:4] in list(dict.fromkeys(c[:4] for c in codes))[:3]
            recall30 += gold in codes[:30]
            recall200 += gold in codes
        return dict(n=n, hs8_top1=top1, hs6_top1=hs6, hs4_top3=hs4, recall30=recall30, recall200=recall200)
    return {"all": measure(list(pred)),
            "unseen_hs8": measure([i for i in pred if cases.at[i,"hs8"] not in seen]),
            "heldout_company": measure([i for i in pred if pd.notna(cases.at[i,"nhom_dn"]) and cases.at[i,"nhom_dn"] not in known_org]),
            "strict_historical_slice": measure([i for i in pred if i in strict_ids])}


def run(artifact, output, audit_path):
    manifest_path = artifact / "pipeline_manifest.json"
    manifest = json.loads(manifest_path.read_text())["sha256"]
    for name in ("precedents.parquet", "ranker.joblib", "predictions.json"):
        if digest(artifact / name) != manifest[name]:
            raise ValueError(f"Checksum mismatch for {name}")
    audit = json.loads(audit_path.read_text())
    if audit["manifest_sha256"] != digest(manifest_path):
        raise ValueError("Audit belongs to another dataset")
    strict_ids = {i for s in audit["splits"].values() for i in s["strict_slice_case_ids"]}
    cases = pd.read_parquet(artifact / "precedents.parquet")
    bundle = joblib.load(artifact / "ranker.joblib")
    saved = json.loads((artifact / "predictions.json").read_text())
    train_cases = cases[cases.split.eq("train")]
    seen, known_org = set(train_cases.hs8), set(train_cases.nhom_dn.dropna())
    output.mkdir(parents=True, exist_ok=False)
    write(output / "PROTOCOL.json", {"manifest_sha256": digest(manifest_path), "code_sha256": digest(Path(__file__)), "audit_sha256": digest(audit_path),
        "pool": "fixed M0 top 200, no insertion of gold into validation or test", "models": MODELS, "random_seed": SEED,
        "gate": "Gain >=2 HS8 Top 1 on validation, no regression on HS4 Top 3, HS6 Top 1, Recall@30, unseen HS8 Top 1 or heldout-company HS8 Top 1",
        "test_historically_seen": True, "production_promotion": False, "gold_is_provisional": True})
    train = read_split(artifact, manifest, "train", cases, bundle)
    valid = read_split(artifact, manifest, "valid", cases, bundle)
    for r in saved["full_valid"]:
        assert valid[int(r["qi"])][0][:10].tolist() == r["codes"][:10]
    trained = fit(train, cases)
    valid_preds = rank(valid, trained, MODELS)
    metrics = {name: metric(p, cases, seen, known_org, strict_ids) for name,p in valid_preds.items()}
    controls = metrics["m0"]
    protected = ("hs4_top3", "hs6_top1", "recall30")
    eligible = [n for n in MODELS[1:] if metrics[n]["all"]["hs8_top1"] >= controls["all"]["hs8_top1"] + 2
                and all(metrics[n]["all"][k] >= controls["all"][k] for k in protected)
                and all(metrics[n][s]["hs8_top1"] >= controls[s]["hs8_top1"] for s in ("unseen_hs8","heldout_company"))]
    best = max(MODELS[1:], key=lambda n: metrics[n]["all"]["hs8_top1"])
    selected = max(eligible,key=lambda n: metrics[n]["all"]["hs8_top1"]) if eligible else "m0"
    write(output / "VALIDATION_FREEZE.json", {"selected": selected,"best_challenger_by_hs8":best,
        "eligible": eligible, "validation": metrics, "test_used_for_selection": False,
        "train_cases_with_gold_in_fixed_pool":sum(cases.at[q,"hs8"] in c for q,(c,_) in train.items())})
    test = read_split(artifact, manifest, "test", cases, bundle)
    for r in saved["full_test"]:
        assert test[int(r["qi"])][0][:10].tolist() == r["codes"][:10]
    ranks = rank(test, trained, tuple(dict.fromkeys(("m0", selected, best))))
    report = {name:metric(p,cases,seen,known_org,strict_ids) for name,p in ranks.items()}
    pairs_test = {}
    for name in ranks.keys() - {"m0"}:
        wins = losses = 0
        for i in test:
            gold = cases.at[i,"hs8"]
            hit = ranks[name][i][0] == gold
            base = ranks["m0"][i][0] == gold
            wins += hit and not base
            losses += base and not hit
        pairs_test[name] = {"wins":wins, "losses":losses,
                            "exploratory_exact_p_unclustered":float(binomtest(wins,wins+losses).pvalue) if wins+losses else None}
    write(output / "HISTORICAL_TEST.json", {"metrics":report,"paired_top1":pairs_test})
    print(json.dumps({"selected":selected,"valid":{n:r["all"] for n,r in metrics.items()},"test":report,"paired":pairs_test}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    args = p.parse_args()
    with threadpool_limits(limits=4):
        run(args.artifact,args.output,args.audit)
