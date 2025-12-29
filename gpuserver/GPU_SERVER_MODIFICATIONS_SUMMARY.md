# GPU Server 修改总结

## 📋 修改日期
2025-12-29

## ✅ 已完成的修改

### 1. WebSocket 端点路径支持 (websocket_server.py:90-91)

**修改内容**：
- 端点路径从 `/ws/{session_id}` 改为 `/ws/{connection_id}`
- **新增**：同时支持 `/ws/ws/{connection_id}` 路径（后端代理使用）
- 支持两种连接模式：
  - **新模式（user-based）**：`connection_id = "user_{user_id}"`
  - **旧模式（session-based）**：`connection_id = "{session_id}"` (向后兼容)

**支持的路径**：
- `/ws/{connection_id}` - 原有路径
- `/ws/ws/{connection_id}` - 后端代理路径（新增）

**判断逻辑**：
```python
is_user_based = connection_id.startswith("user_")
```

### 2. Session 上下文管理 (websocket_server.py:38-40)

**新增数据结构**：
```python
# 活跃的 WebSocket 连接（按 connection_id 索引）
active_connections: Dict[str, WebSocket] = {}

# Session 上下文管理（按 engine_session_id 索引）
session_contexts: Dict[str, dict] = {}
```

**功能**：
- `active_connections`：存储 WebSocket 连接（按 `connection_id` 索引）
- `session_contexts`：存储每个 session 的上下文信息（对话历史、AI 引擎等）

### 3. 消息路由实现 (websocket_server.py:232-266)

**User-based 模式下的消息处理**：
1. 从消息中提取 `engine_session_id`
2. 验证 `engine_session_id` 是否有效
3. 获取或创建对应的 session 上下文
4. 使用正确的 session 上下文处理消息

**关键代码**：
```python
if is_user_based:
    engine_session_id = message.get("engine_session_id")

    # 验证并创建 session 上下文
    if engine_session_id not in session_contexts:
        target_session = manager.get_session(engine_session_id)
        session_contexts[engine_session_id] = {
            "session": target_session,
            "ai_engine": get_ai_engine(target_session.tutor_id)
        }

    # 使用正确的 session 上下文处理消息
    ctx = session_contexts[engine_session_id]
    await handle_message(websocket, ctx["session"], message, ctx["ai_engine"], is_user_based)
```

### 4. WebRTC 连接管理 (已存在，无需修改)

**现有实现已支持 user-based 模式**：
- `text_webrtc` 消息处理：使用 `f"user_{user_id}"` 作为 session_id (line 371)
- `webrtc_offer` 处理：使用 `f"user_{user_id}"` 作为 session_id (line 432)
- `webrtc_ice_candidate` 处理：使用 `f"user_{user_id}"` 作为 session_id (line 466)

### 5. 增强的日志记录 (websocket_server.py:368)

**新增日志信息**：
- 在 `text_webrtc` 消息处理中添加了 `engine_session_id` 日志
- 帮助调试消息路由和 session 上下文管理

**日志格式**：
```python
logger.info(f"Processing text with WebRTC streaming: avatar_id={avatar_id}, user_id={user_id}, engine_session_id={engine_session_id}, session_id={session.session_id}")
```

### 6. 向后兼容性 (websocket_server.py:161-183)

**Session-based 模式（旧模式）**：
- 完全保留原有逻辑
- 每个 session 独立的 WebSocket 连接
- 不需要 `engine_session_id`

---

## 🔄 工作流程

### User-based 模式（新模式）

1. **连接建立**：
   ```
   前端 → 后端代理 → GPU Server
   ws://backend:8000/api/ws/proxy/user/{user_id}?token={auth_token}
   → ws://gpu-server:19001/ws/user_{user_id}?token={engine_token}
   ```

2. **WebRTC 建立**：
   ```json
   {
     "type": "webrtc_offer",
     "sdp": "...",
     "user_id": 123
   }
   ```
   - GPU Server 使用 `user_{user_id}` 作为 WebRTC 连接标识
   - 同一个 user_id 的所有 session 共享这个 WebRTC 连接

3. **发送消息**：
   ```json
   {
     "type": "text_webrtc",
     "content": "用户消息",
     "avatar_id": "avatar_tutor_13",
     "user_id": 123,
     "engine_session_id": "uuid-here"
   }
   ```
   - GPU Server 从 `engine_session_id` 获取正确的 session 上下文
   - 使用 `user_{user_id}` 获取对应的 WebRTC 连接
   - 生成回复并通过 WebRTC 发送视频流

