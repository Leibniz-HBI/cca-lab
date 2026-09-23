'use strict';
// Shared experiment builder for evaluation, prediction and standalone jobs.
let experimentVariants=[], editingVariant=null;
const experimentFields=[
 ['Model and sampling',[
 ['temperature','Temperature','0','Sampling temperature. Multiple comma-separated values generate variants.'],
 ['top_p','Top-p','1','Nucleus sampling probability, greater than 0 and at most 1. Comma-separated values (e.g. 0.8, 1) generate separate variants.'],
 ['thinking','Thinking','default','Server/model-specific thinking control. Select several comma-separated levels: default, off, on, minimal, low, medium, high, max.'],
 ['seeds','Seeds','9721','Comma-separated seeds create repeated runs of each configuration. Blank uses seed 9721.']]],
 ['Classification and context',[
 ['strategy','Classification strategy','joint','Joint: all categories in one decision. Binary: one category per request; only multi-label tasks support binary.','strategy'],
 ['use_context','Include document context',false,'Use the mapped context column before the target text. Context never contributes evidence spans.','boolean']]],
 ['Response content',[
 ['rationale','Rationale',false,'Generate a concise explanation of the coding decision.','boolean'],
 ['evidence','Evidence',false,'Extract exact target-text spans. Quotes from context or other samples are rejected.','boolean'],
 ['alternatives','Alternative interpretations',false,'Generate plausible candidate readings before selecting labels. Binary alternatives remain category-attributed.','boolean'],
 ['confidence','Self-reported confidence',false,'Uncalibrated estimate of decision correctness. Binary scores are retained per category, not combined into whole-set confidence.','boolean']]],
 ['Examples and batching',[
 ['examples_per_category','Few-shot examples per category','3','Comma-separated counts (e.g. 0, 3) generate separate variants. Maximum reference examples per category. Binary mode selects up to this many positive and negative examples.'],
 ['batch_size','Samples per LLM request','1','Comma-separated batch sizes (e.g. 1, 5, 10) generate separate variants. Up to 100 independent documents per request. Batch membership is recorded; batch size can affect results.']]],
 ['Execution and validation',[
 ['concurrency','Concurrent requests','4','Maximum requests in flight within a job. Jobs on separate servers can run simultaneously; jobs sharing a server are queued.'],
 ['retries','Retries','3','Additional attempts per unresolved document/category decision after its initial request.'],
 ['max_tokens','Maximum output tokens','8192','Initial output budget for the entire request, including all batched results and server-counted thinking. Retries after token exhaustion automatically double the budget, within the configured retry count. Server limits still apply.'],
 ['structured_output','Structured output','json_schema','json_schema uses native constraints; json_object requests JSON; none uses prompt instructions plus local validation.'],
 ['max_text_chars','Maximum text characters','30000','Per-document target-text limit.'],
 ['max_context_chars','Maximum context characters','30000','Per-document context limit, separate from the target text.'],
 ['max_batch_chars','Maximum batch input characters','200000','Splits batches deterministically when serialized inputs exceed this limit. Character counts are not token counts.'],
 ['overlong','Overlong input handling','error','error rejects oversized text/context; truncate clips each independently before prompting.'],
 ['default_label','Fallback category ID','','Optional category ID assigned only when a document decision fails. It must exist in every selected task; fallback outputs remain flagged.']]]
];
const numericExperimentFields=new Set(['temperature','top_p','examples_per_category','batch_size','concurrency','retries','max_tokens','max_text_chars','max_context_chars','max_batch_chars']);
function infoIcon(text){return `<span class="option-help" tabindex="0" role="button" aria-label="${esc(text)}">i<span role="tooltip">${esc(text)}</span></span>`;}
function experimentField([key,label,value,help,type]){
 let control;
 if(type==='boolean')control=`<select name="config_${key}"><option value="false">Off</option><option value="true">On</option><option value="both">Compare both</option></select>`;
 else if(type==='strategy')control=`<select name="config_${key}"><option value="joint">Joint labels</option><option value="binary">Per-category binary</option><option value="both">Compare both</option></select>`;
 else control=`<input name="config_${key}" value="${esc(value)}" autocomplete="off">`;
 return `<label><span>${label} ${infoIcon(help)}</span>${control}</label>`;
}
function configurationBuilder(){
 return `<section class="experiment-builder"><div class="section-title"><h3>Experiment configurations</h3><span class="small">Generate, review, then start</span></div><p class="small">Compare settings using “Compare both” or comma-separated values. Seeds repeat each configuration. All combinations are generated explicitly below.</p><div class="grid compiler-grid"><label>Connection ${infoIcon('Select the API connection for configurations generated from these settings.')}<select name="config_profile">${state.profiles.map(p=>option(p.id,p.spec.name)).join('')}</select></label><label>Available models ${infoIcon('Select one or more models. Each selected model creates configurations.')}<select name="config_models" multiple size="3"></select></label><label>Manual model IDs ${infoIcon('Comma-separated model IDs, in addition to selected models.')}<input name="config_manual_models"></label><label>Prompt compiler ${infoIcon("User/assistant roles uses example dialogue turns. Single system message puts annotated reference examples in the system message; target samples remain in the final user message. Compare both generates separate experiments.")}<select name="config_prompt_compiler"><option value="roles">User/assistant roles</option><option value="system">Single system message</option><option value="both">Compare both</option></select></label></div><p id="config-model-hint" class="small"></p><label>Configuration name prefix ${infoIcon('Optional descriptive prefix for generated configuration names.')}<input name="config_name"></label>${experimentFields.map(([title,fields],i)=>`<details class="config-section" ${i<3?'open':''}><summary>${title}</summary><div class="grid">${fields.map(experimentField).join('')}</div></details>`).join('')}<details class="config-section"><summary>Provider-specific parameters</summary><label>Additional API parameters ${infoIcon('JSON object sent to the provider. Controlled fields cannot be overridden. Thinking options depend on the server.')}<textarea name="config_extra_body">{}</textarea></label></details><div class="actions spaced"><button type="button" data-action="config-generate">Generate configurations</button><button type="button" data-action="config-clear">Clear configurations</button></div><div id="configurations-table"></div><div id="query-estimate" class="notice" aria-live="polite"></div><details class="config-section"><summary>Prompt preview</summary><div class="grid"><label>Configuration ${infoIcon('Preview the exact effective settings of a generated configuration.')}<select name="preview_variant"></select></label><label>Task ${infoIcon('Select the task to preview when predicting with multiple tasks.')}<select name="preview_task"></select></label><label>Binary category ${infoIcon('Only this category definition is included in binary mode. Ignored for joint mode.')}<select name="preview_category"></select></label><label>Rows after ${infoIcon('Read dataset rows after this row number, starting with 0 for the first batch.')}<input name="preview_after" type="number" min="0" value="0"></label></div><button type="button" data-action="config-preview">Generate preview</button><div id="configuration-preview" hidden></div></details></section>`;
}
let modelListRequest=0;
async function configModels(){
 const select=$('[name=config_models]'),profile=$('[name=config_profile]'),hint=$('#config-model-hint');
 const id=profile.value,request=++modelListRequest;
 select.innerHTML='';select.disabled=true;hint.textContent='Loading models…';
 const current=()=>request===modelListRequest&&$('[name=config_models]')===select&&profile.value===id;
 try{
  const response=await api('/profiles/'+id+'/models');if(!current())return;
  select.innerHTML=response.models.map(m=>option(m,m)).join('');
  hint.textContent=response.models.length+' models available. Select the model(s) to use.';
 }catch(e){if(current())hint.textContent=e.message+' Enter model IDs manually.';}
 finally{if(current())select.disabled=false;}
}
function selectedExperimentTasks(){
 if(edit.kind==='evaluation')return state.tasks.filter(t=>t.id===$('[name=task_id]').value);
 if(edit.source)return [{id:edit.source.snapshot.task_id,spec:edit.source.snapshot.task}];
 const ids=edit.kind==='job'?[$('[name=task_id]').value]:[...$('[name=task_ids]').selectedOptions].map(o=>o.value);
 return state.tasks.filter(t=>ids.includes(t.id));
}
function experimentMapping(){
 if(edit.kind==='evaluation'){const gold=state.goldSets.find(g=>g.id===$('[name=gold_id]').value);return {dataset_id:gold.spec.dataset_id,text_column:gold.spec.text_column,context_column:gold.spec.context_column||null,total:gold.total};}
 const dataset=state.datasets.find(d=>d.id===$('[name=dataset_id]').value);
 return {dataset_id:dataset.id,text_column:$('[name=text_column]').value,context_column:$('[name=context_column]').value||null,total:dataset.total};
}
function configurationValues(){
 const compiler=$('[name=config_prompt_compiler]').value;
 const values={prompt_compiler:compiler==='both'?['roles','system']:[compiler]};
 for(const [,fields] of experimentFields)for(const [key,,,help,type] of fields){
  const raw=$(`[name=config_${key}]`).value.trim();
  if(key==='seeds'){values.seeds=parseSeedInput(raw)||[9721];continue;}
  if(type==='boolean')values[key]=raw==='both'?[false,true]:[raw==='true'];
  else if(type==='strategy')values[key]=raw==='both'?['joint','binary']:[raw];
  else if(key==='default_label')values[key]=[raw||null];
  else {if(raw.split(',').some(x=>!x.trim()))throw Error('Empty value in '+key);values[key]=[...new Set(raw.split(',').map(x=>numericExperimentFields.has(key)?Number(x.trim()):x.trim()))];if(!raw||values[key].some(x=>x===''||typeof x==='number'&&!Number.isFinite(x)))throw Error('Invalid '+key);}
 }
 const bounds={temperature:[0,2],top_p:[Number.MIN_VALUE,1],examples_per_category:[0,100],batch_size:[1,100],concurrency:[1,128],retries:[0,10],max_tokens:[16,32768],max_text_chars:[1,1000000],max_context_chars:[1,1000000],max_batch_chars:[100,2000000]};
 for(const [key,[min,max]] of Object.entries(bounds))if(values[key].some(x=>x<min||x>max||!['temperature','top_p'].includes(key)&&!Number.isInteger(x)))throw Error(key+' must be '+(['temperature','top_p'].includes(key)?'a number':'an integer')+' between '+min+' and '+max+'.');
 for(const [key,allowed] of Object.entries({thinking:['default','off','on','minimal','low','medium','high','max'],structured_output:['json_schema','json_object','none'],overlong:['error','truncate']}))if(values[key].some(x=>!allowed.includes(x)))throw Error('Invalid '+key+': use '+allowed.join(', '));
 return values;
}
function generateConfigurations(){
 const values=configurationValues(),seeds=values.seeds;delete values.seeds;
 const models=[...new Set([...$('[name=config_models]').selectedOptions].map(o=>o.value).concat($('[name=config_manual_models]').value.split(',').map(v=>v.trim()).filter(Boolean)))];
 if($('[name=config_models]').disabled)throw Error('Wait for the selected connection’s models to load.');
 if(!models.length)throw Error('Select or enter a model.');
 let queries=models.map(model=>({model}));
 for(const [key,options] of Object.entries(values)){if(queries.length*options.length>50)throw Error('Maximum 50 configurations. Reduce the selected variations.');queries=queries.flatMap(q=>options.map(v=>({...q,[key]:v})));}
 const extras=JSON.parse($('[name=config_extra_body]').value||'{}');if(!extras||Array.isArray(extras)||typeof extras!=='object')throw Error('Additional parameters must be a JSON object.');
 const prefix=$('[name=config_name]').value.trim();
 const varying=Object.keys(values).filter(k=>values[k].length>1);
 const generated=queries.map((query,i)=>({name:(prefix?prefix+' · ':'')+query.model+' · '+[...new Set(['temperature','strategy','batch_size','prompt_compiler',...varying])].map(k=>k+'='+query[k]).join(' · '),profile_id:$('[name=config_profile]').value,seeds,query:{...query,seed:seeds[0],extra_body:extras}}));
 if(experimentVariants.length+generated.length-(editingVariant===null?0:1)>50)throw Error('Maximum 50 configurations.');
 if(editingVariant!==null)experimentVariants.splice(editingVariant,1,...generated);else experimentVariants.push(...generated);
 editingVariant=null;renderConfigurations();
}
function renderConfigurations(){
 $('#configurations-table').innerHTML=experimentVariants.length?`<div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Response fields</th><th>Seeds</th><th>Actions</th></tr></thead><tbody>${experimentVariants.map((v,i)=>`<tr><td><input aria-label="Configuration name" data-config-name="${i}" value="${esc(v.name)}"><span class="muted">${esc(state.profiles.find(p=>p.id===v.profile_id)?.spec.name||'Saved connection')} · ${esc(v.query.model)} · ${esc(v.query.strategy)} · batch ${v.query.batch_size} · context ${v.query.use_context?'on':'off'}</span></td><td>${['rationale','evidence','alternatives','confidence'].filter(k=>v.query[k]).join(', ')||'Labels only'}<details><summary>All settings</summary><pre>${esc(JSON.stringify(v.query,null,2))}</pre></details></td><td>${esc(v.seeds.join(', '))}</td><td><button type="button" data-action="config-edit" data-index="${i}">Edit</button><button type="button" data-action="config-duplicate" data-index="${i}">Duplicate</button><button type="button" data-action="config-remove" data-index="${i}">Remove</button></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No configurations yet. Generate configurations above.</p>';
 $('[name=preview_variant]').innerHTML=experimentVariants.map((v,i)=>option(i,v.name)).join('');updatePreviewTasks();queryEstimate();
}
function updatePreviewTasks(){
 if(!$('[name=preview_task]'))return;
 const previous=$('[name=preview_task]').value;
 $('[name=preview_task]').innerHTML=selectedExperimentTasks().map(t=>option(t.id,t.spec.codebook.title,previous)).join('');updatePreviewCategories();
}
function updatePreviewCategories(){const task=selectedExperimentTasks().find(t=>t.id===$('[name=preview_task]').value);$('[name=preview_category]').innerHTML=(task?.spec.codebook.task.categories||[]).map(c=>option(c.id,c.id+' · '+c.label)).join('');}
function queryEstimate(){
 const box=$('#query-estimate');if(!box||!$('#editor').open||!['job','prediction','evaluation'].includes(edit.kind))return;
 try{const mapping=experimentMapping(),tasks=selectedExperimentTasks();let planned=0,maximum=0,runs=0,decisions=0;
 for(const v of experimentVariants)for(const t of tasks){const c=v.query.strategy==='binary'?t.spec.codebook.task.categories.length:1,n=v.seeds.length;runs+=n;planned+=Math.ceil(mapping.total/v.query.batch_size)*c*n;decisions+=mapping.total*c*n;maximum+=mapping.total*c*n*(v.query.retries+1);}
 box.innerHTML=`<strong>Planned LLM queries: ${num(planned)}</strong><p>${num(mapping.total)} source documents · ${tasks.length} tasks · ${experimentVariants.length} configurations · ${runs} seed runs<br>${num(mapping.total*runs)} document classifications · ${num(decisions)} category/joint decisions</p><small>Nominal requests before character-based batch splits and retries. At most ${num(maximum)} attempts if every decision needs all retries and batches split to single documents. Actual requests and costs are recorded separately. ${runs>500?'Too many runs: maximum 500.':''}</small>`;
 }catch(e){box.textContent=e.message;}
}
function editConfiguration(index){
 const v=experimentVariants[index];$('[name=config_prompt_compiler]').value=v.query.prompt_compiler||'roles';editingVariant=index;$('[name=config_profile]').value=v.profile_id;$('[name=config_models]').innerHTML='';$('[name=config_manual_models]').value=v.query.model;$('[name=config_name]').value='';
 for(const [,fields] of experimentFields)for(const [key,,value] of fields)$(`[name=config_${key}]`).value=key==='seeds'?v.seeds.join(', '):v.query[key]??value;
 $('[name=config_extra_body]').value=JSON.stringify(v.query.extra_body||{},null,2);$('.experiment-builder').scrollIntoView({behavior:'smooth'});toast('Edit settings, then Generate configurations to replace this configuration.');
}
async function evaluationEditor(goldId,taskId){
 if(!state.tasks.length||!state.goldSets.length||!state.profiles.length){toast('Create a task, gold registration and model connection first.');return;}
 experimentVariants=[];editingVariant=null;
 openEditor('Configure evaluation',`${input('Evaluation name','name','Model comparison','text','required')}<div class="grid">${select('Gold dataset','gold_id',state.goldSets.map(g=>option(g.id,g.spec.name,goldId)).join(''))}${select('Classification task','task_id',state.tasks.map(t=>option(t.id,t.spec.codebook.title,taskId)).join(''))}</div>${configurationBuilder()}`,'evaluation');
 $('#editor-form button[type=submit]').textContent='Start evaluation';renderConfigurations();await configModels();
}
async function jobEditor(prediction=false,source=null){
 const ready=state.datasets.filter(d=>d.status==='ready'&&d.total);
 if(!ready.length||(!state.tasks.length&&!source)||(!state.profiles.length&&!source)){toast('Create tasks, a model connection and an imported dataset first.');return;}
 experimentVariants=[];editingVariant=null;
 const taskSelect=source?`<p>Evaluated task: ${esc(source.snapshot.task.codebook.title)}</p>`:`<label>${prediction?'Tasks':'Task'}<select name="${prediction?'task_ids':'task_id'}" ${prediction?'multiple size="4"':''}>${state.tasks.map((t,i)=>option(t.id,t.spec.codebook.title,i===0?t.id:null)).join('')}</select></label>`;
 openEditor(prediction?'Configure prediction':'Configure classification job',`${input('Name','name',prediction?'New prediction':'New job','text','required')}<div class="grid">${select('Dataset','dataset_id',ready.map(d=>option(d.id,d.name)).join(''))}${taskSelect}${select('Text column','text_column','')}${select('Context column (optional)','context_column','')}</div>${configurationBuilder()}`,prediction?'prediction':'job');edit.source=source;
 updateColumns();renderConfigurations();
 if(source){experimentVariants=[{name:source.snapshot.experiment_name||source.name,profile_id:'snapshot',query:source.snapshot.query,seeds:[source.snapshot.query.seed??9721]}];renderConfigurations();document.querySelectorAll('.experiment-builder > .grid,.experiment-builder > label,.experiment-builder > .actions,.experiment-builder > .config-section:not(:last-child)').forEach(el=>el.hidden=true);document.querySelectorAll('[data-action^=config-edit],[data-action^=config-remove],[data-action^=config-duplicate]').forEach(el=>el.hidden=true);$('#editor-body').insertAdjacentHTML('afterbegin','<p class="notice">Reusing the evaluated task, connection and configuration. Select the new dataset and remap text/context columns. Execution settings are preserved by the server.</p>');}
 else await configModels();
}
function updateColumns(){
 const d=state.datasets.find(d=>d.id===$('[name=dataset_id]')?.value);if(!$('[name=text_column]'))return;
 $('[name=text_column]').innerHTML=(d?.columns||[]).map(c=>option(c,c,'text')).join('');
 if($('[name=context_column]'))$('[name=context_column]').innerHTML=option('','No context')+(d?.columns||[]).map(c=>option(c,c)).join('');queryEstimate();
}
function effectiveVariants(){
 if(!experimentVariants.length)throw Error('Generate at least one configuration.');
 const names=new Set();return experimentVariants.map((v,i)=>{let name=v.name.trim()||'Configuration '+(i+1);if(names.has(name))name+=' #'+(i+1);names.add(name);return {...v,name};});
}
async function submitEvaluation(f){await api('/evaluations',{method:'POST',body:JSON.stringify({name:f.get('name'),gold_id:f.get('gold_id'),task_id:f.get('task_id'),variants:effectiveVariants()})});}
async function submitConfiguredJob(f){
 const variants=effectiveVariants(),mapping=experimentMapping();delete mapping.total;
 if(edit.kind==='job'){
 if(variants.length!==1||variants[0].seeds.length!==1)throw Error('Standalone jobs use one configuration and seed. Use Prediction for multiple runs.');
 await api('/jobs',{method:'POST',body:JSON.stringify({name:f.get('name'),task_id:f.get('task_id'),...mapping,profile_id:variants[0].profile_id,query:{...variants[0].query,seed:variants[0].seeds[0]}})});
 }else await api('/predictions',{method:'POST',body:JSON.stringify({name:f.get('name'),task_ids:selectedExperimentTasks().map(t=>t.id),...mapping,variants,source_evaluation_job_id:edit.source?.id||null})});
}
async function reuseEvaluation(id){const source=await api('/jobs/'+id);closeWorkflowDetail();location.hash='prediction';await jobEditor(true,source);}
async function previewConfiguration(){
 const v=experimentVariants[Number($('[name=preview_variant]').value)];if(!v)throw Error('Generate a configuration first.');
 const mapping=experimentMapping();delete mapping.total;
 const result=await api('/experiments/preview',{method:'POST',body:JSON.stringify({...mapping,task_id:$('[name=preview_task]').value,profile_id:v.profile_id,query:v.query,category:v.query.strategy==='binary'?$('[name=preview_category]').value:'',after:Number($('[name=preview_after]').value),source_evaluation_job_id:edit.source?.id||null})});
 $('#configuration-preview').hidden=false;$('#configuration-preview').innerHTML='<p class=small>'+esc(result.note)+'</p>'+jsonViewer(result.request);
}
document.addEventListener('click',async e=>{const el=e.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,i=Number(el.dataset.index);try{
 if(a==='config-generate')generateConfigurations();
 if(a==='config-clear'){experimentVariants=[];editingVariant=null;renderConfigurations();}
 if(a==='config-remove'){experimentVariants.splice(i,1);editingVariant=null;renderConfigurations();}
 if(a==='config-duplicate'){if(experimentVariants.length>=50)throw Error('Maximum 50 configurations');experimentVariants.push(structuredClone(experimentVariants[i]));renderConfigurations();}
 if(a==='config-edit')editConfiguration(i);
 if(a==='config-preview')await previewConfiguration();
 }catch(error){$('#form-error').textContent=error.message;}});
