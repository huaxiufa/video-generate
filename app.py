import json, zipfile, tempfile
from pathlib import Path
import streamlit as st
from pipeline import DEFAULT_VOICES, GEMINI_VOICES, GEMINI_VOICE_PROFILES, GEMINI_TTS_MODEL, AGNES_VIDEO_MODELS, GEMINI_TTS_MODELS, generate_shot, list_chinese_voices, synthesize_preview, generate_character_voice_pack, build_segments, render_episode
from script_parser import analyze_script, save_storyboard

ROOT=Path(__file__).resolve().parent; DATA=ROOT/"cache"; DATA.mkdir(exist_ok=True)
STORY=DATA/"storyboard.json"; SETTINGS=DATA/"project.json"
st.set_page_config(page_title="夜行事务所 · AI 动画工作台",page_icon="🎬",layout="wide")
st.title("🎬 夜行事务所 · AI 动画工作台")
st.caption("完整剧本 → Agnes AI 自动拆分约12秒剧情片段 → 分镜动画 → 中文 TTS → 中文字幕 → 片段拼接 → 整集成片。")

def load(p,d):
    try:return json.loads(p.read_text("utf-8"))
    except:return d

project=load(SETTINGS,{"voices":DEFAULT_VOICES.copy(),"voice_settings":{},"video_model":"agnes-video-2.5-flash","gemini_tts_model":GEMINI_TTS_MODEL})
project.setdefault("voices",DEFAULT_VOICES.copy()); project.setdefault("voice_settings",{})
project.setdefault("video_model","agnes-video-2.5-flash"); project.setdefault("gemini_tts_model",GEMINI_TTS_MODEL)
try: VOICE_OPTIONS=list_chinese_voices()
except Exception: VOICE_OPTIONS=sorted(set(DEFAULT_VOICES.values()))
with st.sidebar:
    st.header("Agnes 设置")
    api_key=st.text_input("Agnes API Key",type="password")
    base_url=st.text_input("API Base URL","https://apihub.agnes-ai.com/v1")
    text_model=st.text_input("剧本/分镜 AI Model","agnes-3.0-flash")
    st.markdown("### 🎞️ Agnes 视频模型版本")
    video_options=list(AGNES_VIDEO_MODELS.keys())+["自定义"]
    saved_video=project.get("video_model","agnes-video-2.5-flash")
    video_choice=saved_video if saved_video in video_options else "自定义"
    video_model=st.selectbox("视频模型",video_options,index=video_options.index(video_choice))
    if video_model=="自定义":
        video_model=st.text_input("自定义 Agnes 视频 Model",saved_video if saved_video not in video_options else "agnes-video-2.5-flash")
    st.caption(AGNES_VIDEO_MODELS.get(video_model,"自定义模型；参数协议按模型名自动判断。"))
    project["video_model"]=video_model
    st.divider(); st.header("🔊 配音引擎")
    tts_provider=st.radio("选择配音",["Gemini TTS","Gemini首句 + MOSS-TTS-Nano续配音","Edge TTS"],index=0,key="tts_provider")
    gemini_api_key=st.text_input("Gemini API Key",type="password",help="Google AI Studio / Gemini API Key")
    st.markdown("### 🎙️ Gemini TTS 模型版本")
    gemini_options=list(GEMINI_TTS_MODELS.keys())+["自定义"]
    saved_gemini=project.get("gemini_tts_model",GEMINI_TTS_MODEL)
    gemini_choice=saved_gemini if saved_gemini in gemini_options else "自定义"
    gemini_model=st.selectbox("Gemini TTS 模型",gemini_options,index=gemini_options.index(gemini_choice))
    if gemini_model=="自定义":
        gemini_model=st.text_input("自定义 Gemini TTS Model",saved_gemini if saved_gemini not in gemini_options else GEMINI_TTS_MODEL)
    st.caption(GEMINI_TTS_MODELS.get(gemini_model,"自定义 Gemini TTS 模型。"))
    project["gemini_tts_model"]=gemini_model
    if tts_provider=="Gemini TTS":
        st.caption("每句对白由 Gemini TTS 生成；相同台词会命中缓存。")
    elif tts_provider=="Gemini首句 + MOSS-TTS-Nano续配音":
        st.caption("每个角色第一次出现时只调用一次 Gemini，保存为声音母带；以后同一角色的新台词全部交给 MOSS-TTS-Nano，不再调用 Gemini。")
    st.divider(); st.header("角色声音（全项目复用）")
    for role in list(project["voices"]):
        current=project["voices"].get(role,DEFAULT_VOICES.get(role,VOICE_OPTIONS[0]))
        if current not in VOICE_OPTIONS: VOICE_OPTIONS=[current]+VOICE_OPTIONS
        if tts_provider=="Gemini TTS":
            gopts=list(GEMINI_VOICES.values()); gcurrent=GEMINI_VOICES.get(role,"Kore")
            st.selectbox(role+" · Gemini",gopts,index=gopts.index(gcurrent) if gcurrent in gopts else 0,key="gemini_voice_"+role,disabled=True)
            st.caption(GEMINI_VOICE_PROFILES.get(role,""))
        else:
            project["voices"][role]=st.selectbox(role,VOICE_OPTIONS,index=VOICE_OPTIONS.index(current),key="voice_"+role)
        cfg=project["voice_settings"].get(role,{})
        project["voice_settings"][role]={"rate":st.text_input(role+" 语速",cfg.get("rate","+0%"),key="rate_"+role),"pitch":st.text_input(role+" 音高",cfg.get("pitch","+0Hz"),key="pitch_"+role),"volume":"+0%"}
    st.markdown("### 📦 导入角色声音包")
    voice_zip=st.file_uploader("上传 night-agency-voices.zip",type=["zip"],key="voice_zip")
    if voice_zip is not None and st.button("⬆️ 导入并覆盖角色声音",key="import_voice_pack"):
        try:
            with tempfile.TemporaryDirectory() as td:
                zp=Path(td)/"voices.zip"; zp.write_bytes(voice_zip.getvalue())
                with zipfile.ZipFile(zp) as z: z.extractall(td)
                candidates=list(Path(td).rglob("voices.json"))
                if not candidates: raise RuntimeError("声音包中没有 voices.json")
                manifest=json.loads(candidates[0].read_text("utf-8")); imported=0
                for role,info in manifest.items():
                    if role in project["voices"] and info.get("voice"):
                        project["voices"][role]=info["voice"]
                        if info.get("settings"): project["voice_settings"][role]=info["settings"]
                        imported+=1
                SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8")
                st.success(f"已导入 {imported} 个角色声音。请刷新页面确认。")
        except Exception as e: st.error(f"声音包导入失败：{e}")
    if st.button("保存声音配置"):
        SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8"); st.success("已保存")

