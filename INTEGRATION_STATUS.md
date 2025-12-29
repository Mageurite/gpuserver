# 🎯 GPU Server 与 Web 端集成状态

## ✅ 当前状态

**GPU Server**: ✅ 完全就绪  
**Web Server**: 需要配置连接  
**前端**: 需要实现 WebSocket 集成  

---

## 📊 GPU Server 状态

### 运行状态
- ✅ 服务运行中 (Port 9000)
- ✅ 管理 API 正常
- ✅ WebSocket 接口正常
- ✅ 视频生成功能完整

### 测试结果
```bash
# 健康检查
curl http://localhost:9000/health
# ✅ {"status":"healthy","service":"GPU Server"}

# 创建会话
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'
# ✅ 返回 session_id, engine_url, engine_token
```

---

## 🔗 集成步骤

### 1. Web Server 配置 (Port 8000)

**位置**: `/workspace/virtual_tutor/app_backend`

**配置文件**: `.env`
```bash
ENGINE_URL=http://localhost:9000
```

**实现要点**:
- 调用 GPU Server 的 `/v1/sessions` API 创建会话
- 返回 `engine_url` 和 `engine_token` 给前端
- 前端使用这些信息连接 WebSocket

### 2. 前端集成 (Port 3000)

**WebSocket 连接**:
```javascript
// 1. 从 Web Server 获取会话信息
const response = await fetch('/api/student/sessions', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwt_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ tutor_id: 1 })
});

const { engine_url, engine_token } = await response.json();

// 2. 连接 WebSocket
const ws = new WebSocket(`${engine_url}?token=${engine_token}`);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'text') {
    // 显示文本响应
    displayMessage(msg.content);
  } else if (msg.type === 'video') {
    // 显示视频响应
    displayVideo(msg.video);
  }
};

// 3. 发送消息
ws.send(JSON.stringify({
  type: 'text',
  content: '你好',
  avatar_id: 'avatar_tutor_13'  // 可选，启用视频
}));
```

---

## 📝 API 文档

### GPU Server 管理 API

**Base URL**: `http://localhost:9000`

#### 创建会话
```
POST /v1/sessions
Content-Type: application/json

{
  "tutor_id": 1,
  "student_id": 123,
  "kb_id": "optional"
}

Response:
{
  "session_id": "uuid",
  "engine_url": "ws://localhost:9000/ws/ws/uuid",
  "engine_token": "token",
  "status": "active"
}
```

#### 查询会话
```
GET /v1/sessions/{session_id}

Response:
{
  "session_id": "uuid",
  "tutor_id": 1,
  "student_id": 123,
  "status": "active",
  "created_at": "2025-12-28T...",
  "last_activity": "2025-12-28T..."
}
```

#### 删除会话
```
DELETE /v1/sessions/{session_id}

Response: 204 No Content
```

### WebSocket API

**URL**: `ws://localhost:9000/ws/ws/{session_id}?token={token}`

#### 客户端发送
```json
// 文本消息
{
  "type": "text",
  "content": "你好",
  "avatar_id": "avatar_tutor_13"  // 可选
}

// 音频消息
{
  "type": "audio",
  "data": "base64_encoded_audio"
}
```

#### 服务器响应
```json
// 文本响应
{
  "type": "text",
  "content": "你好！有什么可以帮助你的吗？",
  "role": "assistant",
  "timestamp": "2025-12-28T..."
}

// 视频响应（如果启用）
{
  "type": "video",
  "video": "base64_encoded_video",
  "audio": "base64_encoded_audio",
  "content": "你好！有什么可以帮助你的吗？",
  "role": "assistant"
}

// 转录结果
{
  "type": "transcription",
  "content": "转录的文本",
  "role": "user"
}
```

---

## 🚀 快速开始

### 启动 GPU Server
```bash
cd /workspace/gpuserver
./start_mt.sh
```

### 测试 GPU Server
```bash
# 健康检查
curl http://localhost:9000/health

# 创建会话
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'
```

### 启动 Web Server
```bash
cd /workspace/virtual_tutor/app_backend
# 确保 .env 中有 ENGINE_URL=http://localhost:9000
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 📚 相关文档

- [集成测试报告](gpuserver/INTEGRATION_TEST_REPORT.md)
- [GPU Server 启动指南](gpuserver/STARTUP_SCRIPTS_GUIDE.md)
- [端到端管道说明](gpuserver/END_TO_END_PIPELINE_SUMMARY.md)
- [项目架构文档](claude.md)

---

## ✅ 检查清单

### GPU Server
- [x] 服务运行正常
- [x] 管理 API 可用
- [x] WebSocket 接口正常
- [x] 视频生成功能完整
- [x] 文档完整

### Web Server
- [ ] 配置 ENGINE_URL
- [ ] 实现会话创建接口
- [ ] 测试与 GPU Server 连接

### 前端
- [ ] 实现 WebSocket 连接
- [ ] 实现消息发送/接收
- [ ] 实现视频显示（如需要）
- [ ] 端到端测试

---

**最后更新**: 2025-12-28  
**状态**: GPU Server 就绪，等待 Web Server 和前端集成
