# 前端视频集成指南

## 功能说明

GPU Server 支持在 WebSocket 连接建立后自动加载**待机视频**（idle video），无需等待用户发送消息。

**待机视频**：预先生成的循环视频，avatar 处于静止/待机状态，没有唇动。

**唇动视频**：用户发送文字后，服务器用 TTS 生成音频，然后驱动 avatar 唇动生成新视频。

---

## 快速开始：连接后自动加载待机视频

### 1. 建立 WebSocket 连接

```javascript
const websocket = new WebSocket('ws://your-server:port/ws/session_id?token=your_token');

websocket.onopen = () => {
    console.log('WebSocket 连接已建立');

    // 🎯 连接成功后立即发送初始化请求，获取待机视频
    websocket.send(JSON.stringify({
        type: "init",
        avatar_id: "avatar_tutor_13"  // 必须提供 avatar_id
    }));
};
```

### 2. 接收并播放待机视频

```javascript
websocket.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'video') {
        // 服务器返回待机视频（循环播放）
        playVideo(message.video);  // base64 编码的视频

        // 待机视频没有文本内容
        if (message.content) {
            console.log('消息:', message.content);
        }
    }
};
```

**工作流程**：
1. WebSocket 连接建立
2. 前端发送 `type: "init"` 消息（带 `avatar_id`）
3. 服务器返回预先生成的待机视频（5秒循环）
4. 前端播放待机视频（可设置 `loop` 属性循环播放）
5. 用户发送文字消息时，服务器生成带唇动的新视频

---

## 消息类型说明

### 1. 初始化消息（获取待机视频）

**发送格式**：
```javascript
websocket.send(JSON.stringify({
    type: "init",
    avatar_id: "avatar_tutor_13"  // 必需参数
}));
```

**服务器响应**：
```javascript
{
    type: "video",
    content: "",  // 待机视频没有文本内容
    video: "base64_encoded_idle_video_data",  // 5秒循环视频
    role: "assistant",
    timestamp: "2024-01-01T12:00:00"
}
```

**特点**：
- 不生成 TTS 音频
- 不包含文本内容
- 视频是预先生成的循环视频（5秒）
- 可以设置 `<video loop>` 属性实现无限循环播放

### 2. 文本消息（用户对话，生成唇动视频）

**发送格式**：
```javascript
// ❌ 错误的方式（不会生成视频）
websocket.send(JSON.stringify({
    type: "text",
    content: "你好"
}));

// ✅ 正确的方式（会生成视频）
websocket.send(JSON.stringify({
    type: "text",
    content: "你好",
    avatar_id: "avatar_tutor_13"  // 必须添加这个参数
}));
```

**avatar_id 格式**：`avatar_tutor_{tutor_id}`
- Tutor 13: `avatar_tutor_13`
- Tutor 1: `avatar_tutor_1`
- Tutor 5: `avatar_tutor_5`

---

## 视频播放实现

### 1. 处理服务器响应

服务器会返回包含视频数据的消息：

```javascript
websocket.onmessage = (event) => {
    const message = JSON.parse(event.data);

    console.log('收到消息类型:', message.type);
    console.log('消息内容:', message.content);

    if (message.type === 'video') {
        // 消息包含视频数据
        const videoBase64 = message.video;  // base64 编码的视频
        const audioBase64 = message.audio;  // base64 编码的音频
        const textContent = message.content; // 文本内容

        // 播放视频
        playVideo(videoBase64);
    } else if (message.type === 'audio') {
        // 只有音频，没有视频
        const audioBase64 = message.audio;
        playAudio(audioBase64);
    } else if (message.type === 'text') {
        // 只有文本
        displayText(message.content);
    }
};
```

### 3. 正确播放视频

视频数据是 base64 编码的 MP4 格式，需要转换为 Blob URL：

```javascript
function playVideo(base64Video) {
    try {
        // 1. 解码 base64
        const binaryString = atob(base64Video);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // 2. 创建 Blob
        const blob = new Blob([bytes], { type: 'video/mp4' });

        // 3. 创建 Blob URL
        const videoUrl = URL.createObjectURL(blob);

        // 4. 设置视频元素
        const videoElement = document.getElementById('tutorVideo');
        videoElement.src = videoUrl;

        // 5. 播放视频
        videoElement.play().catch(error => {
            console.error('视频播放失败:', error);
        });

        // 6. 清理旧的 URL（可选，避免内存泄漏）
        videoElement.onended = () => {
            URL.revokeObjectURL(videoUrl);
        };

    } catch (error) {
        console.error('视频处理失败:', error);
    }
}
```

### 4. HTML 视频元素

确保 HTML 中有正确的视频元素：

```html
<video
    id="tutorVideo"
    width="640"
    height="480"
    controls
    autoplay
    muted
    playsinline
>
    您的浏览器不支持视频播放
</video>
```

**重要属性**：
- `autoplay`: 自动播放
- `muted`: 静音（某些浏览器要求静音才能自动播放）
- `playsinline`: iOS 设备内联播放
- `controls`: 显示播放控制条

---

## 完整示例代码

