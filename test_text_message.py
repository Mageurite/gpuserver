#!/usr/bin/env python3
"""
简单测试 - 发送文本消息到 WebSocket 服务器

用法:
    python test_text_message.py
"""

import asyncio
import websockets
import json

WEBSOCKET_URL = "ws://localhost:9001/ws/user_2"
USER_ID = 2
TUTOR_ID = 9
AVATAR_ID = "avatar_tutor_9"


async def test_text():
    """测试文本消息"""
    print(f"连接到 {WEBSOCKET_URL}...")

    async with websockets.connect(WEBSOCKET_URL) as websocket:
        print("✅ 连接成功\n")

        # 1. 发送 init 消息
        print("1. 发送 init 消息...")
        await websocket.send(json.dumps({
            "type": "init",
            "avatar_id": AVATAR_ID
        }))

        response = await websocket.recv()
        data = json.loads(response)
        print(f"   收到: type={data.get('type')}, video_size={len(data.get('video', ''))} bytes\n")

        # 2. 发送 text 消息
        print("2. 发送 text 消息...")
        await websocket.send(json.dumps({
            "type": "text",
            "content": "你好",
            "tutor_id": TUTOR_ID,
            "avatar_id": AVATAR_ID
        }))
        print("   已发送文本消息\n")

        # 3. 接收响应
        print("3. 等待响应...")
        for i in range(5):
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=30)
                data = json.loads(response)
                msg_type = data.get('type')
                content = data.get('content', '')

                print(f"   响应 {i+1}:")
                print(f"     类型: {msg_type}")

                if msg_type == 'text':
                    print(f"     内容: {content}")
                elif msg_type == 'audio':
                    print(f"     音频大小: {len(data.get('audio', ''))} bytes")
                elif msg_type == 'video':
                    print(f"     视频大小: {len(data.get('video', ''))} bytes")
                elif msg_type == 'error':
                    print(f"     错误: {content}")
                    break
            except asyncio.TimeoutError:
                print(f"   超时")
                break

        print("\n✅ 测试完成")


if __name__ == "__main__":
    asyncio.run(test_text())
