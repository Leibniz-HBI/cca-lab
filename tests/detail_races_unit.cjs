const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');
const source=name=>fs.readFileSync(path.join(__dirname,'../cca_lab/static',name),'utf8');
const elements={},pending=[];
for(const id of ['detail','detail-title','detail-body','evaluation-live','evaluation-report'])elements['#'+id]={addEventListener(){},showModal(){this.open=true},open:false,innerHTML:'',textContent:''};
const ctx=vm.createContext({assert,document:{addEventListener(){}},$:s=>elements[s],num:String,esc:String,badge:String,selectedPrediction:null,selectedJob:null,api:url=>new Promise(resolve=>pending.push({url,resolve}))});
vm.runInContext(source('app.js').slice(source('app.js').indexOf('let detailSession='),source('app.js').indexOf('async function api(')),ctx);
vm.runInContext(source('evaluation.js'),ctx);
const result=(id,model)=>({id,name:id,runs:[{id:id+'-run',name:model,model,query:{temperature:0},connection:{name:model+' server',base_url:'http://'+model},status:'queued',done:0,total:4}],status:'queued',done:0,total:4,failed:0});
(async()=>{
 // Slow initial request must not reclaim a newer selection.
 const first=vm.runInContext("showEvaluation('gemma')",ctx);
 const second=vm.runInContext("showEvaluation('gpt')",ctx);
 pending[1].resolve(result('gpt','gpt-oss'));await second;
 pending[0].resolve(result('gemma','gemma4'));await first;
 assert.equal(elements['#detail-title'].textContent,'gpt');
 assert.ok(elements['#evaluation-live'].innerHTML.includes('gpt-oss server'));
 assert.ok(!elements['#evaluation-live'].innerHTML.includes('gemma4'));
 // A refresh from a previous modal must not update a reopened session.
 const refresh=vm.runInContext("showEvaluation('gpt',false)",ctx);
 const reopen=vm.runInContext("showEvaluation('gemma')",ctx);
 pending[3].resolve(result('gemma','gemma4'));await reopen;
 pending[2].resolve(result('gpt','gpt-oss'));await refresh;
 assert.equal(elements['#detail-title'].textContent,'gemma');
 assert.ok(!elements['#evaluation-live'].innerHTML.includes('gpt-oss'));
 // Report response arriving after switching evaluation is discarded.
 const report=vm.runInContext('loadEvaluationReport()',ctx);
 vm.runInContext("beginDetail('evaluation','other')",ctx);
 pending[4].resolve({});await report;
 assert.equal(vm.runInContext('evaluationReport',ctx),null);
 console.log('PASS: delayed initial details, stale polling, and report isolation');
})().catch(e=>{console.error(e);process.exit(1)});
