#!/usr/bin/env python3
"""
测试音频响应 - 验证 WebSocket 是否正确返回音频数据
"""

import asyncio
import websockets
import json

WEBSOCKET_URL = "ws://localhost:9001/ws/user_4"
USER_ID = 4
TUTOR_ID = 9
AVATAR_ID = "avatar_tutor_9"


async def test_audio_in_response():
    """测试 text_webrtc 消息是否返回音频"""
    print(f"连接到 {WEBSOCKET_URL}...")

    async with websockets.connect(WEBSOCKET_URL) as websocket:
        print("✅ 连接成功\n")

        # 1. 发送 init 消息
        print("1. 发送 init 消息...")
        await websocket.send(json.dumps({
            "type": "init",
            "avatar_id": AVATAR_ID
        }))

        # 跳过 init 响应
        await websocket.recv()
        print("   Init 响应已收到\n")

        # 2. 发送 text_webrtc 消息
        print("2. 发送 text_webrtc 消息...")
        await websocket.send(json.dumps({
            "type": "text_webrtc",
            "content": "hello",
            "tutor_id": TUTOR_ID,
            "avatar_id": AVATAR_ID,
            "user_id": USER_ID
        }))
        print("   已发送消息\n")

        # 3. 接收响应
        print("3. 等待响应...\n")
        response = await asyncio.wait_for(websocket.recv(), timeout=30)
        data = json.loads(response)

        print(f"收到响应:")
        print(f"  类型: {data.get('type')}")
        print(f"  内容: {data.get('content', '')[:50]}...")

        # 检查音频
        audio = data.get('audio')
        if audio:
            print(f"  ✅ 包含音频: {len(audio)} bytes")
        else:
            print(f"  ❌ 没有音频字段")

        # 检查视频
        video = data.get('video')
        if video:
            print(f"  视频: {len(video)} bytes")
        else:
            print(f"  没有视频字段（视频应该通过 WebRTC 传输）")

        print("\n✅ 测试完成")


if __name__ == "__main__":
    asyncio.run(test_audio_in_response())
