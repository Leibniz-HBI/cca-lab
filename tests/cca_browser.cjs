const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=500)errors.push(r.status()+' '+r.url())});
 const post=async(path,data)=>{const r=await page.request.post((process.env.TEXTLAB_TEST_URL||'http://127.0.0.1:8099')+'/api'+path,{data:typeof data==='string'?Buffer.from(data):data});if(!r.ok())throw Error(await r.text());return r.json()};
 await page.goto((process.env.TEXTLAB_TEST_URL||'http://127.0.0.1:8099'));await page.waitForFunction(()=>document.querySelector('#title').textContent==='Define tasks');
 if(await page.locator('nav[aria-label="Research workflow"] a').count()!==5)throw Error('Workflow must have 5 steps');
 if(await page.locator('.config-section a[href="#profiles"]').count()!==1)throw Error('Missing separate config');

 const doc={"$schema":"https://cca-schema.org/schema/0.1/schema.json",id:"sentiment",version:"1.0.0",title:"CCA sentiment",description:"Sentiment of a sentence",authors:["Research team"],language:"en",task:{instructions:"Apply the criteria.",unit_of_analysis:"sentence",classification_mode:"single_label",context:"Resolve speaker attribution.",categories:[{id:"101",label:"Positive",definition:"Favorable tone",inclusion_criteria:["Explicit praise"],exclusion_criteria:["Irony"],coding_notes:"Identify the speaker.",aliases:["pos"]},{id:"102",label:"Negative",definition:"Unfavorable tone"}]},examples:[{text:"Wonderful",labels:["101"],context:"A successful outcome",explanation:"Explicit approval"}]};
 // Actual picker, with two forced background refreshes while it is open.
 const pickerPromise=page.waitForEvent('filechooser');
 await page.locator('[data-action=cca-import]').click();
 const picker=await pickerPromise;
 await page.evaluate(async()=>{await refresh();await refresh();});
 if(!await picker.element().evaluate(el=>el.isConnected))throw Error('Picker detached during refresh');
 await picker.setFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{}')});
 await page.waitForFunction(()=>document.querySelector('#cca-import-status').textContent.includes('CCA import:'));
 if((await page.request.get((process.env.TEXTLAB_TEST_URL||'http://127.0.0.1:8099')+'/api/tasks').then(r=>r.json())).length)throw Error('Invalid import created task');
 await page.evaluate(async()=>{await refresh();});
 if(!(await page.locator('#cca-import-status').innerText()).includes('CCA import:'))throw Error('Error disappeared on refresh');
 const second=page.waitForEvent('filechooser');await page.locator('[data-action=cca-import]').click();
 const validPicker=await second;await page.evaluate(async()=>{await refresh();await refresh();});
 await validPicker.setFiles({name:'sentiment.cca.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(doc))});
 await page.waitForFunction(()=>document.querySelector('#editor').open&&document.querySelector('[name=name]').value==='CCA sentiment');
 await page.getByText('CCA codebook context and provenance',{exact:true}).click();
 if(await page.locator('[name=unit_of_analysis]').inputValue()!=='sentence')throw Error('Missing unit');
 await page.locator('[name=name]').fill('Edited CCA sentiment');
 await page.getByText('Category name, criteria and notes',{exact:true}).first().click();
 const extra=JSON.parse(await page.locator('[name=cca_category]').first().inputValue());extra.inclusion_criteria.push('Positive evaluation');
 await page.locator('[name=cca_category]').first().fill(JSON.stringify(extra));
 await page.locator('#editor-form button[type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#editor').open);
 const downloadPromise=page.waitForEvent('download');await page.locator('[data-action=cca-export]').click();const download=await downloadPromise;
 const path=await download.path();const exported=JSON.parse(fs.readFileSync(path,'utf8'));
 if(exported.title!=='Edited CCA sentiment'||exported.authors[0]!=='Research team'||exported.task.categories[0].id!=='101'||exported.task.categories[0].label!=='Positive'||exported.task.categories[0].inclusion_criteria.length!==2||exported.examples[0].context!==doc.examples[0].context)throw Error('Roundtrip lost metadata/edits');
 await page.locator('[data-action=edit-task]').click();await page.getByText('Multi-label examples and output schema',{exact:true}).click();await page.locator('[data-action=prompt-preview]').click();
 await page.waitForFunction(()=>document.querySelector('#prompt-preview').textContent.includes('Positive evaluation'));
 if(!(await page.locator('#prompt-preview').innerText()).includes('Resolve speaker attribution'))throw Error('Missing prompt context');
 await page.locator('[data-action=close]').first().click();

 if(errors.length)throw Error(errors.join('\n'));
 console.log('PASS: real file picker survives refresh; invalid file shows persistent error; CCA file import; editable criteria/context; metadata and category IDs preserved after save/export; prompt includes criteria and context; download works; no JS/HTTP5xx errors.');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
