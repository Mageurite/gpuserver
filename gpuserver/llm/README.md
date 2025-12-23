# LLM 模块

LLM（Large Language Model）文本生成模块，提供基于 Ollama 的 LLM 集成。

## 📋 功能

- ✅ 基于 Ollama 的 LLM 文本生成
- ✅ 按 `tutor_id` 隔离模型实例
- ✅ 支持按 `tutor_id` 配置不同模型
- ✅ 自动降级到 Mock 模式（如果 LLM 不可用）
- ✅ 预留 RAG 上下文接口

## 🏗️ 架构

```
llm/
├── __init__.py          # 模块导出
├── llm_engine.py         # LLM 引擎实现
└── README.md            # 本文档
```

## 🚀 使用方法

### 基本使用

```python
from llm import get_llm_engine

# 获取 LLM 引擎实例
llm_engine = get_llm_engine(tutor_id=1)

# 生成响应
response = await llm_engine.generate(text="你好，请介绍一下 Python")
```

### 在 AIEngine 中使用

`ai_models.py` 中的 `AIEngine` 类已经集成了 LLM 模块：

```python
from ai_models import get_ai_engine

engine = get_ai_engine(tutor_id=1)
response = await engine.process_text(
    text="你好",
    tutor_id=1,
    kb_id=None  # 可选，用于 RAG（当前未实现）
)
```

## ⚙️ 配置

在 `.env` 文件中配置：

```bash
# Ollama 服务地址
OLLAMA_BASE_URL=http://127.0.0.1:11434

# 默认 LLM 模型
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16

# LLM 温度参数
LLM_TEMPERATURE=0.4

# 是否启用 LLM
ENABLE_LLM=true

# 按 tutor_id 配置不同模型（可选）
TUTOR_1_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
TUTOR_2_LLM_MODEL=llama3.1:8b-instruct-q4_K_M
```

## 📝 注意事项

1. **依赖要求**：需要安装 `langchain-ollama`（已在 `requirements.txt` 中）
2. **Ollama 服务**：确保 Ollama 服务正在运行：`ollama serve`
3. **模型安装**：确保已安装模型：`ollama pull mistral-nemo:12b-instruct-2407-fp16`
4. **自动降级**：如果 LLM 不可用，会自动使用 Mock 模式，不会报错

## 🔄 与 try/llm 的区别

- **简化设计**：不包含 LangGraph 工作流、RAG 检索等复杂功能
- **专注核心**：只提供 LLM 文本生成功能
- **易于集成**：作为 `ai_models.py` 的一个组件使用
- **后续扩展**：可以逐步添加 RAG、流式输出等功能

## 🚧 TODO

- [ ] 实现 RAG 知识库检索（当 `context` 参数提供时）
- [ ] 支持流式输出（用于实时对话）
- [ ] 支持对话历史管理
- [ ] 添加更多 prompt 模板选项


