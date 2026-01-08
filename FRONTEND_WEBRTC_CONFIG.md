# 前端 WebRTC 配置修改指南

## 概述

后端已配置为使用公网 IP 和指定端口范围，前端需要从后端获取 ICE 服务器配置以确保 WebRTC 连接成功。

## 🔧 后端提供的 API

### 获取 WebRTC 配置
**端点**: `GET /v1/webrtc/config` 或 `GET /mgmt/v1/webrtc/config`

**响应示例**:
```json
{
    "iceServers": [
        {
            "urls": ["stun:stun.l.google.com:19302"]
        }
    ],
    "publicIp": "51.161.209.200",
    "portRange": {
        "min": 10110,
        "max": 10115
    },
    "sdpSemantics": "unified-plan"
}
```

## 📝 前端需要的修改

### 文件: `/workspace/try/frontend/src/components/HomeChatList/index.js`

#### 当前代码 (第 38-40 行):
```javascript
const config = {
    sdpSemantics: 'unified-plan',
    iceServers: []  // Empty for localhost/SSH tunnel connections
};
pc = new window.RTCPeerConnection(config);
```

#### 修改为:
```javascript
// 从后端获取 WebRTC 配置
const fetchWebRTCConfig = async () => {
    try {
        const backendUrl = getBackendUrl();
        const response = await fetch(`${backendUrl}/v1/webrtc/config`);
        if (!response.ok) {
            console.warn('Failed to fetch WebRTC config, using default');
            return {
                sdpSemantics: 'unified-plan',
                iceServers: []
            };
        }
        const webrtcConfig = await response.json();
        return webrtcConfig;
    } catch (error) {
        console.error('Error fetching WebRTC config:', error);
        // 降级：使用空配置（适用于本地开发）
        return {
            sdpSemantics: 'unified-plan',
            iceServers: []
        };
    }
};

// 获取配置后创建连接
const config = await fetchWebRTCConfig();
pc = new window.RTCPeerConnection(config);
```

### 完整的 startConnection 函数修改:

```javascript
const startConnection = async () => {
    setLoading(true);
    try {
        let pc;
        let stopped = false;
        
        // 从后端获取 WebRTC 配置
        const fetchWebRTCConfig = async () => {
            try {
                const backendUrl = getBackendUrl();
                const response = await fetch(`${backendUrl}/v1/webrtc/config`);
                if (!response.ok) {
                    console.warn('Failed to fetch WebRTC config, using default');
                    return {
                        sdpSemantics: 'unified-plan',
                        iceServers: []
                    };
                }
                return await response.json();
            } catch (error) {
                console.error('Error fetching WebRTC config:', error);
                return {
                    sdpSemantics: 'unified-plan',
                    iceServers: []
                };
            }
        };

        // 获取配置
        const config = await fetchWebRTCConfig();
        console.log('Using WebRTC config:', config);
        
        pc = new window.RTCPeerConnection(config);
        pcRef.current = pc;

        // ... 其余代码保持不变 ...
    } catch (error) {
        console.error('Connection error:', error);
        setLoading(false);
    }
};
```

## 🎯 关键修改点

1. **添加配置获取函数**
   - 从后端 API 获取 WebRTC 配置
   - 包含错误处理和降级方案

2. **使用动态配置**
   - 不再硬编码空的 `iceServers: []`
   - 使用后端提供的 STUN 服务器配置

3. **保持向后兼容**
   - 如果获取配置失败，降级到空配置（适用于本地开发）
   - 添加控制台日志便于调试

## 🔍 验证步骤

1. **修改前端代码**
   ```bash
   cd /workspace/try/frontend
   # 修改 src/components/HomeChatList/index.js
   ```

2. **重启前端服务**
   ```bash
   npm start
   ```

3. **检查浏览器控制台**
   应该看到：
   ```
   Using WebRTC config: {iceServers: [{urls: ["stun:stun.l.google.com:19302"]}], ...}
   ```

4. **测试 WebRTC 连接**
   - 点击连接按钮
   - 查看网络面板确认使用了正确的 ICE 服务器
   - 验证视频流是否正常播放

## 📋 配置说明

### ICE 服务器
- **STUN 服务器**: `stun:stun.l.google.com:19302`
  - 用于 NAT 穿透
  - 帮助客户端发现公网 IP

### 端口范围
- **范围**: 10110-10115
- **公网 IP**: 51.161.209.200
- **协议**: TCP 和 UDP

### SDP 语义
- **值**: `unified-plan`
- 标准的 WebRTC SDP 格式

## 🚨 注意事项

1. **开发环境 vs 生产环境**
   - 开发环境可能不需要 STUN（localhost）
   - 生产环境必须使用后端提供的配置

2. **错误处理**
   - 配置获取失败时使用降级方案
   - 记录错误日志便于排查

3. **CORS 设置**
   - 确保后端 CORS 配置允许前端域名
   - 已在 management_api.py 中配置 `allow_origins=["*"]`

## 🔧 环境变量（可选）

如果需要在开发环境覆盖配置，可以在 `.env.development` 中添加：

```env
REACT_APP_BACKEND_URL=http://localhost:9000
REACT_APP_USE_WEBRTC_CONFIG=true
```

## 📊 测试清单

- [ ] 前端代码已修改
- [ ] 可以成功获取 WebRTC 配置
- [ ] 控制台显示正确的配置信息
- [ ] WebRTC 连接成功建立
- [ ] 视频流正常播放
- [ ] 音频正常工作
- [ ] 网络质量良好（检查丢包率）

## 🆘 故障排除

### 配置获取失败
```
检查：
1. 后端服务是否运行 (http://localhost:9000/health)
2. CORS 是否配置正确
3. 网络连接是否正常
```

### WebRTC 连接失败
```
检查：
1. ICE 服务器是否可访问
2. 防火墙是否阻止端口 10110-10115
3. 公网 IP 是否正确配置
4. 查看浏览器控制台的详细错误信息
```

### 视频不显示
```
检查：
1. WebRTC 连接状态
2. 视频轨道是否正确添加
3. videoRef 是否正确绑定
4. 查看 Network 面板的媒体流
```

## 📚 相关文档

- [WebRTC 端口配置](./gpuserver/WEBRTC_PORT_CONFIG.md)
- [后端配置说明](./gpuserver/.env)
- [WebRTC Streamer 实现](./gpuserver/webrtc_streamer.py)
