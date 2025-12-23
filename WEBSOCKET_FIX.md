# WebSocket 连接问题修复指南

## 部署架构

**当前实际架构**：
- **前端**：用户浏览器（公网访问）
- **Web Server 后端**：`51.161.130.234:8000`
- **GPU Server**：`51.161.130.234:9000`（同一台服务器）

⚠️ **重要**：Web Server **没有实现 WebSocket 代理功能**，因此前端必须直接访问 GPU Server 的 WebSocket。

---

## 问题总结

1. **本地测试 WebSocket 失败**：`BaseEventLoop.create_connection() got an unexpected keyword argument 'timeout'` ✅ **已修复**
2. **前端访问 GPU Server 返回 404**：配置的 `engine_url` 不正确

---

## 根本原因

### 1. WebSocket 路径配置
当前 GPU Server 使用**统一模式**（Unified Mode），所有服务运行在端口 9000：
- 管理 API: `http://51.161.130.234:9000/v1/sessions`
- WebSocket: `ws://51.161.130.234:9000/ws/ws/{session_id}?token=xxx`

**注意双层 `/ws/ws/` 路径**：
- 第一个 `/ws`: 在 `unified_server.py:33` 中挂载的子应用路径
- 第二个 `/ws`: 在 `websocket_server.py:45` 中定义的 WebSocket 路由

### 2. WEBSOCKET_URL 配置错误
当前 `.env` 配置：
```bash
WEBSOCKET_URL=ws://localhost:9000  # ❌ 错误：前端无法访问 localhost
```

应该配置为服务器的公网地址：
```bash
WEBSOCKET_URL=ws://51.161.130.234:9000  # ✅ 正确
```

---

## 解决方案

### 步骤 1：修改 GPU Server 配置

