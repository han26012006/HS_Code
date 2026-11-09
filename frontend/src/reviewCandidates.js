export function reviewCandidateState(sku, proposedCode = '') {
  const analysis=sku.analysis;
  const hasCurrentAnalysis=!!analysis && analysis.sku_revision===sku.revision;
  const seen=new Set();
  const candidates=hasCurrentAnalysis?(analysis.candidates||[]).filter(row=>{
    if(!/^\d{8}$/.test(String(row.code))||seen.has(String(row.code)))return false;
    seen.add(String(row.code));return true;
  }):[];
  const alternatives=candidates.filter(row=>String(row.code)!==proposedCode.trim());
  return {hasCurrentAnalysis,candidates,alternatives,requiresAlternative:alternatives.length>0,
    status:!analysis?'missing':!hasCurrentAnalysis?'stale':candidates.length?'ready':'empty'};
}
