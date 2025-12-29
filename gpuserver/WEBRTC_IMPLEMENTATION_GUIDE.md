# WebRTC 实时视频流实现指南

## 概述

本指南说明如何实现 WebRTC 实时视频流，以解决当前视频生成延迟过高的问题（从 50 秒降低到实时）。

## 当前问题

- **LLM 响应**: 4 秒 ✓
- **TTS 生成**: 1 秒 ✓
- **MuseTalk 视频生成**: 50 秒 ✗ (太慢)
- **总延迟**: ~55 秒

## 解决方案：WebRTC 实时流

### 架构

```
前端                          后端
 |                             |
 |-- WebSocket 信令通道 ------->|
 |<-- WebRTC Offer/Answer -----|
 |                             |
 |====== WebRTC 视频流 ========|
 |<-- 实时帧流 (25fps) ---------|
 |                             |
 |                        MuseTalk
 |                        边生成边推流
```

## 后端实现（已完成）

### 1. WebRTC Streamer 模块

文件: `/workspace/gpuserver/webrtc_streamer.py`

功能:
- 管理 WebRTC peer connections
- 提供视频帧流式传输
- 处理 ICE candidates

### 2. WebSocket 信令支持

文件: `/workspace/gpuserver/api/websocket_server.py`

新增消息类型:
- `webrtc_offer`: 接收客户端 offer
- `webrtc_answer`: 发送服务器 answer
- `webrtc_ice_candidate`: 处理 ICE candidates

## 前端实现（需要你完成）

### 步骤 1: 建立 WebRTC 连接

```javascript
// 1. 创建 RTCPeerConnection
const peerConnection = new RTCPeerConnection({
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' }
  ]
});

// 2. 监听远程视频流
peerConnection.ontrack = (event) => {
  console.log('✓ 收到远程视频流');
  const videoElement = document.getElementById('avatar-video');
  videoElement.srcObject = event.streams[0];
  videoElement.play();
};

// 3. 监听 ICE candidates
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    // 通过 WebSocket 发送 ICE candidate 到服务器
    websocket.send(JSON.stringify({
      type: 'webrtc_ice_candidate',
      candidate: event.candidate
    }));
  }
};

// 4. 创建 offer
const offer = await peerConnection.createOffer();
await peerConnection.setLocalDescription(offer);

// 5. 通过 WebSocket 发送 offer 到服务器
websocket.send(JSON.stringify({
  type: 'webrtc_offer',
  sdp: offer.sdp
}));
```

### 步骤 2: 处理服务器 answer

```javascript
websocket.onmessage = async (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'webrtc_answer') {
    // 设置远程描述
    const answer = new RTCSessionDescription({
      type: 'answer',
      sdp: message.sdp
    });
    await peerConnection.setRemoteDescription(answer);
    console.log('✓ WebRTC 连接建立成功');
  }
};
```

### 步骤 3: 完整的前端代码示例

```javascript
class AvatarWebRTCClient {
  constructor(websocket, videoElement) {
    this.websocket = websocket;
    this.videoElement = videoElement;
    this.peerConnection = null;
  }

  async initialize() {
    // 创建 peer connection
    this.peerConnection = new RTCPeerConnection({
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
      ]
    });

    // 监听远程视频流
    this.peerConnection.ontrack = (event) => {
      console.log('✓ 收到远程视频流');
      this.videoElement.srcObject = event.streams[0];
      this.videoElement.play();
    };

    // 监听 ICE candidates
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        this.websocket.send(JSON.stringify({
          type: 'webrtc_ice_candidate',
          candidate: event.candidate
        }));
      }
    };

    // 监听连接状态
    this.peerConnection.onconnectionstatechange = () => {
      console.log('WebRTC 连接状态:', this.peerConnection.connectionState);
    };

    // 创建并发送 offer
    const offer = await this.peerConnection.createOffer();
    await this.peerConnection.setLocalDescription(offer);

    this.websocket.send(JSON.stringify({
      type: 'webrtc_offer',
      sdp: offer.sdp
    }));
  }

  async handleAnswer(answerSdp) {
    const answer = new RTCSessionDescription({
      type: 'answer',
      sdp: answerSdp
    });
    await this.peerConnection.setRemoteDescription(answer);
    console.log('✓ WebRTC 连接建立成功');
  }

  close() {
    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }
  }
}

// 使用示例
const videoElement = document.getElementById('avatar-video');
const webrtcClient = new AvatarWebRTCClient(websocket, videoElement);

// 在 WebSocket 连接建立后初始化 WebRTC
websocket.onopen = async () => {
  console.log('✓ WebSocket 连接成功');
  await webrtcClient.initialize();
};

// 处理服务器消息
websocket.onmessage = async (event) => {
  const message = JSON.parse(event.data);

  switch(message.type) {
    case 'webrtc_answer':
      await webrtcClient.handleAnswer(message.sdp);
      break;

    case 'text':
      // 显示文本
      displayText(message.content);
      break;

    // ... 其他消息类型
  }
};
```

