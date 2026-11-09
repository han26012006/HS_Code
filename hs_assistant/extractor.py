"""Intelligent Document Type Detection, Information Extraction, and Cross-Document Reconciliation.

Pure local extraction: deterministic regex, dictionary matching, tabular scanning,
and exact text substring provenance (no external API calls or hallucinated quotes).
"""
from __future__ import annotations

import io
import os
import re
import uuid
import hashlib
import zipfile
import tempfile
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Supported Document Types
DOC_TYPES = {
    'commercial_invoice': 'Commercial Invoice (Hóa đơn thương mại)',
    'packing_list': 'Packing List (Bảng kê đóng gói)',
    'bill_of_lading': 'Bill of Lading (Vận đơn đường biển)',
    'air_waybill': 'Air Waybill (Vận đơn hàng không)',
    'certificate_of_quality': 'Certificate of Quality (Chứng nhận chất lượng)',
    'certificate_of_origin': 'Certificate of Origin (Chứng nhận xuất xứ)',
    'technical_spec': 'Technical Specification (Tài liệu kỹ thuật / Datasheet)',
    'product_catalogue': 'Product Catalogue (Catalogue sản phẩm)',
    'customs_declaration': 'Customs Declaration (Tờ khai hải quan)',
    'mill_test': 'Mill Test Certificate (Chứng chỉ xuất xưởng)',
    'sales_contract': 'Sales Contract (Hợp đồng mua bán)',
    'regulatory_permit': 'Giấy phép / Công bố chuyên ngành',
    'legal_reference': 'Tài liệu pháp lý tham chiếu',
    'other': 'Chứng từ khác',
}

# Signal Lexicon for Document Classification
DOC_TYPE_SIGNALS = {
    'commercial_invoice': [
        (r'\b(?:commercial|customs)\s+invoice\b', 12),
        (r'\binvoice\s+no\.?\b', 8),
        (r'\bhóa\s+đơn\s+thương\s+mại\b', 12),
        (r'\bpayment\s+terms?\b', 5),
        (r'\bconsignee\b', 4),
        (r'\bshipper\b', 4),
        (r'\bunit\s+price\b', 5),
        (r'\btotal\s+amount\b', 6),
        (r'发票号', 8),
    ],
    'packing_list': [
        (r'\bpacking\s+list\b', 14),
        (r'\bphiếu\s+đóng\s+gói\b', 12),
        (r'\bbảng\s+kê\s+đóng\s+gói\b', 12),
        (r'\bgross\s+weight\b', 8),
        (r'\bnet\s+weight\b', 8),
        (r'\bg\.?w\.?\b', 5),
        (r'\bn\.?w\.?\b', 5),
        (r'\bcartons?\b', 4),
        (r'\bpackages?\b', 4),
        (r'\bmeasurement\b', 5),
    ],
    'bill_of_lading': [
        (r'\bbill\s+of\s+lading\b', 14),
        (r'\bb/?l\s+no\.?\b', 10),
        (r'\bocean\s+bill\b', 10),
        (r'\bvận\s+đơn\s+đường\s+biển\b', 12),
        (r'\bport\s+of\s+loading\b', 7),
        (r'\bport\s+of\s+discharge\b', 7),
        (r'\bvessel\b', 6),
        (r'\bvoyage\b', 6),
    ],
    'air_waybill': [
        (r'\bair\s*waybill\b', 14),
        (r'\bawb\b', 8),
        (r'\bflight\s+no\.?\b', 8),
        (r'\bairport\s+of\s+departure\b', 8),
        (r'\bairport\s+of\s+destination\b', 8),
    ],
    'certificate_of_origin': [
        (r'\bcertificate\s+of\s+origin\b', 15),
        (r'\bchứng\s+nhận\s+xuất\s+xứ\b', 14),
        (r'\bform\s+(d|e|ak|aj|vj|cptpp|evfta|rcep)\b', 12),
        (r'\borigin\s+criteria\b', 8),
        (r'\bpreferential\s+treatment\b', 7),
    ],
    'mill_test': [
        (r'\bmill\s+test\s+certificate\b', 15),
        (r'\binspection\s+certificate\b', 10),
        (r'产\s*品\s*质\s*量\s*证\s*明\s*书', 15),
        (r'\bchemical\s+composition\b', 9),
        (r'\btensile\s+test\b', 9),
        (r'\bheat\s+no\.?\b', 8),
        (r'\byield\s+strength\b', 7),
        (r'\belongation\b', 7),
    ],
    'technical_spec': [
        (r'\btechnical\s+specifications?\b|hồ\s*sơ\s*kỹ\s*thuật', 14),
        (r'\bthông\s+số\s+kỹ\s+thuật\b', 14),
        (r'\bdatasheet\b', 12),
        (r'\bdata\s+sheet\b', 10),
        (r'\buser\s+manual\b', 10),
        (r'\bhướng\s+dẫn\s+sử\s+dụng\b', 10),
        (r'\boperating\s+instructions?\b', 9),
        (r'\bcông\s+bố\s+tiêu\s+chuẩn\b', 9),
        (r'\bpower\s+supply\b', 6),
        (r'\bwavelength\b', 7),
    ],
    'product_catalogue': [
        (r'\bcatalogue\b', 10),
        (r'\bcatalog\b', 10),
        (r'\bproduct\s+guide\b', 8),
        (r'\bbrochure\b', 8),
    ],
    'customs_declaration': [
        (r'\btờ\s+khai\s+hàng\s+hóa\s+(nhập|xuất)\s+khẩu\b', 15),
        (r'\bcustoms\s+declaration\b', 12),
        (r'\bsố\s+tờ\s+khai\b', 10),
        (r'\bmã\s+loại\s+hình\b', 9),
        (r'\bphân\s+luồng\b', 8),
        (r'<imp>', 10),
        (r'<exp>', 10),
    ],
    'sales_contract': [
        (r'\bsales\s+contract\b', 15),
        (r'\bhợp\s+đồng\s+mua\s+bán\b', 14),
        (r'\bcontract\s+no\.?\b', 10),
        (r'\bpurchase\s+agreement\b', 12),
        (r'\bthe\s+seller\b', 6),
        (r'\bthe\s+buyer\b', 6),
    ],
    'regulatory_permit': [
        (r'\bgiấy\s+phép\b', 10),
        (r'\bgiấy\s+đăng\s+ký\b', 9),
        (r'\bbộ\s+y\s+tế\b', 8),
        (r'\bbộ\s+nông\s+nghiệp\b', 8),
        (r'\bkiểm\s+dịch\b', 8),
    ],
}