document.addEventListener('input',e=>{if(e.target.dataset.configName!==undefined)experimentVariants[Number(e.target.dataset.configName)].name=e.target.value;});
document.addEventListener('change',async e=>{try{if(e.target.name==='config_profile'){$('[name=config_manual_models]').value='';await configModels();}if(['task_id','task_ids','gold_id'].includes(e.target.name)){updatePreviewTasks();queryEstimate();}if(e.target.name==='preview_task')updatePreviewCategories();}catch(error){$('#form-error').textContent=error.message;}});

let requestLogOffset=0;
document.addEventListener('click',async e=>{const el=e.target.closest('[data-action]');if(!el||!['request-log','request-next'].includes(el.dataset.action))return;try{
 if(el.dataset.action==='request-log')requestLogOffset=0;
 const session=detailSession,id=el.dataset.id,offset=requestLogOffset;
 const rows=await api('/jobs/'+id+'/requests?after='+offset+'&limit=20');
 if(!currentDetail(session)||selectedJob!==id||requestLogOffset!==offset)return;
 requestLogOffset+=rows.length;
 $('#request-log').innerHTML=`<h3>LLM request log</h3><p class="small">Exact token usage and returned thinking are recorded once per request. Component results link here by request ID. Per-document duration is an equal allocation of request duration, not isolated latency.</p><a class="button" href="/api/jobs/${el.dataset.id}/requests.jsonl">Download requests JSONL ↓</a>${rows.map(r=>`<details><summary>${esc(r.id)} · ${esc(r.category||'joint')} · ${r.inputs.length} samples · ${esc(r.status)}</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`).join('')}<button type="button" data-action="request-next" data-id="${el.dataset.id}">Next 20</button>`;
 }catch(error){toast(error.message);}});
