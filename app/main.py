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
app=FastAPI(title="Video Generate V2.1")

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

async def agnes(method,path,**kw):
    key=os.getenv("AGNES_API_KEY")
    if not key: raise RuntimeError("AGNES_API_KEY 未配置")
    async with httpx.AsyncClient(timeout=300) as c:
        r=await c.request(method,AGNES+path,headers={"Authorization":"Bearer "+key},**kw)
        r.raise_for_status()
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
    async with httpx.AsyncClient(timeout=300) as c:
        r=await c.get(url);r.raise_for_status();out.write_bytes(r.content)

async def video(pid,s,scene):
    d=ROOT/pid;sd=d/"video"/str(scene["id"]);sd.mkdir(parents=True,exist_ok=True)
    out=sd/"video.mp4";tf=sd/"task.json"
    if out.exists() and out.stat().st_size>1024:return
    task=json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else None
    if not task:
        body={"model":os.getenv("AGNES_VIDEO_MODEL","agnes-video-2.5"),"mode":"keyframe",
              "prompt":scene["video_prompt"],"seconds":scene["seconds"],"size":s["size"],
              "aspect_ratio":s["aspect_ratio"],"n":1}
        if scene.get("first_frame_path"):body["first_frame"]=data_uri(scene["first_frame_path"])
        if scene.get("last_frame_path"):body["last_frame"]=data_uri(scene["last_frame_path"])
        refs=[x["path"] for x in s.get("characters",[]) if x.get("path") and Path(x["path"]).exists()]
        if refs:body["images"]=[data_uri(x) for x in refs[:5]]
        task=await agnes("POST","/v1/videos",json=body)
        tf.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding="utf-8")
    vid=task.get("video_id") or task.get("id")
    if not vid:raise RuntimeError("Agnes 未返回 video_id")
    while True:
        x=await agnes("GET",f"/agnesapi?video_id={vid}&model_name={os.getenv('AGNES_VIDEO_MODEL','agnes-video-2.5')}")
        status=str(x.get("status","")).lower()
        if status=="completed":break
        if status in {"failed","cancelled","error"}:raise RuntimeError("Agnes 视频任务失败: "+json.dumps(x,ensure_ascii=False))
        await asyncio.sleep(2)
    url=x.get("url") or x.get("video_url") or (x.get("data") or {}).get("url")
    if not url:raise RuntimeError("Agnes 没有返回视频地址")
    part=out.with_suffix(".part")
    async with httpx.AsyncClient(timeout=900) as c:
        r=await c.get(url);r.raise_for_status();part.write_bytes(r.content)
    part.replace(out)

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
    cmd=os.getenv("VOICE_CLONE_COMMAND")
    if not cmd:raise RuntimeError("后续角色台词需要 VOICE_CLONE_COMMAND")
    p=await asyncio.create_subprocess_exec(*shlex.split(cmd),text,str(sample),str(out))
    if await p.wait():raise RuntimeError("本地 voice clone 失败")

