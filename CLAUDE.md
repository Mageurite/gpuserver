# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Virtual Tutor System - A multi-tenant AI-powered virtual tutor platform built on Sozio.AI. The system enables teachers/administrators to create dedicated virtual tutors that students interact with through real-time voice, video, and text communication.

**Architecture**: Dual-server setup connected via FRP tunnel

### Server Addresses

- **GPU Server** (Current Server):
  - Internal IP: 172.17.0.3 (Docker container)
  - Host IP: 49.213.134.9:32537
  - Public IP: 51.161.209.200 (FRP mapped)
  - Management API: Port 9000 (FRP → 19000)
  - WebSocket API: Port 9001 (FRP → 19001)
  - TURN Server: Port 10110 (UDP 10110-10115 mapped to public IP)

- **Web Server** (Separate Machine):
  - Public IP: 51.161.130.234
  - React Frontend: Port 3000
  - FastAPI Backend: Port 8000
  - Connection to GPU: Via FRP tunnel

### Service Architecture

- **Web Server**: Handles authentication, management, and data persistence
- **GPU Server**: AI inference engines running LLM, ASR/TTS, and MuseTalk video generation
  - Management API: Port 9000 (mapped to 19000 via FRP)
  - WebSocket API: Port 9001 (mapped to 19001 via FRP)
  - WebRTC TURN: Port 10110 (UDP ports 10110-10115 mapped to public IP 51.161.209.200)
  - **Connection**: Servers connected via FRP tunnel for control/data plane
  - **Critical**: WebRTC media MUST use UDP ports 10110-10115 (only these ports are mapped through Docker to public server)

**Data Flow**:
1. Control plane: Web Server → FRP tunnel → `POST /v1/sessions` on GPU Server → returns `engine_url` + `engine_token`
2. Data plane: Frontend → FRP tunnel → `ws://gpu-server:9000/ws/ws/{session_id}?token={token}` → real-time conversation
3. Media plane: Frontend ↔ WebRTC relay (UDP 10110-10115) ↔ GPU Server (constrained to these ports only)
4. Session termination: Web Server → FRP tunnel → `DELETE /v1/sessions/{id}` → cleanup

## Repository Structure

```
/workspace/
├── gpuserver/              # GPU Server implementation (primary focus)
│   ├── api/
│   │   ├── management_api.py      # Session management API (port 9000)
│   │   └── websocket_server.py    # Real-time WebSocket API (port 9001)
│   ├── llm/llm_engine.py          # Ollama LLM integration (uses rag env)
│   ├── asr/asr_engine.py          # Whisper ASR integration (uses rag env)
│   ├── tts/tts_engine.py          # Edge TTS integration (uses tts env)
│   ├── rag/rag_engine.py          # RAG knowledge retrieval (uses rag env)
│   ├── musetalk/avatar_manager.py # Avatar video management (uses mt env)
│   ├── session_manager.py         # Session lifecycle management
│   ├── ai_models.py               # Main AI engine coordinator
│   ├── webrtc_streamer.py         # WebRTC video streaming
│   ├── config.py                  # Environment configuration
│   └── start_server.sh            # Server startup script (uses rag env)
├── MuseTalk/               # Video generation model (uses mt env)
├── try/                    # Reference implementations (DO NOT MODIFY)
│   ├── llm/                # LLM reference code (uses rag env)
│   ├── rag/                # RAG reference code (uses rag env)
│   ├── tts/                # TTS reference code (uses tts env)
│   └── lip-sync/           # MuseTalk reference code (uses avatar env)
└── virtual_tutor/          # Web Server (uses backend env, on separate machine)
```

## Development Commands

### Conda Virtual Environments

The project uses multiple conda environments for different components:

