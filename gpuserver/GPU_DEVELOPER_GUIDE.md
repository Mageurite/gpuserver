# GPU 开发者 WebRTC 配置指南

## 🎯 核心配置（3个关键点）

### 1️⃣ ICE 服务器配置

```python
# GPU Server: webrtc_streamer.py
ice_servers = [
    # STUN: 发现公网IP
    {"urls": "stun:stun.l.google.com:19302"},
    
    # TURN: 当P2P失败时中继
    {
        "urls": ["turn:51.161.209.200:10110?transport=udp"],
        "username": "vtuser",
        "credential": "vtpass"
    }
]
```

**为什么需要这两个？**
- **STUN**: 帮助发现GPU Server的公网IP（通过FRP映射后的地址）
- **TURN**: 如果P2P连接失败（严格防火墙/NAT），通过TURN服务器中继

### 2️⃣ 公网IP替换（⚠️ 关键！）

**问题**：GPU在私网，生成的ICE candidates包含私网IP（如 `192.168.x.x`），浏览器无法连接。

**解决**：在SDP answer中将私网IP替换为公网IP。

```python
PUBLIC_IP = "51.161.209.200"

def _replace_private_ip_in_sdp(sdp: str, public_ip: str) -> str:
    """将SDP中的私网IP替换为公网IP"""
    import re
    
    # 替换 c= 行中的IP地址
    sdp = re.sub(r'c=IN IP4 \d+\.\d+\.\d+\.\d+', f'c=IN IP4 {public_ip}', sdp)
    
    # 替换 ICE candidate 中的私网IP (10.x, 172.16-31.x, 192.168.x)
    private_ip_pattern = r'(a=candidate:[^ ]+ [^ ]+ [^ ]+ [^ ]+ )((?:10|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)\.\d+\.\d+)'
    sdp = re.sub(private_ip_pattern, rf'\1{public_ip}', sdp)
    
    return sdp

# 在 handle_offer 中使用
answer_sdp = _replace_private_ip_in_sdp(pc.localDescription.sdp, PUBLIC_IP)
```

### 3️⃣ WebRTC 流程

```
浏览器                          GPU Server
  |                                  |
  |-- webrtc_offer (SDP) ---------->|
  |                                  |
  |                         创建 answer
  |                         替换私网IP为公网IP
  |                                  |
  |<- webrtc_answer (SDP) -----------|
  |                                  |
  |<---> 交换 ICE candidates <------>|
  |                                  |
  |====== 建立连接 ==================|
  |                                  |
  |<===== 传输视频流 ================|
```

---

## 📝 完整实现代码

### GPU Server 端

#### config.py
```python
class Settings(BaseSettings):
    # WebRTC 配置
    webrtc_public_ip: str = "51.161.209.200"  # 公网IP
    webrtc_port_min: int = 10111               # 媒体端口范围
    webrtc_port_max: int = 10115
    
    # TURN 服务器配置
    turn_server: str = "turn:51.161.209.200:10110?transport=udp"
    turn_username: str = "vtuser"
    turn_credential: str = "vtpass"
```

