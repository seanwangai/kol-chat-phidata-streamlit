# 使用 Python 3.13 的轻量级镜像
FROM python:3.13-slim-bookworm

# 设置容器内的工作目录
WORKDIR /app

# 复制并安装依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有应用代码到容器
# 注意：此操作会包含 .streamlit/secrets.toml 文件
COPY . .

# 暴露 Streamlit 的默认端口
EXPOSE 8501

# 定义容器启动命令，允许从任何地址访问
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"] 