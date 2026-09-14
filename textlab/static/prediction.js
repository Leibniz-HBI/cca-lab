'use strict';
let selectedPrediction=null;
Object.assign(statuses,{exporting:'Preparing exports',export_failed:'Export failed'});
function thinkingSelect(name,value='default',override=false){
 const levels=['default','off','on','minimal','low','medium','high','max'];
 return select('Thinking',name,(override?option('','Use task setting',value):'')+levels.map(v=>option(v,{default:'Server default',off:'Disabled',on:'Enabled',minimal:'Minimal',low:'Low',medium:'Medium',high:'High',max:'Maximum'}[v],value)).join(''))+'<p class="small">Available thinking controls depend on the model and connection. Unsupported levels may be rejected by the server. Returned thinking text is always stored.</p>';
}
function runtimeTable(runs){
 return `<h3>Runtime comparison</h3><p class="small">Active time includes requests, retries and batch processing; excludes queue time and pauses. Elapsed time includes pauses after the first start. Throughput uses all processed documents, independent of scoring scope. Older or interrupted timing measurements appear as n/a.</p><div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Active seconds</th><th>Elapsed seconds</th><th>Documents/s</th><th>Successful documents/s</th><th>Mean seconds/document</th><th>Output tokens/s</th></tr></thead><tbody>${runs.map(r=>`<tr><td>${esc(r.variant||r.task_name||r.name)}</td>${['active_seconds','elapsed_seconds','documents_per_second','successful_documents_per_second','mean_document_seconds','completion_tokens_per_second'].map(k=>`<td>${metricNumber(r.runtime?.[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
async function predictionEditor(){await jobEditor(true);}
function renderPredictions(){
 const list=state.predictions||[];
 $('#view').innerHTML=`<div class="notice">Classify a dataset with one or more tasks. Each task keeps its own labels and settings. Results are saved on disk as CSV, JSON, JSONL and Parquet, with a configuration manifest.</div><div class="stats"><div class="stat"><span>Prediction batches</span><strong>${num(list.length)}</strong></div><div class="stat"><span>Task runs</span><strong>${num(list.reduce((n,p)=>n+p.runs.length,0))}</strong></div><div class="stat"><span>Processed classifications</span><strong>${num(list.reduce((n,p)=>n+p.done,0))}</strong></div><div class="stat"><span>Exports ready</span><strong>${num(list.filter(p=>p.artifact_status==='ready').length)}</strong></div></div>`+(list.length?`<div class="panel table-wrap"><table><thead><tr><th>Prediction</th><th>Tasks</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>${list.map(p=>`<tr><td><strong>${esc(p.name)}</strong><span class="muted">${esc(state.datasets.find(d=>d.id===p.dataset_id)?.name)}</span></td><td>${p.runs.map(r=>`<span class="chip">${esc(r.task_name)}</span>`).join(' ')}</td><td>${badge(p.status)}</td><td class="progress">${num(p.done)} / ${num(p.total)}<progress value="${p.done}" max="${p.total}"></progress></td><td><button data-action="prediction-detail" data-id="${p.id}">Open</button> <button class="danger" data-action="remove-prediction" data-id="${p.id}">Delete</button></td></tr>`).join('')}</tbody></table></div>`:empty('Predict labels across multiple tasks','Select an imported dataset, choose tasks and configure your model.','new-prediction','Create prediction'));
}
async function showPrediction(id,initial=true){
 const p=await api('/predictions/'+id);
 if(initial){selectedJob=null;selectedEvaluation=null;selectedPrediction=id;$('#detail-title').textContent=p.name;$('#detail').showModal();}
 if(selectedPrediction!==id)return;
 const actions=[];
 if(p.runs.some(r=>['running','queued'].includes(r.status)))actions.push(['pause','Pause all']);
 if(p.runs.some(r=>r.status==='paused'))actions.push(['resume','Resume paused']);
 if(p.runs.some(r=>['running','queued','paused','pausing'].includes(r.status)))actions.push(['cancel','Cancel']);
 if(p.artifact_status==='failed')actions.push(['retry-export','Retry exports']);
 $('#detail-body').innerHTML=`<div class="section-title">${badge(p.status)}<div class="actions">${actions.map(([a,l])=>`<button data-action="prediction-control" data-control="${a}" data-id="${id}">${l}</button>`).join('')}</div></div><progress value="${p.done}" max="${p.total}"></progress><p>${num(p.done)} / ${num(p.total)} classifications · ${num(p.failed)} failed</p>${p.artifact_error?`<p class="error">${esc(p.artifact_error)}</p>`:''}<h3>Saved results</h3><p class="small">One row per source document and task. Includes original columns, labels, rationale, evidence, returned thinking, attempt logs and status. Cancelled runs include unprocessed rows.</p><div class="actions">${p.artifacts.length?p.artifacts.map(a=>`<a class="button" href="/api/predictions/${id}/download/${a.format}">${a.format.toUpperCase()} ↓ <small>${(a.bytes/1024/1024).toFixed(2)} MiB</small></a>`).join(''):'<span class="muted">Exports are generated after all task runs finish or are cancelled.</span>'}</div><h3>Task runs</h3><div class="table-wrap"><table><thead><tr><th>Task</th><th>Model</th><th>Thinking</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>${p.runs.map(r=>`<tr><td>${esc(r.task_name)}</td><td>${esc(r.snapshot.query.model)}</td><td>${esc(r.snapshot.task.thinking||'default')}</td><td>${badge(r.status)}</td><td>${num(r.done)} / ${num(r.total)}</td><td><button data-action="job-detail" data-id="${r.id}">View results</button></td></tr>`).join('')}</tbody></table></div>${runtimeTable(p.runs)}`;
}
async function removeResource(kind,id){
 let path,message;
 if(kind==='profile'){path='/profiles/'+id;message='Delete this LLM connection? Existing jobs keep their connection snapshots.';}
 if(kind==='csv'){path='/datasets/'+id+'/csv';message='Delete the original CSV file? Imported records, gold datasets and results remain available.';}
 if(kind==='evaluation'){path='/evaluations/'+id;message='Delete this evaluation, its task runs, predictions and report? This cannot be undone.';}
 if(kind==='prediction'){path='/predictions/'+id;message='Delete this prediction batch, its task runs and all saved exports? This cannot be undone.';}
 if(kind==='gold'){
  const refs=(state.evaluations||[]).filter(e=>e.gold_id===id);
  path='/gold-sets/'+id+'?cascade=true';message=`Delete this gold registration and ${refs.length} dependent evaluations${refs.length?': '+refs.map(e=>e.name).join(', '):''}? Their runs and results will also be deleted. The imported dataset stays available.`;
 }
 if(kind==='dataset'){
  const refs=await api('/datasets/'+id+'/dependencies');
  path='/datasets/'+id+'?cascade=true';message=`Delete this dataset and its original CSV, ${refs.jobs.length} jobs, ${refs.gold_sets.length} gold registrations, ${refs.evaluations.length} evaluations and ${refs.predictions.length} prediction batches? All associated results and saved exports will be deleted. This cannot be undone.`;
 }
 if(!path||!confirm(message))return;
 await api(path,{method:'DELETE'});toast('Deleted.');await refresh();
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-action]');if(!el)return;
 try{
  const a=el.dataset.action,id=el.dataset.id;
  if(a==='new-prediction')await predictionEditor();
  if(a==='prediction-detail')await showPrediction(id);
  if(a==='prediction-control'){if(el.dataset.control==='cancel'&&!confirm('Cancel remaining task runs? Completed results will be exported.'))return;await api('/predictions/'+id+'/'+el.dataset.control,{method:'POST'});await refresh();}
  if(a.startsWith('remove-')&&['profile','csv','dataset','gold','evaluation','prediction'].includes(a.slice(7)))await removeResource(a.slice(7),id);
 }catch(e){toast(e.message);}
});
$('#detail').addEventListener('close',()=>selectedPrediction=null);
