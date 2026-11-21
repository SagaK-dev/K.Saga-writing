// HandwriteFont offline UI. No CDN, cookies, or external network requests.
'use strict';
let project=null, report=null, selected=null, corners=[], picture=null;
const $=id=>document.getElementById(id);
const api=async(path,options={})=>{
  const r=await fetch('/api'+path,options);
  if(!r.ok){const data=await r.json().catch(()=>({detail:r.statusText}));throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return r.json();
};
const safe=async fn=>{try{await fn();}catch(e){message(e.message||String(e),true);}};
function message(text,error=false){
  const out=document.createElement('div');out.className=error?'warning':'success';out.textContent=text;
  $('message').replaceChildren(out);scrollTo({top:0,behavior:'smooth'});
}
function dl(path,name){
  const a=document.createElement('a');a.href='/api'+path;a.download=name||'';
  document.body.append(a);a.click();a.remove();
}
async function projects(){
  const items=await api('/projects');$('saved-projects').replaceChildren(new Option('選択してください',''));
  items.forEach(p=>$('saved-projects').add(new Option(p.font_name,p.id)));
}
async function openProject(id){
  project=await api('/projects/'+encodeURIComponent(id));report=null;selected=null;
  $('setup').hidden=true;$('work').hidden=false;$('project-name').textContent=project.font_name;
  updateStatus();tab('sheet');renderGlyphs();
  $('preview-cells').replaceChildren();
  Array.from(project.charset_preview||'').slice(0,24).forEach(char=>{
    const cell=document.createElement('div');cell.textContent=char;$('preview-cells').append(cell);
  });
}
function updateStatus(){
  $('project-status').textContent=project.scanned_count+' / '+project.target_count+'文字取り込み済み / 未収録'+project.missing_count+'字 / '+project.pages+'ページ';
  $('progress-value').style.width=(100*project.scanned_count/project.target_count)+'%';
}
async function refresh(){
  const cp=selected;project=await api('/projects/'+project.id);updateStatus();renderGlyphs();
  if(cp!==null)showGlyph(cp);
}
function tab(name){
  ['sheet','scan','glyph','preview','output'].forEach(id=>$('panel-'+id).hidden=id!==name);
  document.querySelectorAll('[data-panel]').forEach(el=>el.classList.toggle('active',el.dataset.panel===name));
  if(name==='preview')preview();
}
function renderGlyphs(){
  const parent=$('glyph-grid');parent.replaceChildren();
  const term=$('search-glyph').value.trim().toUpperCase();
  (project.glyphs||[]).filter(g=>!term||g.char.includes(term)||('U+'+g.codepoint.toString(16).toUpperCase()).includes(term)).forEach(g=>{
    const b=document.createElement('button');b.textContent=g.char;b.className=g.codepoint===selected?'chosen':'';
    b.title='U+'+g.codepoint.toString(16).toUpperCase();b.onclick=()=>showGlyph(g.codepoint);parent.append(b);
  });
}
function showGlyph(cp){
  selected=cp;renderGlyphs();
  const g=project.glyphs.find(v=>v.codepoint===cp);if(!g)return;
  $('glyph-empty').hidden=true;$('glyph-controls').hidden=false;
  $('edit-heading').textContent=g.char+' U+'+cp.toString(16).toUpperCase();
  const path='/api/projects/'+project.id+'/glyphs/'+cp+'/asset/';
  ['raw','mask','svg'].forEach(k=>$(k+'-img').src=path+k+'?t='+Date.now());
  const variant=g.variants[g.selected];
  $('threshold').value=variant.threshold;$('smooth').value=variant.smooth;
  $('shift-x').value=variant.x_shift;$('shift-y').value=variant.y_shift;
  $('variants').replaceChildren();
  g.variants.forEach((v,i)=>{
    const b=document.createElement('button');b.textContent='v'+(i+1);b.className='pill';
    b.style.background=i===g.selected?'#ddd':'white';
    b.onclick=()=>safe(async()=>{await api('/projects/'+project.id+'/glyphs/'+cp+'/select/'+i,{method:'POST'});await refresh();});
    $('variants').append(b);
  });
}
async function build(){
  report=await api('/projects/'+project.id+'/build',{method:'POST'});
  const out=$('file-downloads');out.replaceChildren();
  for(const ext of ['ttf','otf']){
    const b=document.createElement('button');b.className='secondary';b.textContent=ext.toUpperCase()+'ダウンロード';
    b.onclick=()=>dl('/projects/'+project.id+'/exports/'+encodeURIComponent(report.files[ext]));out.append(b);
  }
  const v=document.createElement('button');v.className='secondary';v.textContent='検証結果JSON';
  v.onclick=()=>dl('/projects/'+project.id+'/exports/validation.json');out.append(v);
  message(report.generated+'文字のフォントを生成しました。未収録'+report.missing_count+'文字');
}
function preview(){
  const t=$('text-preview').value;$('font-preview').textContent=t;
  if(!project)return;
  const set=new Set((project.glyphs||[]).map(g=>g.codepoint));
  const missing=[...new Set(Array.from(t).filter(ch=>ch.trim()&&!set.has(ch.codePointAt(0))))];
  $('missing-letters').textContent=missing.length?'未収録：'+missing.slice(0,30).join(' '):'すべて収録済み';
}
async function scan(){
  const files=Array.from($('scan-files').files);if(!files.length)throw Error('画像またはPDFを選択してください');
  const data=new FormData();files.forEach(f=>data.append('files',f));
  if($('page-num').value)data.append('manual_page',String(Number($('page-num').value)-1));
  if($('corner-mode').checked&&corners.length===4)data.append('manual_corners',JSON.stringify(corners));
  const result=await api('/projects/'+project.id+'/scans',{method:'POST',body:data});
  $('scan-results').replaceChildren();
  result.pages.forEach(p=>{
    const d=document.createElement('div');d.className=p.status==='ok'?'success':'warning';
    d.textContent=p.status==='ok'?'ページ'+(p.page+1)+'：'+p.accepted.length+'文字取り込み':'取り込み失敗：'+p.error;
    $('scan-results').append(d);
  });
  await refresh();
  if(result.pages.some(p=>p.status==='ok'&&p.accepted.length))await build();
}
function resetCorners(){
  corners=[];const c=$('corner-canvas');if(!picture)return;
  const scale=Math.min(1,650/picture.width),ctx=c.getContext('2d');
  c.width=Math.round(picture.width*scale);c.height=Math.round(picture.height*scale);
  ctx.drawImage(picture,0,0,c.width,c.height);
  $('corner-guidance').textContent='左上→右上→右下→左下の順番で4点を選択';
}
function paintCorners(){
  resetCornerCanvas();const c=$('corner-canvas'),ctx=c.getContext('2d');
  corners.forEach(([x,y],i)=>{const sx=x*c.width/picture.width,sy=y*c.height/picture.height;
    ctx.fillStyle='red';ctx.fillRect(sx-5,sy-5,10,10);ctx.fillStyle='black';ctx.fillText(String(i+1),sx+7,sy);
  });
}
function resetCornerCanvas(){
  const c=$('corner-canvas');if(picture)c.getContext('2d').drawImage(picture,0,0,c.width,c.height);
}
$('charset').onchange=()=>{$('custom-wrap').style.display=$('charset').value==='custom'?'flex':'none';};
$('custom-file').onchange=()=>safe(async()=>{
  const file=$('custom-file').files[0];if(!file)return;let content=await file.text();
  if(file.name.endsWith('.json')){
    const data=JSON.parse(content),items=Array.isArray(data)?data:data.characters;
    if(!Array.isArray(items))throw Error('characters配列が必要です');
    content=items.map(x=>typeof x==='number'?String.fromCodePoint(x):typeof x==='string'?x:x.char||'').join('');
  }else if(file.name.endsWith('.csv')){
    content=content.split(/\r?\n/).map(x=>x.split(',')[0].trim()).filter(x=>Array.from(x).length===1).join('');
  }
  $('custom-text').value=content;
});
$('make-project').onclick=()=>safe(async()=>{
  const data={font_name:$('font-name').value,charset:$('charset').value,custom_text:$('custom-text').value,
    page_size:$('paper-size').value,orientation:$('orientation').value,
    cols:Number($('columns').value),rows:Number($('rows').value)};
  const result=await api('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  await projects();await openProject(result.id);message('プロジェクトを作成しました');
});
$('open-project').onclick=()=>safe(async()=>{if($('saved-projects').value)await openProject($('saved-projects').value);});
$('import-zip').onchange=()=>safe(async()=>{
  const file=$('import-zip').files[0];if(!file)return;
  const form=new FormData();form.append('file',file);
  const p=await api('/projects/import',{method:'POST',body:form});await projects();await openProject(p.id);
});
$('back-home').onclick=()=>safe(async()=>{$('setup').hidden=false;$('work').hidden=true;await projects();});
document.querySelectorAll('[data-panel]').forEach(el=>el.onclick=()=>tab(el.dataset.panel));
$('get-template').onclick=()=>{if(project)dl('/projects/'+project.id+'/template','HandwriteFont-template.pdf');};
$('send-scans').onclick=()=>safe(scan);
$('search-glyph').oninput=renderGlyphs;
$('save-glyph').onclick=()=>safe(async()=>{
  if(selected===null)return;
  const data={threshold:Number($('threshold').value),smooth:Number($('smooth').value),
    x_shift:Number($('shift-x').value),y_shift:Number($('shift-y').value)};
  await api('/projects/'+project.id+'/glyphs/'+selected,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  await refresh();message('文字を再処理しました');
});
$('build-font').onclick=()=>safe(build);
$('export-project').onclick=()=>{if(project)dl('/projects/'+project.id+'/archive','HandwriteFont-project.zip');};
$('text-preview').oninput=preview;
$('load-font').onclick=()=>safe(async()=>{
  if(!report)await build();
  const face=new FontFace('KSWritingPreview','url(/api/projects/'+project.id+'/exports/'+encodeURIComponent(report.files.ttf)+')');
  await face.load();document.fonts.add(face);$('font-preview').style.fontFamily='KSWritingPreview,sans-serif';preview();
});
$('clear-corners').onclick=resetCorners;
$('corner-mode').onchange=()=>{
  const file=$('scan-files').files[0],canvas=$('corner-canvas');
  if(!$('corner-mode').checked){canvas.style.display='none';return;}
  if(!file||!file.type.startsWith('image/')){message('画像ファイルを選んでください',true);return;}
  const url=URL.createObjectURL(file),img=new Image();
  img.onload=()=>{picture=img;canvas.style.display='block';resetCorners();URL.revokeObjectURL(url);};
  img.src=url;
};
$('scan-files').onchange=()=>{if($('corner-mode').checked)$('corner-mode').onchange();};
$('corner-canvas').onclick=e=>{
  if(!picture||corners.length===4)return;
  const rect=e.currentTarget.getBoundingClientRect();
  corners.push([Math.round((e.clientX-rect.left)/rect.width*picture.width),
                Math.round((e.clientY-rect.top)/rect.height*picture.height)]);
  paintCorners();
};
safe(projects);
