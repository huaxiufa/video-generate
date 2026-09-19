import json
from pathlib import Path
import zipfile, tempfile
import streamlit as st
from pipeline import DEFAULT_VOICES, generate_shot, list_chinese_voices, synthesize_preview, generate_character_voice_pack
from script_parser import analyze_script, save_storyboard

ROOT=Path(__file__).resolve().parent; DATA=ROOT/"cache"; DATA.mkdir(exist_ok=True)
STORY=DATA/"storyboard.json"; SETTINGS=DATA/"project.json"
st.set_page_config(page_title="夜行事务所 · AI 动画工作台",page_icon="🎬",layout="wide")
st.title("🎬 夜行事务所 · AI 动画工作台")
st.caption("正常写剧本 → Agnes AI 自动理解人物、台词、场景与分镜 → 审核 → Agnes 动画 → TTS → 中文字幕 → 成片。")

def load(p,d):
    try:return json.loads(p.read_text("utf-8"))
    except:return d

project=load(SETTINGS,{"voices":DEFAULT_VOICES.copy(),"voice_settings":{}})
try:
    VOICE_OPTIONS=list_chinese_voices()
except Exception:
    VOICE_OPTIONS=sorted(set(DEFAULT_VOICES.values()))
with st.sidebar:
    st.header("Agnes 设置")
    api_key=st.text_input("Agnes API Key",type="password")
    base_url=st.text_input("API Base URL","https://apihub.agnes-ai.com/v1")
    text_model=st.text_input("剧本/分镜 AI Model","agnes-3.0-flash")
    video_model=st.text_input("动画 Video Model","agnes-video-2.5-flash")
    st.divider(); st.header("角色声音（全项目复用）")
    for role in list(project["voices"]):
        current=project["voices"].get(role, DEFAULT_VOICES.get(role, VOICE_OPTIONS[0]))
        if current not in VOICE_OPTIONS: VOICE_OPTIONS=[current]+VOICE_OPTIONS
        project["voices"][role]=st.selectbox(role,VOICE_OPTIONS,index=VOICE_OPTIONS.index(current),key="voice_"+role)
        cfg=project["voice_settings"].get(role,{})
        project["voice_settings"][role]={"rate":st.text_input(role+" 语速",cfg.get("rate","+0%"),key="rate_"+role),"pitch":st.text_input(role+" 音高",cfg.get("pitch","+0Hz"),key="pitch_"+role),"volume":"+0%"}
    st.markdown("### 📦 导入角色声音包")
    voice_zip=st.file_uploader("上传 night-agency-voices.zip",type=["zip"],key="voice_zip")
    if voice_zip is not None and st.button("⬆️ 导入并覆盖角色声音",key="import_voice_pack"):
        try:
            with tempfile.TemporaryDirectory() as td:
                zp=Path(td)/"voices.zip"
                zp.write_bytes(voice_zip.getvalue())
                with zipfile.ZipFile(zp) as z: z.extractall(td)
                candidates=list(Path(td).rglob("voices.json"))
                if not candidates: raise RuntimeError("声音包中没有 voices.json")
                manifest=json.loads(candidates[0].read_text("utf-8"))
                imported=0
                for role,info in manifest.items():
                    if role in project["voices"] and info.get("voice"):
                        project["voices"][role]=info["voice"]
                        if info.get("settings"): project["voice_settings"][role]=info["settings"]
                        imported+=1
                SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8")
                st.success(f"已导入 {imported} 个角色声音。请刷新页面确认。")
        except Exception as e:
            st.error(f"声音包导入失败：{e}")
    if st.button("试听当前角色"):
        role=st.selectbox("试听角色",list(project["voices"]),key="preview_role")
        try:
            preview=synthesize_preview("这是一段声音试听。",project["voices"][role])
            st.audio(preview,format="audio/mp3")
        except Exception as e: st.error(f"试听失败：{e}")
    if st.button("🎁 生成全部角色声音包"):
        try:
            with st.status("正在生成 9 个角色的声音试听包…",expanded=True) as s:
                zip_path, manifest=generate_character_voice_pack(project["voices"],project["voice_settings"],lambda msg: s.write(msg))
                s.update(label="声音包生成完成",state="complete")
            with open(zip_path,"rb") as f:
                st.download_button("⬇️ 下载 night-agency-voices.zip",f,file_name="night-agency-voices.zip",mime="application/zip")
        except Exception as e:
            st.error(f"声音包生成失败：{e}")
    if st.button("保存声音配置"):
        SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8"); st.success("已保存")

