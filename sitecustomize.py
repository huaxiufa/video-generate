"""Night Agency extensions loaded automatically via sitecustomize.py."""
import asyncio, base64, os, subprocess, tempfile, wave, logging
from pathlib import Path
import requests

_MARKER="__NA_TTS__|"
_VOICES=Path(os.getenv("NA_VOICE_DIR","/app/agnes_data/voices"))
_GEMINI_KEY=os.getenv("GEMINI_API_KEY","").strip()
_GEMINI_MODEL=os.getenv("GEMINI_TTS_MODEL","gemini-3.1-flash-tts-preview")
_GEMINI_VOICE=os.getenv("GEMINI_TTS_VOICE","Kore")
_MOSS_COMMAND=os.getenv("MOSS_TTS_COMMAND","moss-tts-nano generate")
_MOSS_MODEL_DIR=os.getenv("MOSS_TTS_ONNX_MODEL_DIR","").strip()
_MOSS_THREADS=os.getenv("MOSS_TTS_CPU_THREADS","4")
_LOG=logging.getLogger("NightAgency")

# 夜行事务所自己的 Agnes 视频调用层。
# 只接管 submit_video；后面的官方轮询/下载/合成流程继续复用 lcy 基础项目，
# 因而不会破坏它现有的任务、断点续传、Key 轮换和进度系统。
async def _na_video_payload(self, prompt, reference_image_paths, duration, width, height, seed, negative_prompt, **kwargs):
    model=self.model
    duration=int(duration or 5)
    refs=reference_image_paths or []

    if model in ("agnes-video-2.5-flash","agnes-video-2.5"):
        seconds=str(max(4,min(duration,12)))
        size=kwargs.get("video_size") or "720P"
        if model=="agnes-video-2.5-flash":
            size="720P"
        aspect=self._width_height_to_aspect_ratio(width,height)
        payload={
            "model":model,
            "mode":"text",
            "prompt":prompt,
            "seconds":seconds,
            "size":size,
            "aspect_ratio":aspect,
        }
        if seed is not None:
            payload["seed"]=seed

        resolved=[]
        for p in refs:
            norm=await asyncio.to_thread(_NA_ORIGINAL_NORMALIZE,p,width,height)
            resolved.append(await self._resolve_image_ref(norm))
        if len(resolved)==1:
            payload["mode"]="reference"
            payload["images"]=resolved
            mode_desc="reference (1 image)"
        elif len(resolved)>=2:
            payload["mode"]="reference"
            payload["images"]=resolved[:5]
            mode_desc=f"reference ({len(resolved[:5])} images)"
        else:
            mode_desc="text-to-video"

    elif model=="agnes-video-v2.0":
        num_frames,frame_rate=self._get_frame_config(duration,width,height)
        payload={
            "model":model,
            "prompt":prompt,
            "width":width,
            "height":height,
            "num_frames":num_frames,
            "frame_rate":frame_rate,
        }
        if seed is not None:
            payload["seed"]=seed
        if negative_prompt:
            payload["negative_prompt"]=negative_prompt

        resolved=[]
        for p in refs:
            norm=await asyncio.to_thread(_NA_ORIGINAL_NORMALIZE,p,width,height)
            resolved.append(await self._resolve_image_ref(norm))
        if len(resolved)==1:
            payload["image"]=resolved[0]
            payload["mode"]="ti2vid"
            mode_desc="image-to-video"
        elif len(resolved)>=2:
            payload["extra_body"]={"image":resolved,"mode":"keyframes"}
            mode_desc=f"keyframes ({len(resolved)} frames)"
        else:
            mode_desc="text-to-video"
    else:
        # 自定义新模型：默认按 2.5 文生视频协议发出，方便后续测试新版本。
        payload={
            "model":model,
            "mode":"text",
            "prompt":prompt,
            "seconds":str(max(4,min(duration,12))),
            "size":"720P",
            "aspect_ratio":self._width_height_to_aspect_ratio(width,height),
        }
        mode_desc="custom-2.5-compatible"

    return payload,mode_desc

def _safe(v): return "".join(c for c in str(v) if c.isalnum() or c in "-_.")[:80] or "default"
def _master(role):
    _VOICES.mkdir(parents=True,exist_ok=True); return _VOICES/f"{_safe(role)}.wav"
def _pcm_wav(path,pcm):
    with wave.open(str(path),"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
def _gemini(text,model,voice,out):
    if not _GEMINI_KEY: raise RuntimeError("GEMINI_API_KEY 未配置")
    r=requests.post("https://generativelanguage.googleapis.com/v1beta/interactions",headers={"x-goog-api-key":_GEMINI_KEY},json={"model":model or _GEMINI_MODEL,"input":text,"response_format":{"type":"audio"},"generation_config":{"speech_config":[{"voice":voice or _GEMINI_VOICE}]}},timeout=180)
    r.raise_for_status(); data=r.json().get("output_audio",{}).get("data")
    if not data: raise RuntimeError("Gemini TTS 未返回 output_audio.data")
    _pcm_wav(out,base64.b64decode(data))
def _moss(text,ref,out):
    cmd=_MOSS_COMMAND.split()+["--backend","onnx","--prompt-speech",str(ref),"--text",text,"--output",str(out),"--execution-provider","cpu","--cpu-threads",str(max(1,int(_MOSS_THREADS)))]
    if _MOSS_MODEL_DIR: cmd += ["--model-dir",_MOSS_MODEL_DIR]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=600)
    if p.returncode: raise RuntimeError("MOSS-TTS-Nano failed: "+p.stdout[-2000:])
