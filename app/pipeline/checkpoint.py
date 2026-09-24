import json
from pathlib import Path
class CheckpointStore:
    def __init__(self,d): self.d=Path(d); self.d.mkdir(parents=True,exist_ok=True)
    def load(self):
        p=self.d/'state.json'; return json.loads(p.read_text()) if p.exists() else None
    def save(self,s):
        p=self.d/'state.json.tmp'; p.write_text(json.dumps(s,ensure_ascii=False,indent=2)); p.replace(self.d/'state.json')
    def done(self,stage):
        s=self.load() or {}; return s.get('stages',{}).get(stage,{}).get('status')=='done'
    def mark_done(self,stage,data=None):
        s=self.load() or {'stages':{}}; s.setdefault('stages',{})[stage]={'status':'done','data':data or {}}; self.save(s)
