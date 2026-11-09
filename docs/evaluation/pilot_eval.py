"""Predict with production CPU routes before opening the separate reviewer labels."""
import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from hs_assistant import __version__
from hs_assistant.catalogue import Catalogue, InferenceService, fold
from hs_assistant.precedents import PrecedentLibrary
from hs_assistant.retrieval_experiment import RetrievalExperiment
from hs_assistant.workspace import FIELDS, Workspace

from prospective_eval import reviewed_label

ENGINES = ("catalogue", "guided")
FAMILIES = {"general","steel","feed","laser","chemical","machine","electronic","food"}
CASE_FIELDS = {"case_id","company_group","product_group","classification_date","product_family","facts"}
FACT_FIELDS = {"field","value","status","source_ref"}
SOURCE_FILES = ("catalogue.jsonl","legal_notes.json","legal_sources.json","precedent_index.jsonl","precedent_lifecycle.json")
MODULE_FILES = ("__init__.py","catalogue.py","guided_retrieval.py","retrieval_experiment.py","precedents.py","workspace.py","legal.py")
EXPLICIT_HS = re.compile(r"(?:(?:\bhs(?:\s*code)?|\bma\s*(?:hs|so)|thuoc\s*nhom|phan\s*nhom)\s*[:.\-]?\s*\d[\d .-]{3,18}|(?<!\d)\d{4}\.\d{2}\.\d{2}(?!\d))")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    keyed = {r["case_id"]: r for r in rows}
    if not rows or len(keyed) != len(rows) or any(not isinstance(k,str) or not k.strip() for k in keyed):
        raise ValueError(f"Invalid case IDs in {path.name}")
    return keyed


def write(path, obj):
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def group(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError("Use nonempty pseudonymous group IDs")
    return value.strip().casefold()


def fingerprint(app):
    data = {n:digest(app/"data"/n) for n in SOURCE_FILES}
    code = {n:digest(app/"hs_assistant"/n) for n in MODULE_FILES}
    return {"data_sha256":data,"code_sha256":code,"runner_sha256":digest(Path(__file__)),
            "review_protocol_sha256":digest(Path(__file__).with_name("prospective_eval.py")),
            "app_version":__version__}


def validate_cases(rows, previous, cutoff):
    company = {group(g) for g in previous["company_groups"]}
    product = {group(g) for g in previous["product_groups"]}
    if not company or not product:
        raise ValueError("Declare known company and product groups from earlier work")
    for key,r in rows.items():
        if set(r) != CASE_FIELDS or r["product_family"] not in FAMILIES:
            raise ValueError(f"Unexpected case fields or family: {key}")
        if group(r["company_group"]) in company or group(r["product_group"]) in product:
            raise ValueError(f"Earlier company or product group present: {key}")
        if date.fromisoformat(r["classification_date"]) <= date.fromisoformat(cutoff):
            raise ValueError(f"Case must be later than frozen historical cutoff: {key}")
        if not isinstance(r["facts"],list):
            raise ValueError("Facts must be structured, an empty list is permitted")
        for fact in r["facts"]:
            if (set(fact) != FACT_FIELDS or fact["field"] not in FIELDS
                    or fact["status"] not in ("verified","unverified","conflict")
                    or not isinstance(fact["value"],str) or not fact["value"].strip()
                    or not isinstance(fact["source_ref"],str) or not fact["source_ref"].strip()):
                raise ValueError(f"Invalid structured fact in {key}")
            if EXPLICIT_HS.search(fold(fact["value"])):
                raise ValueError(f"An explicit HS conclusion appears in a product fact: {key}")


def freeze(cases, known, app, cutoff, output):
    rows = read(cases)
    validate_cases(rows, json.loads(known.read_text()), cutoff)
    write(output, {"protocol":"prospective-pilot-v2","cases_sha256":digest(cases),
                   "known_groups_sha256":digest(known),"n":len(rows),"cutoff":cutoff,
                   "engines":ENGINES, "human_review_required":True, "automatic_promotion":False,
                   "runtime":fingerprint(app)})


def predict(cases, app, manifest, output_dir):
    m = json.loads(manifest.read_text())
    if digest(cases) != m["cases_sha256"] or fingerprint(app) != m["runtime"]:
        raise ValueError("Frozen cases, data or serving code changed")
    rows = read(cases)
    results = []
    data = app/"data"
    catalogue = Catalogue(data/"catalogue.jsonl",data/"legal_notes.json")
    with TemporaryDirectory() as temp:
        service = InferenceService(catalogue, instruction_out=Path(temp))
        service.guided = RetrievalExperiment(catalogue,PrecedentLibrary(data/"precedent_index.jsonl"))
        for key,row in rows.items():
            sku = {"product_family":row["product_family"],"facts":[dict(f,id=str(i)) for i,f in enumerate(row["facts"])]}
            sku["readiness"] = Workspace.readiness(sku)
            result = {"case_id":key,"engines":{}}
            for engine in ENGINES:
                if not sku["readiness"]["can_analyze"]:
                    result["engines"][engine] = {"candidates":[],"headings":[],"proposal":None,
                        "state":"needs_information","input_sha256":None,"elapsed_ms":None}
                    continue
                a = service.analyze(sku,engine,classification_date=row["classification_date"])
                if a["auto_accept"] or not a["human_review_required"]:
                    raise ValueError("Pilot forbids auto-acceptance")
                result["engines"][engine] = {"candidates":[c["code"] for c in a["candidates"]],
                    "headings":[h["heading"] for h in a["heading_candidates"]],
                    "proposal":None,"state":a["decision_support_state"],"input_sha256":a["input_hash"],
                    "elapsed_ms":a["elapsed_ms"]}
            results.append(result)
    output_dir.mkdir(parents=True,exist_ok=False)
    path = output_dir/"PREDICTIONS.jsonl"
    with path.open("x",encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False)+"\n")
    write(output_dir/"PREDICTION_RECEIPT.json",{"manifest_sha256":digest(manifest),
           "predictions_sha256":digest(path),"n":len(rows),"engine_outputs":ENGINES})