def _atempo_filter(rate):
    rate=max(0.5,min(float(rate or 1.0),1.5))
    return f"atempo={rate:.4f}"

def _mp3(src,dst,rate=1.0):
    p=subprocess.run(["ffmpeg","-y","-i",str(src),"-filter:a",_atempo_filter(rate),"-c:a","libmp3lame","-q:a","4",str(dst)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise RuntimeError("ffmpeg 音频转换失败: "+p.stderr[-1000:])
def _parse(v):
    p=v.split("|")
    return None if len(p)<3 or p[0]!="__NA_TTS__" else {"provider":p[1],"role":p[2] or "default","voice":p[3] if len(p)>3 and p[3] else _GEMINI_VOICE,"model":p[4] if len(p)>4 and p[4] else _GEMINI_MODEL,"rate":p[5] if len(p)>5 and p[5] else "1.0","force":p[6]=="1" if len(p)>6 else False}}
def _validate(audio_voice,*a,**k):
    if isinstance(audio_voice,str) and audio_voice.startswith(_MARKER): return
    return _ORIGINAL_VALIDATE(audio_voice,*a,**k)
_ORIGINAL_VALIDATE=lambda *a,**k: None
_NA_VIDEO_PATCHED=False
_NA_ORIGINAL_NORMALIZE=None

def install():
    global _NA_VIDEO_PATCHED,_NA_ORIGINAL_NORMALIZE
    try:
        import core.audio.tts as tts
        try:
            import web.helpers as helpers
            globals()["_ORIGINAL_VALIDATE"]=helpers._validate_voice_compat
            helpers._validate_voice_compat=_validate
        except Exception: pass

        # TTS：首次 Gemini，之后 MOSS。
        if not getattr(tts.EdgeTTSEngine,"_na_patched",False):
            original_generate,original_harvest=tts.EdgeTTSEngine.generate,tts.EdgeTTSEngine.harvest_cues
            async def generate(self,text,output_path,voice="zh-CN-XiaoxiaoNeural",rate="+0%"):
                cfg=_parse(voice)
                if not cfg: return await original_generate(self,text,output_path,voice,rate)
                role,master=cfg["role"],_master(cfg["role"])
                with tempfile.TemporaryDirectory(prefix="na-tts-") as td:
                    tmp=Path(td)/"speech.wav"
                    if cfg["provider"]=="gemini_moss" and master.exists() and not cfg.get("force"): _moss(text,master,tmp)
                    else:
                        _gemini(text,cfg["model"],cfg["voice"],tmp)
                        if cfg["provider"]=="gemini_moss":
                            master.parent.mkdir(parents=True,exist_ok=True); tmp.replace(master); tmp=master
                    _mp3(tmp,Path(output_path),cfg.get("rate",1.0))
                return output_path,None
            async def harvest(self,text,voice="zh-CN-XiaoxiaoNeural",rate="+0%"):
                if _parse(voice): return None
                return await original_harvest(self,text,voice,rate)
            tts.EdgeTTSEngine.generate,tts.EdgeTTSEngine.harvest_cues=generate,harvest
            tts.EdgeTTSEngine._na_patched=True

        # 视频：完全走夜行事务所自己的 model -> payload 分流。
        if not _NA_VIDEO_PATCHED:
            from core.api import agnes_video as av
            _NA_ORIGINAL_NORMALIZE=av.normalize_reference_path
            original_submit=av.AgnesVideoAPI.submit_video

            async def submit_video(self,prompt,reference_image_paths=[],duration=None,width=1152,height=768,seed=None,negative_prompt=None,**kwargs):
                payload,mode_desc=await _na_video_payload(
                    self,prompt,reference_image_paths,duration,width,height,seed,negative_prompt,**kwargs
                )
                _LOG.info("[NightAgencyVideo] model=%s mode=%s payload=%s",self.model,mode_desc,{k:v for k,v in payload.items() if k not in ("images","image")})
                return await self._submit_with_retry(payload,mode_desc)

            # 保存原方法供调试/回滚；真正运行时不再调用原 submit_video。
            av.AgnesVideoAPI._night_agency_original_submit=original_submit
            av.AgnesVideoAPI.submit_video=submit_video
            av.AgnesVideoAPI._night_agency_video_patched=True
            _NA_VIDEO_PATCHED=True
            _LOG.info("[NightAgencyVideo] 独立 Agnes 视频调用层已启用")
    except Exception as e:
        print("[NightAgency] install failed:",e)

install()
