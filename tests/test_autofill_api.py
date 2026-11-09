from test_workspace import client


def test_draft_api_to_save_load_and_incremental_apply(client):
    text=b'TECHNICAL SPECIFICATION\nModel: API-1\nProduct name: Household dryer\nFunction: Dry hair\nPower: 1200 W\n'
    r=client.post('/api/v2/autofill/draft',files=[('files',('spec.txt',text,'text/plain')),('files',('law.txt','Danh mục hàng hóa xuất khẩu, nhập khẩu Việt Nam\n31/2022/TT-BTC\n8507.10.10'.encode(),'text/plain'))])
    assert r.status_code==200,r.text
    d=r.json();assert len(d['skus'])==1
    assert d['extracted_case']['declaration_number']==''
    assert client.get('/api/v2/autofill/draft/'+d['draft_id']).status_code==200
    r=client.post('/api/v2/autofill/draft/'+d['draft_id']+'/commit',json={'owner':'API Tester','title':'API extraction test','skus':d['skus']})
    assert r.status_code==200,r.text
    case=r.json();assert len(case['skus'])==1 and case['declaration_number']==''
    sku=client.get('/api/v2/skus/'+case['skus'][0]['id']).json()
    assert sku['facts'] and all(f['document_id'] and f['status']=='unverified' for f in sku['facts'])
    extracted=client.post('/api/v2/cases/'+case['id']+'/autofill').json()
    assert len(extracted['skus'])==1
    r=client.post('/api/v2/cases/'+case['id']+'/autofill/apply',json={'skus':extracted['skus']})
    assert r.status_code==200,r.text
    assert len(r.json()['skus'])==1