## 后端需要完成的部分

### 修改 AI Models 以支持实时帧流

需要在 `ai_models.py` 中添加新方法：

```python
async def generate_video_stream(
    self,
    text: str,
    avatar_id: str,
    session_id: str
):
    """
    实时生成并流式传输视频帧

    1. TTS 生成音频
    2. MuseTalk 逐帧生成
    3. 每生成一帧就通过 WebRTC 推送
    """
    # 1. 生成音频
    audio_data = await self.synthesize_speech(text)

    # 2. 获取 WebRTC streamer
    from webrtc_streamer import get_webrtc_streamer
    streamer = get_webrtc_streamer()

    # 3. 实时生成并推流帧
    async for frame in self.video_engine.generate_frames_stream(
        audio_data=audio_data,
        avatar_id=avatar_id
    ):
        # 推送帧到 WebRTC
        await streamer.stream_frame(session_id, frame)
```

### 修改 Avatar Manager 以支持帧流

需要在 `avatar_manager.py` 中添加：

```python
async def generate_frames_stream(
    self,
    audio_data: str,
    avatar_id: str
):
    """
    生成器：逐帧生成视频帧

    Yields:
        numpy.ndarray: 视频帧 (H, W, 3) BGR 格式
    """
    # 实现逐帧生成逻辑
    # 每生成一帧就 yield 出去
```

## 测试步骤

### 1. 重启后端服务器

```bash
cd /workspace/gpuserver
kill <old_pid>
nohup /workspace/conda_envs/mt/bin/python unified_server.py > logs/unified_server_console.log 2>&1 &
```

### 2. 前端测试

在浏览器控制台运行：

```javascript
// 测试 WebRTC 连接
const testWebRTC = async () => {
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
  });

  pc.ontrack = (e) => console.log('✓ 收到视频流', e.streams[0]);
  pc.onicecandidate = (e) => console.log('ICE candidate:', e.candidate);

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  console.log('Offer SDP:', offer.sdp);

  // 发送到服务器
  websocket.send(JSON.stringify({
    type: 'webrtc_offer',
    sdp: offer.sdp
  }));
};

testWebRTC();
```

### 3. 查看日志

```bash
tail -f /workspace/gpuserver/logs/unified_server_console.log | grep -E "(WebRTC|webrtc)"
```

## 预期效果

- **文本响应**: 立即显示（4 秒）
- **音频播放**: 立即播放（5 秒）
- **视频流**: 实时显示（5-10 秒开始，边生成边播放）
- **总体验**: 从 55 秒延迟降低到 5-10 秒

## 故障排查

### 问题 1: WebRTC 连接失败

检查：
- 浏览器是否支持 WebRTC
- STUN 服务器是否可达
- 防火墙是否阻止 UDP 连接

### 问题 2: 没有收到视频流

检查：
- 后端是否正确推送帧
- `peerConnection.ontrack` 是否触发
- 视频元素是否正确设置 `srcObject`

### 问题 3: 视频卡顿

检查：
- 帧率是否稳定（25fps）
- 网络带宽是否足够
- 帧队列是否溢出

## 下一步

1. **前端实现 WebRTC 客户端**（你需要完成）
2. **后端实现帧流式生成**（我可以帮你完成）
3. **测试端到端流程**
4. **优化性能和稳定性**

## 需要帮助？

如果遇到问题，请提供：
- 浏览器控制台日志
- 后端服务器日志
- WebRTC 连接状态

我会帮你调试！
