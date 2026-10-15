const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('dashboard.html','latin1');
for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(m[1]);
const helper=html.slice(html.indexOf('let validationRequestActive=false;'),html.indexOf('async function loadValidation(){'));
let calls=0,resolveFetch;
const context={AbortController,setTimeout,clearTimeout,fetch:()=>{calls++;return new Promise(resolve=>{resolveFetch=resolve;});}};
vm.createContext(context);vm.runInContext(helper,context);
(async()=>{
 const pending=context.fetchValidation();assert.equal(await context.fetchValidation(),null);assert.equal(calls,1);
 resolveFetch({ok:true,json:async()=>({captures:[]})});await pending;
 const next=context.fetchValidation();assert.equal(calls,2);
 resolveFetch({ok:false,json:async()=>({error:'fixture failure'})});await assert.rejects(next,/fixture failure/);
 const recovery=context.fetchValidation();assert.equal(calls,3);
 resolveFetch({ok:true,json:async()=>({captures:[]})});await recovery;
 console.log('PASS: inline scripts parse; overlaps skipped; guard releases after success and failure');
})().catch(e=>{console.error(e);process.exitCode=1;});
