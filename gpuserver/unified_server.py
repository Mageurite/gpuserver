#!/usr/bin/env python3
"""
GPU Server - 统一启动脚本
同时运行管理 API 和 WebSocket 服务在同一进程中，共享会话管理器
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from management_api import app as management_app
from websocket_server import app as websocket_app

# 创建主应用
main_app = FastAPI(
    title="GPU Server",
    description="AI 推理引擎 - 管理 API 和 WebSocket 服务",
    version="1.0.0"
)

# 添加 CORS 中间件
main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载子应用
main_app.mount("/mgmt", management_app)
main_app.mount("/ws", websocket_app)

# 路径兼容层：为了保持向后兼容，添加 /v1/sessions 路由转发到 /mgmt/v1/sessions
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

@main_app.api_route("/v1/sessions", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@main_app.api_route("/v1/sessions/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_management_api(request: Request, path: str = ""):
    """
    路径兼容层：将 /v1/sessions 请求转发到 /mgmt/v1/sessions
    这样 Web Server 后端无需修改即可使用统一模式
    """
    # 构建目标 URL
    target_url = f"http://127.0.0.1:{settings.management_api_port}/mgmt/v1/sessions"
    if path:
        target_url += f"/{path}"
    
    # 添加查询参数
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    # 转发请求
    async with httpx.AsyncClient() as client:
        try:
            # 获取请求体
            body = await request.body()
            
            # 转发请求
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                content=body,
                timeout=30.0
            )
            
            # 返回响应
            # 对于 204 No Content，直接返回状态码，不包含内容
            if response.status_code == 204:
                from fastapi import Response
                return Response(status_code=204)
            
            # 对于其他响应，返回内容
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                try:
                    return JSONResponse(
                        content=response.json(),
                        status_code=response.status_code,
                        headers=dict(response.headers)
                    )
                except:
                    return JSONResponse(
                        content={"detail": response.text},
                        status_code=response.status_code
                    )
            else:
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse(
                    content=response.text,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except Exception as e:
            return JSONResponse(
                content={"detail": f"Proxy error: {str(e)}"},
                status_code=500
            )

# 根路径健康检查
@main_app.get("/")
async def root():
    return {
        "service": "GPU Server",
        "status": "running",
        "endpoints": {
            "management_api": "/mgmt",
            "websocket_api": "/ws",
            "docs": "/docs"
        }
    }

@main_app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "GPU Server"
    }


if __name__ == "__main__":
    # 设置统一模式环境变量
    import os
    os.environ["UNIFIED_MODE"] = "true"
    
    print("=" * 60)
    print("GPU Server - Unified Mode")
    print("=" * 60)
    print(f"\nManagement API: http://0.0.0.0:{settings.management_api_port}/mgmt")
    print(f"Management API (兼容): http://0.0.0.0:{settings.management_api_port}/v1/sessions")
    print(f"WebSocket API: ws://0.0.0.0:{settings.management_api_port}/ws/ws/{{session_id}}")
    print(f"API Docs: http://0.0.0.0:{settings.management_api_port}/docs")
    print("\n" + "=" * 60 + "\n")

    uvicorn.run(
        main_app,
        host=settings.management_api_host,
        port=settings.management_api_port,
        log_level="info"
    )
