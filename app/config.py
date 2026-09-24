import os
from dataclasses import dataclass
@dataclass(frozen=True)
class Settings:
    agnes_base_url:str=os.getenv('AGNES_BASE_URL','https://api.agnes.video')
    agnes_api_key:str=os.getenv('AGNES_API_KEY','')
    gemini_api_key:str=os.getenv('GEMINI_API_KEY','')
    gemini_tts_model:str=os.getenv('GEMINI_TTS_MODEL','gemini-3.1-flash-tts-preview')
    voice_clone_command:str=os.getenv('VOICE_CLONE_COMMAND','')
    work_dir:str=os.getenv('WORK_DIR','/data/projects')
settings=Settings()
