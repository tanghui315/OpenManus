from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from typing import List, Dict, Any, Optional
import uuid
import os
import json
from datetime import datetime

# 导入API模型
from modules.doc_server.api.models.template import (
    TemplateRequest,
    TemplateResponse,
    TemplateListResponse
)

# 复用OpenManus的配置和日志系统
from app.config import Config
from app.logger import setup_logger

# 导入文档模板服务
from modules.doc_server.services.template.manager import TemplateManager

# 设置路由
router = APIRouter(prefix="/templates", tags=["templates"])
logger = setup_logger("doc_server.templates")
config = Config()

# 初始化模板管理器
template_manager = TemplateManager(config.get("doc_server.templates", {}))

@router.post("/", response_model=TemplateResponse)
async def create_template(template: TemplateRequest):
    """
    创建新的文档模板
    """
    try:
        # 生成唯一ID
        template_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # 创建模板
        result = await template_manager.create_template(
            template_id=template_id,
            name=template.name,
            description=template.description,
            content=template.content,
            document_type=template.document_type,
            metadata=template.metadata
        )

        # 返回结果
        return TemplateResponse(
            template_id=template_id,
            name=template.name,
            description=template.description,
            document_type=template.document_type,
            created_at=timestamp,
            updated_at=timestamp,
            metadata=template.metadata
        )

    except Exception as e:
        logger.error(f"创建模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建模板失败: {str(e)}")

@router.get("/", response_model=TemplateListResponse)
async def list_templates(
    document_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
):
    """
    获取模板列表
    """
    try:
        # 获取模板列表
        templates, total = await template_manager.list_templates(
            document_type=document_type,
            page=page,
            page_size=page_size
        )

        # 转换为响应模型
        template_list = [
            TemplateResponse(
                template_id=t.get("template_id"),
                name=t.get("name"),
                description=t.get("description"),
                document_type=t.get("document_type"),
                created_at=t.get("created_at"),
                updated_at=t.get("updated_at"),
                metadata=t.get("metadata", {})
            ) for t in templates
        ]

        # 返回结果
        return TemplateListResponse(
            templates=template_list,
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"获取模板列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取模板列表失败: {str(e)}")

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    """
    获取模板详情
    """
    try:
        # 获取模板详情
        template = await template_manager.get_template(template_id)

        if not template:
            raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")

        # 返回结果
        return TemplateResponse(
            template_id=template.get("template_id"),
            name=template.get("name"),
            description=template.get("description"),
            document_type=template.get("document_type"),
            created_at=template.get("created_at"),
            updated_at=template.get("updated_at"),
            metadata=template.get("metadata", {})
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模板详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取模板详情失败: {str(e)}")

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: str, template: TemplateRequest):
    """
    更新模板
    """
    try:
        # 检查模板是否存在
        existing_template = await template_manager.get_template(template_id)

        if not existing_template:
            raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")

        # 更新时间戳
        timestamp = datetime.now().isoformat()

        # 更新模板
        await template_manager.update_template(
            template_id=template_id,
            name=template.name,
            description=template.description,
            content=template.content,
            document_type=template.document_type,
            metadata=template.metadata
        )

        # 返回更新后的结果
        return TemplateResponse(
            template_id=template_id,
            name=template.name,
            description=template.description,
            document_type=template.document_type,
            created_at=existing_template.get("created_at"),
            updated_at=timestamp,
            metadata=template.metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新模板失败: {str(e)}")

@router.delete("/{template_id}")
async def delete_template(template_id: str):
    """
    删除模板
    """
    try:
        # 检查模板是否存在
        existing_template = await template_manager.get_template(template_id)

        if not existing_template:
            raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")

        # 删除模板
        await template_manager.delete_template(template_id)

        # 返回成功响应
        return {"message": f"模板 {template_id} 已成功删除"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除模板失败: {str(e)}")

@router.post("/upload")
async def upload_template_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
    document_type: str = Form("general")
):
    """
    上传模板文件
    """
    try:
        # 生成唯一ID
        template_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # 读取上传的文件内容
        content = await file.read()

        # 解析文件内容（假设为JSON格式）
        try:
            template_content = json.loads(content.decode("utf-8"))
        except:
            # 如果不是JSON，则作为纯文本存储
            template_content = content.decode("utf-8")

        # 创建模板
        await template_manager.create_template(
            template_id=template_id,
            name=name,
            description=description,
            content=template_content,
            document_type=document_type,
            metadata={"filename": file.filename}
        )

        # 返回结果
        return TemplateResponse(
            template_id=template_id,
            name=name,
            description=description,
            document_type=document_type,
            created_at=timestamp,
            updated_at=timestamp,
            metadata={"filename": file.filename}
        )

    except Exception as e:
        logger.error(f"上传模板文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传模板文件失败: {str(e)}")