```javascript
// WebSocket 连接
const ws = new WebSocket('ws://localhost:9000/ws/ws/your-session-id?token=your-token');

ws.onopen = () => {
    console.log('WebSocket 连接成功');
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('收到消息:', message);

    // 显示文本内容
    if (message.content) {
        document.getElementById('chatMessages').innerHTML +=
            `<div class="assistant-message">${message.content}</div>`;
    }

    // 处理视频
    if (message.type === 'video' && message.video) {
        playVideo(message.video);
    }
    // 处理音频
    else if (message.type === 'audio' && message.audio) {
        playAudio(message.audio);
    }
};

ws.onerror = (error) => {
    console.error('WebSocket 错误:', error);
};

ws.onclose = () => {
    console.log('WebSocket 连接关闭');
};

// 发送消息函数
function sendMessage(text) {
    const message = {
        type: "text",
        content: text,
        avatar_id: "avatar_tutor_13"  // 关键：必须包含 avatar_id
    };

    ws.send(JSON.stringify(message));
    console.log('发送消息:', message);
}

// 播放视频函数
function playVideo(base64Video) {
    try {
        // 解码 base64
        const binaryString = atob(base64Video);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // 创建 Blob 和 URL
        const blob = new Blob([bytes], { type: 'video/mp4' });
        const videoUrl = URL.createObjectURL(blob);

        // 播放视频
        const videoElement = document.getElementById('tutorVideo');
        videoElement.src = videoUrl;
        videoElement.play().catch(error => {
            console.error('视频播放失败:', error);
        });

        // 清理
        videoElement.onended = () => {
            URL.revokeObjectURL(videoUrl);
        };

    } catch (error) {
        console.error('视频处理失败:', error);
    }
}

// 播放音频函数
function playAudio(base64Audio) {
    try {
        const audio = new Audio('data:audio/wav;base64,' + base64Audio);
        audio.play().catch(error => {
            console.error('音频播放失败:', error);
        });
    } catch (error) {
        console.error('音频处理失败:', error);
    }
}

// 绑定发送按钮
document.getElementById('sendButton').onclick = () => {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (text) {
        sendMessage(text);
        input.value = '';
    }
};
```

---

## 调试步骤

### 1. 检查是否发送了 avatar_id

在浏览器控制台中查看发送的消息：

```javascript
// 在 ws.send() 之前添加
console.log('发送消息:', message);
```

确认输出包含 `avatar_id`:
```json
{
    "type": "text",
    "content": "你好",
    "avatar_id": "avatar_tutor_13"
}
```

### 2. 检查服务器响应

在浏览器控制台中查看收到的消息：

```javascript
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('收到消息:', message);
    console.log('消息类型:', message.type);
    console.log('是否包含视频:', !!message.video);
    console.log('视频数据长度:', message.video ? message.video.length : 0);
};
```

**期望输出**：
```
收到消息: {type: "video", content: "...", audio: "...", video: "...", ...}
消息类型: video
是否包含视频: true
视频数据长度: 123456
```

### 3. 检查 GPU Server 日志

在服务器端查看日志：

```bash
tail -f /workspace/gpuserver/logs/unified_server.log | grep -i "video\|avatar"
```

**期望看到**：
```
INFO - Generating video for avatar_id=avatar_tutor_13
INFO - Video generated: length=123456
```

如果没有看到这些日志，说明前端没有发送 `avatar_id`。

---

## 常见问题

### Q1: 视频黑屏，没有报错

**原因**：前端没有发送 `avatar_id` 参数

**解决**：在发送消息时添加 `avatar_id: "avatar_tutor_13"`

### Q2: 报错 "null is not an object (evaluating 'videoTrack.configuration')"

**原因**：视频元素尝试访问不存在的视频轨道

**解决**：
1. 确保发送了 `avatar_id`
2. 确保服务器返回了 `video` 字段
3. 检查视频数据是否为空

### Q3: 视频数据很大，传输慢

**原因**：视频通过 WebSocket 传输，base64 编码会增加 33% 大小

**解决**：
- 短期：可以接受，视频通常只有几秒
- 长期：考虑使用 HTTP 流式传输或分块传输

### Q4: 视频无法播放

**原因**：浏览器不支持 MP4 格式或编码

**解决**：
1. 检查浏览器控制台错误
2. 确认视频格式为 MP4
3. 尝试在其他浏览器测试

---

## 测试清单

- [ ] 前端发送消息时包含 `avatar_id` 参数
- [ ] 浏览器控制台显示收到 `type: "video"` 的消息
- [ ] 消息中包含 `video` 字段且不为空
- [ ] GPU Server 日志显示 "Generating video"
- [ ] 视频元素的 `src` 被正确设置
- [ ] 视频可以播放

---

## 联系支持

如果按照以上步骤仍然无法解决问题，请提供：

1. 浏览器控制台的完整错误信息
2. 发送的消息内容（`console.log` 输出）
3. 收到的消息内容（`console.log` 输出）
4. GPU Server 日志（最后 50 行）

```bash
# 获取 GPU Server 日志
tail -50 /workspace/gpuserver/logs/unified_server.log
```
