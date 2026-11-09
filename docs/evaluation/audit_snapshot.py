"""Audit provenance and construct a conservative, company/near-text disjoint slice."""
import argparse
import csv
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from threadpoolctl import threadpool_limits

from hs_assistant.retrieval_experiment import normalize_description

SPLITS = ("train", "valid", "test")
SIMILARITY_THRESHOLD = 0.90


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def coverage_report(path, expected_digest, catalogue):
    if digest(path) != expected_digest:
        raise ValueError("Coverage ledger does not match frozen artifact")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len({r["file"] for r in rows}) != len(rows):
        raise ValueError("Coverage ledger has duplicate filenames")
    held = [r for r in rows if r["included"].casefold() == "false"]
    reasons = Counter(reason for r in held for reason in r["reason"].split(";") if reason)
    priority = []
    for r in held:
        if r["reason"] != "outside_frozen_cohort_quarantine":
            continue
        code = re.fullmatch(r"([0-9]{8})(?:[.]0)?", r["new_hs8"])
        if code and code[1] in catalogue:
            priority.append({"file":r["file"],"ocr_hs8_for_review_only":code[1],
                             "label_status":r["label_status"],"auto_train":False})
    return {"sha256":expected_digest,"files":len(rows),"excluded":len(held),
            "included":len(rows)-len(held),"exclusion_reason_counts_not_mutually_exclusive":dict(reasons),
            "priority_recovery_count":len(priority),"priority_recovery":priority}


def audit(artifact, data, output, coverage):
    source = artifact / "precedents.parquet"
    manifest = artifact / "pipeline_manifest.json"
    inputs = json.loads(manifest.read_text())["sha256"]
    if digest(source) != inputs[source.name]:
        raise ValueError("Dataset does not match artifact manifest")
    cases = pd.read_parquet(source)
    if set(cases.split) != set(SPLITS):
        raise ValueError("Unexpected split labels")
    if not cases.ngay.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("Missing or malformed classification date")
    dates = pd.to_datetime(cases.ngay, format="%Y-%m-%d", errors="raise")
    if any(dates[cases.split.eq(a)].max() >= dates[cases.split.eq(b)].min() for a,b in zip(SPLITS, SPLITS[1:])):
        raise ValueError("Temporal windows overlap or are unordered")

    catalogue = {json.loads(line)["code"] for line in (data/"catalogue.jsonl").read_text().splitlines() if line.strip()}
    texts = cases.input_text.map(normalize_description)
    if texts.eq("").any() or cases.input_text.isna().any():
        raise ValueError("Empty description in cohort")
    code_hits = []
    for r in cases.itertuples():
        raw = str(r.hs8)
        if re.fullmatch(r"[0-9]{8}",raw):
            spelling = raw[:4] + r"[.\s-]?" + raw[4:6] + r"[.\s-]?" + raw[6:]
            if re.search(r"(?<![0-9])" + spelling + r"(?![0-9])", r.input_text):
                code_hits.append(r.Index)
    if not cases.pdf_sha256.fillna("").str.fullmatch("[0-9a-fA-F]{64}").all():
        raise ValueError("Missing/malformed PDF checksums")
    if not cases.hs8.isin(catalogue).all():
        raise ValueError("Target outside frozen catalogue")

    # Connectivity matters: company A and company B may be linked by a duplicate text.
    parent = list(cases.index)
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def link(i,j):
        a,b = sorted((root(i),root(j)))
        parent[b] = a
    for key in ("nhom_dn","pdf_sha256"):
        for indices in cases.groupby(key, dropna=True).groups.values():
            for i in indices[1:]:
                link(indices[0],i)

    matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), dtype=np.float32).fit_transform(texts)
    near = (matrix @ matrix.T).tocoo()
    pair_counts, same_text_different_codes = Counter(), []
    for i,j,similarity in zip(near.row, near.col, near.data, strict=True):
        if i >= j or similarity < SIMILARITY_THRESHOLD:
            continue
        link(i,j)
        a,b = sorted((cases.at[i,"split"],cases.at[j,"split"]))
        pair_counts[f"{a}|{b}"] += 1
        if texts.iat[i] == texts.iat[j] and cases.at[i,"hs8"] != cases.at[j,"hs8"]:
            same_text_different_codes.append([int(i),int(j)])

    components = defaultdict(list)
    for i in cases.index:
        components[root(i)].append(i)
    first_split = {i: min((cases.at[j,"split"] for j in members),key=SPLITS.index)
                   for members in components.values() for i in members}
    split_audit, review_queue = {}, []
    train_codes = set(cases.loc[cases.split.eq("train"), "hs8"])
    corrected = json.loads((data/"precedent_lifecycle.json").read_text())["corrections"]
    for split, rows in cases.groupby("split"):
        missing_org = rows.nhom_dn.isna()
        crossing = [i for i in rows.index if first_split[i] != split]
        clean = [i for i in rows.index if first_split[i] == split and pd.notna(rows.at[i,"nhom_dn"]) and i not in code_hits]
        split_audit[split] = {"cases":len(rows),"dates":[str(rows.ngay.min()), str(rows.ngay.max())],
            "label_status":rows.label_status.value_counts().to_dict(),"missing_company_group":int(missing_org.sum()),
            "connected_to_earlier_window":len(crossing),"strict_slice_cases":len(clean),
            "strict_slice_unseen_hs8":int((~rows.loc[clean,"hs8"].isin(train_codes)).sum()),
            "strict_slice_case_ids":[int(i) for i in clean]}
        for i,row in rows.iterrows():
            reasons = []
            if i in crossing: reasons.append("overlap_earlier_company_or_near_text")
            if pd.isna(row.nhom_dn): reasons.append("company_group_unknown")
            if i in code_hits: reasons.append("target_code_literal_in_description")
            if row.file in corrected: reasons.append("source_has_official_successor")
            if reasons:
                review_queue.append({"row_id":int(i),"split":split,"reasons":reasons})
    report = {"dataset_sha256":digest(source),"manifest_sha256":digest(manifest),
              "catalogue_sha256":digest(data/"catalogue.jsonl"),"splits":split_audit,
              "duplicate_pdf_rows":int(cases.duplicated("pdf_sha256", keep=False).sum()),
              "literal_target_code_in_query_count":len(code_hits),
              "similarity_method":"char_wb TF-IDF (3,5) cosine on normalized descriptions",
              "similarity_threshold":SIMILARITY_THRESHOLD,"near_pairs_by_splits":dict(pair_counts),
              "exact_text_conflicting_label_pairs":same_text_different_codes,
              "known_source_successors_in_snapshot":int(cases.file.isin(corrected).sum()),
              "label_count_gold":int(cases.label_status.eq("expert_adjudicated").sum()),
              "strict_slice_is_independent_future_test":False,
              "review_queue":review_queue}
    if coverage is not None:
        report["coverage_ledger"] = coverage_report(coverage, inputs["cohort_coverage.csv"], catalogue)
        if report["coverage_ledger"]["included"] != len(cases):
            raise ValueError("Coverage ledger included count differs from dataset")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"strict_slice":{s:{k:v for k,v in m.items() if k!="strict_slice_case_ids"} for s,m in split_audit.items()},
                      "near_pairs":dict(pair_counts), "conflicting_pairs":same_text_different_codes},indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("artifact","data","output"):
        parser.add_argument("--"+flag,type=Path,required=True)
    parser.add_argument("--coverage",type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        audit(args.artifact,args.data,args.output,args.coverage)
