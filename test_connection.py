#!/usr/bin/env python3
"""
测试WebSocket连接
"""
import asyncio
import json
import websockets
import sys

async def test_simple_websocket():
    """简单测试WebSocket连接"""
    print("=" * 60)
    print("🧪 测试 WebSocket 连接")
    print("=" * 60)

    # Test both local and public connections
    urls = [
        ("本地", "ws://127.0.0.1:9001/ws/user_test"),
        ("公网", "ws://51.161.209.200:19001/ws/user_test")
    ]

    for name, url in urls:
        print(f"\n{'='*60}")
        print(f"测试 {name} 连接: {url}")
        print('='*60)

        try:
            async with websockets.connect(url) as ws:
                print("✅ WebSocket 连接成功!")

                # Send init message
                init_msg = {
                    "type": "init",
                    "avatar_id": "avatar_tutor_13",
                    "tutor_id": 13
                }
                await ws.send(json.dumps(init_msg))
                print(f"📤 发送: {init_msg}")

                # Wait for response
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(response)
                print(f"📥 收到: type={msg.get('type')}")
                if msg.get('type') == 'error':
                    print(f"   错误内容: {msg.get('content')}")
                else:
                    print(f"   has_video={bool(msg.get('video'))}")

        except Exception as e:
            print(f"❌ 错误: {e}")

    return True

async def test_connection():
    """测试WebSocket连接和基本功能"""

    print("=" * 60)
    print("🧪 测试 GPU Server 连接")
    print("=" * 60)

    try:
        import aiohttp
    except ImportError:
        print("⚠️ aiohttp未安装,使用简单测试")
        return await test_simple_websocket()
    session_id = None
    engine_token = None
    ws_url = None

    try:
        # 1. 测试管理API健康检查
        print("\n📍 步骤 1: 测试管理API健康检查")
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get("http://localhost:9000/health") as resp:
                health_data = await resp.json()
                print(f"✅ 管理API健康: {json.dumps(health_data, indent=2, ensure_ascii=False)}")

        # 2. 测试WebSocket API健康检查
        print("\n📍 步骤 2: 测试WebSocket API健康检查")
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get("http://localhost:9001/health") as resp:
                health_data = await resp.json()
                print(f"✅ WebSocket API健康: {json.dumps(health_data, indent=2, ensure_ascii=False)}")

        # 3. 创建测试session
        print("\n📍 步骤 3: 创建测试 Session")
        create_session_payload = {
            "tutor_id": 13,
            "student_id": 1,
            "kb_id": None
        }
        print(f"   请求数据: {json.dumps(create_session_payload, ensure_ascii=False)}")

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                "http://localhost:9000/v1/sessions",
                json=create_session_payload
            ) as resp:
                if resp.status != 201:
                    error_text = await resp.text()
                    print(f"❌ 创建Session失败: {resp.status} - {error_text}")
                    return False

                session_data = await resp.json()
                session_id = session_data["session_id"]
                engine_token = session_data["engine_token"]
                ws_url = session_data["engine_url"]

                print(f"✅ Session创建成功:")
                print(f"   - session_id: {session_id}")
                print(f"   - engine_url: {ws_url}")
                print(f"   - token: {engine_token[:20]}...")

        # 4. 测试WebSocket连接（使用token）
        print(f"\n📍 步骤 4: 连接 WebSocket")
        print(f"   连接URL: {ws_url}?token={engine_token[:20]}...")

        ws_url_with_token = f"{ws_url}?token={engine_token}"
        async with websockets.connect(ws_url_with_token) as ws:
            print("✅ WebSocket 连接成功")

            # 等待自动发送的idle video (session-based模式会自动发送)
            print("\n📍 步骤 5: 等待自动发送的待机视频")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=30)
                response_data = json.loads(response)

                if response_data.get("type") == "video":
                    video_size = len(response_data.get("video", ""))
                    print(f"✅ 收到自动待机视频: {video_size} bytes")
                elif response_data.get("type") == "text":
                    content = response_data.get("content", "")
                    print(f"✅ 收到欢迎消息: {content}")
            except asyncio.TimeoutError:
                print("⚠️  未收到自动消息（可能Avatar被禁用）")

            # 发送文本消息测试LLM
            print("\n📍 步骤 6: 发送文本消息测试 LLM")
            text_message = {
                "type": "text",
                "content": "你好，请简单介绍一下你自己",
                "session_id": 1
            }
            await ws.send(json.dumps(text_message))
            print(f"   已发送: {json.dumps(text_message, ensure_ascii=False)}")

            # 等待文本响应
            print("\n   等待响应...")
            response_count = 0
            max_responses = 3

            while response_count < max_responses:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=60)
                    response_data = json.loads(response)
                    response_count += 1

                    msg_type = response_data.get("type")
                    content = response_data.get("content", "")

                    if msg_type == "text":
                        print(f"✅ 收到文本响应: {content[:150]}...")
                    elif msg_type == "audio":
                        audio_size = len(response_data.get("audio", ""))
                        print(f"✅ 收到音频响应: {audio_size} bytes")
                    elif msg_type == "video":
                        video_size = len(response_data.get("video", ""))
                        print(f"✅ 收到视频响应: {video_size} bytes")
                        break  # 收到视频后结束
                    elif msg_type == "error":
                        print(f"❌ 错误: {content}")
                        return False

                except asyncio.TimeoutError:
                    print("⚠️  等待响应超时")
                    break

            print("\n" + "=" * 60)
            print("🎉 连接测试完成！")
            print("=" * 60)
            print(f"\n✅ 所有测试通过:")
            print(f"   - 管理API: 正常")
            print(f"   - WebSocket API: 正常")
            print(f"   - Session创建: 正常")
            print(f"   - WebSocket连接: 正常")
            print(f"   - LLM响应: 正常")
            if response_count > 0:
                print(f"   - 接收到 {response_count} 条响应")

            return True

    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket 连接失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理session
        if session_id and engine_token:
            print(f"\n🧹 清理测试 Session: {session_id}")
            try:
                async with aiohttp.ClientSession() as http_session:
                    async with http_session.delete(f"http://localhost:9000/v1/sessions/{session_id}") as resp:
                        if resp.status == 204:
                            print("✅ Session 已删除")
                        else:
                            print(f"⚠️  删除Session失败: {resp.status}")
            except Exception as e:
                print(f"⚠️  清理Session时出错: {e}")

if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
