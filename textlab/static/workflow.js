'use strict';
let resultKind='all';
const workflowSteps=[
 ['tasks','Define tasks','Design the coding instrument: categories, definitions, examples and decision rules.'],
 ['data','Prepare data','Import your corpus and register gold labels for an independent evaluation.'],
 ['evaluations','Evaluate & refine','Compare models, settings and seeds. Inspect errors and revise your coding instrument.'],
 ['prediction','Run predictions','Apply your chosen task and model configuration to the full corpus.'],
 ['results','Analyze & export','Revisit completed experiments and download tables, figures and classification results.']
];
function renderWorkflowContext(){
 const current=['datasets','gold'].includes(page)?'data':page,index=workflowSteps.findIndex(s=>s[0]===current);
 document.querySelectorAll('nav a').forEach(a=>{const active=a.hash==='#'+current;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
 const active=state.jobs.filter(j=>['running','queued','pausing','cancelling'].includes(j.status)).length;
 $('#job-count').textContent=num(active);$('#job-count').title='Active or queued jobs in the latest 500 runs';
 document.querySelector('.eyebrow').textContent=index>=0?`STEP ${index+1} OF 5 · RESEARCH WORKFLOW`:page==='profiles'?'CONFIGURATION':'WORKSPACE ACTIVITY';
 const next=workflowSteps[index+1],prev=workflowSteps[index-1];
 $('#workflow-context').innerHTML=index<0?'':`<section class="workflow-guide"><p>${workflowSteps[index][2]}</p><div class="actions">${prev?`<a class="button" href="#${prev[0]}">← ${prev[1]}</a>`:''}${next?`<a class="button" href="#${next[0]}">${next[1]} →</a>`:''}</div></section>`;
 if(current==='data')$('#workflow-context').insertAdjacentHTML('beforeend',`<nav class="data-tabs" aria-label="Prepare data sections"><a href="#data" ${page==='datasets'?'aria-current="page" class="selected"':''}>Corpus & CSV files <small>${state.datasets.length}</small></a><a href="#gold" ${page==='gold'?'aria-current="page" class="selected"':''}>Gold datasets <small>${state.goldSets?.length||0}</small></a></nav>`);
}
function renderResults(){
 const terminal=['completed','completed_with_errors','cancelled'];
 const evaluations=(state.evaluations||[]).filter(e=>e.report_ready).map(e=>({...e,kind:'evaluation',caption:e.task_snapshot.task.name,action:'evaluation-detail'}));
 const predictions=(state.predictions||[]).filter(p=>p.artifact_status==='ready').map(p=>({...p,kind:'prediction',caption:`${p.runs.length} task / seed runs`,action:'prediction-detail'}));
 const jobs=state.jobs.filter(j=>!j.evaluation_id&&!j.prediction_id&&terminal.includes(j.status)).map(j=>({...j,kind:'job',caption:j.task_name,action:'job-detail'}));
 const all=[...evaluations,...predictions,...jobs].sort((a,b)=>b.created-a.created),rows=all.filter(r=>resultKind==='all'||r.kind===resultKind);
 $('#view').innerHTML=`<div class="stats">${[['Completed outputs',all.length],['Evaluations',evaluations.length],['Prediction batches',predictions.length],['Individual jobs',jobs.length]].map(([k,v])=>`<div class="stat"><span>${k}</span><strong>${num(v)}</strong></div>`).join('')}</div><div class="actions result-filters">${[['all','All results'],['evaluation','Evaluations'],['prediction','Predictions'],['job','Individual jobs']].map(([k,l])=>`<button data-action="workflow-filter" data-kind="${k}" aria-pressed="${resultKind===k}" class="${resultKind===k?'primary':''}">${l}</button>`).join('')}</div>`+(rows.length?`<div class="panel table-wrap"><table><thead><tr><th>Experiment</th><th>Type</th><th>Status</th><th>Results & downloads</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong><span class="muted">${esc(r.caption)}</span></td><td>${esc(r.kind)}</td><td>${badge(r.status)}</td><td><div class="actions"><button data-action="${r.action}" data-id="${r.id}">${r.kind==='evaluation'?'Tables & figures':'Inspect results'}</button>${r.kind==='evaluation'?`<a class="button" href="/api/evaluations/${r.id}/report?format=zip">Report ZIP ↓</a><a class="button" href="/api/evaluations/${r.id}/report?format=csv">Metrics CSV ↓</a>`:r.kind==='prediction'?r.artifacts.filter(a=>a.format!=='manifest').map(a=>`<a class="button" href="/api/predictions/${r.id}/download/${a.format}">${a.format.replaceAll('_',' ').toUpperCase()} ↓</a>`).join(''):['csv','jsonl','parquet'].map(f=>`<a class="button" href="/api/jobs/${r.id}/export?format=${f}">${f.toUpperCase()} ↓</a>`).join('')}</div></td></tr>`).join('')}</tbody></table></div>`:`<div class="panel empty"><h2>No completed outputs yet</h2><p>Finished evaluations and predictions appear here once their reports or exports are ready.</p><a class="button" href="#jobs">Open jobs & monitoring</a></div>`)+`<p class="small muted">Overview of the latest 500 items per type. Individual runs belonging to an evaluation or prediction remain inside that experiment.</p>`;
}
function closeWorkflowDetail(){if($('#detail').open)$('#detail').close();selectedJob=null;selectedEvaluation=null;selectedPrediction=null;}
async function reuseEvaluation(jobId){
 const source=await api('/jobs/'+jobId),s=source.snapshot;
 closeWorkflowDetail();location.hash='prediction';await jobEditor(true,source);
 if(!$('#editor').open||edit?.kind!=='prediction')return;
 edit.source=source;
 $('#dialog-title').textContent='Predict with evaluated configuration';
 const task=$('[name=task_ids]');task.innerHTML=option(s.task_id,s.task.name+' · evaluated revision '+s.task_revision,s.task_id);task.disabled=true;
 const profile=$('[name=profile_id]');profile.innerHTML=option('snapshot',s.profile.name+' · saved connection','snapshot');profile.disabled=true;
 $('[name=name]').value=(s.task.name+' · prediction').slice(0,200);
 for(const [k,v] of Object.entries(s.query)){
  const field=$(`[name=${k}]`);if(field&&typeof v!=='object')field.value=v??'';
 }
 for(const k of ['rationale','evidence','thinking'])$(`[name=${k}_override]`).value=s.query[k]===null||s.query[k]===undefined?'':String(s.query[k]);
 $('[name=extra_body]').value=JSON.stringify(s.query.extra_body||{},null,2);$('[name=seeds]').value=s.query.seed??'';
 $('#model-hint').textContent='Copied from the selected evaluation run. You can adjust model parameters before starting.';
 const corpus=state.datasets.find(d=>d.status==='ready'&&d.total&&d.id!==source.dataset_id);if(corpus)$('[name=dataset_id]').value=corpus.id;
 updateColumns();if([...$('[name=text_column]').options].some(o=>o.value===s.text_column))$('[name=text_column]').value=s.text_column;
 $('#editor-body').insertAdjacentHTML('afterbegin',`<div class="notice">Based on <strong>${esc(source.name)}</strong>. Task revision ${s.task_revision} and the evaluated connection are preserved as snapshots. Choose the target corpus and review parameters before starting.</div>`);
}
async function reviseEvaluatedTask(id){
 const e=await api('/evaluations/'+id),s=e.task_snapshot,current=state.tasks.find(t=>t.id===s.task_id);
 closeWorkflowDetail();location.hash='tasks';
 if(current&&current.revision===s.task_revision)taskEditor(current.id);
 else taskEditor(null,{...s.task,name:(s.task.name+' (revised copy)').slice(0,200)});
 $('#editor-body').insertAdjacentHTML('afterbegin',`<div class="notice">Revising the coding instrument from evaluated revision ${s.task_revision}. ${current?.revision===s.task_revision?'Saving creates a new library revision.':'Saving creates a separate task from the evaluated snapshot.'} Existing evaluation snapshots and results remain unchanged.</div>`);
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-action]');if(!el)return;
 try{
  const a=el.dataset.action,id=el.dataset.id;
  if(a==='workflow-filter'){resultKind=el.dataset.kind;renderResults();}
  if(a==='workflow-evaluate-task'){location.hash='evaluations';await evaluationEditor(undefined,id);}
  if(a==='workflow-use-dataset'){location.hash='prediction';await predictionEditor();if($('#editor').open&&edit.kind==='prediction'){$('[name=dataset_id]').value=id;updateColumns();}}
  if(a==='workflow-reuse')await reuseEvaluation(id);
  if(a==='workflow-revise-task')await reviseEvaluatedTask(id);
 }catch(error){toast(error.message);}
});
