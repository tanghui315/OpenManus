from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import List
import uuid
import os
import shutil
from datetime import datetime

router = APIRouter(prefix="/upload", tags=["upload"])

# 复用OpenManus的日志系统
from app.logger import setup_logger
logger = setup_logger("doc_server.upload")

# 简化版本，实际使用时需扩展
@router.post("/")
async def upload_files(
    files: List[UploadFile] = File(...),
    description: str = Form(None)
):
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    result = []
    for file in files:
        # 确保文件名唯一
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_extension = os.path.splitext(file.filename)[1]
        safe_filename = f"{timestamp}_{unique_id}{file_extension}"

        file_path = os.path.join(upload_dir, safe_filename)

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 添加到结果列表
        result.append({
            "filename": file.filename,
            "saved_as": safe_filename,
            "content_type": file.content_type,
            "path": file_path,
            "upload_time": timestamp,
            "description": description
        })

        logger.info(f"File uploaded: {file.filename} -> {file_path}")

    # 这里应该调用RAG索引服务API进行处理
    # 实际代码中需要实现这部分逻辑

    return {"message": f"Successfully uploaded {len(files)} files", "files": result}
