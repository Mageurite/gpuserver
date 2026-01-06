# WebRTC SDP "Invalid SDP line" 错误修复

## 问题原因

浏览器报错：`SyntaxError: Invalid SDP line`

**根本原因**：前端在接收 WebRTC answer 后，直接将 SDP 字符串传递给 `RTCPeerConnection.setRemoteDescription()`，但格式不正确。

## 正确的前端代码

### ❌ 错误做法

```javascript
// 收到 answer
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'webrtc_answer') {
    // ❌ 错误：直接传字符串
    peerConnection.setRemoteDescription(data.sdp);  // 报错！
    
    // 或者
    // ❌ 错误：缺少 type 字段
    peerConnection.setRemoteDescription({ sdp: data.sdp });  // 也会报错！
  }
};
```

### ✅ 正确做法

```javascript
// 收到 answer
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'webrtc_answer') {
    // ✅ 正确：创建 RTCSessionDescription 对象，包含 type 和 sdp
    const answer = new RTCSessionDescription({
      type: 'answer',  // 必须是 'answer'
      sdp: data.sdp    // SDP 字符串
    });
    
    await peerConnection.setRemoteDescription(answer);
    console.log('✅ Answer 设置成功');
  }
};
```

## 完整的 WebRTC 流程（前端）

```javascript
class WebRTCClient {
  constructor(websocketUrl, sessionId) {
    this.ws = null;
    this.pc = null;
    this.websocketUrl = websocketUrl;
    this.sessionId = sessionId;
  }

  async init() {
    // 1. 连接 WebSocket
    this.ws = new WebSocket(this.websocketUrl);
    
    // 2. 创建 RTCPeerConnection
    this.pc = new RTCPeerConnection({
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
      ]
    });

    // 3. 添加视频接收器
    this.pc.addTransceiver('video', { direction: 'recvonly' });

    // 4. 监听远程视频流
    this.pc.ontrack = (event) => {
      console.log('📹 收到远程视频流');
      const videoElement = document.getElementById('remoteVideo');
      if (videoElement) {
        videoElement.srcObject = event.streams[0];
      }
    };

    // 5. 监听 ICE candidates
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        console.log('🧊 发送 ICE candidate');
        this.ws.send(JSON.stringify({
          type: 'webrtc_ice_candidate',
          session_id: this.sessionId,
          tutor_id: 13,
          user_id: 5,
          candidate: event.candidate
        }));
      }
    };

    // 6. 监听 ICE 连接状态
    this.pc.oniceconnectionstatechange = () => {
      console.log('ICE 状态:', this.pc.iceConnectionState);
    };

    // 7. 监听 WebSocket 消息
    this.ws.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      console.log('📨 收到消息:', data.type);

      if (data.type === 'webrtc_answer') {
        // ✅ 正确：创建 RTCSessionDescription
        const answer = new RTCSessionDescription({
          type: 'answer',
          sdp: data.sdp
        });
        
        try {
          await this.pc.setRemoteDescription(answer);
          console.log('✅ Answer 设置成功');
        } catch (error) {
          console.error('❌ 设置 Answer 失败:', error);
          console.error('SDP 内容:', data.sdp);
        }
      }
    };

    // 8. WebSocket 连接成功后发送 offer
    this.ws.onopen = async () => {
      console.log('✅ WebSocket 已连接');
      await this.sendOffer();
    };
  }

  async sendOffer() {
    try {
      // 创建 offer
      const offer = await this.pc.createOffer();
      await this.pc.setLocalDescription(offer);

      // 发送 offer 到服务器
      this.ws.send(JSON.stringify({
        type: 'webrtc_offer',
        session_id: this.sessionId,
        tutor_id: 13,
        user_id: 5,
        sdp: offer.sdp  // ✅ 只发送 SDP 字符串即可
      }));

      console.log('📤 Offer 已发送');
    } catch (error) {
      console.error('❌ 创建 Offer 失败:', error);
    }
  }
}

// 使用示例
const client = new WebRTCClient('ws://51.161.209.200:10110/ws/session-id', 'session-id');
client.init();
```

## 调试技巧

### 1. 检查 SDP 格式

```javascript
// 收到 answer 后，先检查 SDP 格式
if (data.type === 'webrtc_answer') {
  console.log('SDP 长度:', data.sdp.length);
  console.log('SDP 前100字符:', data.sdp.substring(0, 100));
  
  // 检查行分隔符
  const lines = data.sdp.split('\r\n');
  console.log('SDP 行数:', lines.length);
  console.log('第1行:', lines[0]);  // 应该是 "v=0"
  console.log('第2行:', lines[1]);  // 应该是 "o=..."
  
  // 验证每一行
  let valid = true;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line && !line.match(/^[vosctimabrz]=/)) {
      console.warn(`⚠️ 第${i+1}行格式可能有问题:`, line);
      valid = false;
    }
  }
  
  if (valid) {
    console.log('✅ SDP 格式验证通过');
  } else {
    console.error('❌ SDP 格式有问题');
  }
}
```

### 2. 捕获详细错误

```javascript
try {
  const answer = new RTCSessionDescription({
    type: 'answer',
    sdp: data.sdp
  });
  await pc.setRemoteDescription(answer);
  console.log('✅ 成功');
} catch (error) {
  console.error('❌ 失败:', error.name, error.message);
  console.error('完整错误:', error);
  
  // 尝试找出具体哪一行有问题
  const lines = data.sdp.split('\r\n');
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].match(/^[vosctimabrz]=/)) {
      console.error(`可疑行 ${i+1}:`, lines[i]);
    }
  }
}
```

## 后端已正确配置

后端已经正确返回 WebRTC answer，包含：
- ✅ 正确的 SDP 格式（使用 `\r\n` 行分隔符）
- ✅ 已将私网 IP 替换为公网 IP
- ✅ JSON 序列化正确

**问题在前端**：需要使用 `new RTCSessionDescription({ type: 'answer', sdp: data.sdp })` 而不是直接传递 `data.sdp`。

## 参考资料

- [MDN: RTCPeerConnection.setRemoteDescription()](https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/setRemoteDescription)
- [MDN: RTCSessionDescription](https://developer.mozilla.org/en-US/docs/Web/API/RTCSessionDescription)
- [WebRTC SDP 格式规范](https://datatracker.ietf.org/doc/html/rfc4566)
