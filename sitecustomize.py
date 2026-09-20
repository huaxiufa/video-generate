"""Night Agency extensions loaded automatically via sitecustomize.py."""
import asyncio, base64, os, subprocess, tempfile, wave
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
def _safe(v): return "".join(c if c.isalnum() or c in "-_." else "_" for c in v.strip())[:80] or "default"
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
def _mp3(src,dst):
    p=subprocess.run(["ffmpeg","-y","-i",str(src),"-c:a","libmp3lame","-q:a","4",str(dst)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise RuntimeError("ffmpeg 音频转换失败: "+p.stderr[-1000:])
def _parse(v):
    p=v.split("|")
    return None if len(p)<3 or p[0]!="__NA_TTS__" else {"provider":p[1],"role":p[2] or "default","voice":p[3] if len(p)>3 and p[3] else _GEMINI_VOICE,"model":p[4] if len(p)>4 and p[4] else _GEMINI_MODEL}
def _validate(audio_voice,*a,**k):
    if isinstance(audio_voice,str) and audio_voice.startswith(_MARKER): return
    return _ORIGINAL_VALIDATE(audio_voice,*a,**k)
_ORIGINAL_VALIDATE=lambda *a,**k: None
def install():
    try:
        import core.audio.tts as tts
        if getattr(tts.EdgeTTSEngine,"_na_patched",False): return
        original_generate,original_harvest=tts.EdgeTTSEngine.generate,tts.EdgeTTSEngine.harvest_cues
        try:
            import web.helpers as helpers
            globals()["_ORIGINAL_VALIDATE"]=helpers._validate_voice_compat
            helpers._validate_voice_compat=_validate
        except Exception: pass
        async def generate(self,text,output_path,voice="zh-CN-XiaoxiaoNeural",rate="+0%"):
            cfg=_parse(voice)
            if not cfg: return await original_generate(self,text,output_path,voice,rate)
            role,master=cfg["role"],_master(cfg["role"])
            with tempfile.TemporaryDirectory(prefix="na-tts-") as td:
                tmp=Path(td)/"speech.wav"
                if cfg["provider"]=="gemini_moss" and master.exists(): _moss(text,master,tmp)
                else:
                    _gemini(text,cfg["model"],cfg["voice"],tmp)
                    if cfg["provider"]=="gemini_moss" and not master.exists(): master.parent.mkdir(parents=True,exist_ok=True); tmp.replace(master); tmp=master
                _mp3(tmp,Path(output_path))
            return output_path,None
        async def harvest(self,text,voice="zh-CN-XiaoxiaoNeural",rate="+0%"):
            if _parse(voice): return None
            return await original_harvest(self,text,voice,rate)
        tts.EdgeTTSEngine.generate,tts.EdgeTTSEngine.harvest_cues=generate,harvest
        tts.EdgeTTSEngine._na_patched=True
    except Exception as e: print("[NightAgency] install failed:",e)
install()
