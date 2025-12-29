#!/usr/bin/env python3
"""
WebSocket 连接测试脚本
测试 GPU Server 的 WebSocket 端点
"""
import asyncio
import websockets
import json
import sys

async def test_websocket_connection(uri, test_name, message):
    """测试 WebSocket 连接"""
    print(f"\n{'='*60}")
    print(f"🧪 测试: {test_name}")
    print(f"📍 URI: {uri}")
    print(f"{'='*60}")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket 连接成功！")

            # 接收欢迎消息
            welcome = await websocket.recv()
            print(f"\n📨 收到欢迎消息:")
            print(json.dumps(json.loads(welcome), indent=2, ensure_ascii=False))

            # 发送测试消息
            print(f"\n📤 发送测试消息:")
            print(json.dumps(message, indent=2, ensure_ascii=False))
            await websocket.send(json.dumps(message))

            # 接收响应
            response = await websocket.recv()
            print(f"\n📨 收到响应:")
            print(json.dumps(json.loads(response), indent=2, ensure_ascii=False))

            print(f"\n✅ 测试 '{test_name}' 通过！")
            return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False

async def main():
    """运行所有测试"""
    print("🚀 开始 WebSocket 连接测试")
    print("="*60)

    results = []

    # 测试 1: Session-based 模式 - /ws/ 路径
    test1 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/test_session_123?token=test_token",
        test_name="Session-based 模式 (/ws/)",
        message={
            "type": "text",
            "content": "测试消息 - session-based 模式"
        }
    )
    results.append(("Session-based (/ws/)", test1))

    await asyncio.sleep(1)

    # 测试 2: Session-based 模式 - /ws/ws/ 路径
    test2 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/ws/test_session_456?token=test_token",
        test_name="Session-based 模式 (/ws/ws/)",
        message={
            "type": "text",
            "content": "测试消息 - session-based 模式 (双路径)"
        }
    )
    results.append(("Session-based (/ws/ws/)", test2))

    await asyncio.sleep(1)

    # 测试 3: User-based 模式 - /ws/ 路径
    test3 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/user_6?token=test_token",
        test_name="User-based 模式 (/ws/)",
        message={
            "type": "text_webrtc",
            "content": "测试消息 - user-based 模式",
            "user_id": 6,
            "engine_session_id": "test-session-1",
            "avatar_id": "avatar_tutor_13"
        }
    )
    results.append(("User-based (/ws/)", test3))

    await asyncio.sleep(1)

    # 测试 4: User-based 模式 - /ws/ws/ 路径（后端代理使用）
    test4 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/ws/user_6?token=test_token",
        test_name="User-based 模式 (/ws/ws/) - 后端代理路径",
        message={
            "type": "text_webrtc",
            "content": "测试消息 - user-based 模式 (后端代理路径)",
            "user_id": 6,
            "engine_session_id": "test-session-2",
            "avatar_id": "avatar_tutor_13"
        }
    )
    results.append(("User-based (/ws/ws/)", test4))

    await asyncio.sleep(1)

    # 测试 5: User-based 模式 - 缺少 engine_session_id（应该返回错误）
    test5 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/ws/user_6?token=test_token",
        test_name="User-based 模式 - 缺少 engine_session_id（错误测试）",
        message={
            "type": "text_webrtc",
            "content": "测试消息 - 缺少 engine_session_id",
            "user_id": 6,
            "avatar_id": "avatar_tutor_13"
        }
    )
    results.append(("User-based 错误处理", test5))

    await asyncio.sleep(1)

    # 测试 6: WebRTC Offer（不需要 engine_session_id）
    test6 = await test_websocket_connection(
        uri="ws://localhost:19001/ws/ws/user_6?token=test_token",
        test_name="WebRTC Offer 消息",
        message={
            "type": "webrtc_offer",
            "sdp": "v=0\r\no=- 123456 2 IN IP4 127.0.0.1\r\n...",
            "user_id": 6,
            "avatar_id": "avatar_tutor_13"
        }
    )
    results.append(("WebRTC Offer", test6))

    # 打印测试总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {test_name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
