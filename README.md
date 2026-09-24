# Video Generate V2.2

独立重构版：用户只输入脚本，系统自动完成动画视频生成。

## 12 阶段

1. 初始化
2. 场景配置
3. 图片分析
4. 故事生成
5. 角色参考图
6. 脚本编写
7. 尾帧提示词
8. 尾帧生成
9. 视频生成
10. 音频生成
11. 字幕生成
12. 视频拼接

## AI 链路

- Agnes API：文本规划、图片生成、Agnes Video 2.5 视频生成。
- Gemini TTS：每个角色只建立第一次声音样本。
- MOSS-TTS-Nano：使用角色声音样本完成后续本地 voice cloning。
- FFmpeg：音频混音、字幕烧录和最终封装。

## 断点续跑

项目状态保存在 `/data/projects/<project_id>/state.json`。每个 Agnes 视频任务保存 task.json；重启后继续轮询已有任务，不重复提交。

## 启动

```bash
cp .env.example .env
# 填 AGNES_API_KEY 和 GEMINI_API_KEY
docker compose up --build
```

MOSS-TTS-Nano 模型首次使用时缓存到 `/data/moss-models`。

## 重要

本版本已经彻底独立于旧 Agnes Video Generator 架构；仓库当前分支只保留 V2.2 所需文件。
