import os,json,uuid,asyncio,base64,subprocess,shlex
from pathlib import Path
import httpx
from fastapi import FastAPI,BackgroundTasks,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT=Path(os.getenv("WORK_DIR","/data/projects")); ROOT.mkdir(parents=True,exist_ok=True)
STAGES=["初始化","场景配置","图片分析","故事生成","角色参考图","脚本编写","尾帧提示词","尾帧生成","视频生成","音频生成","字幕生成","视频拼接"]
AGNES=os.getenv("AGNES_BASE_URL","https://apihub.agnes-ai.com").rstrip("/")
TEXT_MODEL=os.getenv("AGNES_TEXT_MODEL","agnes-3.0-flash")
AGNES_KEYS=[x.strip() for x in os.getenv("AGNES_API_KEYS","").split(",") if x.strip()]
if not AGNES_KEYS:
    single=os.getenv("AGNES_API_KEY","").strip()
    if single: AGNES_KEYS=[single]
AGNES_KEY_INDEX=0
AGNES_KEY_LOCK=asyncio.Lock()
app=FastAPI(title="Video Generate V2.2")
RUNNING=set()

class Req(BaseModel):
    script:str
    aspect_ratio:str="16:9"
    size:str="1080P"

def load(pid):
    p=ROOT/pid/"state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def save(pid,s):
    d=ROOT/pid
    t=d/"state.tmp"
    t.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
    t.replace(d/"state.json")

def set_detail(pid,s,stage,index,total,label):
    s["current_item"]=index
    s["total_items"]=total
    s["current_detail"]=f"{label} {index}/{total}" if total else label
    s["stages"][stage]["progress"]=round(index/total*100,1) if total else 0
    save(pid,s)

async def agnes(method,path,**kw):
    global AGNES_KEY_INDEX
    if not AGNES_KEYS: raise RuntimeError("AGNES_API_KEYS / AGNES_API_KEY 未配置")
    async with AGNES_KEY_LOCK:
        key=AGNES_KEYS[AGNES_KEY_INDEX % len(AGNES_KEYS)]
        AGNES_KEY_INDEX=(AGNES_KEY_INDEX+1) % len(AGNES_KEYS)
    async with httpx.AsyncClient(timeout=300) as c:
        r=await c.request(method,AGNES+path,headers={"Authorization":"Bearer "+key},**kw)
        if r.is_error:
            detail=r.text[:2000]
            raise RuntimeError(f"Agnes API {r.status_code}: {detail}")
        return r.json()
async def ai_json(prompt):
    x=await agnes("POST","/v1/chat/completions",json={
        "model":TEXT_MODEL,
        "messages":[
            {"role":"system","content":"你是动画导演、编剧和分镜设计师。只输出合法 JSON，不要 Markdown。"},
            {"role":"user","content":prompt}
        ],
        "temperature":0.2,
        "response_format":{"type":"json_object"}
    })
    text=x["choices"][0]["message"]["content"]
    try:return json.loads(text)
    except json.JSONDecodeError:
        a=text.find("{"); b=text.rfind("}")
        if a>=0 and b>a:return json.loads(text[a:b+1])
        raise RuntimeError("Agnes AI 没有返回合法 JSON")

def data_uri(path):
    p=Path(path)
    mime="image/png" if p.suffix.lower()==".png" else "image/jpeg"
    return "data:"+mime+";base64,"+base64.b64encode(p.read_bytes()).decode()



