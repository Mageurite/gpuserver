# WebRTC 端口映射配置（无需 STUN）

## 架构说明

由于 GPU Server 位于内网且已有公网端口映射，**我们不使用 STUN 服务器**，而是直接利用 FRP 的端口映射。

## 端口映射关系

```
GPU Server (内网)              FRP              公网服务器
-----------                    ---              -----------
localhost:9000    --TCP-->  端口映射  -->  51.161.209.200:10110  (WebSocket 信令)
localhost:10111   --UDP-->  端口映射  -->  51.161.209.200:10111  (WebRTC 媒体)
localhost:10112   --UDP-->  端口映射  -->  51.161.209.200:10112  (WebRTC 媒体)
localhost:10113   --UDP-->  端口映射  -->  51.161.209.200:10113  (WebRTC 媒体)
localhost:10114   --UDP-->  端口映射  -->  51.161.209.200:10114  (WebRTC 媒体)
localhost:10115   --UDP-->  端口映射  -->  51.161.209.200:10115  (WebRTC 媒体)
```

## FRP 配置已完成 ✅

当前 [frpc.toml](file:///workspace/frps/frp_0.66.0_linux_amd64/frpc.toml) 配置：

```toml
# WebSocket 信令通道
[[proxies]]
name = "gpu_server_api"
type = "tcp"
localPort = 9000
remotePort = 10110

# WebRTC 媒体端口（UDP）
[[proxies]]
name = "udp_10111"
type = "udp"
localPort = 10111
remotePort = 10111

[[proxies]]
name = "udp_10112"
type = "udp"
localPort = 10112
remotePort = 10112

# ... 10113, 10114, 10115 同样配置
```

✅ **无需修改 FRP 配置**，UDP 端口已映射。

## GPU Server 配置

[config.py](file:///workspace/gpuserver/config.py) 中已添加：

```python
# WebRTC 配置
webrtc_public_ip: str = "51.161.209.200"     # 公网 IP
webrtc_port_min: int = 10111                  # 媒体端口范围
webrtc_port_max: int = 10115
```

## 前端配置（重要变化）

### ❌ 旧配置（使用 STUN）

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' }  // 不需要了！
  ]
});
```

### ✅ 新配置（使用端口映射）

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: []  // 空数组，不使用 STUN/TURN
});

// 手动添加 ICE candidate（使用映射的公网地址）
peerConnection.addIceCandidate({
  candidate: 'candidate:1 1 UDP 2130706431 51.161.209.200 10111 typ host',
  sdpMLineIndex: 0,
  sdpMid: '0'
});
```

## 工作原理

1. **信令阶段**（通过 WebSocket）
   ```
   前端 --> ws://51.161.209.200:10110/ws/{session_id} --> GPU Server
   ```

2. **媒体传输**（直接使用映射端口）
   ```
   前端 <--> UDP 51.161.209.200:10111-10115 <--> GPU Server
   ```

3. **关键点**：
   - ❌ 不需要 STUN 自动发现公网 IP（因为已知）
   - ✅ GPU Server 在 SDP answer 中指定公网地址 `51.161.209.200`
   - ✅ 前端收到 answer 后，直接连接到映射的 UDP 端口

## 为什么不需要 STUN？

| 场景 | 是否需要 STUN | 原因 |
|------|-------------|------|
| 两端都在公网 | ❌ 不需要 | 直接连接 |
| 一端在内网（有端口映射） | ❌ 不需要 | 使用映射的固定端口 |
| 一端在内网（无端口映射） | ✅ 需要 | 需要 UDP 打洞 |
| 两端都在严格 NAT 后 | ✅ 需要 TURN | P2P 失败，需中继 |

**你的情况：GPU Server 在内网但有端口映射** → ❌ 不需要 STUN

## aiortc 配置（后端）

aiortc 库会自动处理端口绑定，但需要确保：

1. GPU Server 监听本地端口 10111-10115（UDP）
2. 在 SDP answer 中指定公网地址

### 修改后的代码

```python
# webrtc_streamer.py
from config import get_settings

async def handle_offer(self, session_id: str, offer_sdp: str, idle_frames=None):
    settings = get_settings()
    
    # 创建 peer connection（不使用 ICE servers）
    pc = RTCPeerConnection()
    
    # 设置本地描述
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
    
    # 创建 answer
    answer = await pc.createAnswer()
    
    # 修改 SDP，替换内网地址为公网地址
    sdp_lines = answer.sdp.split('\r\n')
    modified_sdp = []
    
    for line in sdp_lines:
        if line.startswith('c=IN IP4'):
            # 替换为公网 IP
            modified_sdp.append(f'c=IN IP4 {settings.webrtc_public_ip}')
        else:
            modified_sdp.append(line)
    
    answer_sdp = '\r\n'.join(modified_sdp)
    
    # 设置修改后的 SDP
    await pc.setLocalDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))
    
    return pc.localDescription.sdp
```

## 测试步骤

### 1. 确认端口映射

```bash
# 在 GPU Server 上测试 UDP 端口
nc -u -l 10111
```

```bash
# 在外部机器测试连通性
nc -u 51.161.209.200 10111
```

### 2. 启动服务

```bash
# 启动 GPU Server
cd /workspace/gpuserver
./start_server.sh

# 启动 FRP Client
cd /workspace/frps/frp_0.66.0_linux_amd64
./frpc -c frpc.toml
```

### 3. 前端测试

打开 [test_webrtc.html](file:///workspace/test_webrtc.html)，查看浏览器控制台：

```javascript
// 检查 ICE candidates 类型
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    console.log('ICE Candidate:', event.candidate);
    // 期望看到: typ host, candidate 包含 51.161.209.200
  }
};

// 检查连接状态
peerConnection.onconnectionstatechange = () => {
  console.log('Connection State:', peerConnection.connectionState);
  // 期望: connecting -> connected
};
```

## 优势

✅ **稳定可靠**：不依赖 STUN 服务器可用性  
✅ **延迟更低**：直连，无需 NAT 穿透  
✅ **配置简单**：固定端口，易于防火墙配置  
✅ **成本更低**：无需部署 TURN 中继服务器

## 故障排除

### 问题：前端连接超时

**检查 1**：UDP 端口是否可达
```bash
# 在前端机器测试
nc -u -v 51.161.209.200 10111
```

**检查 2**：GPU Server 是否监听端口
```bash
# 在 GPU Server 上
netstat -uln | grep 1011
```

**检查 3**：FRP 日志
```bash
tail -f /tmp/frpc.log | grep udp
```

### 问题：收不到视频流

**检查 1**：SDP 中的 IP 地址
在浏览器控制台查看：
```javascript
console.log(peerConnection.remoteDescription.sdp);
// 应该包含: c=IN IP4 51.161.209.200
```

**检查 2**：防火墙规则
```bash
# 确保公网服务器允许 UDP 10111-10115
sudo ufw allow 10111:10115/udp
```

## 总结

✅ **已有端口映射 → 不需要 STUN**  
✅ **FRP 配置已完成 → 无需修改**  
✅ **前端移除 STUN 配置**  
✅ **后端使用固定公网地址**
