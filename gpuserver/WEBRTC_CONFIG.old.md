# WebRTC 配置指南

## 当前架构

```
前端 (51.161.209.200)
    |
    |-- WebSocket (信令) --> ws://51.161.209.200:10110/ws/{session_id}
    |-- WebRTC (视频) ----> P2P 直连或 TURN 中继
    |
GPU Server (内网，无公网IP)
    |
    |-- FRP Client --> FRP Server (51.161.209.200:7504)
```

## 1. FRP 配置（已完成）

文件: `/workspace/frps/frp_0.66.0_linux_amd64/frpc.toml`

### 当前配置
```toml
# WebSocket 信令通道
[[proxies]]
name = "gpu_server_api"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9000
remotePort = 10110
```

✅ WebSocket 信令已通过端口 10110 提供

## 2. WebRTC 连接方式

### 方式一：P2P 直连（推荐，延迟最低）

**工作原理：**
- 前端和GPU Server通过STUN服务器获取各自的公网IP
- 直接建立点对点连接，无需中继

**配置要求：**
- 无需额外FRP端口
- 需要STUN服务器：`stun:stun.l.google.com:19302`（公共免费）

**限制：**
- 需要GPU Server所在网络允许UDP打洞
- 如果网络有严格NAT/防火墙，可能失败

### 方式二：TURN 中继（备选，适用于P2P失败时）

**工作原理：**
- 当P2P连接失败时，通过TURN服务器中继数据
- 所有视频流量经过TURN服务器转发

**配置要求：**
需要部署TURN服务器在公网服务器上：

```bash
# 在 51.161.209.200 上安装 coturn
sudo apt install coturn

# 配置 /etc/turnserver.conf
listening-port=3478
fingerprint
lt-cred-mech
use-auth-secret
static-auth-secret=your_secret_here
realm=turn.yourdomain.com
total-quota=100
stale-nonce=600
```

**FRP 配置（如果使用TURN）：**
```toml
# 添加到 frpc.toml
[[proxies]]
name = "turn_server"
type = "udp"
localIP = "127.0.0.1"
localPort = 3478
remotePort = 3478
```

## 3. 前端配置

### 基础配置（使用端口映射，无需 STUN）✅ 推荐

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: []  // 空数组：已有端口映射 10110-10115，不需要 STUN
});
```

### 完整配置（STUN + TURN备选）

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: [
    // STUN 服务器（P2P直连）
    { urls: 'stun:stun.l.google.com:19302' },
    
    // TURN 服务器（中继备选）- 如果部署了TURN
    {
      urls: 'turn:51.161.209.200:3478',
      username: 'your_username',
      credential: 'your_password'
    }
  ]
});
```

## 4. WebSocket 消息格式

### 建立 WebRTC 连接

**前端发送 Offer：**
```json
{
  "type": "webrtc_offer",
  "session_id": "session-123",
  "user_id": 5,
  "avatar_id": "avatar_tutor_13",
  "sdp": "v=0\r\no=- ... (SDP内容)"
}
```

**后端返回 Answer：**
```json
{
  "type": "webrtc_answer",
  "sdp": "v=0\r\no=- ... (SDP内容)",
  "timestamp": "2026-01-05T10:30:00"
}
```

### ICE Candidate 交换

**前端发送 ICE Candidate：**
```json
{
  "type": "webrtc_ice_candidate",
  "user_id": 5,
  "candidate": {
    "candidate": "candidate:...",
    "sdpMLineIndex": 0,
    "sdpMid": "0"
  }
}
```

## 5. 完整前端实现代码

```html
<!DOCTYPE html>
<html>
<head>
  <title>Avatar WebRTC Test</title>
</head>
<body>
  <h1>Avatar 实时视频测试</h1>
  <video id="avatar-video" autoplay playsinline style="width: 512px; height: 512px;"></video>
  <br>
  <button onclick="connectWebRTC()">连接 WebRTC</button>
  <button onclick="sendMessage()">发送消息</button>
  <div id="status"></div>

  <script>
    let websocket;
    let peerConnection;
    const userId = 5;
    const sessionId = "test-session-" + Date.now();

    // 连接 WebSocket
    function connectWebSocket() {
      websocket = new WebSocket(`ws://51.161.209.200:10110/ws/${sessionId}`);
      
      websocket.onopen = () => {
        console.log('✓ WebSocket 连接成功');
        updateStatus('WebSocket 已连接');
      };

      websocket.onmessage = async (event) => {
        const message = JSON.parse(event.data);
        console.log('收到消息:', message);

        if (message.type === 'webrtc_answer') {
          // 处理 WebRTC Answer
          const answer = new RTCSessionDescription({
            type: 'answer',
            sdp: message.sdp
          });
          await peerConnection.setRemoteDescription(answer);
          console.log('✓ WebRTC 连接建立成功');
          updateStatus('WebRTC 已连接');
        }
      };

      websocket.onerror = (error) => {
        console.error('WebSocket 错误:', error);
        updateStatus('WebSocket 错误');
      };
    }

    // 建立 WebRTC 连接
    async function connectWebRTC() {
      if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        connectWebSocket();
        await new Promise(resolve => setTimeout(resolve, 1000));
      }

      // 创建 RTCPeerConnection
      peerConnection = new RTCPeerConnection({
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' }
        ]
      });

      // 监听远程视频流
      peerConnection.ontrack = (event) => {
        console.log('✓ 收到远程视频流');
        const videoElement = document.getElementById('avatar-video');
        videoElement.srcObject = event.streams[0];
        videoElement.play();
        updateStatus('正在播放视频');
      };

      // 监听 ICE candidates
      peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
          console.log('发送 ICE candidate');
          websocket.send(JSON.stringify({
            type: 'webrtc_ice_candidate',
            user_id: userId,
            candidate: event.candidate
          }));
        }
      };

      // 监听连接状态
      peerConnection.onconnectionstatechange = () => {
        console.log('WebRTC 连接状态:', peerConnection.connectionState);
        updateStatus('WebRTC: ' + peerConnection.connectionState);
      };

      // 创建 Offer
      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);

      // 发送 Offer 到服务器
      websocket.send(JSON.stringify({
        type: 'webrtc_offer',
        session_id: sessionId,
        user_id: userId,
        avatar_id: 'avatar_tutor_13',
        sdp: offer.sdp
      }));

      console.log('✓ WebRTC Offer 已发送');
      updateStatus('等待 WebRTC Answer...');
    }

    // 发送消息触发 AI 响应（带视频）
    function sendMessage() {
      if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        alert('请先连接 WebSocket');
        return;
      }

      websocket.send(JSON.stringify({
        type: 'text_webrtc',  // 使用 text_webrtc 类型触发视频生成
        session_id: sessionId,
        user_id: userId,
        tutor_id: 13,
        message: '你好，请介绍一下自己',
        avatar_id: 'avatar_tutor_13'
      }));

      console.log('✓ 消息已发送');
      updateStatus('等待 AI 响应...');
    }

    function updateStatus(text) {
      document.getElementById('status').textContent = text;
    }

    // 页面加载时自动连接
    window.onload = () => {
      connectWebSocket();
    };
  </script>
