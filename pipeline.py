import json, os, subprocess, time, asyncio, hashlib, shutil
from pathlib import Path
import requests, edge_tts
ROOT=Path(__file__).resolve().parent; OUT=ROOT/"output"; AUDIO=ROOT/"audio"; CACHE=ROOT/"cache"
for p in (OUT,AUDIO,CACHE): p.mkdir(exist_ok=True)
DEFAULT_VOICES={"林默":"zh-CN-YunxiNeural","苏晚":"zh-CN-XiaoxiaoNeural","顾言":"zh-CN-YunyangNeural","零":"zh-CN-YunyangNeural","韩成":"zh-CN-YunyangNeural","警员":"zh-CN-YunxiNeural","沈哲":"zh-CN-YunxiNeural","陈凯":"zh-CN-YunxiNeural","周启":"zh-CN-YunyangNeural"}

GEMINI_VOICES={"林默":"Leda","苏晚":"Iapetus","顾言":"Schedar","零":"Charon","韩成":"Gacrux","警员":"Puck","沈哲":"Orus","陈凯":"Zubenelgenubi","周启":"Alnilam"}
GEMINI_VOICE_PROFILES={"林默":"young male, cool and clean, mid-low register, slightly breathy, restrained, observant; slow measured pace; never hot-blooded or anime-like","苏晚":"young female, clear and cool, rational and evidence-first, medium register, slightly brisk; not sweet, not sexy","顾言":"male, mid-low, dry and relaxed, technical/nerdy, concise with mild dry humor","零":"male, low-mid, calm, slow, mysterious with a slight smile; not villainous, not gangster, not CEO","韩成":"male detective, thick low-mid, slightly tired, professional and realistic; never shouting","警员":"ordinary young adult male, medium register, slightly fast and nervous; realistic, not heroic or comic","沈哲":"ordinary office worker, medium register, tired, realistic, restrained","陈凯":"ordinary colleague, medium register, slightly fast and nervous, evasive but not villainous","周启":"finance supervisor, calm, warm and polite, controlled low-mid voice, normal sounding; gradually colder under pressure, never cartoon-villain"}
GEMINI_TTS_MODEL="gemini-3.1-flash-tts-preview"

def gemini_tts(text, voice, path, profile, api_key, model=GEMINI_TTS_MODEL, progress=None):
    if not api_key:
        raise RuntimeError("未配置 Gemini API Key")
    prompt = ("Perform this Chinese dialogue as a professional animated detective drama character. "
              f"Character voice profile: {profile}. Keep the exact wording and do not add words. "
              "Natural pauses, restrained acting, realistic Chinese delivery. Dialogue: " + text)
    payload = {"model": model, "input": prompt, "response_format": {"type": "audio"},
               "generation_config": {"speech_config": [{"voice": voice}]}}
    if progress:
        progress("Gemini TTS", f"生成 {voice} 语音")
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/interactions",
                      headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                      json=payload, timeout=180)
    if not r.ok:
        raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {r.text[:1500]}")
    data = r.json().get("output_audio", {}).get("data")
    if not data:
        raise RuntimeError(f"Gemini TTS 未返回音频：{r.text[:1500]}")
    import base64, wave
    pcm = base64.b64decode(data)
    wav_path = Path(path).with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(pcm)
    return wav_path

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

def probe(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],text=True).strip())

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

def normalize_dialogue(shot):
    raw=shot.get("dialogue")
    if raw is None: raw=shot.get("dialogues",[])
    if isinstance(raw,str): raw=[{"role":"林默","text":raw}]
    elif isinstance(raw,dict): raw=[raw]
    result=[]
    for item in raw or []:
        if isinstance(item,str): result.append({"role":"林默","text":item}); continue
        if not isinstance(item,dict): continue
        role=item.get("role") or item.get("speaker") or item.get("character") or item.get("name") or "林默"
        text=item.get("text") or item.get("line") or item.get("dialogue") or item.get("content") or ""
        if isinstance(text,str) and text.strip(): result.append({"role":str(role),"text":text.strip()})
    return result

