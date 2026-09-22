'use strict';
let errorAfter=0;
function parseSeedInput(value){
 if(!value?.trim())return null;
 const parts=value.split(',').map(s=>s.trim());
 if(parts.some(s=>!/^[-+]?\d+$/.test(s)||!Number.isSafeInteger(Number(s))))throw Error('Seeds must be comma-separated safe integers.');
 const seeds=parts.map(Number);
 if(new Set(seeds).size!==seeds.length)throw Error('Seeds must be unique.');
 if(seeds.length>100)throw Error('Maximum 100 seeds.');
 return seeds;
}
function meanSD(run,key,section,expectedRuns=run.expected_runs){
 const value=section?run[section]?.[key]:run[key],sd=section?run.std?.[section]?.[key]:run.std?.[key],n=section?run.sample_n?.[section]?.[key]:run.sample_n?.[key];
 return `<span title="${n??1} defined run(s)">${metricNumber(value)}${run.std&&expectedRuns>1&&sd!=null?' ± '+metricNumber(sd):''}</span>`;
}
async function loadErrors(first=false){
 if(!selectedJob)return;
 if(first)errorAfter=0;
 const recovered=$('#errors-recovered').checked;
 const session=detailSession,id=selectedJob,after=errorAfter;
 const result=await api(`/jobs/${id}/errors?after=${after}&include_recovered=${recovered}`);
 if(!currentDetail(session)||selectedJob!==id||errorAfter!==after||$('#errors-recovered')?.checked!==recovered)return;
 $('#errors-download').href=`/api/jobs/${selectedJob}/errors?format=jsonl&include_recovered=${recovered}`;
 $('#job-errors').innerHTML=`<p>${num(result.total)} records with errors · ${esc(statuses[result.status]||result.status)}</p>${result.last_error?`<p class="error">Latest job error: ${esc(result.last_error)}</p>`:''}`+(result.rows.length?`<div class="table-wrap"><table><thead><tr><th>Row / source</th><th>Outcome</th><th>Error / attempts</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${r.row_no}<details><summary>Source text</summary><pre>${esc(JSON.stringify(r.source,null,2))}</pre></details></td><td>${esc(r.status)}${r.fallback_used?`<p>Fallback: ${esc(r.labels.join(', '))}</p>`:''}</td><td><p class="error">${esc(r.error||'Recovered after retry')}</p><details><summary>${r.attempts} attempts · ${r.error_count} errors</summary><pre>${esc(JSON.stringify(r.attempt_outputs,null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No further error records. Refresh to check new results.</p>');
 errorAfter=result.next_after;
}
document.addEventListener('click',async e=>{const a=e.target.closest('[data-action]')?.dataset.action;try{if(a==='errors-open'){$('#job-error-panel').open=true;await loadErrors(true);$('#job-error-panel')?.scrollIntoView({behavior:'smooth',block:'start'});}if(a==='errors-first')await loadErrors(true);if(a==='errors-next')await loadErrors();}catch(error){toast(error.message);}});
document.addEventListener('change',async e=>{if(e.target.id==='errors-recovered')try{await loadErrors(true);}catch(error){toast(error.message);}});
