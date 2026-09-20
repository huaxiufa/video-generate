FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=8
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg fonts-noto-cjk libsndfile1 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/lcy362/agnes-video-generator.git /opt/agnes-base
COPY sitecustomize.py /app/sitecustomize.py
COPY night-agency-ui.js /app/night-agency-ui.js
RUN pip install --no-cache-dir --default-timeout=600 -r /opt/agnes-base/requirements.txt  && pip install --no-cache-dir --default-timeout=600 --retries 8 --no-deps git+https://github.com/OpenMOSS/MOSS-TTS-Nano.git  && cp /app/night-agency-ui.js /opt/agnes-base/static/night-agency-ui.js  && sed -i 's#</body>#<script src="/static/night-agency-ui.js"></script></body>#' /opt/agnes-base/static/index.html
ENV PYTHONPATH=/app:/opt/agnes-base
ENV NA_VOICE_DIR=/app/agnes_data/voices
WORKDIR /opt/agnes-base
EXPOSE 8765
CMD ["python","server.py"]
