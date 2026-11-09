"""Optional geometry from the existing Tesseract engine; no new OCR dependency.

The TSV mode is opt-in until reviewed real scanned-document evaluation exists.
Raw engine confidence applies to recognition only, never to semantic facts.
"""
import csv
import io
import os
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path


def geometry_from_tsv(tsv):
    words=[]
    for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
        if row.get('level')!='5' or not row.get('text','').strip():continue
        try:
            x,y,w,h=[int(row[k]) for k in ('left','top','width','height')]
            words.append({'text':row['text'],'bbox':[x,y,x+w,y+h], 'recognition_confidence':float(row['conf']),
                          'block':row['block_num'],'paragraph':row['par_num'],'line':row['line_num']})
        except (KeyError,ValueError):continue
    return words


def aligned_text(words):
    """Rebuild horizontal gaps from measured word positions, with no invented text."""
    if not words:return ''
    widths=[(w['bbox'][2]-w['bbox'][0])/len(w['text']) for w in words if w['text']]
    cell=max(1,statistics.median(widths));origin=min(w['bbox'][0] for w in words)
    lines={}
    for word in words:lines.setdefault((word['block'],word['paragraph'],word['line']),[]).append(word)
    rendered=[]
    for line in sorted(lines.values(),key=lambda x:(min(w['bbox'][1] for w in x),min(w['bbox'][0] for w in x))):
        text=''
        for word in sorted(line,key=lambda w:w['bbox'][0]):
            column=round((word['bbox'][0]-origin)/cell)
            text+=' '*max(1 if text else 0,column-len(text))+word['text']
        rendered.append(text.rstrip())
    return '\n'.join(rendered)


def read_image(path,*,layout_enabled=None):
    executable=shutil.which('tesseract')
    if not executable:raise RuntimeError('Cần Tesseract cho tài liệu scan.')
    env=dict(os.environ,OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
    if os.environ.get('HS_TESSDATA_PREFIX'):env['TESSDATA_PREFIX']=os.environ['HS_TESSDATA_PREFIX']
    langs=subprocess.run([executable,'--list-langs'],capture_output=True,text=True,timeout=10,env=env).stdout.split()
    lang='vie+eng' if {'vie','eng'}<=set(langs) else 'vie' if 'vie' in langs else 'eng'
    enabled=os.environ.get('HS_OCR_LAYOUT_TSV','0')=='1' if layout_enabled is None else layout_enabled
    with tempfile.TemporaryDirectory() as directory:
        prefix=Path(directory)/'recognition'
        result=subprocess.run([executable,str(path),str(prefix),'-l',lang,'--psm','6','txt','tsv'],capture_output=True,text=True,timeout=90,env=env)
        if result.returncode:raise RuntimeError('Tesseract: '+result.stderr[-400:])
        text=prefix.with_suffix('.txt').read_text()
        words=geometry_from_tsv(prefix.with_suffix('.tsv').read_text())
        return {'text':aligned_text(words) if enabled else text,'method':'ocr_'+lang+('_tsv_layout' if enabled else ''),'geometry':words,
                'warnings':[{'stage':'ocr','status':'needs_review','message':'OCR recognition requires review; TSV layout is opt-in'}]}
