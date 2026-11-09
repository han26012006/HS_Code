const {chromium}=require('/Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1600,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:8765');
 await page.getByRole('button',{name:'Tạo hồ sơ mới',exact:true}).click();
 const fixtureFiles=JSON.parse(fs.readFileSync('scratch/document_ai_browser_files.json','utf8'));
 await page.locator('input[type=file]').setInputFiles(fixtureFiles.map(f=>({name:f.name,mimeType:'application/pdf',buffer:fs.readFileSync(f.path)})));
 const draftResponse=page.waitForResponse(r=>r.url().endsWith('/autofill/draft') && r.request().method()==='POST',{timeout:120000});
 await page.getByRole('button',{name:/Tự động xử lý & Tiếp tục/}).click();
 const response=await draftResponse;assert.equal(response.status(),200);const draft=await response.json();
 assert.deepEqual(draft.skus.map(s=>s.sku_code),['DEMO-DRY-1200','DEMO-DRY-1600']);
 assert.equal(draft.extracted_case.declaration_number,'');assert.equal(draft.summary.total_pages,105);
 for(const sku of draft.skus){assert.equal(sku.declared_code,null);const power=sku.sku_code.endsWith('1200')?'1200':'1600';assert(sku.facts.some(f=>f.field==='specifications'&&f.value.includes(power+' W')));assert(sku.facts.every(f=>f.page_number===(power==='1200'?1:2)));}
 await page.locator('#btnCommitCase').waitFor({timeout:120000});
 assert.equal(await page.locator('.sku-code-input').count(),2);
 assert.equal(await page.locator('#caseDeclNum').inputValue(),'');
 assert(await page.locator('body').innerText().then(t=>t.includes('1200 W')&&t.includes('1600 W')));
 await page.screenshot({path:'scratch/document_ai_demo_browser_review.png',fullPage:true});
 const commitResponse=page.waitForResponse(r=>r.url().includes('/autofill/draft/')&&r.url().endsWith('/commit'),{timeout:120000});
 await page.locator('#btnCommitCase').click();const commit=await commitResponse;const saved=await commit.json();assert.equal(commit.status(),200,JSON.stringify(saved));
 assert.equal(saved.skus.length,2);assert.equal(saved.declaration_number,'');
 for(const sku of saved.skus){const res=await page.request.get('http://127.0.0.1:8765/api/v2/skus/'+sku.id);const loaded=await res.json();assert(loaded.facts.every(f=>f.document_id && f.source_document_id===f.document_id));assert(loaded.facts.every(f=>f.status==='unverified'));}
 await page.waitForURL('**/#case/'+saved.id,{timeout:10000});await page.waitForTimeout(800);await page.reload();await page.waitForTimeout(1000);
 await page.screenshot({path:'scratch/document_ai_demo_browser_saved.png',fullPage:true});
 assert.equal(errors.length,0,errors.join('\n'));
 fs.writeFileSync('scratch/document_ai_browser_e2e_result.json',JSON.stringify({status:'passed',inputs:fixtureFiles.map(f=>f.name),total_pages:draft.summary.total_pages,sku_codes:draft.skus.map(s=>s.sku_code),case_id:saved.id,workflow:'browser upload → review → commit → API load → browser reload',page_errors:errors},null,2));
 await browser.close();console.log('PASS: original two PDFs, 105 pages, two SKUs, correct power/page, blank HS/declaration, commit/reload');
})().catch(e=>{console.error(e);process.exit(1)});
