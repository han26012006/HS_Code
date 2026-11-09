"""Intelligent Document Type Detection, Information Extraction, and Cross-Document Reconciliation.

Pure local extraction: deterministic regex, dictionary matching, tabular scanning,
and exact text substring provenance (no external API calls or hallucinated quotes).
"""
from __future__ import annotations

import io
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
            if total_pages == 0:
                total_pages = 1

            # Detect available OCR & extraction engines
            tess_bin = shutil.which('tesseract')
            ppm_bin = shutil.which('pdftoppm')
            pdftotext_bin = shutil.which('pdftotext')

            # Language for tesseract
            ocr_lang = 'eng'
            if tess_bin:
                try:
                    langs = subprocess.check_output([tess_bin, '--list-langs'], text=True).split()
                    if 'vie' in langs and 'eng' in langs:
                        ocr_lang = 'vie+eng'
                    elif 'vie' in langs:
                        ocr_lang = 'vie'
                    else:
                        ocr_lang = 'eng'
                except Exception:
                    pass

            for i in range(1, total_pages + 1):
                txt = ''
                method = 'pdf_text'
                # 1. Try pypdf text extraction
                try:
                    if i <= len(reader.pages):
                        txt = reader.pages[i - 1].extract_text() or ''
                except Exception:
                    txt = ''

                # 2. If text is too short, try pdftotext
                if sum(c.isalpha() for c in txt) < 40 and pdftotext_bin and tmp_pdf_path:
                    try:
                        p_res = subprocess.run([pdftotext_bin, '-f', str(i), '-l', str(i), '-layout', tmp_pdf_path, '-'],
                                               capture_output=True, text=True, timeout=20)
                        if p_res.returncode == 0 and len(p_res.stdout.strip()) > len(txt.strip()):
                            txt = p_res.stdout
                            method = 'pdftotext'
                    except Exception:
                        pass

                # 3. If text is still too short and OCR tools are available, run OCR on scanned page
                if sum(c.isalpha() for c in txt) < 40 and tess_bin and ppm_bin and tmp_pdf_path:
                    try:
                        with tempfile.TemporaryDirectory() as td:
                            prefix = Path(td) / f"page_{i}"
                            cmd_ppm = [ppm_bin, '-f', str(i), '-l', str(i), '-singlefile', '-r', '200', '-png', tmp_pdf_path, str(prefix)]
                            p_ppm = subprocess.run(cmd_ppm, capture_output=True, timeout=30)
                            img_out = str(prefix) + '.png'
                            if Path(img_out).exists():
                                p_tess = subprocess.run([tess_bin, img_out, 'stdout', '-l', ocr_lang, '--psm', '6'],
                                                        capture_output=True, text=True, timeout=40)
                                if p_tess.returncode == 0 and len(p_tess.stdout.strip()) > len(txt.strip()):
                                    txt = p_tess.stdout
                                    method = f"ocr_{ocr_lang}"
                    except Exception:
                        pass

                pages.append({'number': i, 'text': txt, 'method': method})

        except Exception as exc:
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
            for idx, sheet in enumerate(wb.worksheets, 1):
                sheet_lines = [f"[{sheet.title}]"]
                for row in sheet.iter_rows():
                    vals = [f"{c.coordinate}={c.value}" for c in row if c.value is not None]
                    if vals:
                        sheet_lines.append(' | '.join(vals))
                pages.append({'number': idx, 'text': '\n'.join(sheet_lines), 'method': 'xlsx_sheet'})
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
                p = subprocess.run([tess_bin, tmp_path, 'stdout', '-l', ocr_lang, '--psm', '6'], capture_output=True, text=True, timeout=60)
                txt = p.stdout if p.returncode == 0 else ''
                Path(tmp_path).unlink(missing_ok=True)
                pages.append({'number': 1, 'text': txt, 'method': f"ocr_{ocr_lang}"})
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

    return pages


