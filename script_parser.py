import json, re, requests
from pathlib import Path

def _extract_json(text):
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^\s*```(?:json)?\s*","",text,flags=re.I)
        text=re.sub(r"\s*```\s*$","",text)
    a=text.find("{"); b=text.rfind("}")
    if a<0 or b<=a: raise ValueError("Agnes 没有返回 JSON")
    return json.loads(text[a:b+1])

SYSTEM_PROMPT = """你是专业动画剧本导演、分镜师和剪辑师。把用户提供的中文正常剧本转换为可直接制作动画的结构化分镜。
必须严格返回 JSON，不要 Markdown。
JSON 格式：
{"scenes":[{"scene_no":1,"title":"地点·时间","summary":"场景摘要"}],
"shots":[{"id":1,"scene_no":1,"scene":"地点·时间","shot_size":"中景","visual":"可直接给视频模型的中文画面描述，包含人物外观、动作、环境、情绪和连续性","camera":"镜头运动/构图","duration":6,"dialogue":[{"role":"角色名","text":"台词"}]}],
"segments":[{"segment_no":1,"title":"剧情片段标题","summary":"这个连续片段发生了什么","shot_ids":[1,2],"target_duration":12}],
"warnings":[]}

规则：
1. 保留剧情事实，不擅自增加凶手、线索、人物或关键情节。
2. 正常剧本里的动作描写不是台词。
3. 台词通常不带角色名；根据上下文、上一句、动作、场景和人物位置判断说话人。
4. 每句台词必须有 role。无法确定时放入 warnings，并给出最可能角色。
5. dialogue.text 只能是实际说出口的内容，不要把角色名放进去。
6. 字幕最终只显示 text，绝不能显示 role。
7. 每个镜头 4-12 秒；对白较长时 duration 要足够，不要删台词。
8. 剧情片段不需要固定时长，也不要为了凑时长强行切镜头。优先在自然的动作、对白和镜头边界切段；通常一个片段可包含连续的多个镜头，时长可自然落在约6-30秒或更长，只要叙事连贯、地点和动作连续即可。
9. segments.shot_ids 必须覆盖全部 shots，按剧情顺序排列，每个镜头只能属于一个 segment，不能漏镜头、不能重复镜头。
10. 一个剧情片段尽量保持同一地点、同一小段连续行动，避免把一句完整对白拆到两个片段。
11. visual 不要出现字幕、文字、水印、UI；人物外观要具体、稳定。
12. 输出必须是完整合法 JSON。"""

def analyze_script(script, api_key="", base_url="https://apihub.agnes-ai.com/v1", model="agnes-3.0-flash"):
    if not api_key: raise ValueError("请填写 Agnes API Key")
    payload={"model":model,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":"请分析下面这份完整剧本并生成分镜与自然连续的剧情片段：\n\n"+script}],"temperature":0.2}
    r=requests.post(base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json=payload,timeout=300)
    if not r.ok: raise RuntimeError(f"Agnes 文本模型 HTTP {r.status_code}: {r.text[:2000]}")
    data=r.json(); content=data.get("choices",[{}])[0].get("message",{}).get("content","")
    result=_extract_json(content)
    if not result.get("shots"): raise ValueError("Agnes 返回的分镜为空")
    for i,s in enumerate(result["shots"],1):
        s["id"]=i; s["duration"]=max(4,min(12,int(s.get("duration",6))))
        s.setdefault("dialogue",[]); s.setdefault("visual",""); s.setdefault("camera","cinematic slow push-in"); s.setdefault("shot_size","中景")
    result.setdefault("scenes",[]); result.setdefault("warnings",[])
    result["segments"]=normalize_segments(result.get("segments"),result["shots"])
    return result

def normalize_segments(raw, shots):
    ids=[s["id"] for s in shots]
    valid=set(ids); used=set(); segments=[]
    for i,seg in enumerate(raw or [],1):
        if not isinstance(seg,dict): continue
        picked=[]
        for sid in seg.get("shot_ids",[]):
            try: sid=int(sid)
            except: continue
            if sid in valid and sid not in used:
                picked.append(sid); used.add(sid)
        if picked:
            dur=sum(next(s["duration"] for s in shots if s["id"]==sid) for sid in picked)
            segments.append({"segment_no":len(segments)+1,"title":seg.get("title",f"剧情片段 {len(segments)+1:03d}"),"summary":seg.get("summary",""),"shot_ids":picked,"target_duration":round(dur,2)})
    for sid in ids:
        if sid not in used:
            # 保证任何异常 AI 返回都不会丢镜头
            segments.append({"segment_no":len(segments)+1,"title":f"剧情片段 {len(segments)+1:03d}","summary":"","shot_ids":[sid],"target_duration":next(s["duration"] for s in shots if s["id"]==sid)})
    for i,s in enumerate(segments,1):
        s["segment_no"]=i
    return segments

def save_storyboard(data,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
