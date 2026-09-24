FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk git build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN git clone --depth 1 https://github.com/OpenMOSS/MOSS-TTS-Nano.git /opt/MOSS-TTS-Nano && \
    pip install --no-cache-dir -r /opt/MOSS-TTS-Nano/requirements.txt && \
    pip install --no-cache-dir -e /opt/MOSS-TTS-Nano
COPY app ./app
COPY web ./web
RUN mkdir -p /data/projects /data/moss-models
ENV WORK_DIR=/data/projects
ENV MOSS_TTS_REPO=/opt/MOSS-TTS-Nano
ENV MOSS_TTS_MODEL_DIR=/data/moss-models
ENV MOSS_TTS_EXECUTION_PROVIDER=cpu
EXPOSE 8765
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8765"]
