# Video Generate V2
独立重建版：用户只输入脚本，自动生成完整视频。阶段固定为：初始化、场景配置、图片分析、故事生成、角色参考图、脚本编写、尾帧提示词、尾帧生成、视频生成、音频生成、字幕生成、视频拼接。所有阶段和 Agnes 视频任务都持久化，可重启继续。启动：cp .env.example .env && docker compose up --build。