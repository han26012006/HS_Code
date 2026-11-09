"""Optional provider boundary. Disabled/offline unless explicitly authorized per request.

No provider is installed or called by the default pipeline. Suggestions are
unverified and must resolve to an existing page/block/quote and allowed field.
"""
from dataclasses import dataclass
import math
from typing import Protocol
from .document_layout import norm
from .document_schema import allowed


class ExtractionProvider(Protocol):
    def estimate_cost(self,pages:list[dict])->float: ...
    def suggest(self,pages:list[dict],max_output_tokens:int)->list[dict]: ...


@dataclass(frozen=True)
class AssistancePolicy:
    enabled:bool=False
    allow_external_data:bool=False
    max_cost:float=0.0
    max_pages:int=4
    max_output_tokens:int=1000


class AssistedExtraction:
    def __init__(self,provider:ExtractionProvider|None=None,policy:AssistancePolicy|None=None):
        self.provider=provider;self.policy=policy or AssistancePolicy();self.spent=0.0

    def extract(self,pages,document_kind,*,authorized=False):
        policy=self.policy
        if not policy.enabled:return {'status':'disabled','suggestions':[]}
        if not authorized or not policy.allow_external_data:
            return {'status':'authorization_required','suggestions':[]}
        if self.provider is None:return {'status':'provider_unavailable','suggestions':[]}
        if len(pages)>policy.max_pages:return {'status':'page_budget_exceeded','suggestions':[]}
        estimate=self.provider.estimate_cost(pages)
        if not math.isfinite(estimate) or estimate<0 or estimate>policy.max_cost-self.spent:return {'status':'cost_budget_exceeded','suggestions':[]}
        # Reserve the quoted maximum before invocation, including provider failures.
        self.spent+=estimate
        accepted=[];rejected=[]
        for proposal in self.provider.suggest(pages,policy.max_output_tokens):
            page=next((p for p in pages if p.get('document_id')==proposal.get('source_document_id') and p.get('number')==proposal.get('source_page')),None)
            quote=proposal.get('source_quote','');value=str(proposal.get('value',''))
            block_ids=proposal.get('source_block_ids',[])
            blocks=[b for b in (page or {}).get('layout',{}).get('blocks',[]) if b['id'] in block_ids]
            valid=page is not None and bool(quote) and bool(value) and allowed(document_kind,proposal.get('field_name')) and norm(quote) in norm(page.get('text','')) and norm(value) in norm(quote) and bool(blocks) and norm(quote) in norm('\n'.join(b['text'] for b in blocks))
            if valid:
                accepted.append({**proposal,'status':'unverified','extraction_status':'needs_review','source_kind':'ai_suggestion','extraction_method':'assisted_provider','source_valid':True})
            else:rejected.append({'reason':'invalid_source_or_field','field_name':proposal.get('field_name')})
        # These remain suggestions; product/row ownership must be reviewed by a human.
        return {'status':'review_required','suggestions':accepted,'rejected':rejected,'reserved_cost':estimate}
