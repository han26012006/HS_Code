import test from 'node:test';
import assert from 'node:assert/strict';
import {groupFacts, factValueKey, missingFields, editFactGroup} from '../frontend/public/assets/fact-review.js';

const fact = (field, value, document_id, unit) => ({field,value,document_id,unit,quote:`source ${document_id}: ${value}`,status:'unverified'});
test('equivalent source values have one editor with both original sources', () => {
  const facts = [fact('name','Himalayan Pink Salt','invoice'),fact('quantity','2000.00','invoice','BAGS'),fact('gross_weight','50,200.00','invoice','KGM'),fact('origin','India','invoice'),fact('name','Himalayan Pink Salt','packing'),fact('quantity','2,000','packing','BAGS'),fact('gross_weight','50,200','packing','KGM'),fact('origin','India','packing')];
  const snapshot = JSON.stringify(facts);
  const groups = groupFacts(facts);
  assert.equal(groups.length,4);
  for (const group of groups) assert.equal(group.facts.length,2);
  assert.equal(JSON.stringify(facts),snapshot);
  assert.deepEqual(groups.find(g=>g.field==='quantity').indices,[1,5]);
});
test('different values, units and identifiers stay distinct; numbers keep exact precision', () => {
  assert.equal(groupFacts([fact('quantity','2000','a','BAGS'),fact('quantity','2100','b','BAGS')]).length,2);
  assert.equal(groupFacts([fact('quantity','2000','a','BAGS'),fact('quantity','2000','b','PCS')]).length,2);
  assert.notEqual(factValueKey(fact('declared_code','01012100')),factValueKey(fact('declared_code','1012100')));
  assert.notEqual(factValueKey(fact('quantity','1,5')),factValueKey(fact('quantity','15')));
  assert.notEqual(factValueKey(fact('quantity','1.000')),factValueKey(fact('quantity','1,000')));
  assert.notEqual(factValueKey(fact('amount','9007199254740993')),factValueKey(fact('amount','9007199254740992')));
  assert.equal(factValueKey(fact('net_weight','1000','a','g')),factValueKey(fact('net_weight','1','b','kg')));
});
test('editing a grouped field updates every represented fact without losing source quotes', () => {
  const sku={facts:[fact('quantity','2000.00','a','BAGS'),fact('quantity','2,000','b','BAGS'),fact('origin','India','a')]};
  const originalQuotes=sku.facts.map(f=>f.quote);
  editFactGroup(sku,groupFacts(sku.facts)[0].indices,'2100');
  assert.deepEqual(sku.facts.map(f=>f.value),['2100','2100','India']);
  assert.deepEqual(sku.facts.map(f=>f.quote),originalQuotes);
  assert.ok(sku.facts.slice(0,2).every(f=>f.source_kind==='user_input' && f.status==='unverified' && !f.source_valid));
});
test('missing fields follow the selected family and present facts', () => {
  const sku={product_family:'general',facts:[fact('name','Salt','a')]};
  assert.deepEqual(missingFields(sku),['function']);
  sku.product_family='food';
  assert.deepEqual(missingFields(sku),['function','material','manufacturing']);
  sku.product_family='machine';
  assert.deepEqual(missingFields(sku),['function','construction','specifications']);
});

test('actual review renderer has one editor per value, one name input and all source links', async () => {
  const {readFileSync}=await import('node:fs');
  const vm=await import('node:vm');
  const helpers=await import('../frontend/public/assets/fact-review.js');
  let overlay;
  const document={readyState:'loading',addEventListener(){},createElement(){return {style:{},innerHTML:'',querySelectorAll(){return []},querySelector(){return null}}},body:{appendChild(el){overlay=el}}};
  const code=readFileSync(new URL('../frontend/public/assets/docfirst.js',import.meta.url),'utf8')
    .replace(/await import\('\/assets\/fact-review\.js[^']*'\)/,'globalThis.helpers')
    .replace('function openReviewWorkspaceModal(draft) {','globalThis.openReview = openReviewWorkspaceModal; function openReviewWorkspaceModal(draft) {');
  const context={document,helpers,console:{log(){}},setInterval(){},setTimeout(){}};
  vm.runInNewContext(code,context);
  const facts=[fact('name','Salt','invoice'),fact('quantity','2000.00','invoice','BAGS'),fact('origin','India','invoice'),fact('name','Salt','packing'),fact('quantity','2,000','packing','BAGS'),fact('origin','India','packing')];
  context.openReview({documents:[],skus:[{id:'salt',sku_code:'salt',name:'Salt',product_family:'general',facts,missing_fields:['function','construction','specifications']}]});
  const html=overlay.innerHTML;
  assert.equal((html.match(/class="sku-name-input"/g)||[]).length,1);
  assert.equal((html.match(/data-field="quantity"/g)||[]).length,1);
  assert.equal((html.match(/data-field="origin"/g)||[]).length,1);
  assert.equal((html.match(/data-field="function"/g)||[]).length,1);
  assert.equal((html.match(/data-field="name"/g)||[]).length,0);
  assert.ok(html.includes('Tên trên chứng từ · 2 nguồn'));
  assert.ok(html.includes('Đối chiếu · 2 nguồn'));
  assert.ok(html.includes('invoice')&&html.includes('packing'));
  assert.ok(!html.includes('data-field="construction"'));
  assert.ok(!html.includes('data-field="specifications"'));
  assert.ok(!html.includes('Cần bổ sung: Công dụng / Chức năng sử dụng, Cấu tạo'));
});

test('saved facts use conservative group status and never hide an unchecked source', async () => {
  const {factGroupStatus}=await import('../frontend/src/factReview.js');
  const a={...fact('quantity','2000.00','a','BAGS'),id:'a',status:'verified'};
  const b={...fact('quantity','2,000','b','BAGS'),id:'b',status:'unverified'};
  assert.equal(factGroupStatus(groupFacts([a,b])[0]),'unverified');
  b.status='verified';assert.equal(factGroupStatus(groupFacts([a,b])[0]),'verified');
  b.document_scope_mismatch=true;assert.equal(factGroupStatus(groupFacts([a,b])[0]),'unverified');
  b.status='conflict';assert.equal(factGroupStatus(groupFacts([a,b])[0]),'conflict');
});
test('one group action handles all distinct source IDs and reloads authoritative state', async () => {
  const {performFactGroupAction}=await import('../frontend/src/factReview.js');
  const calls=[];
  const result=await performFactGroupAction([{id:'invoice'},{id:'packing'},{id:'invoice'}],async id=>{calls.push(id);return id;},async()=>calls.push('reload'));
  assert.deepEqual(calls,['invoice','packing','reload']);assert.equal(result,'packing');
});
test('failed group action reloads partial state without reporting full success', async () => {
  const {performFactGroupAction}=await import('../frontend/src/factReview.js');
  const calls=[];
  await assert.rejects(performFactGroupAction([{id:'invoice'},{id:'packing'},{id:'third'}],async id=>{calls.push(id);if(id==='packing')throw Error('source rejected');},async()=>calls.push('reload')),/source rejected/);
  assert.deepEqual(calls,['invoice','packing','reload']);
});
test('bundled and Document-First views share the same grouping rules', async () => {
  const {readFileSync}=await import('node:fs');
  assert.equal(readFileSync(new URL('../frontend/src/factReview.js',import.meta.url),'utf8'),readFileSync(new URL('../frontend/public/assets/fact-review.js',import.meta.url),'utf8'));
});
