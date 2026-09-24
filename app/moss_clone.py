import os,subprocess,sys
from pathlib import Path

text,reference,output=sys.argv[1:4]
repo=os.getenv("MOSS_TTS_REPO","/opt/MOSS-TTS-Nano")
model_dir=os.getenv("MOSS_TTS_MODEL_DIR","/data/moss-models")
cmd=["python",str(Path(repo)/"infer_onnx.py"),"--model-dir",model_dir,
     "--prompt-audio-path",reference,"--text",text,"--output-audio-path",output,
     "--execution-provider",os.getenv("MOSS_TTS_EXECUTION_PROVIDER","cpu"),
     "--cpu-threads",os.getenv("MOSS_TTS_CPU_THREADS","4"),
     "--disable-wetext-processing","--disable-normalize-tts-text"]
subprocess.run(cmd,check=True)
if not Path(output).exists() or Path(output).stat().st_size<1024:
    raise SystemExit("MOSS-TTS-Nano did not produce a valid wav")
