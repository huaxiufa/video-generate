import json
from pathlib import Path
import streamlit as st
from pipeline import DEFAULT_VOICES, generate_shot
from script_parser import analyze_script, save_storyboard
ROOT=Path(__file__).resolve().parent; DATA=ROOT/"cache"; DATA.mkdir(exist_ok=True)
STORY=DATA/"storyboard.json"; SETTINGS=DATA/"project.json"
st.set_page_config(page_title="夜行事务所 · AI 动画工作台",page_icon="🎬",layout="wide")
st.title("🎬 夜行事务所 · AI 动画工作台")
st.caption("只写剧本。系统负责理解剧本、拆场、分镜、配音、字幕、Agnes 动画与最终合成。")
def load(p,d):
    try:return json.loads(p.read_text("utf-8"))
    except:return d
project=load(SETTINGS,{"voices":DEFAULT_VOICES.copy(),"voice_settings":{}})
with st.sidebar:
    st.header("项目设置")
    api_key=st.text_input("Agnes API Key",type="password")
    base_url=st.text_input("API Base URL","https://apihub.agnes-ai.com/v1")
    model=st.text_input("Video Model","agnes-video-2.5-flash")
    st.divider(); st.header("角色声音（全项目复用）")
    for role in list(project["voices"]):
        project["voices"][role]=st.text_input(role,project["voices"][role],key="voice_"+role)
        cfg=project["voice_settings"].get(role,{})
        project["voice_settings"][role]={"rate":st.text_input(role+" 语速",cfg.get("rate","+0%"),key="rate_"+role),"pitch":st.text_input(role+" 音高",cfg.get("pitch","+0Hz"),key="pitch_"+role),"volume":"+0%"}
    if st.button("保存声音配置"):
        SETTINGS.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding="utf-8"); st.success("已保存")
t1,t2,t3=st.tabs(["① 写剧本","② 审核分镜","③ 生成成片"])
with t1:
    script=st.text_area("完整剧本",height=520,placeholder="直接粘贴正常剧本。台词不要写“角色名：”，系统会结合上下文判断说话人。\n\n第一场 公寓·凌晨\n警笛声从远处传来。\n韩成走进客厅。\n先别碰现场。\n林默站在门口。\n时间不对。")
    if st.button("🧠 自动分析剧本并生成分镜",type="primary"):
        if not script.strip(): st.error("请先输入剧本")
        else:
            data=analyze_script(script); save_storyboard(data,STORY); st.success(f"分析完成：{len(data['scenes'])} 个场景，{len(data['shots'])} 个镜头。"); st.rerun()
with t2:
    data=load(STORY,{"scenes":[],"shots":[]})
    if not data["shots"]: st.info("先在“写剧本”中分析剧本。")
    else:
        st.subheader(f"分镜审核 · {len(data['shots'])} 个镜头")
        for i,shot in enumerate(data["shots"]):
            with st.expander(f"Shot {shot['id']:03d} · {shot['scene']} · {shot['duration']}s",expanded=i==0):
                shot["duration"]=st.number_input("时长",4,20,int(shot["duration"]),key=f"d{i}")
                shot["shot_size"]=st.selectbox("景别",["特写","近景","中近景","中景","全景"],index=["特写","近景","中近景","中景","全景"].index(shot["shot_size"]),key=f"s{i}")
                shot["camera"]=st.text_input("镜头运动",shot["camera"],key=f"c{i}")
                shot["visual"]=st.text_area("画面",shot["visual"],key=f"v{i}")
                st.caption("台词仅用于配音与字幕，字幕不会显示角色名。")
                for d in shot.get("dialogue",[]): st.write(f"{d['role']} → {d['text']}")
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
                    final,cues=generate_shot(api_key,base_url,model,shot,project["voices"],project["voice_settings"],progress)
                    st.video(str(final))
                    with open(final,"rb") as f: st.download_button(f"下载 Shot {shot['id']:03d}",f,file_name=final.name,key=f"dl{shot['id']}")
                except Exception as e: st.error(f"Shot {shot['id']:03d} 失败：{e}"); st.stop()
                bar.progress(n/len(data["shots"]))
            st.success("整集生成完成。")
