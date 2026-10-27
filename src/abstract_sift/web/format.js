/* Pure display helpers: never interpret source abstract text as HTML. */
(function(root){
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const heading=/^(Background|Introduction|Methods|Materials and methods|Patients and methods|Results|Conclusions?|Discussion|Objectives?|Purpose|Aims?|Trial design|Clinical trial identification|Editorial acknowledgement|Legal entity responsible for the study|Funding|Disclosure)\s*:?[ \t]*$/i;
function stripPrefix(text,value){
 if(!value)return text;
 const pattern=String(value).trim().split(/\s+/).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('\\s+');
 return text.replace(new RegExp('^\\s*'+pattern+'(?=\\s|$)'),'').trimStart();
}
function splitAbstract(text,record){
 let rest=String(text??'').trim(),authorPrefixRemoved=false;
 for(const k of ['id','title','authors']){const next=stripPrefix(rest,record[k]);if(k==='authors'&&next!==rest)authorPrefixRemoved=true;rest=next;}
 const lines=rest.split('\n');const index=lines.findIndex(l=>heading.test(l.trim()));
 // Only move recognizable affiliation material; never hide an unstructured abstract.
 if(index>0){const prefix=lines.slice(0,index).join('\n').trim();
  if(authorPrefixRemoved||/^[¹²³⁴⁵⁶⁷⁸⁹⁰\d]/.test(prefix)||/\b(department|university|hospital|institute|center|centre|oncology|pharma)\b/i.test(prefix))
   return {affiliations:prefix,body:lines.slice(index).join('\n').trim()};
 }
 return {affiliations:'',body:rest};
}
function bodyHTML(text){return String(text).split('\n').map(line=>heading.test(line.trim())?`<strong class="sectionheading">${escape(line.trim())}</strong>`:escape(line)).join('\n');}
function percent(n){return n==null?'—':(n*100).toLocaleString('en-US',{maximumFractionDigits:1})+'%';}
const api={splitAbstract,bodyHTML,percent};root.AbstractFormat=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
