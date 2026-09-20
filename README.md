# Agnes Video Generator · 夜行事务所

一个面向中文动画连续剧制作的网页工作台：**完整剧本 → Agnes AI 自动分镜 → 约12秒剧情片段 → 中文 TTS → 中文字幕 → 片段拼接 → 完整一集**。

## 核心工作流

1. 在网页中一次性粘贴完整剧本，不需要手写“角色|台词”。
2. Agnes 文本模型理解人物、场景、动作和对白，并自动生成镜头。
3. 自动把镜头组织成**目标约12秒的剧情片段**。每个片段可以包含1～多个 Agnes 镜头；单个 Agnes 镜头仍限制在4～12秒。
4. 每个镜头独立生成动画画面。
5. Edge TTS 根据角色声音配置生成中文配音。
6. 使用真实 TTS 时长生成 SRT，字幕只显示台词正文，不显示角色名。
7. 如果对白超过原始画面时长，自动冻结最后一帧，保证最后一句对白也有声音和字幕。
8. 镜头先拼成 segment_001.mp4、segment_002.mp4……，最后按剧情顺序拼成 night_agency_episode.mp4。

## 12秒片段规则

- 目标：每个剧情片段约 **12 秒**。
- 实际允许一定浮动（默认8～16秒），优先保证剧情和对白完整。
- 不为了凑12秒删除对白。
- 用户可以在“审核12秒片段”页面调整镜头时长，保存后片段时长会重新计算。
- 片段边界优先放在动作或对白自然结束的位置。

## 断点续跑

cache/tasks.json 保存 Agnes video_id。如果某个镜头生成后程序中断，再次运行会继续查询已有任务，而不是盲目重复提交。

## 中文声音

侧栏可以：
- 选择 Edge TTS 中文角色声音；
- 选择 Gemini TTS；
- 选择 **Gemini 首句 + MOSS-TTS-Nano 续配音**：每个角色第一次没有声音母带时调用一次 Gemini，把生成的 WAV 保存到 `audio/voices/`；之后该角色的新对白直接使用 MOSS-TTS-Nano 的 ONNX CPU 零样本音色克隆，不再调用 Gemini；
- 调整 Edge TTS 语速和音高；
- 导入之前生成的 night-agency-voices.zip 覆盖声音配置。

### MOSS-TTS-Nano 声音克隆

本项目使用 MOSS-TTS-Nano 的 ONNX CPU 推理作为轻量级续配音引擎。官方项目目前提供约 0.1B 参数的 Nano 模型，支持中文、参考音频 voice cloning，并提供 ONNX CPU 推理路径；因此不需要像 CosyVoice 3 那样额外运行一个大型 GPU 服务。

工作方式：

1. 某角色第一次出现：Gemini TTS 生成第一句。
2. 自动把这句声音保存成 `audio/voices/<角色>.wav`。
3. 后续该角色的所有新对白：使用这个 WAV 作为参考音频，交给 MOSS-TTS-Nano 生成。
4. 相同对白仍会命中本地 TTS 缓存。

角色声音母带会保存在：
- `audio/voices/<角色>.wav`
- `audio/voices/<角色>.txt`

MOSS-TTS-Nano 的 ONNX 模型首次运行时会自动下载并缓存。可通过 `MOSS_TTS_ONNX_MODEL_DIR` 指定本地模型目录，或通过 `HF_HOME` 控制 Hugging Face 缓存位置。

## 启动

1. 复制 .env.example 为 .env 并填写 AGNES_API_KEY。
2. 运行：

    docker compose up --build

3. 浏览器打开 http://localhost:8501。

如果已经构建过镜像，通常直接运行 docker compose up 即可。

## 项目结构

- app.py — Streamlit 网页界面
- script_parser.py — 完整剧本理解、分镜和12秒片段规划
- pipeline.py — Agnes 视频、TTS、SRT、FFmpeg、片段/整集拼接
- output/ — 视频、字幕、FFmpeg 日志
- audio/ — TTS 音频
- cache/ — 剧本、项目设置、Agnes 任务断点
