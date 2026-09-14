'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n || 0).toLocaleString('en-US');
const statuses = {queued:'Queued',running:'Running',pausing:'Pausing',paused:'Paused',cancelling:'Cancelling',cancelled:'Cancelled',completed:'Completed',completed_with_errors:'Completed with errors',uploaded:'Waiting for import',importing:'Importing',ready:'Ready',failed:'Errors',evaluating:'Computing metrics',report_failed:'Report failed'};
const badge = s => `<span class="badge ${esc(s)}">${esc(statuses[s] || s)}</span>`;
let state = {tasks:[],datasets:[],profiles:[],jobs:[]}, page = '', edit = null, selectedJob = null, resultAfter = 0, loading = false;
async function api(path, opts = {}) {
  const response = await fetch('/api'+path, { ...opts, headers:{...(opts.body ? {'Content-Type':'application/json'} : {}),...opts.headers} });
  if (!response.ok) { let body; try {body=await response.json()} catch {body={detail:response.statusText}}; throw Error(typeof body.detail==='string' ? body.detail : JSON.stringify(body.detail)); }
  return response.json();
}
function toast(message) { $('#toast').textContent=message;$('#toast').style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').style.display='none',5000); }
const option = (value,label,selected) => `<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
const input = (label,name,value='',type='text',extra='') => `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const area = (label,name,value='',hint='') => `<label>${label}<textarea name="${name}">${esc(value)}</textarea>${hint?`<small>${hint}</small>`:''}</label>`;
const select = (label,name,options) => `<label>${label}<select name="${name}">${options}</select></label>`;
const empty = (title,description,action,label) => `<div class="panel empty"><div class="glyph">▤</div><h2>${title}</h2><p>${description}</p><button class="primary" data-action="${action}">${label}</button></div>`;
async function refresh() {
  if(loading) return; loading=true;
  try {
    const [tasks,datasets,profiles,jobs,evaluations,goldSets,predictions,health] = await Promise.all(['/tasks','/datasets','/profiles','/jobs','/evaluations','/gold-sets','/predictions','/health'].map(p=>api(p)));
    state={tasks,datasets,profiles,jobs,evaluations,goldSets,predictions};
    $('#health').textContent=health.worker_online?'Worker connected':'Worker offline';
    render();
    if(typeof selectedPrediction!=='undefined' && selectedPrediction && $('#detail').open) await showPrediction(selectedPrediction,false);
    if(selectedJob && $('#detail').open) await showJob(selectedJob,false);
    if(typeof selectedEvaluation!=='undefined' && selectedEvaluation && $('#detail').open) await showEvaluation(selectedEvaluation,false);
  } finally { loading=false; }
}
function render() {
  page=location.hash.slice(1) || 'jobs';if(!['jobs','tasks','datasets','profiles','evaluations','gold','prediction'].includes(page))page='jobs';
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+page));
  const labels={prediction:['Prediction','New prediction'],evaluations:['Evaluations','New evaluation'],gold:['Gold datasets','Register gold dataset'],jobs:['Classification jobs','New job'],tasks:['Task library','New task'],datasets:['Datasets','Upload CSV'],profiles:['LLM connections','New connection']};
  $('#title').textContent=labels[page][0];$('#primary').textContent=labels[page][1];
  if(page==='prediction')renderPredictions();if(page==='evaluations')renderEvaluations();if(page==='gold')renderGold();if(page==='jobs') renderJobs();if(page==='tasks') renderTasks();if(page==='datasets') renderDatasets();if(page==='profiles')renderProfiles();
}
function renderJobs() {
 const jobs=state.jobs;
 const stats=[['Total jobs',jobs.length],['Active / queued',jobs.filter(j=>['running','queued'].includes(j.status)).length],['Processed texts',jobs.reduce((a,j)=>a+j.done,0)],['Failed texts',jobs.reduce((a,j)=>a+j.failed,0)]];
 $('#view').innerHTML=`<div class="stats">${stats.map(([k,v])=>`<div class="stat"><span>${k}</span><strong>${num(v)}</strong></div>`).join('')}</div>`+(jobs.length?`<div class="panel"><div class="panel-head"><h2>Runs</h2><span class="muted">Auto-refresh · 3 s</span></div><div class="table-wrap"><table><thead><tr><th>Job / model</th><th>Status</th><th>Progress</th><th>Errors</th><th></th></tr></thead><tbody>${jobs.map(j=>`<tr><td><button class="link-button" data-action="job-detail" data-id="${j.id}">${esc(j.name)}</button><div class="muted">${esc(j.model)} · ${esc(j.task_name)}</div></td><td>${badge(j.status)}</td><td class="progress">${num(j.done)} / ${num(j.total)}<progress value="${j.done}" max="${j.total}" aria-label="Progress"></progress></td><td>${num(j.failed)}</td><td><button data-action="job-detail" data-id="${j.id}">Open</button></td></tr>`).join('')}</tbody></table></div></div>`:empty('Your first classification','Create a task, upload a dataset and connect your language model to start a job.','new-job','Create job'));
}
function renderTasks() {
 $('#view').innerHTML=state.tasks.length?`<div class="cards">${state.tasks.map(t=>`<article class="card"><div class="muted">${t.spec.mode==='single'?'SINGLE-LABEL':'MULTI-LABEL'} · VERSION ${t.revision}</div><h2>${esc(t.spec.name)}</h2><p>${esc(t.spec.description||t.spec.instructions.slice(0,180))}</p><div class="chips">${t.spec.categories.map(c=>`<span class="chip">${esc(c.label)}</span>`).join('')}</div><p>${t.spec.categories.reduce((n,c)=>n+c.examples.length,0)+t.spec.examples.length} Few-shot examples · ${t.spec.rationale?'with':'without'} Rationale</p><div class="actions"><button data-action="edit-task" data-id="${t.id}">Edit</button><button data-action="download-task" data-id="${t.id}">JSON ↓</button><button class="danger" data-action="delete-task" data-id="${t.id}">Delete</button></div></article>`).join('')}</div>`:empty('Reusable classification tasks','Define categories, instructions and examples. Jobs preserve the task version in a snapshot.','new-task','Create task');
}
function renderDatasets() {
 $('#view').innerHTML=`<div class="notice">CSV files stream to the server and are imported in batches. Default limit: 1 GiB. Choose the delimiter and encoding when uploading.</div>`+(state.datasets.length?`<div class="panel table-wrap"><table><thead><tr><th>Dataset</th><th>Status</th><th>Rows</th><th>Size</th><th></th></tr></thead><tbody>${state.datasets.map(d=>`<tr><td><strong>${esc(d.name)}</strong><span class="muted">${esc(d.columns.join(' · ').slice(0,180))}</span>${d.error?`<p class="error">${esc(d.error)}</p>`:''}</td><td>${badge(d.status)}</td><td>${num(d.total)}</td><td>${(d.bytes/1024/1024).toFixed(1)} MiB</td><td><button data-action="dataset-preview" data-id="${d.id}">Preview</button> ${d.csv_available?`<button class="danger" data-action="remove-csv" data-id="${d.id}">Delete CSV file</button>`:'<span class="muted">CSV removed</span>'} <button class="danger" data-action="remove-dataset" data-id="${d.id}">Delete dataset</button></td></tr>`).join('')}</tbody></table></div>`:empty('Texts for classification','Upload a CSV with a header, such as id, text, date. Original columns are preserved for export.','new-dataset','Upload CSV'));
}
function renderProfiles() {
 $('#view').innerHTML=`<div class="notice">Ollama: native API, e.g. http://host.docker.internal:11434. vLLM: OpenAI-compatible API with /v1. Supply API keys through server environment variables.</div>`+(state.profiles.length?`<div class="cards">${state.profiles.map(p=>`<article class="card"><span class="muted">${esc(p.spec.provider.toUpperCase())}</span><h2>${esc(p.spec.name)}</h2><p class="break">${esc(p.spec.base_url)}</p><p>${p.spec.provider==='mock'?'Demo: always selects the first category.':`Timeout: ${p.spec.timeout} s · Key: ${esc(p.spec.api_key_env||'not required')}`}</p><div class="actions"><button data-action="edit-profile" data-id="${p.id}">Edit</button><button data-action="test-profile" data-id="${p.id}">List models</button><button class="danger" data-action="remove-profile" data-id="${p.id}">Delete</button></div></article>`).join('')}</div>`:empty('Connect your language model','Use Ollama, vLLM or another OpenAI-compatible API. A demo connection lets you test without a model server.','new-profile','Create connection'));
}
function openEditor(title,html,kind,id=null) {
 edit={kind,id};$('#dialog-title').textContent=title;$('#editor-body').innerHTML=html;$('#form-error').textContent='';$('#editor-form button[type=submit]').disabled=false;$('#editor-form button[type=submit]').textContent=kind==='job'?'Start job':kind==='dataset'?'Upload':'Save';$('#editor').showModal();
}
function categoryHTML(c={label:'',definition:'',examples:[]}) {
 return `<div class="category"><div class="category-head"><strong>Category</strong><button type="button" data-action="remove-category">Remove</button></div>${input('Label','cat-label',c.label,'text','required')}${area('Definition','cat-definition',c.definition)}${area('Few-shot examples','cat-examples',c.examples.join('\n---\n'),'Separate examples with --- on its own line. Each example receives only this label.')}</div>`;
}
function taskEditor(id) {
 const existing=state.tasks.find(t=>t.id===id);
 const t=existing?.spec||{name:'',description:'',instructions:'Classify the text using only the following categories.',mode:'single',categories:[{label:'FOR',definition:'The text supports the subject under study.',examples:[]},{label:'AGAINST',definition:'The text opposes the subject under study.',examples:[]},{label:'NO',definition:'No clear position on the subject is identifiable.',examples:[]}],examples:[],ambiguity_rule:'Use NO when no clear position is identifiable.',allow_empty:false,rationale:false};
 openEditor(existing?'Edit task':'Create task',`${input('Name','name',t.name,'text','required')}${area('Description','description',t.description)}<div class="grid">${select('Classification mode','mode',option('single','Single-Label (Multi-class)',t.mode)+option('multi','Multi-Label',t.mode))}<div><label><input type="checkbox" name="rationale" ${t.rationale?'checked':''}>Generate rationale</label><label><input type="checkbox" name="evidence" ${t.evidence?'checked':''}>Extract verbatim evidence</label><label><input type="checkbox" name="allow_empty" ${t.allow_empty?'checked':''}>Allow empty selection (multi-label)</label></div></div>${thinkingSelect('thinking',t.thinking||'default')}${area('General coding instructions','instructions',t.instructions)}${area('Ambiguity rule','ambiguity_rule',t.ambiguity_rule)}<div class="section-title"><h3>Categories</h3><button type="button" data-action="add-category">+ Category</button></div><div id="categories">${t.categories.map(categoryHTML).join('')}</div><details><summary>Multi-label examples and output schema</summary>${area('Additional few-shot examples (JSON)','examples',JSON.stringify(t.examples,null,2),'List of {"text":"…","labels":["FOR"],"rationale":"…"}. Use multiple labels for multi-label examples.')}<p class="small">Output: JSON with labels and optional rationale and evidence (label + exact quote). Character offsets are added after validation. Unknown or duplicate labels, extra fields and invalid cardinality are rejected.</p><button type="button" data-action="prompt-preview">Prompt preview</button><pre id="prompt-preview" hidden></pre></details>`,'task',id);
 edit.revision=existing?.revision;
}
function readTask() {
 const form=$('#editor-form'), f=new FormData(form);
 return {thinking:f.get('thinking'),name:f.get('name'),description:f.get('description'),instructions:f.get('instructions'),mode:f.get('mode'),ambiguity_rule:f.get('ambiguity_rule'),rationale:f.has('rationale'),evidence:f.has('evidence'),allow_empty:f.has('allow_empty'),examples:JSON.parse(f.get('examples')||'[]'),categories:[...document.querySelectorAll('.category')].map(c=>({label:c.querySelector('[name=cat-label]').value,definition:c.querySelector('[name=cat-definition]').value,examples:c.querySelector('[name=cat-examples]').value.split(/^---\s*$/m).map(s=>s.trim()).filter(Boolean)}))};
}
function profileEditor(id) {
 const p=state.profiles.find(p=>p.id===id)?.spec||{name:'Local vLLM',provider:'openai',base_url:'http://host.docker.internal:8000/v1',api_key_env:'',timeout:120};
 openEditor(id?'Edit connection':'Connect LLM',`${input('Name','name',p.name,'text','required')}${select('API type','provider',['openai','ollama','mock'].map(v=>option(v,{openai:'OpenAI-compatible / vLLM',ollama:'Ollama (native API)',mock:'Demo without LLM — always the first label'}[v],p.provider)).join(''))}${input('Base URL','base_url',p.base_url,'url','required')}${input('API key environment variable (optional)','api_key_env',p.api_key_env)}${select('Thinking control for OpenAI-compatible APIs','thinking_adapter',['auto','reasoning_effort','chat_template'].map(a=>option(a,{auto:'Auto (reasoning_effort)',reasoning_effort:'reasoning_effort',chat_template:'Chat template (on/off only)'}[a],p.thinking_adapter||'auto')).join(''))}${input('Request timeout (seconds)','timeout',p.timeout,'number','min=1 max=1800 required')}<p class="muted">The backend and worker call this URL. Use localhost for a direct Python installation; host.docker.internal refers to the host in Docker.</p>`,'profile',id);
}
function datasetEditor() {
 openEditor('Upload CSV',`<label class="file-input">Choose file<input name="file" type="file" accept=".csv,.tsv,text/csv" required></label><div class="grid">${select('Delimiter','delimiter',option(',','Comma',',')+option(';','Semicolon')+option('\t','Tab')+option('|','Pipe'))}${select('Encoding','encoding',['utf-8-sig','utf-8','cp1252','latin-1'].map(v=>option(v,v,'utf-8-sig')).join(''))}</div><p class="muted">A header with unique column names is required. Select the text column when creating a job.</p><div class="upload-progress" hidden><span id="upload-label"></span><progress id="upload-progress" max=100 value=0></progress></div>`,'dataset');
}
async function jobEditor(prediction=false) {
 if(!state.tasks.length||!state.datasets.some(d=>d.status==='ready'&&d.total)||!state.profiles.length) {toast('Requires a task, a fully imported dataset and an LLM connection.');return;}
 openEditor('Create classification job',`${input('Job name','name','New classification','text','required')}<div class="grid">${select('Task','task_id',state.tasks.map(t=>option(t.id,t.spec.name)).join(''))}${select('Dataset','dataset_id',state.datasets.filter(d=>d.status==='ready'&&d.total).map(d=>option(d.id,d.name)).join(''))}${select('Text column','text_column','')}${select('LLM connection','profile_id',state.profiles.map(p=>option(p.id,p.spec.name)).join(''))}<label>Model<input name="model" list="model-list" required placeholder="Load a model or enter its ID"><datalist id="model-list"></datalist><small id="model-hint">Loading model list …</small></label>${input('Concurrent requests','concurrency',4,'number','min=1 max=128 required')}${input('Retries after failure','retries',2,'number','min=0 max=10 required')}${input('Temperature','temperature',0,'number','min=0 max=2 step=0.1 required')}</div><details><summary>Model and task parameters</summary><div class="grid">${outputToggles()}${input('Top-p','top_p',1,'number','min=0.01 max=1 step=0.01 required')}${input('Maximum output tokens','max_tokens',256,'number','min=16 max=32768 required')}${input('Seed (optional)','seed','','number')}${select('Structured output','structured_output',option('json_schema','JSON Schema','json_schema')+option('json_object','JSON object')+option('none','Prompt only'))}${input('Examples per category','examples_per_category',3,'number','min=0 max=100 required')}${input('Maximum text length (characters)','max_text_chars',30000,'number','min=1 max=1000000 required')}${select('Overlong texts','overlong',option('error','Mark as failed','error')+option('truncate','Explicitly truncate'))}</div>${area('Additional API parameters (JSON)','extra_body','{}','Example for supported vLLM models: {"chat_template_kwargs":{"enable_thinking":false}}. Compatibility depends on the server.')}</details><p class="muted">Task and settings are saved as an immutable job snapshot. A worker processes jobs sequentially using the selected concurrency.</p>`,'job');
 if(prediction){edit.kind='prediction';$('#dialog-title').textContent='Create prediction';$('[name=name]').value='New prediction';const t=$('[name=task_id]');t.name='task_ids';t.multiple=true;t.size=Math.min(6,state.tasks.length);t.required=true;t.options[0].selected=true;t.insertAdjacentHTML('afterend','<small>Use Ctrl/Cmd to select multiple tasks. Each task runs on every row.</small>');$('#editor-form button[type=submit]').textContent='Start prediction';}
 updateColumns();await loadModels();
}
function updateColumns() {
 const d=state.datasets.find(d=>d.id===$('[name=dataset_id]').value);$('[name=text_column]').innerHTML=(d?.columns||[]).map(c=>option(c,c,c==='text'?'text':undefined)).join('');
}
async function loadModels() {
 const id=$('[name=profile_id]').value;
 try {const {models}=await api('/profiles/'+id+'/models');if(!$('#model-list') || $('[name=profile_id]').value!==id)return;$('#model-list').innerHTML=models.map(m=>option(m,m)).join('');$('[name=model]').value=models[0]||'';$('#model-hint').textContent=models.length+' models available; you can also enter a custom ID.';}catch(e){if($('#model-hint'))$('#model-hint').textContent=e.message+' You can enter the model ID manually.';}
}
async function submit(event) {
 event.preventDefault();const button=$('#editor-form button[type=submit]');button.disabled=true;$('#form-error').textContent='';
 try {
  const f=new FormData($('#editor-form'));
  if(edit.kind==='gold')await submitGold(f);
  if(edit.kind==='evaluation')await submitEvaluation(f);
  if(edit.kind==='task') await api('/tasks'+(edit.id?'/'+edit.id+'?revision='+edit.revision:''),{method:edit.id?'PUT':'POST',body:JSON.stringify(readTask())});
  if(edit.kind==='profile') await api('/profiles'+(edit.id?'/'+edit.id:''),{method:edit.id?'PUT':'POST',body:JSON.stringify({name:f.get('name'),provider:f.get('provider'),base_url:f.get('base_url'),api_key_env:f.get('api_key_env'),timeout:Number(f.get('timeout')),thinking_adapter:f.get('thinking_adapter')})});
  if(edit.kind==='dataset') await uploadFile(f);
  if(edit.kind==='job'||edit.kind==='prediction') {
   const query={};for(const k of ['concurrency','retries','temperature','top_p','max_tokens','examples_per_category','max_text_chars'])query[k]=Number(f.get(k));
   for(const k of ['model','structured_output','overlong'])query[k]=f.get(k);
   query.thinking=f.get('thinking_override')||null;query.rationale=triState(f.get('rationale_override'));query.evidence=triState(f.get('evidence_override'));query.seed=f.get('seed')===''?null:Number(f.get('seed'));query.extra_body=JSON.parse(f.get('extra_body'));
   await api(edit.kind==='prediction'?'/predictions':'/jobs',{method:'POST',body:JSON.stringify({name:f.get('name'),...(edit.kind==='prediction'?{task_ids:f.getAll('task_ids')}:{task_id:f.get('task_id')}),dataset_id:f.get('dataset_id'),profile_id:f.get('profile_id'),text_column:f.get('text_column'),query})});
  }
  $('#editor').close();toast(edit.kind==='dataset'?'Upload completed. The worker will import the file.':'Saved.');await refresh();
 }catch(e){$('#form-error').textContent=e.message;}finally{button.disabled=false;}
}
function uploadFile(f) {
 return new Promise((resolve,reject)=>{
  const file=f.get('file'),params=new URLSearchParams({filename:file.name,delimiter:f.get('delimiter'),encoding:f.get('encoding')});
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/datasets?'+params);xhr.setRequestHeader('Content-Type','application/octet-stream');
  $('.upload-progress').hidden=false;
  xhr.upload.onprogress=e=>{if(e.lengthComputable){$('#upload-progress').value=e.loaded/e.total*100;$('#upload-label').textContent=Math.round(e.loaded/e.total*100)+' % uploaded';}};
  xhr.onerror=()=>reject(Error('Upload connection interrupted; upload again.'));
  xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300)resolve();else{let m=xhr.statusText;try{m=JSON.parse(xhr.responseText).detail}catch{}reject(Error(m));}};
  xhr.send(file);
 });
}
async function showJob(id,initial=true) {
 if(initial)selectedPrediction=null;
 const job=await api('/jobs/'+id);selectedJob=id;
 if(initial){resultAfter=0;$('#detail-title').textContent=job.name;$('#detail-body').innerHTML='<div id="job-live"></div><div id="job-results" class="spaced"></div><details><summary>View / download job snapshot</summary><div class="actions"><button data-action="snapshot" data-id="'+id+'">Snapshot JSON ↓</button></div><pre>'+esc(JSON.stringify(job.snapshot,null,2))+'</pre></details>';$('#detail').showModal();}
 if(!$('#job-live'))return;
 const allowed=[];if(['queued','running'].includes(job.status))allowed.push(['pause','Pause']);if(job.status==='paused')allowed.push(['resume','Resume']);if(['queued','running','paused','pausing'].includes(job.status))allowed.push(['cancel','Cancel']);
 $('#job-live').innerHTML=`<div class="section-title">${badge(job.status)}<div class="actions">${allowed.map(([a,l])=>`<button data-action="control" data-control="${a}" data-id="${id}">${l}</button>`).join('')}</div></div><div class="stats"><div class="stat"><span>Processed</span><strong>${num(job.done)}</strong></div><div class="stat"><span>Total</span><strong>${num(job.total)}</strong></div><div class="stat"><span>Errors</span><strong>${num(job.failed)}</strong></div><div class="stat"><span>API attempts</span><strong>${num(job.metrics.requests)}</strong></div></div><progress value="${job.done}" max="${job.total}" aria-label="Job progress"></progress><p class="muted">Active: ${metricNumber(job.runtime.active_seconds)} s · ${metricNumber(job.runtime.documents_per_second)} docs/s · ${esc(job.model)} · Ø ${job.metrics.avg_seconds.toFixed(2)} s per text (including retries) · ${num(job.metrics.prompt_tokens)} Input- / ${num(job.metrics.completion_tokens)} Output-Tokens</p>${job.last_error?`<p class="error">Last error: ${esc(job.last_error)}</p>`:''}<div class="actions">${['completed','completed_with_errors','cancelled'].includes(job.status)?['csv','jsonl','parquet'].map(fmt=>`<a class="button" href="/api/jobs/${id}/export?format=${fmt}">${fmt.toUpperCase()} ↓</a>`).join(''):'<span class="muted">Exports are available once the job has completed or cancellation has finished.</span>'}</div>`;
 if(initial)await loadResults();
}
async function loadResults() {
 const rows=await api('/jobs/'+selectedJob+'/results?after='+resultAfter);
 $('#job-results').innerHTML=`<div class="section-title"><h3>Results</h3><div class="actions"><button data-action="results-first">First page / refresh</button>${rows.length?`<button data-action="results-next" data-after="${rows.at(-1).row_no}">Next</button>`:''}</div></div>`+(rows.length?`<div class="table-wrap"><table><thead><tr><th>Row</th><th>Source data</th><th>Labels</th><th>Status / Rationale</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.row_no}</td><td class="result-text">${esc(JSON.stringify(r.source).slice(0,650))}</td><td>${r.labels.map(esc).join(', ')||'—'}</td><td class="result-text">${esc(r.error||r.rationale||r.status)}<details><summary>Evidence / thinking / attempts</summary><pre>${esc(JSON.stringify({evidence:r.evidence,thinking:r.thinking,attempt_outputs:r.attempt_outputs},null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No more results available.</p>');
}
function download(name,value) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function action(event) {
 const el=event.target.closest('[data-action]');if(!el)return;
 const a=el.dataset.action,id=el.dataset.id;
 try {
  if(a==='close')$('#editor').close();if(a==='close-detail'){$('#detail').close();selectedJob=null;}
  if(a==='new-task'||a==='edit-task')taskEditor(id);if(a==='new-profile'||a==='edit-profile')profileEditor(id);if(a==='new-dataset')datasetEditor();if(a==='new-job')await jobEditor();
  if(a==='add-category')$('#categories').insertAdjacentHTML('beforeend',categoryHTML());if(a==='remove-category')el.closest('.category').remove();
  if(a==='prompt-preview'){const prompt=await api('/tasks/preview',{method:'POST',body:JSON.stringify(readTask())});$('#prompt-preview').hidden=false;$('#prompt-preview').textContent=JSON.stringify(prompt,null,2);}
  if(a==='download-task')download('textlab-task.json',state.tasks.find(t=>t.id===id).spec);
  if(a==='delete-task'&&confirm('Delete this task? Existing job snapshots are preserved.')){await api('/tasks/'+id,{method:'DELETE'});await refresh();}
  if(a==='test-profile'){const r=await api('/profiles/'+id+'/models');toast(r.models.join(', ')||'No models available.');}
  if(a==='job-detail'){selectedEvaluation=null;await showJob(id);}
  if(a==='control'){if(el.dataset.control==='cancel'&&!confirm('Job abbrechen? Readys verarbeitete Results bleiben erhalten.'))return;await api('/jobs/'+id+'/'+el.dataset.control,{method:'POST'});await refresh();}
  if(a==='results-next'){resultAfter=Number(el.dataset.after);await loadResults();}if(a==='results-first'){resultAfter=0;await loadResults();}
  if(a==='snapshot')download('textlab-job-'+id+'.json',(await api('/jobs/'+id)).snapshot);
  if(a==='dataset-preview'){selectedJob=null;const r=await api('/datasets/'+id+'/preview');$('#detail-title').textContent='Dataset preview · first 10 rows';$('#detail-body').innerHTML='<pre>'+esc(JSON.stringify(r,null,2))+'</pre>';$('#detail').showModal();}
 }catch(e){if($('#editor').open)$('#form-error').textContent=e.message;else toast(e.message);}
}
$('#primary').onclick=()=>({prediction:predictionEditor,jobs:jobEditor,tasks:taskEditor,datasets:datasetEditor,profiles:profileEditor,evaluations:evaluationEditor,gold:goldEditor}[page])();
$('#editor-form').addEventListener('submit',submit);document.addEventListener('click',action);
$('#editor-form').addEventListener('change',e=>{if(e.target.name==='dataset_id'){if(edit.kind==='gold')updateGoldColumns();else updateColumns();}if(e.target.name==='profile_id')loadModels();});
$('#detail').addEventListener('close',()=>selectedJob=null);
window.addEventListener('hashchange',render);
refresh().catch(e=>toast(e.message));setInterval(()=>{if(!document.hidden)refresh().catch(e=>toast(e.message));},3000);