#### webrtc_streamer.py
```python
from aiortc import RTCPeerConnection, RTCSessionDescription
from config import get_settings
import re
import logging

logger = logging.getLogger(__name__)

class WebRTCStreamer:
    def __init__(self):
        self.connections = {}
        self.video_tracks = {}
    
    async def create_peer_connection(self, session_id: str):
        """创建 WebRTC 连接（配置 STUN + TURN）"""
        settings = get_settings()
        
        # 配置 ICE 服务器
        ice_servers = [
            {"urls": "stun:stun.l.google.com:19302"},
            {
                "urls": settings.turn_server,
                "username": settings.turn_username,
                "credential": settings.turn_credential
            }
        ]
        
        pc = RTCPeerConnection(configuration={"iceServers": ice_servers})
        self.connections[session_id] = pc
        return pc
    
    async def handle_offer(self, session_id: str, offer_sdp: str):
        """处理 WebRTC offer"""
        settings = get_settings()
        
        # 创建连接
        if session_id not in self.connections:
            pc = await self.create_peer_connection(session_id)
        else:
            pc = self.connections[session_id]
        
        # 设置远程描述
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await pc.setRemoteDescription(offer)
        
        # 创建 answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # ⚠️ 关键：替换私网IP为公网IP
        answer_sdp = self._replace_private_ip_in_sdp(
            pc.localDescription.sdp, 
            settings.webrtc_public_ip
        )
        
        logger.info(f"WebRTC answer created (IP replaced): {session_id}")
        return answer_sdp
    
    def _replace_private_ip_in_sdp(self, sdp: str, public_ip: str) -> str:
        """将SDP中的私网IP替换为公网IP"""
        # 替换 c= 行
        sdp = re.sub(
            r'c=IN IP4 \d+\.\d+\.\d+\.\d+', 
            f'c=IN IP4 {public_ip}', 
            sdp
        )
        
        # 替换 ICE candidate 中的私网IP
        private_ip_pattern = (
            r'(a=candidate:[^ ]+ [^ ]+ [^ ]+ [^ ]+ )'
            r'((?:10|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)\.\d+\.\d+)'
        )
        sdp = re.sub(private_ip_pattern, rf'\1{public_ip}', sdp)
        
        logger.debug(f"Replaced private IPs with {public_ip}")
        return sdp
```

#### websocket_server.py
```python
from webrtc_streamer import WebRTCStreamer

webrtc_streamer = WebRTCStreamer()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            
            if msg_type == "webrtc_offer":
                # 处理 WebRTC offer
                offer_sdp = message.get("sdp")
                user_id = message.get("user_id")
                
                # 生成 answer（自动替换IP）
                answer_sdp = await webrtc_streamer.handle_offer(
                    session_id=f"user_{user_id}",
                    offer_sdp=offer_sdp
                )
                
                # 发送 answer
                await websocket.send_json({
                    "type": "webrtc_answer",
                    "sdp": answer_sdp
                })
                
            elif msg_type == "webrtc_ice_candidate":
                # 处理 ICE candidate
                candidate = message.get("candidate")
                user_id = message.get("user_id")
                
                await webrtc_streamer.add_ice_candidate(
                    session_id=f"user_{user_id}",
                    candidate=candidate
                )
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
```

---

## 🌐 前端代码

```javascript
// 创建 WebRTC 连接
const peerConnection = new RTCPeerConnection({
  iceServers: [
    // STUN: 发现公网IP
    { urls: 'stun:stun.l.google.com:19302' },
    
    // TURN: 中继备选
    {
      urls: 'turn:51.161.209.200:10110?transport=udp',
      username: 'vtuser',
      credential: 'vtpass'
    }
  ]
});

// 监听视频流
peerConnection.ontrack = (event) => {
  console.log('✅ 收到视频流');
  videoElement.srcObject = event.streams[0];
};

// 监听 ICE candidates
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    // 发送 ICE candidate 到服务器
    websocket.send(JSON.stringify({
      type: 'webrtc_ice_candidate',
      user_id: userId,
      candidate: event.candidate
    }));
  }
};

// 创建并发送 offer
const offer = await peerConnection.createOffer();
await peerConnection.setLocalDescription(offer);

websocket.send(JSON.stringify({
  type: 'webrtc_offer',
  session_id: sessionId,
  user_id: userId,
  sdp: offer.sdp
}));

// 接收 answer
websocket.onmessage = async (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'webrtc_answer') {
    await peerConnection.setRemoteDescription({
      type: 'answer',
      sdp: msg.sdp  // 已替换为公网IP的SDP
    });
    console.log('✅ WebRTC 连接已建立');
  }
};
```

---

## 🔍 调试技巧

### 1. 检查 SDP 中的 IP 地址

**在 GPU Server 端：**
```python
# 在 handle_offer 中添加日志
logger.info(f"Original SDP:\n{pc.localDescription.sdp}")
logger.info(f"Modified SDP:\n{answer_sdp}")

# 验证是否替换成功
assert "192.168" not in answer_sdp, "私网IP未替换！"
assert PUBLIC_IP in answer_sdp, "公网IP不存在！"
```

