import os,json,uuid,asyncio,base64,subprocess
from pathlib import Path
import httpx
from fastapi import FastAPI,BackgroundTasks,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
ROOT=Path(os.getenv("WORK_DIR","/data/projects")); ROOT.mkdir(parents=True,exist_ok=True)
STAGES=["初始化","场景配置","图片分析","故事生成","角色参考图","脚本编写","尾帧提示词","尾帧生成","视频生成","音频生成","字幕生成","视频拼接"]
AGNES=os.getenv("AGNES_BASE_URL","https://apihub.agnes-ai.com").rstrip("/")
app=FastAPI(title="Video Generate V2")
class Req(BaseModel): script:str; aspect_ratio:str="16:9"; size:str="1080P"
def load(pid):
 p=ROOT/pid/"state.json"
 return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
def save(pid,s):
 d=ROOT/pid; t=d/"state.tmp"; t.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8"); t.replace(d/"state.json")
async def agnes(method,path,**kw):
 key=os.getenv("AGNES_API_KEY")
 if not key: raise RuntimeError("AGNES_API_KEY 未配置")
 async with httpx.AsyncClient(timeout=300) as c:
  r=await c.request(method,AGNES+path,headers={"Authorization":"Bearer "+key},**kw); r.raise_for_status(); return r.json()
async def image(prompt,out):
 out=Path(out)
 if out.exists() and out.stat().st_size>1024:return
 x=await agnes("POST","/v1/images/generations",json={"model":os.getenv("AGNES_IMAGE_MODEL","agnes-image-2.5-flash"),"prompt":prompt,"size":"1024x576","n":1})
 item=(x.get("data") or [{}])[0]
 if item.get("b64_json"): out.write_bytes(base64.b64decode(item["b64_json"])); return
 url=item.get("url")
 if not url: raise RuntimeError("Agnes 图片返回异常")
 async with httpx.AsyncClient(timeout=300) as c:
  r=await c.get(url); r.raise_for_status(); out.write_bytes(r.content)
async def video(pid,s,scene):
 d=ROOT/pid; sd=d/"video"/str(scene["id"]); sd.mkdir(parents=True,exist_ok=True); out=sd/"video.mp4"; tf=sd/"task.json"
 if out.exists() and out.stat().st_size>1024:return
 task=json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else None
 if not task:
  task=await agnes("POST","/v1/videos",json={"model":os.getenv("AGNES_VIDEO_MODEL","agnes-video-2.5"),"mode":"keyframe","prompt":scene["video_prompt"],"seconds":scene["seconds"],"size":s["size"],"aspect_ratio":s["aspect_ratio"],"n":1})
  tf.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding="utf-8")
 vid=task.get("id") or task.get("video_id")
 while True:
  x=await agnes("GET",f"/agnesapi?video_id={vid}&model_name={os.getenv('AGNES_VIDEO_MODEL','agnes-video-2.5')}")
  if str(x.get("status","")).lower()=="completed":break
  if str(x.get("status","")).lower() in {"failed","cancelled","error"}:raise RuntimeError("Agnes 视频任务失败")
  await asyncio.sleep(2)
 url=x.get("url") or x.get("video_url") or (x.get("data") or {}).get("url")
 if not url:raise RuntimeError("Agnes 没有返回视频地址")
 async with httpx.AsyncClient(timeout=900) as c:
  r=await c.get(url); r.raise_for_status(); out.with_suffix(".part").write_bytes(r.content)
 out.with_suffix(".part").replace(out)
