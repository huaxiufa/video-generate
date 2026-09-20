(()=>{const K='night_agency_tts';
const characterVoices={
 '林默':{gender:'male',age:18,style:'年轻男性，安静克制，观察力强，低沉但清晰，略带少年感',voice:'Puck'},
 '苏晚':{gender:'female',age:23,style:'年轻女性，理性冷静，语气干练，成熟而有距离感',voice:'Kore'},
 '顾言':{gender:'male',age:26,style:'年轻男性，安静理工型，声音平稳，语速偏慢，冷静专业',voice:'Charon'},
 '韩成':{gender:'male',age:38,style:'成年男性，经验丰富，沉稳可靠，警察办案口吻，自然克制',voice:'Fenrir'},
 '周启':{gender:'male',age:42,style:'中年男性，表面温和客气，实际紧张，语气克制而略显心虚',voice:'Gacrux'},
 '沈哲':{gender:'male',age:34,style:'成年男性，普通职员，疲惫谨慎，声音自然，略带压力感',voice:'Achird'},
 '陈凯':{gender:'male',age:34,style:'成年男性，普通同事，紧张心虚，说话略快但不夸张',voice:'Zephyr'},
 '旁白':{gender:'neutral',age:30,style:'中性电影旁白，低沉、冷静、克制，带都市悬疑纪录片质感',voice:'Charon'}
};
const defaults={provider:'gemini_moss',model:'gemini-3.1-flash-tts-preview'};
const saved=JSON.parse(localStorage.getItem(K)||'{}');
const state=Object.assign({speed:1.0,roleSpeeds:{},forceGemini:{}},defaults,saved);
const SPEEDS=[0.8,0.9,1.0,1.1,1.2];
const roles=Object.keys(characterVoices);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const oldPanel=document.getElementById('night-agency-voice-panel'); if(oldPanel) oldPanel.remove();
const panel=document.createElement('div');
panel.id='night-agency-voice-panel';
panel.style.cssText='position:fixed;right:18px;top:18px;z-index:99999;background:rgba(20,20,24,.96);color:#fff;padding:14px 16px;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.35);font:13px system-ui;min-width:270px';
panel.innerHTML='<b>🌙 夜行事务所语音</b>'+
'<div style="margin-top:8px;opacity:.78">角色音色由人物设定自动匹配<br>无需手动选择声音</div>'+
'<label style="display:block;margin-top:10px">当前角色<select id=na-r style="width:100%;margin-top:4px;padding:5px">'+roles.map(x=>'<option>'+x+'</option>').join('')+'</select></label>'+
'<label style="display:block;margin-top:10px">全局语速<select id=na-speed style="width:100%;margin-top:4px;padding:5px">'+SPEEDS.map(x=>'<option value="'+x+'">'+x+'×</option>').join('')+'</select></label>'+
'<label style="display:block;margin-top:8px">当前角色语速<select id=na-role-speed style="width:100%;margin-top:4px;padding:5px">'+SPEEDS.map(x=>'<option value="'+x+'">'+x+'×</option>').join('')+'</select></label>'+
'<div id=na-info style="margin-top:8px;line-height:1.5"></div>'+
'<button id=na-s style="width:100%;margin-top:8px;padding:6px;border:0;border-radius:8px;background:#7c5cff;color:#fff">保存角色配置</button><button id=na-g style="width:100%;margin-top:6px;padding:6px;border:1px solid #7c5cff;border-radius:8px;background:transparent;color:#fff">重新用 Gemini 建立该角色声音</button>'+
'<small id=na-t style="display:block;margin-top:8px;opacity:.75">首次使用角色调用 Gemini，之后自动使用该角色的声音。</small>';
document.body.appendChild(panel);
const $=x=>document.getElementById(x);
function updateInfo(){
 const c=characterVoices[$('na-r').value];
 $('na-info').innerHTML='<b>'+esc($('na-r').value)+'</b><br>性别：'+c.gender+'　年龄：'+c.age+'<br>人物音色：'+esc(c.style)+'<br>Gemini 音色：'+c.voice;
}
$('na-r').value=state.role||'林默';
$('na-speed').value=String(state.speed||1.0);
function roleSpeed(){return Number((state.roleSpeeds||{})[$('na-r').value]||state.speed||1.0)} function forceGemini(){return state.forceGemini&&state.forceGemini[$('na-r').value]?'1':'0'}
$('na-role-speed').value=String(roleSpeed());
$('na-r').onchange=()=>{state.role=$('na-r').value;updateInfo();$('na-role-speed').value=String(roleSpeed())};
$('na-speed').onchange=()=>{state.speed=Number($('na-speed').value);$('na-role-speed').value=String(roleSpeed())};
$('na-role-speed').onchange=()=>{state.roleSpeeds=state.roleSpeeds||{};state.roleSpeeds[$('na-r').value]=Number($('na-role-speed').value)};
$('na-s').onclick=()=>{localStorage.setItem(K,JSON.stringify(state));$('na-t').textContent='已保存：'+state.role+'。首次/重建用 Gemini，后续自动用声音克隆。'}; $('na-g').onclick=()=>{state.forceGemini=state.forceGemini||{};state.forceGemini[$('na-r').value]=true;localStorage.setItem(K,JSON.stringify(state));$('na-t').textContent='已标记：下一次生成该角色会重新调用 Gemini，之后恢复克隆。'};
const oldAudioCards=()=>{document.querySelectorAll('.glass-card').forEach(card=>{const t=(card.innerText||'').trim();if(/音频配置|Audio Config|voice role|speech rate/i.test(t)&&/启用旁白|enable narration/i.test(t))card.remove();});};
oldAudioCards();
const origFetch=window.fetch;
window.fetch=async function(input,init={}){
 try{
  const url=typeof input==='string'?input:(input&&input.url)||'';
  if(/\/api\/tasks\/(creative|manuscript|anchor|poetry|simple)/.test(url)&&init.body instanceof FormData){
   const role=state.role||'林默', c=characterVoices[role]||characterVoices['林默'];
   if(state.provider==='gemini_moss'){
    init.body.set('audio_enabled','true');
    const fg=forceGemini(); init.body.set('audio_voice','__NA_TTS__|gemini_moss|'+role+'|'+c.voice+'|'+state.model+'|'+roleSpeed()+'|'+fg); if(fg==='1'){state.forceGemini[role]=false;localStorage.setItem(K,JSON.stringify(state));}
   }
  }
 }catch(e){}
 return origFetch.call(this,input,init);
};


// ── 夜行事务所：清理原作者/原站导流 UI，并把「创意」入口改成剧本编辑区 ──
function cleanOriginalUi(){
  const body=document.body;
  if(!body) return;
  // 原作者的支持项目、快速入口、官网资源、Demo/GitHub 等均不属于本项目 UI。
  body.querySelectorAll('a[href*="lichuanyang.top"], a[href*="github.com/lcy362"]').forEach(a=>{
    const wrap=a.closest('nav,footer,aside,.sidebar-card');
    if(wrap) wrap.style.display='none'; else a.style.display='none';
  });
  body.querySelectorAll('aside').forEach(aside=>{
    const txt=(aside.innerText||'').trim();
    if(!txt || (/支持项目|快速入口/.test(txt) && !aside.querySelector('[class*="timeline"], [class*="Timeline"]'))){
      aside.style.display='none';
    }
  });
  body.querySelectorAll('.sidebar-card').forEach(card=>{
    const text=(card.innerText||'').trim();
    if(/支持项目|快速入口|给个 Star|更多创作方向|在线体验|Prompt 技巧|API 文档|模型概览/.test(text)){
      card.style.display='none';
    }
  });
  body.querySelectorAll('nav,footer').forEach(el=>{
    const text=(el.innerText||'').trim();
    if(/Demo|Home|Guides|FAQ|GitHub|快速入口|更多资源/.test(text)) el.style.display='none';
  });
  const h1=[...body.querySelectorAll('h1')].find(x=>/Agnes Video Generator/i.test(x.textContent||''));
  if(h1) h1.textContent='夜行事务所';
  const title=[...body.querySelectorAll('p')].find(x=>/AI 视频，一键生成/.test(x.textContent||''));
  if(title) title.textContent='都市悬疑动画 · 剧本成片工作台';
  document.title='夜行事务所｜动画剧本工作台';

  body.querySelectorAll('.glass-card').forEach(card=>{ const text=(card.innerText||'').trim(); if(/音频配置|Audio Config|音色|voice role|speech rate/i.test(text) && /启用旁白|enable narration/i.test(text)){ card.style.display='none'; } });
  // 主入口：保留原 Creative Pipeline，但把“创意”字段明确变成剧本输入框。
  const labels=[...body.querySelectorAll('label')];
  labels.forEach(label=>{
    const txt=(label.textContent||'').trim();
    if(/^创意$|^Idea$/i.test(txt)){
      label.textContent='剧本';
    }
  });
  const textareas=[...body.querySelectorAll('textarea')];
  textareas.forEach(ta=>{
    const ph=(ta.getAttribute('placeholder')||'').toLowerCase();
    const near=(ta.parentElement?.innerText||'').toLowerCase();
    if(/idea|创意/.test(ph+' '+near) && !/api key|提示词/.test(near)){
      ta.setAttribute('placeholder','在这里粘贴《夜行事务所》剧本……\\n\\n建议格式：场景 / 时间 / 人物 / 动作 / 对白。\\n系统会根据剧本生成分镜、视频、角色配音和字幕。');
      ta.style.minHeight='260px';
    }
  });
}
cleanOriginalUi();
new MutationObserver(cleanOriginalUi).observe(document.body,{childList:true,subtree:true});
