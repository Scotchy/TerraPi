FROM python:3.11-alpine@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1
WORKDIR /app
RUN pip install --no-cache-dir paho-mqtt==1.6.1 && mkdir /data && chown 65534:65534 /data
COPY *.py ./monitoring/
RUN chmod 0555 monitoring && chmod 0444 monitoring/*.py
USER 65534:65534
ENTRYPOINT ["python", "-m", "monitoring.server"]
