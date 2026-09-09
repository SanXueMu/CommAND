# CommAND 生产镜像（amd64，目标 CentOS 7 + Docker）
FROM python:3.13-slim

WORKDIR /app

# 国内镜像源装依赖（内网出公网直连 pypi 慢，统一走清华源）
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    COMMAND_HOST=0.0.0.0

# 先装依赖（利用层缓存：代码改动不重装）
COPY pyproject.toml ./
RUN pip install "fastapi>=0.115" "uvicorn[standard]>=0.32" "psycopg[binary,pool]>=3.2" "pydantic>=2.9"

# 再拷代码（store/migrations 随代码进镜像，启动时自动执行）
COPY . .

EXPOSE 8800

CMD ["python", "main.py", "serve"]
