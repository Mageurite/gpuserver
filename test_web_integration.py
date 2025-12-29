#!/usr/bin/env python3
"""
Web Server 集成测试脚本
快速验证 Web Server 与 GPU Server 的集成状态
"""
import requests
import json
import sys
from typing import Optional

# 配置
WEB_SERVER_URL = "http://localhost:8000"
GPU_SERVER_URL = "http://localhost:9000"

# 颜色输出
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def print_header(text: str):
    """打印标题"""
    print(f"\n{BLUE}{'='*60}{NC}")
    print(f"{BLUE}{text:^60}{NC}")
    print(f"{BLUE}{'='*60}{NC}\n")


def print_success(text: str):
    """打印成功信息"""
    print(f"{GREEN}✓ {text}{NC}")


def print_error(text: str):
    """打印错误信息"""
    print(f"{RED}✗ {text}{NC}")


def print_warning(text: str):
    """打印警告信息"""
    print(f"{YELLOW}⚠ {text}{NC}")


def print_info(text: str):
    """打印信息"""
    print(f"  {text}")


def test_gpu_server() -> bool:
    """测试 GPU Server 直连"""
    print_header("测试 GPU Server (直连)")

    try:
        response = requests.get(f"{GPU_SERVER_URL}/health", timeout=5)
        data = response.json()

        print_success("GPU Server 运行正常")
        print_info(f"状态: {data.get('status')}")
        print_info(f"服务: {data.get('service')}")
        return True
    except Exception as e:
        print_error(f"GPU Server 连接失败: {e}")
        print_warning("请确保 GPU Server 正在运行:")
        print_info("cd /workspace/gpuserver && ./start_mt.sh")
        return False


def test_web_server() -> bool:
    """测试 Web Server"""
    print_header("测试 Web Server")

    try:
        response = requests.get(f"{WEB_SERVER_URL}/health", timeout=5)
        data = response.json()

        print_success("Web Server 运行正常")
        print_info(f"状态: {data.get('status')}")
        return True
    except Exception as e:
        print_error(f"Web Server 连接失败: {e}")
        print_warning("请确保 Web Server 正在运行:")
        print_info("cd /workspace/virtual_tutor/app_backend")
        print_info("uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return False


def test_gpu_health_endpoint() -> bool:
    """测试 Web Server 的 GPU 健康检查接口"""
    print_header("测试 Web Server → GPU Server 连接")

    try:
        response = requests.get(f"{WEB_SERVER_URL}/api/student/gpu/health", timeout=5)

        if response.status_code == 404:
            print_error("GPU 健康检查接口不存在")
            print_warning("请按照集成指南添加路由:")
            print_info("参考: /workspace/WEB_SERVER_INTEGRATION_GUIDE.md")
            return False

        data = response.json()
        gpu_status = data.get('gpu_server', {})
        enabled = data.get('enabled', False)

        if gpu_status.get('status') == 'healthy':
            print_success("Web Server 成功连接到 GPU Server")
            print_info(f"GPU Server 状态: {gpu_status.get('status')}")
            print_info(f"GPU Server 启用: {enabled}")
            return True
        else:
            print_error("GPU Server 状态异常")
            print_info(f"错误: {gpu_status.get('error', 'Unknown')}")
            return False

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


def test_create_session(jwt_token: Optional[str] = None) -> bool:
    """测试创建会话"""
    print_header("测试创建会话")

    if not jwt_token:
        print_warning("未提供 JWT token，跳过会话创建测试")
        print_info("要测试完整流程，请先登录获取 token:")
        print_info(f"curl -X POST {WEB_SERVER_URL}/api/auth/login \\")
        print_info('  -H "Content-Type: application/json" \\')
        print_info('  -d \'{"email": "admin@example.com", "password": "admin123"}\'')
        return False

    try:
        response = requests.post(
            f"{WEB_SERVER_URL}/api/student/sessions",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json"
            },
            json={
                "tutor_id": 1,
                "kb_id": "test"
            },
            timeout=10
        )

        if response.status_code == 404:
            print_error("会话创建接口不存在")
            print_warning("请按照集成指南添加路由:")
            print_info("参考: /workspace/WEB_SERVER_INTEGRATION_GUIDE.md")
            return False

        if response.status_code == 401:
            print_error("JWT token 无效或已过期")
            return False

        response.raise_for_status()
        data = response.json()

        print_success("会话创建成功")
        print_info(f"Session ID: {data.get('session_id')}")
        print_info(f"Engine URL: {data.get('engine_url')}")
        print_info(f"Status: {data.get('status')}")

        return True

    except Exception as e:
        print_error(f"创建会话失败: {e}")
        return False


def test_direct_gpu_session() -> bool:
    """直接测试 GPU Server 创建会话"""
    print_header("测试 GPU Server 会话创建 (直连)")

    try:
        response = requests.post(
            f"{GPU_SERVER_URL}/v1/sessions",
            json={
                "tutor_id": 1,
                "student_id": 999,
                "kb_id": "test"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        print_success("GPU Server 会话创建成功")
        print_info(f"Session ID: {data.get('session_id')}")
        print_info(f"Engine URL: {data.get('engine_url')}")
        print_info(f"Token: {data.get('engine_token')[:20]}...")

        return True

    except Exception as e:
        print_error(f"创建会话失败: {e}")
        return False


def print_summary(results: dict):
    """打印测试总结"""
    print_header("测试总结")

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test_name, result in results.items():
        if result:
            print_success(test_name)
        else:
            print_error(test_name)

    print(f"\n{BLUE}总计: {passed}/{total} 通过{NC}\n")

    if passed == total:
        print_success("所有测试通过！集成成功！")
        print("\n下一步:")
        print_info("1. 前端可以开始集成 WebSocket")
        print_info("2. 参考: /workspace/WEB_SERVER_INTEGRATION_GUIDE.md")
        return 0
    else:
        print_error("部分测试失败，请检查配置")
        print("\n故障排除:")

        if not results.get("GPU Server 直连"):
            print_info("• 启动 GPU Server: cd /workspace/gpuserver && ./start_mt.sh")

        if not results.get("Web Server"):
            print_info("• 启动 Web Server: cd /workspace/virtual_tutor/app_backend")
            print_info("  uvicorn app.main:app --host 0.0.0.0 --port 8000")

        if not results.get("Web Server → GPU Server 连接"):
            print_info("• 检查 .env 配置: ENGINE_URL=http://localhost:9000")
            print_info("• 按照集成指南添加路由和客户端代码")

        return 1


def main():
    """主函数"""
    print(f"\n{BLUE}{'='*60}{NC}")
    print(f"{BLUE}{'Web Server 集成测试':^60}{NC}")
    print(f"{BLUE}{'='*60}{NC}")

    # 检查命令行参数
    jwt_token = None
    if len(sys.argv) > 1:
        jwt_token = sys.argv[1]

    # 运行测试
    results = {}

    # 1. 测试 GPU Server
    results["GPU Server 直连"] = test_gpu_server()

    # 2. 测试 Web Server
    results["Web Server"] = test_web_server()

    # 3. 测试 GPU Server 会话创建（直连）
    if results["GPU Server 直连"]:
        results["GPU Server 会话创建"] = test_direct_gpu_session()

    # 4. 测试 Web Server → GPU Server 连接
    if results["Web Server"]:
        results["Web Server → GPU Server 连接"] = test_gpu_health_endpoint()

    # 5. 测试创建会话（需要 JWT）
    if results.get("Web Server → GPU Server 连接"):
        results["创建会话 (需要 JWT)"] = test_create_session(jwt_token)

    # 打印总结
    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
