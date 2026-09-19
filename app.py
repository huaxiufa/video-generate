import streamlit as st
from pipeline import generate_shot, DEFAULT_VOICES

st.set_page_config(page_title="Agnes Video Generator",page_icon="🎬",layout="wide")
st.title("🎬 Agnes Video Generator")
st.caption("Agnes 视频 + Edge TTS + 实际时间轴 + 中文字幕 + 自动延长画面")

with st.sidebar:
 st.header("Agnes 设置")
 base_url=st.text_input("API Base URL","https://apihub.agnes-ai.com/v1")
 api_key=st.text_input("API Key",type="password")
 model=st.text_input("Video Model","agnes-video-2.5-flash")
 st.divider(); st.header("角色声音")
 voices={n:st.text_input(n,v) for n,v in DEFAULT_VOICES.items()}

a,b=st.columns(2)
with a:
 shot_id=st.number_input("Shot ID",1,9999,4)
 seconds=st.slider("画面时长（秒）",4,20,8)
 scene=st.text_input("场景","深夜公寓")
 action=st.text_area("画面动作","人物站在门口，观察室内环境。")
 camera=st.text_input("镜头","slow push-in, cinematic")
 atmosphere=st.text_input("氛围","冷色、安静、悬疑、写实动画")
with b:
 st.subheader("对白")
 dialogue=st.text_area("每行：角色|台词","韩成|先别碰现场。\n警员|已经确认身份了。\n韩成|把附近监控调出来。",height=180)
 st.info("最终时长根据真实 TTS 自动计算；对白超出画面时自动延长最后画面。")

if st.button("🚀 生成测试镜头",type="primary"):
 if not api_key: st.error("请先填写 Agnes API Key")
 else:
  try:
   with st.spinner("正在生成 Agnes 画面、TTS、字幕并合成……"):
    result=generate_shot(api_key,base_url,model,int(shot_id),int(seconds),scene,action,camera,atmosphere,dialogue,voices)
   st.success("生成完成")
   st.video(str(result["final"]))
   with open(result["final"],"rb") as f: st.download_button("⬇️ 下载 MP4",f,file_name=result["final"].name)
   st.subheader("TTS 时间轴"); st.json(result["timeline"])
  except Exception as e: st.exception(e)
