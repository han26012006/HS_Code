import hashlib
import io
import json
import zipfile
from test_workspace import approve, client, dossier, evidence, ready


def test_guided_from_facts_to_frozen_decision(client):
    case, sku = dossier(client)
    url = '/api/v2/skus/' + sku['id']
    assert client.post(url+'/analyze', json={'engine':'guided'}).status_code == 409
    sku = ready(client, sku)
    response = client.post(url+'/analyze', json={'engine':'guided'})
    assert response.status_code == 200, response.text
    sku = response.json()
    analysis = sku['analysis']
    assert analysis['engine'] == 'guided' and analysis['human_review_required']
    assert not analysis['auto_accept'] and analysis['instruction_result'] is None
    assert {rule['pdf_page'] for rule in analysis['classification_guidance']} == {50,74}
    candidates = analysis['candidates']
    assert 0 < len(candidates) <= 30 and len({x['code'] for x in candidates}) == len(candidates)
    assert all(not x['score_is_probability'] and
               (not x['unverified_prior_reference'] or
                x['unverified_prior_reference']['notice_date'] < case['classification_date']) for x in candidates)
    assert approve(client, sku).status_code == 422
    sku = evidence(client, sku)
    sku = client.post(url+'/analyze', json={'engine':'guided'}).json()
    result = approve(client, sku)
    assert result.status_code == 200, result.text
    frozen = client.get('/api/v2/decisions/'+result.json()['decision']['id']+'/snapshot').json()
    assert frozen['integrity_matches']
    assert frozen['snapshot']['sku']['analysis']['engine'] == 'guided'
    exported = client.get('/api/v2/cases/'+case['id']+'/export/zip')
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        manifest = json.loads(z.read('MANIFEST.json'))
        assert all(hashlib.sha256(z.read(name)).hexdigest() == h for name,h in manifest['file_hashes'].items())


def test_gri_signed_bulletin_bytes_match_registry(client):
    data = client.get('/api/v2/knowledge', params={'scope':'GRI'}).json()
    assert sorted(n['pdf_page'] for n in data['notes']) == [50,53,59,69,70,74]
    source = next(r for r in data['legal_sources']['rules'] if r['id'] == '31/2022/TT-BTC')
    document = client.get('/api/v2/legal-document/31_2022_TT-BTC')
    assert document.status_code == 200
    assert hashlib.sha256(document.content).hexdigest() == source['sha256']
