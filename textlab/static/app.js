'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n || 0).toLocaleString('de-DE');
const statuses = {queued:'Warteschlange',running:'Läuft',pausing:'Wird pausiert',paused:'Pausiert',cancelling:'Wird abgebrochen',cancelled:'Abgebrochen',completed:'Abgeschlossen',completed_with_errors:'Mit Fehlern beendet',uploaded:'Wartet auf Import',importing:'Import läuft',ready:'Bereit',failed:'Fehler',evaluating:'Metriken werden berechnet',report_failed:'Reportfehler'};
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
    const [tasks,datasets,profiles,jobs,evaluations,goldSets,health] = await Promise.all(['/tasks','/datasets','/profiles','/jobs','/evaluations','/gold-sets','/health'].map(p=>api(p)));
    state={tasks,datasets,profiles,jobs,evaluations,goldSets};
    $('#health').textContent=health.worker_online?'Worker verbunden':'Worker offline';
    render();
    if(selectedJob && $('#detail').open) await showJob(selectedJob,false);
    if(typeof selectedEvaluation!=='undefined' && selectedEvaluation && $('#detail').open) await showEvaluation(selectedEvaluation,false);
  } finally { loading=false; }
}
function render() {
  page=location.hash.slice(1) || 'jobs';if(!['jobs','tasks','datasets','profiles','evaluations','gold'].includes(page))page='jobs';
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+page));
  const labels={evaluations:['Evaluationen','Neue Evaluation'],gold:['Gold-Datensätze','Gold-Datensatz registrieren'],jobs:['Klassifikationsjobs','Neuer Job'],tasks:['Task-Bibliothek','Neuer Task'],datasets:['Datensätze','CSV hochladen'],profiles:['LLM-Verbindungen','Neue Verbindung']};
  $('#title').textContent=labels[page][0];$('#primary').textContent=labels[page][1];
  if(page==='evaluations')renderEvaluations();if(page==='gold')renderGold();if(page==='jobs') renderJobs();if(page==='tasks') renderTasks();if(page==='datasets') renderDatasets();if(page==='profiles')renderProfiles();
}
function renderJobs() {
 const jobs=state.jobs;
 const stats=[['Jobs gesamt',jobs.length],['Aktiv / wartend',jobs.filter(j=>['running','queued'].includes(j.status)).length],['Texte verarbeitet',jobs.reduce((a,j)=>a+j.done,0)],['Fehlerhafte Texte',jobs.reduce((a,j)=>a+j.failed,0)]];
 $('#view').innerHTML=`<div class="stats">${stats.map(([k,v])=>`<div class="stat"><span>${k}</span><strong>${num(v)}</strong></div>`).join('')}</div>`+(jobs.length?`<div class="panel"><div class="panel-head"><h2>Auswertungen</h2><span class="muted">Automatische Aktualisierung · 3 s</span></div><div class="table-wrap"><table><thead><tr><th>Job / Modell</th><th>Status</th><th>Fortschritt</th><th>Fehler</th><th></th></tr></thead><tbody>${jobs.map(j=>`<tr><td><button class="link-button" data-action="job-detail" data-id="${j.id}">${esc(j.name)}</button><div class="muted">${esc(j.model)} · ${esc(j.task_name)}</div></td><td>${badge(j.status)}</td><td class="progress">${num(j.done)} / ${num(j.total)}<progress value="${j.done}" max="${j.total}" aria-label="Fortschritt"></progress></td><td>${num(j.failed)}</td><td><button data-action="job-detail" data-id="${j.id}">Öffnen</button></td></tr>`).join('')}</tbody></table></div></div>`:empty('Deine erste Auswertung','Lege ein Kodierbuch an, lade einen Datensatz hoch und verbinde dein Sprachmodell. Ein Job verbindet diese drei Bausteine.','new-job','Job anlegen'));
}
function renderTasks() {
 $('#view').innerHTML=state.tasks.length?`<div class="cards">${state.tasks.map(t=>`<article class="card"><div class="muted">${t.spec.mode==='single'?'SINGLE-LABEL':'MULTI-LABEL'} · VERSION ${t.revision}</div><h2>${esc(t.spec.name)}</h2><p>${esc(t.spec.description||t.spec.instructions.slice(0,180))}</p><div class="chips">${t.spec.categories.map(c=>`<span class="chip">${esc(c.label)}</span>`).join('')}</div><p>${t.spec.categories.reduce((n,c)=>n+c.examples.length,0)+t.spec.examples.length} Few-Shot-Beispiele · ${t.spec.rationale?'mit':'ohne'} Begründung</p><div class="actions"><button data-action="edit-task" data-id="${t.id}">Bearbeiten</button><button data-action="download-task" data-id="${t.id}">JSON ↓</button><button class="danger" data-action="delete-task" data-id="${t.id}">Löschen</button></div></article>`).join('')}</div>`:empty('Kodierbücher für wiederholbare Analysen','Definiere Kategorien, Kodieranweisungen und Beispiele. Jobs bewahren die verwendete Version als Snapshot.','new-task','Task erstellen');
}
function renderDatasets() {
 $('#view').innerHTML=`<div class="notice">CSV-Dateien werden direkt auf den Server übertragen und anschließend blockweise importiert. Standardlimit: 1 GiB. Wähle Trennzeichen und Zeichenkodierung beim Upload.</div>`+(state.datasets.length?`<div class="panel table-wrap"><table><thead><tr><th>Datensatz</th><th>Status</th><th>Zeilen</th><th>Größe</th><th></th></tr></thead><tbody>${state.datasets.map(d=>`<tr><td><strong>${esc(d.name)}</strong><span class="muted">${esc(d.columns.join(' · ').slice(0,180))}</span>${d.error?`<p class="error">${esc(d.error)}</p>`:''}</td><td>${badge(d.status)}</td><td>${num(d.total)}</td><td>${(d.bytes/1024/1024).toFixed(1)} MiB</td><td><button data-action="dataset-preview" data-id="${d.id}">Vorschau</button></td></tr>`).join('')}</tbody></table></div>`:empty('Texte für die Klassifikation','CSV mit Kopfzeile: etwa id, text, date. Die Originalspalten bleiben für den späteren Export erhalten.','new-dataset','CSV hochladen'));
}
function renderProfiles() {
 $('#view').innerHTML=`<div class="notice">Ollama: native API, z. B. http://host.docker.internal:11434. vLLM: OpenAI-kompatible API mit /v1. API-Schlüssel werden über Umgebungsvariablen auf dem Server bereitgestellt.</div>`+(state.profiles.length?`<div class="cards">${state.profiles.map(p=>`<article class="card"><span class="muted">${esc(p.spec.provider.toUpperCase())}</span><h2>${esc(p.spec.name)}</h2><p class="break">${esc(p.spec.base_url)}</p><p>${p.spec.provider==='mock'?'Demo: vergibt immer die erste Kategorie.':`Timeout: ${p.spec.timeout} s · Key: ${esc(p.spec.api_key_env||'nicht erforderlich')}`}</p><div class="actions"><button data-action="edit-profile" data-id="${p.id}">Bearbeiten</button><button data-action="test-profile" data-id="${p.id}">Modelle abfragen</button></div></article>`).join('')}</div>`:empty('Verbinde dein Sprachmodell','Nutze Ollama, vLLM oder eine andere OpenAI-kompatible API. Eine Demo-Verbindung erlaubt einen Test ohne Modellserver.','new-profile','Verbindung anlegen'));
}
function openEditor(title,html,kind,id=null) {
 edit={kind,id};$('#dialog-title').textContent=title;$('#editor-body').innerHTML=html;$('#form-error').textContent='';$('#editor-form button[type=submit]').disabled=false;$('#editor-form button[type=submit]').textContent=kind==='job'?'Job starten':kind==='dataset'?'Hochladen':'Speichern';$('#editor').showModal();
}
function categoryHTML(c={label:'',definition:'',examples:[]}) {
 return `<div class="category"><div class="category-head"><strong>Kategorie</strong><button type="button" data-action="remove-category">Entfernen</button></div>${input('Label','cat-label',c.label,'text','required')}${area('Definition','cat-definition',c.definition)}${area('Few-Shot-Beispiele','cat-examples',c.examples.join('\n---\n'),'Mehrere Beispiele mit einer eigenen Zeile --- trennen. Jedes Beispiel erhält nur dieses Label.')}</div>`;
}
function taskEditor(id) {
 const existing=state.tasks.find(t=>t.id===id);
 const t=existing?.spec||{name:'',description:'',instructions:'Klassifiziere den Text ausschließlich anhand der folgenden Kategorien.',mode:'single',categories:[{label:'FOR',definition:'Der Text befürwortet den untersuchten Gegenstand.',examples:[]},{label:'AGAINST',definition:'Der Text lehnt den untersuchten Gegenstand ab.',examples:[]},{label:'NO',definition:'Keine eindeutige Position zum untersuchten Gegenstand erkennbar.',examples:[]}],examples:[],ambiguity_rule:'Wenn keine eindeutige Position erkennbar ist, verwende NO.',allow_empty:false,rationale:false};
 openEditor(existing?'Task bearbeiten':'Task erstellen',`${input('Name','name',t.name,'text','required')}${area('Beschreibung','description',t.description)}<div class="grid">${select('Klassifikationsmodus','mode',option('single','Single-Label (Multi-class)',t.mode)+option('multi','Multi-Label',t.mode))}<div><label><input type="checkbox" name="rationale" ${t.rationale?'checked':''}>Begründung anfordern</label><label><input type="checkbox" name="evidence" ${t.evidence?'checked':''}>Wortgetreue Textbelege extrahieren</label><label><input type="checkbox" name="allow_empty" ${t.allow_empty?'checked':''}>Leere Auswahl erlauben (Multi-Label)</label></div></div>${area('Allgemeine Kodieranweisungen','instructions',t.instructions)}${area('Umgang mit unklaren Fällen','ambiguity_rule',t.ambiguity_rule)}<div class="section-title"><h3>Kategorien</h3><button type="button" data-action="add-category">+ Kategorie</button></div><div id="categories">${t.categories.map(categoryHTML).join('')}</div><details><summary>Mehrfach gelabelte Beispiele und Output-Schema</summary>${area('Zusätzliche Few-Shot-Beispiele (JSON)','examples',JSON.stringify(t.examples,null,2),'Liste von {"text":"…","labels":["FOR"],"rationale":"…"}. Für Multi-Label-Beispiele mehrere Labels verwenden.')}<p class="small">Output: JSON mit labels, optional rationale und evidence (Label + wortgetreues Zitat). Zeichenpositionen werden nach der Validierung ergänzt. Unbekannte Labels, doppelte Labels, zusätzliche Felder und falsche Kardinalität werden zurückgewiesen.</p><button type="button" data-action="prompt-preview">Prompt-Vorschau</button><pre id="prompt-preview" hidden></pre></details>`,'task',id);
 edit.revision=existing?.revision;
}
function readTask() {
 const form=$('#editor-form'), f=new FormData(form);
 return {name:f.get('name'),description:f.get('description'),instructions:f.get('instructions'),mode:f.get('mode'),ambiguity_rule:f.get('ambiguity_rule'),rationale:f.has('rationale'),evidence:f.has('evidence'),allow_empty:f.has('allow_empty'),examples:JSON.parse(f.get('examples')||'[]'),categories:[...document.querySelectorAll('.category')].map(c=>({label:c.querySelector('[name=cat-label]').value,definition:c.querySelector('[name=cat-definition]').value,examples:c.querySelector('[name=cat-examples]').value.split(/^---\s*$/m).map(s=>s.trim()).filter(Boolean)}))};
}
function profileEditor(id) {
 const p=state.profiles.find(p=>p.id===id)?.spec||{name:'Lokales vLLM',provider:'openai',base_url:'http://host.docker.internal:8000/v1',api_key_env:'',timeout:120};
 openEditor(id?'Verbindung bearbeiten':'LLM verbinden',`${input('Name','name',p.name,'text','required')}${select('API-Typ','provider',['openai','ollama','mock'].map(v=>option(v,{openai:'OpenAI-kompatibel / vLLM',ollama:'Ollama (native API)',mock:'Demo ohne LLM – immer erstes Label'}[v],p.provider)).join(''))}${input('Basis-URL','base_url',p.base_url,'url','required')}${input('Umgebungsvariable für API-Key (optional)','api_key_env',p.api_key_env)}${input('Timeout pro Anfrage in Sekunden','timeout',p.timeout,'number','min=1 max=1800 required')}<p class="muted">Die URL wird vom Backend und Worker aufgerufen. Bei direktem Python-Betrieb kann localhost verwendet werden; in Docker verweist host.docker.internal auf den Host.</p>`,'profile',id);
}
function datasetEditor() {
 openEditor('CSV hochladen',`<label class="file-input">Datei auswählen<input name="file" type="file" accept=".csv,.tsv,text/csv" required></label><div class="grid">${select('Trennzeichen','delimiter',option(',','Komma',',')+option(';','Semikolon')+option('\t','Tabulator')+option('|','Pipe'))}${select('Zeichenkodierung','encoding',['utf-8-sig','utf-8','cp1252','latin-1'].map(v=>option(v,v,'utf-8-sig')).join(''))}</div><p class="muted">Eine Kopfzeile mit eindeutigen Spaltennamen ist erforderlich. Welche Spalte klassifiziert wird, legst du im Job fest.</p><div class="upload-progress" hidden><span id="upload-label"></span><progress id="upload-progress" max=100 value=0></progress></div>`,'dataset');
}
async function jobEditor() {
 if(!state.tasks.length||!state.datasets.some(d=>d.status==='ready'&&d.total)||!state.profiles.length) {toast('Benötigt: mindestens ein Task, ein fertig importierter Datensatz und eine LLM-Verbindung.');return;}
 openEditor('Klassifikationsjob anlegen',`${input('Jobname','name','Neue Auswertung','text','required')}<div class="grid">${select('Task','task_id',state.tasks.map(t=>option(t.id,t.spec.name)).join(''))}${select('Datensatz','dataset_id',state.datasets.filter(d=>d.status==='ready'&&d.total).map(d=>option(d.id,d.name)).join(''))}${select('Textspalte','text_column','')}${select('LLM-Verbindung','profile_id',state.profiles.map(p=>option(p.id,p.spec.name)).join(''))}<label>Modell<input name="model" list="model-list" required placeholder="Modell laden oder ID eingeben"><datalist id="model-list"></datalist><small id="model-hint">Modellliste wird abgefragt …</small></label>${input('Parallele Anfragen','concurrency',4,'number','min=1 max=128 required')}${input('Wiederholungen nach Fehler','retries',2,'number','min=0 max=10 required')}${input('Temperatur','temperature',0,'number','min=0 max=2 step=0.1 required')}</div><details><summary>Modell- und Task-Parameter</summary><div class="grid">${outputToggles()}${input('Top-p','top_p',1,'number','min=0.01 max=1 step=0.01 required')}${input('Maximale Output-Tokens','max_tokens',256,'number','min=16 max=32768 required')}${input('Seed (optional)','seed','','number')}${select('Strukturiertes Ausgabeformat','structured_output',option('json_schema','JSON Schema','json_schema')+option('json_object','JSON-Objekt')+option('none','Nur Prompt-Instruktion'))}${input('Beispiele je Kategorie','examples_per_category',3,'number','min=0 max=100 required')}${input('Maximale Textlänge (Zeichen)','max_text_chars',30000,'number','min=1 max=1000000 required')}${select('Überlange Texte','overlong',option('error','Als Fehler markieren','error')+option('truncate','Explizit abschneiden'))}</div>${area('Weitere API-Parameter (JSON)','extra_body','{}','Beispiel für unterstützte vLLM-Modelle: {"chat_template_kwargs":{"enable_thinking":false}}. Kompatibilität hängt vom Server ab.')}</details><p class="muted">Task und Einstellungen werden unveränderlich mit dem Job gespeichert. Ein Worker bearbeitet Jobs nacheinander mit der gewählten Parallelität.</p>`,'job');
 updateColumns();await loadModels();
}
function updateColumns() {
 const d=state.datasets.find(d=>d.id===$('[name=dataset_id]').value);$('[name=text_column]').innerHTML=(d?.columns||[]).map(c=>option(c,c,c==='text'?'text':undefined)).join('');
}
async function loadModels() {
 const id=$('[name=profile_id]').value;
 try {const {models}=await api('/profiles/'+id+'/models');if(!$('#model-list') || $('[name=profile_id]').value!==id)return;$('#model-list').innerHTML=models.map(m=>option(m,m)).join('');$('[name=model]').value=models[0]||'';$('#model-hint').textContent=models.length+' Modelle verfügbar; eigene ID möglich.';}catch(e){if($('#model-hint'))$('#model-hint').textContent=e.message+' Modell-ID kann manuell eingegeben werden.';}
}
async function submit(event) {
 event.preventDefault();const button=$('#editor-form button[type=submit]');button.disabled=true;$('#form-error').textContent='';
 try {
  const f=new FormData($('#editor-form'));
  if(edit.kind==='gold')await submitGold(f);
  if(edit.kind==='evaluation')await submitEvaluation(f);
  if(edit.kind==='task') await api('/tasks'+(edit.id?'/'+edit.id+'?revision='+edit.revision:''),{method:edit.id?'PUT':'POST',body:JSON.stringify(readTask())});
  if(edit.kind==='profile') await api('/profiles'+(edit.id?'/'+edit.id:''),{method:edit.id?'PUT':'POST',body:JSON.stringify({name:f.get('name'),provider:f.get('provider'),base_url:f.get('base_url'),api_key_env:f.get('api_key_env'),timeout:Number(f.get('timeout'))})});
  if(edit.kind==='dataset') await uploadFile(f);
  if(edit.kind==='job') {
   const query={};for(const k of ['concurrency','retries','temperature','top_p','max_tokens','examples_per_category','max_text_chars'])query[k]=Number(f.get(k));
   for(const k of ['model','structured_output','overlong'])query[k]=f.get(k);
   query.rationale=triState(f.get('rationale_override'));query.evidence=triState(f.get('evidence_override'));query.seed=f.get('seed')===''?null:Number(f.get('seed'));query.extra_body=JSON.parse(f.get('extra_body'));
   await api('/jobs',{method:'POST',body:JSON.stringify({name:f.get('name'),task_id:f.get('task_id'),dataset_id:f.get('dataset_id'),profile_id:f.get('profile_id'),text_column:f.get('text_column'),query})});
  }
  $('#editor').close();toast(edit.kind==='dataset'?'Upload abgeschlossen. Import startet im Worker.':'Gespeichert.');await refresh();
 }catch(e){$('#form-error').textContent=e.message;}finally{button.disabled=false;}
}
function uploadFile(f) {
 return new Promise((resolve,reject)=>{
  const file=f.get('file'),params=new URLSearchParams({filename:file.name,delimiter:f.get('delimiter'),encoding:f.get('encoding')});
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/datasets?'+params);xhr.setRequestHeader('Content-Type','application/octet-stream');
  $('.upload-progress').hidden=false;
  xhr.upload.onprogress=e=>{if(e.lengthComputable){$('#upload-progress').value=e.loaded/e.total*100;$('#upload-label').textContent=Math.round(e.loaded/e.total*100)+' % übertragen';}};
  xhr.onerror=()=>reject(Error('Upload-Verbindung unterbrochen; erneut hochladen.'));
  xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300)resolve();else{let m=xhr.statusText;try{m=JSON.parse(xhr.responseText).detail}catch{}reject(Error(m));}};
  xhr.send(file);
 });
}
async function showJob(id,initial=true) {
 const job=await api('/jobs/'+id);selectedJob=id;
 if(initial){resultAfter=0;$('#detail-title').textContent=job.name;$('#detail-body').innerHTML='<div id="job-live"></div><div id="job-results" class="spaced"></div><details><summary>Job-Snapshot herunterladen / ansehen</summary><div class="actions"><button data-action="snapshot" data-id="'+id+'">Snapshot JSON ↓</button></div><pre>'+esc(JSON.stringify(job.snapshot,null,2))+'</pre></details>';$('#detail').showModal();}
 if(!$('#job-live'))return;
 const allowed=[];if(['queued','running'].includes(job.status))allowed.push(['pause','Pausieren']);if(job.status==='paused')allowed.push(['resume','Fortsetzen']);if(['queued','running','paused','pausing'].includes(job.status))allowed.push(['cancel','Abbrechen']);
 $('#job-live').innerHTML=`<div class="section-title">${badge(job.status)}<div class="actions">${allowed.map(([a,l])=>`<button data-action="control" data-control="${a}" data-id="${id}">${l}</button>`).join('')}</div></div><div class="stats"><div class="stat"><span>Verarbeitet</span><strong>${num(job.done)}</strong></div><div class="stat"><span>Gesamt</span><strong>${num(job.total)}</strong></div><div class="stat"><span>Fehler</span><strong>${num(job.failed)}</strong></div><div class="stat"><span>API-Versuche</span><strong>${num(job.metrics.requests)}</strong></div></div><progress value="${job.done}" max="${job.total}" aria-label="Jobfortschritt"></progress><p class="muted">${esc(job.model)} · Ø ${job.metrics.avg_seconds.toFixed(2)} s pro Text (inkl. Retries) · ${num(job.metrics.prompt_tokens)} Input- / ${num(job.metrics.completion_tokens)} Output-Tokens</p>${job.last_error?`<p class="error">Letzter Fehler: ${esc(job.last_error)}</p>`:''}<div class="actions">${['completed','completed_with_errors','cancelled'].includes(job.status)?['csv','jsonl','parquet'].map(fmt=>`<a class="button" href="/api/jobs/${id}/export?format=${fmt}">${fmt.toUpperCase()} ↓</a>`).join(''):'<span class="muted">Export nach Abschluss oder vollständig ausgeführtem Abbruch verfügbar.</span>'}</div>`;
 if(initial)await loadResults();
}
async function loadResults() {
 const rows=await api('/jobs/'+selectedJob+'/results?after='+resultAfter);
 $('#job-results').innerHTML=`<div class="section-title"><h3>Ergebnisse</h3><div class="actions"><button data-action="results-first">Anfang / Aktualisieren</button>${rows.length?`<button data-action="results-next" data-after="${rows.at(-1).row_no}">Weiter</button>`:''}</div></div>`+(rows.length?`<div class="table-wrap"><table><thead><tr><th>Zeile</th><th>Originaldaten</th><th>Labels</th><th>Status / Begründung</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.row_no}</td><td class="result-text">${esc(JSON.stringify(r.source).slice(0,650))}</td><td>${r.labels.map(esc).join(', ')||'—'}</td><td class="result-text">${esc(r.error||r.rationale||r.status)}<details><summary>Textbelege / Thinking / Versuche</summary><pre>${esc(JSON.stringify({evidence:r.evidence,thinking:r.thinking,attempt_outputs:r.attempt_outputs},null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">Hier liegen noch keine weiteren Ergebnisse vor.</p>');
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
  if(a==='delete-task'&&confirm('Task aus der Bibliothek löschen? Bestehende Job-Snapshots bleiben erhalten.')){await api('/tasks/'+id,{method:'DELETE'});await refresh();}
  if(a==='test-profile'){const r=await api('/profiles/'+id+'/models');toast(r.models.join(', ')||'Keine Modelle verfügbar.');}
  if(a==='job-detail'){selectedEvaluation=null;await showJob(id);}
  if(a==='control'){if(el.dataset.control==='cancel'&&!confirm('Job abbrechen? Bereits verarbeitete Ergebnisse bleiben erhalten.'))return;await api('/jobs/'+id+'/'+el.dataset.control,{method:'POST'});await refresh();}
  if(a==='results-next'){resultAfter=Number(el.dataset.after);await loadResults();}if(a==='results-first'){resultAfter=0;await loadResults();}
  if(a==='snapshot')download('textlab-job-'+id+'.json',(await api('/jobs/'+id)).snapshot);
  if(a==='dataset-preview'){selectedJob=null;const r=await api('/datasets/'+id+'/preview');$('#detail-title').textContent='Datensatz-Vorschau · erste 10 Zeilen';$('#detail-body').innerHTML='<pre>'+esc(JSON.stringify(r,null,2))+'</pre>';$('#detail').showModal();}
 }catch(e){if($('#editor').open)$('#form-error').textContent=e.message;else toast(e.message);}
}
$('#primary').onclick=()=>({jobs:jobEditor,tasks:taskEditor,datasets:datasetEditor,profiles:profileEditor,evaluations:evaluationEditor,gold:goldEditor}[page])();
$('#editor-form').addEventListener('submit',submit);document.addEventListener('click',action);
$('#editor-form').addEventListener('change',e=>{if(e.target.name==='dataset_id'){if(edit.kind==='gold')updateGoldColumns();else updateColumns();}if(e.target.name==='profile_id')loadModels();});
$('#detail').addEventListener('close',()=>selectedJob=null);
window.addEventListener('hashchange',render);
refresh().catch(e=>toast(e.message));setInterval(()=>{if(!document.hidden)refresh().catch(e=>toast(e.message));},3000);