async def download_url(url,out,timeout=900,retries=5):
    """Download a remote asset safely; retry truncated HTTP bodies and resume with Range when supported."""
    out=Path(out); out.parent.mkdir(parents=True,exist_ok=True)
    part=out.with_suffix(out.suffix+".part")
    last_error=None
    for attempt in range(1,retries+1):
        start=part.stat().st_size if part.exists() else 0
        headers={"Range":f"bytes={start}-"} if start else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=30)) as c:
                async with c.stream("GET",url,headers=headers) as r:
                    r.raise_for_status()
                    mode="ab" if start and r.status_code==206 else "wb"
                    if mode=="wb": start=0
                    expected=r.headers.get("content-length")
                    expected_total=(start+int(expected)) if expected and r.status_code==206 else (int(expected) if expected else None)
                    with part.open(mode) as f:
                        async for chunk in r.aiter_bytes(1024*1024):
                            f.write(chunk)
                    actual=part.stat().st_size
                    if expected_total is not None and actual != expected_total:
                        raise httpx.ReadError(f"incomplete download: received {actual} bytes, expected {expected_total}")
            if part.stat().st_size<=1024:
                raise RuntimeError("下载文件为空或过小")
            part.replace(out)
            return
        except (httpx.HTTPError, OSError, RuntimeError) as e:
            last_error=e
            if attempt<retries:
                await asyncio.sleep(min(2**attempt,8))
    raise RuntimeError(f"远程文件下载失败（已重试{retries}次）: {last_error}")

async def image(prompt,out,size="1024x576",references=None):
    out=Path(out)
    if out.exists() and out.stat().st_size>1024:return
    body={"model":os.getenv("AGNES_IMAGE_MODEL","agnes-image-2.5-flash"),"prompt":prompt,"size":size,"n":1}
    if references: body["extra_body"]={"image":[data_uri(x) for x in references[:5]]}
    x=await agnes("POST","/v1/images/generations",json=body)
    item=(x.get("data") or [{}])[0]
    if item.get("b64_json"):out.write_bytes(base64.b64decode(item["b64_json"]));return
    url=item.get("url")
    if not url:raise RuntimeError("Agnes 图片返回异常")
    await download_url(url,out,timeout=900)

async def video(pid,s,scene):
    d=ROOT/pid;sd=d/"video"/str(scene["id"]);sd.mkdir(parents=True,exist_ok=True)
    out=sd/"video.mp4";tf=sd/"task.json"
    if out.exists() and out.stat().st_size>1024:return
    task=json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else None
    if not task:
        model=os.getenv("AGNES_VIDEO_MODEL","agnes-video-2.5-flash")
        # Video 2.5 Flash only accepts 720P and seconds 4-12.
        size="720P" if model=="agnes-video-2.5-flash" else s["size"]
        seconds=max(4,min(12,int(scene["seconds"])))
        body={"model":model,"mode":"keyframe",
              "prompt":scene["video_prompt"],"seconds":str(seconds),"size":size,
              "aspect_ratio":s["aspect_ratio"],"n":1}
        if scene.get("first_frame_path"):body["first_frame"]=data_uri(scene["first_frame_path"])
        if scene.get("last_frame_path"):body["last_frame"]=data_uri(scene["last_frame_path"])
        refs=[x["path"] for x in s.get("characters",[]) if x.get("path") and Path(x["path"]).exists()]
        # Agnes 2.5 keyframe mode accepts first/last frames; character references
        # are injected into generated frames instead of images[].
        # Agnes may temporarily reject new jobs when its video queue is full.
        # Retry only this transient condition; never duplicate an accepted task.
        queue_retries=int(os.getenv("AGNES_VIDEO_QUEUE_RETRIES","8"))
        for attempt in range(1,queue_retries+1):
            try:
                task=await agnes("POST","/v1/videos",json=body)
                tf.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding="utf-8")
                break
            except RuntimeError as e:
                msg=str(e)
                if "video_queue_full" not in msg and "queue is full" not in msg:
                    raise
                if attempt>=queue_retries:
                    raise RuntimeError(f"Agnes 视频队列持续繁忙，已自动重试 {queue_retries} 次，最后错误：{msg}")
                wait=min(30*attempt,180)
                await asyncio.sleep(wait)
    vid=task.get("video_id") or task.get("id")
    if not vid:raise RuntimeError("Agnes 未返回 video_id")
    while True:
        x=await agnes("GET",f"/agnesapi?video_id={vid}&model_name={model}")
        status=str(x.get("status","")).lower()
        if status=="completed":break
        if status in {"failed","cancelled","error"}:raise RuntimeError("Agnes 视频任务失败: "+json.dumps(x,ensure_ascii=False))
        await asyncio.sleep(2)
    url=x.get("url") or x.get("video_url") or (x.get("data") or {}).get("url")
    if not url:raise RuntimeError("Agnes 没有返回视频地址")
    await download_url(url,out,timeout=900)

