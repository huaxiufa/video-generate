from pathlib import Path
class FFmpeg:
    def concat_project(self,project_dir,state):
        out=project_dir/'final.mp4'
        if out.exists(): return out
        raise RuntimeError('视频拼接阶段尚未配置 scene/audio/subtitle 输入')
