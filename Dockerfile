# CommAND 生产镜像（amd64，目标 CentOS 7 + Docker）
FROM python:3.13-slim


WORKDIR /app

# 系统依赖：扫描版 PDF 的 OCR（Tesseract + OCRmyPDF 所需的 ghostscript/qpdf/unpaper）
# 说明：均装在镜像内，宿主机零改动；Debian 源换清华镜像加速
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim \
        ghostscript qpdf unpaper pngquant \
    && rm -rf /var/lib/apt/lists/*

# 国内镜像源（pip 装 uv + uv sync 装依赖均走清华源）
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_DEFAULT_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    COMMAND_HOST=0.0.0.0

# 依赖层：按锁文件精确安装（新增依赖自动覆盖，无需改本文件）
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# 代码层（store/migrations 随代码进镜像，启动时自动执行）
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8800

CMD ["python", "main.py", "serve"]
