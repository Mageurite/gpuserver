# WebRTC 连接问题排查记录

## 当前状态 (2026-01-06)

### 问题描述
前端与GPU服务器的WebRTC连接失败，ICE连接状态为"failed"，视频无法播放。

### 已完成的修复

#### 1. ✅ 修复了ICE Candidate发送机制
**问题**: GPU服务器没有发送ICE candidates给前端
**原因**: aiortc库不支持`onicecandidate`事件，需要从SDP中提取candidates
**解决方案**:
- 添加了`_send_ice_candidates_from_sdp()`方法 (`webrtc_streamer.py:213-243`)
- 从SDP answer中提取ICE candidates并通过WebSocket发送给前端
- 前端现在能收到4个GPU Server的ICE candidates

**代码位置**: `/workspace/gpuserver/webrtc_streamer.py`

#### 2. ✅ 添加了TURN服务器配置
**问题**: aiortc使用随机端口（如44925），不在配置的端口范围（10110-10115）内
**原因**: aiortc不支持限制端口范围，需要使用TURN服务器中继流量
**解决方案**:
- 添加TURN服务器配置到`config.py` (行78-83)
- 更新WebRTC配置API端点 (`management_api.py:430-434`)
- 更新RTCPeerConnection创建逻辑 (`webrtc_streamer.py:167-175`)

**TURN服务器信息**:
- URL: `turn:51.161.209.200:10110`
- 用户名: `vtuser`
- 密码: `vtpass`
- 状态: 运行中 (PID: 1822768)

#### 3. ✅ 修复了前端ICE Candidate处理
**问题**: 前端收到candidates但无法添加到RTCPeerConnection
**解决方案**: 前端现在正确缓存candidates，等待远程描述设置后再添加

### 当前问题

#### 🔴 ICE连接仍然失败

**症状**:
- ✅ GPU服务器发送4个ICE candidates
- ✅ 前端成功添加candidates
- ✅ 形成4个candidate pairs（状态: in-progress）
- ❌ 所有pairs最终失败，没有nominated pair
- ❌ ICE连接状态变为"failed"

**观察到的Candidates**:
```
GPU Server发送:
1. 51.161.209.200:44925 (typ host)
2. 49.213.134.9:44925 (typ srflx)
3. 51.161.209.200:44925 (typ host) - 音频
4. 49.213.134.9:44925 (typ srflx) - 音频

前端发送:
- 多个 typ host (本地)
- 多个 typ srflx (STUN反射)
```

**关键发现**:
1. ❌ **没有看到 `typ relay` candidates** - TURN服务器可能没有生效
2. ❌ **端口44925不在配置范围内** (应该是10110-10115)
3. ⚠️ **Candidate pairs状态一直是"in-progress"**，从未变为"succeeded"

### 待验证的问题

#### 1. TURN服务器配置是否生效？
**检查方法**:
```bash
# 查看日志，应该看到TURN服务器信息
tail -f /workspace/gpuserver/logs/websocket_server_console.log | grep -E "TURN|ICE servers"
```

**预期输出**:
```
WebRTC peer connection created for session user_2
  STUN server: stun:stun.l.google.com:19302
  TURN server: turn:51.161.209.200:10110
  TURN username: vtuser
  ICE servers count: 2
```

**当前输出**:
```
WebRTC peer connection created for session user_2 with STUN: stun:stun.l.google.com:19302
```
⚠️ 只提到STUN，没有TURN信息

#### 2. 端口44925是否可访问？
**检查方法**:
```bash
# 检查端口监听状态
ss -tulnp | grep 44925

# 检查防火墙规则
iptables -L -n | grep 44925
```

#### 3. TURN服务器是否正常工作？
**检查方法**:
```bash
# 检查TURN服务器状态
ps aux | grep turnserver

# 检查TURN服务器配置
cat /etc/turnserver.conf | grep -E "listening-port|external-ip|relay-ip"
```

**当前配置**:
```
listening-port=10110
external-ip=51.161.209.200/172.17.0.3
relay-ip=172.17.0.3
user=vtuser:vtpass
realm=gpu-turn
```

### 下一步行动

#### 优先级1: 验证TURN服务器配置
1. 刷新前端页面
2. 检查GPU服务器日志，确认TURN服务器配置已加载
3. 查看前端日志，确认是否收到`typ relay` candidates

#### 优先级2: 测试TURN服务器连通性
如果TURN配置正确但仍无relay candidates，需要测试TURN服务器：
```bash
# 使用turnutils测试TURN服务器
turnutils-uclient -v -u vtuser -w vtpass 51.161.209.200 -p 10110
```

#### 优先级3: 考虑替代方案
如果TURN服务器无法工作，考虑：
1. 使用公共TURN服务器（如Twilio, Xirsys）
2. 配置aiortc使用固定端口范围（如果可能）
3. 使用端口转发/代理

### 网络架构

```
前端 (103.120.10.202)
    |
    | WebSocket: ws://51.161.130.234:19001
    | WebRTC: 尝试连接到 51.161.209.200:44925
    |
    v
FRP隧道 (51.161.130.234:19001 -> GPU Server:9001)
    |
    v
GPU Server (172.17.0.3 in Docker)
    |
    +-- WebSocket Server: 0.0.0.0:9001
    +-- Management API: 0.0.0.0:9000
    +-- aiortc: 随机端口 (如44925)
    |
    v
TURN Server (51.161.209.200:10110)
    - 应该中继流量，但可能未生效
```

### 配置文件位置

- **WebRTC配置**: `/workspace/gpuserver/config.py` (行69-83)
- **WebRTC Streamer**: `/workspace/gpuserver/webrtc_streamer.py`
- **Management API**: `/workspace/gpuserver/api/management_api.py`
- **WebSocket Server**: `/workspace/gpuserver/api/websocket_server.py`
- **TURN配置**: `/etc/turnserver.conf`

### 日志文件位置

- **WebSocket Server**: `/workspace/gpuserver/logs/websocket_server_console.log`
- **Management API**: `/workspace/gpuserver/logs/management_api_console.log`
- **WebSocket详细日志**: `/workspace/gpuserver/logs/websocket_server.log`

### 服务器状态

```bash
# 当前运行的服务
WebSocket Server: PID 2255896 (端口9001)
Management API: PID 2257301 (端口9000)
TURN Server: PID 1822768 (端口10110)

# 重启服务
cd /workspace/gpuserver
kill <PID>
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/websocket_server.py > logs/websocket_server_console.log 2>&1 &
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/management_api.py > logs/management_api_console.log 2>&1 &
```

### 测试命令

```bash
# 测试WebRTC配置端点
curl http://localhost:9000/api/webrtc/config | python3 -m json.tool

# 测试健康检查
curl http://localhost:9000/health

# 查看实时日志
tail -f /workspace/gpuserver/logs/websocket_server_console.log

# 查看端口使用情况
ss -tulnp | grep -E "(9000|9001|10110|44925)"
```

### 参考资料

- **aiortc文档**: https://aiortc.readthedocs.io/
- **WebRTC ICE**: https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Connectivity
- **TURN服务器**: https://github.com/coturn/coturn

### 更新历史

- **2026-01-06 18:50**: 添加TURN服务器配置，增加详细日志
- **2026-01-06 17:30**: 修复ICE candidate发送机制
- **2026-01-06 17:00**: 添加 `/api/webrtc/config` 端点别名
- **2026-01-06 16:30**: 修复ICE candidate处理逻辑
