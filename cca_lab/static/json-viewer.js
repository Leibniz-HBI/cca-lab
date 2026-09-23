'use strict';
// Shared, text-only rendering: source strings are escaped before insertion.
function highlightJSON(value){
 const source=JSON.stringify(value,null,2);
 const token=/"(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/g;
 let html='',last=0;
 for(const m of source.matchAll(token)){
  html+=esc(source.slice(last,m.index));
  const kind=m[0].startsWith('"')?(m[0].endsWith(':')?'key':'string'):/^(true|false|null)$/.test(m[0])?'literal':'number';
  html+='<span class="json-'+kind+'">'+esc(m[0])+'</span>';last=m.index+m[0].length;
 }
 return html+esc(source.slice(last));
}
function readableJSON(value,depth=0){
 if(depth>16)return '<pre>'+esc(JSON.stringify(value,null,2))+'</pre>';
 if(typeof value==='string'){
  // Provider responses and chat message content often contain JSON inside a string.
  if(/^[\s]*[\[{]/.test(value)){try{return readableJSON(JSON.parse(value),depth+1);}catch{}}
  return '<pre class="json-text">'+esc(value)+'</pre>';
 }
 if(value===null||typeof value!=='object')return '<span class="json-literal">'+esc(JSON.stringify(value))+'</span>';
 const entries=Object.entries(value);
 if(!entries.length)return '<code>'+ (Array.isArray(value)?'[]':'{}')+'</code>';
 return '<dl class="json-tree">'+entries.map(([key,v])=>'<div><dt>'+esc(Array.isArray(value)?'Item '+(Number(key)+1):key)+'</dt><dd>'+readableJSON(v,depth+1)+'</dd></div>').join('')+'</dl>';
}
function jsonViewer(value){
 return '<section class="json-viewer"><label class="json-switch"><input type="checkbox" class="json-mode"> JSON mode <small>Exact JSON with escaped strings</small></label><div class="json-readable">'+readableJSON(value)+'</div><pre class="json-raw" hidden>'+highlightJSON(value)+'</pre></section>';
}
document.addEventListener('change',event=>{
 if(!event.target.matches('.json-mode'))return;
 const viewer=event.target.closest('.json-viewer');
 viewer.querySelector('.json-readable').hidden=event.target.checked;
 viewer.querySelector('.json-raw').hidden=!event.target.checked;
});
// Upgrade existing JSON displays, including asynchronously inserted logs/results.
function enhanceJSONDisplays(){
 document.querySelectorAll('pre:not([data-json-checked])').forEach(pre=>{
  pre.dataset.jsonChecked='true';if(pre.closest('.json-viewer'))return;
  try{const value=JSON.parse(pre.textContent);if(value===null||typeof value!=='object')return;
   const wrapper=document.createElement('div');wrapper.innerHTML=jsonViewer(value);pre.replaceWith(wrapper.firstElementChild);
  }catch{}
 });
}
new MutationObserver(enhanceJSONDisplays).observe(document.body,{childList:true,subtree:true});
enhanceJSONDisplays();
