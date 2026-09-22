'use strict';
// Keep the picker connected while background refresh replaces #view.
const ccaFile=document.createElement('input');
ccaFile.id='cca-file';ccaFile.type='file';ccaFile.accept='.json,application/json';
ccaFile.style.display='none';document.body.appendChild(ccaFile);
let ccaImportBusy=false,ccaImportMessage='';
function ccaStatus(message){ccaImportMessage=message;const el=$('#cca-import-status');if(el)el.textContent=message;}
function newCodebookId(){
 if(crypto.randomUUID)return 'urn:uuid:'+crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const h=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
 return 'urn:uuid:'+h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
}
const CCA_SCHEMA='https://cca-schema.org/schema/0.1/schema.json';
function ccaField(label,name,value='',type='text',required=false){
 return '<label>'+esc(label)+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+(required?'required':'')+'></label>';
}
function ccaArea(label,name,value='',required=false){
 return '<label>'+esc(label)+'<textarea name="'+name+'" '+(required?'required':'')+'>'+esc(value)+'</textarea></label>';
}
function criteriaText(values){return values.map(v=>'- '+v.replaceAll('\n','\n  ')).join('\n');}
function parseCriteria(text){
 if(!text.trim())return [];
 if(!text.startsWith('- '))return [text];
 const values=[];
 for(const line of text.split('\n')){
  if(line.startsWith('- '))values.push(line.slice(2));
  else if(line.startsWith('  ')&&values.length)values[values.length-1]+='\n'+line.slice(2);
  else throw Error('Criteria: start each item with "- " and indent continuation lines by two spaces.');
 }
 return values;
}
function criteriaField(key,values,label){
 return '<div class="cca-criteria" data-key="'+key+'">'+ccaArea(label,key,criteriaText(values))+
 '<small>Start each item with “- ”; indent continuation lines by two spaces. Plain text is one criterion.</small></div>';
}
async function previewTask(){
 const task=readTask(),query={model:'preview',structured_output:$('[name=preview_mode]').value},provider=$('[name=preview_provider]').value;
 const preview=await api('/tasks/preview-request',{method:'POST',body:JSON.stringify({task,query,provider})});
 const box=$('#prompt-preview');box.hidden=false;box.replaceChildren();
 const note=document.createElement('p');note.className='small';note.textContent=preview.note+' Protocol: '+preview.prompt_protocol;box.append(note);
 for(const message of preview.request.messages){
  const panel=document.createElement('section'),heading=document.createElement('h4'),content=document.createElement('pre');
  heading.textContent=message.role.toUpperCase();content.textContent=message.content;panel.append(heading,content);box.append(panel);
 }
 const details=document.createElement('details'),summary=document.createElement('summary'),raw=document.createElement('pre');
 summary.textContent='Raw request JSON · '+preview.path;raw.textContent=JSON.stringify(preview.request,null,2);
 details.append(summary,raw);box.append(details);
}
function listItems(key,values=[],label=key){
 return '<div class="cca-list" data-key="'+key+'"><div class="section-title"><strong>'+esc(label)+'</strong><button type="button" data-action="cca-add-item">+ Add</button></div><div class="cca-items">'+values.map(v=>listItem(v)).join('')+'</div></div>';
}
function listItem(value=''){return '<div class="cca-list-item"><textarea aria-label="List entry" required>'+esc(value)+'</textarea><button type="button" data-action="cca-remove-item" aria-label="Remove list entry">Remove</button></div>';}
function referenceHTML(r={}){
 return '<div class="cca-reference"><div class="category-head"><strong>Reference</strong><button type="button" data-action="cca-remove-reference">Remove</button></div>'+ccaArea('Citation','citation',r.citation||'',true)+ccaField('DOI (optional)','doi',r.doi||'')+'</div>';
}
function exampleHTML(ex={}){
 return '<div class="cca-example"><div class="category-head"><strong>Coding example</strong><button type="button" data-action="cca-remove-example">Remove</button></div>'+ccaArea('Example text','example_text',ex.text||'',true)+'<label>Category IDs<select name="example_labels" multiple required data-selected="'+esc(JSON.stringify(ex.labels||[]))+'"></select><small>Select all applicable categories. Use Ctrl/Cmd for multiple labels.</small></label>'+ccaArea('Context (optional)','example_context',ex.context||'')+ccaArea('Explanation (optional)','explanation',ex.explanation||'')+'</div>';
}
categoryHTML=function(c={}){
 return '<div class="category cca-category"><div class="category-head"><strong>Category</strong><button type="button" data-action="remove-category">Remove</button></div><div class="grid">'+ccaField('Category ID','cat-id',c.id||'','text',true)+ccaField('Label / display name','cat-label',c.label||'','text',true)+'</div>'+ccaArea('Definition','cat-definition',c.definition||'',true)+'<details><summary>Criteria, aliases and coding notes</summary>'+criteriaField('inclusion_criteria',c.inclusion_criteria||[],'Inclusion criteria')+criteriaField('exclusion_criteria',c.exclusion_criteria||[],'Exclusion criteria')+listItems('aliases',c.aliases||[],'Aliases')+ccaArea('Coding notes','coding_notes',c.coding_notes||'')+'</details></div>';
};
taskEditor=function(id,seedSpec=null){
 const existing=state.tasks.find(t=>t.id===id),t=existing?.spec||seedSpec;
 const c=t?.codebook||{$schema:CCA_SCHEMA,id:newCodebookId(),version:'0.1.0',title:'',description:'',task:{instructions:'',unit_of_analysis:'document',classification_mode:'single_label',categories:[{id:'',label:'',definition:''}]}};
 const task=c.task;
 openEditor(existing?'Edit task':'Create task',
 '<section class="cca-section"><h3>Codebook identity</h3>'+ccaField('Title','title',c.title,'text',true)+ccaArea('Description','description',c.description,true)+'<div class="grid">'+ccaField('Stable codebook ID','codebook_id',c.id,'text',true)+ccaField('Codebook version','codebook_version',c.version,'text',true)+'</div><p class="small">CCA Schema 0.1 · Codebook version is independent of the automatic CCA-Lab revision.</p><details><summary>Language, provenance and references</summary>'+ccaField('Language (optional, e.g. en or de)','language',c.language||'')+listItems('authors',c.authors||[],'Authors')+listItems('maintainers',c.maintainers||[],'Maintainers')+'<div class="grid">'+ccaField('Created date','created_at',c.created_at||'','date')+ccaField('Modified date','modified_at',c.modified_at||'','date')+'</div><div class="section-title"><strong>References</strong><button type="button" data-action="cca-add-reference">+ Reference</button></div><div id="cca-references">'+(c.references||[]).map(referenceHTML).join('')+'</div></details></section>'+
 '<section class="cca-section"><h3>Coding instructions</h3>'+ccaArea('General coding instructions','instructions',task.instructions,true)+'<div class="grid">'+ccaField('Unit of analysis','unit_of_analysis',task.unit_of_analysis,'text',true)+select('Classification mode','classification_mode',option('single_label','Single label',task.classification_mode)+option('multi_label','Multi-label',task.classification_mode))+'</div>'+ccaArea('Permitted additional context (optional)','context',task.context||'')+'</section>'+
 '<section class="cca-section"><div class="section-title"><h3>Categories</h3><button type="button" data-action="add-category">+ Category</button></div><p class="small">Predictions use category IDs. Define an explicit category for “none applicable” if your codebook requires it.</p><div id="categories">'+task.categories.map(categoryHTML).join('')+'</div></section>'+
 '<section class="cca-section"><div class="section-title"><h3>Examples</h3><button type="button" data-action="cca-add-example">+ Example</button></div><div id="cca-examples">'+(c.examples||[]).map(exampleHTML).join('')+'</div></section>'+
 '<details class="cca-section"><summary>Prompt preview</summary><div class="grid"><label>Preview provider<select name="preview_provider"><option value="openai">OpenAI-compatible</option><option value="ollama">Ollama</option></select></label><label>Output format<select name="preview_mode"><option value="json_schema">Native JSON Schema</option><option value="json_object">JSON object</option><option value="none">Prompt only</option></select></label></div><button type="button" data-action="prompt-preview">Generate preview</button><div id="prompt-preview" hidden></div></details>','task',id);
 edit.revision=existing?.revision;edit.originalCodebook=structuredClone(c);
 syncCategoryChoices();indexCCAFields();
 document.querySelectorAll('.cca-criteria textarea').forEach(el=>{el.dataset.original=JSON.stringify(task.categories[Array.from(document.querySelectorAll('.cca-category')).indexOf(el.closest('.cca-category'))][el.name]||[]);});
 $('#editor').scrollTop=0;$('[name=title]').focus({preventScroll:true});
};
function syncCategoryChoices(){
 if(edit?.kind!=='task')return;
 const categories=[...document.querySelectorAll('.cca-category')].map(el=>({id:el.querySelector('[name=cat-id]').value,label:el.querySelector('[name=cat-label]').value})).filter(c=>c.id);
 document.querySelectorAll('[name=example_labels]').forEach(el=>{
  const selected=el.dataset.selected!==undefined?JSON.parse(el.dataset.selected):[...el.selectedOptions].map(o=>o.value);delete el.dataset.selected;
  const ids=new Set(categories.map(c=>c.id));
  el.innerHTML=categories.map(c=>'<option value="'+esc(c.id)+'" '+(selected.includes(c.id)?'selected':'')+'>'+esc(c.id+' · '+c.label)+'</option>').join('')+selected.filter(id=>!ids.has(id)).map(id=>'<option selected value="'+esc(id)+'">'+esc(id+' (missing category)')+'</option>').join('');
  el.size=Math.max(2,Math.min(6,el.options.length));
 });

}
function indexCCAFields(){
 const set=(el,path)=>{if(el)el.dataset.ccaPath=path;};
 const fields={title:'/title',description:'/description',codebook_id:'/id',codebook_version:'/version',language:'/language',created_at:'/created_at',modified_at:'/modified_at',instructions:'/task/instructions',unit_of_analysis:'/task/unit_of_analysis',classification_mode:'/task/classification_mode',context:'/task/context'};
 Object.entries(fields).forEach(([name,path])=>set($('[name='+name+']'),path));
 set($('#categories'),'/task/categories');
 document.querySelectorAll('.cca-category').forEach((el,i)=>{
  const base='/task/categories/'+i;
  for(const [name,key] of [['cat-id','id'],['cat-label','label'],['cat-definition','definition'],['coding_notes','coding_notes']])set(el.querySelector('[name='+name+']'),base+'/'+key);
  for(const key of ['inclusion_criteria','exclusion_criteria'])set(el.querySelector('[name='+key+']'),base+'/'+key);
  el.querySelectorAll('.cca-list').forEach(list=>{set(list,base+'/'+list.dataset.key);list.querySelectorAll('textarea').forEach((input,j)=>set(input,base+'/'+list.dataset.key+'/'+j));});
 });
 for(const key of ['authors','maintainers']){const list=$('.cca-list[data-key='+key+']');set(list,'/'+key);list.querySelectorAll('textarea').forEach((el,i)=>set(el,'/'+key+'/'+i));}
 document.querySelectorAll('.cca-example').forEach((el,i)=>{for(const [name,key] of [['example_text','text'],['example_labels','labels'],['example_context','context'],['explanation','explanation']])set(el.querySelector('[name='+name+']'),'/examples/'+i+'/'+key);});
 document.querySelectorAll('.cca-reference').forEach((el,i)=>{for(const key of ['citation','doi'])set(el.querySelector('[name='+key+']'),'/references/'+i+'/'+key);});
}
function readList(el,key){
 const field=el.querySelector('.cca-criteria textarea[name='+key+']');if(field){if(field.dataset.original&&field.value===field.defaultValue)return JSON.parse(field.dataset.original);return parseCriteria(field.value);}
 return [...el.querySelectorAll('.cca-list[data-key='+key+'] textarea')].map(e=>e.value);}