### Session-based 模式（旧模式，向后兼容）

1. **连接建立**：
   ```
   ws://gpu-server:19001/ws/{session_id}?token={engine_token}
   ```

2. **发送消息**：
   ```json
   {
     "type": "text",
     "content": "用户消息"
   }
   ```
   - 不需要 `engine_session_id` 或 `user_id`
   - 使用 connection_id (session_id) 直接处理

---

## 📝 消息格式

### 前端发送的消息

#### 1. WebRTC Offer
```json
{
  "type": "webrtc_offer",
  "sdp": "...",
  "user_id": 123,
  "avatar_id": "avatar_tutor_13"
}
```

#### 2. ICE Candidate
```json
{
  "type": "webrtc_ice_candidate",
  "candidate": {...},
  "user_id": 123
}
```

#### 3. 文本消息（WebRTC 模式）
```json
{
  "type": "text_webrtc",
  "content": "用户消息",
  "avatar_id": "avatar_tutor_13",
  "user_id": 123,
  "engine_session_id": "uuid-here"
}
```

### GPU Server 返回的消息

#### 1. WebRTC Answer
```json
{
  "type": "webrtc_answer",
  "sdp": "...",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 2. 文本响应
```json
{
  "type": "text",
  "content": "AI 回复",
  "audio": "base64-encoded-audio",
  "role": "assistant",
  "timestamp": "2025-12-29T12:00:00"
}
```

#### 3. 错误消息
```json
{
  "type": "error",
  "content": "错误描述",
  "timestamp": "2025-12-29T12:00:00"
}
```

---

## ⚠️ 重要注意事项

### 1. 连接复用
- 同一个 `user_id` 的所有 session 共享一个 WebSocket 和 WebRTC 连接
- 每个 session 的上下文（对话历史、状态等）独立管理

### 2. 消息路由
- **必须**从消息中提取 `engine_session_id` 来获取正确的 session 上下文
- WebRTC 相关消息（offer、ice_candidate）不需要 `engine_session_id`

### 3. 错误处理
- 如果消息中缺少 `engine_session_id`（user-based 模式），返回错误
- 如果 `engine_session_id` 无效，返回错误
- 如果 `user_id` 缺失（WebRTC 消息），返回错误

### 4. 连接清理
- User-based 模式：连接断开时不清理 `session_contexts`（用户可能重新连接）
- Session-based 模式：连接断开时清理所有资源

---

## ✅ 测试检查清单

- [x] WebSocket 端点支持 `user_{user_id}` 路径格式
- [x] WebRTC 连接管理基于 `user_id`（已存在）
- [x] 消息处理从 `engine_session_id` 提取 session 信息
- [x] ICE candidate 处理支持 `user_id`（已存在）
- [x] 向后兼容旧的 `session_id` 模式
- [ ] 测试同一个用户多个 session 共享连接
- [ ] 测试消息正确路由到对应的 session
- [ ] 测试 WebRTC 视频流正确发送

---

## 🔧 文件修改列表

1. **`/workspace/gpuserver/api/websocket_server.py`**
   - 修改 WebSocket 端点路径：`/ws/{connection_id}`
   - 添加 session 上下文管理：`session_contexts`
   - 实现 user-based 和 session-based 双模式支持
   - 实现基于 `engine_session_id` 的消息路由

2. **`/workspace/gpuserver/webrtc_streamer.py`**
   - 无需修改（已支持 user-based 模式）

---

## 📚 相关文档

- `/workspace/WEB_SERVER_INTEGRATION_GUIDE.md` - Web Server 集成指南
- `/workspace/GPU_SERVER_MODIFICATION_GUIDE.md` - GPU Server 修改指南（用户提供）
- `/workspace/gpuserver/WEBRTC_IMPLEMENTATION_GUIDE.md` - WebRTC 实现指南

---

## 🎯 总结

GPU Server 已成功修改以支持新的 user-based 架构：

1. ✅ WebSocket 端点支持 `user_{user_id}` 格式
2. ✅ Session 上下文管理支持多个 session 共享连接
3. ✅ 消息路由基于 `engine_session_id`
4. ✅ WebRTC 连接基于 `user_id`（已存在）
5. ✅ 完全向后兼容 session-based 模式

**关键改进**：
- 减少了连接数量（同一用户的多个 session 共享连接）
- 提高了系统效率
- 保持了向后兼容性
- 支持灵活的消息路由
