# 🚀 部署检查清单

## GPU Server 部署

### 环境准备
- [ ] 安装 conda 环境 (mt 或 rag)
- [ ] 安装 Python 依赖: `pip install -r requirements.txt`
- [ ] 配置 `.env` 文件
- [ ] 确认 Ollama 运行: `curl http://127.0.0.1:11434/api/tags`
- [ ] 下载 LLM 模型: `ollama pull mistral-nemo:12b-instruct-2407-fp16`

### 启动服务
- [ ] 启动 GPU Server: `cd /workspace/gpuserver && ./start_mt.sh`
- [ ] 验证健康检查: `curl http://localhost:9000/health`
- [ ] 测试创建会话: `curl -X POST http://localhost:9000/v1/sessions -H "Content-Type: application/json" -d '{"tutor_id": 1, "student_id": 123}'`

### 功能验证
- [ ] LLM 响应正常
- [ ] ASR/TTS 功能正常
- [ ] 视频生成功能正常（如启用）
- [ ] WebSocket 连接正常

---

## Web Server 部署

### 代码集成
- [ ] 添加 `ENGINE_URL` 到 `.env`
- [ ] 添加 `ENGINE_ENABLED=true` 到 `.env`
- [ ] 更新 `app/core/config.py` 添加 GPU Server 配置
- [ ] 创建 `app/services/gpu_client.py`
- [ ] 创建 `app/api/routes_sessions.py`
- [ ] 在 `app/main.py` 注册新路由
- [ ] 安装依赖: `pip install httpx`

### 启动服务
- [ ] 启动 Web Server: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] 验证健康检查: `curl http://localhost:8000/health`
- [ ] 测试 GPU 健康检查: `curl http://localhost:8000/api/student/gpu/health`

### 功能验证
- [ ] 用户认证正常
- [ ] GPU Server 连接正常
- [ ] 会话创建接口正常
- [ ] 会话查询接口正常
- [ ] 会话删除接口正常

---

## 前端部署

### 代码集成
- [ ] 创建 `services/aiService.js`
- [ ] 创建 `components/AIChat.jsx`
- [ ] 配置 API Base URL
- [ ] 实现 WebSocket 连接逻辑
- [ ] 实现消息发送/接收
- [ ] 实现视频显示（如需要）

### 功能验证
- [ ] 登录功能正常
- [ ] 创建会话成功
- [ ] WebSocket 连接成功
- [ ] 发送文本消息正常
- [ ] 接收 AI 响应正常
- [ ] 视频显示正常（如启用）
- [ ] 音频功能正常（如启用）

---

## 集成测试

### 自动化测试
- [ ] 运行集成测试脚本: `python3 /workspace/test_web_integration.py`
- [ ] 所有测试通过

### 手动测试
- [ ] GPU Server 健康检查
- [ ] Web Server 健康检查
- [ ] 创建会话（通过 Web Server）
- [ ] WebSocket 连接
- [ ] 发送文本消息
- [ ] 接收 AI 响应
- [ ] 视频生成（如启用）
- [ ] 会话结束

### 端到端测试
- [ ] 用户登录
- [ ] 选择导师
- [ ] 创建对话会话
- [ ] 发送多轮对话
- [ ] 接收 AI 响应
- [ ] 视频正常显示
- [ ] 会话正常结束

---

## 性能测试

### 负载测试
- [ ] 单会话性能测试
- [ ] 多会话并发测试
- [ ] 长时间运行稳定性测试
- [ ] 内存使用监控
- [ ] GPU 使用监控

### 响应时间
- [ ] 会话创建 < 2s
- [ ] 文本响应 < 5s
- [ ] 视频生成 < 10s
- [ ] WebSocket 延迟 < 100ms

---

## 安全检查

### 认证授权
- [ ] JWT token 验证正常
- [ ] 会话 token 验证正常
- [ ] 用户权限隔离正常
- [ ] 跨域配置正确

### 数据安全
- [ ] 敏感信息不在日志中
- [ ] 数据库连接安全
- [ ] API 密钥安全存储
- [ ] HTTPS 配置（生产环境）

---

## 监控和日志

### 日志配置
- [ ] GPU Server 日志: `/workspace/gpuserver/logs/unified_server.log`
- [ ] Web Server 日志配置
- [ ] 前端错误日志配置
- [ ] 日志轮转配置

### 监控指标
- [ ] 服务健康状态
- [ ] 活跃会话数
- [ ] API 响应时间
- [ ] 错误率
- [ ] GPU 使用率
- [ ] 内存使用率

---

## 文档检查

### 技术文档
- [ ] API 文档完整
- [ ] 集成指南完整
- [ ] 部署文档完整
- [ ] 故障排除文档完整

### 用户文档
- [ ] 使用说明
- [ ] 常见问题
- [ ] 联系方式

---

## 生产环境配置

### 环境变量
- [ ] 更新 `ENGINE_URL` 为生产地址
- [ ] 配置 `SECRET_KEY`
- [ ] 配置数据库连接
- [ ] 配置 CORS 域名
- [ ] 配置日志级别

### 服务配置
- [ ] 配置进程管理 (systemd/supervisor)
- [ ] 配置反向代理 (nginx)
- [ ] 配置 SSL 证书
- [ ] 配置防火墙规则
- [ ] 配置备份策略

### 性能优化
- [ ] 启用 gzip 压缩
- [ ] 配置缓存策略
- [ ] 优化数据库索引
- [ ] 配置 CDN（如需要）

---

## 回滚计划

### 备份
- [ ] 代码备份
- [ ] 数据库备份
- [ ] 配置文件备份
- [ ] 模型文件备份

### 回滚步骤
- [ ] 停止新服务
- [ ] 恢复旧版本代码
- [ ] 恢复数据库
- [ ] 恢复配置文件
- [ ] 重启服务
- [ ] 验证功能

---

## 上线后验证

### 功能验证
- [ ] 所有核心功能正常
- [ ] 性能指标达标
- [ ] 无严重错误日志
- [ ] 用户反馈正常

### 监控验证
- [ ] 监控系统正常
- [ ] 告警配置正常
- [ ] 日志收集正常
- [ ] 指标上报正常

---

## 快速命令参考

### 启动服务
```bash
# GPU Server
cd /workspace/gpuserver && ./start_mt.sh

# Web Server
cd /workspace/virtual_tutor/app_backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
cd /workspace/virtual_tutor/frontend
npm start
```

### 测试命令
```bash
# 集成测试
python3 /workspace/test_web_integration.py

# GPU Server 健康检查
curl http://localhost:9000/health

# Web Server 健康检查
curl http://localhost:8000/health

# GPU 连接测试
curl http://localhost:8000/api/student/gpu/health
```

### 查看日志
```bash
# GPU Server 日志
tail -f /workspace/gpuserver/logs/unified_server.log

# Web Server 日志
# (根据实际配置)

# 查看进程
ps aux | grep -E "unified_server|uvicorn"
```

### 停止服务
```bash
# GPU Server
cd /workspace/gpuserver && ./stop.sh

# Web Server
pkill -f "uvicorn app.main:app"
```

---

**最后更新**: 2025-12-28
**版本**: 1.0