def score(cases, app, manifest, prediction_dir, gold, output):
    m = json.loads(manifest.read_text())
    receipt = json.loads((prediction_dir/"PREDICTION_RECEIPT.json").read_text())
    path = prediction_dir/"PREDICTIONS.jsonl"
    if (digest(cases) != m["cases_sha256"] or fingerprint(app) != m["runtime"]
            or receipt["manifest_sha256"] != digest(manifest) or receipt["predictions_sha256"] != digest(path)):
        raise ValueError("Inputs, serving environment or predictions differ from frozen receipts")
    rows, preds, labels = map(read,(cases,path,gold))
    if set(rows) != set(preds) or set(rows) != set(labels):
        raise ValueError("Every case requires a prediction and separately reviewed label")
    codes = {json.loads(l)["code"] for l in (app/"data/catalogue.jsonl").read_text().splitlines() if l.strip()}
    agreements = 0
    metrics = {engine: Counter({key:0 for key in ("classifiable","needs_information_reviewed","candidate_hit_at30",
       "heading_hit_at3","hs8_first_candidate_hit","asked_for_info_on_incomplete","asked_for_info_on_classifiable")}) for engine in ENGINES}
    wins = Counter({"guided_only_hit_at30":0,"bm25_only_hit_at30":0})
    for key in rows:
        label, agreed = reviewed_label(labels[key],codes)
        agreements += agreed
        hits = {}
        for engine,c in metrics.items():
            pred = preds[key]["engines"][engine]
            candidates = pred["candidates"]
            distinct = list(dict.fromkeys(code[:4] for code in candidates))
            if (len(candidates)>30 or len(set(candidates))!=len(candidates) or any(k not in codes for k in candidates)
                    or pred["proposal"] is not None or pred["headings"] != distinct[:3]):
                raise ValueError(f"Invalid prediction record: {key}")
            needs = pred["state"]=="needs_information"
            if label is None:
                c["needs_information_reviewed"] += 1
                c["asked_for_info_on_incomplete"] += needs
            else:
                c["classifiable"] += 1
                hits[engine] = label in candidates
                c["candidate_hit_at30"] += hits[engine]
                c["heading_hit_at3"] += label[:4] in pred["headings"]
                c["hs8_first_candidate_hit"] += candidates[:1]==[label]
                c["asked_for_info_on_classifiable"] += needs
        if label is not None:
            wins["guided_only_hit_at30"] += hits["guided"] and not hits["catalogue"]
            wins["bm25_only_hit_at30"] += hits["catalogue"] and not hits["guided"]
    write(output, {"n":len(rows),"reviewer_agreements":agreements,"metrics":metrics,"paired":wins,
                   "company_groups":len({group(r["company_group"]) for r in rows.values()}),
                   "product_groups":len({group(r["product_group"]) for r in rows.values()}),
                   "prediction_receipt_sha256":digest(prediction_dir/"PREDICTION_RECEIPT.json"),
                   "reviewed_labels_sha256":digest(gold),"human_review_required":True,
                   "receipts_not_external_timestamp_proof":True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode",required=True)
    for mode,flags in (("freeze",("known","cutoff","output")),
                       ("predict",("manifest","prediction_dir")),
                       ("score",("manifest","prediction_dir","gold","output"))):
        command = modes.add_parser(mode)
        for flag in ("cases","app",*flags):
            command.add_argument("--"+flag.replace("_","-"),type=str if flag=="cutoff" else Path,required=True)
    a = parser.parse_args()
    if a.mode=="freeze":
        freeze(a.cases,a.known,a.app,a.cutoff,a.output)
    elif a.mode=="predict":
        predict(a.cases,a.app,a.manifest,a.prediction_dir)
    else:
        score(a.cases,a.app,a.manifest,a.prediction_dir,a.gold,a.output)
