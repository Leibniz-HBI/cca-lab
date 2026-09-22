'use strict';
// Sort displayed metric rows; retain each table's choice across UI refreshes.
const metricSortChoices=new Map();
function metricSortValue(text){
 const value=text.trim();
 if(!value||/^(?:n\/a|null|undefined|—|–|-)(?:\s|$)/i.test(value))return null;
 const number=value.match(/^([+-]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(?=$|\s*(?:±|\/|%))/i);
 return number?Number(number[1].replaceAll(',','')):value;
}
function compareMetricValues(a,b,direction){
 if(a===null||b===null)return a===b?0:a===null?1:-1;
 const compared=typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b),'en',{numeric:true,sensitivity:'base'});
 return direction==='ascending'?compared:-compared;
}
function metricTableKey(table){return location.hash+'|'+(document.querySelector('#detail-title')?.textContent||'')+'|'+table.dataset.sortKey;}
function sortMetricTable(table,column,direction){
 const body=table.tBodies[0];if(!body)return;
 const rows=[...body.rows];
 rows.sort((a,b)=>compareMetricValues(metricSortValue(a.cells[column]?.textContent||''),metricSortValue(b.cells[column]?.textContent||''),direction)||Number(a.dataset.sortIndex)-Number(b.dataset.sortIndex));
 body.append(...rows);
 [...table.tHead.rows[0].cells].forEach((header,i)=>{
  header.setAttribute('aria-sort',i===column?direction:'none');
  const button=header.querySelector('.column-sort');
  button.title=i===column?'Sorted '+direction+'. Click to reverse.':'Sort ascending';
 });
}
function enhanceMetricTables(){
 document.querySelectorAll('table[data-sort-key]:not([data-sort-ready])').forEach(table=>{
  if(!table.tHead||!table.tBodies[0])return;
  table.dataset.sortReady='true';
  [...table.tBodies[0].rows].forEach((row,index)=>row.dataset.sortIndex=index);
  [...table.tHead.rows[0].cells].forEach((header,column)=>{
   const label=header.textContent.trim(),button=document.createElement('button');
   button.type='button';button.className='column-sort';button.title='Sort ascending';
   button.setAttribute('aria-label','Sort by '+label);button.append(...header.childNodes);header.append(button);header.setAttribute('aria-sort','none');
   button.addEventListener('click',()=>{
    const direction=header.getAttribute('aria-sort')==='ascending'?'descending':'ascending';
    metricSortChoices.set(metricTableKey(table),{column,direction,label});sortMetricTable(table,column,direction);
   });
  });
  const saved=metricSortChoices.get(metricTableKey(table));
  if(saved&&table.tHead.rows[0].cells[saved.column]?.textContent.trim()===saved.label)sortMetricTable(table,saved.column,saved.direction);
 });
}
new MutationObserver(enhanceMetricTables).observe(document.body,{childList:true,subtree:true});
enhanceMetricTables();
