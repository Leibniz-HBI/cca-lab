'use strict';
const baseRenderTasks=renderTasks;
renderTasks=function(){baseRenderTasks();$('#view').insertAdjacentHTML('afterbegin','<div class="actions spaced"><button data-action="cca-import">Import CCA codebook JSON</button><input id="cca-file" style="display:none" type="file" accept=".json,application/json" hidden><span class="small">CCA 0.1 · category IDs become output labels</span></div>');document.querySelectorAll('[data-action="download-task"]').forEach(b=>b.insertAdjacentHTML('afterend',`<button data-action="cca-export" data-id="${b.dataset.id}">CCA JSON ↓</button>`));};
const baseCategoryHTML=categoryHTML;
categoryHTML=function(c={label:'',definition:'',examples:[]}){
 const extra={display_label:c.display_label||'',inclusion_criteria:c.inclusion_criteria||[],exclusion_criteria:c.exclusion_criteria||[],coding_notes:c.coding_notes||'',aliases:c.aliases||[]};
 return baseCategoryHTML(c).slice(0,-6)+`<details><summary>Category name, criteria and notes</summary>${area('CCA category details (JSON)','cca_category',JSON.stringify(extra,null,2),'Label is the machine-facing category ID; display_label is the human-facing name.')}</details></div>`;
};
const baseTaskEditor=taskEditor;
taskEditor=function(id,seedSpec=null){
 baseTaskEditor(id,seedSpec);const t=state.tasks.find(x=>x.id===id)?.spec||seedSpec||{};edit.taskSpec=t;
 let metadata='';if(t.cca_source){const {task,examples,...m}=t.cca_source;metadata=area('CCA identity and provenance (JSON)','cca_metadata',JSON.stringify(m,null,2),'Update the codebook version after substantive edits. TextLab revisions are independent.');}
 $('#editor-body').insertAdjacentHTML('afterbegin',`<details><summary>CCA codebook context and provenance</summary>${input('Unit of analysis','unit_of_analysis',t.unit_of_analysis||'document','text','required')}${area('Permitted additional context','cca_context',t.context||'')}${metadata}<p class="small">CCA export contains the codebook. Runtime settings and output switches belong to native Task JSON. Empty-label tasks cannot be exported to CCA 0.1.</p></details>`);
};
const baseReadTask=readTask;
readTask=function(){
 const result=baseReadTask(),original=edit.taskSpec||{};
 result.unit_of_analysis=$('[name=unit_of_analysis]').value;result.context=$('[name=cca_context]').value;
 result.categories=result.categories.map((c,i)=>{const x=JSON.parse(document.querySelectorAll('[name=cca_category]')[i].value);if(Object.keys(x).some(k=>!['display_label','inclusion_criteria','exclusion_criteria','coding_notes','aliases'].includes(k)))throw Error('Unknown CCA category detail.');return {...c,...x};});
 if(original.cca_source){const metadata=JSON.parse($('[name=cca_metadata]').value);if('task' in metadata||'examples' in metadata)throw Error('Edit task content in its own fields.');result.cca_source={...metadata,task:original.cca_source.task,...('examples' in original.cca_source?{examples:original.cca_source.examples}:{})};}
 return result;
};
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b)return;
 try{
  if(b.dataset.action==='cca-import')$('#cca-file').click();
  if(b.dataset.action==='cca-export'){
   const response=await fetch('/api/tasks/'+b.dataset.id+'/export-cca');if(!response.ok)throw Error((await response.json()).detail);
   const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='codebook-'+b.dataset.id+'.cca.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
 }catch(error){toast(error.message);}
});
document.addEventListener('change',async e=>{
 if(e.target.id!=='cca-file')return;const file=e.target.files[0];if(!file)return;
 try{
  if(file.size>5*1024*1024)throw Error('Maximum codebook size is 5 MiB.');
  const response=await fetch('/api/tasks/import-cca',{method:'POST',headers:{'Content-Type':'application/json'},body:file}),body=await response.json();if(!response.ok)throw Error(body.detail);
  state.tasks=await api('/tasks');render();taskEditor(body.id);toast('CCA codebook imported as a new task. Review settings before running.');
 }catch(error){toast(error.message);}finally{e.target.value='';}
});