</body>
</html>
```

## 6. 测试步骤

### Step 1: 启动 GPU Server
```bash
cd /workspace/gpuserver
./start_server.sh
```

### Step 2: 启动 FRP Client
```bash
cd /workspace/frps/frp_0.66.0_linux_amd64
./frpc -c frpc.toml
```

### Step 3: 在浏览器中测试
1. 将上面的HTML代码保存为 `test_webrtc.html`
2. 在浏览器中打开
3. 点击"连接 WebRTC"按钮
4. 等待连接成功（应该看到待机视频）
5. 点击"发送消息"按钮
6. 观察视频是否实时播放（应该5秒内看到 Avatar 口型同步视频）

### Step 4: 验证连接类型
在浏览器控制台执行：
```javascript
peerConnection.getStats().then(stats => {
  stats.forEach(report => {
    if (report.type === 'candidate-pair' && report.state === 'succeeded') {
      console.log('连接类型:', report.localCandidateType, '->', report.remoteCandidateType);
    }
  });
});
```

**期望结果：**
- `host -> host`: 局域网直连（最快）
- `srflx -> srflx`: P2P 公网直连（推荐）
- `relay -> relay`: TURN 中继（如果配置了TURN）

## 7. 故障排除

### 问题 1: WebRTC 连接失败

**检查 1: WebSocket 信令是否正常**
```bash
# 测试 WebSocket 连接
python3 /tmp/test_ws.py
```

**检查 2: ICE candidates 类型**
在浏览器控制台查看：
```javascript
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    console.log('ICE Candidate:', event.candidate.type, event.candidate.candidate);
  }
};
```

如果只有 `host` 类型候选，说明 STUN 服务器无法访问。

**检查 3: GPU Server 网络环境**
```bash
# 测试 UDP 是否被防火墙阻止
nc -u -l 50000  # 在 GPU Server 上
# 从前端尝试连接这个端口
```

### 问题 2: 视频不显示

**检查 1: 待机视频是否加载**
查看 GPU Server 日志：
```bash
tail -f /workspace/gpuserver/logs/unified_server.log | grep "idle frames"
```

应该看到：`Set X idle frames for WebRTC track`

**检查 2: 视频轨道是否添加**
在浏览器控制台：
```javascript
peerConnection.getReceivers().forEach(receiver => {
  console.log('Track:', receiver.track.kind, receiver.track.enabled);
});
```

### 问题 3: P2P 连接失败，需要 TURN

如果网络环境不支持 P2P，需要部署 TURN 服务器（见上文配置）。

## 8. 性能优化

### 当前指标
- **LLM 响应**: ~5 秒
- **TTS 生成**: ~1 秒
- **视频首帧**: 实时（待机视频立即显示）
- **对话视频**: 边生成边推流（~25fps）

### 优化建议
1. **降低视频分辨率**: 512x512 → 256x256（如果带宽不足）
2. **调整帧率**: 25fps → 15fps（如果 GPU 负载过高）
3. **启用硬件编码**: 使用 GPU 编码（需要修改 webrtc_streamer.py）

## 9. 下一步

- [ ] 前端集成 WebRTC 代码到实际项目
- [ ] 测试不同网络环境下的连接稳定性
- [ ] 如果需要，部署 TURN 服务器
- [ ] 监控 WebRTC 连接质量和带宽使用

## 10. 常见问题 FAQ

**Q: 为什么不需要额外的FRP端口？**
A: WebRTC 使用 P2P 直连，或通过公共 STUN 服务器建立连接。只有信令（WebSocket）需要经过 FRP，视频流是点对点传输的。

**Q: 如果 P2P 失败怎么办？**
A: 可以部署 TURN 服务器作为中继。但这会增加延迟和带宽成本。

**Q: WebRTC 安全吗？**
A: WebRTC 使用 DTLS 加密视频流，信令通过 WebSocket 传输（建议升级到 WSS）。

**Q: 能否通过 FRP 转发 WebRTC 流量？**
A: 技术上可以，但会失去 WebRTC 的低延迟优势。不推荐。
