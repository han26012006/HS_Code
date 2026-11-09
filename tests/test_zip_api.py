from pathlib import Path
from test_workspace import client


def test_real_pdf_table_draft_api_commit_load(client):
    content=(Path(__file__).parent/'fixtures/zip_accuracy/254374c4.pdf').read_bytes()
    response=client.post('/api/v2/autofill/draft',files=[('files',('opaque.pdf',content,'application/pdf'))])
    assert response.status_code==200,response.text
    draft=response.json();assert len(draft['skus'])==9
    saved=client.post('/api/v2/autofill/draft/'+draft['draft_id']+'/commit',json={'title':'ZIP real PDF API check','owner':'QA Tester','skus':draft['skus']})
    assert saved.status_code==200,saved.text
    case=saved.json();assert len(case['skus'])==9
    for sku in case['skus']:
        loaded=client.get('/api/v2/skus/'+sku['id']).json()
        assert any(f.get('source_cell_bbox')for f in loaded['facts'])
        assert all(f['status']=='unverified'for f in loaded['facts'])
        assert all(f['document_id']==f['source_document_id']for f in loaded['facts'])
