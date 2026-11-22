FROM python:3.11-alpine@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1
RUN pip install --no-cache-dir paho-mqtt==1.6.1
COPY notify.py /app/notify.py
USER nobody
ENTRYPOINT ["python", "/app/notify.py"]
