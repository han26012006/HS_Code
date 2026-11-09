from copy import deepcopy
from decimal import Decimal
import pytest
from hs_assistant.document_reconciliation import comparable, fact_value_key, check
from hs_assistant.extractor import AutoFillDraftManager
from hs_assistant.documents import DocumentService
from hs_assistant.workspace import Workspace


def test_formatted_numbers_compare_without_changing_source_or_units():
    assert comparable('2,000','BAGS')==comparable('2000.00','BAGS')
    assert comparable('50,200.00','KGM')==comparable('50,200','KGM')
    assert comparable('1,5','kg')!=comparable('15','kg')
    assert comparable('1.000','kg')!=comparable('1,000','kg')
    assert comparable('2000','BAGS')!=comparable('2000','PCS')
    assert fact_value_key({'field':'declared_code','value':'01012100'})=='01012100'
    a={'field':'quantity','value':'2000.00','unit':'BAGS'}
    b={'field':'quantity','value':'2,000','unit':'BAGS'}
    assert check('quantity','quantity',[a],[b])['status']=='match'
    assert a['value']=='2000.00' and b['value']=='2,000'


@pytest.mark.parametrize('packing_quantity,conflict',[('2,000',False),('2,100',True)])
def test_confirmed_merge_retains_sources_and_only_flags_real_differences(tmp_path,packing_quantity,conflict):
    manager=AutoFillDraftManager(Workspace(tmp_path/'workspace.db'))
    svc=DocumentService(manager.db,tmp_path/'uploads')
    try:
        invoice='COMMERCIAL INVOICE\nInvoice No: A-20\nProduct name: Mechanical coupling\nQuantity: 2000.00 BAGS\nGross weight: 50200.00 KGM\n'
        packing=f'PACKING LIST\nProduct name: Mechanical coupling\nQuantity: {packing_quantity} BAGS\nGross weight: 50,200 KGM\n'
        draft=manager.create_draft([('invoice.txt',invoice.encode()),('packing.txt',packing.encode())])
        assert len(draft['skus'])==2
        a,b=draft['skus']
        original=deepcopy(a['facts']+b['facts'])
        draft=manager.update_draft(draft['draft_id'],{'match_confirmations':[{'target_sku_id':a['id'],'source_sku_id':b['id'],'confirmed':True}]})
        assert len(draft['skus'])==1
        facts=draft['skus'][0]['facts']
        assert [(f['document_id'],f['quote'],f['value'])for f in facts]==[(f['document_id'],f['quote'],f['value'])for f in original]
        quantities=[f for f in facts if f['field']=='quantity']
        assert len(quantities)==2
        assert all((f['status']=='conflict')==conflict for f in quantities)
        weights=[f for f in facts if f['field']=='gross_weight']
        assert len(weights)==2 and all(f['status']!='conflict' for f in weights)
        saved=manager.commit_draft(draft['draft_id'],{},svc)
        loaded=manager.db.get_sku(saved['skus'][0]['id'])
        assert len({f['document_id']for f in loaded['facts']})==2
        assert len(loaded['facts'])==len(original)
    finally:
        svc.close()
