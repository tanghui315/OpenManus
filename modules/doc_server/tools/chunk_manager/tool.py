"""
文档Chunk管理工具
负责文档块的管理、处理和转换
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Union

from app.logger import setup_logger
from modules.doc_server.database.document import DocumentStorage
from modules.doc_server.tools.base import DocServerTool
from modules.doc_server.tools.chunk_manager.model import (
    ChunkManagerResult,
    ChunkOperation,
    DocumentChunk,
)

logger = setup_logger("doc_server.tools.chunk_manager")


class ChunkManagerTool(DocServerTool):
    """文档Chunk管理工具，提供文档块的增删改查、合并拆分等功能"""

    def initialize(self, **kwargs) -> None:
        """
        初始化工具

        Args:
            kwargs: 初始化参数
        """
        super().initialize(**kwargs)

        # 初始化文档存储
        self.storage = DocumentStorage()

        logger.info("文档Chunk管理工具初始化完成")

    async def execute(
        self,
        operation: str,
        document_id: str,
        section_id: Optional[str] = None,
        section_title: Optional[str] = None,
        section_type: str = "text",
        content: Optional[str] = None,
        position: Optional[int] = None,
        target_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> ChunkManagerResult:
        """
        执行文档块操作

        Args:
            operation: 操作类型，支持add/update/delete/merge/split/reorder
            document_id: 文档ID
            section_id: 节点ID
            section_title: 节点标题
            section_type: 节点类型
            content: 节点内容
            position: 插入位置索引
            target_ids: 目标节点ID列表
            **kwargs: 其他参数

        Returns:
            文档块操作结果
        """
        # 检查文档是否存在
        document = await self.storage.get_document(document_id)
        if not document:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=operation,
                error=f"文档 {document_id} 不存在",
            )

        try:
            # 根据操作类型执行不同处理
            if operation == ChunkOperation.ADD:
                return await self._add_chunk(
                    document_id, section_title, section_type, content, position
                )
            elif operation == ChunkOperation.UPDATE:
                if not section_id:
                    return ChunkManagerResult(
                        success=False,
                        document_id=document_id,
                        operation=operation,
                        error="更新操作需要提供section_id",
                    )
                return await self._update_chunk(
                    document_id, section_id, section_title, section_type, content
                )
            elif operation == ChunkOperation.DELETE:
                if not section_id:
                    return ChunkManagerResult(
                        success=False,
                        document_id=document_id,
                        operation=operation,
                        error="删除操作需要提供section_id",
                    )
                return await self._delete_chunk(document_id, section_id)
            elif operation == ChunkOperation.MERGE:
                if not target_ids or len(target_ids) < 2:
                    return ChunkManagerResult(
                        success=False,
                        document_id=document_id,
                        operation=operation,
                        error="合并操作需要提供至少两个target_ids",
                    )
                return await self._merge_chunks(document_id, target_ids, section_title)
            elif operation == ChunkOperation.SPLIT:
                if not section_id or not content:
                    return ChunkManagerResult(
                        success=False,
                        document_id=document_id,
                        operation=operation,
                        error="拆分操作需要提供section_id和content",
                    )
                return await self._split_chunk(document_id, section_id, content)
            elif operation == ChunkOperation.REORDER:
                if not target_ids:
                    return ChunkManagerResult(
                        success=False,
                        document_id=document_id,
                        operation=operation,
                        error="重排序操作需要提供target_ids",
                    )
                return await self._reorder_chunks(document_id, target_ids)
            else:
                return ChunkManagerResult(
                    success=False,
                    document_id=document_id,
                    operation=operation,
                    error=f"不支持的操作类型: {operation}",
                )

        except Exception as e:
            error_msg = f"执行文档块操作时发生错误: {str(e)}"
            logger.error(error_msg)
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=operation,
                error=error_msg,
            )

    async def _add_chunk(
        self,
        document_id: str,
        section_title: Optional[str],
        section_type: str,
        content: Optional[str],
        position: Optional[int],
    ) -> ChunkManagerResult:
        """
        添加文档块

        Args:
            document_id: 文档ID
            section_title: 节点标题
            section_type: 节点类型
            content: 节点内容
            position: 插入位置索引

        Returns:
            操作结果
        """
        # 生成块ID
        section_id = str(uuid.uuid4())

        # 创建块数据
        chunk_data = {
            "id": section_id,
            "document_id": document_id,
            "section_id": section_id,
            "section_title": section_title or "未命名节点",
            "section_type": section_type,
            "content": content or "",
            "position": position if position is not None else 999999,  # 默认添加到末尾
        }

        # 保存块
        chunk_id = await self.storage.save_chunk(chunk_data)

        if not chunk_id:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.ADD,
                error="添加文档块失败",
            )

        # 获取所有块并重排序
        all_chunks = await self._adjust_positions(document_id)

        # 找到新添加的块
        added_chunk = None
        for chunk in all_chunks:
            if chunk.get("section_id") == section_id:
                added_chunk = DocumentChunk(**chunk)
                break

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.ADD,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=[added_chunk] if added_chunk else [],
        )

    async def _update_chunk(
        self,
        document_id: str,
        section_id: str,
        section_title: Optional[str],
        section_type: Optional[str],
        content: Optional[str],
    ) -> ChunkManagerResult:
        """
        更新文档块

        Args:
            document_id: 文档ID
            section_id: 节点ID
            section_title: 节点标题
            section_type: 节点类型
            content: 节点内容

        Returns:
            操作结果
        """
        # 查找块
        chunk = await self.storage.get_chunk(section_id)
        if not chunk:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.UPDATE,
                error=f"文档块 {section_id} 不存在",
            )

        # 检查块是否属于指定的文档
        if chunk.get("document_id") != document_id:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.UPDATE,
                error=f"文档块 {section_id} 不属于文档 {document_id}",
            )

        # 更新字段
        update_data = {}
        if section_title is not None:
            update_data["section_title"] = section_title
        if section_type is not None:
            update_data["section_type"] = section_type
        if content is not None:
            update_data["content"] = content

        # 如果没有更新字段，返回成功
        if not update_data:
            all_chunks = await self.storage.get_document_chunks(document_id)
            return ChunkManagerResult(
                success=True,
                document_id=document_id,
                operation=ChunkOperation.UPDATE,
                chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
                affected_chunks=[],
            )

        # 更新块
        success = await self.storage.update_chunk(section_id, update_data)
        if not success:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.UPDATE,
                error=f"更新文档块 {section_id} 失败",
            )

        # 获取更新后的块
        updated_chunk = await self.storage.get_chunk(section_id)
        all_chunks = await self.storage.get_document_chunks(document_id)

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.UPDATE,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=[DocumentChunk(**updated_chunk)] if updated_chunk else [],
        )

    async def _delete_chunk(
        self, document_id: str, section_id: str
    ) -> ChunkManagerResult:
        """
        删除文档块

        Args:
            document_id: 文档ID
            section_id: 节点ID

        Returns:
            操作结果
        """
        # 查找块
        chunk = await self.storage.get_chunk(section_id)
        if not chunk:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.DELETE,
                error=f"文档块 {section_id} 不存在",
            )

        # 检查块是否属于指定的文档
        if chunk.get("document_id") != document_id:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.DELETE,
                error=f"文档块 {section_id} 不属于文档 {document_id}",
            )

        # 删除块
        deleted_chunk = DocumentChunk(**chunk)
        success = await self.storage.delete_chunk(section_id)
        if not success:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.DELETE,
                error=f"删除文档块 {section_id} 失败",
            )

        # 重新排序块
        all_chunks = await self._adjust_positions(document_id)

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.DELETE,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=[deleted_chunk],
        )

    async def _merge_chunks(
        self, document_id: str, target_ids: List[str], section_title: Optional[str]
    ) -> ChunkManagerResult:
        """
        合并多个文档块

        Args:
            document_id: 文档ID
            target_ids: 要合并的节点ID列表
            section_title: 合并后的节点标题

        Returns:
            操作结果
        """
        # 检查所有块是否存在
        chunks_to_merge = []
        for chunk_id in target_ids:
            chunk = await self.storage.get_chunk(chunk_id)
            if not chunk:
                return ChunkManagerResult(
                    success=False,
                    document_id=document_id,
                    operation=ChunkOperation.MERGE,
                    error=f"文档块 {chunk_id} 不存在",
                )

            # 检查块是否属于指定的文档
            if chunk.get("document_id") != document_id:
                return ChunkManagerResult(
                    success=False,
                    document_id=document_id,
                    operation=ChunkOperation.MERGE,
                    error=f"文档块 {chunk_id} 不属于文档 {document_id}",
                )

            chunks_to_merge.append(chunk)

        # 按position排序
        chunks_to_merge.sort(key=lambda x: x.get("position", 0))

        # 合并内容
        merged_content = "\n\n".join(
            [chunk.get("content", "") for chunk in chunks_to_merge]
        )

        # 确定合并块的position（使用第一个块的位置）
        position = chunks_to_merge[0].get("position", 0) if chunks_to_merge else 0

        # 创建新块
        merged_chunk = {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "section_id": str(uuid.uuid4()),
            "section_title": section_title
            or chunks_to_merge[0].get("section_title", "合并节点"),
            "section_type": chunks_to_merge[0].get("section_type", "text"),
            "content": merged_content,
            "position": position,
        }

        # 保存合并后的块
        merged_chunk_id = await self.storage.save_chunk(merged_chunk)
        if not merged_chunk_id:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.MERGE,
                error="保存合并块失败",
            )

        # 删除原始块
        for chunk in chunks_to_merge:
            await self.storage.delete_chunk(chunk.get("id"))

        # 重新排序块
        all_chunks = await self._adjust_positions(document_id)

        # 获取合并后的块
        merged_result = await self.storage.get_chunk(merged_chunk_id)

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.MERGE,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=([DocumentChunk(**merged_result)] if merged_result else []),
        )

    async def _split_chunk(
        self, document_id: str, section_id: str, content: str
    ) -> ChunkManagerResult:
        """
        拆分文档块

        Args:
            document_id: 文档ID
            section_id: 要拆分的节点ID
            content: 拆分点标记，格式如 "---SPLIT---"

        Returns:
            操作结果
        """
        # 查找块
        chunk = await self.storage.get_chunk(section_id)
        if not chunk:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.SPLIT,
                error=f"文档块 {section_id} 不存在",
            )

        # 检查块是否属于指定的文档
        if chunk.get("document_id") != document_id:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.SPLIT,
                error=f"文档块 {section_id} 不属于文档 {document_id}",
            )

        # 使用拆分标记分割内容
        original_content = chunk.get("content", "")
        if content not in original_content:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.SPLIT,
                error=f"拆分标记 '{content}' 未在文档块内容中找到",
            )

        split_contents = original_content.split(content)
        if len(split_contents) < 2:
            return ChunkManagerResult(
                success=False,
                document_id=document_id,
                operation=ChunkOperation.SPLIT,
                error="拆分后没有足够的内容",
            )

        # 更新原始块
        update_data = {"content": split_contents[0].strip()}
        await self.storage.update_chunk(section_id, update_data)

        # 创建新块
        position = chunk.get("position", 0)
        new_chunks = []

        for i, split_content in enumerate(split_contents[1:], 1):
            new_chunk = {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "section_id": str(uuid.uuid4()),
                "section_title": f"{chunk.get('section_title', '未命名节点')} (分段 {i})",
                "section_type": chunk.get("section_type", "text"),
                "content": split_content.strip(),
                "position": position + i,
            }

            chunk_id = await self.storage.save_chunk(new_chunk)
            if chunk_id:
                saved_chunk = await self.storage.get_chunk(chunk_id)
                if saved_chunk:
                    new_chunks.append(saved_chunk)

        # 重新排序块
        all_chunks = await self._adjust_positions(document_id)

        # 获取更新后的原始块
        updated_original = await self.storage.get_chunk(section_id)

        affected_chunks = []
        if updated_original:
            affected_chunks.append(DocumentChunk(**updated_original))

        for new_chunk in new_chunks:
            affected_chunks.append(DocumentChunk(**new_chunk))

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.SPLIT,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=affected_chunks,
        )

    async def _reorder_chunks(
        self, document_id: str, target_ids: List[str]
    ) -> ChunkManagerResult:
        """
        重新排序文档块

        Args:
            document_id: 文档ID
            target_ids: 按新顺序排列的节点ID列表

        Returns:
            操作结果
        """
        # 检查所有块是否存在并属于指定文档
        for i, chunk_id in enumerate(target_ids):
            chunk = await self.storage.get_chunk(chunk_id)
            if not chunk:
                return ChunkManagerResult(
                    success=False,
                    document_id=document_id,
                    operation=ChunkOperation.REORDER,
                    error=f"文档块 {chunk_id} 不存在",
                )

            # 检查块是否属于指定的文档
            if chunk.get("document_id") != document_id:
                return ChunkManagerResult(
                    success=False,
                    document_id=document_id,
                    operation=ChunkOperation.REORDER,
                    error=f"文档块 {chunk_id} 不属于文档 {document_id}",
                )

            # 更新位置
            await self.storage.update_chunk(chunk_id, {"position": i})

        # 重新排序所有块
        all_chunks = await self._adjust_positions(document_id)

        return ChunkManagerResult(
            success=True,
            document_id=document_id,
            operation=ChunkOperation.REORDER,
            chunks=[DocumentChunk(**chunk) for chunk in all_chunks],
            affected_chunks=[],
        )

    async def _adjust_positions(self, document_id: str) -> List[Dict[str, Any]]:
        """
        调整文档块的位置，确保连续且无重复

        Args:
            document_id: 文档ID

        Returns:
            调整后的所有文档块列表
        """
        # 获取所有块
        all_chunks = await self.storage.get_document_chunks(document_id)

        # 按position排序
        all_chunks.sort(key=lambda x: x.get("position", 0))

        # 重新分配position
        for i, chunk in enumerate(all_chunks):
            if chunk.get("position") != i:
                await self.storage.update_chunk(chunk.get("id"), {"position": i})
                chunk["position"] = i

        return all_chunks