| Environment | Path | Purpose | Used By |
|-------------|------|---------|---------|
| `rag` | `/workspace/conda_envs/rag` | LLM and RAG services | GPU Server (primary), LLM engine |
| `mt` | `/workspace/conda_envs/mt` | MuseTalk video generation | MuseTalk avatar system |
| `avatar` | `/workspace/conda_envs/avatar` | Avatar processing (lip-sync) | Avatar video pipeline |
| `tts` | `/workspace/conda_envs/tts` | Text-to-speech synthesis | TTS engine |
| `backend` | `/workspace/conda_envs/backend` | Web server backend | Web Server (on separate machine) |
| `vtb` | `/workspace/conda_envs/vtb` | Virtual tutor base utilities | Shared utilities |

**Primary environment for GPU Server**: `rag` (contains FastAPI, langchain, ollama, and core dependencies)

### GPU Server Setup and Running

```bash
# Navigate to GPU server directory
cd /workspace/gpuserver

# Use conda environment (preferred)
export PATH="/workspace/conda_envs/rag/bin:$PATH"

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with appropriate settings

# Start services
bash start_server.sh                    # Start in background
bash start_server.sh --foreground       # Start in foreground

# Start individual services manually
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH \
  /workspace/conda_envs/rag/bin/python api/management_api.py

PYTHONPATH=/workspace/gpuserver:$PYTHONPATH \
  /workspace/conda_envs/rag/bin/python api/websocket_server.py

# Stop services
bash stop_server.sh
# Or kill by PID
ps aux | grep -E "(management_api|websocket_server)" | grep python | grep -v grep
kill <PID>
```

### Health Checks and Testing

```bash
# Check GPU server health
curl http://localhost:9000/health

# Check WebRTC configuration
curl http://localhost:9000/api/webrtc/config | python3 -m json.tool

# Test session creation
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'

# List active sessions
curl http://localhost:9000/v1/sessions

# Check port availability
ss -tulnp | grep -E "(9000|9001|10110)"

# Monitor logs
tail -f /workspace/gpuserver/logs/websocket_server.log
tail -f /workspace/gpuserver/logs/management_api.log
```

### LLM and Ollama

```bash
# Check Ollama status
curl http://127.0.0.1:11434/api/tags

# Pull a model
ollama pull mistral-nemo:12b-instruct-2407-fp16

# List available models
ollama list
```

## Key Architecture Patterns

### Session Management

The system uses a dual-mode session architecture:
1. **New mode** (user-based): `connection_id = "user_{user_id}"` - One WebSocket connection per user, supports multiple sessions
2. **Legacy mode** (session-based): `connection_id = "{session_id}"` - One WebSocket per session

Sessions are managed by `session_manager.py` with:
- Token-based authentication via `engine_token`
- Automatic timeout cleanup (configurable via `SESSION_TIMEOUT_SECONDS`)
- Maximum concurrent session limits (`MAX_SESSIONS`)

### AI Engine Architecture

`AIEngine` class (in `ai_models.py`) coordinates multiple AI components:
- **LLM Engine**: Ollama integration via langchain-ollama, supports per-tutor model configuration
- **ASR Engine**: Whisper-based speech recognition
- **TTS Engine**: Edge TTS for speech synthesis
- **RAG Engine**: Knowledge base retrieval (placeholder for future implementation)
- **Video Engine**: MuseTalk integration for lip-sync avatar generation

Each `tutor_id` gets its own `AIEngine` instance for model isolation. Configure per-tutor models via environment variables: `TUTOR_{id}_LLM_MODEL=model-name`

### WebRTC Video Streaming

Real-time avatar video uses WebRTC with custom STUN/TURN configuration:
- **Signaling**: WebSocket on port 9001 (via FRP tunnel)
- **Media**: WebRTC with TURN relay (coturn on port 10110)
- **Port range**: **10110-10115 (UDP only)** - CRITICAL: Only these 6 UDP ports are mapped through Docker to public server at 51.161.209.200
- **Public IP**: 51.161.209.200 (configured via `WEBRTC_PUBLIC_IP` environment variable)
- **TURN server**: Self-hosted coturn on port 10110, required for NAT traversal
- **Port constraint**: aiortc MUST use TURN relay because only UDP 10110-10115 are accessible from internet