t1,t2,t3=st.tabs(["① 写剧本","② 审核分镜","③ 生成成片"])
with t1:
    script=st.text_area("完整剧本",height=520,placeholder="""直接写正常剧本，不要写“角色|台词”。
例如：
第一场 公寓·凌晨
警笛声从远处传来。
韩成走进客厅，示意警员停下。
先别碰现场。
警员停在门口。
已经确认身份了。
林默站在门外，没有进去。
苏晚看了他一眼。
你又发现什么了？
林默盯着桌上的手机。
时间不对。

系统会自动判断“先别碰现场”是谁说的，并把角色只用于 TTS。
最终字幕只显示：
先别碰现场。
不会显示“韩成：先别碰现场。”""")
    if st.button("🧠 用 Agnes AI 自动分析剧本并生成分镜",type="primary"):
        if not script.strip(): st.error("请先输入剧本")
        elif not api_key: st.error("请先填写 Agnes API Key")
        else:
            with st.status("Agnes 正在理解剧本并拆分镜头…",expanded=True) as s:
                try:
                    data=analyze_script(script,api_key,base_url,text_model)
                    save_storyboard(data,STORY)
                    s.update(label=f"完成：{len(data['scenes'])} 个场景，{len(data['shots'])} 个镜头",state="complete")
                    if data.get("warnings"):
                        st.warning("需要人工确认的内容：")
                        for w in data["warnings"]: st.write("• "+w)
                except Exception as e:
                    s.update(label="剧本分析失败",state="error"); st.exception(e)
with t2:
    data=load(STORY,{"scenes":[],"shots":[],"warnings":[]})
    if not data["shots"]: st.info("先在“写剧本”中让 Agnes AI 分析剧本。")
    else:
        st.subheader(f"分镜审核 · {len(data['shots'])} 个镜头")
        if data.get("warnings"):
            st.warning("Agnes 标记了可能需要确认的台词说话人。下面的 role 可以直接修改。")
            for w in data["warnings"]: st.write("• "+w)
        for i,shot in enumerate(data["shots"]):
            with st.expander(f"Shot {shot['id']:03d} · {shot['scene']} · {shot['duration']}s",expanded=i==0):
                shot["duration"]=st.number_input("时长",4,20,int(shot["duration"]),key=f"d{i}")
                sizes=["特写","近景","中近景","中景","全景"]
                shot["shot_size"]=st.selectbox("景别",sizes,index=sizes.index(shot.get("shot_size","中景")) if shot.get("shot_size","中景") in sizes else 3,key=f"s{i}")
                shot["camera"]=st.text_input("镜头运动",shot.get("camera",""),key=f"c{i}")
                shot["visual"]=st.text_area("画面",shot.get("visual",""),key=f"v{i}")
                st.caption("字幕只显示台词正文，不显示角色名。角色名仅供 TTS 使用。")
                for j,d in enumerate(shot.get("dialogue",[])):
                    cols=st.columns([1,3])
                    d["role"]=cols[0].text_input("说话人",d.get("role",""),key=f"r{i}_{j}")
                    d["text"]=cols[1].text_input("台词",d.get("text",""),key=f"t{i}_{j}")
        if st.button("💾 保存分镜修改"):
            save_storyboard(data,STORY); st.success("已保存")

with t3:
    data=load(STORY,{"scenes":[],"shots":[]})
    st.subheader("生成成片")
    if st.button("🚀 开始生成整集",type="primary",disabled=not bool(data["shots"])):
        if not api_key: st.error("请填写 Agnes API Key")
        else:
            bar=st.progress(0); status=st.empty()
            for n,shot in enumerate(data["shots"],1):
                def progress(stage,msg): status.info(f"[{stage}] {msg}")
                try:
                    final,cues=generate_shot(api_key,base_url,video_model,shot,project["voices"],project["voice_settings"],progress)
                    st.video(str(final))
                    with open(final,"rb") as f: st.download_button(f"下载 Shot {shot['id']:03d}",f,file_name=final.name,key=f"dl{shot['id']}")
                except Exception as e: st.error(f"Shot {shot['id']:03d} 失败：{e}"); st.stop()
                bar.progress(n/len(data["shots"]))
            st.success("整集生成完成。")
