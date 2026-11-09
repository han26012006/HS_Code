"""CPU retrieval challengers for Vietnamese product descriptions."""
from collections import defaultdict
from datetime import date
import re

import numpy as np

from .catalogue import fold
from .guided_retrieval import CHANNELS, GuidedRetrieval, LIMIT


STOP = set("la cua cho co va duoc hoac trong tu cac theo thi nay khi nhung do mot de".split())
NOTICE_TERMS = (
    "hang hoa de nghi xac dinh truoc ma so do to chuc ca nhan cung cap",
    "tom tat mo ta hang hoa duoc xac dinh truoc ma so",
    "thong tin mat hang nhu sau",
    "ten goi theo cau tao cong dung",
    "theo ho so de nghi xac dinh truoc ma so",
    "theo ho so xac dinh truoc ma so",
    "ky ma hieu chung loai",
    "classification removed",
)
SELECTED_RECIPE = "hybrid_plus_bigram"
RECIPE = "guided-word-char-v2"
RECIPES = {
    "guided_v1": (dict.fromkeys(CHANNELS, 1), 60, True),
    "prior_word": ({"prior_word": 1}, 40, False),
    "hybrid_equal": ({"catalogue_bm25": 1, "catalogue_char": 1, "prior_char_clean": 1, "prior_word": 1}, 40, False),
    "hybrid_prior2": ({"catalogue_bm25": 1, "catalogue_char": 1, "prior_char_clean": 2, "prior_word": 2}, 40, False),
    "hybrid_prior2_expand": ({"catalogue_bm25": 1, "catalogue_char": 1, "prior_char_clean": 2, "prior_word": 2}, 40, True),
    "hybrid_plus_bigram": ({"catalogue_bm25": 1, "catalogue_char": 1, "prior_char_clean": 1, "prior_word": 1, "catalogue_word": 2}, 20, False),
}


def normalize_description(text):
    text = fold(text)
    text = re.sub(r"\b(?:hs(?:\s+code)?|ma\s+(?:hs|so))\s*[:.\-]?\s*\d[\d .,-]{3,18}", " ", text)
    text = re.sub(r"\b\d{4}[.]\d{2}[.]\d{2}\b", " ", text)
    text = " ".join(re.findall(r"[a-z0-9]+", text))
    for phrase in NOTICE_TERMS:
        text = text.replace(phrase, " ")
    return " ".join(word for word in text.split() if word not in STOP)


class RetrievalExperiment(GuidedRetrieval):
    def __init__(self, catalogue, precedents):
        super().__init__(catalogue, precedents)
        self.additional_index = None

    def _additional_indices(self):
        with self.lock:
            if self.additional_index is None:
                from sklearn.feature_extraction.text import TfidfVectorizer

                def index(texts, analyzer):
                    vec = TfidfVectorizer(analyzer=analyzer,
                                          token_pattern=r"(?u)\b\w+\b" if analyzer == "word" else None,
                                          ngram_range=(1, 2) if analyzer == "word" else (3, 5),
                                          sublinear_tf=True, max_features=150000, dtype=np.float32)
                    return vec, vec.fit_transform(texts)

                docs = [normalize_description(row["goods_excerpt"]) for _, row in self.rows]
                codes = [normalize_description(r["path"] + " " + r.get("path_en", "")) for r in self.catalogue.rows]
                self.additional_index = (
                    index(docs, "char_wb") if any(docs) else None,
                    index(docs, "word") if any(docs) else None,
                    index(codes, "word"),
                )
        return self.additional_index

    def experiment_channels(self, query, as_of):
        channels, references = self.channels(query, as_of)
        text = normalize_description(query)
        if not text:
            return {**channels, "prior_word": [], "prior_char_clean": [], "catalogue_word": []}, references
        day = date.fromisoformat(as_of)
        prior_char, prior_word, catalogue_word = self._additional_indices()

        def rank_prior(index):
            if index is None:
                return []
            scores = self._similarities(index, text)
            codes = {}
            for i in np.argsort(-scores, kind="stable"):
                issued, row = self.rows[i]
                if scores[i] <= 0:
                    break
                if issued < day and self.precedents.available(row, as_of):
                    code = row["reported_hs8"]
                    codes.setdefault(code, None)
                    if code not in references:
                        ref = {key: row.get(key) for key in ("id", "notice_date", "source_name", "source_url", "label_status")}
                        if not str(ref["source_url"]).startswith("https://"):
                            ref["source_url"] = None
                        references[code] = ref
                if len(codes) == LIMIT:
                    break
            return list(codes)

        scores = self._similarities(catalogue_word, text)
        channels["catalogue_word"] = [self.catalogue.rows[i]["code"] for i in np.argsort(-scores, kind="stable")[:LIMIT]
                                      if scores[i] > 0]
        channels["prior_char_clean"] = rank_prior(prior_char)
        channels["prior_word"] = rank_prior(prior_word)
        return channels, references

    def search(self, query, as_of, limit=30):
        channels, references = self.experiment_channels(query, as_of)
        codes = self.rank(channels, SELECTED_RECIPE)
        membership = {name: set(channels[name]) for name in RECIPES[SELECTED_RECIPE][0]}
        return [dict(self.catalogue.by_code[code], rank=rank, score_is_probability=False,
                     retrieval_channels=[name for name, pool in membership.items() if code in pool],
                     unverified_prior_reference=references.get(code))
                for rank, code in enumerate(codes[:limit], 1)]

    def rank(self, channels, recipe):
        weights, constant, expand = RECIPES[recipe]
        if constant == 60:
            return self.combine(channels, weights, expand)
        scores = defaultdict(float)
        for channel, weight in weights.items():
            for rank, code in enumerate(channels[channel], 1):
                scores[code] += weight / (constant + rank)
        ranked = sorted(scores, key=lambda code: -scores[code])
        if expand:
            families = list(dict.fromkeys(code[:6] for code in ranked[:40]))[:12]
            related = [code for family in families for code in self.families[family]]
            ranked = list(dict.fromkeys(ranked[:30] + related + ranked))
        return ranked[:LIMIT]