**双地址配置 (Critical)**:
- **GPU Server (aiortc)**: Uses `WEBRTC_TURN_SERVER_LOCAL=turn:127.0.0.1:10110` (local address, because GPU server is in Docker container at 172.17.0.3 and cannot access public IP)
- **Frontend (browser)**: Uses `WEBRTC_TURN_SERVER=turn:51.161.209.200:10110` (public address, returned by `/v1/webrtc/config` API)
- **Why**: GPU server in Docker container (172.17.0.3) cannot connect to its own public IP (51.161.209.200), must use localhost

**TURN Server Configuration** (`/etc/turnserver.conf`):
- **CRITICAL**: Must NOT have `no-loopback-peers` - this prevents relay-to-relay communication
- Configuration allows both peers to use the same TURN server and communicate through relay channels
- Port range: 10111-10115 (10110 is for TURN control, 10111-10115 for relay)

Key files: `webrtc_streamer.py`, `api/websocket_server.py`, `config.py`

The streamer supports idle video frames that loop when no active speech is being generated.

**Important**: WebRTC connections will fail if:
1. TURN server is not running or not configured
2. Frontend uses `iceTransportPolicy: "all"` instead of `"relay"`
3. Ports outside 10110-10115 range are attempted (they won't be accessible)
4. `/etc/turnserver.conf` has `no-loopback-peers` enabled (prevents relay-to-relay communication)
5. GPU server tries to use public IP instead of localhost for TURN connection
6. TURN server ports exhausted (only 5 ports available, restart TURN to clear: `kill <pid> && turnserver -c /etc/turnserver.conf -o &`)

### WebSocket Message Protocol

**Client to Server**:
```json
{
  "type": "text_webrtc" | "text" | "audio" | "webrtc_offer" | "webrtc_ice_candidate",
  "content": "user input text",
  "tutor_id": 1,              // Required: selects avatar video
  "session_id": 59,           // Optional: distinguishes chat history
  "engine_session_id": "uuid",// Optional: for session-based mode
  "user_id": 123,             // Required for WebRTC messages
  "avatar_id": "avatar_tutor_13", // Optional
  "kb_id": "kb-001"           // Optional: knowledge base ID
}
```

**Server to Client**:
```json
{
  "type": "text" | "audio" | "video" | "transcription" | "error",
  "content": "AI response",
  "role": "assistant",
  "timestamp": "2024-01-01T12:00:00"
}
```

### Multi-Tenant Model Isolation

- Avatar videos are shared by `tutor_id` (all students of a tutor see the same avatar)
- Chat history is separated by `session_id` (each student session has independent history)
- LLM models can be configured per `tutor_id` via environment variables

## Configuration

### Core Environment Variables

**Server Configuration**:
- `MANAGEMENT_API_HOST`: Management API bind address (default: 0.0.0.0)
- `MANAGEMENT_API_PORT`: Management API port (default: 9000)
- `WEBSOCKET_HOST`: WebSocket server bind address (default: 0.0.0.0)
- `WEBSOCKET_PORT`: WebSocket server port (default: 9001)
- `WEBSOCKET_URL`: WebSocket URL for clients (e.g., ws://localhost:9001)

**Session Management**:
- `MAX_SESSIONS`: Maximum concurrent sessions (default: 10)
- `SESSION_TIMEOUT_SECONDS`: Session timeout in seconds (default: 3600)

**LLM Configuration**:
- `ENABLE_LLM`: Enable real LLM (true) or use mock (false)
- `OLLAMA_BASE_URL`: Ollama API endpoint (default: http://127.0.0.1:11434)
- `DEFAULT_LLM_MODEL`: Default model name (e.g., mistral-nemo:12b-instruct-2407-fp16)
- `LLM_TEMPERATURE`: Response temperature (default: 0.4)
- `TUTOR_{id}_LLM_MODEL`: Per-tutor model override

**ASR/TTS Configuration**:
- `ENABLE_ASR`: Enable Whisper ASR (true) or mock (false)
- `ASR_MODEL`: Whisper model size (tiny, base, small, medium, large)
- `ASR_DEVICE`: Device for ASR (cuda or cpu)
- `ASR_LANGUAGE`: Default language (zh, en)
- `ENABLE_TTS`: Enable Edge TTS (true) or mock (false)
- `TTS_VOICE`: Voice name (e.g., zh-CN-XiaoxiaoNeural)

**WebRTC Configuration**:
- `WEBRTC_PUBLIC_IP`: Public IP for WebRTC (required for NAT traversal)
- `WEBRTC_PORT_MIN`, `WEBRTC_PORT_MAX`: Port range for media (10110-10115)
- `WEBRTC_STUN_SERVER`: STUN server URL (default: stun:stun.l.google.com:19302)
- `WEBRTC_TURN_SERVER`: TURN server URL for frontend (e.g., turn:51.161.209.200:10110)
- `WEBRTC_TURN_SERVER_LOCAL`: TURN server URL for GPU server (e.g., turn:127.0.0.1:10110) - CRITICAL for Docker deployment
- `WEBRTC_TURN_USERNAME`, `WEBRTC_TURN_PASSWORD`: TURN credentials (default: vtuser/vtpass)

**MuseTalk/Avatar Configuration**:
- `ENABLE_AVATAR`: Enable MuseTalk video generation
- `AVATARS_DIR`: Avatar storage directory (default: /workspace/gpuserver/data/avatars)
- `MUSETALK_BASE`: MuseTalk code directory (default: /workspace/MuseTalk)
- `MUSETALK_CONDA_ENV`: Optional conda environment path for MuseTalk
- `FFMPEG_PATH`: Path to ffmpeg binary

### Network Deployment Scenarios

| Scenario | Web Server ENGINE_URL | GPU Server WEBSOCKET_URL | Notes |
|----------|------------------------|---------------------------|-------|
| Current Production | http://51.161.209.200:19000 | ws://51.161.209.200:19001 | Via FRP tunnel |
| GPU Server Direct | http://51.161.209.200:19000 | ws://51.161.209.200:19001 | Public access |
| Web Server Internal | http://gpu-server-host:9000 | ws://gpu-server-host:9001 | Via FRP |
| Local dev (GPU) | http://127.0.0.1:9000 | ws://127.0.0.1:9001 | Direct local |

**Current Setup**:
- Web Server at 51.161.130.234 connects to GPU Server at 51.161.209.200:19000/19001 (via FRP)
- Frontend (browser) connects to ws://51.161.209.200:19001 for WebSocket
- Frontend uses TURN at turn:51.161.209.200:10110 for WebRTC media
- GPU Server uses TURN at turn:127.0.0.1:10110 (local address)

## API Endpoints

### Management API (Port 9000)

- `GET /health` - Health check
- `POST /v1/sessions` - Create new session
  - Request: `{"tutor_id": 1, "student_id": 123, "kb_id": "kb-001"}`
  - Response: `{"session_id": "uuid", "engine_url": "ws://...", "engine_token": "token", "status": "active"}`
- `GET /v1/sessions/{session_id}` - Query session status
- `DELETE /v1/sessions/{session_id}` - Terminate session
- `GET /v1/sessions` - List all active sessions (debug)

### Avatar Management API (Port 9000)

- `POST /v1/avatars` - Create avatar from video path
- `POST /v1/avatars/upload` - Create avatar from uploaded video file
- `GET /v1/avatars/{avatar_id}` - Get avatar info
- `DELETE /v1/avatars/{avatar_id}` - Delete avatar
- `GET /v1/avatars` - List all avatars

### WebRTC Configuration API (Port 9000)

- `GET /v1/webrtc/config` - Get WebRTC configuration (ICE servers, public IP, port range)

### WebSocket API (Port 9001)

- `ws://host:9001/ws/{connection_id}?token={token}` - WebSocket endpoint
- `ws://host:9001/ws/ws/{connection_id}?token={token}` - Alternative path (unified mode)

## Integration with Web Server

The GPU Server is designed to be called by the Web Server running on a separate machine, connected via FRP tunnel:

**Network Architecture**:
- **GPU Server**: Current server (this machine)
- **Web Server**: Separate server running frontend and backend
- **Connection**: FRP tunnel for HTTP/WebSocket, Docker port mapping (10110-10115 UDP) to 51.161.209.200 for WebRTC
- **Public IP**: 51.161.209.200 (only UDP ports 10110-10115 are accessible from internet)

**Integration Steps**:

1. **Web Server configuration**: Set `ENGINE_URL=http://51.161.209.200:19000` in Web Server's `.env` (FRP mapped port)
2. **Session creation flow**:
   - User initiates conversation on frontend at 51.161.130.234
   - Web Server backend calls GPU Server: `POST http://51.161.209.200:19000/v1/sessions`
   - GPU Server returns `engine_url` and `engine_token`
   - Frontend connects to WebSocket: `ws://51.161.209.200:19001/ws/user_{user_id}`
   - Frontend gets WebRTC config: `GET http://51.161.209.200:19000/v1/webrtc/config`
   - WebRTC media flows: Browser ↔ TURN(51.161.209.200:10110) ↔ GPU Server
3. **Testing the connection**:
   ```bash
   # From Web Server, test GPU Server connectivity
   curl http://51.161.209.200:19000/health

   # From GPU Server, verify services
   curl http://localhost:9000/health
   curl http://localhost:9000/v1/webrtc/config | python3 -m json.tool

   # Check TURN server status
   ss -tulnp | grep 10110
   ps aux | grep turnserver

   # Verify port mapping (from outside)
   # UDP ports 10110-10115 should be accessible on 51.161.209.200
   ```

**Critical WebRTC Configuration**:
- Frontend MUST receive and use `iceTransportPolicy: "relay"` from backend config
- WebRTC media can ONLY use UDP ports 10110-10115 (no other ports will work)
- TURN server must be running on GPU Server port 10110
- Public IP 51.161.209.200 must be configured in `WEBRTC_PUBLIC_IP`
- GPU Server MUST use local TURN address: `turn:127.0.0.1:10110`
- Frontend MUST use public TURN address: `turn:51.161.209.200:10110`
- TURN config must NOT have `no-loopback-peers` (prevents relay-to-relay communication)

**API Endpoints for Frontend**:
- WebSocket: `ws://51.161.209.200:19001/ws/user_{user_id}`
- WebRTC Config: `GET http://51.161.209.200:19000/v1/webrtc/config`
- Health Check: `GET http://51.161.209.200:19000/health`

## MuseTalk Avatar System

Located in `/workspace/MuseTalk/`, this provides lip-sync video generation using the `mt` conda environment:

**Conda Environment**: `/workspace/conda_envs/mt` (MuseTalk-specific dependencies)

**Functionality**:
- Processes uploaded teacher videos to extract avatar data
- Generates synchronized lip movements based on TTS audio
- Avatars stored in `/workspace/gpuserver/data/avatars/{avatar_id}/`
- Each avatar directory contains:
  - `full_imgs/`: Extracted video frames
  - `coords.pkl`: Face coordinate data
  - `latent.pt`: Latent representation

**Integration**: The `avatar_manager.py` in `gpuserver/musetalk/` handles avatar lifecycle and interfaces with MuseTalk.

## Important Constraints

1. **DO NOT modify** code in `try/` directory - it's reference implementation only
2. **DO NOT modify** Web Server code when working on GPU Server tasks (Web Server is on a separate machine)
3. **Session isolation**: Each `AIEngine` instance is tied to a specific `tutor_id` for model isolation
4. **WebRTC port constraints**:
   - **CRITICAL**: Only UDP ports 10110-10115 are mapped through Docker to public IP 51.161.209.200
   - WebRTC MUST use TURN relay on these ports - direct connections will fail
   - aiortc library does not support port range limitation, so TURN is mandatory
   - Frontend MUST use `iceTransportPolicy: "relay"` (not "all")
5. **Token validation**: All WebSocket connections must provide valid `engine_token` (obtained from session creation)
6. **FRP tunnel dependency**: GPU Server and Web Server communicate through FRP tunnel for control/data plane
7. **Environment isolation**: Use correct conda environment for each component (see Conda Virtual Environments section)

## Common Issues and Solutions

**LLM call failures**:
1. Verify Ollama is running: `curl http://127.0.0.1:11434/api/tags`
2. Verify model is installed: `ollama pull <model-name>`
3. Check environment variables: `ENABLE_LLM=true`, correct `OLLAMA_BASE_URL`

**WebSocket connection failures**:
1. Verify server is running: `curl http://localhost:9000/health`
2. Check path format: `ws://localhost:9000/ws/ws/{session_id}?token={token}` (note double `/ws`)
3. Validate token: Create session via management API first

**WebRTC connection issues**:
1. Verify TURN server is running: `ss -tulnp | grep 10110`
2. Check public IP configuration in `.env`: `WEBRTC_PUBLIC_IP=51.161.209.200`
3. **Verify UDP port mapping**: Docker must map ports 10110-10115 UDP to 51.161.209.200:10110-10115
4. Frontend must use `iceTransportPolicy: "relay"` from backend config (not hardcoded to "all")
5. Check TURN credentials: `WEBRTC_TURN_USERNAME=vtuser`, `WEBRTC_TURN_PASSWORD=vtpass`
6. Monitor TURN logs: `tail -f /var/log/turnserver.log`
7. **Port exhaustion**: If TURN shows "no available ports" errors, restart TURN server:
   ```bash
   ps aux | grep turnserver | grep -v grep | awk '{print $2}' | xargs kill -9
   turnserver -c /etc/turnserver.conf -o &
   ```
8. **Docker container TURN connection**: GPU server MUST use `turn:127.0.0.1:10110`, NOT public IP
9. **Relay-to-relay communication**: `/etc/turnserver.conf` must NOT have `no-loopback-peers` enabled
10. **ICE connection failure symptoms**:
    - Frontend: `ICE connection state: disconnected` or `failed`
    - GPU Server logs: `Check CandidatePair... State.IN_PROGRESS -> State.FAILED`
    - Solution: Verify TURN config and restart both TURN and GPU servers

**Frontend autoplay issues**:
- Modern browsers block autoplay of videos with audio
- Solution: Video element must have `muted` attribute for autoplay to work
- Can unmute after first user interaction

**Per-tutor model configuration**:
Add to `.env`: `TUTOR_{id}_LLM_MODEL=model-name` (e.g., `TUTOR_1_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16`)

**Session capacity limits**:
Increase `MAX_SESSIONS` in `.env`, adjust `SESSION_TIMEOUT_SECONDS` as needed

**Conda environment issues**:
1. Always activate correct environment for each component:
   - GPU Server (main): `export PATH="/workspace/conda_envs/rag/bin:$PATH"`
   - MuseTalk: Use `mt` environment
   - TTS: Use `tts` environment
   - Avatar processing: Use `avatar` environment
2. Check Python path: `which python` should point to correct conda environment
3. If dependencies missing: `pip install -r requirements.txt` in appropriate environment

**FRP tunnel issues**:
1. Verify FRP client is running: `ps aux | grep frp`
2. Check tunnel status for ports 9000, 9001
3. Test connectivity from Web Server through tunnel endpoint
4. Note: UDP ports 10110-10115 use Docker port mapping, not FRP

## Git Status

The repository currently has uncommitted changes in:
- `gpuserver/api/management_api.py` (modified - uses environment variable for TURN server)
- `gpuserver/webrtc_streamer.py` (modified - dual TURN address configuration)
- `gpuserver/config.py` (modified - added WEBRTC_TURN_SERVER_LOCAL)
- `gpuserver/.env` (modified - TURN server configuration)
- `/etc/turnserver.conf` (modified - removed no-loopback-peers)

Recent commits focus on WebRTC video integration and session management improvements.

## Critical WebRTC Fix (2026-01-19)

**Problem**: WebRTC connections failed with `ICE connection state: failed`

**Root Causes**:
1. TURN server had `no-loopback-peers` enabled, preventing relay-to-relay communication
2. GPU server in Docker (172.17.0.3) tried to connect to public IP (51.161.209.200) instead of localhost
3. Frontend had hardcoded `iceTransportPolicy: "all"` instead of using backend config value `"relay"`
4. TURN server port exhaustion (only 5 ports, no cleanup of stale allocations)

**Solutions Applied**:
1. Removed `no-loopback-peers` from `/etc/turnserver.conf`
2. Added dual TURN address configuration:
   - `WEBRTC_TURN_SERVER_LOCAL=turn:127.0.0.1:10110` (for GPU server)
   - `WEBRTC_TURN_SERVER=turn:51.161.209.200:10110` (for frontend)
3. Frontend now uses `iceTransportPolicy` from backend config
4. Restart TURN server when ports exhausted
5. Frontend video element requires `muted` attribute for autoplay

**Verification**:
- Frontend logs should show: `ICE connection state: connected`
- GPU Server logs should show: `ICE completed`, `WebRTC connection state: connected`
- Both sides should only generate `typ relay` candidates

以后所有的临时文件、测试文件、和无关的md文件放到temp文件夹里

所有问题都用中文回答

# GPU Server - WebRTC Avatar 项目

## 服务器说明
**当前服务器**: GPU Server (49.213.134.9:32537)
- 运行AI Avatar (MuseTalk)
- 提供WebRTC视频流
- 映射到公网 (51.161.209.200)

## 核心服务

| 服务 | 端口 | 状态 | PID |
|------|------|------|-----|
| WebSocket Server | 9001 | ✅ | 2267130 |
| Management API | 9000 | ✅ | 2284588 |
| TURN Server | 10110 | ✅ | 1822768 |

## 配置

### 网络配置

**GPU服务器**: 49.213.134.9:32537 (本机)
**公网IP**: 51.161.209.200 (FRP映射)
**端口映射**: 仅5个UDP端口 (10110-10115) 被映射到公网

### WebRTC配置 (`config.py`)
```python
webrtc_stun_server = "stun:stun.l.google.com:19302"
webrtc_turn_server = "turn:51.161.209.200:10110"
webrtc_turn_username = "vtuser"
webrtc_turn_password = "vtpass"
webrtc_public_ip = "51.161.209.200"  # FRP映射的公网IP
webrtc_port_min = 10110  # ⚠️ 仅这5个端口被映射到公网
webrtc_port_max = 10115
```

### TURN服务器 (`/etc/turnserver.conf`)
```ini
listening-port=10110
external-ip=51.161.209.200/172.17.0.3
min-port=10111
max-port=10115
user=vtuser:vtpass
realm=gpu-turn
```

## 已解决的问题 ✅

1. **ICE Candidates发送** - 从SDP提取并发送 (`webrtc_streamer.py:229-282`)
2. **ICE Candidate解析** - 使用`candidate_from_sdp()` (`webrtc_streamer.py:378-390`)
3. **TURN服务器配置** - 已配置并运行在端口10110
4. **前端配置获取** - Web服务器后端已添加`iceTransportPolicy`字段到`/api/webrtc/config`
5. **aiortc随机端口问题** - GPU服务器端过滤非relay类型的candidates (`webrtc_streamer.py:263-267, 301-315`)

## 解决方案总结 🎯

### 问题：aiortc生成随机端口的candidates

**根本原因**:
- aiortc库会生成3种类型的ICE candidates:
  - `typ host`: 使用随机端口（如37384, 59138）
  - `typ srflx`: STUN映射，也使用随机端口
  - `typ relay`: TURN中继，使用正确的端口范围10110-10115 ✅
- 即使配置了TURN服务器，aiortc仍然会生成所有类型的candidates
- 前端的`iceTransportPolicy: "relay"`只影响前端选择，不影响后端生成

**最终解决方案**:
1. **Web服务器端**: 在`/api/webrtc/config`响应中添加`iceTransportPolicy: "relay"`字段
2. **前端**: 使用后端配置中的`iceTransportPolicy`值（已修改）
3. **GPU服务器端**: 在发送candidates给前端时，过滤掉非relay类型的candidates

**关键代码修改** (`webrtc_streamer.py`):

```python
# 在 _send_ice_candidates_from_sdp 方法中 (lines 263-267)
if 'typ relay' not in candidate_str:
    logger.info(f"Skipping non-relay candidate: {candidate_str[:60]}...")
    continue  # 只发送relay类型的candidates

# 在 _modify_sdp_for_public_ip 方法中 (lines 301-315)
for line in lines:
    if line.startswith('a=candidate'):
        if 'typ relay' in line:
            modified_lines.append(line)  # 只保留relay candidates
        else:
            logger.debug(f"Removing non-relay candidate: {line}")
    else:
        modified_lines.append(line)
```

## 当前状态 ✅

**所有组件已修复**:
- ✅ TURN服务器运行在10110端口
- ✅ Web服务器返回`iceTransportPolicy: "relay"`配置
- ✅ 前端使用后端配置值
- ✅ GPU服务器过滤非relay candidates
- ✅ 所有WebRTC流量通过TURN中继（端口10110-10115）

**验证方法**:
- 前端日志显示: `iceTransportPolicy: "relay"`
- 出现 `typ relay` 类型的candidates
- ICE连接状态: `"connected"`

## 服务管理

### 启动
```bash
cd /workspace/gpuserver
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/websocket_server.py > logs/websocket_server_console.log 2>&1 &
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/management_api.py > logs/management_api_console.log 2>&1 &
```

### 停止
```bash
ps aux | grep -E "(management_api|websocket_server)" | grep python | grep -v grep
kill <PID>
```

### 查看日志
```bash
tail -f /workspace/gpuserver/logs/websocket_server_console.log
tail -f /workspace/gpuserver/logs/management_api_console.log
tail -f /var/log/turnserver.log
```

### 健康检查
```bash
curl http://localhost:9000/health
curl http://localhost:9000/api/webrtc/config | python3 -m json.tool
ss -tulnp | grep -E "(9000|9001|10110)"
```

## 待办事项

- [ ] 在Web服务器上修改前端代码
- [ ] 重新打包前端
- [ ] 验证TURN中继工作
- [ ] 切换回自建TURN服务器 (当前使用公共TURN测试)

## 文件位置

```
/workspace/gpuserver/          # GPU服务器代码（本服务器）
├── api/
│   ├── management_api.py
│   └── websocket_server.py
├── webrtc_streamer.py
├── config.py
├── logs/
└── CLAUDE.md (本文档)

/workspace/try/frontend/       # ⚠️ 参考代码，不能修改！
                               # 实际前端在Web服务器上（另一台服务器）
```

## 重要说明

⚠️ **服务器架构**
- **GPU服务器** (本机): 49.213.134.9:32537
- **公网IP**: 51.161.209.200 (映射)
- **端口限制**: 仅5个UDP端口 (10110-10115) 被映射到公网
- **Web服务器**: 另一台服务器，运行前端，通过FRP连接

⚠️ **前端代码不在本服务器上**
- `/workspace/try/frontend/` 仅供参考，不是实际使用的前端
- 实际前端在Web服务器上
- **前端修改需要在Web服务器上进行**

---
**更新**: 2026-01-06 19:50
**GPU服务器**: 49.213.134.9:32537 (SSH: `ssh new`)
**公网IP**: 51.161.209.200 (FRP映射，仅5个UDP端口)
**状态**: 🟡 等待Web服务器上修改前端代码
