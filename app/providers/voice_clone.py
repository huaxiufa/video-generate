import asyncio
from ..config import settings
class VoiceClone:
    async def synthesize(self,text,voice_sample,output):
        if not settings.voice_clone_command: raise RuntimeError('VOICE_CLONE_COMMAND 未配置')
        p=await asyncio.create_subprocess_exec(settings.voice_clone_command,text,str(voice_sample),str(output)); code=await p.wait()
        if code: raise RuntimeError(f'voice clone exit code={code}')
