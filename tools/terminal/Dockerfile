# 构建镜像时安装固定依赖；运行 Agent 任务时由服务端强制关闭网络。
FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates fontconfig fonts-noto-cjk python3 python3-venv \
    && python3 -m venv /opt/agent/venv \
    && /opt/agent/venv/bin/pip install --no-cache-dir \
        numpy==2.3.4 pandas==2.3.3 matplotlib==3.10.7 Pillow==12.0.0 \
        python-docx==1.2.0 openpyxl==3.1.5 pypdf==6.1.3 reportlab==4.4.4 \
    && npm install --prefix /opt/agent \
        three@0.181.1 vite@7.2.2 typescript@5.9.3 esbuild@0.25.12 \
    && chmod -R a-w /opt/agent/venv /opt/agent/node_modules \
    && rm -rf /root/.cache /root/.npm /var/lib/apt/lists/*

COPY container_entrypoint.py /opt/agent/container_entrypoint.py
RUN chmod 0555 /opt/agent/container_entrypoint.py
WORKDIR /workspace
ENTRYPOINT ["python3", "-I", "/opt/agent/container_entrypoint.py"]
