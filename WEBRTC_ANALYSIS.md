# WebRTC 连接失败根本原因分析

## 📊 问题现象
WebRTC 连接始终无法建立成功，表现为：
- **ICE 连接失败**（ICE Connection State: "failed"）
- 信令（WebSocket）建立成功，但媒体连接失败
- 浏览器控制台无法看到视频流

---

## 🔴 **核心问题分析**

### **问题 1: 严重的架构矛盾** ⚠️ **最关键**

您的系统存在**三种互相冲突的 WebRTC 实现方案**：

#### 方案A: STUN/TURN 服务器（当前在 webrtc_streamer.py 中）
```python
# webrtc_streamer.py 第140行
ice_servers = [
    {"urls": "stun:stun.l.google.com:19302"},
    {
        "urls": settings.turn_server,  # 需要部署 coturn
        "username": settings.turn_username,
        "credential": settings.turn_credential
    }
]
```

**问题**: 
- 需要部署完整的 TURN 服务器（coturn）
- 配置文件中 `settings.turn_server` 可能为 None 或格式错误
- 浏览器和后端配置不一致

#### 方案B: 无 ICE 直接端口映射（WEBRTC_PORT_MAPPING.md）
```javascript
// 前端应该这样做
const peerConnection = new RTCPeerConnection({
  iceServers: []  // 不使用 STUN/TURN
});
```

**问题**:
- 文档要求不使用 ICE，但代码实际在配置 STUN/TURN
- 这会导致 ICE candidate 生成失败

#### 方案C: 已弃用的配置

结合以上，系统处于**配置混乱状态**。

---

### **问题 2: 依赖环境崩溃**

#### server.log 中的错误：
```
ModuleNotFoundError: No module named 'uvicorn'
```

✅ **影响**: GPU Server 无法启动！

#### unified_server.log 中的错误：
```
ERROR - Error loading Whisper model: Numpy is not available
UserWarning: Failed to initialize NumPy: _ARRAY_API not found
```

**原因**: `NumPy 2.x` 与 PyTorch/Whisper 的兼容性问题

✅ **影响**: ASR 模块加载失败（降级到 Mock 模式）

#### frpc.log 中的错误：
```
[E] [proxy/proxy.go:204] [gpu_websocket] connect to local service [127.0.0.1:9001]
error: dial tcp 127.0.0.1:9001: connect: connection refused
```

✅ **影响**: FRP 无法连接到本地 WebSocket 服务，因为端口配置错误或服务未启动

---

### **问题 3: 端口配置混乱**

#### frpc.toml 中的端口映射：
```toml
# 这个配置是 WRONG！
[[proxies]]
name = "gpu_server_api"
type = "tcp"
localPort = 9000      # GPU Server API 在 9000
remotePort = 10110    # 映射到公网 10110 ✅

# 但还有这个
[[proxies]]
name = "turn_server"
type = "udp"
localPort = 10110     # ❌ TURN 应该在不同端口！
remotePort = 10110
```

**问题分析**:
```
GPU Server 实际上：
- 管理 API: 127.0.0.1:9000   ✅
- WebSocket: 127.0.0.1:9001  ✅ （从 config.py 看）
- WebRTC 媒体: 10111-10115   ❌ （未绑定？）

FRP 配置期望：
- TCP 9000 -> 公网 10110     ✅
- UDP 10110 (TURN) -> 10110  ⚠️ （这不对）
- UDP 10111-10115 -> ...     ❌ （配置不完整）
```

**实际影响**:
1. FRP 尝试连接 `127.0.0.1:9001` 失败
2. 前端无法正确建立信令连接
3. 即使信令成功，WebRTC 媒体端口绑定状态不明确

---

### **问题 4: 配置文件未正确读取或初始化**

#### config.py 中的 WebRTC 配置（第 50+ 行）：
需要查看以下配置是否正确：
```python
webrtc_public_ip: str = "51.161.209.200"     # ✅ 正确
turn_server: str = ???                        # ❌ 未知（可能为 None）
turn_username: str = ???                      # ❌ 未知
turn_credential: str = ???                    # ❌ 未知
```

---

### **问题 5: 前端-后端 ICE 配置不匹配**

#### 后端 (webrtc_streamer.py)：
```python
# 使用 STUN + TURN
ice_servers = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": settings.turn_server, ...}
]
```

#### 前端 (test_webrtc.html)：
```javascript
// 可能也在使用相同的配置？还是没有配置？
// 需要确认前端中的 RTCPeerConnection 初始化代码
```

**问题**: 如果前后端 ICE 配置不一致，会导致 candidate 不兼容。

---

## 📋 **问题优先级排序**

