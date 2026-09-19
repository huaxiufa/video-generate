import json, os, subprocess, time, asyncio
from pathlib import Path
import requests, edge_tts
ROOT=Path(__file__).resolve().parent; OUT=ROOT/"output"; AUDIO=ROOT/"audio"; CACHE=ROOT/"cache"
for p in (OUT,AUDIO,CACHE): p.mkdir(exist_ok=True)
DEFAULT_VOICES={"林默":"zh-CN-YunxiNeural","苏晚":"zh-CN-XiaoxiaoNeural","顾言":"zh-CN-YunyangNeural","零":"zh-CN-YunyangNeural","韩成":"zh-CN-YunyangNeural","警员":"zh-CN-YunxiNeural","沈哲":"zh-CN-YunxiNeural","陈凯":"zh-CN-YunxiNeural","周启":"zh-CN-YunyangNeural"}
def post_json(url,payload,headers,progress=None):
    for i in range(7):
        try:
            r=requests.post(url,json=payload,headers=headers,timeout=360)
            if r.ok:return r.json()
            body=r.text[:1000]; retry=r.status_code in (408,425,429,500,502,503,504) or "queue_full" in body.lower() or "queue is full" in body.lower()
            if retry and i<6:
                if progress: progress("Agnes",f"服务繁忙，{15*(i+1)} 秒后重试")
                time.sleep(15*(i+1)); continue
            raise RuntimeError(f"Agnes HTTP {r.status_code}: {body}")
        except requests.RequestException as e:
            if i>=6: raise
            if progress: progress("Agnes",f"网络异常，稍后重试：{e}")
            time.sleep(15*(i+1))
def probe(p): return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],text=True).strip())
def generate_video(api_key,base_url,model,shot,progress=None):
    h={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}
    payload={"model":model,"mode":"text","prompt":f"Cinematic animated mystery drama. Scene: {shot['scene']}. Visual: {shot['visual']}. Shot: {shot['shot_size']}. Camera: {shot['camera']}. No dialogue, no text, no subtitles.","seconds":str(int(shot["duration"])),"size":"720P","aspect_ratio":"16:9","n":1}
    tasks=CACHE/"tasks.json"; data=json.loads(tasks.read_text("utf-8")) if tasks.exists() else {}; item=data.get(str(shot["id"]),{})
    vid=item.get("video_id"); url=item.get("video_url")
    if not vid and not url:
        if progress: progress("Agnes",f"提交 Shot {shot['id']:03d}")
        res=post_json(base_url.rstrip("/")+"/videos",payload,h,progress); vid=res.get("video_id") or res.get("id")
        if not vid: raise RuntimeError(f"没有 video_id: {res}")
        data[str(shot["id"])]={"video_id":vid}; tasks.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    if not url:
        deadline=time.time()+int(os.getenv("AGNES_POLL_TIMEOUT","1800"))
        while time.time()<deadline:
            try:
                r=requests.get(base_url.rstrip("/")+"/agnesapi",params={"video_id":vid,"model_name":model},headers=h,timeout=60); r.raise_for_status(); st=r.json()
            except requests.RequestException:
                time.sleep(10); continue
            status=st.get("status")
            if progress: progress("Agnes",f"Shot {shot['id']:03d}：{status}")
            if status=="completed":
                url=st.get("video_url") or st.get("output_url") or st.get("url"); data[str(shot["id"])]["video_url"]=url; tasks.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); break
            if status in ("failed","error","cancelled"): raise RuntimeError(f"Agnes 任务失败：{st}")
            time.sleep(10)
        if not url: raise TimeoutError(f"Shot {shot['id']} 超时，任务可从 cache/tasks.json 恢复")
    silent=OUT/f"shot_{shot['id']:03d}_silent.mp4"
    if not silent.exists():
        if progress: progress("下载",f"下载 Shot {shot['id']:03d}")
        with requests.get(url,headers={} if "platform-outputs.agnes-ai.space" in url else h,stream=True,timeout=180) as r:
            r.raise_for_status()
            with open(silent,"wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:f.write(chunk)
    return silent
async def tts(text,voice,path,cfg):
    await edge_tts.Communicate(text,voice,rate=cfg.get("rate","+0%"),pitch=cfg.get("pitch","+0Hz"),volume=cfg.get("volume","+0%")).save(str(path))
def make_timeline(shot,voices,settings,progress=None):
    cues=[]; cursor=.35
    for i,d in enumerate(shot.get("dialogue",[])):
        p=AUDIO/f"shot_{shot['id']:03d}_{i:02d}.mp3"; role=d["role"]; cfg=settings.get(role,{})
        if progress: progress("TTS",f"{role} 配音 {i+1}/{len(shot.get('dialogue',[]))}")
        asyncio.run(tts(d["text"],voices.get(role,DEFAULT_VOICES.get(role,"zh-CN-YunxiNeural")),p,cfg))
        dur=probe(p); cues.append({"role":role,"text":d["text"],"audio":str(p),"start":cursor,"end":cursor+dur,"duration":dur}); cursor+=dur+.14
    return cues
def srt(cues,p):
    def ts(x):
        ms=int(round(x*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(p,"w",encoding="utf-8") as f:
        for i,c in enumerate(cues,1): f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")
def render(video,cues,shot,progress=None):
    sid=shot["id"]; sp=OUT/f"shot_{sid:03d}.srt"; srt(cues,sp); vdur=probe(video); end=max([c["end"] for c in cues],default=0)+.25; target=max(vdur,end)
    al=OUT/f"shot_{sid:03d}_audio.txt"; audio=AUDIO/f"shot_{sid:03d}_mix.wav"
    if cues:
        with open(al,"w",encoding="utf-8") as f:
            for c in cues:f.write(f"file '{Path(c['audio']).resolve()}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(al),"-c:a","pcm_s16le",str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    else: subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t",str(max(1,vdur)),str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    base=video
    if target>vdur+.05:
        if progress: progress("合成",f"对白超出画面，冻结最后一帧 {target-vdur:.1f}s")
        ext=OUT/f"shot_{sid:03d}_extended.mp4"
        subprocess.run(["ffmpeg","-y","-i",str(video),"-vf",f"tpad=stop_mode=clone:stop_duration={target-vdur:.3f}","-t",f"{target:.3f}","-an","-c:v","libx264","-pix_fmt","yuv420p",str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT); base=ext
    final=OUT/f"shot_{sid:03d}_final.mp4"
    sf=f"subtitles={sp}:force_style='FontName=Noto Sans CJK SC,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=40'"
    subprocess.run(["ffmpeg","-y","-i",str(base),"-i",str(audio),"-vf",sf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-c:a","aac","-b:a","192k","-t",f"{target:.3f}",str(final)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    return final
def generate_shot(api_key,base_url,model,shot,voices,settings=None,progress=None):
    v=generate_video(api_key,base_url,model,shot,progress); cues=make_timeline(shot,voices,settings or {},progress); return render(v,cues,shot,progress),cues
