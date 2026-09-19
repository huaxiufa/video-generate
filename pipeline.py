import json, os, subprocess, time
from pathlib import Path
import requests, edge_tts

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"; AUDIO=ROOT/"audio"; CACHE=ROOT/"cache"
for p in (OUT,AUDIO,CACHE): p.mkdir(exist_ok=True)

DEFAULT_VOICES={
"林默":"zh-CN-YunxiNeural","苏晚":"zh-CN-XiaoxiaoNeural","顾言":"zh-CN-YunyangNeural",
"零":"zh-CN-YunyangNeural","韩成":"zh-CN-YunyangNeural","警员":"zh-CN-YunxiNeural",
"沈哲":"zh-CN-YunxiNeural","陈凯":"zh-CN-YunxiNeural","周启":"zh-CN-YunyangNeural"}

def post_json(url,payload,headers,timeout=360,retries=5):
    for i in range(retries+1):
        try:
            r=requests.post(url,json=payload,headers=headers,timeout=timeout)
            if r.ok:return r.json()
            if r.status_code in (408,425,429,500,502,503,504) and i<retries:
                time.sleep(15*(i+1)); continue
            raise RuntimeError(f"Agnes HTTP {r.status_code}: {r.text[:1000]}")
        except requests.RequestException:
            if i>=retries: raise
            time.sleep(15*(i+1))

def generate_video(api_key,base_url,model,shot_id,seconds,scene,action,camera,atmosphere,progress=None):
    headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}
    payload={"model":model,"mode":"text","prompt":f"Animated cinematic shot. Scene: {scene}. Action: {action}. Camera: {camera}. Atmosphere: {atmosphere}. No dialogue, no text, no subtitles.","seconds":str(seconds),"size":"720P","aspect_ratio":"16:9","n":1}
    tasks=CACHE/"tasks.json"
    data=json.loads(tasks.read_text("utf-8")) if tasks.exists() else {}
    key=str(shot_id)
    video_url=data.get(key,{}).get("video_url")
    video_id=data.get(key,{}).get("video_id")

    if video_url:
        if progress: progress("Agnes", "已找到缓存的视频任务，准备下载")
    else:
        if not video_id:
            if progress: progress("Agnes", "正在提交视频任务……")
            res=post_json(base_url.rstrip("/")+"/videos",payload,headers)
            video_id=res.get("video_id") or res.get("id")
            if not video_id: raise RuntimeError(f"没有拿到 video_id: {res}")
            data[key]={"video_id":video_id}
            tasks.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
            if progress: progress("Agnes", f"任务已提交：{video_id}")
        deadline=time.time()+int(os.getenv("AGNES_POLL_TIMEOUT","1800"))
        last_status=None
        while True:
            if time.time()>deadline:
                raise TimeoutError(f"Agnes 任务超过 {os.getenv('AGNES_POLL_TIMEOUT','1800')} 秒仍未完成。video_id={video_id}。可检查 cache/tasks.json 后重试。")
            try:
                r=requests.get(base_url.rstrip("/")+"/agnesapi",params={"video_id":video_id,"model_name":model},headers=headers,timeout=60)
                r.raise_for_status(); st=r.json()
            except requests.RequestException as e:
                if progress: progress("Agnes", f"查询暂时失败，10 秒后重试：{e}")
                time.sleep(10); continue
            status=st.get("status")
            if status!=last_status:
                if progress: progress("Agnes", f"当前状态：{status or '未知'}")
                last_status=status
            if status=="completed":
                video_url=st.get("video_url") or st.get("output_url") or st.get("url")
                if not video_url: raise RuntimeError(f"完成但没有输出 URL: {st}")
                data[key]["video_url"]=video_url
                tasks.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                break
            if status in ("failed","error","cancelled"):
                raise RuntimeError(f"Agnes 任务失败：{st}")
            if status not in ("pending","in_progress"):
                raise RuntimeError(f"Agnes 返回了无法识别的状态：{st}")
            time.sleep(10)

    silent=OUT/f"shot_{shot_id:03d}_silent.mp4"
    if not silent.exists():
        if progress: progress("下载", "正在下载 Agnes 视频……")
        h={} if "platform-outputs.agnes-ai.space" in video_url else headers
        with requests.get(video_url,headers=h,stream=True,timeout=180) as r:
            r.raise_for_status()
            with open(silent,"wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:f.write(chunk)
    return silent

def probe(path):
    x=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],text=True)
    return float(x.strip())

