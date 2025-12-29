/**
 * WebRTC 实时视频流 - 前端完整实现
 *
 * 使用方法：
 * 1. 复制这个文件到你的前端项目
 * 2. 在你的组件中导入并使用 AvatarWebRTCClient
 * 3. 确保你的视频元素已经挂载
 */

class AvatarWebRTCClient {
  constructor(websocket, videoElement) {
    this.websocket = websocket;
    this.videoElement = videoElement;
    this.peerConnection = null;
    this.isConnected = false;
  }

  /**
   * 初始化 WebRTC 连接
   */
  async initialize() {
    console.log('🚀 初始化 WebRTC 连接...');

    // 创建 RTCPeerConnection
    this.peerConnection = new RTCPeerConnection({
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' }
      ]
    });

    // 监听远程视频流
    this.peerConnection.ontrack = (event) => {
      console.log('✓ 收到远程视频流');
      if (event.streams && event.streams[0]) {
        this.videoElement.srcObject = event.streams[0];
        this.videoElement.play().catch(err => {
          console.error('视频播放失败:', err);
        });
        this.isConnected = true;
      }
    };

    // 监听 ICE candidates
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        console.log('📡 发送 ICE candidate');
        this.websocket.send(JSON.stringify({
          type: 'webrtc_ice_candidate',
          candidate: event.candidate
        }));
      }
    };

    // 监听连接状态变化
    this.peerConnection.onconnectionstatechange = () => {
      console.log('WebRTC 连接状态:', this.peerConnection.connectionState);

      if (this.peerConnection.connectionState === 'connected') {
        console.log('✓ WebRTC 连接成功建立');
      } else if (this.peerConnection.connectionState === 'failed') {
        console.error('✗ WebRTC 连接失败');
        this.reconnect();
      }
    };

    // 监听 ICE 连接状态
    this.peerConnection.oniceconnectionstatechange = () => {
      console.log('ICE 连接状态:', this.peerConnection.iceConnectionState);
    };

    // 创建并发送 offer
    try {
      const offer = await this.peerConnection.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: false
      });

      await this.peerConnection.setLocalDescription(offer);

      console.log('📤 发送 WebRTC offer');
      this.websocket.send(JSON.stringify({
        type: 'webrtc_offer',
        sdp: offer.sdp
      }));
    } catch (error) {
      console.error('创建 offer 失败:', error);
    }
  }

  /**
   * 处理服务器返回的 answer
   */
  async handleAnswer(answerSdp) {
    try {
      const answer = new RTCSessionDescription({
        type: 'answer',
        sdp: answerSdp
      });

      await this.peerConnection.setRemoteDescription(answer);
      console.log('✓ WebRTC answer 已设置');
    } catch (error) {
      console.error('设置 answer 失败:', error);
    }
  }

  /**
   * 重新连接
   */
  async reconnect() {
    console.log('🔄 尝试重新连接...');
    this.close();
    await new Promise(resolve => setTimeout(resolve, 1000));
    await this.initialize();
  }

  /**
   * 关闭连接
   */
  close() {
    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }
    this.isConnected = false;
    console.log('WebRTC 连接已关闭');
  }

  /**
   * 检查是否已连接
   */
  isReady() {
    return this.isConnected &&
           this.peerConnection &&
           this.peerConnection.connectionState === 'connected';
  }
}

/**
 * 完整的使用示例（React）
 */
