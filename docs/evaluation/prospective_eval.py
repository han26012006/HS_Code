"""Freeze a blind prospective cohort and score reviewed labels separately."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

CASE_FIELDS = {"case_id", "group_id", "classification_date", "facts"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    keyed = {row["case_id"]: row for row in rows}
    if not rows or len(keyed) != len(rows) or any(not isinstance(k, str) or not k.strip() for k in keyed):
        raise ValueError(f"Missing or duplicate case IDs in {path}")
    return keyed


def write_new(path, result):
    with path.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")


def freeze(cases_path, existing_groups_path, catalogue_path, cutoff, output):
    cases = read_jsonl(cases_path)
    known = {line.strip() for line in existing_groups_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    if not known:
        raise ValueError("Declare groups used for train, validation, or prior review")
    for c in cases.values():
        if (set(c) != CASE_FIELDS or not isinstance(c["group_id"], str)
                or not c["group_id"].strip() or c["group_id"] in known):
            raise ValueError("Case schema violation or overlap with a previously used group")
        if date.fromisoformat(c["classification_date"]) <= date.fromisoformat(cutoff):
            raise ValueError("Prospective cases must follow the declared cutoff")
        if not isinstance(c["facts"], str) or not c["facts"].strip():
            raise ValueError("The classification facts are missing")
    write_new(output, {"cases_sha256": digest(cases_path), "catalogue_sha256": digest(catalogue_path),
                      "existing_groups_sha256": digest(existing_groups_path), "cutoff":cutoff,
                      "cases":len(cases), "groups":len({c["group_id"] for c in cases.values()}),
                      "requires_independent_review":True})


def reviewed_label(row, codes):
    votes = row["reviews"]
    if len(votes) != 2:
        raise ValueError("Two reviewers required")
    def reviewed(vote):
        result = vote["result"]
        if not vote["reviewer"].strip() or not vote["evidence_ref"].strip():
            raise ValueError("Review identity and cited evidence are required")
        if result == "needs_information":
            return None
        if result not in codes:
            raise ValueError("Reference HS8 absent from frozen catalogue")
        return result
    a,b = map(reviewed, votes)
    identities = {v["reviewer"].strip().casefold() for v in votes}
    if len(identities) != 2:
        raise ValueError("Independent reviewers must differ")
    if a == b:
        return a, True
    adjudication = row["adjudication"]
    if adjudication["reviewer"].strip().casefold() in identities:
        raise ValueError("Adjudication requires a third reviewer")
    return reviewed(adjudication), False


def score(cases_path, catalogue_path, manifest_path, gold_path, predictions_path, output):
    m = json.loads(manifest_path.read_text())
    if digest(cases_path) != m["cases_sha256"] or digest(catalogue_path) != m["catalogue_sha256"]:
        raise ValueError("Frozen cohort or catalogue changed")
    cases, gold, predictions = (read_jsonl(p) for p in (cases_path,gold_path,predictions_path))
    if not set(cases) == set(gold) == set(predictions):
        raise ValueError("Every frozen case requires a reviewed label and a prediction")
    codes = {json.loads(line)["code"] for line in catalogue_path.read_text().splitlines() if line.strip()}
    groups = {code[:4] for code in codes}
    counts = Counter()
    for key in cases:
        label, agreement = reviewed_label(gold[key],codes)
        counts["reviewers_agree"] += agreement
        p = predictions[key]
        shortlist, heads, decision = p["candidates"], p["headings"], p["proposal"]
        if len(shortlist)>30 or len(set(shortlist))!=len(shortlist) or any(c not in codes for c in shortlist):
            raise ValueError("Invalid HS8 candidate list")
        if len(heads)>3 or len(set(heads))!=len(heads) or any(h not in groups for h in heads):
            raise ValueError("Invalid HS4 shortlist")
        if decision is not None and decision not in shortlist:
            raise ValueError("A proposal must appear in the candidate list")
        counts["proposals"] += decision is not None
        if label is None:
            counts["review_requires_more_information"] += 1
            counts["proposal_despite_missing_information"] += decision is not None
        else:
            counts["classifiable"] += 1
            counts["candidate_hit_at30"] += label in shortlist
            counts["heading_hit_at3"] += label[:4] in heads
            counts["correct_proposals"] += decision == label
            counts["wrong_proposals_on_classifiable"] += decision is not None and decision != label
    write_new(output, {"n":len(cases), "counts":dict(counts), "manifest_sha256":digest(manifest_path),
                      "predictions_sha256":digest(predictions_path), "gold_sha256":digest(gold_path),
                      "human_review_required":True, "automatic_promotion":False})


if __name__ == "__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    modes=cli.add_subparsers(dest="mode",required=True)
    for mode,extra in (("freeze",("existing-groups","cutoff")),("score",("manifest","gold","predictions"))):
        p=modes.add_parser(mode)
        for name in ("cases","catalogue","output",*extra):
            p.add_argument("--"+name,type=str if name=="cutoff" else Path,required=True)
    a=cli.parse_args()
    if a.mode=="freeze":
        freeze(a.cases,a.existing_groups,a.catalogue,a.cutoff,a.output)
    else:
        score(a.cases,a.catalogue,a.manifest,a.gold,a.predictions,a.output)
