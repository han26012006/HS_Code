"""Shared page-preserving PDF text/OCR stage for draft and persisted ingestion."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from .document_layout import pdf_geometry


def read_pdf_page(path,number,reader):
    text='';method='pdf_text';warnings=[];geometry=[]
    poppler=shutil.which('pdftotext')
    if poppler:
        try:
            result=subprocess.run([poppler,'-f',str(number),'-l',str(number),'-layout',str(path),'-'],capture_output=True,text=True,timeout=30)
            if result.returncode==0:text=result.stdout;method='pdftotext'
            else:warnings.append({'stage':'text_extraction','status':'needs_review','message':'Poppler extraction failed; trying PDF text layer'})
        except (subprocess.SubprocessError,OSError):warnings.append({'stage':'text_extraction','status':'needs_review','message':'Poppler unavailable for this page'})
    if not text.strip():
        try:text=reader.pages[number-1].extract_text(extraction_mode='layout') or '';method='pdf_text'
        except Exception as exc:warnings.append({'stage':'text_extraction','status':'needs_review','message':str(exc)[:200]})
    corrupt=text.count('\ufffd')>max(2,len(text)*.05)
    # A small digital date/stamp over a scanned page is not a usable text layer.
    try:
        image_heavy=sum(c.isalnum() for c in text)<80 and len(reader.pages[number-1].images)>0
    except Exception:image_heavy=False
    sparse_scan=image_heavy and sum(c.isalnum() for c in text)<80
    if sparse_scan:warnings.append({'stage':'text_extraction','status':'needs_review','message':'Sparse text overlay on image page; OCR required'})
    if not text.strip() or corrupt or sparse_scan:
        if not shutil.which('pdftoppm') or not shutil.which('tesseract'):
            warnings.append({'stage':'ocr','status':'missing','message':'Page needs OCR but Poppler/Tesseract is unavailable'})
        else:
            try:
                dpi=max(100,min(600,int(os.environ.get('HS_OCR_DPI','300'))))
                with tempfile.TemporaryDirectory() as directory:
                    prefix=Path(directory)/'page'
                    result=subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-singlefile','-r',str(dpi),'-png',str(path),str(prefix)],capture_output=True,timeout=60)
                    if result.returncode:raise RuntimeError('PDF page rasterization failed')
                    from .ocr_layout import read_image
                    ocr=read_image(str(prefix)+'.png');text,method,geometry=ocr['text'],ocr['method'],ocr['geometry'];warnings+=ocr['warnings']
            except Exception as exc:
                warnings.append({'stage':'ocr','status':'missing','message':str(exc)[:200]})
    if method in {'pdftotext','pdf_text'}:geometry=pdf_geometry(path,number)
    if not text.strip():warnings.append({'stage':'text_extraction','status':'missing','message':'No readable page text; review original image'})
    tables=[]
    if method in {'pdftotext','pdf_text'} and os.environ.get('HS_PDF_TABLES','1')=='1':
        try:
            from .pdf_tables import extract_pdf_tables
            context=getattr(reader,'_hs_table_context',{})
            tables=extract_pdf_tables(path,number,geometry,text,context)
            reader._hs_table_context=context
        except Exception as exc:warnings.append({'stage':'layout','status':'needs_review','message':'Physical table extraction unavailable: '+str(exc)[:120]})
    return {'pdf_tables':tables,'number':number,'text':text,'method':method,'geometry':geometry,'warnings':warnings}
