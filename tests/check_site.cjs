// Offline interaction checks for generated HTML. No browser or network required.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8');
const payload=html.match(/<script id="explorer-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes={};function node(id){return nodes[id]??={textContent:id==='explorer-data'?payload:'',innerHTML:'',value:({view:'all',sort:'openai',min:'0',match:'either'})[id]??'',selectedOptions:[{textContent:'All abstracts'}],handlers:{},setAttribute(k,v){this[k]=v},addEventListener(k,v){this.handlers[k]=v},showModal(){this.open=true},close(){this.open=false},focus(){}};}
const context=vm.createContext({document:{getElementById:node,createElement:()=>({click(){}})},location:{origin:'null',href:'file:///local/report.html',pathname:'/local/report.html',hash:''},history:{replaceState(){throw Error('file history unavailable')}},URL,Blob,console,setTimeout,clearTimeout,fetch(){throw Error('Local export must not fetch')}});
vm.runInContext(script,context);const run=s=>vm.runInContext(s,context);
(async()=>{await new Promise(r=>setTimeout(r,10));const data=JSON.parse(payload);assert.equal(run('filtered.length'),data.metadata.records.length);
const first=data.metadata.records.find(r=>data.details[r.chunk][r.id]);await run('openAbstract('+JSON.stringify(first.id)+')');
assert(node('detail').open);assert(!node('fulltext').innerHTML.includes('Loading'));assert(node('fulltext').innerHTML.length>100);assert(node('detailbody').innerHTML.includes(first.id));
node('scattertab').onclick();assert.equal(node('scatterpanel').hidden,false);assert(node('scatterchart').innerHTML.includes('<svg'));
node('min').value='90';node('match').value='both';run('apply()');assert(run('filtered.every(r=>r.openai>=.9&&r.jev>=.9)'));
node('reset').onclick();assert.equal(run('filtered.length'),data.metadata.records.length);
console.log(`PASS: standalone HTML loads ${data.metadata.records.length} records, full text modal, scatter and filters without network or file-history support.`);
})().catch(e=>{console.error(e);process.exitCode=1});
