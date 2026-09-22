'use strict';
let selectedEvaluation=null, evaluationReport=null, evaluationScope='common', evaluationAfter=0;
const metricNumber=v=>v===null||v===undefined?'n/a':Number(v).toLocaleString('en-US',{minimumFractionDigits:3,maximumFractionDigits:3});
const triState=v=>v==='true'?true:v==='false'?false:null;
function renderGold(){
 const gold=state.goldSets||[];
 $('#view').innerHTML=`<div class="notice"><strong>Register a gold standard.</strong> Upload CSV, wait for import, then map document ID, text and gold label columns. Multi-label cells are split using the selected separator.<div class="actions spaced"><button data-action="new-dataset">Upload CSV</button></div></div>`+(gold.length?`<div class="cards">${gold.map(g=>`<article class="card"><span class="muted">${g.spec.mode==='multi'?'MULTI-LABEL':'SINGLE-LABEL'} · ${num(g.total)} DOCUMENTS</span><h2>${esc(g.spec.name)}</h2><p>ID: ${esc(g.spec.doc_id_column)} · Text: ${esc(g.spec.text_column)} · Gold: ${esc(g.spec.gold_column)}</p><div class="chips">${Object.entries(g.label_counts).map(([k,n])=>`<span class="chip">${esc(k)} · ${num(n)}</span>`).join('')}</div><div class="actions"><button data-action="gold-edit" data-id="${g.id}">Edit</button><button data-action="gold-preview" data-id="${g.id}">Gold preview</button><button data-action="new-evaluation" data-gold="${g.id}">Evaluate</button><button class="danger" data-action="remove-gold" data-id="${g.id}">Delete</button></div></article>`).join('')}</div>`:'<p class="muted">No gold dataset registered yet.</p>')+`<div class="panel spaced"><div class="panel-head"><h2>CSV files available for registration</h2></div><div class="table-wrap"><table><thead><tr><th>File</th><th>Status</th><th>Rows</th><th></th></tr></thead><tbody>${state.datasets.map(d=>`<tr><td>${esc(d.name)}</td><td>${badge(d.status)}</td><td>${num(d.total)}</td><td>${d.status==='ready'?`<button data-action="gold-register" data-id="${d.id}">Map columns</button>`:esc(d.error||'')}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function goldEditor(datasetId,goldId=null){
 const saved=state.goldSets.find(g=>g.id===goldId)?.spec;
 if(saved)datasetId=saved.dataset_id;
 const ready=state.datasets.filter(d=>d.status==='ready'&&d.total);
 if(!ready.length){toast('Upload a CSV and wait for import to complete first.');datasetEditor();return;}
 openEditor(saved?'Edit gold dataset':'Register gold dataset',`${input('Name','name','Gold standard','text','required')}${select('Imported CSV','dataset_id',ready.map(d=>option(d.id,d.name,datasetId)).join(''))}<div class="grid">${select('Document ID','doc_id_column','')}${select('Text','text_column','')}${select('Gold-Label','gold_column','')}${select('Context column (optional)','context_column','')}${select('Label mode','mode',option('single','Single-Label','single')+option('multi','Multi-Label'))}${input('Separator within gold cells','separator','|','text','required maxlength=16')}<label><input type="checkbox" name="allow_empty">Empty gold cell = no labels (multi-label only)</label></div><p class="muted">Example: FOR|SECURITY. The separator is a literal string, not a regular expression. Document IDs must be unique. If this registration is used by an evaluation, saving creates a revised registration and preserves the original for reproducibility.</p>`,'gold',goldId);
 updateGoldColumns();
 if(saved)for(const [key,value] of Object.entries(saved)){const field=$(`[name=${key}]`);if(field){if(field.type==='checkbox')field.checked=value;else field.value=value;}}
}
function updateGoldColumns(){
 const d=state.datasets.find(d=>d.id===$('[name=dataset_id]').value);
 $('[name=context_column]').innerHTML=option('','No context')+d.columns.map(c=>option(c,c)).join('');
 for(const [field,standard] of [['doc_id_column','doc_id'],['text_column','text'],['gold_column','gold_label']])$(`[name=${field}]`).innerHTML=d.columns.map(c=>option(c,c,standard)).join('');
}
async function submitGold(f){await api('/gold-sets'+(edit.id?'/'+edit.id:''),{method:edit.id?'PUT':'POST',body:JSON.stringify({name:f.get('name'),dataset_id:f.get('dataset_id'),doc_id_column:f.get('doc_id_column'),text_column:f.get('text_column'),gold_column:f.get('gold_column'),context_column:f.get('context_column')||null,mode:f.get('mode'),separator:f.get('separator'),allow_empty:f.has('allow_empty')})});}
function renderEvaluations(){
 const list=state.evaluations||[];
 $('#view').innerHTML=`<div class="stats"><div class="stat"><span>Evaluations</span><strong>${num(list.length)}</strong></div><div class="stat"><span>Gold datasets</span><strong>${num(state.goldSets?.length)}</strong></div><div class="stat"><span>Model configurations</span><strong>${num(list.reduce((n,e)=>n+e.runs.length,0))}</strong></div><div class="stat"><span>Reports available</span><strong>${num(list.filter(e=>e.report_ready).length)}</strong></div></div>`+(list.length?`<div class="panel"><div class="panel-head"><h2>Model comparisons</h2><span class="muted">Gold → Predictions → Metrics</span></div><div class="table-wrap"><table><thead><tr><th>Evaluation</th><th>Variants</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>${list.map(e=>`<tr><td><strong>${esc(e.name)}</strong><span class="muted">${esc(e.task_snapshot.task.codebook.title)}</span></td><td>${e.runs.length}</td><td>${badge(e.status)}</td><td class="progress">${num(e.done)} / ${num(e.total)}<progress value="${e.done}" max="${e.total}"></progress></td><td><button data-action="evaluation-detail" data-id="${e.id}">Compare</button> <button class="danger" data-action="remove-evaluation" data-id="${e.id}">Delete</button></td></tr>`).join('')}</tbody></table></div></div>`:empty('Compare models against gold labels','Select a task and a registered gold dataset. Compare models with different temperatures or other query parameters.','new-evaluation','Create evaluation'));
}
async function showEvaluation(id,initial=true){
 const session=initial?beginDetail('evaluation',id):detailSession;
 const e=await api('/evaluations/'+id);
 if(!currentDetail(session)||selectedEvaluation!==id)return;
 if(initial){selectedPrediction=null;selectedJob=null;selectedEvaluation=id;evaluationReport=null;evaluationScope='common';evaluationAfter=0;$('#detail-title').textContent=e.name;$('#detail-body').innerHTML='<div id="evaluation-live"></div><div id="evaluation-report" class="spaced"></div>';$('#detail').showModal();}
 if(!$('#evaluation-live')||selectedEvaluation!==id)return;
 const actions=[];if(e.runs.some(r=>['running','queued'].includes(r.status)))actions.push(['pause','Pause all']);if(e.runs.some(r=>r.status==='paused'))actions.push(['resume','Resume paused']);if(e.runs.some(r=>['running','queued','paused','pausing'].includes(r.status)))actions.push(['cancel','Cancel']);if(e.report_error)actions.push(['retry-report','Recalculate report']);
 $('#evaluation-live').innerHTML=`<div class="section-title">${badge(e.status)}<button data-action="workflow-revise-task" data-id="${id}">Revise task</button><div class="actions">${actions.map(([a,l])=>`<button data-action="evaluation-control" data-id="${id}" data-control="${a}">${l}</button>`).join('')}</div></div><progress value="${e.done}" max="${e.total}"></progress><p class="muted">${num(e.done)} / ${num(e.total)} classifications · ${num(e.failed)} Errors</p>${e.report_error?`<p class="error">${esc(e.report_error)}</p>`:''}<p class="small">Planned queries: ${num(e.query_count?.planned??e.total)} · Up to ${num(e.query_count?.maximum_attempts)} attempts including retries.</p><div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>${e.runs.map(r=>`<tr><td>${esc(r.name)}<div class="muted">${esc(r.model)} · T=${r.query.temperature}<br>${esc(r.connection.name)} · ${esc(r.connection.base_url)}</div></td><td>${badge(r.status)}</td><td>${num(r.done)} / ${num(r.total)}</td><td><button data-action="job-detail" data-id="${r.id}">Individual run</button>${['completed','completed_with_errors'].includes(r.status)?`<button data-action="workflow-reuse" data-id="${r.id}">Use configuration for prediction →</button>`:''}</td></tr>`).join('')}</tbody></table></div>`;
 if(e.report_ready&&!evaluationReport)await loadEvaluationReport();
}
async function loadEvaluationReport(){
 const session=detailSession,id=selectedEvaluation,scope=evaluationScope;
 const r=await api('/evaluations/'+id+'/report?scope='+scope);
 if(!currentDetail(session)||selectedEvaluation!==id||evaluationScope!==scope||!$('#evaluation-report'))return;
 evaluationReport=r;
 const kappa=r.mode==='multi'?'kappa_macro_ovr':'kappa',mcc=r.mode==='multi'?'mcc_macro_ovr':'mcc';
 $('#evaluation-report').innerHTML=`<h2>Compare quality and runtime</h2><div class="notice spaced">${esc(r.policies[evaluationScope])}<br>Coverage includes all ${num(r.gold.total)} gold documents. Coverage counts valid model responses. Fallback labels are scored as assigned output and counted separately. Unprocessed or unassigned records count as incorrect in Accuracy (all). Metrics without valid predictions appear as n/a.</div><div class="grid">${select('Scoring scope','eval_scope',option('common','Common assigned documents',evaluationScope)+option('valid','Assigned documents per run',evaluationScope))}${select('Average for precision / recall / F1','eval_average',['macro','micro','weighted',...(r.mode==='multi'?['samples']:[])].map(a=>option(a,a,'macro')).join(''))}</div><div id="evaluation-summary"></div><div class="actions spaced">${[['csv','Metrics CSV'],['class_csv','Per-class CSV'],['html','HTML report'],['json','Report JSON'],['zip','Report bundle ZIP']].map(([f,l])=>`<a class="button" href="/api/evaluations/${id}/report?scope=${evaluationScope}&format=${f}" target="_blank" rel="noopener">${l} ↓</a>`).join('')}<a class="button" href="/api/evaluations/${id}/export-predictions?format=csv">Gold + Predictions CSV ↓</a><a class="button" href="/api/evaluations/${id}/export-predictions?format=jsonl">Gold + Predictions JSONL ↓</a></div><details open><summary>Model comparison charts</summary>${select('Metric','eval_plot_metric',['accuracy','precision_macro','recall_macro','f1_macro','f1_micro','f1_weighted',kappa,mcc,'coverage','accuracy_all','hamming_loss','active_seconds','elapsed_seconds','documents_per_second','successful_documents_per_second','mean_document_seconds','completion_tokens_per_second'].map(m=>option(m,m,'f1_macro')).join(''))}<div id="evaluation-overview-chart"></div></details><details open><summary>Results by class</summary>${select('Class metric','eval_class_metric',['precision','recall','f1','accuracy','specificity','kappa','mcc'].map(m=>option(m,m,'f1')).join(''))}<div id="evaluation-class-table"></div><div id="evaluation-class-chart"></div></details><details><summary>Individual-run confusion matrices</summary>${select('Configuration','eval_confusion_run',r.runs.map(v=>option(v.job_id,v.variant)).join(''))}<div id="evaluation-confusion-chart"></div></details><details><summary>Gold labels and stored predictions</summary>${select('Configuration','eval_prediction_run',r.runs.map(v=>option(v.job_id,v.variant)).join(''))}<div class="actions"><button data-action="evaluation-predictions-first">Load / first page</button><button data-action="evaluation-predictions-next">Next 50</button></div><div id="evaluation-predictions" class="spaced"></div></details><details><summary>Scoring conventions</summary>${Object.entries(r.policies).map(([k,v])=>`<p class="small"><strong>${esc(k)}:</strong> ${esc(v)}</p>`).join('')}</details>`;
 renderUncertaintyReport(r,id);renderEvaluationSummary();renderEvaluationClasses();renderEvaluationCharts();$('#evaluation-summary').insertAdjacentHTML('afterend',runtimeTable(r.groups));
}
function renderEvaluationSummary(){
 const r=evaluationReport,avg=$('[name=eval_average]').value,kappa=r.mode==='multi'?'kappa_macro_ovr':'kappa',mcc=r.mode==='multi'?'mcc_macro_ovr':'mcc';
 $('#evaluation-summary').innerHTML=`<p class="small">${r.groups.some(g=>g.expected_runs>1)?'Mean ± sample SD across completed seed runs. Undefined metrics are excluded per metric.':'One run per configuration; values are reported without standard deviations.'} Cancelled runs are excluded from aggregates. Individual runs remain available below and in the report bundle.</p><div class="table-wrap"><table data-sort-key="summary"><thead><tr><th>Configuration / seeds</th><th>Completed runs</th><th>Mean N</th><th>Coverage</th><th>Fallbacks</th><th>Accuracy</th><th>Precision ${avg}</th><th>Recall ${avg}</th><th>F1 ${avg}</th><th>${esc(kappa)}</th><th>${esc(mcc)}</th><th>Accuracy (all)</th></tr></thead><tbody>${(r.groups).map(v=>`<tr><td>${esc(v.variant)}<span class="muted">${esc((v.seeds||[]).join(', '))}</span></td><td>${v.repeat_n??1} / ${v.expected_runs??1}</td><td>${meanSD(v,'n')}</td><td>${meanSD(v,'coverage')}</td><td>${meanSD(v,'fallback_n')}</td>${['accuracy','precision_'+avg,'recall_'+avg,'f1_'+avg,kappa,mcc].map(k=>`<td>${meanSD(v,k,'summary')}</td>`).join('')}<td>${meanSD(v,'accuracy_all')}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderEvaluationClasses(){
 const r=evaluationReport,metric=$('[name=eval_class_metric]').value,runs=r.groups;
 $('#evaluation-class-table').innerHTML=`<div class="table-wrap"><table data-sort-key="class"><thead><tr><th>Class</th>${runs.map(v=>`<th>${esc(v.variant)}<br>${esc(metric)}${v.expected_runs>1?' mean ± SD':''} / gold support</th>`).join('')}</tr></thead><tbody>${r.labels.map(label=>`<tr><td>${esc(label)}</td>${runs.map(v=>{const c=v.per_class.find(c=>c.label===label);return `<td>${meanSD(c,metric,null,v.expected_runs)} <span class="muted">/ ${num(c.support)}</span></td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function chartBlock(kind,metric,job){const url=`/api/evaluations/${selectedEvaluation}/chart?scope=${evaluationScope}&kind=${kind}&metric=${encodeURIComponent(metric)}${job?'&job_id='+job:''}`;return `<div class="chart-frame"><img src="${url}&format=svg" alt="${kind==='classes'?'Class comparison':kind==='confusion'?'Confusion matrix':'Model comparison'}"></div><div class="actions"><a class="button" href="${url}&format=svg" download>SVG ↓</a><a class="button" href="${url}&format=png" download>PNG ↓</a></div>`;}
function renderEvaluationCharts(){
 $('#evaluation-overview-chart').innerHTML=chartBlock('overview',$('[name=eval_plot_metric]').value);
 $('#evaluation-class-chart').innerHTML=chartBlock('classes',$('[name=eval_class_metric]').value);
 $('#evaluation-confusion-chart').innerHTML=chartBlock('confusion','f1',$('[name=eval_confusion_run]').value);
}
async function loadEvaluationPredictions(){
 const session=detailSession,id=selectedEvaluation,job=$('[name=eval_prediction_run]').value,after=evaluationAfter;
 const rows=await api(`/evaluations/${id}/predictions?job_id=${job}&after=${after}`);
 if(!currentDetail(session)||selectedEvaluation!==id||$('[name=eval_prediction_run]')?.value!==job||evaluationAfter!==after)return;
 $('#evaluation-predictions').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>Document</th><th>Gold</th><th>Prediction</th><th>Details</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.doc_id)}<p class="result-text small">${esc(row.text.slice(0,500))}</p></td><td>${esc(row.gold_labels.join(', ')||'∅')}</td><td>${row.predicted_labels===null?'No valid prediction':esc(row.predicted_labels.join(', ')||'∅')}<p class="muted">${row.exact_match?'Exact Match':esc(row.status)}</p></td><td><details><summary>Confidence / alternatives / rationale / evidence / thinking</summary><pre>${esc(JSON.stringify({evidence:row.evidence,candidate_interpretations:row.candidate_interpretations,rationale:row.rationale,labels:row.predicted_labels,self_reported_confidence:row.self_reported_confidence,alternative_interpretations:row.alternative_interpretations,thinking:row.thinking,error:row.error,attempt_outputs:row.attempt_outputs},null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No more documents.</p>';
 if(rows.length)evaluationAfter=rows.at(-1).row_no;
}
async function evaluationAction(event){
 const el=event.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,id=el.dataset.id;
 try{
 if(a==='gold-register')goldEditor(id);
 if(a==='gold-edit')goldEditor(null,id);
 if(a==='gold-preview'){const session=beginDetail('preview',id);const r=await api('/gold-sets/'+id+'/preview');if(!currentDetail(session))return;$('#detail-title').textContent='Gold standard · Preview';$('#detail-body').innerHTML='<pre>'+esc(JSON.stringify(r,null,2))+'</pre>';$('#detail').showModal();}
 if(a==='new-evaluation')await evaluationEditor(el.dataset.gold);

 if(a==='evaluation-detail')await showEvaluation(id);
 if(a==='evaluation-control'){if(el.dataset.control==='cancel'&&!confirm('Cancel all active variants?'))return;await api('/evaluations/'+id+'/'+el.dataset.control,{method:'POST'});await refresh();}
 if(a==='evaluation-predictions-first'){evaluationAfter=0;await loadEvaluationPredictions();}if(a==='evaluation-predictions-next')await loadEvaluationPredictions();
 }catch(e){if($('#editor').open)$('#form-error').textContent=e.message;else toast(e.message);}
}
document.addEventListener('click',evaluationAction);
document.addEventListener('change',async e=>{try{

 if(e.target.name==='eval_scope'){evaluationScope=e.target.value;await loadEvaluationReport();}
 if(e.target.name==='eval_average')renderEvaluationSummary();
 if(e.target.name==='eval_class_metric'){renderEvaluationClasses();$('#evaluation-class-chart').innerHTML=chartBlock('classes',e.target.value);}
 if(e.target.name==='eval_plot_metric')$('#evaluation-overview-chart').innerHTML=chartBlock('overview',e.target.value);
 if(e.target.name==='eval_confusion_run')$('#evaluation-confusion-chart').innerHTML=chartBlock('confusion','f1',e.target.value);
 if(e.target.name==='eval_prediction_run'){evaluationAfter=0;await loadEvaluationPredictions();}
 }catch(error){toast(error.message);}});
$('#detail').addEventListener('close',()=>{selectedEvaluation=null;evaluationReport=null;});
