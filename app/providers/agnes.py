import asyncio,json,httpx
from pathlib import Path
from ..config import settings
class AgnesClient:
    def __init__(self): self.base=settings.agnes_base_url.rstrip('/'); self.headers={'Authorization':'Bearer '+settings.agnes_api_key}
    async def req(self,method,path,**kw):
        async with httpx.AsyncClient(timeout=300) as c:
            r=await c.request(method,self.base+path,headers=self.headers,**kw); r.raise_for_status(); return r.json()
    async def generate_image(self,prompt,**kw): return await self.req('POST','/v1/images',json={'prompt':prompt,**kw})
    async def generate_video(self,prompt,first_frame=None,last_frame=None,**kw):
        p={'model':'agnes-video-2.5','prompt':prompt,**kw}
        if first_frame: p['first_frame']=first_frame
        if last_frame: p['last_frame']=last_frame
        return await self.req('POST','/v1/videos',json=p)
    async def wait_video(self,vid):
        while True:
            x=await self.req('GET',f'/v1/videos/{vid}'); status=x.get('status')
            if status=='completed': return x
            if status in ('failed','cancelled'): raise RuntimeError(x)
            await asyncio.sleep(5)
    async def generate_video_from_scenes(self,d,s):
        for scene in s.get('scenes',[]):
            sd=d/'video'/str(scene['id']); sd.mkdir(parents=True,exist_ok=True); vf=sd/'video.mp4'; tf=sd/'task.json'
            if vf.exists(): continue
            task=json.loads(tf.read_text()) if tf.exists() else None
            if not task:
                task=await self.generate_video(scene['prompt'],scene.get('first_frame'),scene.get('last_frame'),seconds=scene.get('seconds',8),size=s.get('size','1080P'),aspect_ratio=s.get('aspect_ratio','16:9'),n=1)
                tf.write_text(json.dumps(task,ensure_ascii=False,indent=2));
            vid=task.get('id') or task.get('video_id'); result=await self.wait_video(vid); url=result.get('url') or result.get('video_url')
            if url:
                async with httpx.AsyncClient(timeout=600) as c: vf.write_bytes((await c.get(url)).content)
