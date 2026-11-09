import time

from test_workspace import client, dossier, ready, evidence, analyze, approve


def attach(client, case, content, sku=None):
    path = '/api/v2/cases/'+case['id']+'/documents'
    data = {'sku_id':sku['id']} if sku else {}
    return client.post(path, files=[('files',('technical.txt',content.encode(),'text/plain'))], data=data)


def wait_for_text(client, document):
    for _ in range(50):
        record = client.get('/api/v2/documents/'+document['id']).json()
        if record['pages']:
            return
        time.sleep(.02)
    raise AssertionError('Document extraction did not finish')


def test_same_case_does_not_authorize_another_sku_document(client):
    case, first = dossier(client)
    second = client.post('/api/v2/cases/'+case['id']+'/skus',
                         json={'sku_code':'SKU-2','name':'Mặt hàng thứ hai'}).json()
    source = 'Đoạn chứng từ kỹ thuật dành riêng cho mặt hàng thứ hai.'
    res = attach(client,case,source,second)
    assert res.status_code == 200, res.text
    document = res.json()['documents'][0]
    wait_for_text(client,document)
    source_payload = {'document_id':document['id'],'page_number':1,'quote':source}
    fact = {'field':'specifications','value':'Kích thước 30 mm','status':'verified','reviewer':'Người thử',**source_payload}
    legal = {'kind':'technical','title':'Chứng từ kiểm thử','role':'reference',**source_payload}
    for endpoint, body in (('facts',fact),('evidence',legal)):
        blocked = client.post('/api/v2/skus/'+first['id']+'/'+endpoint,json=body)
        assert blocked.status_code == 422 and 'SKU' in blocked.json()['detail']
        assert client.post('/api/v2/skus/'+second['id']+'/'+endpoint,json=body).status_code == 200
    assert attach(client,case,source,first).status_code == 422

    shared_text = 'Bản xác nhận chung cho các SKU trong cùng hồ sơ này.'
    shared = attach(client,case,shared_text).json()['documents'][0]
    wait_for_text(client,shared)
    fact.update(document_id=shared['id'],quote=shared_text)
    for sku in (first,second):
        assert client.post('/api/v2/skus/'+sku['id']+'/facts',json=fact).status_code == 200


def test_legacy_cross_sku_evidence_is_flagged_and_cannot_approve(client):
    case, first = dossier(client)
    first = ready(client,first)
    first = evidence(client,first)
    first = analyze(client,first)
    second = client.post('/api/v2/cases/'+case['id']+'/skus',
                         json={'sku_code':'SKU-2','name':'Mặt hàng thứ hai'}).json()
    doc = attach(client,case,'Tài liệu của SKU thứ hai.',second).json()['documents'][0]
    import api
    with api.state['db'].connect() as conn:
        conn.execute('UPDATE evidence SET document_id=? WHERE id=?',(doc['id'],first['evidence'][0]['id']))
        conn.execute('UPDATE facts SET document_id=? WHERE id=?',
                     (doc['id'],next(f['id'] for f in first['facts'] if f['field']=='name')))
    updated = client.get('/api/v2/skus/'+first['id']).json()
    assert updated['evidence'][0]['document_scope_mismatch']
    assert not updated['readiness']['can_analyze']
    assert approve(client,updated).status_code==422
    with api.state['db'].connect() as conn:
        conn.execute('UPDATE facts SET document_id=NULL WHERE sku_id=?',(first['id'],))
    result = approve(client,client.get('/api/v2/skus/'+first['id']).json())
    assert result.status_code==422 and 'SKU khác' in result.json()['detail']
