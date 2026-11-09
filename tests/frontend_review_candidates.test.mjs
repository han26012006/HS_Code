import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewCandidateState} from '../frontend/src/reviewCandidates.js';
const rows=[{code:'25010020',description:'Muối mỏ chưa chế biến'},{code:'25010010',description:'Muối thực phẩm'}];
test('evidence changes without a current analysis give an explicit missing state',()=>{
  const state=reviewCandidateState({revision:20,analysis:null},'25010020');
  assert.equal(state.status,'missing');assert.equal(state.hasCurrentAnalysis,false);
  assert.deepEqual(state.alternatives,[]);assert.equal(state.requiresAlternative,false);
});
test('an old analysis cannot populate a selectable stale list',()=>{
  const state=reviewCandidateState({revision:20,analysis:{sku_revision:19,candidates:rows}},'25010020');
  assert.equal(state.status,'stale');assert.deepEqual(state.candidates,[]);
});
test('refresh provides alternatives and excludes the proposed approval code',()=>{
  const sku={revision:20,analysis:{sku_revision:20,candidates:rows}};
  let state=reviewCandidateState(sku,'25010020');
  assert.equal(state.hasCurrentAnalysis,true);assert.equal(state.requiresAlternative,true);
  assert.deepEqual(state.alternatives.map(x=>x.code),['25010010']);
  state=reviewCandidateState(sku,'25010010');
  assert.deepEqual(state.alternatives.map(x=>x.code),['25010020']);
});
test('duplicate or malformed candidates cannot create invalid options',()=>{
  const state=reviewCandidateState({revision:1,analysis:{sku_revision:1,candidates:[...rows,rows[0],{code:'250100'},{code:null}]}});
  assert.deepEqual(state.candidates,rows);
});
test('a single candidate equal to the proposal does not require a nonexistent alternative',()=>{
  const state=reviewCandidateState({revision:1,analysis:{sku_revision:1,candidates:[rows[0]]}},'25010020');
  assert.equal(state.requiresAlternative,false);assert.deepEqual(state.alternatives,[]);
});
test('an analyzed empty list is distinct from a missing analysis',()=>{
  const state=reviewCandidateState({revision:1,analysis:{sku_revision:1,candidates:[]}});
  assert.equal(state.status,'empty');assert.equal(state.hasCurrentAnalysis,true);
});
