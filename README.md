# Video Generate V2.1

全新独立架构：用户只输入脚本，AI 自动完成场景拆分、视觉分析、故事整理、角色识别、角色参考图、对白/分镜脚本、尾帧、Agnes Video 2.5、音频、字幕和最终视频。

固定 12 阶段：
初始化 → 场景配置 → 图片分析 → 故事生成 → 角色参考图 → 脚本编写 → 尾帧提示词 → 尾帧生成 → 视频生成 → 音频生成 → 字幕生成 → 视频拼接

V2.1 重点：
- Agnes 文本模型负责真正的场景、视觉、故事、角色和对白规划，不再按脚本换行机械切镜头。
- Agnes Image 2.5 Flash 生成角色参考图和尾帧。
- Agnes Video 2.5 使用 keyframe 模式，首尾帧和角色参考图进入视频任务。
- 每个视频场景保存 task.json；重启后继续使用 video_id 轮询，不重复提交。
- 每个阶段持久化 state.json，失败后继续运行只执行未完成阶段。
- 角色第一次有对白时用 Gemini TTS 建立该角色声音样本；同角色后续对白调用 VOICE_CLONE_COMMAND 做本地克隆。
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
- VOICE_CLONE_COMMAND（角色第二句及之后的对白需要本地克隆）

VOICE_CLONE_COMMAND 接收三个位置参数：文本、角色参考 wav、输出 wav。

项目数据：`data/projects/<project_id>`。
