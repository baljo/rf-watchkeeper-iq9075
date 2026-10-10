// Render current Markdown and syntax-check inline dashboard JavaScript without execution.
const fs=require('fs'),path=require('path'),vm=require('vm');
const {pathToFileURL}=require('url');
(async()=>{
 const root=path.resolve(__dirname,'../../..');
 const deps=process.argv[2]||path.resolve(path.dirname(process.execPath),'../node_modules');
 const {marked}=await import(pathToFileURL(path.join(deps,'marked/lib/marked.esm.js')));
 const files=['README.md','current-status','architecture','airband','atis','tower-anomaly','operation','rf-jobs','dashboard','data-retention','ais','meteor','installation','troubleshooting','watchdog-and-recovery','reliability','testing-and-validation','experiments','project-history','hardware','433mhz','location-privacy'].map(n=>n==='README.md'?n:'docs/'+n+'.md');
 let links=0;
 for(const n of files){
  const html=marked.parse(fs.readFileSync(path.join(root,n),'utf8'));
  if(!html.includes('<h1>'))throw Error('Missing rendered title '+n);
  const anchors=[...html.matchAll(/href="([^"\s]+)"/g)].map(m=>m[1]);
  for(const a of anchors){
   if(/^https?:|^#/.test(a))continue;
   links++;
   if(!fs.existsSync(path.resolve(root,path.dirname(n),decodeURI(a.split('#')[0]))))throw Error(n+': missing '+a);
  }
 }
 const html=fs.readFileSync(path.join(root,'dashboard.html'),'utf8');let scripts=0;
 for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)){if(m[1].trim()){new vm.Script(m[1]);scripts++;}}
 const report={markdownFiles:files.length,renderedLocalLinks:links,inlineDashboardScriptsParsed:scripts,scope:'Markdown rendering and JavaScript syntax only; no dashboard browser/inference execution'};
 fs.writeFileSync(path.join(__dirname,'render-validation.json'),JSON.stringify(report,null,2)+'\n');console.log(report);
})().catch(e=>{console.error(e);process.exit(1)});