class DocumentTypeDetector:
    """Classifies document type using rule-based scoring and evidence gathering."""

    @classmethod
    def detect(cls, text: str) -> Dict[str, Any]:
        import unicodedata
        normalized = unicodedata.normalize('NFC', text).lower()
        if re.search(r'danh\s*mục\s*hàng\s*hóa\s*xuất\s*khẩu|\b\d+/\d{4}/TT-BTC\b|chú\s*giải\s*(?:HS|phân|chương)|harmonized\s*(?:system|tariff)|nghị\s*định\s*số', normalized, re.I):
            return dict(kind='legal_reference', type='legal_reference', confidence=None, signals=['legal_content'], status='needs_review', label=DOC_TYPES['legal_reference'])
        scores = {}
        matched_signals = {}

        for doc_type, rules in DOC_TYPE_SIGNALS.items():
            score = 0
            signals = []
            for pattern, weight in rules:
                matches = re.findall(pattern, normalized, re.IGNORECASE)
                if matches:
                    score += weight * min(len(matches), 3)
                    signals.append(pattern)
            if score > 0:
                scores[doc_type] = score
                matched_signals[doc_type] = signals

        if not scores:
            return {
                'kind': 'other',
                'type': 'other',
                'confidence': None,
                'signals': [],
                'status': 'unverified',
                'label': DOC_TYPES['other'],
            }

        best_type = max(scores, key=scores.get)
        conf = None  # Rule scores are not calibrated probabilities.

        return {
            'kind': best_type,
            'type': best_type,
            'confidence': conf,
            'signals': matched_signals[best_type][:5],
            'status': 'needs_review',
            'label': DOC_TYPES.get(best_type, best_type),
        }

    @classmethod
    def detect_type(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        all_text = '\n'.join(p.get('text', '') for p in doc.get('pages', []))
        return cls.detect(all_text)



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
        from .product_extraction import normalized
        fields = {}
        for doc in docs:
            for name, candidate in cls._extract_dossier_document_fields([doc]).items():
                if name not in fields:
                    fields[name] = candidate
                elif normalized(fields[name]['value']) != normalized(candidate['value']):
                    previous = fields[name]
                    alternatives = previous.get('alternatives', [dict(previous)])
                    alternatives.append(candidate)
                    fields[name] = {**previous, 'value': '', 'status': 'conflicting',
                                    'verification_status': 'pending_review', 'alternatives': alternatives}
        return fields

    @classmethod
    def _extract_dossier_document_fields(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extracts shipment & dossier metadata from one or more documents."""
        fields = {}

        from .product_extraction import role
        for doc in sorted(docs, key=lambda d: (d.get('sha256', ''), d.get('name', ''))):
            if role(doc) != 'transaction_evidence':
                continue
            doc_id = doc.get('id', '')
            doc_name = doc.get('name', 'Tài liệu')
            for page in doc.get('pages', []):
                p_num = page.get('number', 1)
                text = page.get('text', '')

                # Document Number (Thông tư, Quyết định, Thông báo kết quả phân loại)
                if 'document_number' not in fields:
                    m = re.search(r'(?:thông\s*tư\s*số|số\s*thông\s*tư|thông\s*báo\s*số|số\s*thông\s*báo|quyết\s*định\s*số|số\s*quyết\s*định|số\s*văn\s*bản|số\s*công\s*văn|số\s*hđ|số|no\.?)[\s:=|]+([0-9]{1,6}\/[A-Za-z0-9\/\-_]+)', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['document_number'] = cls._make_field('document_number', val, doc_id, doc_name, p_num, quote)

                # Invoice No & Date
                if 'invoice_number' not in fields:
                    m = re.search(r'(?:invoice\s*no\.?|số\s*h[óo]a\s*đơn|发票号|hđ\s*số)[\s:=]+([A-Z0-9\/\-_]{3,30})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['invoice_number'] = cls._make_field('invoice_number', val, doc_id, doc_name, p_num, quote)

                if 'invoice_date' not in fields:
                    m = re.search(r'(?:invoice\s*date|ngày\s*h[óo]a\s*đơn|date\s*of\s*delivery|发货日期)[\s:=]+([0-9]{4}[-/][0-9]{2}[-/][0-9]{2}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{4})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['invoice_date'] = cls._make_field('invoice_date', val, doc_id, doc_name, p_num, quote)

                # Declaration No & Date
                if 'declaration_number' not in fields:
                    m = re.search(r'(?:số\s*tờ\s*khai|tờ\s*khai\s*số)[\s:=|]+([0-9]{11,12})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['declaration_number'] = cls._make_field('declaration_number', val, doc_id, doc_name, p_num, quote)

                # Exporter / Seller
                if 'exporter' not in fields:
                    m = re.search(r'(?:the\s*seller|seller|shipper|người\s*xuất\s*khẩu|deliver)[\s:=|]+([A-Za-z0-9\s,\u00C0-\u1EF9]{4,60})', text, re.IGNORECASE)
                    if m and not re.search(r'address|add:|tel|email|mã|phân\s*loại', m.group(1), re.IGNORECASE):
                        val = m.group(1).strip(' :|-')
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text and len(val) >= 3:
                            fields['exporter'] = cls._make_field('exporter', val, doc_id, doc_name, p_num, quote)

                # Importer / Consignee
                if 'importer' not in fields:
                    m = re.search(r'(?:the\s*buyer|buyer|consignee|customer|người\s*nhập\s*khẩu|khách\s*hàng)[\s:=|]+([A-Za-z0-9\s,\u00C0-\u1EF9]{4,60})', text, re.IGNORECASE)
                    if m and not re.search(r'address|add:|tel|email|mã|phân\s*loại', m.group(1), re.IGNORECASE):
                        val = m.group(1).strip(' :|-')
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text and len(val) >= 3:
                            fields['importer'] = cls._make_field('importer', val, doc_id, doc_name, p_num, quote)

                # Incoterms
                if 'incoterms' not in fields:
                    m = re.search(r'\b(CIF|FOB|CFR|EXW|DAP|DDP|FCA|CIP|CPT)\b(?:\s+([A-Za-z\s,]{3,35}))?', text, re.IGNORECASE)
                    if m:
                        val = m.group(0).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['incoterms'] = cls._make_field('incoterms', val.upper(), doc_id, doc_name, p_num, quote)

                # Currency
                if 'currency' not in fields:
                    m = re.search(r'\b(USD|EUR|VND|JPY|CNY|RMB|SGD|GBP)\b', text)
                    if m:
                        val = m.group(1)
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['currency'] = cls._make_field('currency', val, doc_id, doc_name, p_num, quote)

                # Total Weight (Gross & Net)
                if 'total_gross_weight' not in fields:
                    m = re.search(r'(?:gross\s*weight|g\.?w\.?|tổng\s*trọng\s*lượng|总毛重)[\s:=|]+([0-9,.]+)\s*(kg|kgs|mt|tons?)?', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip() + (' ' + m.group(2) if m.group(2) else '')
                        quote = cls._find_exact_quote(text, m.group(1)) or m.group(0)
                        if quote in text:
                            fields['total_gross_weight'] = cls._make_field('total_gross_weight', val, doc_id, doc_name, p_num, quote, unit='kg')

                if 'total_net_weight' not in fields:
                    m = re.search(r'(?:net\s*weight|n\.?w\.?|trọng\s*lượng\s*tịnh)[\s:=|]+([0-9,.]+)\s*(kg|kgs|mt|tons?)?', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip() + (' ' + m.group(2) if m.group(2) else '')
                        quote = cls._find_exact_quote(text, m.group(1)) or m.group(0)
                        if quote in text:
                            fields['total_net_weight'] = cls._make_field('total_net_weight', val, doc_id, doc_name, p_num, quote, unit='kg')

                # Ports
                if 'port_of_loading' not in fields:
                    m = re.search(r'(?:port\s*of\s*loading|cảng\s*xếp|cảng\s*đi|export\s*port)[\s:=|]+([A-Za-z\s\u00C0-\u1EF9]{3,35})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['port_of_loading'] = cls._make_field('port_of_loading', val, doc_id, doc_name, p_num, quote)

                if 'port_of_discharge' not in fields:
                    m = re.search(r'(?:port\s*of\s*discharge|destination|cảng\s*dỡ|cảng\s*đến|đáo\s*trạm|到站港)[\s:=|]+([A-Za-z\s\u00C0-\u1EF9]{3,35})', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['port_of_discharge'] = cls._make_field('port_of_discharge', val, doc_id, doc_name, p_num, quote)

                # Total Value / Total Amount
                if 'total_value' not in fields:
                    m = re.search(r'(?:total\s*amount|total\s*value|grand\s*total|tổng\s*tiền|tổng\s*trị\s*giá)[\s:=|]+([0-9,.]+)', text, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        quote = cls._find_exact_quote(text, val) or m.group(0)
                        if quote in text:
                            fields['total_value'] = cls._make_field('total_value', val, doc_id, doc_name, p_num, quote)

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
        reconciliations = []

        # 1. Compare total weights between invoice and packing list
        invoice_doc = next((d for d in docs if d.get('kind') in ('commercial_invoice', 'invoice')), None)
        pl_doc = next((d for d in docs if d.get('kind') == 'packing_list'), None)

        if invoice_doc and pl_doc:
            inv_text = '\n'.join(p.get('text', '') for p in invoice_doc.get('pages', []))
            pl_text = '\n'.join(p.get('text', '') for p in pl_doc.get('pages', []))

            # Weight extraction
            inv_gw = re.search(r'(?:gross\s*weight|g\.?w\.?)[\s:=|]+([0-9,.]+)', inv_text, re.IGNORECASE)
            pl_gw = re.search(r'(?:gross\s*weight|g\.?w\.?)[\s:=|]+([0-9,.]+)', pl_text, re.IGNORECASE)

            if inv_gw and pl_gw:
                w1 = inv_gw.group(1).replace(',', '')
                w2 = pl_gw.group(1).replace(',', '')
                try:
                    is_match = abs(float(w1) - float(w2)) < 0.01
                    reconciliations.append({
                        'field': 'gross_weight',
                        'label': 'Tổng trọng lượng cả bì (Gross Weight)',
                        'status': 'match' if is_match else 'conflict',
                        'items': [
                            {'source': invoice_doc.get('name'), 'value': inv_gw.group(0), 'page': 1},
                            {'source': pl_doc.get('name'), 'value': pl_gw.group(0), 'page': 1},
                        ],
                        'description': 'Khớp trọng lượng cả bì giữa Invoice và Packing List.' if is_match else f"Mâu thuẫn trọng lượng: Invoice ghi {w1} nhưng Packing List ghi {w2}.",
                    })
                except ValueError:
                    pass

        # 2. Check for specification conflicts across documents for each SKU
        for sku in skus:
            spec_facts = [f for f in sku.get('facts', []) if f['field'] == 'specifications']
            powers = {}
            for f in spec_facts:
                m_pwr = re.search(r'(\d{3,4})\s*w\b', f['value'], re.IGNORECASE)
                if m_pwr:
                    pwr_val = m_pwr.group(1)
                    doc_n = f.get('document_name', 'Tài liệu')
                    powers[doc_n] = (pwr_val, f)

            if len(powers) > 1 and len(set(v[0] for v in powers.values())) > 1:
                vals = list(powers.items())
                reconciliations.append({
                    'field': 'power',
                    'label': f"Công suất kỹ thuật ({sku.get('sku_code')})",
                    'status': 'conflict',
                    'items': [{'source': k, 'value': v[1]['value'], 'page': v[1]['page_number']} for k, v in powers.items()],
                    'description': f"Mâu thuẫn công suất giữa các tài liệu cho cùng SKU: {vals[0][0]} ghi {vals[0][1][0]}W nhưng {vals[1][0]} ghi {vals[1][1][0]}W.",
                })

        return reconciliations


class AutoFillDraftManager:
    """Manages draft state for Document-First onboarding and handles atomic commits."""

    def __init__(self, workspace_db):
        self.db = workspace_db
        self.drafts: Dict[str, Dict[str, Any]] = {}
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
            all_text = '\n\n'.join(p.get('text', '') for p in doc.get('pages', [])).strip()
            detected = DocumentTypeDetector.detect(all_text)
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
        self.drafts[draft_id] = draft
        return draft

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        return self.drafts.get(draft_id)

    def update_draft(self, draft_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        draft = self.get_draft(draft_id)
        if not draft:
            raise KeyError(f"Draft {draft_id} không tồn tại.")
        if 'dossier_fields' in updates:
            draft['dossier_fields'].update(updates['dossier_fields'])
        if 'skus' in updates:
            self._validate_reviewed_sources(draft, updates['skus'])
            draft['skus'] = updates['skus']
            draft['proposed_skus'] = draft['skus']
        return draft

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
                original = next((s for s in draft.get('skus', []) if s['sku_code'] == sku['sku_code']), None)
                if not original or not any(f.get('field') == fact.get('field') and f.get('id') == fact.get('id') and f.get('quote') == fact.get('quote') and f.get('document_id') == fact.get('document_id') and f.get('page_number') == fact.get('page_number') for f in original.get('facts', [])):
                    raise ValueError('Trích dẫn không thuộc SKU đã trích xuất.')
                source = next(f for f in original['facts'] if f.get('id') == fact.get('id'))
                if normalized(source['value']) != normalized(fact['value']):
                    fact['source_kind'] = 'user_input'
                    fact['status'] = 'unverified'

    def commit_draft(self, draft_id: str, payload: Dict[str, Any], doc_service) -> Dict[str, Any]:
        """Atomically commits reviewed draft into the actual cases, skus, documents, and facts tables."""
        draft = self.get_draft(draft_id)
        if not draft:
            raise KeyError(f"Draft {draft_id} không tồn tại.")

        self._validate_reviewed_sources(draft, payload.get('skus', draft.get('skus', [])))

        owner = payload.get('owner', 'Người lập')
        title = payload.get('title') or draft['dossier_fields'].get('importer', {}).get('value') or 'Hồ sơ tạo từ chứng từ'
        trade_type = payload.get('trade_type', 'import')
        classification_date = payload.get('classification_date') or datetime.now().strftime('%Y-%m-%d')
        declaration_number = payload.get('declaration_number', '')
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
                    res = doc_service.upload(case_id, name, raw_content)
                    if res.get('documents'):
                        real_doc = res['documents'][0]
                        doc_service.process(real_doc['id'])
                        doc_id_mapping[draft_doc.get('id')] = real_doc['id']
                        # update kind in DB
                        with self.db.connect() as c:
                            c.execute('UPDATE documents SET kind=? WHERE id=?', (draft_doc.get('kind', 'other'), real_doc['id']))

            # 3. Create SKUs and Facts
            reviewed_skus = payload.get('skus', draft.get('skus', []))
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
                            source_kind='manual_declaration' if fact.get('source_kind') == 'user_input' else ('document' if real_d_id else 'manual_declaration')
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
        return self.db.get_case(case_id)

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
                'pages': [{'number': p.get('number') or p.get('page_number', 1), 'page_number': p.get('number') or p.get('page_number', 1), 'text': p['text']} for p in pages]
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
            match = next((s for s in existing_skus if s['sku_code'] == c_sku['sku_code']), None)
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
        originals = InformationExtractor.extract_candidate_skus(source_docs)
        # Compare source tuples; fact UUIDs are per extraction.
        for candidate in originals:
            incoming = next((s for s in payload.get('skus', []) if s['sku_code'] == candidate['sku_code']), {})
            for f in candidate['facts']:
                match = next((x for x in incoming.get('facts', []) if all(x.get(k) == f.get(k) for k in ('field', 'document_id', 'page_number', 'quote'))), None)
                if match: f['id'] = match.get('id')
        self._validate_reviewed_sources({'documents': source_docs, 'skus': originals}, payload.get('skus', []))
        items = payload.get('skus', [])
        for sku_data in items:
            target_sku_id = sku_data.get('existing_sku_id')
            if target_sku_id and target_sku_id not in existing_skus_by_id:
                raise ValueError('SKU không thuộc hồ sơ hiện tại.')
            if not target_sku_id and sku_data.get('sku_code') in existing_skus:
                target_sku_id = existing_skus[sku_data['sku_code']]['id']

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

            for fact in sku_data.get('facts', []):
                field_name = fact.get('field')
                val = fact.get('value', '').strip()
                if not val or not field_name:
                    continue

                # Never overwrite verified facts
                if field_name in existing_facts and existing_facts[field_name]['status'] == 'verified':
                    continue

                doc_id = fact.get('document_id')
                p_num = fact.get('page_number', 1)
                quote = fact.get('quote', '').strip()

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
                        source_kind='manual_declaration' if fact.get('source_kind') == 'user_input' else ('document' if doc_id else 'manual_declaration')
                    )
                except Exception as exc:
                    raise ValueError(f'Không lưu được nguồn cho {field_name}: {exc}') from exc

        return self.db.get_case(case_id)

