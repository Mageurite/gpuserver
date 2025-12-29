"""
简单的 WebSocket 服务器测试
用于验证 WebSocket 端点路径是否正确配置
"""
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
import uvicorn

app = FastAPI(title="WebSocket Test Server")

# 模拟的活跃连接
active_connections = {}

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "WebSocket Test Server",
        "active_connections": len(active_connections)
    }

@app.websocket("/ws/{connection_id}")
@app.websocket("/ws/ws/{connection_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    connection_id: str,
    token: str = Query(default="test_token")
):
    """
    WebSocket 测试端点
    支持两种路径：
    - /ws/{connection_id}
    - /ws/ws/{connection_id}
    """
    # 判断连接模式
    is_user_based = connection_id.startswith("user_")

    # 接受连接
    await websocket.accept()
    active_connections[connection_id] = websocket

    mode = "user-based" if is_user_based else "session-based"
    print(f"✅ WebSocket connected: connection_id={connection_id}, mode={mode}, token={token}")

    # 发送欢迎消息
    await websocket.send_json({
        "type": "connection_success",
        "connection_id": connection_id,
        "mode": mode,
        "message": f"Connected successfully in {mode} mode",
        "supported_paths": ["/ws/{connection_id}", "/ws/ws/{connection_id}"]
    })

    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)

            print(f"📨 Received message: type={message.get('type')}, connection_id={connection_id}")

            # 提取关键字段
            msg_type = message.get("type")
            engine_session_id = message.get("engine_session_id")
            user_id = message.get("user_id")
            avatar_id = message.get("avatar_id")

            # 验证必需字段
            if is_user_based and msg_type not in ["webrtc_offer", "webrtc_ice_candidate"]:
                if not engine_session_id:
                    await websocket.send_json({
                        "type": "error",
                        "content": "engine_session_id is required in user-based mode"
                    })
                    continue

            # 回显消息
            response = {
                "type": "echo",
                "original_message": message,
                "connection_id": connection_id,
                "mode": mode,
                "validation": {
                    "is_user_based": is_user_based,
                    "has_engine_session_id": engine_session_id is not None,
                    "has_user_id": user_id is not None,
                    "has_avatar_id": avatar_id is not None
                }
            }

            await websocket.send_json(response)
            print(f"✅ Sent response to {connection_id}")

    except WebSocketDisconnect:
        print(f"❌ WebSocket disconnected: connection_id={connection_id}")
    except Exception as e:
        print(f"⚠️ Error: {e}")
    finally:
        active_connections.pop(connection_id, None)
        print(f"🧹 Cleaned up connection: {connection_id}")

if __name__ == "__main__":
    print("🚀 Starting WebSocket Test Server...")
    print("📍 Endpoints:")
    print("   - GET  /health")
    print("   - WS   /ws/{connection_id}")
    print("   - WS   /ws/ws/{connection_id}")
    print("\n🧪 Test URLs:")
    print("   - ws://localhost:19001/ws/test_session_123?token=test")
    print("   - ws://localhost:19001/ws/ws/user_6?token=test")
    print("\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=19001,
        log_level="info"
    )