t1,t2,t3=st.tabs(["① 写剧本","② 审核12秒片段","③ 生成成片"])
with t1:
    script=st.text_area("完整剧本",height=520,placeholder="直接粘贴完整中文剧本。可以包含场景、动作、人物对白，不需要写角色|台词格式。")
    if st.button("🧠 用 Agnes AI 自动分析剧本并生成约12秒片段",type="primary"):
        if not script.strip(): st.error("请先输入剧本")
        elif not api_key: st.error("请先填写 Agnes API Key")
        else:
            with st.status("Agnes 正在理解完整剧本、人物、对白和12秒剧情段落…",expanded=True) as s:
                try:
                    data=analyze_script(script,api_key,base_url,text_model); save_storyboard(data,STORY)
                    s.update(label=f"完成：{len(data['scenes'])} 个场景，{len(data['segments'])} 个剧情片段，{len(data['shots'])} 个镜头",state="complete")
                    if data.get("warnings"):
                        st.warning("需要人工确认：")
                        for w in data["warnings"]: st.write("• "+w)
                except Exception as e: s.update(label="剧本分析失败",state="error"); st.exception(e)

with t2:
    data=load(STORY,{"scenes":[],"shots":[],"segments":[],"warnings":[]})
    if not data["shots"]: st.info("先在“写剧本”中分析完整剧本。")
    else:
        st.subheader(f"剧情片段 · 共 {len(data.get('segments',[]))} 段 · 目标约12秒/段")
        for seg in data.get("segments",[]):
            shots=[s for s in data["shots"] if s["id"] in seg["shot_ids"]]
            actual=sum(s["duration"] for s in shots)
            with st.expander(f"片段 {seg['segment_no']:03d} · {seg.get('title','')} · 约 {actual:.0f}s",expanded=False):
                st.caption(seg.get("summary",""))
                st.write("镜头顺序："," → ".join(f"{s['id']:03d}" for s in shots))
                if actual>16 or actual<8: st.warning("片段长度偏离12秒较多，可以调整下面镜头时长。")
                for shot in shots:
                    i=data["shots"].index(shot)
                    st.markdown(f"**Shot {shot['id']:03d} · {shot['scene']}**")
                    shot["duration"]=st.number_input("时长",4,12,int(shot["duration"]),key=f"d{i}")
                    shot["shot_size"]=st.selectbox("景别",["特写","近景","中近景","中景","全景"],index=["特写","近景","中近景","中景","全景"].index(shot.get("shot_size","中景")) if shot.get("shot_size","中景") in ["特写","近景","中近景","中景","全景"] else 3,key=f"s{i}")
                    shot["camera"]=st.text_input("镜头运动",shot.get("camera",""),key=f"c{i}")
                    shot["visual"]=st.text_area("画面",shot.get("visual",""),key=f"v{i}")
                    for j,d in enumerate(shot.get("dialogue",[])):
                        cols=st.columns([1,3]); d["role"]=cols[0].text_input("说话人",d.get("role",""),key=f"r{i}_{j}"); d["text"]=cols[1].text_input("台词",d.get("text",""),key=f"t{i}_{j}")
        if st.button("💾 保存分镜修改"):
            data["segments"]=build_segments(data["shots"],data.get("segments",[])); save_storyboard(data,STORY); st.success("已保存，片段时长已重新计算。")