编辑 [.env](.env#L8) 文件：
```bash
cd /workspace/gpuserver
vim .env
```

修改 `WEBSOCKET_URL`：
```bash
# 将这行：
WEBSOCKET_URL=ws://localhost:9000

# 改为：
WEBSOCKET_URL=ws://51.161.130.234:9000
```

完整配置应该是：
```bash
# GPU Server 配置
MANAGEMENT_API_HOST=0.0.0.0
MANAGEMENT_API_PORT=9000

WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=9001  # 统一模式下此端口不使用，保留是为了兼容配置

WEBSOCKET_URL=ws://51.161.130.234:9000  # 前端访问的 WebSocket 地址

CUDA_VISIBLE_DEVICES=0

MAX_SESSIONS=10
SESSION_TIMEOUT_SECONDS=3600
```

### 步骤 2：重启 GPU Server

```bash
cd /workspace/gpuserver
./restart.sh
```

### 步骤 3：验证配置

#### 3.1 测试管理 API
```bash
curl http://51.161.130.234:9000/health
```

预期输出：
```json
{"status":"healthy","service":"GPU Server"}
```

#### 3.2 创建测试会话
```bash
curl -X POST http://51.161.130.234:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 999, "kb_id": "test"}'
```

预期输出（**注意 engine_url**）：
```json
{
  "session_id": "xxx-xxx-xxx",
  "engine_url": "ws://51.161.130.234:9000/ws/ws/xxx-xxx-xxx",
  "engine_token": "xxxxxxxx",
  "status": "active"
}
```

#### 3.3 测试 WebSocket 连接
```bash
cd /workspace/gpuserver
./test_webserver_connection.sh
```

如果所有测试通过（包括 WebSocket 测试），说明配置正确。

### 步骤 4：前端配置

前端需要：
1. 调用 Web Server API 创建会话，获取 `engine_url` 和 `engine_token`（隐含在 `engine_url` 中）
2. 使用返回的 `engine_url` 直接连接 GPU Server 的 WebSocket

**前端示例代码**：
```javascript
// 1. 创建会话（通过 Web Server）
const response = await fetch("http://51.161.130.234:8000/api/tutors/1/sessions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_JWT_TOKEN"  // 如果需要认证
  },
  body: JSON.stringify({
    student_id: 123,
    kb_id: "test"
  })
})

const data = await response.json()
console.log("Session created:", data)

// data 结构应该是：
// {
//   session_id: "xxx",
//   engine_url: "ws://51.161.130.234:9000/ws/ws/xxx?token=yyy"
// }

// 2. 直接连接 GPU Server 的 WebSocket
const ws = new WebSocket(data.engine_url)  // 已包含 token

ws.onopen = () => {
  console.log("✓ WebSocket connected")

  // 发送测试消息
  ws.send(JSON.stringify({
    type: "text",
    content: "Hello"
  }))
}

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  console.log("✓ Received:", message)

  if (message.type === "text") {
    console.log("AI:", message.content)
  } else if (message.type === "error") {
    console.error("Error:", message.content)
  }
}

ws.onerror = (error) => {
  console.error("✗ WebSocket error:", error)
}

ws.onclose = () => {
  console.log("WebSocket closed")
}
```

---

## 完整工作流程

### 1. Web Server 负责
- 用户认证（JWT）
- 多租户隔离（检查 tutor 是否属于当前用户）
- 会话管理（调用 GPU Server API 创建/删除会话）
- 返回 `engine_url` 给前端

### 2. GPU Server 负责
- AI 推理（LLM、ASR、TTS）
- WebSocket 实时通信
- 会话状态管理

### 3. 前端负责
- 通过 Web Server 创建会话
- 直接连接 GPU Server WebSocket
- 发送/接收实时消息

**流程图**：
```
前端浏览器
    ↓ (1) POST /api/tutors/1/sessions
Web Server (8000)
    ↓ (2) POST /v1/sessions
GPU Server (9000)
    ↓ (3) 返回 session_id, engine_url, token
Web Server (8000)
    ↓ (4) 返回给前端
前端浏览器
    ↓ (5) WebSocket 连接 engine_url
GPU Server (9000) ← 直接连接，不经过 Web Server
```

---

## Web Server 需要实现的 API

Web Server 需要添加会话管理接口（如果还没有）：

### 创建会话
```python
# app/api/routes_tutors.py

from fastapi import HTTPException
import httpx
from app.core.config import settings

@router.post("/{tutor_id}/sessions")
async def create_session(
    tutor_id: int,
    student_id: int,
    kb_id: str = None,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    # 1. 验证 tutor 是否属于当前管理员
    tutor = db.query(Tutor).filter(
        Tutor.id == tutor_id,
        Tutor.admin_id == current_admin.id
    ).first()

    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor not found")

    # 2. 调用 GPU Server 创建会话
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.ENGINE_URL}/v1/sessions",
                json={
                    "tutor_id": tutor_id,
                    "student_id": student_id,
                    "kb_id": kb_id
                },
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=503,
                detail=f"GPU Server error: {str(e)}"
            )

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_admin: Admin = Depends(get_current_admin),
):
    # 调用 GPU Server 删除会话
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(
                f"{settings.ENGINE_URL}/v1/sessions/{session_id}",
                timeout=10.0
            )
            response.raise_for_status()
            return {"status": "deleted"}

        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=503,
                detail=f"GPU Server error: {str(e)}"
            )
```

---

## 常见问题排查

### 1. 前端连接 WebSocket 返回 404

**可能原因**：
- `WEBSOCKET_URL` 配置错误（仍然是 `localhost`）
- 路径错误（缺少 `/ws/ws/` 双层路径）
- GPU Server 未启动

**排查步骤**：
```bash
# 1. 检查配置
cd /workspace/gpuserver
cat .env | grep WEBSOCKET_URL
# 应该显示: WEBSOCKET_URL=ws://51.161.130.234:9000

# 2. 检查 GPU Server 是否运行
./status.sh

# 3. 创建测试会话，检查返回的 engine_url
curl -X POST http://51.161.130.234:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 999, "kb_id": "test"}'

# 4. 测试 WebSocket（使用返回的 engine_url）
./test_webserver_connection.sh
```

### 2. WebSocket 连接后立即断开

**可能原因**：
- Token 验证失败
- session_id 不存在或已过期

**解决**：确保前端使用完整的 `engine_url`（包含 token）

### 3. WebSocket 测试脚本报错

**已修复**：[test_webserver_connection.sh:133](test_webserver_connection.sh#L133) 中的 `timeout` 参数问题已修复

### 4. Web Server 无法连接 GPU Server

**可能原因**：
- `ENGINE_URL` 配置错误
- GPU Server 未启动

**排查**：
```bash
# 检查 Web Server 配置
cat /workspace/virtual_tutor/app_backend/.env | grep ENGINE_URL
# 应该显示: ENGINE_URL=http://localhost:9000

# 测试连接
curl http://localhost:9000/health
```

### 5. 防火墙问题

**症状**：本地测试正常，前端无法连接

**解决**：确保服务器防火墙开放端口 9000
```bash
# 检查端口是否监听
netstat -tlnp | grep 9000

# 如果使用 ufw
sudo ufw allow 9000/tcp

# 如果使用 firewalld
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --reload
```

---

## 安全建议

### 1. 使用 wss:// (WebSocket over TLS)
生产环境应该使用 HTTPS/WSS：
```bash
# 使用 nginx 反向代理
# /etc/nginx/sites-available/default

server {
    listen 443 ssl;
    server_name 51.161.130.234;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Web Server
    location /api/ {
        proxy_pass http://localhost:8000;
    }

    # GPU Server WebSocket
    location /ws/ {
        proxy_pass http://localhost:9000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

配置 GPU Server：
```bash
WEBSOCKET_URL=wss://51.161.130.234/ws
```

### 2. 限制连接数和速率
在 GPU Server 中已实现：
- 最大会话数限制：`MAX_SESSIONS=10`
- 会话超时：`SESSION_TIMEOUT_SECONDS=3600`

### 3. Token 验证
已实现：WebSocket 连接需要有效的 `engine_token`

---

## 总结

**关键配置变更**：
```bash
# GPU Server .env
WEBSOCKET_URL=ws://51.161.130.234:9000  # 改为公网地址

# Web Server .env
ENGINE_URL=http://localhost:9000  # Web Server 和 GPU Server 在同一台机器
```

**完整的 WebSocket URL 格式**：
```
ws://51.161.130.234:9000/ws/ws/{session_id}?token={engine_token}
```

**前端连接步骤**：
1. 调用 Web Server API 创建会话
2. 获取 `engine_url`（已包含 session_id 和 token）
3. 直接使用 `engine_url` 连接 WebSocket

**不要手动拼接 WebSocket URL**，直接使用 API 返回的 `engine_url`！
