import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 复用OpenManus的配置和日志系统
from app.config import Config
from app.logger import setup_logger

# 导入API路由
from modules.doc_server.api.routers import documents, rag, stream, template

# 创建FastAPI应用
app = FastAPI(
    title="OpenManus Document Writer",
    description="智能文档编写服务，支持基于RAG的文档自动生成",
    version="0.1.0",
)

# 添加CORS支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 可以设置为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置日志
logger = setup_logger("doc_server")

# 注册路由
app.include_router(documents.router)
app.include_router(template.router)
app.include_router(rag.router)
app.include_router(stream.router)


@app.get("/")
async def root():
    return {"message": "Welcome to OpenManus Document Writer Service"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    # 读取配置
    config = Config()
    host = config.get("doc_server.host", "127.0.0.1")
    port = config.get("doc_server.port", 8000)

    uvicorn.run("app:app", host=host, port=port, reload=True)