readTask=function(){
 indexCCAFields();const form=$('#editor-form'),value=name=>form.querySelector('[name='+name+']').value;
 const original=edit.originalCodebook;
 const c={$schema:original.$schema,id:value('codebook_id'),version:value('codebook_version'),title:value('title'),description:value('description'),
 task:{instructions:value('instructions'),unit_of_analysis:value('unit_of_analysis'),classification_mode:value('classification_mode'),categories:[]}};
 for(const k of ['language','created_at','modified_at'])if(value(k))c[k]=value(k);
 for(const k of ['authors','maintainers']){const values=readList(form,k);if(values.length)c[k]=values;}
 if(value('context'))c.task.context=value('context');
 c.task.categories=[...document.querySelectorAll('.cca-category')].map(el=>{
  const v=name=>el.querySelector('[name='+name+']').value,out={id:v('cat-id'),label:v('cat-label'),definition:v('cat-definition')};
  for(const key of ['inclusion_criteria','exclusion_criteria','aliases']){const values=readList(el,key);if(values.length)out[key]=values;}
  if(v('coding_notes'))out.coding_notes=v('coding_notes');return out;
 });
 const examples=[...document.querySelectorAll('.cca-example')].map(el=>{
  const v=name=>el.querySelector('[name='+name+']').value,out={text:v('example_text'),labels:[...el.querySelector('[name=example_labels]').selectedOptions].map(o=>o.value)};
  if(v('example_context'))out.context=v('example_context');if(v('explanation'))out.explanation=v('explanation');return out;
 });
 if(examples.length||'examples' in original)c.examples=examples;
 const references=[...document.querySelectorAll('.cca-reference')].map(el=>{const out={citation:el.querySelector('[name=citation]').value},doi=el.querySelector('[name=doi]').value;if(doi)out.doi=doi;return out;});
 if(references.length||'references' in original)c.references=references;
 return {codebook:c};
};
function showCCAErrors(error){
 document.querySelectorAll('.cca-field-error').forEach(el=>el.remove());
 document.querySelectorAll('[aria-invalid]').forEach(el=>el.removeAttribute('aria-invalid'));
 indexCCAFields();
 const issues=(error.details||[]).flatMap(e=>e.ctx?.issues||[{path:'/'+e.loc.filter(x=>!['body','codebook'].includes(x)).join('/'),message:e.msg}]);
 let first;
 for(const issue of issues){
  let path=issue.path,el;
  while(path){el=[...document.querySelectorAll('[data-cca-path]')].find(e=>e.dataset.ccaPath===path);if(el)break;path=path.slice(0,path.lastIndexOf('/'));}
  if(!el)continue;
  el.setAttribute('aria-invalid','true');for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
  const message=document.createElement('small');message.className='cca-field-error error';message.textContent=issue.message;
  el.insertAdjacentElement('afterend',message);first ||=el;
 }
 if(first){first.scrollIntoView({block:'center'});first.focus();}
}
document.addEventListener('click',e=>{
 const button=e.target.closest('[data-action]');if(!button||edit?.kind!=='task'||!$('#editor').open)return;
 const a=button.dataset.action;
 if(a==='cca-add-item')button.closest('.cca-list').querySelector('.cca-items').insertAdjacentHTML('beforeend',listItem());
 if(a==='cca-remove-item')button.closest('.cca-list-item').remove();
 if(a==='cca-add-example')$('#cca-examples').insertAdjacentHTML('beforeend',exampleHTML());
 if(a==='cca-remove-example')button.closest('.cca-example').remove();
 if(a==='cca-add-reference')$('#cca-references').insertAdjacentHTML('beforeend',referenceHTML());
 if(a==='cca-remove-reference')button.closest('.cca-reference').remove();
 if(['add-category','remove-category','cca-add-example'].includes(a))syncCategoryChoices();
 indexCCAFields();
});
document.addEventListener('change',e=>{if(edit?.kind==='task'&&['cat-id','cat-label'].includes(e.target.name))syncCategoryChoices();});
document.addEventListener('invalid',e=>{
 for(let p=e.target.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
},true);
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b)return;
 try{
  if(b.dataset.action==='cca-import'&&!ccaImportBusy){console.debug('[CCA-Lab] CCA picker opened');ccaFile.click();}
  if(b.dataset.action==='cca-export'){
   const response=await fetch('/api/tasks/'+b.dataset.id+'/export-cca');if(!response.ok)throw Error((await response.json()).detail);
   const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='codebook-'+b.dataset.id+'.cca.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
 }catch(error){toast(error.message);}
});
ccaFile.addEventListener('change',async ()=>{
 const file=ccaFile.files[0];if(!file||ccaImportBusy)return;
 ccaImportBusy=true;const button=$('[data-action=cca-import]');if(button)button.disabled=true;
 ccaStatus('Importing CCA codebook…');
 console.debug('[CCA-Lab] CCA import started',{bytes:file.size});
 let importedId=null;
 try{
  if(file.size>5*1024*1024)throw Error('Maximum codebook size is 5 MiB.');
  const response=await fetch('/api/tasks/import-cca',{method:'POST',headers:{'Content-Type':'application/json'},body:file});
  const requestId=response.headers.get('X-Request-ID');
  console.debug('[CCA-Lab] CCA import response',{status:response.status,requestId});
  let body;try{body=await response.json();}catch{throw Error('Server returned an unreadable response (HTTP '+response.status+'). Check server logs.');}
  if(!response.ok)throw Error((typeof body.detail==='string'?body.detail:JSON.stringify(body.detail)||'Import failed')+(requestId?' [Request '+requestId+']':''));
  importedId=body.id;
  state.tasks=await api('/tasks');
  ccaStatus('CCA codebook imported successfully.');render();taskEditor(body.id);
  toast('CCA codebook imported as a new task. Review settings before running.');
 }catch(error){
  const message=importedId?'Task imported ('+importedId+'), but the view could not refresh. Reload the page.':error.message;
  ccaStatus(message);toast(message);
  console.warn('[CCA-Lab] CCA import failed',{stage:importedId?'refresh':'upload',errorType:error.name});
 }finally{ccaImportBusy=false;ccaFile.value='';const button=$('[data-action=cca-import]');if(button)button.disabled=false;}
});
