import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

# 导入配置
from app.config import Config

# 导入RAG客户端
from modules.doc_server.services.rag.client import RAGClient

# 设置路由
router = APIRouter(prefix="/rag", tags=["rag"])
logger = logging.getLogger("doc_server.api.rag")
config = Config()


# 创建RAG客户端依赖
async def get_rag_client():
    return RAGClient(config.get("doc_server.rag", {}))


@router.post("/index")
async def index_document(
    document_id: str = Form(..., description="文档ID"),
    content: str = Form(..., description="文档内容"),
    metadata: Optional[str] = Form(None, description="文档元数据（JSON字符串）"),
    rag_client: RAGClient = Depends(get_rag_client),
):
    """
    将文档内容索引到RAG服务
    """
    try:
        # 解析元数据
        meta_dict = {}
        if metadata:
            try:
                meta_dict = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="元数据JSON格式无效")

        # 调用RAG客户端索引文档
        result = await rag_client.index_document(
            document_id=document_id, content=content, metadata=meta_dict
        )

        # 检查结果
        if not result.get("success", False):
            return JSONResponse(
                status_code=500, content={"error": result.get("error", "索引文档失败")}
            )

        return result

    except Exception as e:
        logger.error(f"索引文档时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"索引文档失败: {str(e)}")


@router.post("/retrieve")
async def retrieve_content(
    query: str = Form(..., description="查询文本"),
    document_ids: Optional[str] = Form(None, description="文档ID列表（JSON数组）"),
    top_k: int = Form(5, description="返回结果数量"),
    filters: Optional[str] = Form(None, description="过滤条件（JSON对象）"),
    rag_client: RAGClient = Depends(get_rag_client),
):
    """
    从RAG服务检索与查询相关的内容
    """
    try:
        # 解析文档ID列表
        doc_ids = None
        if document_ids:
            try:
                doc_ids = json.loads(document_ids)
                if not isinstance(doc_ids, list):
                    raise HTTPException(
                        status_code=400, detail="document_ids必须是文档ID的JSON数组"
                    )
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="document_ids JSON格式无效")

        # 解析过滤条件
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
                if not isinstance(filter_dict, dict):
                    raise HTTPException(status_code=400, detail="filters必须是JSON对象")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="filters JSON格式无效")

        # 调用RAG客户端检索内容
        result = await rag_client.retrieve(
            query=query, document_ids=doc_ids, top_k=top_k, filters=filter_dict
        )

        # 检查结果
        if not result.get("success", False) and "error" in result:
            return JSONResponse(
                status_code=500, content={"error": result.get("error", "检索内容失败")}
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检索内容时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检索内容失败: {str(e)}")


@router.delete("/documents/{document_id}")
async def delete_document_index(
    document_id: str, rag_client: RAGClient = Depends(get_rag_client)
):
    """
    从RAG服务中删除指定文档的索引
    """
    try:
        # 调用RAG客户端删除文档索引
        result = await rag_client.delete_document(document_id)

        # 检查结果
        if not result.get("success", False):
            return JSONResponse(
                status_code=500,
                content={"error": result.get("error", "删除文档索引失败")},
            )

        return result

    except Exception as e:
        logger.error(f"删除文档索引时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文档索引失败: {str(e)}")


@router.get("/health")
async def check_rag_health(rag_client: RAGClient = Depends(get_rag_client)):
    """
    检查RAG服务健康状态
    """
    try:
        result = await rag_client.health_check()

        if result.get("status") != "ok":
            return JSONResponse(status_code=500, content=result)

        return result

    except Exception as e:
        logger.error(f"RAG服务健康检查时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")


@router.post("/index/file")
async def index_file(
    file: UploadFile = File(...),
    document_id: Optional[str] = Form(None, description="文档ID，不提供则自动生成"),
    metadata: Optional[str] = Form(None, description="文档元数据（JSON字符串）"),
    rag_client: RAGClient = Depends(get_rag_client),
):
    """
    上传文件并索引到RAG服务
    """
    try:
        # 读取文件内容
        content = await file.read()
        content_text = content.decode("utf-8")

        # 如果没有提供文档ID，生成一个
        if not document_id:
            document_id = str(uuid.uuid4())

        # 解析元数据
        meta_dict = {"filename": file.filename, "content_type": file.content_type}

        if metadata:
            try:
                user_meta = json.loads(metadata)
                meta_dict.update(user_meta)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="元数据JSON格式无效")

        # 调用RAG客户端索引文档
        result = await rag_client.index_document(
            document_id=document_id, content=content_text, metadata=meta_dict
        )

        # 检查结果
        if not result.get("success", False):
            return JSONResponse(
                status_code=500, content={"error": result.get("error", "索引文件失败")}
            )

        return {**result, "document_id": document_id, "filename": file.filename}

    except HTTPException:
        raise
    except UnicodeDecodeError:
        logger.error(f"文件编码错误，无法解析为文本")
        raise HTTPException(status_code=400, detail="文件编码错误，无法解析为文本")
    except Exception as e:
        logger.error(f"索引文件时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"索引文件失败: {str(e)}")
