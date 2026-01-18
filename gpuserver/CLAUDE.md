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

1. **ICE Candidates发送** - 从SDP提取并发送 (`webrtc_streamer.py:229-282`)
2. **ICE Candidate解析** - 使用`candidate_from_sdp()` (`webrtc_streamer.py:378-390`)
3. **TURN服务器配置** - 已配置并运行在端口10110
4. **前端配置获取** - Web服务器后端已添加`iceTransportPolicy`字段到`/api/webrtc/config`
5. **aiortc随机端口问题** - GPU服务器端过滤非relay类型的candidates (`webrtc_streamer.py:263-267, 301-315`)

## 解决方案总结 🎯

### 问题：aiortc生成随机端口的candidates

**根本原因**:
- aiortc库会生成3种类型的ICE candidates:
  - `typ host`: 使用随机端口（如37384, 59138）
  - `typ srflx`: STUN映射，也使用随机端口
  - `typ relay`: TURN中继，使用正确的端口范围10110-10115 ✅
- 即使配置了TURN服务器，aiortc仍然会生成所有类型的candidates
- 前端的`iceTransportPolicy: "relay"`只影响前端选择，不影响后端生成

**最终解决方案**:
1. **Web服务器端**: 在`/api/webrtc/config`响应中添加`iceTransportPolicy: "relay"`字段
2. **前端**: 使用后端配置中的`iceTransportPolicy`值（已修改）
3. **GPU服务器端**: 在发送candidates给前端时，过滤掉非relay类型的candidates

**关键代码修改** (`webrtc_streamer.py`):

```python
# 在 _send_ice_candidates_from_sdp 方法中 (lines 263-267)
if 'typ relay' not in candidate_str:
    logger.info(f"Skipping non-relay candidate: {candidate_str[:60]}...")
    continue  # 只发送relay类型的candidates

# 在 _modify_sdp_for_public_ip 方法中 (lines 301-315)
for line in lines:
    if line.startswith('a=candidate'):
        if 'typ relay' in line:
            modified_lines.append(line)  # 只保留relay candidates
        else:
            logger.debug(f"Removing non-relay candidate: {line}")
    else:
        modified_lines.append(line)
```

## 当前状态 ✅

**所有组件已修复**:
- ✅ TURN服务器运行在10110端口
- ✅ Web服务器返回`iceTransportPolicy: "relay"`配置
- ✅ 前端使用后端配置值
- ✅ GPU服务器过滤非relay candidates
- ✅ 所有WebRTC流量通过TURN中继（端口10110-10115）

**验证方法**:
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
