"""Exercise the product path when retrieval misses or a reference is superseded."""
from test_workspace import client, dossier, ready


def test_manual_catalogue_addition_is_not_ranked_or_sent_to_model(client):
    _, sku = dossier(client)
    sku = ready(client, sku)
    url = '/api/v2/skus/' + sku['id'] + '/analyze'
    control = client.post(url, json={'engine':'catalogue'}).json()['analysis']
    codes = [row['code'] for row in control['candidates']]
    manual = next(code for code in ('01012100','85044090') if code not in codes)
    assert client.post(url, json={'manual_codes':['00000000']}).status_code == 422
    res = client.post(url, json={'manual_codes':[manual]})
    assert res.status_code == 200, res.text
    result = res.json()['analysis']
    assert result['manual_candidate_codes'] == [manual]
    assert [row['code'] for row in result['candidates'][:-1]] == codes
    assert result['candidates'][-1]['candidate_source'] == 'operator_catalogue_lookup'
    assert result['candidates'][-1]['rank'] is None
    assert result['input_hash'] == control['input_hash']
    assert result['heading_candidates'] == control['heading_candidates']


def test_official_replacement_excludes_old_reference_by_date(client):
    import api
    library = api.state['precedents']
    row = next(r for r in library.rows if r['source_name'].startswith('5523_TB'))
    assert library.available(row,'2025-02-11')
    assert not library.available(row,'2025-02-12')
    assert not library.available(row,row['notice_date'])
    assert library.lifecycle_version
    results = library.search(row['goods_excerpt'],'2025-02-12')
    assert not any(r['id'] == row['id'] for r in results)
    result = api.state['inference'].guided.search(row['goods_excerpt'],'2025-02-12')
    assert not any((r['unverified_prior_reference'] or {}).get('id') == row['id'] for r in result)


def test_old_catalogue_date_and_incomplete_llm_request_fail_before_inference(client, monkeypatch):
    import api
    _, sku = dossier(client, family='steel')
    sku = ready(client, sku)
    calls = []
    monkeypatch.setattr(api.state['inference'].instruction,'rerank',lambda *args: calls.append(args))
    url = '/api/v2/skus/' + sku['id'] + '/analyze'
    res = client.post(url, json={'engine':'openai','allow_paid_api':True})
    assert res.status_code == 409 and 'thuộc tính bắt buộc' in res.json()['detail']
    assert not calls
    old = client.post('/api/v2/cases',json={'title':'Hồ sơ năm 2022','owner':'Người lập','classification_date':'2022-12-29'}).json()
    old_sku = client.post('/api/v2/cases/'+old['id']+'/skus',json={'sku_code':'OLD','name':'Sản phẩm'}).json()
    old_sku = ready(client,old_sku)
    res = client.post('/api/v2/skus/'+old_sku['id']+'/analyze',json={'engine':'guided'})
    assert res.status_code == 409 and '30/12/2022' in res.json()['detail']


def test_model_data_cutoff_blocks_retrospective_run(client, monkeypatch):
    import api
    from types import SimpleNamespace
    _, sku = dossier(client)
    sku = ready(client, sku)
    inference=api.state['inference']
    monkeypatch.setattr(inference, 'artifact_profile', {})
    calls=[]
    monkeypatch.setattr(inference,'assistant',SimpleNamespace(model_data_through='2026-11-01',classify=lambda *args,**kw:calls.append(args)))
    res=client.post('/api/v2/skus/'+sku['id']+'/analyze',json={'engine':'model'})
    assert res.status_code==409 and 'mốc dữ liệu' in res.json()['detail']
    assert not calls


def test_selected_replay_and_serving_use_same_order(client):
    import api
    from hs_assistant.retrieval_experiment import SELECTED_RECIPE
    engine=api.state['inference'].guided
    query='Máy sấy tóc dùng điện, gia nhiệt điện trở'
    day='2026-11-04'
    channels,_=engine.experiment_channels(query,day)
    assert [r['code'] for r in engine.search(query,day)]==engine.rank(channels,SELECTED_RECIPE)[:30]
