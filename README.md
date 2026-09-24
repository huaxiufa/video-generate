# Agnes Story Video

独立的视频生成流水线：只需要输入剧本，自动完成 12 个阶段，并支持断点续传。

流程：初始化 → 场景配置 → 图片分析 → 故事生成 → 角色参考图 → 脚本编写 → 尾帧提示词 → 尾帧生成 → 视频生成（Agnes Video 2.5）→ 音频生成（Gemini 首次建声样，本地克隆后续）→ 字幕生成 → 视频拼接。

每个阶段、每个场景独立 checkpoint。服务重启或 API 失败后不会重复已完成任务。

启动：`docker compose up --build`，打开 http://localhost:8765。
