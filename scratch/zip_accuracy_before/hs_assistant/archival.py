"""Portable evidence copies with an integrity manifest, not a digital signature."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from . import __version__
from .workspace import WorkspaceError

MAX_ARCHIVE_BYTES = 512 * 1024**2


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def source_context(root, catalogue_version):
    root = Path(root)
    files = ['data/catalogue.jsonl', 'data/legal_notes.json', 'data/legal_sources.json',
             'data/tax/TAX_SOURCE_RECEIPT.json', 'data/tax/TAX_LEGAL_REGISTRY.json',
             'data/precedent_index.jsonl', 'data/precedent_lifecycle.json']
    return {'application_version': __version__, 'catalogue_version': catalogue_version,
            'files': {p: hashlib.sha256((root/p).read_bytes()).hexdigest()
                      for p in files if (root/p).is_file()},
            'legal_registry': json.loads((root/'data/legal_sources.json').read_text()),
            'tax_receipt': json.loads((root/'data/tax/TAX_SOURCE_RECEIPT.json').read_text()),
            'automatic_current_law_certification': False}


def build_case_archive(case, workspace, root):
    """Validate every document before any final archive is returned to a user."""
    root = Path(root)
    files = []
    size = 0
    with workspace.connect() as db:
        records = [dict(r) for r in db.execute('SELECT * FROM documents WHERE case_id=?', (case['id'],))]
    for r in records:
        path = Path(r['path'])
        if not path.is_file():
            raise WorkspaceError('Thiếu bản gốc chứng từ '+r['name']+'; chưa thể xuất gói lưu bằng chứng đầy đủ.')
        size += path.stat().st_size
        if size > MAX_ARCHIVE_BYTES:
            raise WorkspaceError('Gói chứng từ vượt 512 MB; sao lưu workspace bằng công cụ quản trị được hướng dẫn.')
        name = re.sub(r'[^\w.\-]+', '_', Path(r['name']).name)[:100]
        files.append(('documents/'+r['id']+'_'+name, path, r['sha256']))
    sources = json.loads((root/'data/legal_sources.json').read_text())
    for s in sources.get('rules', []):
        if s.get('packaged_official_pdf') and s.get('local_file'):
            name = s['local_file']
            if Path(name).name != name: raise WorkspaceError('Tên tệp trong registry không an toàn.')
            files.append(('official_sources/'+name, root/'data/legal_documents'/name, s['sha256']))
    directory = Path(tempfile.mkdtemp(prefix='hs-evidence-'))
    target = directory/(case['reference']+'.zip')
    manifest = {'schema_version': 'case-archive-1', 'file_hashes': {},
                'hash_algorithm': 'SHA256', 'digital_signature': False,
                'trusted_external_timestamp': False, 'retention_guaranteed_by_export': False,
                'note': 'Sao lưu và kiểm tra phục hồi riêng. Nguồn chỉ có URL/đoạn trích chưa có bản gốc trong gói.'}
    try:
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, path, expected in files:
                digest = hashlib.sha256()
                with path.open('rb') as src, z.open(name, 'w') as dest:
                    for block in iter(lambda: src.read(1024*1024), b''):
                        digest.update(block); dest.write(block)
                if digest.hexdigest() != expected:
                    raise WorkspaceError('Bản gốc không khớp SHA256 đã lưu: '+path.name)
                manifest['file_hashes'][name] = digest.hexdigest()
            payloads = {'dossier.json': case, 'legal_registry.json': sources,
                        'audit_chain_check.json': workspace.verify_events()}
            lifecycle = root/'data/precedent_lifecycle.json'
            if lifecycle.is_file():
                payloads['precedent_lifecycle.json'] = json.loads(lifecycle.read_text(encoding='utf-8'))
            for name, value in payloads.items():
                content = canonical(value); z.writestr(name, content)
                manifest['file_hashes'][name] = hashlib.sha256(content).hexdigest()
            z.writestr('MANIFEST.json', canonical(manifest))
        return target, directory
    except Exception:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)
        raise