def make_timeline(shot,voices,settings,progress=None,tts_provider="edge",gemini_api_key="",gemini_model=GEMINI_TTS_MODEL):
    dialogues=normalize_dialogue(shot)
    if progress: progress("TTS",f"Shot {shot['id']:03d}：识别到 {len(dialogues)} 句对白")
    cues=[]; cursor=.35
    cache_dir=AUDIO/"cache"; cache_dir.mkdir(parents=True,exist_ok=True)
    for i,d in enumerate(dialogues):
        role=d["role"]; cfg=settings.get(role,{})
        if progress: progress("TTS",f"{role} 配音 {i+1}/{len(dialogues)}")
        voice=GEMINI_VOICES.get(role,"Kore") if tts_provider=="gemini" else voices.get(role,DEFAULT_VOICES.get(role,"zh-CN-YunxiNeural"))
        profile=GEMINI_VOICE_PROFILES.get(role,"realistic Chinese character voice") if tts_provider=="gemini" else ""
        cache_payload=json.dumps({
            "provider":tts_provider,
            "model":gemini_model if tts_provider=="gemini" else "edge",
            "role":role,"text":d["text"],"voice":voice,"profile":profile,
            "settings":cfg if tts_provider!="gemini" else {}
        },ensure_ascii=False,sort_keys=True)
        cache_key=hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:24]
        cache_path=cache_dir/f"{cache_key}.wav"
        p=AUDIO/f"shot_{shot['id']:03d}_{i:02d}.wav"
        if cache_path.exists():
            if progress: progress("TTS缓存",f"命中缓存：{role}，不再调用 TTS")
            shutil.copyfile(cache_path,p)
        else:
            if tts_provider=="gemini":
                generated=gemini_tts(d["text"],voice,p,profile,gemini_api_key,gemini_model,progress)
            else:
                edge_path=AUDIO/f"shot_{shot['id']:03d}_{i:02d}_edge.mp3"
                asyncio.run(tts(d["text"],voice,edge_path,cfg))
                generated=edge_path
                subprocess.run(["ffmpeg","-y","-i",str(generated),"-ar","48000","-ac","2","-c:a","pcm_s16le",str(p)],
                               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
                generated=p
            shutil.copyfile(generated,cache_path)
            if Path(generated)!=p: shutil.copyfile(generated,p)
        audio_path=p
        dur=probe(audio_path)
        cues.append({"role":role,"text":d["text"],"audio":str(audio_path),"start":cursor,"end":cursor+dur,"duration":dur})
        cursor+=dur+.14
    return cues

def srt(cues,p):
    def ts(x):
        ms=int(round(x*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(p,"w",encoding="utf-8") as f:
        for i,c in enumerate(cues,1): f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")
    if not p.exists(): raise RuntimeError(f"SRT 字幕文件无法创建：{p}")
    if cues and p.stat().st_size==0: raise RuntimeError(f"SRT 字幕文件为空：{p}")

def render(video,cues,shot,progress=None):
    sid=shot["id"]; sp=OUT/f"shot_{sid:03d}.srt"; srt(cues,sp); vdur=probe(video); end=max([c["end"] for c in cues],default=0)+.25; target=max(vdur,end)
    al=OUT/f"shot_{sid:03d}_audio.txt"; audio=AUDIO/f"shot_{sid:03d}_mix.wav"
    if cues:
        with open(al,"w",encoding="utf-8") as f:
            for c in cues:f.write(f"file '{Path(c['audio']).resolve()}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(al),"-c:a","pcm_s16le",str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    else:
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t",str(max(1,vdur)),str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    base=video
    if target>vdur+.05:
        if progress: progress("合成",f"对白超出画面，冻结最后一帧 {target-vdur:.1f}s")
        ext=OUT/f"shot_{sid:03d}_extended.mp4"
        subprocess.run(["ffmpeg","-y","-i",str(video),"-vf",f"tpad=stop_mode=clone:stop_duration={target-vdur:.3f}","-t",f"{target:.3f}","-an","-c:v","libx264","-pix_fmt","yuv420p",str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT); base=ext
    final=OUT/f"shot_{sid:03d}_final.mp4"
    subtitle_file=str(sp.resolve()).replace("\\","\\\\").replace(":","\\:")
    sf=f"subtitles=filename='{subtitle_file}':charenc=UTF-8:force_style='FontName=Noto Sans CJK SC,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=40'
    cmd=["ffmpeg","-y","-i",str(base),"-i",str(audio),"-vf",sf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-c:a","aac","-b:a","192k","-t",f"{target:.3f}",str(final)]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if proc.returncode!=0:
        log=OUT/f"shot_{sid:03d}_ffmpeg_error.log"; log.write_text(proc.stderr[-12000:],encoding="utf-8")
        fallback=["ffmpeg","-y","-i",str(base),"-i",str(audio),"-vf",f"subtitles=filename='{subtitle_file}':charenc=UTF-8","-map","0:v:0","-map","1:a:0","-c:v","libx264","-c:a","aac","-b:a","192k","-t",f"{target:.3f}",str(final)]
        proc2=subprocess.run(fallback,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if proc2.returncode!=0:
            log.write_text(log.read_text(encoding="utf-8")+"\n\n--- FALLBACK ---\n"+proc2.stderr[-12000:],encoding="utf-8")
            raise RuntimeError(f"FFmpeg 字幕合成失败（exit {proc2.returncode}）。详细日志：{log}")
    return final

def generate_shot(api_key,base_url,model,shot,voices,settings=None,progress=None,tts_provider="edge",gemini_api_key="",gemini_model=GEMINI_TTS_MODEL):
    v=generate_video(api_key,base_url,model,shot,progress); cues=make_timeline(shot,voices,settings or {},progress,tts_provider,gemini_api_key,gemini_model); return render(v,cues,shot,progress),cues

def build_segments(shots,segments):
    valid={s["id"]:s for s in shots}; out=[]; used=set()
    for seg in segments or []:
        picked=[int(x) for x in seg.get("shot_ids",[]) if str(x).isdigit() and int(x) in valid and int(x) not in used]
        if not picked: continue
        used.update(picked)
        out.append({"segment_no":len(out)+1,"title":seg.get("title",f"剧情片段 {len(out)+1:03d}"),"summary":seg.get("summary",""),"shot_ids":picked,"target_duration":sum(valid[x]["duration"] for x in picked)})
    for s in shots:
        if s["id"] not in used:
            out.append({"segment_no":len(out)+1,"title":f"剧情片段 {len(out)+1:03d}","summary":"","shot_ids":[s["id"]],"target_duration":s["duration"]})
    return out

def concat_mp4s(files,dest,progress=None):
    files=[Path(x) for x in files]
    if not files: raise ValueError("没有可拼接的视频")
    if len(files)==1:
        if files[0]!=Path(dest): Path(dest).write_bytes(files[0].read_bytes())
        return Path(dest)
    listfile=CACHE/(Path(dest).stem+"_concat.txt")
    with open(listfile,"w",encoding="utf-8") as f:
        for p in files: f.write("file '"+str(p.resolve()).replace("'","'\\''")+"'\n")
    cmd=["ffmpeg","-y","-f","concat","-safe","0","-i",str(listfile),"-c","copy",str(dest)]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if proc.returncode!=0:
        if progress: progress("拼接","编码参数不一致，使用兼容模式重新拼接")
        cmd=["ffmpeg","-y","-f","concat","-safe","0","-i",str(listfile),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",str(dest)]
        proc2=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if proc2.returncode!=0: raise RuntimeError("视频拼接失败："+proc2.stderr[-5000:])
    return Path(dest)

def render_episode(api_key,base_url,model,data,voices,settings=None,progress=None,bar=None,tts_provider="edge",gemini_api_key="",gemini_model=GEMINI_TTS_MODEL):
    shots={s["id"]:s for s in data["shots"]}
    segments=build_segments(data["shots"],data.get("segments",[]))
    segment_paths=[]
    total=len(data["shots"])
    done=0
    for seg in segments:
        paths=[]
        for sid in seg["shot_ids"]:
            shot=shots[sid]
            def shot_progress(stage,msg): 
                if progress: progress(stage,msg)
            final,_=generate_shot(api_key,base_url,model,shot,voices,settings or {},shot_progress,tts_provider,gemini_api_key,gemini_model)
            paths.append(final); done+=1
            if bar: bar.progress(min(done/total,1.0))
        segpath=OUT/f"segment_{seg['segment_no']:03d}.mp4"
        concat_mp4s(paths,segpath,progress)
        segment_paths.append((seg["segment_no"],segpath))
        if progress: progress("片段完成",f"剧情片段 {seg['segment_no']:03d} 完成，目标约12秒，实际 {probe(segpath):.1f}s")
    episode=OUT/"night_agency_episode.mp4"
    concat_mp4s([p for _,p in segment_paths],episode,progress)
    if bar: bar.progress(1.0)
    return episode,segment_paths

def list_chinese_voices():
    import asyncio
    async def _load(): return await edge_tts.list_voices()
    voices=asyncio.run(_load())
    return [v["ShortName"] for v in voices if v.get("Locale","").lower().startswith("zh-cn")]

def synthesize_preview(text, voice):
    path=AUDIO/"voice_preview.mp3"
    asyncio.run(tts(text,voice,path,{"rate":"+0%","pitch":"+0Hz","volume":"+0%"}))
    return str(path)

def generate_character_voice_pack(voices, settings=None, progress=None):
    import zipfile, json
    settings=settings or {}; pack=ROOT/"output"/"night-agency-voices"; pack.mkdir(parents=True,exist_ok=True)
    samples={"林默":"时间不对。","苏晚":"先别猜，证据呢？","顾言":"我查到了监控记录。","零":"有些案子，结了才是真的开始。","韩成":"先别碰现场。","警员":"已经确认身份了。","沈哲":"我知道他来了。","陈凯":"我只是回来拿一样东西。","周启":"我什么都不知道。"}
    manifest={}
    for role,voice in voices.items():
        if progress: progress(f"生成 {role} 的声音")
        cfg=settings.get(role,{"rate":"+0%","pitch":"+0Hz","volume":"+0%"})
        mp3=pack/f"{role}.mp3"; asyncio.run(tts(samples.get(role,"这是一段角色声音试听。"),voice,mp3,cfg))
        manifest[role]={"voice":voice,"sample_text":samples.get(role,"这是一段角色声音试听。"),"settings":cfg,"file":mp3.name}
    (pack/"voices.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    zip_path=ROOT/"output"/"night-agency-voices.zip"
    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pack.iterdir()): z.write(p,p.relative_to(pack))
    return zip_path, manifest
