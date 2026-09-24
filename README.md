# Video Generate V2.2

全新独立架构：用户只输入脚本，AI 自动完成场景拆分、视觉分析、故事整理、角色识别、角色参考图、对白/分镜脚本、尾帧、Agnes Video 2.5、音频、字幕和最终视频。

固定 12 阶段：
初始化 → 场景配置 → 图片分析 → 故事生成 → 角色参考图 → 脚本编写 → 尾帧提示词 → 尾帧生成 → 视频生成 → 音频生成 → 字幕生成 → 视频拼接

V2.2 重点：
- Agnes 文本模型负责真正的场景、视觉、故事、角色和对白规划，不再按脚本换行机械切镜头。
- Agnes Image 2.5 Flash 生成角色参考图和尾帧。
- Agnes Video 2.5 使用 keyframe 模式，首尾帧和角色参考图进入视频任务。
- 每个视频场景保存 task.json；重启后继续使用 video_id 轮询，不重复提交。
- 每个阶段持久化 state.json，失败后继续运行只执行未完成阶段。
- 角色第一次有对白时用 Gemini TTS 建立该角色声音样本；同角色后续对白调用 MOSS_TTS_MODEL_DIR 做本地克隆。
- 字幕、音频和视频均保存到项目目录。

当前 API 参数依据 Agnes 的现代 Video 2.5 协议：视频创建使用 POST /v1/videos，异步结果通过 /agnesapi?video_id=... 查询；2.5 支持 text、img2video、keyframe、reference 模式。citeturn0search0

Gemini TTS 使用 Generate Content 的 AUDIO modality；官方示例当前使用 `gemini-3.1-flash-tts-preview`。citeturn0search1

## 启动

```bash
cp .env.example .env
docker compose up --build
```

打开 http://localhost:8765。

必须配置：
- AGNES_API_KEY
- GEMINI_API_KEY
- MOSS_TTS_MODEL_DIR（角色第二句及之后的对白需要本地克隆）

MOSS_TTS_MODEL_DIR 接收三个位置参数：文本、角色参考 wav、输出 wav。

项目数据：`data/projects/<project_id>`。


### V2.2 声音链路

V2.2 已把 MOSS-TTS-Nano 直接集成进 Docker。Gemini TTS 只负责每个角色第一次台词的声音样本；后续该角色全部台词都通过本地 MOSS-TTS-Nano 做 zero-shot voice cloning，不再需要手工配置 VOICE_CLONE_COMMAND。

MOSS-TTS-Nano 官方当前提供 ONNX CPU 推理入口，支持参考音频 voice cloning；首次生成时会把 ONNX 模型下载到 /data/moss-models，之后复用本地模型缓存。citeturn0search0turn2search0

V2.2 同时修正了 Agnes Video 2.5 的 keyframe 请求：keyframe 使用 first_frame/last_frame，角色参考图先注入首帧/尾帧生成，不再把 images[] 错用于 keyframe 模式。Agnes 的 2.5 API 明确将 images[] 用于 reference 模式。citeturn0search1

字幕阶段现在会生成 SRT，并在最终视频拼接时直接烧录字幕。
