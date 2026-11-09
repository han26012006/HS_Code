"""Search project OCR of Vietnamese notices as unverified references.

Default train-only corpus preserves the separation from historical evaluation.
Age warnings do not decide whether an individual notice is legally applicable.
"""
import json
import threading
from datetime import date
from pathlib import Path
import numpy as np
from .catalogue import tokens, sha


class PrecedentLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
        self.version = sha(self.path)
        lifecycle = self.path.with_name("precedent_lifecycle.json")
        self.corrections = json.loads(lifecycle.read_text(encoding="utf-8"))["corrections"] if lifecycle.is_file() else {}
        self.lifecycle_version = sha(lifecycle) if lifecycle.is_file() else None
        for correction in self.corrections.values():
            date.fromisoformat(correction["effective_from"])
        self.index = None
        self.lock = threading.Lock()

    def available(self, row, as_of):
        if row["split"] != "train" or row["lifecycle_observed"] != "not_flagged_in_project":
            return False
        issued = row["notice_date"]
        correction = self.corrections.get(row["source_name"])
        return bool(issued and issued < as_of and
                    (not correction or as_of < correction["effective_from"]))

    def search(self, query, as_of, headings=None, limit=8):
        day = date.fromisoformat(as_of)
        with self.lock:
            if self.index is None:
                from sklearn.feature_extraction.text import CountVectorizer
                from scipy import sparse
                cv = CountVectorizer(analyzer=tokens)
                x = cv.fit_transform([r['goods_excerpt'] for r in self.rows]).tocoo().astype(np.float32)
                length = np.asarray(x.tocsr().sum(1)).ravel()
                df = np.bincount(x.col, minlength=x.shape[1])
                idf = np.log(1+(len(self.rows)-df+.5)/(df+.5))
                weight = idf[x.col]*x.data*2.5/(x.data+1.5*(.25+.75*length[x.row]/max(length.mean(), 1)))
                self.index = cv, sparse.csr_matrix((weight, (x.row, x.col)), shape=x.shape)
        cv, matrix = self.index
        scores = np.asarray((cv.transform([query])@matrix.T).toarray()).ravel()
        rows = []
        for idx in np.argsort(-scores, kind='stable'):
            r = self.rows[int(idx)]
            if scores[idx] <= 0: break
            if not self.available(r, as_of): continue
            if headings and r['reported_hs8'][:4] not in headings: continue
            issued = date.fromisoformat(r['notice_date'])
            try: anniversary = issued.replace(year=issued.year+3)
            except ValueError: anniversary = date(issued.year+3, 3, 1)
            rows.append(dict(r, retrieval_score=round(float(scores[idx]), 4), score_is_probability=False,
                             more_than_three_years_old=day >= anniversary,
                             age_warning='Đối chiếu loại thông báo, hiệu lực riêng và văn bản thay thế; tuổi trên 3 năm không tự chứng minh mọi loại thông báo hết giá trị tham khảo.' if day >= anniversary else '',
                             legal_applicability_verified=False, role='reference',
                             source_capture='project_ocr_excerpt_requires_original_check'))
            if len(rows) >= limit: break
        return rows