class DocumentPageLimitError(ValueError):
    pass


def parse_file_bytes(filename: str, content: bytes) -> List[Dict[str, Any]]:
    """Extracts text pages from raw bytes of supported document formats with OCR fallback."""
    ext = Path(filename).suffix.lower()
    pages = []

    if ext == '.pdf':
        tmp_pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_f:
                tmp_f.write(content)
                tmp_pdf_path = tmp_f.name

            from pypdf import PdfReader
            reader = PdfReader(tmp_pdf_path)
            total_pages = len(reader.pages)
            limit=int(os.environ.get('HS_MAX_DOCUMENT_PAGES','500'))
            if total_pages>limit:raise DocumentPageLimitError(f'PDF có {total_pages} trang, vượt giới hạn {limit}; không cắt trang âm thầm.')
            if total_pages == 0:
                total_pages = 1

            from .document_text import read_pdf_page
            for number in range(1,total_pages+1):
                pages.append(read_pdf_page(tmp_pdf_path,number,reader))

        except Exception as exc:
            if isinstance(exc,DocumentPageLimitError):raise
            pages.append({'number': 1, 'text': '', 'method': 'parse_error', 'error': str(exc), 'status': 'needs_review'})
        finally:
            if tmp_pdf_path and Path(tmp_pdf_path).exists():
                Path(tmp_pdf_path).unlink(missing_ok=True)

    elif ext == '.docx':
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            lines = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    lines.append(' | '.join(c.text for c in row.cells))
            pages.append({'number': 1, 'text': '\n'.join(lines), 'method': 'docx_text'})
        except Exception:
            pages.append({'number': 1, 'text': '', 'method': 'docx_error'})

    elif ext in ('.xlsx', '.xls'):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            from .spreadsheet_layout import sheet_page
            for idx,sheet in enumerate(wb.worksheets,1):pages.append(sheet_page(sheet,idx))
            wb.close()
        except Exception:
            pages.append({'number': 1, 'text': '', 'method': 'xlsx_error'})

    elif ext in ('.png', '.jpg', '.jpeg'):
        tess_bin = shutil.which('tesseract')
        if tess_bin:
            try:
                ocr_lang = 'eng'
                try:
                    langs = subprocess.check_output([tess_bin, '--list-langs'], text=True).split()
                    if 'vie' in langs and 'eng' in langs:
                        ocr_lang = 'vie+eng'
                    elif 'vie' in langs:
                        ocr_lang = 'vie'
                except Exception:
                    pass

                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    from .ocr_layout import read_image
                    ocr=read_image(tmp_path)
                    pages.append({'number':1,**ocr})
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            except Exception:
                pages.append({'number': 1, 'text': f"[Hình ảnh {filename}]", 'method': 'image_metadata'})
        else:
            pages.append({'number': 1, 'text': f"[Hình ảnh {filename} - Chưa có OCR engine]", 'method': 'image_metadata'})

    elif ext in ('.txt', '.csv'):
        try:
            txt = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            txt = content.decode('cp1258', errors='replace')
        pages.append({'number': 1, 'text': txt, 'method': 'plain_text'})

    else:
        # Generic text extraction
        pages.append({'number': 1, 'text': content.decode('utf-8', errors='replace'), 'method': 'generic'})

    from .document_layout import build_layout
    for page in pages:
        if 'layout' not in page:page['layout']=build_layout(page.get('text',''),page['number'],geometry=page.pop('geometry',None),table_geometry=page.get('pdf_tables'))
    return pages


class DocumentTypeDetector:
    """Classifies document type using rule-based scoring and evidence gathering."""

    @classmethod
    def detect(cls, text: str) -> Dict[str, Any]:
        from .document_classification import classify_pages
        return classify_pages([{'number':1,'text':text}], DOC_TYPES)

    @classmethod
    def detect_type(cls, doc):
        from .document_classification import classify_pages
        return classify_pages(doc.get('pages', []), DOC_TYPES)