async def run(pid):
 s=load(pid); d=ROOT/pid
 try:
  s["status"]="running"; save(pid,s)
  for i,stage in enumerate(STAGES):
   if s["stages"][stage]["status"]=="done":continue
   s["current_stage"]=i;s["stages"][stage]={"status":"running"};save(pid,s)
   if stage=="初始化":
    for n in ["images","characters","video","audio"]: (d/n).mkdir(exist_ok=True)
   elif stage=="场景配置":
    lines=[x.strip() for x in s["script"].splitlines() if x.strip()]
    s["scenes"]=[{"id":i,"raw":x,"seconds":8} for i,x in enumerate(lines)]
   elif stage=="图片分析":
    for x in s["scenes"]:x["visual_prompt"]="cinematic anime, consistent character design, "+x["raw"]
   elif stage=="故事生成":
    s["story"]={"title":"Auto Video","tone":"cinematic anime"}
    for x in s["scenes"]:x["story_beat"]=x["raw"]
   elif stage=="角色参考图":
    s["characters"]=[]
   elif stage=="脚本编写":
    for x in s["scenes"]:x["video_prompt"]=x["visual_prompt"]+". "+x["story_beat"]+". natural camera motion."
   elif stage=="尾帧提示词":
    for x in s["scenes"]:x["last_frame_prompt"]="stable final frame, "+x["visual_prompt"]
   elif stage=="尾帧生成":
    for x in s["scenes"]:
     p=d/"images"/f"{x['id']}_last.png";await image(x["last_frame_prompt"],p);x["last_frame_ref"]=str(p)
   elif stage=="视频生成":
    for x in s["scenes"]:await video(pid,s,x)
   elif stage=="音频生成":
    # Gemini 首次建声入口；未配置 Gemini 时保留失败状态，重跑本阶段即可。
    key=os.getenv("GEMINI_API_KEY")
    if not key:raise RuntimeError("GEMINI_API_KEY 未配置")
    for x in s["scenes"]:
     out=d/"audio"/f"{x['id']}.wav"
     if out.exists() and out.stat().st_size>1024:continue
     model=os.getenv("GEMINI_TTS_MODEL","gemini-3.8-flash-lite-tts")
     url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
     body={"contents":[{"parts":[{"text":x["raw"]}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":os.getenv("GEMINI_TTS_VOICE","Kore")}}}}}
     async with httpx.AsyncClient(timeout=300) as c:
      r=await c.post(url,params={"key":key},json=body);r.raise_for_status();data=r.json()
     raw=data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"];pcm=out.with_suffix(".pcm");pcm.write_bytes(base64.b64decode(raw));subprocess.run(["ffmpeg","-y","-f","s16le","-ar","24000","-ac","1","-i",str(pcm),str(out)],check=True);pcm.unlink(missing_ok=True)
   elif stage=="字幕生成":
    s["subtitles"]=[{"start":i*8,"end":(i+1)*8,"text":x["raw"]} for i,x in enumerate(s["scenes"])]
    (d/"subtitles.json").write_text(json.dumps(s["subtitles"],ensure_ascii=False,indent=2),encoding="utf-8")
   elif stage=="视频拼接":
    vids=sorted((d/"video").glob("*/video.mp4"),key=lambda p:int(p.parent.name));lst=d/"concat.txt";lst.write_text("".join("file '"+p.resolve().as_posix()+"'\n" for p in vids),encoding="utf-8");subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(d/"final.mp4")],check=True)
   s["stages"][stage]={"status":"done"};s["current_stage"]=i+1;save(pid,s)
  s["status"]="done";save(pid,s)
 except Exception as e:
  s=load(pid);s["status"]="failed";s["error"]=str(e);s["stages"][stage]={"status":"failed","error":str(e)};save(pid,s)
@app.get("/")
def index():return FileResponse(Path(__file__).parent.parent/"web"/"index.html")
@app.post("/api/projects")
def create(x:Req):
 if not x.script.strip():raise HTTPException(400,"script 不能为空")
 pid=uuid.uuid4().hex[:12];d=ROOT/pid;d.mkdir();s={"project_id":pid,"script":x.script,"aspect_ratio":x.aspect_ratio,"size":x.size,"status":"pending","current_stage":0,"error":None,"stages":{x:{"status":"pending"} for x in STAGES}};save(pid,s);return s
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