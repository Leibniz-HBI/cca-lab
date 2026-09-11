'use strict';
let selectedEvaluation=null, evaluationReport=null, evaluationScope='common', evaluationAfter=0;
const metricNumber=v=>v===null||v===undefined?'n/a':Number(v).toLocaleString('de-DE',{minimumFractionDigits:3,maximumFractionDigits:3});
const triState=v=>v==='true'?true:v==='false'?false:null;
function outputToggles(){return select('Begründung','rationale_override',option('','Task-Einstellung übernehmen','')+option('true','An')+option('false','Aus'))+select('Textbelege','evidence_override',option('','Task-Einstellung übernehmen','')+option('true','An')+option('false','Aus'));}
function renderGold(){
 const gold=state.goldSets||[];
 $('#view').innerHTML=`<div class="notice"><strong>Gold-Standard registrieren.</strong> CSV hochladen, auf den Import warten und anschließend die Spalten für Dokument-ID, Text und Gold-Label zuordnen. Multi-Label-Zellen werden am gewählten Trennzeichen aufgeteilt.<div class="actions spaced"><button data-action="new-dataset">CSV hochladen</button></div></div>`+(gold.length?`<div class="cards">${gold.map(g=>`<article class="card"><span class="muted">${g.spec.mode==='multi'?'MULTI-LABEL':'SINGLE-LABEL'} · ${num(g.total)} DOKUMENTE</span><h2>${esc(g.spec.name)}</h2><p>ID: ${esc(g.spec.doc_id_column)} · Text: ${esc(g.spec.text_column)} · Gold: ${esc(g.spec.gold_column)}</p><div class="chips">${Object.entries(g.label_counts).map(([k,n])=>`<span class="chip">${esc(k)} · ${num(n)}</span>`).join('')}</div><div class="actions"><button data-action="gold-preview" data-id="${g.id}">Gold-Vorschau</button><button data-action="new-evaluation" data-gold="${g.id}">Evaluieren</button></div></article>`).join('')}</div>`:'<p class="muted">Noch kein Gold-Datensatz registriert.</p>')+`<div class="panel spaced"><div class="panel-head"><h2>CSV-Dateien zur Registrierung</h2></div><div class="table-wrap"><table><thead><tr><th>Datei</th><th>Status</th><th>Zeilen</th><th></th></tr></thead><tbody>${state.datasets.map(d=>`<tr><td>${esc(d.name)}</td><td>${badge(d.status)}</td><td>${num(d.total)}</td><td>${d.status==='ready'?`<button data-action="gold-register" data-id="${d.id}">Spalten zuordnen</button>`:esc(d.error||'')}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function goldEditor(datasetId){
 const ready=state.datasets.filter(d=>d.status==='ready'&&d.total);
 if(!ready.length){toast('Zuerst eine CSV hochladen und vollständig importieren lassen.');datasetEditor();return;}
 openEditor('Gold-Datensatz registrieren',`${input('Name','name','Gold-Standard','text','required')}${select('Importierte CSV','dataset_id',ready.map(d=>option(d.id,d.name,datasetId)).join(''))}<div class="grid">${select('Dokument-ID','doc_id_column','')}${select('Text','text_column','')}${select('Gold-Label','gold_column','')}${select('Label-Modus','mode',option('single','Single-Label','single')+option('multi','Multi-Label'))}${input('Trennzeichen innerhalb der Gold-Zelle','separator','|','text','required maxlength=16')}<label><input type="checkbox" name="allow_empty">Leere Gold-Zelle = keine Labels (nur Multi-Label)</label></div><p class="muted">Beispiel: FOR|SECURITY. Das Trennzeichen ist eine wörtliche Zeichenfolge, kein regulärer Ausdruck. Dokument-IDs müssen eindeutig sein. Registrierungen bleiben unveränderlich; für eine andere Zuordnung neu registrieren.</p>`,'gold');
 updateGoldColumns();
}
function updateGoldColumns(){
 const d=state.datasets.find(d=>d.id===$('[name=dataset_id]').value);
 for(const [field,standard] of [['doc_id_column','doc_id'],['text_column','text'],['gold_column','gold_label']])$(`[name=${field}]`).innerHTML=d.columns.map(c=>option(c,c,standard)).join('');
}
async function submitGold(f){await api('/gold-sets',{method:'POST',body:JSON.stringify({name:f.get('name'),dataset_id:f.get('dataset_id'),doc_id_column:f.get('doc_id_column'),text_column:f.get('text_column'),gold_column:f.get('gold_column'),mode:f.get('mode'),separator:f.get('separator'),allow_empty:f.has('allow_empty')})});}
function renderEvaluations(){
 const list=state.evaluations||[];
 $('#view').innerHTML=`<div class="stats"><div class="stat"><span>Evaluationen</span><strong>${num(list.length)}</strong></div><div class="stat"><span>Gold-Datensätze</span><strong>${num(state.goldSets?.length)}</strong></div><div class="stat"><span>Modellkonfigurationen</span><strong>${num(list.reduce((n,e)=>n+e.runs.length,0))}</strong></div><div class="stat"><span>Reports verfügbar</span><strong>${num(list.filter(e=>e.report_ready).length)}</strong></div></div>`+(list.length?`<div class="panel"><div class="panel-head"><h2>Modellvergleiche</h2><span class="muted">Gold → Vorhersagen → Metriken</span></div><div class="table-wrap"><table><thead><tr><th>Evaluation</th><th>Varianten</th><th>Status</th><th>Fortschritt</th><th></th></tr></thead><tbody>${list.map(e=>`<tr><td><strong>${esc(e.name)}</strong><span class="muted">${esc(e.task_snapshot.task.name)}</span></td><td>${e.runs.length}</td><td>${badge(e.status)}</td><td class="progress">${num(e.done)} / ${num(e.total)}<progress value="${e.done}" max="${e.total}"></progress></td><td><button data-action="evaluation-detail" data-id="${e.id}">Vergleichen</button></td></tr>`).join('')}</tbody></table></div></div>`:empty('Modelle auf Gold-Labels vergleichen','Wähle ein Kodierbuch und einen registrierten Gold-Datensatz. Kombiniere mehrere Modelle mit unterschiedlichen Temperaturen oder weiteren Query-Parametern.','new-evaluation','Evaluation erstellen'));
}
async function evaluationEditor(goldId){
 if(!state.tasks.length||!state.goldSets?.length||!state.profiles.length){toast('Benötigt: Task, registrierter Gold-Datensatz und LLM-Verbindung.');return;}
 openEditor('Evaluation konfigurieren',`${input('Name der Evaluation','name','Modellvergleich','text','required')}<div class="grid">${select('Gold-Datensatz','gold_id',state.goldSets.map(g=>option(g.id,g.spec.name,goldId)).join(''))}${select('Klassifikationstask','task_id',state.tasks.map(t=>option(t.id,t.spec.name)).join(''))}</div><div class="category"><h3>Modell × Temperatur</h3>${select('Verbindung für neue Varianten','eval_profile',state.profiles.map(p=>option(p.id,p.spec.name)).join(''))}<label>Verfügbare Modelle<select name="eval_models" multiple size="4" aria-label="Verfügbare Modelle"></select><small>Mehrere Modelle mit Strg/Cmd auswählen.</small></label>${input('Modell-IDs manuell (optional, durch Komma getrennt)','manual_models')}${input('Temperaturen (Komma-getrennt; Dezimalpunkt verwenden)','temperatures','0, 0.5')}<p id="eval-model-hint" class="muted">Modelle werden geladen …</p><button type="button" data-action="evaluation-add-variants">Kombinationen hinzufügen</button></div><div class="section-title"><h3>Zu startende Konfigurationen</h3></div><div id="variants"></div><details open><summary>Gemeinsame Einstellungen</summary><div class="grid">${outputToggles()}${input('Parallele Anfragen je Variante','concurrency',4,'number','min=1 max=128 required')}${input('Wiederholungen','retries',2,'number','min=0 max=10 required')}${input('Maximale Output-Tokens','max_tokens',1024,'number','min=16 max=32768 required')}${input('Top-p','top_p',1,'number','min=0.01 max=1 step=0.01 required')}${input('Seed (optional)','seed','','number')}${select('Ausgabeformat','structured_output',option('json_schema','JSON Schema','json_schema')+option('json_object','JSON-Objekt')+option('none','Nur Prompt'))}${input('Beispiele je Kategorie','examples_per_category',3,'number','min=0 max=100 required')}${input('Maximale Textlänge','max_text_chars',30000,'number','min=1 max=1000000 required')}${select('Überlange Texte','overlong',option('error','Als Fehler markieren','error')+option('truncate','Abschneiden'))}</div>${area('Weitere API-Parameter (JSON)','extra_body','{}','Thinking aktivieren: abhängig vom Server, z. B. {"think":true} für Ollama oder chat_template_kwargs für vLLM. Gelieferte Thinking-Ausgaben werden automatisch gespeichert.')}</details><p class="muted">Bis zu 50 Varianten. Jede Variante verwendet denselben Gold-Datensatz und ein Task-Snapshot. Gold-Labels werden nicht an das Modell gesendet.</p>`,'evaluation');
 $('#editor-form button[type=submit]').textContent='Evaluation starten';
 await evalLoadModels();
}
async function evalLoadModels(){
 const id=$('[name=eval_profile]').value;
 try{const r=await api('/profiles/'+id+'/models');if(!$('[name=eval_models]')||$('[name=eval_profile]').value!==id)return;$('[name=eval_models]').innerHTML=r.models.map((m,i)=>option(m,m,i===0?m:null)).join('');$('#eval-model-hint').textContent=r.models.length+' Modelle verfügbar.';}catch(e){if($('#eval-model-hint'))$('#eval-model-hint').textContent=e.message;}
}
function addVariants(){
 const selected=[...$('[name=eval_models]').selectedOptions].map(o=>o.value),manual=$('[name=manual_models]').value.split(',').map(s=>s.trim()).filter(Boolean);
 const models=[...new Set([...selected,...manual])],temps=$('[name=temperatures]').value.split(',').map(s=>s.trim());
 if(!models.length||!temps.length||temps.some(t=>t===''||!Number.isFinite(Number(t))||Number(t)<0||Number(t)>2))throw Error('Mindestens ein Modell und gültige Temperaturen zwischen 0 und 2 angeben.');
 if($('#variants').children.length+models.length*temps.length>50)throw Error('Maximal 50 Konfigurationen pro Evaluation.');
 const profile=$('[name=eval_profile]').value;
 for(const model of models)for(const temp of temps){const n=$('#variants').children.length+1;$('#variants').insertAdjacentHTML('beforeend',`<div class="variant category"><div class="category-head"><strong>Variante ${n}</strong><button type="button" data-action="evaluation-remove-variant">Entfernen</button></div>${input('Name','variant_name',`${model} · T=${temp} · #${n}`,'text','required')}<div class="grid">${select('Verbindung','variant_profile',state.profiles.map(p=>option(p.id,p.spec.name,profile)).join(''))}${input('Modell-ID','variant_model',model,'text','required')}${input('Temperatur','variant_temperature',temp,'number','min=0 max=2 step=0.01 required')}</div><details><summary>Weitere Parameter dieser Variante überschreiben</summary>${area('Query-Overrides (JSON)','variant_overrides','{}','Beispiel: {"top_p":0.8,"seed":42,"rationale":false,"evidence":true}. Die vollständigen effektiven Einstellungen werden gespeichert.')}</details></div>`);}
}
async function submitEvaluation(f){
 if(!$('#variants').children.length)throw Error('Zuerst Modell-Temperatur-Kombinationen hinzufügen.');
 const base={};for(const k of ['concurrency','retries','top_p','max_tokens','examples_per_category','max_text_chars'])base[k]=Number(f.get(k));
 for(const k of ['structured_output','overlong'])base[k]=f.get(k);
 base.seed=f.get('seed')===''?null:Number(f.get('seed'));base.rationale=triState(f.get('rationale_override'));base.evidence=triState(f.get('evidence_override'));base.extra_body=JSON.parse(f.get('extra_body'));
 const variants=[...document.querySelectorAll('.variant')].map(c=>{const get=n=>c.querySelector(`[name=${n}]`).value;return {name:get('variant_name'),profile_id:get('variant_profile'),query:{...base,model:get('variant_model'),temperature:Number(get('variant_temperature')),...JSON.parse(get('variant_overrides'))}};});
 await api('/evaluations',{method:'POST',body:JSON.stringify({name:f.get('name'),task_id:f.get('task_id'),gold_id:f.get('gold_id'),variants})});
 location.hash='evaluations';
}
async function showEvaluation(id,initial=true){
 const e=await api('/evaluations/'+id);
 if(initial){selectedJob=null;selectedEvaluation=id;evaluationReport=null;evaluationScope='common';evaluationAfter=0;$('#detail-title').textContent=e.name;$('#detail-body').innerHTML='<div id="evaluation-live"></div><div id="evaluation-report" class="spaced"></div>';$('#detail').showModal();}
 if(!$('#evaluation-live')||selectedEvaluation!==id)return;
 const actions=[];if(e.runs.some(r=>['running','queued'].includes(r.status)))actions.push(['pause','Alle pausieren']);if(e.runs.some(r=>r.status==='paused'))actions.push(['resume','Pausierte fortsetzen']);if(e.runs.some(r=>['running','queued','paused','pausing'].includes(r.status)))actions.push(['cancel','Abbrechen']);if(e.report_error)actions.push(['retry-report','Report erneut berechnen']);
 $('#evaluation-live').innerHTML=`<div class="section-title">${badge(e.status)}<div class="actions">${actions.map(([a,l])=>`<button data-action="evaluation-control" data-id="${id}" data-control="${a}">${l}</button>`).join('')}</div></div><progress value="${e.done}" max="${e.total}"></progress><p class="muted">${num(e.done)} / ${num(e.total)} Klassifikationen · ${num(e.failed)} Fehler</p>${e.report_error?`<p class="error">${esc(e.report_error)}</p>`:''}<div class="table-wrap"><table><thead><tr><th>Konfiguration</th><th>Status</th><th>Fortschritt</th><th></th></tr></thead><tbody>${e.runs.map(r=>`<tr><td>${esc(r.name)}<div class="muted">${esc(r.model)} · T=${r.query.temperature}</div></td><td>${badge(r.status)}</td><td>${num(r.done)} / ${num(r.total)}</td><td><button data-action="job-detail" data-id="${r.id}">Einzellauf</button></td></tr>`).join('')}</tbody></table></div>`;
 if(e.report_ready&&!evaluationReport)await loadEvaluationReport();
}
async function loadEvaluationReport(){
 evaluationReport=await api('/evaluations/'+selectedEvaluation+'/report?scope='+evaluationScope);
 const r=evaluationReport,id=selectedEvaluation;
 const kappa=r.mode==='multi'?'kappa_macro_ovr':'kappa',mcc=r.mode==='multi'?'mcc_macro_ovr':'mcc';
 $('#evaluation-report').innerHTML=`<h2>Qualität vergleichen</h2><div class="notice spaced">${esc(r.policies[evaluationScope])}<br>Coverage berücksichtigt alle ${num(r.gold.total)} Gold-Dokumente. Accuracy (alle) zählt Fehler und unbearbeitete Texte als falsch. Metriken ohne auswertbare Vorhersagen erscheinen als n/a.</div><div class="grid">${select('Auswertungsbasis','eval_scope',option('common','Gemeinsame gültige Dokumente',evaluationScope)+option('valid','Gültige Dokumente je Variante',evaluationScope))}${select('Mittelwert für Precision / Recall / F1','eval_average',['macro','micro','weighted',...(r.mode==='multi'?['samples']:[])].map(a=>option(a,a,'macro')).join(''))}</div><div id="evaluation-summary"></div><div class="actions spaced">${[['csv','Metriken CSV'],['class_csv','Klassen CSV'],['html','HTML-Report'],['json','Report JSON'],['zip','Reportpaket ZIP']].map(([f,l])=>`<a class="button" href="/api/evaluations/${id}/report?scope=${evaluationScope}&format=${f}" target="_blank" rel="noopener">${l} ↓</a>`).join('')}<a class="button" href="/api/evaluations/${id}/export-predictions?format=csv">Gold + Predictions CSV ↓</a><a class="button" href="/api/evaluations/${id}/export-predictions?format=jsonl">Gold + Predictions JSONL ↓</a></div><details open><summary>Grafischer Modellvergleich</summary>${select('Metrik','eval_plot_metric',['accuracy','precision_macro','recall_macro','f1_macro','f1_micro','f1_weighted',kappa,mcc,'coverage','accuracy_all','hamming_loss'].map(m=>option(m,m,'f1_macro')).join(''))}<div id="evaluation-overview-chart"></div></details><details open><summary>Ergebnisse nach Klasse</summary>${select('Klassenmetrik','eval_class_metric',['precision','recall','f1','accuracy','specificity','kappa','mcc'].map(m=>option(m,m,'f1')).join(''))}<div id="evaluation-class-table"></div><div id="evaluation-class-chart"></div></details><details><summary>Confusion-Matrizen</summary>${select('Konfiguration','eval_confusion_run',r.runs.map(v=>option(v.job_id,v.variant)).join(''))}<div id="evaluation-confusion-chart"></div></details><details><summary>Gold-Labels und gespeicherte Vorhersagen</summary>${select('Konfiguration','eval_prediction_run',r.runs.map(v=>option(v.job_id,v.variant)).join(''))}<div class="actions"><button data-action="evaluation-predictions-first">Laden / Anfang</button><button data-action="evaluation-predictions-next">Weitere 50</button></div><div id="evaluation-predictions" class="spaced"></div></details><details><summary>Auswertungskonventionen</summary>${Object.entries(r.policies).map(([k,v])=>`<p class="small"><strong>${esc(k)}:</strong> ${esc(v)}</p>`).join('')}</details>`;
 renderEvaluationSummary();renderEvaluationClasses();renderEvaluationCharts();
}
function renderEvaluationSummary(){
 const r=evaluationReport,avg=$('[name=eval_average]').value,kappa=r.mode==='multi'?'kappa_macro_ovr':'kappa',mcc=r.mode==='multi'?'mcc_macro_ovr':'mcc';
 $('#evaluation-summary').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Variante</th><th>N</th><th>Coverage</th><th>Accuracy</th><th>Precision ${avg}</th><th>Recall ${avg}</th><th>F1 ${avg}</th><th>${esc(kappa)}</th><th>${esc(mcc)}</th><th>Accuracy (alle)</th></tr></thead><tbody>${r.runs.map(v=>`<tr><td>${esc(v.variant)}</td><td>${num(v.n)}</td><td>${metricNumber(v.coverage)}</td>${['accuracy','precision_'+avg,'recall_'+avg,'f1_'+avg,kappa,mcc].map(k=>`<td>${metricNumber(v.summary[k])}</td>`).join('')}<td>${metricNumber(v.accuracy_all)}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderEvaluationClasses(){
 const r=evaluationReport,metric=$('[name=eval_class_metric]').value;
 $('#evaluation-class-table').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Klasse</th>${r.runs.map(v=>`<th>${esc(v.variant)}<br>${esc(metric)} / Gold-Support</th>`).join('')}</tr></thead><tbody>${r.labels.map(label=>`<tr><td>${esc(label)}</td>${r.runs.map(v=>{const c=v.per_class.find(c=>c.label===label);return `<td>${metricNumber(c[metric])} <span class="muted">/ ${num(c.support)}</span></td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function chartBlock(kind,metric,job){const url=`/api/evaluations/${selectedEvaluation}/chart?scope=${evaluationScope}&kind=${kind}&metric=${encodeURIComponent(metric)}${job?'&job_id='+job:''}`;return `<div class="chart-frame"><img src="${url}&format=svg" alt="${kind==='classes'?'Klassenvergleich':kind==='confusion'?'Confusion-Matrix':'Modellvergleich'}"></div><div class="actions"><a class="button" href="${url}&format=svg" download>SVG ↓</a><a class="button" href="${url}&format=png" download>PNG ↓</a></div>`;}
function renderEvaluationCharts(){
 $('#evaluation-overview-chart').innerHTML=chartBlock('overview',$('[name=eval_plot_metric]').value);
 $('#evaluation-class-chart').innerHTML=chartBlock('classes',$('[name=eval_class_metric]').value);
 $('#evaluation-confusion-chart').innerHTML=chartBlock('confusion','f1',$('[name=eval_confusion_run]').value);
}
async function loadEvaluationPredictions(){
 const rows=await api(`/evaluations/${selectedEvaluation}/predictions?job_id=${$('[name=eval_prediction_run]').value}&after=${evaluationAfter}`);
 $('#evaluation-predictions').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>Dokument</th><th>Gold</th><th>Vorhersage</th><th>Details</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.doc_id)}<p class="result-text small">${esc(row.text.slice(0,500))}</p></td><td>${esc(row.gold_labels.join(', ')||'∅')}</td><td>${row.predicted_labels===null?'Keine gültige Vorhersage':esc(row.predicted_labels.join(', ')||'∅')}<p class="muted">${row.exact_match?'Exact Match':esc(row.status)}</p></td><td><details><summary>Begründung / Belege / Thinking</summary><pre>${esc(JSON.stringify({rationale:row.rationale,evidence:row.evidence,thinking:row.thinking,error:row.error,attempt_outputs:row.attempt_outputs},null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">Keine weiteren Dokumente.</p>';
 if(rows.length)evaluationAfter=rows.at(-1).row_no;
}
async function evaluationAction(event){
 const el=event.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,id=el.dataset.id;
 try{
 if(a==='gold-register')goldEditor(id);
 if(a==='gold-preview'){selectedJob=null;selectedEvaluation=null;const r=await api('/gold-sets/'+id+'/preview');$('#detail-title').textContent='Gold-Standard · Vorschau';$('#detail-body').innerHTML='<pre>'+esc(JSON.stringify(r,null,2))+'</pre>';$('#detail').showModal();}
 if(a==='new-evaluation')await evaluationEditor(el.dataset.gold);
 if(a==='evaluation-add-variants')addVariants();if(a==='evaluation-remove-variant')el.closest('.variant').remove();
 if(a==='evaluation-detail')await showEvaluation(id);
 if(a==='evaluation-control'){if(el.dataset.control==='cancel'&&!confirm('Alle noch aktiven Varianten abbrechen?'))return;await api('/evaluations/'+id+'/'+el.dataset.control,{method:'POST'});await refresh();}
 if(a==='evaluation-predictions-first'){evaluationAfter=0;await loadEvaluationPredictions();}if(a==='evaluation-predictions-next')await loadEvaluationPredictions();
 }catch(e){if($('#editor').open)$('#form-error').textContent=e.message;else toast(e.message);}
}
document.addEventListener('click',evaluationAction);
document.addEventListener('change',async e=>{try{
 if(e.target.name==='eval_profile')await evalLoadModels();
 if(e.target.name==='eval_scope'){evaluationScope=e.target.value;await loadEvaluationReport();}
 if(e.target.name==='eval_average')renderEvaluationSummary();
 if(e.target.name==='eval_class_metric'){renderEvaluationClasses();$('#evaluation-class-chart').innerHTML=chartBlock('classes',e.target.value);}
 if(e.target.name==='eval_plot_metric')$('#evaluation-overview-chart').innerHTML=chartBlock('overview',e.target.value);
 if(e.target.name==='eval_confusion_run')$('#evaluation-confusion-chart').innerHTML=chartBlock('confusion','f1',e.target.value);
 if(e.target.name==='eval_prediction_run'){evaluationAfter=0;await loadEvaluationPredictions();}
 }catch(error){toast(error.message);}});
$('#detail').addEventListener('close',()=>{selectedEvaluation=null;evaluationReport=null;});
