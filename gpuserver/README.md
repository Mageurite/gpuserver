# GPU Server

AI 推理引擎 - 支持 LLM、ASR、TTS、视频生成

## 快速开始

```bash
# 启动
./server.sh start

# 停止
./server.sh stop

# 重启
./server.sh restart

# 状态
./server.sh status
```

## API

- 管理 API: `http://localhost:9000/v1/sessions`
- WebSocket: `ws://localhost:9000/ws/ws/{session_id}?token={token}`
- 健康检查: `http://localhost:9000/health`

## 配置

编辑 `.env` 文件配置服务参数。

## 目录结构

```
gpuserver/
├── server.sh              # 启动/停止脚本
├── unified_server.py      # 主服务器
├── config.py              # 配置管理
├── session_manager.py     # 会话管理
├── ai_models.py           # AI 模型接口
├── api/                   # API 模块
│   ├── management_api.py  # 管理 API
│   └── websocket_server.py # WebSocket 服务
├── llm/                   # LLM 模块
├── asr/                   # 语音识别
├── tts/                   # 语音合成
├── musetalk/              # 视频生成
└── rag/                   # RAG 检索
```
