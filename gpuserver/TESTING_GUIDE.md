# GPU Server 测试指南

## 📋 测试目标

验证 GPU Server 是否正确支持 user-based WebSocket 和 WebRTC 连接架构。

---

## 🔧 测试环境准备

### 1. 启动 GPU Server

```bash
cd /workspace/gpuserver
python api/websocket_server.py
```

**预期输出**：
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:19001
```

### 2. 检查健康状态

```bash
curl http://localhost:19001/health
```

**预期响应**：
```json
{
  "status": "healthy",
  "service": "GPU Server WebSocket API",
  "active_connections": 0
}
```

---

## 🧪 测试用例

### 测试 1: WebSocket 端点路径支持

#### 1.1 测试 `/ws/{connection_id}` 路径

```bash
# 使用 websocat 或类似工具测试
websocat "ws://localhost:19001/ws/test_session_123?token=YOUR_TOKEN"
```

**预期**：连接成功（如果 token 有效）

#### 1.2 测试 `/ws/ws/{connection_id}` 路径（后端代理使用）

```bash
websocat "ws://localhost:19001/ws/ws/user_6?token=YOUR_TOKEN"
```

**预期**：连接成功（如果 token 有效）

---

### 测试 2: User-based 模式

#### 2.1 建立 WebSocket 连接

**连接 URL**：
```
ws://localhost:19001/ws/ws/user_6?token=YOUR_ENGINE_TOKEN
```

**预期日志**：
```
INFO - User-based connection mode: user_id=6
INFO - WebSocket connected (user-based): connection_id=user_6, user_id=6
```

#### 2.2 发送 WebRTC Offer

**消息**：
```json
{
  "type": "webrtc_offer",
  "sdp": "v=0\r\no=- ...",
  "user_id": 6,
  "avatar_id": "avatar_tutor_13"
}
```

**预期响应**：
```json
{
  "type": "webrtc_answer",
  "sdp": "v=0\r\no=- ...",
  "timestamp": "2025-12-29T12:00:00"
}
```

**预期日志**：
```
INFO - Received WebRTC offer from session xxx, user_id=6
INFO - WebRTC answer sent to user 6 with idle frames
```

#### 2.3 发送 ICE Candidate

**消息**：
```json
{
  "type": "webrtc_ice_candidate",
  "candidate": {
    "candidate": "candidate:...",
    "sdpMLineIndex": 0,
    "sdpMid": "0"
  },
  "user_id": 6
}
```

**预期日志**：
```
INFO - Received ICE candidate from session xxx, user_id=6
```

#### 2.4 发送文本消息（带 engine_session_id）

**消息**：
```json
{
  "type": "text_webrtc",
  "content": "你好",
  "avatar_id": "avatar_tutor_13",
  "user_id": 6,
  "engine_session_id": "uuid-session-1"
}
```

**预期日志**：
```
INFO - Created session context for engine_session_id=uuid-session-1
INFO - Processing text with WebRTC streaming: avatar_id=avatar_tutor_13, user_id=6, engine_session_id=uuid-session-1, session_id=uuid-session-1
INFO - WebRTC streaming response sent
```

**预期响应**：
```json
{
  "type": "text",
  "content": "AI 的回复内容",
  "audio": "base64-encoded-audio-data",
  "role": "assistant",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 2.5 测试多个 Session 共享连接

**场景**：同一个 user_id (6) 有两个不同的 session

**第一个 Session 消息**：
```json
{
  "type": "text_webrtc",
  "content": "第一个会话的消息",
  "avatar_id": "avatar_tutor_13",
  "user_id": 6,
  "engine_session_id": "uuid-session-1"
}
```

**第二个 Session 消息**：
```json
{
  "type": "text_webrtc",
  "content": "第二个会话的消息",
  "avatar_id": "avatar_tutor_13",
  "user_id": 6,
  "engine_session_id": "uuid-session-2"
}
```

**预期**：
- 两个消息都通过同一个 WebSocket 连接发送
- 两个消息都通过同一个 WebRTC 连接发送视频
- 每个消息使用各自的 session 上下文（对话历史独立）

**预期日志**：
```
INFO - Created session context for engine_session_id=uuid-session-1
INFO - Processing text with WebRTC streaming: ... engine_session_id=uuid-session-1, session_id=uuid-session-1
INFO - Created session context for engine_session_id=uuid-session-2
INFO - Processing text with WebRTC streaming: ... engine_session_id=uuid-session-2, session_id=uuid-session-2
```

---

### 测试 3: Session-based 模式（向后兼容）

#### 3.1 建立 WebSocket 连接

**连接 URL**：
```
ws://localhost:19001/ws/session_abc123?token=YOUR_ENGINE_TOKEN
```

**预期日志**：
```
INFO - Session-based connection mode: session_id=session_abc123
INFO - WebSocket connected (session-based): session_id=session_abc123, tutor_id=13
```

#### 3.2 发送文本消息（不需要 engine_session_id）

**消息**：
```json
{
  "type": "text",
  "content": "你好"
}
```

**预期**：正常处理，返回响应

---

### 测试 4: 错误处理

#### 4.1 缺少 engine_session_id（user-based 模式）

**消息**：
```json
{
  "type": "text_webrtc",
  "content": "你好",
  "avatar_id": "avatar_tutor_13",
  "user_id": 6
}
```

**预期响应**：
```json
{
  "type": "error",
  "content": "engine_session_id is required in user-based mode",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 4.2 缺少 user_id（WebRTC 消息）

**消息**：
```json
{
  "type": "text_webrtc",
  "content": "你好",
  "avatar_id": "avatar_tutor_13",
  "engine_session_id": "uuid-session-1"
}
```

**预期响应**：
```json
{
  "type": "error",
  "content": "user_id is required for WebRTC streaming",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 4.3 无效的 engine_session_id

**消息**：
```json
{
  "type": "text_webrtc",
  "content": "你好",
  "avatar_id": "avatar_tutor_13",
  "user_id": 6,
  "engine_session_id": "invalid-session-id"
}
```

**预期响应**：
```json
{
  "type": "error",
  "content": "Invalid engine_session_id: invalid-session-id",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 4.4 缺少 avatar_id

**消息**：
```json
{
  "type": "text_webrtc",
  "content": "你好",
  "user_id": 6,
  "engine_session_id": "uuid-session-1"
}
```

**预期响应**：
```json
{
  "type": "error",
  "content": "avatar_id is required for WebRTC streaming",
  "timestamp": "2025-12-29T12:00:00"
}
```

---

## 🔍 日志检查

### 关键日志点

1. **连接建立**：
   ```
   INFO - User-based connection mode: user_id=6
   INFO - WebSocket connected (user-based): connection_id=user_6, user_id=6
   ```

2. **Session 上下文创建**：
   ```
   INFO - Created session context for engine_session_id=uuid-session-1
   ```

3. **消息处理**：
   ```
   INFO - Processing text with WebRTC streaming: avatar_id=avatar_tutor_13, user_id=6, engine_session_id=uuid-session-1, session_id=uuid-session-1
   ```

4. **WebRTC 连接**：
   ```
   INFO - Received WebRTC offer from session xxx, user_id=6
   INFO - WebRTC answer sent to user 6 with idle frames
   ```

5. **连接清理**：
   ```
   INFO - Connection cleaned up (user-based): connection_id=user_6
   ```

---

## 🧰 测试工具

### 1. websocat（WebSocket 客户端）

安装：
```bash
# macOS
brew install websocat

# Linux
cargo install websocat
```

使用：
```bash
websocat "ws://localhost:19001/ws/ws/user_6?token=YOUR_TOKEN"
```

### 2. Python 测试脚本

创建 `test_websocket.py`：

```python
import asyncio
import websockets
import json

async def test_user_based_connection():
    uri = "ws://localhost:19001/ws/ws/user_6?token=YOUR_TOKEN"

    async with websockets.connect(uri) as websocket:
        # 发送 WebRTC offer
        offer = {
            "type": "webrtc_offer",
            "sdp": "v=0...",
            "user_id": 6,
            "avatar_id": "avatar_tutor_13"
        }
        await websocket.send(json.dumps(offer))

        # 接收 answer
        response = await websocket.recv()
        print(f"Received: {response}")

        # 发送文本消息
        message = {
            "type": "text_webrtc",
            "content": "你好",
            "avatar_id": "avatar_tutor_13",
            "user_id": 6,
            "engine_session_id": "test-session-1"
        }
        await websocket.send(json.dumps(message))

        # 接收响应
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.run(test_user_based_connection())
```

运行：
```bash
python test_websocket.py
```

---

## ✅ 测试检查清单

### 基本功能
- [ ] GPU Server 启动成功
- [ ] 健康检查接口正常
- [ ] `/ws/{connection_id}` 路径可访问
- [ ] `/ws/ws/{connection_id}` 路径可访问

### User-based 模式
- [ ] 连接 `user_{user_id}` 格式成功
- [ ] WebRTC offer/answer 交换成功
- [ ] ICE candidate 处理成功
- [ ] 文本消息处理成功（带 engine_session_id）
- [ ] 多个 session 共享连接成功
- [ ] Session 上下文正确创建和管理
- [ ] 视频通过 WebRTC 正确发送

### Session-based 模式（向后兼容）
- [ ] 连接 `session_id` 格式成功
- [ ] 文本消息处理成功（不需要 engine_session_id）
- [ ] 所有旧功能正常工作

### 错误处理
- [ ] 缺少 engine_session_id 返回错误
- [ ] 缺少 user_id 返回错误
- [ ] 无效的 engine_session_id 返回错误
- [ ] 缺少 avatar_id 返回错误
- [ ] 无效的 token 拒绝连接

### 日志验证
- [ ] 连接模式正确识别（user-based vs session-based）
- [ ] Session 上下文创建日志正确
- [ ] 消息处理日志包含所有关键信息
- [ ] WebRTC 连接日志正确
- [ ] 错误日志清晰明确

---

## 🐛 常见问题排查

### 问题 1: 连接被拒绝

**症状**：WebSocket 连接失败，返回 403 或 1008 错误

**可能原因**：
- Token 无效或过期
- Session 不存在

**排查步骤**：
1. 检查 token 是否有效
2. 检查 session 是否已创建
3. 查看 GPU Server 日志

### 问题 2: 消息路由失败

**症状**：发送消息后没有响应或返回错误

**可能原因**：
- 缺少 engine_session_id
- engine_session_id 无效
- Session 上下文未创建

**排查步骤**：
1. 检查消息是否包含 engine_session_id
2. 检查 engine_session_id 是否有效
3. 查看日志中的 session 上下文创建记录

### 问题 3: WebRTC 连接失败

**症状**：WebRTC offer 发送后没有 answer

**可能原因**：
- 缺少 user_id
- WebRTC streamer 未初始化

**排查步骤**：
1. 检查消息是否包含 user_id
2. 检查 GPU Server 日志中的 WebRTC 相关日志
3. 验证 idle frames 是否加载成功

---

## 📊 性能测试

### 测试场景：多个 Session 共享连接

**目标**：验证同一个 user_id 的多个 session 可以共享连接

**步骤**：
1. 建立一个 user-based WebSocket 连接（user_6）
2. 发送 10 条消息，使用 5 个不同的 engine_session_id
3. 验证所有消息都通过同一个连接处理
4. 验证每个 session 的上下文独立

**预期结果**：
- 只有 1 个 WebSocket 连接
- 只有 1 个 WebRTC 连接
- 创建了 5 个 session 上下文
- 所有消息都正确处理

---

## 📝 测试报告模板

```markdown
# GPU Server 测试报告

## 测试日期
2025-12-29

## 测试环境
- GPU Server 版本: 1.0.0
- Python 版本: 3.x
- 操作系统: Linux

## 测试结果

### 基本功能
- [x] GPU Server 启动成功
- [x] 健康检查接口正常
- [x] WebSocket 端点可访问

### User-based 模式
- [x] 连接建立成功
- [x] WebRTC 交换成功
- [x] 消息处理成功
- [x] 多 session 共享连接成功

### Session-based 模式
- [x] 向后兼容性验证通过

### 错误处理
- [x] 所有错误场景正确处理

## 发现的问题
无

## 建议
无

## 测试人员
[Your Name]
```

---

## 🎯 总结

完成以上所有测试后，GPU Server 应该能够：

1. ✅ 支持 user-based WebSocket 连接（`/ws/ws/user_{user_id}`）
2. ✅ 支持 session-based WebSocket 连接（向后兼容）
3. ✅ 正确路由消息到对应的 session（基于 engine_session_id）
4. ✅ 支持多个 session 共享 WebSocket 和 WebRTC 连接
5. ✅ 提供清晰的错误消息和日志
6. ✅ 与后端代理正确集成
