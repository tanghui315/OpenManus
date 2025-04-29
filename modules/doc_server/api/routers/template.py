from typing import List, Optional

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ...database.template import TemplateStorage
from ..models.template import (
    TemplateDeleteResponse,
    TemplateListResponse,
    TemplateRequest,
    TemplateResponse,
)

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
)


# 依赖项：获取模板存储实例
async def get_template_storage():
    template_storage = TemplateStorage()
    return template_storage


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_request: TemplateRequest,
    template_storage: TemplateStorage = Depends(get_template_storage),
):
    """
    创建新模板

    参数:
        template_request: 模板创建请求数据

    返回:
        创建的模板信息
    """
    try:
        # 创建模板
        template = {
            "name": template_request.name,
            "description": template_request.description,
            "document_type": template_request.document_type,
            "content": template_request.content,
            "variables": template_request.variables,
            "tags": template_request.tags,
            "metadata": template_request.metadata,
        }

        template_id = await template_storage.save(template)
        if not template_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建模板失败"
            )

        # 查询新创建的模板
        created_template = await template_storage.get(template_id)
        if not created_template:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建模板成功但无法检索",
            )

        return TemplateResponse(**created_template)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建模板时发生错误: {str(e)}",
        )


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页记录数"),
    document_type: Optional[str] = Query(None, description="按文档类型过滤"),
    template_storage: TemplateStorage = Depends(get_template_storage),
):
    """
    获取模板列表

    参数:
        page: 页码，默认为1
        page_size: 每页记录数，默认为10
        document_type: 文档类型过滤

    返回:
        模板列表及分页信息
    """
    try:
        skip = (page - 1) * page_size

        templates, total = await template_storage.list(
            skip=skip, limit=page_size, document_type=document_type
        )

        # 转换为响应模型
        items = [TemplateResponse(**template) for template in templates]

        return TemplateListResponse(
            items=items, total=total, page=page, page_size=page_size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模板列表时发生错误: {str(e)}",
        )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str = Path(..., description="模板ID"),
    template_storage: TemplateStorage = Depends(get_template_storage),
):
    """
    获取指定模板详情

    参数:
        template_id: 模板ID

    返回:
        模板详情
    """
    try:
        template = await template_storage.get(template_id)

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到ID为'{template_id}'的模板",
            )

        return TemplateResponse(**template)

    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="无效的模板ID格式"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模板时发生错误: {str(e)}",
        )


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_request: TemplateRequest,
    template_id: str = Path(..., description="模板ID"),
    template_storage: TemplateStorage = Depends(get_template_storage),
):
    """
    更新指定模板

    参数:
        template_id: 模板ID
        template_request: 模板更新请求数据

    返回:
        更新后的模板信息
    """
    try:
        # 检查模板是否存在
        existing_template = await template_storage.get(template_id)
        if not existing_template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到ID为'{template_id}'的模板",
            )

        # 更新模板
        template = {
            "name": template_request.name,
            "description": template_request.description,
            "document_type": template_request.document_type,
            "content": template_request.content,
            "variables": template_request.variables,
            "tags": template_request.tags,
            "metadata": template_request.metadata,
        }

        success = await template_storage.update(template_id, template)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新模板失败"
            )

        # 获取更新后的模板
        updated_template = await template_storage.get(template_id)
        if not updated_template:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新模板成功但无法检索",
            )

        return TemplateResponse(**updated_template)

    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="无效的模板ID格式"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新模板时发生错误: {str(e)}",
        )


@router.delete("/{template_id}", response_model=TemplateDeleteResponse)
async def delete_template(
    template_id: str = Path(..., description="模板ID"),
    template_storage: TemplateStorage = Depends(get_template_storage),
):
    """
    删除指定模板

    参数:
        template_id: 模板ID

    返回:
        删除结果
    """
    try:
        # 检查模板是否存在
        existing_template = await template_storage.get(template_id)
        if not existing_template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到ID为'{template_id}'的模板",
            )

        # 删除模板
        success = await template_storage.delete(template_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除模板失败"
            )

        return TemplateDeleteResponse(success=True, id=template_id)

    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="无效的模板ID格式"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除模板时发生错误: {str(e)}",
        )
