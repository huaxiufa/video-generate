FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk git libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=600 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
# MOSS-TTS-Nano 的 ONNX 推理代码仍会导入 torch/torchaudio；这里使用官方 CPU wheel，
# 避免从 PyPI 拉取体积更大的 CUDA 版本。
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --timeout 600 --retries 10 \
       --index-url https://download.pytorch.org/whl/cpu \
       torch==2.7.0 torchaudio==2.7.0 \
    && python -m pip install --no-cache-dir --timeout 600 --retries 10 -r requirements.txt \
    && python -m pip install --no-cache-dir --timeout 600 --retries 10 --no-deps \
       git+https://github.com/OpenMOSS/MOSS-TTS-Nano.git

COPY . .
EXPOSE 8501
CMD ["streamlit","run","app.py","--server.address=0.0.0.0","--server.port=8501"]
