import json, re, requests
from pathlib import Path

def _extract_json(text):
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^\\s*```(?:json)?\\s*","",text,flags=re.I)
        text=re.sub(r"\\s*```\\s*$","",text)
    a=text.find("{"); b=text.rfind("}")
    if a<0 or b<=a: raise ValueError("Agnes 没有返回 JSON")
    return json.loads(text[a:b+1])

def analyze_script(script, api_key="", base_url="https://apihub.agnes-ai.com/v1", model="agnes-3.0-flash"):
    if not api_key: raise ValueError("请填写 Agnes API Key")
    system="""你是专业动画剧本导演和分镜师。把用户提供的中文正常剧本转换为可直接用于动画生成的结构化分镜。
必须严格返回 JSON，不要 Markdown。JSON 格式：
{"scenes":[{"scene_no":1,"title":"地点·时间","summary":"场景摘要"}],"shots":[{"id":1,"scene_no":1,"scene":"地点·时间","shot_size":"中景","visual":"可直接给视频模型的中文画面描述，包含人物外观、动作、环境、情绪和连续性","camera":"镜头运动/构图","duration":6,"dialogue":[{"role":"角色名","text":"台词"}]}],"warnings":[]}
规则：
1. 保留剧情事实，不擅自增加凶手、线索、人物或关键情节。
2. 正常剧本里的动作描写不是台词。
3. 台词通常不带角色名；根据上下文、上一句、动作、场景和人物位置判断说话人。
4. 每句台词必须有 role。无法确定时，把该句放入 warnings，格式为“第N镜头：台词……的说话人不确定”，并仍给出最可能角色。
5. dialogue 的 text 只能是实际说出口的内容，不要把角色名放进去。
6. 字幕最终只显示 text，绝不能显示 role。
7. 每个镜头 4-12 秒；如果对白较长，duration 必须足够容纳对白。不要为了凑时长删台词。
8. 一个镜头尽量保持一个连续动作；对白和动作要分配到合理镜头。
9. visual 不要出现字幕、文字、水印、UI；人物外观要具体、稳定。
10. 输出必须是完整合法 JSON。"""
    payload={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":"请分析下面这份剧本并生成分镜：\n\n"+script}],"temperature":0.2}
    r=requests.post(base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json=payload,timeout=180)
    if not r.ok: raise RuntimeError(f"Agnes 文本模型 HTTP {r.status_code}: {r.text[:2000]}")
    data=r.json(); content=data.get("choices",[{}])[0].get("message",{}).get("content","")
    result=_extract_json(content)
    if not result.get("shots"): raise ValueError("Agnes 返回的分镜为空")
    for i,s in enumerate(result["shots"],1):
        s["id"]=i; s["duration"]=max(4,min(12,int(s.get("duration",6))))
        s.setdefault("dialogue",[]); s.setdefault("visual",""); s.setdefault("camera","cinematic slow push-in"); s.setdefault("shot_size","中景")
    result.setdefault("scenes",[]); result.setdefault("warnings",[])
    return result

def save_storyboard(data,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