async def gemini_tts(text,out,voice):
    key=os.getenv("GEMINI_API_KEY")
    if not key:raise RuntimeError("GEMINI_API_KEY 未配置")
    out=Path(out)
    if out.exists() and out.stat().st_size>1024:return
    model=os.getenv("GEMINI_TTS_MODEL","gemini-3.1-flash-tts-preview")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body={"contents":[{"parts":[{"text":text}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":voice}}}}}
    async with httpx.AsyncClient(timeout=300) as c:
        r=await c.post(url,params={"key":key},json=body);r.raise_for_status();data=r.json()
    raw=data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    pcm=out.with_suffix(".pcm");pcm.write_bytes(base64.b64decode(raw))
    subprocess.run(["ffmpeg","-y","-f","s16le","-ar","24000","-ac","1","-i",str(pcm),str(out)],check=True)
    pcm.unlink(missing_ok=True)

async def clone_tts(text,sample,out):
    out=Path(out)
    if out.exists() and out.stat().st_size>1024:return
    script=os.getenv("MOSS_TTS_SCRIPT","/app/app/moss_clone.py")
    p=await asyncio.create_subprocess_exec("python",script,text,str(sample),str(out))
    if await p.wait():raise RuntimeError("MOSS-TTS-Nano voice clone 失败")

async def run(pid):
    s=load(pid);d=ROOT/pid
    try:
        s["status"]="running";s["error"]=None;save(pid,s)
        for i,stage in enumerate(STAGES):
            if s["stages"][stage]["status"]=="done":continue
            s["current_stage"]=i;s["stages"][stage]={"status":"running","progress":0};s["current_detail"]="准备中";s["current_item"]=0;s["total_items"]=0;save(pid,s)
            if stage=="初始化":
                for n in ["images","characters","video","audio","voices"]:(d/n).mkdir(exist_ok=True)
            elif stage=="场景配置":
                plan=await ai_json("""把下面用户脚本拆成适合动画视频的连续场景。不要机械按换行切。输出 JSON：{"scenes":[{"id":0,"summary":"","duration":8,"characters":[],"location":"","time":"","action":""}]}。duration 只能 4-12 秒。脚本：\n"""+s["script"])
                s["scenes"]=plan["scenes"]
                for i,x in enumerate(s["scenes"]):x["id"]=i;x["seconds"]=int(x.get("duration",8))
            elif stage=="图片分析":
                total=len(s["scenes"])
                for n,x in enumerate(s["scenes"],1):
                    set_detail(pid,s,stage,n,total,"分析场景")
                    r=await ai_json("""为这个动画场景生成视觉设计。输出 JSON：{"visual_prompt":"","camera":"","lighting":"","style":"","continuity":""}。保持角色和服装连续。场景："""+json.dumps(x,ensure_ascii=False))
                    x.update(r)
            elif stage=="故事生成":
                r=await ai_json("""把这些场景整理成完整动画故事，保持事件因果、人物动机和结尾连贯。输出 JSON：{"title":"","logline":"","story_beats":[{"scene_id":0,"beat":""}]}。场景："""+json.dumps(s["scenes"],ensure_ascii=False))
                s["story"]=r
                beats={x["scene_id"]:x["beat"] for x in r.get("story_beats",[])}
                for x in s["scenes"]:x["story_beat"]=beats.get(x["id"],x.get("summary",""))
            elif stage=="角色参考图":
                r=await ai_json("""从故事场景中识别所有重要角色。输出 JSON：{"characters":[{"id":"","name":"","appearance":"","personality":"","voice_style":""}]}。同一个角色必须使用同一个 id。场景："""+json.dumps(s["scenes"],ensure_ascii=False))
                s["characters"]=r.get("characters",[])
                total=len(s["characters"])
                for n,c in enumerate(s["characters"],1):
                    set_detail(pid,s,stage,n,total,"生成角色参考图")
                    c["path"]=str(d/"characters"/(c["id"]+".png"))
                    await image("character reference sheet, full body, neutral pose, clean background, "+c["appearance"],c["path"],"1024x1024")
            elif stage=="脚本编写":
                total=len(s["scenes"])
                for n,x in enumerate(s["scenes"],1):
                    set_detail(pid,s,stage,n,total,"编写场景脚本")
                    r=await ai_json("""为一个动画场景写可直接用于视频生成的英文 prompt，并提取对白。输出 JSON：{"video_prompt":"","dialogues":[{"character_id":"","text":""}]}. 不要改变剧情。场景："""+json.dumps(x,ensure_ascii=False)+",角色："+json.dumps(s["characters"],ensure_ascii=False))
                    x.update(r)
                (d/"script.json").write_text(json.dumps({"story":s.get("story"),"characters":s["characters"],"scenes":s["scenes"]},ensure_ascii=False,indent=2),encoding="utf-8")
            elif stage=="尾帧提示词":
                total=len(s["scenes"])
                for n,x in enumerate(s["scenes"],1):
                    set_detail(pid,s,stage,n,total,"生成尾帧提示词")
                    r=await ai_json("""生成下一镜头可衔接的尾帧设计。输出 JSON：{"last_frame_prompt":"","transition_note":""}。保持人物位置、服装、道具连续。当前场景："""+json.dumps(x,ensure_ascii=False))
                    x.update(r)
            elif stage=="尾帧生成":
                total=len(s["scenes"])
                for n,x in enumerate(s["scenes"],1):
                    set_detail(pid,s,stage,n,total,"生成尾帧")
                    refs=[c["path"] for c in s["characters"] if c.get("path") and c.get("id") in {z.get("character_id") for z in x.get("dialogues",[])}]
                    if x["id"]==0:
                        sp=d/"images"/"0_first.png"
                        await image(x.get("visual_prompt","")+", opening frame, establish the scene and characters, "+x.get("style",""),sp,"1024x576",refs)
                        x["first_frame_path"]=str(sp)
                    else:
                        prev=d/"images"/f"{x['id']-1}_last.png"
                        if prev.exists():x["first_frame_path"]=str(prev)
                    p=d/"images"/f"{x['id']}_last.png"
                    await image(x["last_frame_prompt"],p,"1024x576",refs);x["last_frame_path"]=str(p)
            elif stage=="视频生成":
                total=len(s["scenes"])
                for n,x in enumerate(s["scenes"],1):
                    set_detail(pid,s,stage,n,total,"生成视频片段")
                    await video(pid,s,x)
            elif stage=="音频生成":
                cursor=0.0;subs=[]
                total=sum(len(x.get("dialogues",[])) for x in s["scenes"])
                item=0
                for x in s["scenes"]:
                    dialogs=x.get("dialogues",[])
                    slot=x["seconds"]/max(1,len(dialogs))
                    for j,dia in enumerate(dialogs):
                        item+=1
                        set_detail(pid,s,stage,item,total,"生成对白音频")
                        ch=next((c for c in s["characters"] if c["id"]==dia["character_id"]),None)
                        if not ch:continue
                        voice=d/"voices"/(ch["id"]+".wav");out=d/"audio"/f"{x['id']}_{j}.wav"
                        if not voice.exists():
                            await gemini_tts(dia["text"],voice,os.getenv("GEMINI_TTS_VOICE","Kore"))
                        await clone_tts(dia["text"],voice,out)
                        start=cursor+j*slot
                        subs.append({"start":start,"end":start+slot,"text":ch["name"]+": "+dia["text"],"audio_file":str(out)})
                    cursor+=x["seconds"]
                s["subtitles"]=subs
                if not subs:raise RuntimeError("没有识别到对白")
            elif stage=="字幕生成":
                subs=s.get("subtitles",[])
                (d/"subtitles.json").write_text(json.dumps(subs,ensure_ascii=False,indent=2),encoding="utf-8")
                def ts(v):
                    h=int(v//3600);m=int((v%3600)//60);sec=v%60
                    return "%02d:%02d:%06.3f"%(h,m,sec)
                srt=[]
                for n,q in enumerate(subs,1):
                    srt += [str(n),ts(q["start"])+" --> "+ts(q["end"]),q["text"],""]
                (d/"subtitles.srt").write_text("\n".join(srt),encoding="utf-8")
            elif stage=="视频拼接":
                vids=sorted((d/"video").glob("*/video.mp4"),key=lambda p:int(p.parent.name))
                if not vids:raise RuntimeError("没有视频片段")
                lst=d/"concat.txt";lst.write_text("".join("file '"+p.resolve().as_posix()+"'\\n" for p in vids),encoding="utf-8")
                merged=d/"merged.mp4";subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(merged)],check=True)
                wavs=sorted((d/"audio").glob("*.wav"))
                if wavs:
                    # Preserve scene/dialogue timing instead of simply concatenating speech.
                    inputs=[];filters=[]
                    for idx,p in enumerate(wavs):
                        q=next((z for z in s.get("subtitles",[]) if z.get("audio_file")==str(p)),None)
                        delay=int(max(0,float(q["start"]))*1000) if q else 0
                        inputs += ["-i",str(p)]
                        filters.append(f"[{idx}:a]adelay={delay}|{delay}[a{idx}]")
                    labels="".join(f"[a{i}]" for i in range(len(wavs)))
                    filters.append(labels+f"amix=inputs={len(wavs)}:duration=longest:normalize=0[mix]")
                    mix=d/"mix.wav"
                    subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",";".join(filters),"-map","[mix]","-c:a","pcm_s16le",str(mix)],check=True)
                cmd=["ffmpeg","-y","-i",str(merged)]
                if (d/"mix.wav").exists():cmd+=["-i",str(d/"mix.wav")]
                if (d/"subtitles.srt").exists():
                    sub=(d/"subtitles.srt").as_posix().replace(":","\\:")
                    cmd += ["-vf","subtitles="+sub+":fontsdir=/usr/share/fonts/opentype/noto"]
                cmd+=["-c:v","libx264","-c:a","aac","-shortest",str(d/"final.mp4")]
                subprocess.run(cmd,check=True)
            s["stages"][stage]={"status":"done","progress":100};s["current_item"]=s.get("total_items",0);s["current_detail"]="阶段完成";s["current_stage"]=i+1;s["current_stage_name"]=STAGES[i+1] if i+1<len(STAGES) else "完成";s["progress_percent"]=round(((i+1)/len(STAGES))*100,1);save(pid,s)
        s["status"]="done";s["progress_percent"]=100;s["current_stage_name"]="完成";save(pid,s)
    except Exception as e:
        s=load(pid);s["status"]="failed";s["error"]=str(e);s["stages"][stage]={"status":"failed","error":str(e)};save(pid,s)

@app.get("/")
def index():return FileResponse(Path(__file__).parent.parent/"web"/"index.html")
@app.post("/api/projects")
def create(x:Req):
    if not x.script.strip():raise HTTPException(400,"script 不能为空")
    pid=uuid.uuid4().hex[:12];d=ROOT/pid;d.mkdir()
    s={"project_id":pid,"script":x.script,"aspect_ratio":x.aspect_ratio,"size":x.size,"status":"pending","current_stage":0,"current_stage_name":STAGES[0],"progress_percent":0,"error":None,"stages":{x:{"status":"pending","progress":0} for x in STAGES}}
    save(pid,s);return s
@app.post("/api/projects/{pid}/run")
def start(pid:str,bg:BackgroundTasks):
    if not load(pid):raise HTTPException(404,"project not found")
    if pid in RUNNING:return {"ok":True,"project_id":pid,"already_running":True}
    RUNNING.add(pid)
    async def wrapped():
        try: await run(pid)
        finally: RUNNING.discard(pid)
    bg.add_task(wrapped)
    return {"ok":True,"project_id":pid}
@app.get("/api/projects/{pid}")
def state(pid:str):
    s=load(pid)
    if not s:raise HTTPException(404,"project not found")
    return s
@app.get("/api/projects/{pid}/download")
def download(pid:str):
    p=ROOT/pid/"final.mp4"
    if not p.exists():raise HTTPException(404,"视频尚未生成")
    return FileResponse(p,media_type="video/mp4",filename=pid+".mp4")
