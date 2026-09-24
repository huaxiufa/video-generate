from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .pipeline.orchestrator import PipelineOrchestrator
app=FastAPI(title='Agnes Story Video')
orchestrator=PipelineOrchestrator()
class ProjectRequest(BaseModel):
    script:str
    aspect_ratio:str='16:9'
    size:str='1080P'
@app.get('/')
def index(): return FileResponse(Path(__file__).parent.parent/'web'/'index.html')
@app.post('/api/projects')
def create(req:ProjectRequest):
    if not req.script.strip(): raise HTTPException(400,'剧本不能为空')
    return orchestrator.create_project(req.script,req.aspect_ratio,req.size)
@app.post('/api/projects/{project_id}/run')
async def run(project_id:str): return await orchestrator.run(project_id)
@app.get('/api/projects/{project_id}')
def state(project_id:str):
    s=orchestrator.get_state(project_id)
    if not s: raise HTTPException(404,'项目不存在')
    return s
