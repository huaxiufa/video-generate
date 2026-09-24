import uuid
from pathlib import Path
from .checkpoint import CheckpointStore
from ..config import settings
from ..models import STAGES
from ..providers.agnes import AgnesClient
from ..providers.gemini import GeminiTTS
from ..providers.voice_clone import VoiceClone
from ..media.ffmpeg import FFmpeg
class PipelineOrchestrator:
    def __init__(self):
        self.root=Path(settings.work_dir); self.root.mkdir(parents=True,exist_ok=True)
        self.agnes=AgnesClient(); self.gemini=GeminiTTS(); self.voice_clone=VoiceClone(); self.ffmpeg=FFmpeg()
    def create_project(self,script,aspect_ratio,size):
        pid=uuid.uuid4().hex[:12]; d=self.root/pid; d.mkdir(parents=True); (d/'input.txt').write_text(script)
        s={'project_id':pid,'script':script,'aspect_ratio':aspect_ratio,'size':size,'current_stage':0,'status':'pending','stages':{x:{'status':'pending'} for x in STAGES}}
        CheckpointStore(d).save(s); return s
    def get_state(self,pid): return CheckpointStore(self.root/pid).load()
    async def run(self,pid):
        d=self.root/pid; store=CheckpointStore(d); s=store.load()
        if not s: raise FileNotFoundError(pid)
        s['status']='running'; store.save(s)
        for i,stage in enumerate(STAGES):
            if store.done(stage): s['current_stage']=i+1; continue
            s['current_stage']=i; store.save(s); await self._run_stage(stage,s,d)
            store.mark_done(stage); s=store.load(); s['current_stage']=i+1; store.save(s)
        s['status']='done'; store.save(s); return s
    async def _run_stage(self,stage,s,d):
        if stage=='视频生成': await self.agnes.generate_video_from_scenes(d,s)
        elif stage=='音频生成': await self.gemini.generate_initial_voices_and_audio(d,s,self.voice_clone)
        elif stage=='视频拼接': self.ffmpeg.concat_project(d,s)
