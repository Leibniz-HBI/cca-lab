const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');
const ctx=vm.createContext({assert,document:{body:{},querySelectorAll:()=>[]},MutationObserver:class{observe(){}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../cca_lab/static/tables.js'),'utf8'),ctx);
vm.runInContext(`
assert.equal(metricSortValue('0.750 ± 0.030'),.75);
assert.equal(metricSortValue('1,234.5'),1234.5);
assert.equal(metricSortValue('-0.10 / 8'),-.1);
assert.equal(metricSortValue('1e-4'),.0001);
assert.equal(metricSortValue('n/a'),null);
assert.equal(metricSortValue('Model 12'), 'Model 12');
assert.ok(compareMetricValues(2,10,'ascending')<0);
assert.ok(compareMetricValues(2,10,'descending')>0);
assert.ok(compareMetricValues(null,10,'ascending')>0);
assert.ok(compareMetricValues(null,10,'descending')>0);
assert.ok(compareMetricValues('Model 2','Model 10','ascending')<0);
`,ctx);
console.log('PASS: numeric metrics, means, missing values and natural text ordering');
