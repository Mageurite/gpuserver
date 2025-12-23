"""
LLM 引擎实现

提供基于 Ollama 的 LLM 文本生成功能。
支持按 tutor_id 配置不同模型。
"""

import logging
import os
from typing import Optional, Dict
from threading import Lock
from functools import lru_cache

# LLM imports (optional, will fallback to mock if not available)
try:
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMEngine:
    """
    LLM 引擎
    
    负责 LLM 文本生成，支持 Ollama 集成。
    每个实例对应一个 tutor_id，实现模型隔离。
    """

    def __init__(self, tutor_id: int):
        """
        初始化 LLM 引擎

        Args:
            tutor_id: 导师 ID，用于标识不同的模型实例
        """
        self.tutor_id = tutor_id
        self.use_llm = settings.enable_llm and LLM_AVAILABLE
        
        # 获取该 tutor_id 的模型配置（支持按 tutor 配置不同模型）
        # 环境变量格式: TUTOR_{tutor_id}_LLM_MODEL
        tutor_model_key = f"TUTOR_{tutor_id}_LLM_MODEL"
        self.model_name = os.getenv(tutor_model_key, settings.default_llm_model)
        
        # 初始化 LLM（如果启用）
        self.llm = None
        self.llm_chain = None
        
        if self.use_llm:
            try:
                self.llm = ChatOllama(
                    temperature=settings.llm_temperature,
                    model=self.model_name,
                    base_url=settings.ollama_base_url
                )
                # 构建 prompt 模板
                self.prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "你是一个专业的虚拟导师助手，能够友好、准确地回答学生的问题。"),
                    ("user", "{input}")
                ])
                self.llm_chain = self.prompt_template | self.llm | StrOutputParser()
                logger.info(f"LLM Engine initialized for tutor_id={tutor_id} with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize LLM for tutor_id={tutor_id}: {e}, falling back to Mock mode")
                self.use_llm = False
                self.llm = None
                self.llm_chain = None
        else:
            logger.info(f"LLM Engine initialized for tutor_id={tutor_id} (Mock mode - LLM disabled or not available)")

    async def generate(
        self,
        text: str,
        context: Optional[str] = None
    ) -> str:
        """
        生成 LLM 响应

        Args:
            text: 用户输入的文本
            context: 可选的上下文信息（用于 RAG，当前版本暂未实现）

        Returns:
            str: LLM 生成的响应文本
        """
        logger.info(f"LLM generating response for tutor_id={self.tutor_id}, text={text[:50]}...")

        # 如果启用了 LLM 且有可用的 chain，使用真实 LLM
        if self.use_llm and self.llm_chain is not None:
            try:
                # 构建输入
                input_data = {"input": text}
                
                # TODO: 如果 context 存在，应该将其添加到 prompt 中（用于 RAG）
                if context:
                    logger.info(f"Context provided but RAG integration not yet implemented")
                
                # 调用 LLM 生成响应
                response = await self.llm_chain.ainvoke(input_data)
                
                logger.info(f"LLM generated response (tutor_id={self.tutor_id}, model={self.model_name}): {response[:100]}...")
                return response
                
            except Exception as e:
                logger.error(f"LLM call failed for tutor_id={self.tutor_id}: {e}, falling back to Mock")
                # Fallback to Mock on error
                pass

        # Mock 模式或 LLM 调用失败时的 fallback
        mock_response = (
            f"[Mock LLM Response - Tutor {self.tutor_id}] "
            f"您刚才说：「{text}」。这是一个模拟的 LLM 回复。"
            f"在真实环境中，这里会调用 LLM 模型生成智能回复。"
        )
        logger.info(f"Generated mock response: {mock_response[:100]}...")
        return mock_response


# 按 tutor_id 隔离的 LLM 引擎实例缓存
_tutor_llm_engines: Dict[int, LLMEngine] = {}
_llm_engines_lock = Lock()


def get_llm_engine(tutor_id: int) -> LLMEngine:
    """
    获取指定 tutor_id 的 LLM 引擎实例
    
    实现按 tutor_id 隔离模型：
    - 每个 tutor_id 对应一个独立的 LLMEngine 实例
    - 不同 tutor 使用不同的模型实例
    - 模型实例会被缓存，避免重复创建
    
    Args:
        tutor_id: 导师 ID
        
    Returns:
        LLMEngine: 对应 tutor_id 的 LLM 引擎实例
    """
    global _tutor_llm_engines
    
    # 如果已存在，直接返回
    if tutor_id in _tutor_llm_engines:
        return _tutor_llm_engines[tutor_id]
    
    # 线程安全地创建新实例
    with _llm_engines_lock:
        # 双重检查，避免并发创建
        if tutor_id not in _tutor_llm_engines:
            _tutor_llm_engines[tutor_id] = LLMEngine(tutor_id=tutor_id)
            logger.info(f"Created new LLM Engine instance for tutor_id={tutor_id}")
        
        return _tutor_llm_engines[tutor_id]


def remove_llm_engine(tutor_id: int) -> bool:
    """
    移除指定 tutor_id 的 LLM 引擎实例（用于清理）
    
    Args:
        tutor_id: 导师 ID
        
    Returns:
        bool: 是否成功移除
    """
    global _tutor_llm_engines
    
    with _llm_engines_lock:
        if tutor_id in _tutor_llm_engines:
            del _tutor_llm_engines[tutor_id]
            logger.info(f"Removed LLM Engine instance for tutor_id={tutor_id}")
            return True
        return False


def get_all_tutor_ids() -> list:
    """
    获取所有已创建 LLM 引擎的 tutor_id 列表
    
    Returns:
        list: tutor_id 列表
    """
    with _llm_engines_lock:
        return list(_tutor_llm_engines.keys())