async def run(pid):
    s=load(pid);d=ROOT/pid
    try:
        s["status"]="running";s["error"]=None;save(pid,s)
        for i,stage in enumerate(STAGES):
            if s["stages"][stage]["status"]=="done":continue
            s["current_stage"]=i;s["stages"][stage]={"status":"running"};save(pid,s)
            if stage=="初始化":
                for n in ["images","characters","video","audio","voices"]:(d/n).mkdir(exist_ok=True)
            elif stage=="场景配置":
                plan=await ai_json("""把下面用户脚本拆成适合动画视频的连续场景。不要机械按换行切。输出 JSON：{"scenes":[{"id":0,"summary":"","duration":8,"characters":[],"location":"","time":"","action":""}]}。duration 只能 4-12 秒。脚本：\n"""+s["script"])
                s["scenes"]=plan["scenes"]
                for i,x in enumerate(s["scenes"]):x["id"]=i;x["seconds"]=int(x.get("duration",8))
            elif stage=="图片分析":
                for x in s["scenes"]:
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
                for c in s["characters"]:
                    c["path"]=str(d/"characters"/(c["id"]+".png"))
                    await image("character reference sheet, full body, neutral pose, clean background, "+c["appearance"],c["path"],"1024x1024")
            elif stage=="脚本编写":
                for x in s["scenes"]:
                    r=await ai_json("""为一个动画场景写可直接用于视频生成的英文 prompt，并提取对白。输出 JSON：{"video_prompt":"","dialogues":[{"character_id":"","text":""}]}. 不要改变剧情。场景："""+json.dumps(x,ensure_ascii=False)+",角色："+json.dumps(s["characters"],ensure_ascii=False))
                    x.update(r)
                (d/"script.json").write_text(json.dumps({"story":s.get("story"),"characters":s["characters"],"scenes":s["scenes"]},ensure_ascii=False,indent=2),encoding="utf-8")
            elif stage=="尾帧提示词":
                for x in s["scenes"]:
                    r=await ai_json("""生成下一镜头可衔接的尾帧设计。输出 JSON：{"last_frame_prompt":"","transition_note":""}。保持人物位置、服装、道具连续。当前场景："""+json.dumps(x,ensure_ascii=False))
                    x.update(r)
            elif stage=="尾帧生成":
                for x in s["scenes"]:
                    p=d/"images"/f"{x['id']}_last.png"
                    refs=[c["path"] for c in s["characters"] if c.get("path") and c.get("id") in {z.get("character_id") for z in x.get("dialogues",[])}]
                    await image(x["last_frame_prompt"],p,"1024x576",refs);x["last_frame_path"]=str(p)
                    if x["id"]>0:
                        prev=d/"images"/f"{x['id']-1}_last.png"
                        if prev.exists():x["first_frame_path"]=str(prev)
            elif stage=="视频生成":
                for x in s["scenes"]:await video(pid,s,x)
            elif stage=="音频生成":
                cursor=0.0;subs=[]
                for x in s["scenes"]:
                    for j,dia in enumerate(x.get("dialogues",[])):
                        ch=next((c for c in s["characters"] if c["id"]==dia["character_id"]),None)
                        if not ch:continue
                        voice=d/"voices"/(ch["id"]+".wav");out=d/"audio"/f"{x['id']}_{j}.wav"
                        if not voice.exists():
                            await gemini_tts(dia["text"],voice,os.getenv("GEMINI_TTS_VOICE","Kore"))
                        if voice.exists() and out.exists() is False:
                            await clone_tts(dia["text"],voice,out)
                        subs.append({"start":cursor,"end":cursor+max(1.0,x["seconds"]),"text":ch["name"]+": "+dia["text"]});cursor+=x["seconds"]
                s["subtitles"]=subs
                if not subs:raise RuntimeError("没有识别到对白")
            elif stage=="字幕生成":
                (d/"subtitles.json").write_text(json.dumps(s.get("subtitles",[]),ensure_ascii=False,indent=2),encoding="utf-8")
            elif stage=="视频拼接":
                vids=sorted((d/"video").glob("*/video.mp4"),key=lambda p:int(p.parent.name))
                if not vids:raise RuntimeError("没有视频片段")
                lst=d/"concat.txt";lst.write_text("".join("file '"+p.resolve().as_posix()+"'\\n" for p in vids),encoding="utf-8")
                merged=d/"merged.mp4";subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(merged)],check=True)
                wavs=sorted((d/"audio").glob("*.wav"))
                if wavs:
                    al=d/"audio_concat.txt";al.write_text("".join("file '"+p.resolve().as_posix()+"'\\n" for p in wavs),encoding="utf-8")
                    mix=d/"mix.wav";subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(al),"-c:a","pcm_s16le",str(mix)],check=True)
                cmd=["ffmpeg","-y","-i",str(merged)]
                if (d/"mix.wav").exists():cmd+=["-i",str(d/"mix.wav")]
                cmd+=["-c:v","libx264","-c:a","aac","-shortest",str(d/"final.mp4")]
                subprocess.run(cmd,check=True)
            s["stages"][stage]={"status":"done"};s["current_stage"]=i+1;save(pid,s)
        s["status"]="done";save(pid,s)
    except Exception as e:
        s=load(pid);s["status"]="failed";s["error"]=str(e);s["stages"][stage]={"status":"failed","error":str(e)};save(pid,s)

@app.get("/")
def index():return FileResponse(Path(__file__).parent.parent/"web"/"index.html")
@app.post("/api/projects")
def create(x:Req):
    if not x.script.strip():raise HTTPException(400,"script 不能为空")
    pid=uuid.uuid4().hex[:12];d=ROOT/pid;d.mkdir()
    s={"project_id":pid,"script":x.script,"aspect_ratio":x.aspect_ratio,"size":x.size,"status":"pending","current_stage":0,"error":None,"stages":{x:{"status":"pending"} for x in STAGES}}
    save(pid,s);return s
@app.post("/api/projects/{pid}/run")
def start(pid:str,bg:BackgroundTasks):
    if not load(pid):raise HTTPException(404,"project not found")
    bg.add_task(run,pid);return {"ok":True,"project_id":pid}
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
