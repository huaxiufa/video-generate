FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN git clone --depth 1 https://github.com/OpenMOSS/MOSS-TTS-Nano.git /opt/MOSS-TTS-Nano
RUN python - <<'PY'
from pathlib import Path
p=Path("/opt/MOSS-TTS-Nano/onnx_tts_runtime.py")
s=p.read_text()
s=s.replace("import torch\nimport torchaudio\n","")
old='''def _load_reference_audio(self, reference_audio_path: str | Path) -> np.ndarray:
        waveform, sample_rate = torchaudio.load(str(Path(reference_audio_path).expanduser().resolve()))
        waveform = waveform.to(torch.float32)
        target_sample_rate = int(self.codec_meta["codec_config"]["sample_rate"])
        target_channels = int(self.codec_meta["codec_config"]["channels"])
        if sample_rate != target_sample_rate:
            waveform = torchaudio.functional.resample(waveform, sample_rate, target_sample_rate)
        current_channels = int(waveform.shape[0])
        if current_channels == target_channels:
            pass
        elif current_channels == 1 and target_channels > 1:
            waveform = waveform.repeat(target_channels, 1)
        elif current_channels > 1 and target_channels == 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        else:
            raise ValueError(f"Unsupported reference audio channel conversion: {current_channels} -> {target_channels}")
        return waveform.unsqueeze(0).detach().cpu().numpy().astype(np.float32, copy=False)
'''
new='''def _load_reference_audio(self, reference_audio_path: str | Path) -> np.ndarray:
        path = Path(reference_audio_path).expanduser().resolve()
        with wave.open(str(path), "rb") as wav_file:
            channels = int(wav_file.getnchannels())
            sample_width = int(wav_file.getsampwidth())
            sample_rate = int(wav_file.getframerate())
            frame_count = int(wav_file.getnframes())
            if sample_width != 2:
                raise ValueError("Reference audio must be 16-bit PCM WAV.")
            raw = wav_file.readframes(frame_count)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if channels <= 0 or samples.size % channels:
            raise ValueError("Invalid reference audio channel layout.")
        waveform = samples.reshape(-1, channels)
        target_sample_rate = int(self.codec_meta["codec_config"]["sample_rate"])
        target_channels = int(self.codec_meta["codec_config"]["channels"])
        if sample_rate != target_sample_rate:
            raise ValueError(
                f"Reference audio must be {target_sample_rate} Hz; received {sample_rate} Hz."
            )
        if channels == target_channels:
            pass
        elif channels == 1 and target_channels > 1:
            waveform = np.repeat(waveform, target_channels, axis=1)
        elif channels > 1 and target_channels == 1:
            waveform = waveform.mean(axis=1, keepdims=True)
        else:
            raise ValueError(f"Unsupported reference audio channel conversion: {channels} -> {target_channels}")
        return np.transpose(waveform, (1, 0))[None, ...].astype(np.float32, copy=False)
'''
if old not in s:
    raise SystemExit("MOSS ONNX runtime reference-audio block changed upstream; patch aborted")
p.write_text(s.replace(old,new))
PY
COPY app ./app
COPY web ./web
RUN mkdir -p /data/projects /data/moss-models
ENV WORK_DIR=/data/projects
ENV MOSS_TTS_REPO=/opt/MOSS-TTS-Nano
ENV MOSS_TTS_MODEL_DIR=/data/moss-models
ENV MOSS_TTS_EXECUTION_PROVIDER=cpu
EXPOSE 8765
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8765"]
