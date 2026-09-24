import os, subprocess, sys, tempfile
from pathlib import Path

text, reference, output = sys.argv[1:4]
repo = os.getenv("MOSS_TTS_REPO", "/opt/MOSS-TTS-Nano")
model_dir = os.getenv("MOSS_TTS_MODEL_DIR", "/data/moss-models")

# MOSS ONNX expects 48 kHz PCM WAV for its audio tokenizer.
normalized_reference = Path(output).with_suffix(".reference.wav")
try:
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", reference,
        "-ar", "48000", "-ac", "2", "-sample_fmt", "s16",
        str(normalized_reference),
    ], check=True)

    cmd = [
        "python", str(Path(repo) / "infer_onnx.py"),
        "--model-dir", model_dir,
        "--prompt-audio-path", str(normalized_reference),
        "--text", text,
        "--output-audio-path", output,
        "--execution-provider", os.getenv("MOSS_TTS_EXECUTION_PROVIDER", "cpu"),
        "--cpu-threads", os.getenv("MOSS_TTS_CPU_THREADS", "4"),
        "--disable-wetext-processing",
        "--disable-normalize-tts-text",
    ]
    subprocess.run(cmd, check=True)
finally:
    normalized_reference.unlink(missing_ok=True)

if not Path(output).exists() or Path(output).stat().st_size < 1024:
    raise SystemExit("MOSS-TTS-Nano ONNX did not produce a valid wav")
