import re, json
from pathlib import Path
SCENE_RE=re.compile(r"^(?:第[一二三四五六七八九十百0-9]+[场幕]|场景|SCENE|Scene)\b[：:\s]*(.*)$",re.I)
CHAR_RE=re.compile(r"^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z·]{0,15})[：:]\s*(.+)$")
def analyze_script(script):
    lines=[x.strip() for x in script.splitlines() if x.strip()]
    scenes=[]; current=None; speaker=None; shot_no=1
    def new_scene(title):
        nonlocal current
        current={"scene_no":len(scenes)+1,"title":title or f"场景 {len(scenes)+1}","lines":[]}
        scenes.append(current)
    for line in lines:
        m=SCENE_RE.match(line)
        if m: new_scene(m.group(1).strip() or line); speaker=None; continue
        if current is None:new_scene("开场")
        m=CHAR_RE.match(line)
        if m:
            speaker=m.group(1).strip(); current["lines"].append({"type":"dialogue","role":speaker,"text":m.group(2).strip()}); continue
        lead=re.match(r"^([\u4e00-\u9fff]{2,4})(?:走|看|站|坐|转|抬|低|盯|拿|推|进|离|停|回|问|说|开|指|靠|来到|观察|皱|沉默|看着)",line)
        if lead:speaker=lead.group(1)
        if speaker and len(line)<=45 and line.endswith(("。","？","?","！","!","……","...")):
            current["lines"].append({"type":"dialogue","role":speaker,"text":line}); continue
        current["lines"].append({"type":"action","text":line})
    for s in scenes:
        shots=[]; visual=[]; ds=[]
        for item in s["lines"]:
            (ds if item["type"]=="dialogue" else visual).append(item)
            if len(visual)>=2 or len(ds)>=2:
                shots.append(make_shot(shot_no,s,visual,ds)); shot_no+=1; visual=[]; ds=[]
        if visual or ds: shots.append(make_shot(shot_no,s,visual,ds)); shot_no+=1
        s["shots"]=shots
    return {"scenes":scenes,"shots":[x for s in scenes for x in s["shots"]]}
def make_shot(no,s,visual,ds):
    dur=max(6,min(12,round(sum(max(2,len(d["text"])*0.22) for d in ds)+2)))
    return {"id":no,"scene_no":s["scene_no"],"scene":s["title"],"shot_size":"中景","visual":" ".join(visual) or "角色自然表演，保持连续动作。","camera":"cinematic slow push-in","dialogue":ds[:],"duration":dur}
def save_storyboard(data,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
