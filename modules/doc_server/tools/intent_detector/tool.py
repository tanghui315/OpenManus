"""
意图检测工具
用于分析用户查询并检测用户的意图类型，帮助文档生成系统理解用户需求
"""

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.llm import LLM
from app.logger import setup_logger
from app.schema import Message
from modules.doc_server.config import IntentType
from modules.doc_server.tools.base import DocServerTool

logger = setup_logger("doc_server.tools.intent_detector")


class IntentDetectionResult(BaseModel):
    """意图检测结果"""

    intent: str = Field(..., description="检测到的主要意图类型")
    confidence: float = Field(..., description="意图检测的置信度(0-1)")
    sub_intents: Optional[List[Dict[str, Any]]] = Field(
        None, description="检测到的次要意图列表，每个包含意图类型和置信度"
    )
    query: str = Field(..., description="原始查询文本")
    entities: Optional[List[Dict[str, Any]]] = Field(
        None, description="从查询中提取的实体信息"
    )
    explanation: Optional[str] = Field(None, description="意图检测的解释说明")
    error: Optional[str] = Field(None, description="错误信息(如有)")


class IntentDetectorTool(DocServerTool):
    """意图检测工具，用于分析用户查询并检测用户的意图类型"""

    def initialize(self, **kwargs) -> None:
        """
        初始化工具

        Args:
            kwargs: 初始化参数
        """
        super().initialize(**kwargs)

        # 加载意图类型配置
        self.intent_types = {
            intent_type.value: intent_type for intent_type in IntentType
        }

        # 设置意图匹配的关键词和规则
        self.intent_keywords = {
            IntentType.CREATE.value: [
                "创建",
                "新建",
                "生成",
                "撰写",
                "写一篇",
                "制作",
                "开始",
                "建立",
            ],
            IntentType.QUERY.value: [
                "查询",
                "搜索",
                "查找",
                "查看",
                "检索",
                "获取",
                "了解",
                "告诉我关于",
                "什么是",
            ],
            IntentType.EXPLAIN.value: [
                "解释",
                "说明",
                "阐述",
                "描述",
                "详细介绍",
                "具体讲解",
                "为什么",
                "如何理解",
            ],
            IntentType.SUMMARIZE.value: [
                "总结",
                "概括",
                "摘要",
                "归纳",
                "简述",
                "简介",
                "简要说明",
            ],
            IntentType.COMPARE.value: [
                "比较",
                "对比",
                "区别",
                "差异",
                "不同点",
                "相似点",
                "优缺点",
            ],
            IntentType.LIST.value: [
                "列出",
                "列举",
                "枚举",
                "罗列",
                "展示所有",
                "给出清单",
            ],
            IntentType.UNKNOWN.value: [],  # 默认兜底意图
        }

        # 设置实体类型和提取规则
        self.entity_patterns = {
            "topic": [],  # 主题实体规则
            "document_type": ["文档", "报告", "指南", "手册", "教程", "说明书"],
            "time_period": ["今天", "昨天", "本周", "上周", "本月", "去年"],
        }

        # 初始化LLM客户端
        self.llm = kwargs.get("llm", LLM())

        # 关键词匹配置信度阈值，低于此阈值时使用大模型进行意图检测
        self.keyword_confidence_threshold = kwargs.get(
            "keyword_confidence_threshold", 0.5
        )

        logger.info("意图检测工具初始化完成")

    async def execute(
        self, query: str, detailed_analysis: bool = False, **kwargs
    ) -> IntentDetectionResult:
        """
        执行意图检测

        Args:
            query: 用户查询文本
            detailed_analysis: 是否需要返回详细分析结果
            kwargs: 其他参数

        Returns:
            意图检测结果
        """
        if not query.strip():
            return IntentDetectionResult(
                intent=IntentType.UNKNOWN.value,
                confidence=0.0,
                query=query,
                error="查询文本不能为空",
            )

        try:
            # 先使用关键词匹配进行意图检测
            intent_scores = {}
            for intent_type, keywords in self.intent_keywords.items():
                score = self._calculate_intent_score(query, keywords)
                intent_scores[intent_type] = score

            # 获取主要意图（得分最高的）
            main_intent = max(intent_scores.items(), key=lambda x: x[1])
            intent_type, confidence = main_intent

            # 如果最高得分低于阈值，则使用大模型进行意图检测
            if confidence < self.keyword_confidence_threshold:
                logger.info(
                    f"关键词匹配置信度较低({confidence:.2f})，尝试使用大模型进行意图检测"
                )
                llm_intent_result = await self._detect_intent_with_llm(query)
                if llm_intent_result:
                    intent_type, confidence = llm_intent_result
                    logger.info(
                        f"大模型检测到的意图: {intent_type}, 置信度: {confidence:.2f}"
                    )
                else:
                    # 如果大模型检测失败，则使用最高得分的关键词匹配结果，但至少给一个基础置信度
                    intent_type = max(intent_scores.items(), key=lambda x: x[1])[0]
                    if confidence < 0.3:
                        intent_type = IntentType.UNKNOWN.value
                        confidence = max(confidence, 0.3)  # 至少给一个基础置信度

            # 提取次要意图
            sub_intents = []
            if detailed_analysis:
                for intent, score in sorted(
                    intent_scores.items(), key=lambda x: x[1], reverse=True
                ):
                    if (
                        intent != intent_type and score > 0.2
                    ):  # 只保留置信度0.2以上的次要意图
                        sub_intents.append(
                            {"intent": intent, "confidence": round(score, 2)}
                        )

            # 提取实体
            entities = self._extract_entities(query) if detailed_analysis else None

            # 生成解释说明（仅当需要详细分析时）
            explanation = None
            if detailed_analysis:
                explanation = self._generate_explanation(
                    query, intent_type, confidence, entities
                )

            # 构建结果
            result = IntentDetectionResult(
                intent=intent_type,
                confidence=round(confidence, 2),
                sub_intents=sub_intents if sub_intents else None,
                query=query,
                entities=entities,
                explanation=explanation,
            )

            logger.info(f"意图检测结果: 类型={intent_type}, 置信度={confidence:.2f}")
            return result

        except Exception as e:
            error_msg = f"执行意图检测时发生错误: {str(e)}"
            logger.error(error_msg)
            return IntentDetectionResult(
                intent=IntentType.UNKNOWN.value,
                confidence=0.0,
                query=query,
                error=error_msg,
            )

    async def _detect_intent_with_llm(self, query: str) -> Optional[tuple]:
        """
        使用大模型检测用户意图

        Args:
            query: 用户查询文本

        Returns:
            元组(意图类型, 置信度)，如果检测失败则返回None
        """
        try:
            # 构建系统提示
            system_prompt = [
                Message(
                    role="system",
                    content=(
                        "你是一个专门用于意图检测的AI助手。请分析用户查询并确定其最可能的意图类型。"
                        f"可用的意图类型有：\n"
                        + "\n".join(
                            [
                                f"- {intent}: {self._get_intent_description(intent)}"
                                for intent in self.intent_types.keys()
                            ]
                        )
                    ),
                )
            ]

            # 构建用户提示
            user_prompt = [
                Message(
                    role="user",
                    content=(
                        f'请分析以下用户查询，并确定最可能的意图类型：\n\n"{query}"\n\n'
                        "请以JSON格式返回结果，包含以下字段：\n"
                        "1. intent: 意图类型（必须是给定的意图类型之一）\n"
                        "2. confidence: 置信度（0-1之间的小数）\n"
                        "3. reasoning: 推理过程\n\n"
                        "只返回JSON对象，不要有任何其他文本。"
                    ),
                )
            ]

            # 调用大模型
            response = await self.llm.ask(
                messages=user_prompt,
                system_msgs=system_prompt,
                stream=False,
                temperature=0.2,  # 使用较低的温度以获得更确定的结果
            )

            # 解析响应
            try:
                result = json.loads(response)
                intent = result.get("intent", "")
                confidence = float(result.get("confidence", 0.0))

                # 确保意图在有效范围内
                if intent not in self.intent_types:
                    logger.warning(
                        f"大模型返回了无效的意图类型: {intent}，使用UNKNOWN作为替代"
                    )
                    intent = IntentType.UNKNOWN.value
                    confidence = min(confidence, 0.5)  # 降低置信度

                return intent, confidence

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"解析大模型响应失败: {str(e)}, 响应内容: {response}")
                return None

        except Exception as e:
            logger.error(f"使用大模型检测意图时发生错误: {str(e)}")
            return None

    def _get_intent_description(self, intent_type: str) -> str:
        """
        获取意图类型的描述

        Args:
            intent_type: 意图类型

        Returns:
            意图类型的描述
        """
        descriptions = {
            IntentType.CREATE.value: "创建或生成新内容",
            IntentType.QUERY.value: "查询或搜索信息",
            IntentType.EXPLAIN.value: "解释或详细说明概念",
            IntentType.SUMMARIZE.value: "总结或概括内容",
            IntentType.COMPARE.value: "比较或对比多个事物",
            IntentType.LIST.value: "列举或枚举项目",
            IntentType.UNKNOWN.value: "未能明确识别意图",
        }
        return descriptions.get(intent_type, "未知意图类型")

    def _calculate_intent_score(self, query: str, keywords: List[str]) -> float:
        """
        计算查询文本与意图关键词的匹配得分

        Args:
            query: 查询文本
            keywords: 意图关键词列表

        Returns:
            匹配得分(0-1)
        """
        if not keywords:
            return 0.1  # 给默认兜底意图一个很低的基础分

        # 简单的关键词匹配算法
        matched_keywords = 0
        for keyword in keywords:
            if keyword in query:
                matched_keywords += 1

                # 如果关键词在句子开头，增加权重
                if query.startswith(keyword):
                    matched_keywords += 0.5

        # 计算得分
        base_score = matched_keywords / (len(keywords) * 0.5)  # 基础得分

        # 限制在0-1范围内
        return min(max(base_score, 0.0), 1.0)

    def _extract_entities(self, query: str) -> List[Dict[str, Any]]:
        """
        从查询文本中提取实体

        Args:
            query: 查询文本

        Returns:
            提取的实体列表
        """
        entities = []

        # 检测文档类型实体
        for doc_type in self.entity_patterns["document_type"]:
            if doc_type in query:
                entities.append(
                    {
                        "type": "document_type",
                        "value": doc_type,
                        "position": query.find(doc_type),
                    }
                )

        # 检测时间周期实体
        for time_period in self.entity_patterns["time_period"]:
            if time_period in query:
                entities.append(
                    {
                        "type": "time_period",
                        "value": time_period,
                        "position": query.find(time_period),
                    }
                )

        # 简单的主题实体提取（根据停用词和意图关键词排除后的主要名词短语）
        # 在实际项目中，这里应该使用更复杂的NLP技术

        return entities

    def _generate_explanation(
        self,
        query: str,
        intent_type: str,
        confidence: float,
        entities: Optional[List[Dict[str, Any]]],
    ) -> str:
        """
        生成意图检测的解释说明

        Args:
            query: 查询文本
            intent_type: 检测到的意图类型
            confidence: 置信度
            entities: 提取的实体列表

        Returns:
            解释说明文本
        """
        intent_desc = self._get_intent_description(intent_type)

        explanation = f"查询「{query}」被识别为「{intent_desc}」意图"
        explanation += f"，置信度为{confidence:.0%}。"

        if entities and len(entities) > 0:
            explanation += "检测到以下实体："
            for entity in entities:
                explanation += f"「{entity['value']}」({entity['type']})、"
            explanation = explanation.rstrip("、") + "。"

        return explanation
