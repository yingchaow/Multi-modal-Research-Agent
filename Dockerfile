# 1. 使用官方 Python 3.11 瘦身版镜像作为基础环境
FROM python:3.11-slim

# 2. 设置容器内的工作目录
WORKDIR /app

# 3. 设置环境变量，优化 Python 在容器内的运行表现
ENV PYTHONDONTWRITEBYTECODE=1 
ENV PYTHONUNBUFFERED=1

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list 2>/dev/null || true && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list 2>/dev/null || true

# 4. 安装系统基础编译依赖 (为了防止某些 LangChain C++ 底层库安装报错)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
# 5. 复制依赖清单并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 复制当前目录下的所有代码和静态资源到容器中
COPY . .

# 7. 暴露 FastAPI 默认监听的 8000 端口
EXPOSE 8000

# 8. 定义启动命令
# 容器内不要启用 --reload；reload 会递归扫描宿主机挂载进来的 .venv，
# 容易因为 Python 版本/缓存目录变化触发 FileNotFoundError。
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