def parse_dialogue(text):
    out=[]
    for line in text.splitlines():
        line=line.strip()
        if not line: continue
        if "|" in line: role,words=line.split("|",1)
        elif "：" in line: role,words=line.split("：",1)
        elif ":" in line: role,words=line.split(":",1)
        else: continue
        out.append((role.strip(),words.strip()))
    return out

async def make_tts(text,voice,path):
    await edge_tts.Communicate(text,voice,rate="+0%",pitch="+0Hz").save(str(path))

def build_timeline(dialogue,voices,shot_id,progress=None):
    import asyncio
    cues=[]; cursor=0.35
    for idx,(role,words) in enumerate(dialogue):
        audio=AUDIO/f"shot_{shot_id:03d}_{idx:02d}.mp3"
        if progress: progress("TTS", f"正在生成 {role} 的第 {idx+1} 段语音……")
        asyncio.run(make_tts(words,voices.get(role,DEFAULT_VOICES.get(role,"zh-CN-YunxiNeural")),audio))
        dur=probe(audio); start=cursor; end=start+dur
        cues.append({"role":role,"text":words,"audio":str(audio),"start":start,"end":end,"duration":dur})
        cursor=end+0.14
    return cues

def write_srt(cues,path):
    def ts(x):
        ms=int(round(x*1000)); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(path,"w",encoding="utf-8") as f:
        for i,c in enumerate(cues,1):
            f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['role']}：{c['text']}\n\n")

def render(silent,cues,shot_id,progress=None):
    if progress: progress("字幕", "正在生成字幕时间轴……")
    srt=OUT/f"shot_{shot_id:03d}.srt"; write_srt(cues,srt)
    audio_list=OUT/f"shot_{shot_id:03d}_audio.txt"
    with open(audio_list,"w",encoding="utf-8") as f:
        for c in cues:f.write(f"file '{Path(c['audio']).resolve()}'\n")
    audio=AUDIO/f"shot_{shot_id:03d}_mix.wav"
    if progress: progress("合成", "正在合并角色语音……")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(audio_list),"-c:a","pcm_s16le",str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    video_d=probe(silent); end=max([c["end"] for c in cues],default=0)+0.25
    target=max(video_d,end)
    base=silent
    if target>video_d+0.05:
        if progress: progress("合成", f"对白比画面长，延长最后画面到 {target:.1f}s")
        extended=OUT/f"shot_{shot_id:03d}_extended.mp4"
        subprocess.run(["ffmpeg","-y","-i",str(silent),"-vf",f"tpad=stop_mode=clone:stop_duration={target-video_d:.3f}","-t",f"{target:.3f}","-an","-c:v","libx264","-pix_fmt","yuv420p",str(extended)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
        base=extended
    final=OUT/f"shot_{shot_id:03d}_final.mp4"
    if progress: progress("字幕+合成", "正在烧录中文字幕并输出 MP4……")
    subtitle_filter=f"subtitles={srt}:force_style='FontName=Noto Sans CJK SC,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=40'"
    subprocess.run(["ffmpeg","-y","-i",str(base),"-i",str(audio),"-vf",subtitle_filter,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-c:a","aac","-b:a","192k","-t",f"{target:.3f}",str(final)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    return final

def generate_shot(api_key,base_url,model,shot_id,seconds,scene,action,camera,atmosphere,dialogue,voices,progress=None):
    silent=generate_video(api_key,base_url,model,shot_id,seconds,scene,action,camera,atmosphere,progress)
    cues=build_timeline(parse_dialogue(dialogue),voices,shot_id,progress)
    final=render(silent,cues,shot_id,progress)
    return {"final":final,"timeline":cues}
