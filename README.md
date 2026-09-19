# Agnes Video Generator

基于 Agnes Video API 的网页视频生成器，支持 Edge TTS 中文角色配音、真实 TTS 时间轴、自动 SRT 中文字幕，以及对白超出原视频时自动延长最后画面。

## 功能

- 🎬 Agnes Video 2.5 Flash
- 🎙️ Edge TTS 中文角色声音
- 📝 网页对白编辑
- ⏱️ 按真实 TTS 时长建立时间轴
- 💬 自动生成中文字幕
- 🧊 对白超过画面时自动克隆最后一帧延长
- 🎞️ FFmpeg 自动合成 MP4
- 💾 Agnes video_id 断点续跑
- 🐳 Docker / docker-compose

## 启动

1. 复制 `.env.example` 为 `.env` 并填写 `AGNES_API_KEY`。
2. 运行 `docker compose up --build`。
3. 浏览器打开 `http://localhost:8501`。

也可以直接安装依赖后运行 `pip install -r requirements.txt` 和 `streamlit run app.py`。

## 时间轴规则

TTS 实际生成的音频长度决定字幕结束时间和最终音频长度。若对白超过 Agnes 原始视频时长，程序使用 FFmpeg 克隆最后画面，使视频覆盖完整对白，再烧录字幕并混入音频。

## 项目结构

- `app.py` — Web UI
- `pipeline.py` — Agnes / TTS / 时间轴 / SRT / FFmpeg
- `output/` — 最终视频
- `audio/` — TTS 音频
- `cache/tasks.json` — Agnes 任务断点信息
