const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const elements={},pending=[];
const ctx=vm.createContext({document:{addEventListener(){}},$:s=>elements[s],option:(m)=>'<option>'+m+'</option>',api:url=>new Promise((resolve,reject)=>pending.push({url,resolve,reject}))});
vm.runInContext(fs.readFileSync('cca_lab/static/configurations.js','utf8'),ctx);
function editor(id){elements['[name=config_profile]']={value:id};elements['[name=config_models]']={innerHTML:'old model'};elements['#config-model-hint']={};}
(async()=>{
 editor('first');const a=vm.runInContext('configModels()',ctx);
 assert.equal(elements['[name=config_models]'].innerHTML,'');assert.equal(elements['[name=config_models]'].disabled,true);
 elements['[name=config_profile]'].value='second';const b=vm.runInContext('configModels()',ctx);
 pending[1].resolve({models:['gpt-oss']});await b;
 pending[0].resolve({models:['gemma']});await a;
 assert.equal(elements['[name=config_models]'].innerHTML,'<option>gpt-oss</option>');
 const c=vm.runInContext('configModels()',ctx);editor('second');const d=vm.runInContext('configModels()',ctx);
 pending[3].resolve({models:['new']});await d;pending[2].reject(Error('stale failure'));await c;
 assert.equal(elements['[name=config_models]'].innerHTML,'<option>new</option>');
 assert.ok(!elements['#config-model-hint'].textContent.includes('failure'));
 console.log('PASS: clear stale model choices, connection switching, editor reopening, stale errors');
})().catch(e=>{console.error(e);process.exit(1)});
