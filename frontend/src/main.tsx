import React, { useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Variant = {threshold:number;smooth:number;x_shift:number;y_shift:number;directory:string};
type Glyph = {codepoint:number;char:string;variants:Variant[];selected:number};
type Project = {id:string;font_name:string;target_count:number;scanned_count:number;missing_count:number;pages:number;cols:number;rows:number;charset_preview:string;glyphs:Glyph[]};
type Report = {generated:number;missing_count:number;files:{ttf:string;otf:string}};
type PageResult = {status:string;page?:number;accepted?:number[];error?:string};
type Notice = {text:string;error:boolean};
type Tab = 'sheet'|'scan'|'glyphs'|'preview'|'export';

async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const result = await fetch('/api'+path,init);
  if (!result.ok) {
    const info: {detail?:unknown} = await result.json().catch(()=>({detail:result.statusText}));
    throw new Error(typeof info.detail==='string'?info.detail:JSON.stringify(info.detail));
  }
  return result.json() as Promise<T>;
}
function download(path:string,name:string) {
  const a=document.createElement('a');a.href='/api'+path;a.download=name;
  document.body.appendChild(a);a.click();a.remove();
}
function App() {
  const [projects,setProjects]=useState<Array<{id:string;font_name:string}>>([]);
  const [project,setProject]=useState<Project|null>(null);
  const [name,setName]=useState('K.Saga writing');
  const [charset,setCharset]=useState('all');
  const [custom,setCustom]=useState('');
  const [size,setSize]=useState('A4');
  const [orientation,setOrientation]=useState('portrait');
  const [cols,setCols]=useState(6);
  const [rows,setRows]=useState(8);
  const [tab,setTab]=useState<Tab>('sheet');
  const [files,setFiles]=useState<File[]>([]);
  const [manualPage,setManualPage]=useState('');
  const [selected,setSelected]=useState<number|null>(null);
  const [threshold,setThreshold]=useState(22);
  const [smooth,setSmooth]=useState(.0018);
  const [shiftX,setShiftX]=useState(0);
  const [shiftY,setShiftY]=useState(0);
  const [search,setSearch]=useState('');
  const [report,setReport]=useState<Report|null>(null);
  const [scanResult,setScanResult]=useState<PageResult[]>([]);
  const [notice,setNotice]=useState<Notice|null>(null);
  const [busy,setBusy]=useState(false);
  const [previewText,setPreviewText]=useState('私の文字で、文章を印刷する。\nK.Saga writing 2026');
  const [fontLoaded,setFontLoaded]=useState(false);
  const updateProjects=useCallback(async()=>setProjects(await api<Array<{id:string;font_name:string}>>('/projects')),[]);
  const open=useCallback(async(pid:string)=>{
    const p=await api<Project>('/projects/'+pid);setProject(p);setSelected(null);
    setTab('sheet');setReport(null);setFontLoaded(false);
  },[]);
  useEffect(()=>{void updateProjects().catch(e=>setNotice({text:String(e),error:true}));},[updateProjects]);
  const run=async(fn:()=>Promise<void>)=>{
    setBusy(true);setNotice(null);
    try {await fn();}catch(error){setNotice({text:error instanceof Error?error.message:String(error),error:true});}
    finally{setBusy(false);}
  };
  const refresh=async()=>{if(!project)return;setProject(await api<Project>('/projects/'+project.id));};
  const create=()=>void run(async()=>{
    const p=await api<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({font_name:name,charset,custom_text:custom,page_size:size,orientation,cols,rows})});
    await updateProjects();await open(p.id);setNotice({text:'プロジェクトを作成しました。記入用紙を印刷してください。',error:false});
  });
  const upload=()=>void run(async()=>{
    if(!project||!files.length)throw new Error('スキャンファイルを指定してください。');
    const form=new FormData();files.forEach(f=>form.append('files',f));
    if(manualPage)form.append('manual_page',String(Math.max(0,Number(manualPage)-1)));
    const result=await api<{pages:PageResult[]}>('/projects/'+project.id+'/scans',{method:'POST',body:form});
    setScanResult(result.pages);await refresh();
    const accepted=result.pages.reduce((n,p)=>n+(p.accepted?.length||0),0);
    setNotice({text:accepted+'文字を取り込みました。',error:!accepted});
    if(accepted) {
      try{setReport(await api<Report>('/projects/'+project.id+'/build',{method:'POST'}));}
      catch(e){setNotice({text:'取り込み済みですがフォント生成に失敗しました：'+String(e),error:true});}
    }
  });
  const build=()=>void run(async()=>{
    if(!project)return;setReport(await api<Report>('/projects/'+project.id+'/build',{method:'POST'}));
    setFontLoaded(false);setNotice({text:'TTFとOTFを生成・検証しました。',error:false});
  });
  const selection=project?.glyphs.find(g=>g.codepoint===selected);
  const selectedVersion=selection?.variants[selection.selected];
  useEffect(()=>{
    if(!selectedVersion)return;
    setThreshold(selectedVersion.threshold);setSmooth(selectedVersion.smooth);
    setShiftX(selectedVersion.x_shift||0);setShiftY(selectedVersion.y_shift||0);
  },[selected,selectedVersion?.directory]);
  const reprocess=()=>void run(async()=>{
    if(!project||selected===null)return;
    await api('/projects/'+project.id+'/glyphs/'+selected,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({threshold,smooth,x_shift:shiftX,y_shift:shiftY})});
    await refresh();setNotice({text:'文字を再処理して履歴に保存しました。',error:false});
  });
  const selectVersion=(n:number)=>void run(async()=>{
    if(!project||selected===null)return;
    await api('/projects/'+project.id+'/glyphs/'+selected+'/select/'+n,{method:'POST'});
    await refresh();
  });
  const applyFont=()=>void run(async()=>{
    if(!project||!report)throw Error('先にフォントを生成してください。');
    const url='/api/projects/'+project.id+'/exports/'+encodeURIComponent(report.files.ttf)+'?t='+Date.now();
    const font=new FontFace('HWF-Preview','url('+url+')');await font.load();
    document.fonts.add(font);setFontLoaded(true);
  });
  const chars=project?.glyphs.filter(g=>g.char.includes(search)||('U+'+g.codepoint.toString(16).toUpperCase()).includes(search.toUpperCase())).sort((a,b)=>a.codepoint-b.codepoint)||[];
  const missing=project?[...new Set(Array.from(previewText).filter(c=>c.trim()&&!project.glyphs.some(g=>g.codepoint===c.codePointAt(0))))]:[];
  const field=(title:string,value:number,set:(n:number)=>void,min:number,max:number,step:number=1)=>(
    <label>{title}<input type="number" min={min} max={max} step={step} value={value} onChange={e=>set(Number(e.target.value))}/></label>
  );
  return <div className="shell">
    <header className="topbar"><strong>H. / HandwriteFont</strong><span>LOCAL / PRIVATE · K.Saga writing</span></header>
    <main className="workspace">
      {notice&&<div className={notice.error?'warning':'success'} role="status">{notice.text}<button onClick={()=>setNotice(null)}>閉じる</button></div>}
      {!project?<><p className="section-kicker">FONT STUDIO / 01</p><h1>手書き文字を、<br/>使えるフォントに。</h1>
        <p className="lead">専用用紙に赤い0.7mmボールペンで記入し、スキャナーで読み込みます。データはローカルで処理されます。</p>
        <section className="panel"><h2>新規プロジェクト</h2><div className="form-grid">
          <label>フォント名<input value={name} onChange={e=>setName(e.target.value)}/></label>
          <label>文字集合<select value={charset} onChange={e=>setCharset(e.target.value)}><option value="all">常用漢字＋かな＋英数字・記号</option><option value="joyo">常用漢字 2,136字</option><option value="kana">ひらがな・カタカナ</option><option value="latin">英数字</option><option value="jis">JIS第1・第2水準</option><option value="custom">任意の文字</option></select></label>
          {charset==='custom'&&<label className="span2">収録する文字<textarea rows={4} value={custom} onChange={e=>setCustom(e.target.value)}/></label>}
          <label>用紙<select value={size} onChange={e=>setSize(e.target.value)}><option>A4</option><option>A3</option></select></label>
          <label>向き<select value={orientation} onChange={e=>setOrientation(e.target.value)}><option value="portrait">縦</option><option value="landscape">横</option></select></label>
          {field('列数',cols,setCols,2,12)}{field('行数',rows,setRows,2,18)}
        </div><div className="toolbar"><button disabled={busy} onClick={create} className="primary">プロジェクトを作成</button></div></section>
        <section className="panel"><h2>保存済みのプロジェクト</h2><div className="toolbar">{projects.map(p=><button key={p.id} onClick={()=>void run(()=>open(p.id))}>{p.font_name}</button>)}</div>
          <label>プロジェクトZIPを読み込む<input type="file" accept=".zip" onChange={e=>{const f=e.target.files?.[0];if(!f)return;void run(async()=>{const form=new FormData();form.append('file',f);const p=await api<Project>('/projects/import',{method:'POST',body:form});await open(p.id);await updateProjects();});}}/></label>
        </section>
      </>:<><button className="text-button" onClick={()=>{setProject(null);void updateProjects();}}>← プロジェクト一覧</button>
        <p className="section-kicker">PROJECT / HANDWRITING</p><h1>{project.font_name}</h1><p className="muted">{project.scanned_count} / {project.target_count} 文字取り込み済み ／ 未収録 {project.missing_count} ／ {project.pages} ページ</p>
        <div className="progress"><div style={{width:100*project.scanned_count/project.target_count+'%'}}/></div>
        <nav className="nav">{([['sheet','01 / 用紙'],['scan','02 / スキャン'],['glyphs','03 / 文字編集'],['preview','04 / プレビュー'],['export','05 / フォント出力']] as [Tab,string][]).map(([key,title])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{title}</button>)}</nav>
        {tab==='sheet'&&<section className="panel"><h2>記入用紙PDF</h2><p className="help">倍率100%で印刷し、赤い0.7mmのボールペンで指定文字を1文字ずつ記入してください。四隅の黒いマーカーを切り取らないでください。</p><div className="mini-grid">{Array.from(project.charset_preview).slice(0,48).map((c,i)=><div key={i}>{c}</div>)}</div><div className="toolbar"><button className="primary" onClick={()=>download('/projects/'+project.id+'/template','HandwriteFont-template.pdf')}>用紙PDFを保存</button></div></section>}
        {tab==='scan'&&<section className="panel"><h2>スキャン画像を読み込む</h2><p className="help">PNG・JPEG・TIFF・PDFを読み込み、用紙に印刷されたQRコードで文字を対応づけます。</p>
          <input type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.pdf" multiple onChange={e=>setFiles(Array.from(e.target.files||[]))}/>
          <details><summary>QRが読み取れない場合</summary><label>手動ページ番号（1始まり）<input type="number" min={1} value={manualPage} onChange={e=>setManualPage(e.target.value)}/></label></details>
          <div className="toolbar"><button className="primary" disabled={busy||!files.length} onClick={upload}>スキャンを取り込む</button></div>
          {scanResult.map((p,i)=><p key={i} className={p.status==='ok'?'success':'warning'}>{p.status==='ok'?'ページ '+((p.page||0)+1)+': '+(p.accepted?.length||0)+'文字を保存':p.error}</p>)}
        </section>}
        {tab==='glyphs'&&<section className="panel"><h2>文字を確認・再処理</h2><div className="editor"><aside><input placeholder="文字 / U+3042" value={search} onChange={e=>setSearch(e.target.value)}/><div className="glyph-grid">{chars.map(g=><button className={selected===g.codepoint?'active':''} key={g.codepoint} onClick={()=>setSelected(g.codepoint)}>{g.char}</button>)}</div></aside>
          <article>{selection&&selected!==null?<><h2>{selection.char}　U+{selected.toString(16).toUpperCase()}</h2><div className="comparison">{(['raw','mask','svg'] as const).map(kind=><div key={kind}><img src={'/api/projects/'+project.id+'/glyphs/'+selected+'/asset/'+kind+'?v='+selection.selected} alt={kind}/><small>{kind}</small></div>)}</div>
            <div className="form-grid">{field('赤色抽出閾値',threshold,setThreshold,1,150)}{field('輪郭の平滑化',smooth,setSmooth,0,.03,.0001)}{field('横移動',shiftX,setShiftX,-200,200)}{field('縦移動',shiftY,setShiftY,-200,200)}</div>
            <div className="toolbar">{selection.variants.map((_,i)=><button key={i} className={i===selection.selected?'active':''} onClick={()=>selectVersion(i)}>v{i+1}</button>)}<button className="primary" disabled={busy} onClick={reprocess}>再処理</button></div>
          </>:<p className="help">左側の一覧から文字を選択してください。</p>}</article></div></section>}
        {tab==='preview'&&<section className="panel"><h2>フォントのプレビュー</h2><textarea rows={4} value={previewText} onChange={e=>setPreviewText(e.target.value)}/><div className="preview-page" style={{fontFamily:fontLoaded?'HWF-Preview, sans-serif':'sans-serif'}}>{previewText}</div><p className="muted">未収録：{missing.slice(0,40).join(' ')||'なし'}</p><button className="primary" disabled={busy||!report} onClick={applyFont}>生成済みフォントを適用</button></section>}
        {tab==='export'&&<section className="panel"><h2>フォントを生成・保存</h2><p className="help">TTF（glyf）とOTF（CFF）を生成し、読み戻してUnicode対応を検証します。</p><div className="toolbar"><button className="primary" disabled={busy||project.scanned_count===0} onClick={build}>TTF・OTF生成</button><button onClick={()=>download('/projects/'+project.id+'/archive','HandwriteFont-project.zip')}>プロジェクトZIP</button></div>
          {report&&<><p>{report.generated}文字生成 ／ 未収録 {report.missing_count}文字</p><div className="toolbar"><button onClick={()=>download('/projects/'+project.id+'/exports/'+report.files.ttf,report.files.ttf)}>TTFダウンロード</button><button onClick={()=>download('/projects/'+project.id+'/exports/'+report.files.otf,report.files.otf)}>OTFダウンロード</button><button onClick={()=>download('/projects/'+project.id+'/exports/validation.json','validation.json')}>検証結果JSON</button></div></>}
        </section>}
      </>}
      <footer>HandwriteFont v0.1.0 · フォントの個人利用のみ・二次配布禁止</footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
