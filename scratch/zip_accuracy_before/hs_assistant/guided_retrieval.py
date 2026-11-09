"""Fuse catalogue and strictly prior notice retrieval for human comparison."""
from collections import defaultdict
from datetime import date
from threading import Lock

import numpy as np

from .catalogue import fold

LIMIT = 200
CHANNELS = ("catalogue_bm25", "catalogue_char", "prior_char")
RECIPE = "guided-rrf-hs6-v1"


class GuidedRetrieval:
    def __init__(self, catalogue, precedents):
        self.catalogue = catalogue
        self.precedents = precedents
        self.rows = []
        for row in precedents.rows:
            if (row["split"] == "train" and row["reported_hs8"] in catalogue.by_code
                    and row["lifecycle_observed"] == "not_flagged_in_project"):
                try:
                    issued = date.fromisoformat(row["notice_date"])
                except (TypeError, ValueError):
                    continue
                self.rows.append((issued, row))
        self.families = defaultdict(list)
        for code in catalogue.by_code:
            self.families[code[:6]].append(code)
        self.index = None
        self.lock = Lock()

    def _indices(self):
        with self.lock:
            if self.index is None:
                from sklearn.feature_extraction.text import TfidfVectorizer

                def fit(texts):
                    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                          sublinear_tf=True, max_features=150000, dtype=np.float32)
                    return vec, vec.fit_transform([fold(s) for s in texts])

                catalogue = [r["path"] + " " + r.get("path_en", "") for r in self.catalogue.rows]
                precedents = [r["goods_excerpt"] for _, r in self.rows]
                self.index = fit(catalogue), fit(precedents) if precedents else None
        return self.index

    @staticmethod
    def _similarities(index, query):
        vec, matrix = index
        return (vec.transform([fold(query)]) @ matrix.T).toarray().ravel()

    def channels(self, query, as_of):
        day = date.fromisoformat(as_of)
        if not query.strip():
            return {name: [] for name in CHANNELS}, {}
        cat_index, prior_index = self._indices()
        scores = self._similarities(cat_index, query)
        catalogue_char = [self.catalogue.rows[j]["code"] for j in np.argsort(-scores, kind="stable")[:LIMIT]
                          if scores[j] > 0]
        prior_char, references = [], {}
        if prior_index is not None:
            scores = self._similarities(prior_index, query)
            for j in np.argsort(-scores, kind="stable"):
                issued, row = self.rows[j]
                if scores[j] <= 0:
                    break
                # Historical decisions never see same-day or future notices.
                if issued >= day or not self.precedents.available(row, as_of):
                    continue
                code = row["reported_hs8"]
                if code in references:
                    continue
                prior_char.append(code)
                ref = {k: row.get(k) for k in ("id", "notice_date", "source_name", "source_url", "label_status")}
                if not str(ref["source_url"]).startswith("https://"):
                    ref["source_url"] = None
                references[code] = ref
                if len(prior_char) == LIMIT:
                    break
        return {"catalogue_bm25": [r["code"] for r in self.catalogue.search(query, LIMIT)],
                "catalogue_char": catalogue_char, "prior_char": prior_char}, references

    def combine(self, channels, weights, expand=False):
        scores = defaultdict(float)
        for channel, weight in weights.items():
            for rank, code in enumerate(channels[channel], 1):
                scores[code] += weight / (60 + rank)
        ranked = sorted(scores, key=lambda code: -scores[code])
        if expand:
            families = list(dict.fromkeys(code[:6] for code in ranked[:40]))[:12]
            related = [code for family in families for code in self.families[family]]
            ranked = list(dict.fromkeys(ranked[:30] + related + ranked))
        return ranked[:LIMIT]

    def search(self, query, as_of, limit=30):
        channels, references = self.channels(query, as_of)
        codes = self.combine(channels, dict.fromkeys(CHANNELS, 1), expand=True)
        membership = {name: set(rows) for name, rows in channels.items()}
        return [dict(self.catalogue.by_code[code], rank=rank, score_is_probability=False,
                     retrieval_channels=[name for name in CHANNELS if code in membership[name]],
                     unverified_prior_reference=references.get(code))
                for rank, code in enumerate(codes[:limit], 1)]