class InformationExtractor:
    """Extracts field-level dossier, shipment, SKU, and technical facts with exact string provenance."""

    @staticmethod
    def _find_exact_quote(page_text: str, match_text: str, context_len: int = 120) -> str:
        """Returns an exact substring from page_text containing match_text."""
        pos = page_text.find(match_text)
        if pos != -1:
            start = max(0, page_text.rfind('\n', 0, pos) + 1)
            end = page_text.find('\n', pos + len(match_text))
            if end == -1:
                end = len(page_text)
            snippet = page_text[start:end].strip()
            if len(snippet) > 200:
                snippet = page_text[max(0, pos - 20):min(len(page_text), pos + len(match_text) + 60)].strip()
            # Must strictly be a substring of page_text
            if snippet in page_text:
                return snippet
            return match_text if match_text in page_text else ""
        return ""

    @classmethod
    def extract_dossier_fields(cls, docs):
        from .document_layout import ensure_layout, norm
        from .document_schema import label_field, allowed
        sources = {}
        for doc in docs:
            ensure_layout(doc)
            kind=DocumentTypeDetector.detect_type(doc)['kind']
            for page in doc['pages']:
                if DocumentTypeDetector.detect_type({'pages':[page]})['kind']=='legal_reference':continue
                for relation in page['layout']['key_values']:
                    field=label_field(relation['label'],metadata=True)
                    first_row=min((r['start'] for table in page['layout']['tables']for r in table['rows']),default=min(2500,len(page['text'])))
                    if kind=='commercial_invoice' and relation['start']<first_row:
                        if norm(relation['label']).rstrip('.')=='no':field='invoice_number'
                        if norm(relation['label'])=='date':field='invoice_date'
                    if not field or not allowed(kind,field,metadata=True):continue
                    value=relation['value']
                    from .field_validation import usable_metadata
                    if not usable_metadata(field,value):continue
                    if field in {'invoice_number','bl_number','contract_number','certificate_number'}:
                        value=re.split(r'\s*(?:&\s*(?:dated?|date)|\bdated\b)\s*[:.]?',value,flags=re.I)[0].strip()
                        if len(value)<3 or not re.search(r'\d',value):continue
                    if field=='declaration_number' and not re.fullmatch(r'\d{11,12}',value):continue
                    if field in {'total_packages','total_gross_weight','total_net_weight','total_value'} and not re.search(r'\d',value):continue
                    date_state=None
                    if field=='invoice_date':
                        from .source_dates import source_date
                        date_state=source_date(value)
                        if not date_state:continue
                    fact=cls._make_field(field,value,doc['id'],doc.get('name',''),page['number'],relation['quote'])
                    fact.update(source_block_ids=relation['block_ids'],source_span=[relation['start'],relation['end']],source_document_type=kind)
                    if date_state:fact.update(canonical_value=date_state.get('iso'),status=date_state['status'])
                    sources.setdefault(field,[]).append(fact)
                    # Currency in a labelled monetary amount is explicit, never a default.
                    if field=='total_value':
                        currency=re.search(r'\b(?:USD|EUR|VND|JPY|CNY|RMB|SGD|GBP)\b',value)
                        if currency:
                            cur=cls._make_field('currency',currency.group(0),doc['id'],doc.get('name',''),page['number'],relation['quote'])
                            sources.setdefault('currency',[]).append(cur)
                # CIF/FOB etc require a labelled incoterms relation, handled above.
        fields={}
        for field,records in sources.items():
            distinct={norm(f['value']) for f in records}
            fields[field]={**records[0],'sources':records}
            if len(distinct)>1:
                fields[field].update(value='',status='conflicting',alternatives=records)
        return fields

    @classmethod
    def extract_candidate_skus(cls, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identifies distinct candidate SKUs across documents and attaches field-level facts with strict provenance."""
        from .product_extraction import extract
        return extract(docs, cls._make_fact)

    @classmethod
    def _extract_observed_hs(cls, text: str) -> List[str]:
        """Strictly extracts 8-digit or 6-digit HS codes observed in document text."""
        codes = []
        for m in re.finditer(r'\b([0-9]{4})\.([0-9]{2})\.([0-9]{2})\b', text):
            code = m.group(1) + m.group(2) + m.group(3)
            if code not in codes:
                codes.append(code)
        for m in re.finditer(r'(?:hs|mã\s*số|mã\s*hs)[\s:=|]*([0-9]{8})\b', text, re.IGNORECASE):
            code = m.group(1)
            if code not in codes:
                codes.append(code)
        return codes

    @classmethod
    def _make_field(cls, field_name: str, value: str, doc_id: str, doc_name: str, page_num: int, quote: str, unit: Optional[str] = None) -> Dict[str, Any]:
        return {
            'field': field_name,
            'value': value,
            'unit': unit,
            'source_document_id': doc_id,
            'source_document_name': doc_name,
            'source_page': page_num,
            'source_excerpt': quote,
            'field_name': field_name,
            'source_quote': quote,
            'status': 'extracted',
            'source_kind': 'document_extracted',
            'extraction_method': 'explicit_label',
            'verification_status': 'pending_review',
            'verified_by': None,
            'verified_at': None,
        }

    @classmethod
    def _make_fact(cls, field_name: str, value: str, doc_id: str, doc_name: str, page_num: int, quote: str, unit: Optional[str] = None) -> Dict[str, Any]:
        return {
            'id': f"fact_{uuid.uuid4().hex[:8]}",
            'field': field_name,
            'value': value,
            'unit': unit,
            'document_id': doc_id,
            'document_name': doc_name,
            'page_number': page_num,
            'quote': quote,
            'extraction_method': 'document_parser',
            'status': 'unverified',  # STRICT: never auto-verified
            'reviewer': None,
            'source_kind': 'document',
        }


class CrossDocumentReconciler:
    """Reconciles extracted data across multiple documents, highlighting matches and flagging conflicts."""

    @classmethod
    def reconcile(cls, docs: List[Dict[str, Any]], skus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from .document_reconciliation import reconcile
        return reconcile(docs,skus)


class AutoFillDraftManager:
    """Manages draft state for Document-First onboarding and handles atomic commits."""

    def __init__(self, workspace_db):
        self.db = workspace_db
        self.drafts: Dict[str, Dict[str, Any]] = {}
        self._canonical_drafts = {}
        self._draft_files: Dict[str, Dict[str, bytes]] = {}

    def create_draft(self, files_or_tuples: Any, parsed_docs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        draft_id = f"draft_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        self._draft_files[draft_id] = {}

        if parsed_docs is None:
            files_meta = []
            parsed_docs = []
            for item in files_or_tuples:
                if isinstance(item, tuple):
                    fname, content = item
                elif isinstance(item, dict):
                    fname = item.get('filename') or item.get('name')
                    content = item.get('content') or item.get('bytes')
                else:
                    continue
                f_sha = hashlib.sha256(content).hexdigest()
                files_meta.append({
                    'name': fname,
                    'size': len(content),
                    'sha256': f_sha
                })
                p_pages = parse_file_bytes(fname, content)
                doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                self._draft_files[draft_id][doc_id] = content
                p_doc = {
                    'id': doc_id,
                    'name': fname,
                    'sha256': f_sha,
                    'size': len(content),
                    'pages': p_pages
                }
                parsed_docs.append(p_doc)
        else:
            files_meta = files_or_tuples

        # 1. Detect document types & enrich metadata
        for doc in parsed_docs:
            from .document_layout import ensure_layout
            ensure_layout(doc)
            all_text = '\n\n'.join(p.get('text', '') for p in doc.get('pages', [])).strip()
            detected = DocumentTypeDetector.detect_type(doc)
            doc['detected_type'] = detected
            from .product_extraction import role
            doc['role'] = role(doc)
            doc['kind'] = detected['kind']
            doc['document_type'] = detected['kind']
            doc['document_type_name'] = DOC_TYPES.get(detected['kind'], 'Chưa xác định')
            doc['confidence'] = detected['confidence']
            doc['type_confidence'] = detected['confidence']
            doc['signals'] = detected.get('signals', [])
            doc['filename'] = doc.get('name', 'Tài liệu')
            doc['text_content'] = all_text
            doc['text'] = all_text

        # 2. Extract dossier metadata
        dossier_fields = InformationExtractor.extract_dossier_fields(parsed_docs)

        # 3. Extract candidate SKUs
        sku_candidates = InformationExtractor.extract_candidate_skus(parsed_docs)

        # 4. Reconcile across documents
        reconciliations = CrossDocumentReconciler.reconcile(parsed_docs, sku_candidates)

        # 5. Build flattened extracted_case for seamless UI binding
        doc_num = dossier_fields.get('document_number', {}).get('value')
        first_fname = files_meta[0]['name'] if files_meta else 'chứng từ'
        base_name = Path(first_fname).stem.replace('_', ' ').replace('-', ' ').strip()

        case_title = ""
        if doc_num:
            case_title = f"Hồ sơ theo văn bản {doc_num}"
        elif dossier_fields.get('title', {}).get('value'):
            case_title = dossier_fields['title']['value']
        elif dossier_fields.get('importer', {}).get('value'):
            case_title = f"Hồ sơ nhập khẩu {dossier_fields['importer']['value']}"
        elif dossier_fields.get('exporter', {}).get('value'):
            case_title = f"Hồ sơ xuất khẩu {dossier_fields['exporter']['value']}"
        elif sku_candidates and sku_candidates[0].get('name'):
            case_title = f"Hồ sơ phân loại {sku_candidates[0]['name']}"
        else:
            case_title = f"Hồ sơ phân loại {base_name}"

        extracted_case = {
            'title': case_title,
            'importer_name': dossier_fields.get('importer', {}).get('value', ''),
            'exporter_name': dossier_fields.get('exporter', {}).get('value', ''),
            'invoice_number': dossier_fields.get('invoice_number', {}).get('value', ''),
            'invoice_date': dossier_fields.get('invoice_date', {}).get('value', ''),
            'declaration_number': dossier_fields.get('declaration_number', {}).get('value', ''),
            'port_of_loading': dossier_fields.get('port_of_loading', {}).get('value', ''),
            'port_of_discharge': dossier_fields.get('port_of_discharge', {}).get('value', ''),
            'origin_country': dossier_fields.get('origin_country', {}).get('value', ''),
            'currency': dossier_fields.get('currency', {}).get('value', ''),
            'incoterms': dossier_fields.get('incoterms', {}).get('value', ''),
            'total_value': dossier_fields.get('total_value', {}).get('value', ''),
            'total_gross_weight': dossier_fields.get('total_gross_weight', {}).get('value', ''),
            'total_net_weight': dossier_fields.get('total_net_weight', {}).get('value', ''),
            'total_packages': dossier_fields.get('total_packages', {}).get('value', ''),
        }

        draft = {
            'draft_id': draft_id,
            'created_at': now_str,
            'status': 'review_required',
            'files': files_meta,
            'documents': parsed_docs,
            'dossier_fields': dossier_fields,
            'extracted_case': extracted_case,
            'system_defaults': {'classification_date': 'user_review_required', 'title': case_title},
            'skus': sku_candidates,
            'proposed_skus': sku_candidates,
            'warnings': [{'document_id': d['id'], 'page': p.get('number'), 'status': 'needs_review', 'message': p.get('error') or 'Trang thiếu văn bản hoặc OCR cần kiểm tra'} for d in parsed_docs for p in d.get('pages', []) if not p.get('text', '').strip() or p.get('method', '').startswith(('ocr', 'parse_error', 'fallback'))],
            'reconciliations': reconciliations,
            'reconciliation': reconciliations,
            'summary': {
                'total_files': len(files_meta),
                'total_pages': sum(len(d.get('pages', [])) for d in parsed_docs),
                'total_skus': len(sku_candidates),
                'total_fields': len(dossier_fields) + sum(len(s.get('facts', [])) for s in sku_candidates),
                'conflicts_count': sum(1 for r in reconciliations if r['status'] == 'conflict'),
            }
        }
        from copy import deepcopy
        self._canonical_drafts[draft_id]=deepcopy({'documents':parsed_docs,'skus':sku_candidates,'dossier_fields':dossier_fields})
        draft['diagnostics']=[{'document_id':d['id'],'stage':'classification','status':d['detected_type'].get('classification_status','needs_review'),'kind':d['kind']} for d in parsed_docs]+[{'document_id':d['id'],'page':p['number'],'stage':'layout','status':'table_detected' if p['layout']['tables'] else 'no_table_detected','table_count':len(p['layout']['tables'])} for d in parsed_docs for p in d['pages']]
        draft['warnings'] += [{'document_id':d['id'],'page':p['number'],**warning} for d in parsed_docs for p in d['pages'] for warning in p.get('warnings',[])+p['layout'].get('warnings',[])]
        self.drafts[draft_id] = draft
        return draft

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        return self.drafts.get(draft_id)

    def update_draft(self, draft_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        draft = self.get_draft(draft_id)
        if not draft:
            raise KeyError(f"Draft {draft_id} không tồn tại.")
        from copy import deepcopy
        before=deepcopy(draft);canonical_before=deepcopy(self._canonical_drafts[draft_id])
        try:
            if updates.get('dossier_fields') is not None:
                draft['dossier_fields']=self._review_dossier_fields(self._canonical_drafts[draft_id]['dossier_fields'],updates['dossier_fields'])
            if updates.get('skus') is not None:
                self._validate_reviewed_sources(self._canonical_drafts[draft_id], updates['skus'])
                draft['skus'] = updates['skus']
                draft['proposed_skus'] = draft['skus']
            if updates.get('match_confirmations'):
                self._confirm_matches(draft_id,updates['match_confirmations'])
        except Exception:
            self.drafts[draft_id]=before;self._canonical_drafts[draft_id]=canonical_before
            raise
        return draft

    def _confirm_matches(self,draft_id,confirmations):
        from copy import deepcopy
        from .document_reconciliation import fact_value_key
        draft=self.drafts[draft_id];canonical=self._canonical_drafts[draft_id]
        for confirmation in confirmations:
            target_id=confirmation.get('target_sku_id');source_id=confirmation.get('source_sku_id')
            if not confirmation.get('confirmed') or target_id==source_id:raise ValueError('Cần xác nhận hai bản ghi sản phẩm khác nhau.')
            target=next((s for s in canonical['skus'] if s['id']==target_id),None)
            source=next((s for s in canonical['skus'] if s['id']==source_id),None)
            if not target or not source:raise ValueError('Không tìm thấy bản ghi cần ghép.')
            link=next((l for l in target.get('matching',[]) if l.get('candidate_id')==source_id and l['status']=='needs_review'),None)
            if not link:raise ValueError('Chỉ được xác nhận đề xuất ghép đang cần rà soát, không ghép thông số xung đột.')
            from .product_extraction import _relation
            relation,_=_relation(target,source)
            if relation in {'different','conflicting'}:raise ValueError('Không ghép sản phẩm khác định danh hoặc thông số quan trọng.')
            for container in (canonical,draft):
                a=next(s for s in container['skus'] if s['id']==target_id)
                b=next(s for s in container['skus'] if s['id']==source_id)
                a['facts']+=deepcopy(b['facts']);a['source_members']+=deepcopy(b.get('source_members',[]))
                for f in a['facts']:f['sku_id']=target_id
                for field in {f['field'] for f in a['facts']} - {'specifications'}:
                    facts=[f for f in a['facts'] if f['field']==field]
                    if len({fact_value_key(f) for f in facts})>1:
                        for f in facts:f.update(status='conflict',extraction_status='conflicting')
                a['identity_status']='user_confirmed_match';a['matching']=[x for x in a.get('matching',[]) if x.get('candidate_id')!=source_id]
                for f in a['facts']:f['matching_decision']='user_confirmed'
                container['skus']=[s for s in container['skus'] if s['id']!=source_id]
            draft.setdefault('matching_confirmations',[]).append(deepcopy(confirmation))
        draft['proposed_skus']=draft['skus'];draft['summary']['total_skus']=len(draft['skus'])
        draft['reconciliations']=CrossDocumentReconciler.reconcile(draft['documents'],draft['skus'])
        draft['reconciliation']=draft['reconciliations']

    @staticmethod
    def _review_dossier_fields(original,updates):
        from copy import deepcopy
        from .document_layout import norm
        reviewed=deepcopy(original)
        for field,incoming in updates.items():
            if field not in original:raise ValueError('Trường hồ sơ không thuộc schema trích xuất.')
            value=str(incoming.get('value',''))
            prior=original[field]
            if norm(value)==norm(prior.get('value','')):continue
            records=prior.get('sources',prior.get('alternatives',[prior]))
            selected=next((r for r in records if norm(r['value'])==norm(value)),records[0])
            user={**selected,'value':value,'original_value':selected['value'],'source_kind':'user_input','status':'needs_review'}
            reviewed[field]={**user,'sources':[user]}
        return reviewed

    @staticmethod
    def _validate_reviewed_sources(draft, skus):
        from .product_extraction import normalized, role
        docs = {d['id']: d for d in draft.get('documents', [])}
        for sku in skus:
            for fact in sku.get('facts', []):
                if not str(fact.get('value', '')).strip():
                    continue
                if fact.get('source_kind') == 'user_input' and not fact.get('document_id'):
                    continue
                doc = docs.get(fact.get('document_id'))
                page = next((p for p in (doc or {}).get('pages', []) if p.get('number') == fact.get('page_number')), None)
                quote = normalized(fact.get('quote', ''))
                if not doc or role(doc) not in {'product_evidence', 'transaction_evidence'} or not page or not quote or quote not in normalized(page['text']):
                    raise ValueError('Nguồn trích xuất không hợp lệ; kiểm tra tài liệu và trang.')
                original = next((s for s in draft.get('skus', []) if s['id'] == sku.get('id')), None) or next((s for s in draft.get('skus', []) if s['sku_code'] == sku['sku_code']), None)
                if not original or not any(f.get('field') == fact.get('field') and f.get('id') == fact.get('id') and f.get('quote') == fact.get('quote') and f.get('document_id') == fact.get('document_id') and f.get('page_number') == fact.get('page_number') for f in original.get('facts', [])):
                    raise ValueError('Trích dẫn không thuộc SKU đã trích xuất.')
                if sku['sku_code']!=original['sku_code']:sku['sku_code_origin']='user_input'
                source = next(f for f in original['facts'] if f.get('id') == fact.get('id'))
                from copy import deepcopy
                # Only value/review status are editable. Structural provenance is server-owned.
                for key,val in source.items():
                    if key not in {'value','status','reviewer','source_kind'}:
                        fact[key]=deepcopy(val)
                if normalized(source['value']) != normalized(fact['value']):
                    fact['source_kind'] = 'user_input'
                    fact['status'] = 'unverified'
                    fact['original_value']=source['value']
                    fact['extraction_status']='needs_review'
                    fact['source_valid']=False

    def commit_draft(self, draft_id: str, payload: Dict[str, Any], doc_service) -> Dict[str, Any]:
        """Atomically commits reviewed draft into the actual cases, skus, documents, and facts tables."""
        draft = self.get_draft(draft_id)
        if not draft:
            raise KeyError(f"Draft {draft_id} không tồn tại.")

        self._validate_reviewed_sources(self._canonical_drafts[draft_id], payload.get('skus') if payload.get('skus') is not None else draft.get('skus', []))

        owner = payload.get('owner', 'Người lập')
        title = payload.get('title') or draft['dossier_fields'].get('importer', {}).get('value') or 'Hồ sơ tạo từ chứng từ'
        trade_type = payload.get('trade_type', 'import')
        classification_date = payload.get('classification_date') or datetime.now().strftime('%Y-%m-%d')
        declaration_number = payload.get('declaration_number',draft.get('dossier_fields',{}).get('declaration_number',{}).get('value',''))
        notes = payload.get('notes', 'Khởi tạo qua luồng Document-First & Tự động điền thông tin.')

        # 1. Create Case
        case = self.db.create_case(
            title=title,
            owner=owner,
            trade_type=trade_type,
            classification_date=classification_date,
            notes=notes,
            declaration_number=declaration_number
        )
        case_id = case['id']

        try:
            # 2. Attach Documents
            doc_id_mapping = {}  # temporary doc id in draft -> real DB doc id
            draft_files = self._draft_files.get(draft_id, {})
            for draft_doc in draft.get('documents', []):
                raw_content = draft_doc.get('raw_bytes') or draft_files.get(draft_doc.get('id'))
                name = draft_doc.get('name', 'document.pdf')
                if raw_content:
                    if draft_doc.get('sha256') and hashlib.sha256(raw_content).hexdigest()!=draft_doc['sha256']:
                        raise ValueError('Nội dung bản gốc không khớp chứng từ đã trích xuất.')
                    res = doc_service.upload(case_id, name, raw_content, parsed_pages=draft_doc.get('pages',[]))
                    if res.get('documents'):
                        real_doc = res['documents'][0]
                        doc_id_mapping[draft_doc.get('id')] = real_doc['id']
                        # update kind in DB
                        with self.db.connect() as c:
                            c.execute('UPDATE documents SET kind=? WHERE id=?', (draft_doc.get('kind', 'other'), real_doc['id']))

            fields_to_save=self._review_dossier_fields(self._canonical_drafts[draft_id]['dossier_fields'],payload.get('dossier_fields') or draft.get('dossier_fields',{}))
            self.db.save_extracted_fields(case_id, fields_to_save, doc_id_mapping)
            if draft.get('matching_confirmations'):
                with self.db.connect() as conn:self.db.event(conn,case_id,None,'product_matching_confirmed',owner,{'confirmations':draft['matching_confirmations']})

            # 3. Create SKUs and Facts
            reviewed_skus = payload.get('skus') if payload.get('skus') is not None else draft.get('skus', [])
            for sku_data in reviewed_skus:
                code = sku_data.get('sku_code', 'SKU-001')
                name = sku_data.get('name', 'Mặt hàng')
                desc = sku_data.get('description', '')
                family = sku_data.get('product_family', 'general')
                declared_code = sku_data.get('declared_code')

                created_sku = self.db.add_sku(case_id, code, name, description=desc, declared_code=declared_code, product_family=family)
                sku_id = created_sku['id']

                # Add facts
                for fact in sku_data.get('facts', []):
                    field_name = fact.get('field')
                    val = fact.get('value', '').strip()
                    if not val or not field_name:
                        continue

                    draft_d_id = fact.get('document_id')
                    real_d_id = doc_id_mapping.get(draft_d_id)
                    if draft_d_id and not real_d_id:
                        raise ValueError('Thiếu bản gốc chứng từ; không chuyển thành nguồn nhập tay.')
                    p_num = fact.get('page_number', 1)
                    quote = fact.get('quote', '').strip()
                    status = fact.get('status', 'unverified')
                    if fact.get('source_kind') == 'user_input':
                        status = 'unverified'
                    reviewer = owner if status == 'verified' else None

                    try:
                        self.db.add_fact(
                            sku_id=sku_id,
                            field=field_name,
                            value=val,
                            document_id=real_d_id,
                            page_number=p_num,
                            quote=quote if quote else val,
                            status=status,
                            reviewer=reviewer,
                            source_kind='manual_declaration' if fact.get('source_kind') == 'user_input' else ('document' if real_d_id else 'manual_declaration'),
                            provenance=fact
                        )
                    except Exception as exc:
                        raise ValueError(f'Không lưu được nguồn cho {code}/{field_name}: {exc}') from exc

        except Exception:
            # Compensate writes made by Workspace methods, which own connections.
            # Uploaded content is content-addressed and may be shared by other cases.
            with self.db.lock, self.db.connect() as conn:
                conn.execute('DELETE FROM facts WHERE sku_id IN (SELECT id FROM skus WHERE case_id=?)', (case_id,))
                conn.execute('DELETE FROM pages WHERE document_id IN (SELECT id FROM documents WHERE case_id=?)', (case_id,))
                conn.execute('DELETE FROM documents WHERE case_id=?', (case_id,))
                conn.execute('DELETE FROM skus WHERE case_id=?', (case_id,))
                conn.execute('DELETE FROM events WHERE case_id=?', (case_id,))
                conn.execute('DELETE FROM cases WHERE id=?', (case_id,))
            raise

        del self.drafts[draft_id]
        self._draft_files.pop(draft_id, None)
        self._canonical_drafts.pop(draft_id, None)
        return self.db.get_case(case_id)

    def _existing_match(self,candidate,existing_skus):
        exact=next((s for s in existing_skus if s['sku_code']==candidate['sku_code']),None)
        if exact:return exact
        from .product_extraction import _relation
        matches=[]
        for sku in existing_skus:
            facts=self.db.get_sku(sku['id']).get('facts',[])
            identity={field:[f['value'] for f in facts if f['field']==field] for field in ('model','part_number')}
            if not any(identity.values()):continue
            status,_=_relation(candidate,{'facts':facts,'identifiers':identity})
            if status=='match':matches.append(sku)
        return matches[0] if len(matches)==1 else None

    def extract_for_case(self, case_id: str, doc_service) -> Dict[str, Any]:
        """Extracts candidate fields, SKUs, and reconciliation for an existing case."""
        case = self.db.get_case(case_id)
        docs = case.get('documents', [])
        if not docs:
            return {
                'case_id': case_id,
                'dossier_fields': {},
                'skus': [],
                'reconciliations': [],
                'message': 'Hồ sơ chưa có chứng từ để trích xuất.'
            }

        parsed_docs = []
        for d in docs:
            pages = doc_service.pages(d['id'])
            p_doc = {
                'id': d['id'],
                'name': d['name'],
                'sha256': d['sha256'],
                'mime': d['mime'],
                'kind': d.get('kind', 'other'),
                'pages': pages
            }
            det = DocumentTypeDetector.detect_type(p_doc)
            p_doc['detected_type'] = det['type']
            p_doc['type_confidence'] = det['confidence']
            p_doc['signals'] = det['signals']
            parsed_docs.append(p_doc)

        dossier_fields = InformationExtractor.extract_dossier_fields(parsed_docs)
        candidate_skus = InformationExtractor.extract_candidate_skus(parsed_docs)
        reconciliations = CrossDocumentReconciler.reconcile(parsed_docs, candidate_skus)

        # Annotate with existing case facts so we don't propose overwriting verified facts
        existing_skus = case.get('skus', [])
        for c_sku in candidate_skus:
            match = self._existing_match(c_sku,existing_skus)
            if match:
                c_sku['existing_sku_id'] = match['id']
                full_sku = self.db.get_sku(match['id'])
                existing_facts = full_sku.get('facts', [])
                for f in c_sku.get('facts', []):
                    ef = next((x for x in existing_facts if x['field'] == f['field']), None)
                    if ef:
                        f['existing_status'] = ef['status']
                        f['existing_value'] = ef['value']
                        if ef['status'] == 'verified':
                            f['skip_overwrite'] = True

        return {
            'case_id': case_id,
            'dossier_fields': dossier_fields,
            'skus': candidate_skus,
            'reconciliations': reconciliations,
            'summary': {
                'total_documents': len(docs),
                'total_candidate_skus': len(candidate_skus),
                'total_fields': len(dossier_fields) + sum(len(s.get('facts', [])) for s in candidate_skus),
            }
        }

    def apply_to_case(self, case_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Applies selected facts/SKUs to an existing case without overwriting verified facts."""
        case = self.db.get_case(case_id)
        existing_skus = {s['sku_code']: s for s in case.get('skus', [])}
        existing_skus_by_id = {s['id']: s for s in case.get('skus', [])}

        source_docs = []
        with self.db.connect() as conn:
            for doc in case.get('documents', []):
                source_docs.append({**doc, 'pages': [dict(p) for p in conn.execute('SELECT number,text,method FROM pages WHERE document_id=?', (doc['id'],))]})
        # Re-extraction gives stable product identities and source-scoped candidates.
        import json
        with self.db.connect() as conn:
            for doc in source_docs:
                for page in doc['pages']:
                    row=conn.execute('SELECT layout_json FROM page_layouts WHERE document_id=? AND page_number=?',(doc['id'],page['number'])).fetchone()
                    if row:page['layout']=json.loads(row[0])
        originals = InformationExtractor.extract_candidate_skus(source_docs)
        # Compare source tuples; fact UUIDs are per extraction.
        for candidate in originals:
            incoming = next((s for s in payload.get('skus', []) if s.get('id') == candidate['id'] or s['sku_code'] == candidate['sku_code']), {})
            for f in candidate['facts']:
                match = next((x for x in incoming.get('facts', []) if all(x.get(k) == f.get(k) for k in ('field', 'document_id', 'page_number', 'quote'))), None)
                if match: f['id'] = match.get('id')
        self._validate_reviewed_sources({'documents': source_docs, 'skus': originals}, payload.get('skus', []))
        dossier=InformationExtractor.extract_dossier_fields(source_docs)
        if payload.get('dossier_fields') is not None:dossier=self._review_dossier_fields(dossier,payload['dossier_fields'])
        items = payload.get('skus', [])
        for sku_data in items:
            target_sku_id = sku_data.get('existing_sku_id')
            if target_sku_id and target_sku_id not in existing_skus_by_id:
                raise ValueError('SKU không thuộc hồ sơ hiện tại.')
            if not target_sku_id and sku_data.get('sku_code') in existing_skus:
                target_sku_id = existing_skus[sku_data['sku_code']]['id']

            if target_sku_id:
                original=next((s for s in originals if s['id']==sku_data.get('id') or s['sku_code']==sku_data['sku_code']),None)
                match=self._existing_match(original,list(existing_skus.values())) if original else None
                if not match or match['id']!=target_sku_id:raise ValueError('SKU đích không khớp định danh chứng từ; cần xác nhận riêng.')

            if not target_sku_id:
                # Create as new SKU
                new_sku = self.db.add_sku(
                    case_id,
                    sku_data.get('sku_code', 'SKU-001'),
                    sku_data.get('name', 'Mặt hàng'),
                    description=sku_data.get('description', ''),
                    declared_code=sku_data.get('declared_code'),
                    product_family=sku_data.get('product_family', 'general')
                )
                target_sku_id = new_sku['id']
                current_sku = self.db.get_sku(target_sku_id)
            else:
                current_sku = self.db.get_sku(target_sku_id)

            existing_facts = {f['field']: f for f in current_sku.get('facts', [])}
            verified_fields={f['field'] for f in current_sku.get('facts',[]) if f['status']=='verified'}
            signatures={(f['field'],f['value'],f.get('document_id'),f.get('page_number'),f.get('quote','')) for f in current_sku.get('facts',[])}

            for fact in sku_data.get('facts', []):
                field_name = fact.get('field')
                val = fact.get('value', '').strip()
                if not val or not field_name:
                    continue

                # Never overwrite verified facts
                if field_name in verified_fields:
                    continue

                doc_id = fact.get('document_id')
                p_num = fact.get('page_number', 1)
                quote = fact.get('quote', '').strip()
                signature=(field_name,val,doc_id,p_num,quote)
                if signature in signatures:continue

                try:
                    self.db.add_fact(
                        sku_id=target_sku_id,
                        field=field_name,
                        value=val,
                        document_id=doc_id,
                        page_number=p_num,
                        quote=quote if quote else val,
                        status='unverified',
                        reviewer=None,
                        source_kind='manual_declaration' if fact.get('source_kind') == 'user_input' else ('document' if doc_id else 'manual_declaration'),
                        provenance=fact
                    )
                    signatures.add(signature)
                except Exception as exc:
                    raise ValueError(f'Không lưu được nguồn cho {field_name}: {exc}') from exc

        self.db.save_extracted_fields(case_id,dossier,{d['id']:d['id'] for d in source_docs})
        return self.db.get_case(case_id)

