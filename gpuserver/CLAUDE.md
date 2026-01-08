# GPU Server - WebRTC Avatar 项目

## 服务器说明
**当前服务器**: GPU Server (49.213.134.9:32537)
- 运行AI Avatar (MuseTalk)
- 提供WebRTC视频流
- 映射到公网 (51.161.209.200)

## 核心服务

| 服务 | 端口 | 状态 | PID |
|------|------|------|-----|
| WebSocket Server | 9001 | ✅ | 2267130 |
| Management API | 9000 | ✅ | 2284588 |
| TURN Server | 10110 | ✅ | 1822768 |

## 配置

### 网络配置

**GPU服务器**: 49.213.134.9:32537 (本机)
**公网IP**: 51.161.209.200 (FRP映射)
**端口映射**: 仅5个UDP端口 (10110-10115) 被映射到公网

### WebRTC配置 (`config.py`)
```python
webrtc_stun_server = "stun:stun.l.google.com:19302"
webrtc_turn_server = "turn:51.161.209.200:10110"
webrtc_turn_username = "vtuser"
webrtc_turn_password = "vtpass"
webrtc_public_ip = "51.161.209.200"  # FRP映射的公网IP
webrtc_port_min = 10110  # ⚠️ 仅这5个端口被映射到公网
webrtc_port_max = 10115
```

### TURN服务器 (`/etc/turnserver.conf`)
```ini
listening-port=10110
external-ip=51.161.209.200/172.17.0.3
min-port=10111
max-port=10115
user=vtuser:vtpass
realm=gpu-turn
```

## 已解决的问题 ✅

1. **ICE Candidates发送** - 从SDP提取并发送 (`webrtc_streamer.py:213-243`)
2. **ICE Candidate解析** - 使用`candidate_from_sdp()` (`webrtc_streamer.py:362-370`)
3. **TURN服务器配置** - 已配置并运行

## 当前问题 ❌

### 核心问题：WebRTC连接失败

**原因**: 前端硬编码 `iceTransportPolicy: "all"`，忽略后端的 `"relay"` 配置

**证据**:
```javascript
// 后端返回: iceTransportPolicy: "relay" ✅
// 前端使用: iceTransportPolicy: "all"  ❌ (bundle.js:85631)
```

**结果**:
- aiortc使用随机端口 (43472, 37772等)
- 这些端口不在10110-10115范围内
- ⚠️ FRP只映射了5个UDP端口到公网，其他端口无法访问
- TURN服务器虽然工作但未被使用

## 解决方案 🎯

### 必须修改前端代码（在Web服务器上）

**查找文件**:
```bash
cd /path/to/frontend
grep -rn "iceTransportPolicy" src/ --include="*.js" --include="*.jsx"
grep -rn "RTCPeerConnection" src/ --include="*.js" --include="*.jsx"
```

**修改代码**:
```javascript
// 修改前 ❌
const rtcConfig = {
  iceServers: config.iceServers,
  iceTransportPolicy: 'all',  // 硬编码
  sdpSemantics: config.sdpSemantics || 'unified-plan'
};

// 修改后 ✅
const rtcConfig = {
  iceServers: config.iceServers,
  iceTransportPolicy: config.iceTransportPolicy || 'all',  // 使用后端配置
  sdpSemantics: config.sdpSemantics || 'unified-plan'
};
```

**重新打包**:
```bash
npm run build
```

**验证成功标志**:
- 前端日志显示: `iceTransportPolicy: "relay"`
- 出现 `typ relay` 类型的candidates
- ICE连接状态: `"connected"`

## 服务管理

### 启动
```bash
cd /workspace/gpuserver
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/websocket_server.py > logs/websocket_server_console.log 2>&1 &
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/management_api.py > logs/management_api_console.log 2>&1 &
```

### 停止
```bash
ps aux | grep -E "(management_api|websocket_server)" | grep python | grep -v grep
kill <PID>
```

### 查看日志
```bash
tail -f /workspace/gpuserver/logs/websocket_server_console.log
tail -f /workspace/gpuserver/logs/management_api_console.log
tail -f /var/log/turnserver.log
```

### 健康检查
```bash
curl http://localhost:9000/health
curl http://localhost:9000/api/webrtc/config | python3 -m json.tool
ss -tulnp | grep -E "(9000|9001|10110)"
```

## 待办事项

- [ ] 在Web服务器上修改前端代码
- [ ] 重新打包前端
- [ ] 验证TURN中继工作
- [ ] 切换回自建TURN服务器 (当前使用公共TURN测试)

## 文件位置

```
/workspace/gpuserver/          # GPU服务器代码（本服务器）
├── api/
│   ├── management_api.py
│   └── websocket_server.py
├── webrtc_streamer.py
├── config.py
├── logs/
└── CLAUDE.md (本文档)

/workspace/try/frontend/       # ⚠️ 参考代码，不能修改！
                               # 实际前端在Web服务器上（另一台服务器）
```

## 重要说明

⚠️ **服务器架构**
- **GPU服务器** (本机): 49.213.134.9:32537
- **公网IP**: 51.161.209.200 (映射)
- **端口限制**: 仅5个UDP端口 (10110-10115) 被映射到公网
- **Web服务器**: 另一台服务器，运行前端，通过FRP连接

⚠️ **前端代码不在本服务器上**
- `/workspace/try/frontend/` 仅供参考，不是实际使用的前端
- 实际前端在Web服务器上
- **前端修改需要在Web服务器上进行**

---
**更新**: 2026-01-06 19:50
**GPU服务器**: 49.213.134.9:32537 (SSH: `ssh new`)
**公网IP**: 51.161.209.200 (FRP映射，仅5个UDP端口)
**状态**: 🟡 等待Web服务器上修改前端代码