| 优先级 | 问题 | 影响 | 修复时间 |
|--------|------|------|---------|
| 🔴 P0 | `uvicorn` 模块缺失 | **GPU Server 无法启动** | 5分钟 |
| 🔴 P0 | 端口配置错误 (9001 vs 9000) | **WebSocket 信令无法建立** | 10分钟 |
| 🔴 P0 | 架构方案矛盾（3个冲突方案） | **ICE 配置混乱** | 30分钟 |
| 🟠 P1 | NumPy 2.x 兼容性问题 | **ASR 模块功能降级** | 20分钟 |
| 🟠 P1 | TURN 服务器配置缺失 | **P2P 失败时无备选方案** | 30分钟 |
| 🟡 P2 | 前端 ICE 配置不确定 | **可能的 candidate 不兼容** | 15分钟 |

---

## ✅ **修复方案（按优先级）**

### **第一步: 安装缺失的依赖** (5分钟)
```bash
cd /workspace/gpuserver
source /workspace/conda_envs/backend/bin/activate
pip install uvicorn
```

### **第二步: 修正 FRP 配置** (10分钟)

**编辑** `/workspace/frps/frp_0.66.0_linux_amd64/frpc.toml`

当前错误配置：
```toml
[[proxies]]
name = "gpu_server_api"
type = "tcp"
localPort = 9000         # ❌ 错
localPort = 9001         # ✅ 改成这个
remotePort = 10110
```

**为什么**: config.py 中 WebSocket 服务在 9001，而 Management API 在 9000
- Management API (9000) → HTTP（不需要暴露到公网，只需本地）
- WebSocket (9001) → 信令（需要暴露到公网）

### **第三步: 选择一个 WebRTC 方案并坚持** (30分钟)

#### **推荐方案: 使用 STUN + TURN（最稳定）**

**理由**:
- 不依赖固定的端口映射
- 在 NAT 环保下更可靠
- 部署一次，配置一次

**步骤**:

1. **部署 TURN 服务器**（在公网服务器上）
```bash
# 在 51.161.209.200 上执行
sudo apt-get update
sudo apt-get install coturn
```

2. **配置 coturn** （/etc/turnserver.conf）
```ini
listening-port=3478
tls-listening-port=5349
external-ip=51.161.209.200
realm=avatar-tutor.com
user=webrtc:your_secure_password_here
log-file=/var/log/turnserver.log
```

3. **更新后端配置** (config.py)
```python
# WebRTC TURN 配置
turn_server: str = "turn:51.161.209.200:3478?transport=udp"
turn_username: str = "webrtc"
turn_credential: str = "your_secure_password_here"
```

4. **验证前端配置** (test_webrtc.html)
```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    {
      urls: 'turn:51.161.209.200:3478?transport=udp',
      username: 'webrtc',
      credential: 'your_secure_password_here'
    }
  ]
});
```

### **第四步: 修复 NumPy 兼容性** (20分钟)

```bash
cd /workspace/gpuserver
source /workspace/conda_envs/backend/bin/activate

# 降级 NumPy 到 1.x
pip install 'numpy<2'

# 重新启动 GPU Server
bash start_server.sh
```

### **第五步: 验证 WebRTC 连接**

```bash
# 1. 检查 GPU Server 是否运行
curl http://localhost:9000/health

# 2. 检查 WebSocket 是否运行
# （通过 test_webrtc.html 测试）

# 3. 检查 FRP 连接
ps aux | grep frpc
tail -20 /workspace/gpuserver/logs/frpc.log

# 4. 检查端口绑定
netstat -tuln | grep -E '9000|9001|10110|10111'
```

---

## 🎯 **立即行动清单**

```
[ ] 1. 安装 uvicorn: pip install uvicorn
[ ] 2. 修改 frpc.toml: 9000 → 9001
[ ] 3. 修改 config.py: 添加 TURN 服务器配置
[ ] 4. 验证 test_webrtc.html: 确认 ICE 配置一致
[ ] 5. 部署 coturn 服务器（可选，但推荐）
[ ] 6. 修复 NumPy 兼容性: pip install 'numpy<2'
[ ] 7. 重启所有服务: bash start_webrtc.sh
[ ] 8. 测试 WebRTC 连接
```

---

## 📌 **附录: 快速诊断命令**

```bash
# 检查各个服务状态
echo "=== GPU Server ===" && curl -s http://localhost:9000/health || echo "❌ 无法连接"
echo "=== FRP 状态 ===" && ps aux | grep frpc | grep -v grep || echo "❌ FRP 未运行"
echo "=== WebSocket ===" && nc -zv localhost 9001 || echo "❌ WebSocket 不可用"
echo "=== 端口映射 ===" && netstat -tuln | grep -E '9000|9001|10110|10111' || echo "❌ 端口未绑定"
```

---

## 🔗 **相关文件位置**

- 配置文件: [/workspace/gpuserver/config.py](../gpuserver/config.py)
- FRP 配置: [/workspace/frps/frp_0.66.0_linux_amd64/frpc.toml](../frps/frp_0.66.0_linux_amd64/frpc.toml)
- WebRTC 后端: [/workspace/gpuserver/webrtc_streamer.py](../gpuserver/webrtc_streamer.py)
- WebRTC 前端: [/workspace/test_webrtc.html](../test_webrtc.html)
- GPU Server 统一启动: [/workspace/gpuserver/unified_server.py](../gpuserver/unified_server.py)