class AvatarChatComponent extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      messages: [],
      inputText: '',
      isConnecting: false,
      isWebRTCReady: false
    };

    this.videoRef = React.createRef();
    this.websocket = null;
    this.webrtcClient = null;
  }

  componentDidMount() {
    this.connectWebSocket();
  }

  componentWillUnmount() {
    if (this.webrtcClient) {
      this.webrtcClient.close();
    }
    if (this.websocket) {
      this.websocket.close();
    }
  }

  /**
   * 连接 WebSocket
   */
  connectWebSocket() {
    // 1. 先创建 session（调用你的 API）
    fetch('http://your-server:9000/mgmt/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tutor_id: 13,
        kb_id: null
      })
    })
    .then(res => res.json())
    .then(data => {
      const { session_id, engine_token } = data;

      // 2. 建立 WebSocket 连接
      const wsUrl = `ws://your-server:9000/ws/ws/${session_id}?token=${engine_token}`;
      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        console.log('✓ WebSocket 连接成功');
        this.initializeWebRTC();
      };

      this.websocket.onmessage = (event) => {
        this.handleWebSocketMessage(JSON.parse(event.data));
      };

      this.websocket.onerror = (error) => {
        console.error('WebSocket 错误:', error);
      };

      this.websocket.onclose = () => {
        console.log('WebSocket 连接关闭');
      };
    })
    .catch(error => {
      console.error('创建 session 失败:', error);
    });
  }

  /**
   * 初始化 WebRTC
   */
  async initializeWebRTC() {
    if (!this.videoRef.current) {
      console.error('视频元素未挂载');
      return;
    }

    this.webrtcClient = new AvatarWebRTCClient(
      this.websocket,
      this.videoRef.current
    );

    await this.webrtcClient.initialize();
  }

  /**
   * 处理 WebSocket 消息
   */
  handleWebSocketMessage(message) {
    console.log('📨 收到消息:', message.type);

    switch(message.type) {
      case 'webrtc_answer':
        // 处理 WebRTC answer
        this.webrtcClient.handleAnswer(message.sdp);
        this.setState({ isWebRTCReady: true });
        break;

      case 'video':
        // 待机视频（初始连接时）
        console.log('收到待机视频');
        // 如果使用传统模式，在这里处理视频
        break;

      case 'text':
        // 文本响应
        this.setState(prevState => ({
          messages: [...prevState.messages, {
            role: 'assistant',
            content: message.content
          }]
        }));

        // 播放音频（如果有）
        if (message.audio) {
          this.playAudio(message.audio);
        }
        break;

      case 'error':
        console.error('服务器错误:', message.content);
        break;

      default:
        console.log('未知消息类型:', message.type);
    }
  }

  /**
   * 播放音频
   */
  playAudio(audioBase64) {
    const audioBlob = this.base64ToBlob(audioBase64, 'audio/wav');
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();
  }

  /**
   * Base64 转 Blob
   */
  base64ToBlob(base64, mimeType) {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  }

  /**
   * 发送消息
   */
  sendMessage() {
    const { inputText } = this.state;

    if (!inputText.trim()) return;

    // 添加用户消息到界面
    this.setState(prevState => ({
      messages: [...prevState.messages, {
        role: 'user',
        content: inputText
      }],
      inputText: ''
    }));

    // 发送到服务器（使用 WebRTC 流式传输）
    this.websocket.send(JSON.stringify({
      type: 'text_webrtc',  // 使用 WebRTC 流式传输
      content: inputText,
      avatar_id: 'avatar_tutor_13'
    }));
  }

  render() {
    const { messages, inputText, isWebRTCReady } = this.state;

    return (
      <div className="avatar-chat">
        {/* 视频显示区域 */}
        <div className="video-container">
          <video
            ref={this.videoRef}
            autoPlay
            playsInline
            muted={false}
            style={{ width: '100%', height: 'auto' }}
          />
          {!isWebRTCReady && (
            <div className="loading">正在建立视频连接...</div>
          )}
        </div>

        {/* 消息列表 */}
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.role}`}>
              {msg.content}
            </div>
          ))}
        </div>

        {/* 输入框 */}
        <div className="input-area">
          <input
            type="text"
            value={inputText}
            onChange={(e) => this.setState({ inputText: e.target.value })}
            onKeyPress={(e) => e.key === 'Enter' && this.sendMessage()}
            placeholder="输入消息..."
          />
          <button onClick={() => this.sendMessage()}>
            发送
          </button>
        </div>
      </div>
    );
  }
}

/**
 * 简化版使用示例（纯 JavaScript）
 */
function simpleExample() {
  const videoElement = document.getElementById('avatar-video');
  let websocket;
  let webrtcClient;

  // 1. 创建 session
  fetch('http://your-server:9000/mgmt/v1/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tutor_id: 13, kb_id: null })
  })
  .then(res => res.json())
  .then(data => {
    const { session_id, engine_token } = data;

    // 2. 连接 WebSocket
    const wsUrl = `ws://your-server:9000/ws/ws/${session_id}?token=${engine_token}`;
    websocket = new WebSocket(wsUrl);

    websocket.onopen = async () => {
      console.log('✓ WebSocket 连接成功');

      // 3. 初始化 WebRTC
      webrtcClient = new AvatarWebRTCClient(websocket, videoElement);
      await webrtcClient.initialize();
    };

    websocket.onmessage = async (event) => {
      const message = JSON.parse(event.data);

      if (message.type === 'webrtc_answer') {
        await webrtcClient.handleAnswer(message.sdp);
        console.log('✓ WebRTC 连接已建立，可以开始对话');
      } else if (message.type === 'text') {
        console.log('收到回复:', message.content);
      }
    };
  });

  // 4. 发送消息
  function sendMessage(text) {
    websocket.send(JSON.stringify({
      type: 'text_webrtc',
      content: text,
      avatar_id: 'avatar_tutor_13'
    }));
  }

  // 使用示例
  // sendMessage('你好');
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AvatarWebRTCClient };
}