with t3:
    data=load(STORY,{"scenes":[],"shots":[],"segments":[]})
    st.subheader("生成成片")
    if not data["shots"]: st.info("请先完成剧本分析。")
    else:
        st.write(f"当前：{len(data.get('segments',[]))} 个约12秒剧情片段，{len(data['shots'])} 个镜头。")
        current_tts_model = gemini_model if tts_provider == "Gemini TTS" else ("MOSS-TTS-Nano" if tts_provider == "Gemini首句 + MOSS-TTS-Nano续配音" else "Edge TTS")
        st.caption(f"当前视频模型：{video_model} · 当前 TTS 模型：{current_tts_model}")
        if st.button("🚀 开始生成整集",type="primary"):
            if not api_key: st.error("请填写 Agnes API Key")
            else:
                bar=st.progress(0); status=st.empty()
                def progress(stage,msg): status.info(f"[{stage}] {msg}")
                try:
                    if tts_provider in ("Gemini TTS","Gemini首句 + MOSS-TTS-Nano续配音") and not gemini_api_key:
                        raise RuntimeError("选择 Gemini 配音模式后请填写 Gemini API Key")
                    SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8")
                    episode, segments=render_episode(api_key,base_url,video_model,data,project["voices"],project["voice_settings"],progress,bar,{"Gemini TTS":"gemini","Gemini首句 + MOSS-TTS-Nano续配音":"gemini_moss","Edge TTS":"edge"}[tts_provider],gemini_api_key,gemini_model)
                    for seg_no, path in segments:
                        st.markdown(f"### 片段 {seg_no:03d}")
                        st.video(str(path))
                        with open(path,"rb") as f: st.download_button(f"下载片段 {seg_no:03d}",f,file_name=path.name,key=f"segdl{seg_no}")
                    st.markdown("### 🎬 完整一集")
                    st.video(str(episode))
                    with open(episode,"rb") as f: st.download_button("⬇️ 下载完整一集",f,file_name=episode.name,key="episode_download")
                    st.success("整集生成完成。")
                except Exception as e: st.error(f"生成失败：{e}")