**在浏览器端：**
```javascript
// 检查收到的 answer SDP
websocket.onmessage = async (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'webrtc_answer') {
    console.log('Answer SDP:', msg.sdp);
    
    // 验证公网IP
    if (msg.sdp.includes('51.161.209.200')) {
      console.log('✅ SDP 包含公网IP');
    } else {
      console.error('❌ SDP 缺少公网IP！');
    }
  }
};
```

### 2. 检查 ICE Candidates 类型

```javascript
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    console.log('ICE Candidate:', {
      type: event.candidate.type,         // host, srflx, relay
      ip: event.candidate.address,        // IP地址
      port: event.candidate.port,         // 端口
      protocol: event.candidate.protocol  // udp, tcp
    });
  }
};
```

**期望结果：**
- `type: "host"` - 本地地址
- `type: "srflx"` - STUN 反射地址（公网IP）
- `type: "relay"` - TURN 中继地址

### 3. 检查连接状态

```javascript
peerConnection.onconnectionstatechange = () => {
  console.log('连接状态:', peerConnection.connectionState);
  /*
   * new -> connecting -> connected (成功)
   * new -> connecting -> failed (失败)
   */
};

peerConnection.oniceconnectionstatechange = () => {
  console.log('ICE 状态:', peerConnection.iceConnectionState);
  /*
   * checking -> connected (P2P成功)
   * checking -> completed (P2P成功，所有candidates已检查)
   * checking -> failed -> connected (通过TURN中继成功)
   */
};
```

### 4. 检查端口映射

```bash
# 在 GPU Server 上检查端口监听
netstat -uln | grep -E "(10110|10111|10112|10113|10114|10115)"

# 在外部机器测试 TURN 端口
nc -u -v 51.161.209.200 10110
```

---

## ⚠️ 常见问题

### 问题 1: 连接超时 / failed

**原因**：SDP 中仍包含私网IP

**解决**：
1. 检查 `_replace_private_ip_in_sdp` 是否被调用
2. 验证正则表达式是否匹配所有私网IP格式
3. 查看日志确认替换成功

### 问题 2: TURN 服务器无响应

**原因**：端口 10110 UDP 未正确映射

**解决**：
```bash
# 检查 FRP 配置
grep -A 3 "udp_10110" frpc.toml

# 如果不存在，添加：
[[proxies]]
name = "turn_server"
type = "udp"
localPort = 10110
remotePort = 10110
```

### 问题 3: ICE gathering 卡住

**原因**：STUN 服务器无法访问

**解决**：
1. 测试 STUN 连通性：`nc -u stun.l.google.com 19302`
2. 更换其他 STUN 服务器：`stun:stun1.l.google.com:19302`

---

## 📊 配置总结

| 组件 | 配置项 | 值 | 说明 |
|------|--------|-----|------|
| **STUN** | urls | `stun:stun.l.google.com:19302` | 发现公网IP |
| **TURN** | urls | `turn:51.161.209.200:10110?transport=udp` | 中继服务器 |
| **TURN** | username | `vtuser` | 认证用户名 |
| **TURN** | credential | `vtpass` | 认证密码 |
| **公网IP** | webrtc_public_ip | `51.161.209.200` | 替换目标 |
| **媒体端口** | webrtc_port_min/max | `10111-10115` | UDP 端口范围 |

---

## ✅ 验证清单

- [ ] GPU Server 配置了 STUN + TURN
- [ ] 实现了 `_replace_private_ip_in_sdp` 函数
- [ ] SDP answer 中不包含私网IP
- [ ] 前端配置了相同的 ICE 服务器
- [ ] FRP 映射了 UDP 端口 10110-10115
- [ ] 浏览器能收到视频流

---

## 🚀 快速测试

```bash
# 1. 启动 GPU Server
cd /workspace/gpuserver
./start_server.sh

# 2. 启动 FRP
cd /workspace/frps/frp_0.66.0_linux_amd64
./frpc -c frpc.toml

# 3. 打开测试页面
# 浏览器访问: file:///workspace/test_webrtc.html
```

---

**关键点总结：**
1. ✅ 配置 STUN（发现公网IP）+ TURN（中继备选）
2. ✅ **必须替换 SDP 中的私网IP为公网IP**
3. ✅ 前后端使用相同的 ICE 配置
