# WebRTC 端口配置

## 客户提供的端口映射

Docker端口 10110-10115 已映射到公网服务器：
- **公网IP**: `51.161.209.200`
- **端口范围**: `10110-10115`
- **协议**: TCP 和 UDP 都已启用

## 配置位置

### .env 文件
```bash
WEBRTC_PUBLIC_IP=51.161.209.200
WEBRTC_PORT_MIN=10110
WEBRTC_PORT_MAX=10115
WEBRTC_STUN_SERVER=stun:stun.l.google.com:19302
```

### config.py
已添加 WebRTC 配置项

### webrtc_streamer.py
- 使用配置的 STUN 服务器
- 自动修改 SDP 将内网IP替换为公网IP
- 确保客户端使用公网地址连接

## 验证

查看日志确认配置生效：
```bash
tail -f /workspace/gpuserver/logs/websocket_server.log | grep "STUN"
```

预期看到：`WebRTC peer connection created for session X with STUN: stun:stun.l.google.com:19302`
