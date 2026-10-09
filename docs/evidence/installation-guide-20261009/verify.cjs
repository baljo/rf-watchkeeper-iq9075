const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const deps = process.argv[2] || path.resolve(path.dirname(process.execPath), '../node_modules');
(async () => {
  const {marked} = await import(pathToFileURL(path.join(deps, 'marked/lib/marked.esm.js')));
  const root = path.resolve(__dirname, '../../..');
  const files = ['docs/installation.md', 'README.md', 'docs/project-log.md'];
  const results = [];
  for (const file of files) {
    const fullSource = fs.readFileSync(path.join(root,file),'utf8');
    const source = file === 'docs/project-log.md' ? fullSource.slice(fullSource.indexOf('### 2026-10-09 17:09')) : fullSource;
    const html = marked.parse(source);
    const links = [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1]);
    const local = links.filter(l=>!/^https?:|^#/.test(l));
    const missing = local.filter(l=>l !== 'evidence/installation-guide-20261009/validation.json' && !fs.existsSync(path.resolve(root,path.dirname(file),decodeURI(l.split('#')[0]))));
    if (missing.length) throw new Error(file+': missing '+missing.join(', '));
    results.push({file,scope:file === 'docs/project-log.md' ? 'new entry only' : 'whole file',localLinks:local.length,missingLinks:missing,headings:(html.match(/<h[1-6]>/g)||[]).length});
    if (file === 'docs/installation.md') {
      if ((source.match(/^```/gm)||[]).length % 2) throw new Error('Unclosed code fence');
      if (!html.includes('<table>') || !html.includes('<pre><code')) throw new Error('Table/code rendering failed');
      const rendered = '<!doctype html><meta charset="utf-8"><title>Installation guide</title><style>body{max-width:960px;margin:40px auto;padding:0 28px;font:16px/1.6 Arial;color:#202020}h1,h2,h3{line-height:1.25}h2{border-bottom:1px solid #ddd;padding-bottom:12px;margin-top:40px}pre{background:#f3f4f6;padding:18px;overflow:auto}code{font-size:14px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:10px;text-align:left}a{color:#0969da}</style>'+html;
      fs.writeFileSync(path.join(root,'../installation-preview.html'),rendered);
      const {chromium} = require(path.join(deps,'playwright'));
      const browser = await chromium.launch({channel:'msedge',headless:true});
      const page = await browser.newPage({viewport:{width:1200,height:900}});
      await page.goto(pathToFileURL(path.join(root,'../installation-preview.html')).href);
      const overflow = await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth);
      if (overflow) throw new Error('Page horizontally overflows');
      await page.screenshot({path:path.join(root,'../installation-preview.png'),fullPage:true});
      await browser.close();
    }
  }
  const added = require('child_process').execFileSync('git',['diff','--unified=0','--','docs/installation.md','README.md','docs/project-log.md'],{cwd:root,encoding:'utf8'}).split('\n').filter(l=>l.startsWith('+')&&!l.startsWith('+++')).join('\n');
  if (/\b\d{2}\.\d{3,}\s*[,/]\s*\d{2}\.\d{3,}\b/.test(added)) throw new Error('Precise coordinate pair in added prose');
  const report = {date:'2026-10-09',checks:results,render:'marked + headless Chromium; table/code present; no horizontal overflow; screenshot inspected separately',privacy:'Added prose contains no precise coordinate pair; manual scope review also required',liveInspection:'SSH authentication failed; not deployed',runtimeTests:'Not run: documentation-only change; no EVK credentials',completionRecord:'completion.md'};
  fs.writeFileSync(path.join(__dirname,'validation.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
