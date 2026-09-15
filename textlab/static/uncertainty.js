'use strict';
function agreementPanel(kind,id){return `<details><summary>Per-document agreement across seeds</summary><p class="small">Same task, model and parameters; seeds vary. Failed, fallback and cancelled runs are excluded. At least two valid runs are required for agreement. Frequencies measure stability, not calibrated correctness. Row numbers identify documents in the source dataset.</p><div class="actions"><button data-action="agreement-load" data-kind="${kind}" data-id="${id}" data-after="0">Load first 50 per configuration</button><a class="button" href="/api/${kind}/${id}/agreement?format=csv">Agreement CSV ↓</a><a class="button" href="/api/${kind}/${id}/agreement?format=jsonl">Agreement JSONL ↓</a></div><div id="agreement-results"></div></details>`;}
function renderUncertaintyReport(r,id){
 const rows=(r.groups||[]).map(g=>{const c=g.confidence;return `<tr><td>${esc(g.variant)}</td>${['n','brier','ece','error_auroc','error_ap'].map(k=>{const v=c?.metrics?.[k];return `<td>${v?.mean==null?'n/a':v.mean.toFixed(3)+(v.sd==null?'':` ± ${v.sd.toFixed(3)}`)}</td>`;}).join('')}</tr>`;}).join('');
 $('#evaluation-report').insertAdjacentHTML('beforeend',`<h2>Confidence diagnostics</h2><p class="small">Uncalibrated self-reports, predicting exact agreement with gold labels. Uses the selected scoring scope, excluding fallback/failed responses and cancelled runs from averages. Mean ± sample SD across runs. Brier and ECE: lower is better. Error AUROC/AP: higher is better; n/a when only one outcome occurs. Reliability bins average contributing runs only. Risk curves accept complete confidence ties; coverage is conditional on valid scored responses, not the entire dataset.</p><div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Mean scored N</th><th>Brier</th><th>ECE</th><th>Error AUROC</th><th>Error AP</th></tr></thead><tbody>${rows}</tbody></table></div>${['reliability','risk'].map(kind=>{const url=`/api/evaluations/${id}/confidence-chart?scope=${evaluationScope}&kind=${kind}`;return `<div class="chart-frame"><img src="${url}" alt="Confidence ${kind}"></div><div class="actions"><a class="button" href="${url}&format=svg" download>SVG ↓</a><a class="button" href="${url}&format=png" download>PNG ↓</a></div>`;}).join('')}${agreementPanel('evaluations',id)}`);
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-action="agreement-load"]');if(!el)return;
 try{const rows=await api(`/${el.dataset.kind}/${el.dataset.id}/agreement?after=${el.dataset.after}`);
 $('#agreement-results').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>Task / model / row</th><th>Valid / eligible runs</th><th>Modal share</th><th>Entropy (bits)</th><th>Details</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.configuration)} / ${esc(r.model)} · T=${r.temperature} / ${r.row_no}</td><td>${r.valid_runs} / ${r.expected_runs}</td><td>${r.modal_vote_share==null?'n/a':r.modal_vote_share.toFixed(3)}</td><td>${r.label_set_entropy_bits==null?'n/a':r.label_set_entropy_bits.toFixed(3)}</td><td><details><summary>Label frequencies and exclusions</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div><button data-action="agreement-load" data-kind="${el.dataset.kind}" data-id="${el.dataset.id}" data-after="${Math.max(...rows.map(r=>r.row_no))}">Next 50 per configuration</button>`:'<p>No further documents.</p>';
 }catch(e){toast(e.message);}
});
function queryEstimate(){
 if(!$('#editor').open||!['prediction','evaluation'].includes(edit?.kind))return;
 let box=$('#query-estimate');if(!box){$('#editor-body').insertAdjacentHTML('afterbegin','<div class="notice" id="query-estimate" aria-live="polite"></div>');box=$('#query-estimate');}
 try{
 const seeds=parseSeedInput($('[name=seeds]')?.value)||[null], retries=Number($('[name=retries]')?.value||0);
 let documents,runs,maximum,description;
 if(edit.kind==='prediction'){
  documents=state.datasets.find(d=>d.id===$('[name=dataset_id]').value)?.total||0;
  const tasks=$('[name=task_ids]').selectedOptions.length;runs=tasks*seeds.length;maximum=documents*runs*(retries+1);
  description=`${num(documents)} documents × ${tasks} tasks × ${seeds.length} seeds × 1 model configuration`;
 }else{
  const gold=state.goldSets.find(g=>g.id===$('[name=gold_id]').value);documents=gold?.total||0;
  const variants=[...document.querySelectorAll('.variant')];runs=variants.length*seeds.length;
  maximum=documents*seeds.length*variants.reduce((n,v)=>{const overrides=JSON.parse(v.querySelector('[name=variant_overrides]').value||'{}');const r=overrides.retries??retries;if(!Number.isInteger(r)||r<0||r>10)throw Error('Retries must be 0–10.');return n+r+1;},0);
  description=`${num(documents)} gold documents × ${variants.length} added model/parameter configurations × ${seeds.length} seeds`;
 }
 if(!Number.isInteger(retries)||retries<0||retries>10)throw Error('Retries must be 0–10.');
 box.innerHTML=`<strong>Planned LLM queries: ${num(documents*runs)}</strong><br>${description} = ${num(runs)} runs.<br>Up to ${num(maximum)} attempts including retries. Concurrency affects throughput, not query count. Empty or rejected texts may skip requests; runtime also depends on model speed and output length.${runs===0?' Add configurations to calculate the experiment size.':''}`;
 }catch(e){box.textContent='Query estimate unavailable: '+e.message;}
}
// Observe form creation, variant add/remove and programmatic preselection without polling.
const estimateObserver=new MutationObserver(()=>{if(!$('#query-estimate'))queryEstimate();});
estimateObserver.observe($('#editor-body'),{childList:true});
document.addEventListener('input',queryEstimate);document.addEventListener('change',queryEstimate);
document.addEventListener('click',()=>setTimeout(queryEstimate,0));
