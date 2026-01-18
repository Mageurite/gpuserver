# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Virtual Tutor System - A multi-tenant AI-powered virtual tutor platform built on Sozio.AI. The system enables teachers/administrators to create dedicated virtual tutors that students interact with through real-time voice, video, and text communication.

**Architecture**: Dual-server setup connected via FRP tunnel
- **Web Server (Server A)**: Located on a separate server, runs React frontend (port 3000) + FastAPI backend (port 8000) - handles authentication, management, and data persistence
- **GPU Server (Current Server)**: AI inference engines running LLM, ASR/TTS, and MuseTalk video generation
  - Management API: Port 9000
  - WebSocket API: Port 9001
  - WebRTC TURN: Port 10110 (UDP ports 10110-10115 mapped to public IP 51.161.209.200)
  - **Connection**: Servers connected via FRP tunnel
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
- **TURN server**: Required for NAT traversal, running on port 10110
- **Port constraint**: aiortc MUST use TURN relay because only UDP 10110-10115 are accessible from internet

Key files: `webrtc_streamer.py`, `api/websocket_server.py`

The streamer supports idle video frames that loop when no active speech is being generated.

**Important**: WebRTC connections will fail if:
1. TURN server is not running or not configured
2. Frontend uses `iceTransportPolicy: "all"` instead of `"relay"`
3. Ports outside 10110-10115 range are attempted (they won't be accessible)

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
- `WEBRTC_PORT_MIN`, `WEBRTC_PORT_MAX`: Port range for media
- `WEBRTC_STUN_SERVER`: STUN server URL
- `WEBRTC_TURN_SERVER`: TURN server URL (e.g., turn:51.161.209.200:10110)
- `WEBRTC_TURN_USERNAME`, `WEBRTC_TURN_PASSWORD`: TURN credentials

**MuseTalk/Avatar Configuration**:
- `ENABLE_AVATAR`: Enable MuseTalk video generation
- `AVATARS_DIR`: Avatar storage directory (default: /workspace/gpuserver/data/avatars)
- `MUSETALK_BASE`: MuseTalk code directory (default: /workspace/MuseTalk)
- `MUSETALK_CONDA_ENV`: Optional conda environment path for MuseTalk
- `FFMPEG_PATH`: Path to ffmpeg binary

### Network Deployment Scenarios

| Scenario | Web Server ENGINE_URL | GPU Server WEBSOCKET_URL |
|----------|------------------------|---------------------------|
| Local dev | http://127.0.0.1:9000 | ws://127.0.0.1:9001 |
| LAN | http://192.168.1.100:9000 | ws://192.168.1.100:9001 |
| Public IP | http://gpu-public-ip:9000 | ws://gpu-public-ip:9001 |
| FRP tunnel | http://gpu-server.frp.example.com | - |

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

1. **Web Server configuration**: Set `ENGINE_URL=http://<gpu-server-ip>:9000` in Web Server's `.env` (via FRP tunnel endpoint)
2. **Session creation flow**:
   - User initiates conversation on frontend
   - Web Server calls GPU Server through FRP: `POST http://gpu-server:9000/v1/sessions`
   - GPU Server returns `engine_url` and `engine_token`
   - Frontend connects to WebSocket using returned credentials (via FRP tunnel)
   - WebRTC media flows through UDP ports 10110-10115 (Docker port mapping to 51.161.209.200)
3. **Testing the connection**:
   ```bash
   # From Web Server machine, test GPU Server connectivity (via FRP)
   curl http://<frp-endpoint>:9000/health

   # From GPU Server, check TURN server status
   ss -tulnp | grep 10110

   # Verify UDP port mapping
   # These ports should be mapped: 10110-10115 UDP → 51.161.209.200:10110-10115
   ```

**Critical WebRTC Configuration**:
- Frontend MUST receive and use `iceTransportPolicy: "relay"` from backend config
- WebRTC media can ONLY use UDP ports 10110-10115 (no other ports will work)
- TURN server must be running on GPU Server port 10110
- Public IP 51.161.209.200 must be configured in `WEBRTC_PUBLIC_IP`

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
6. Monitor logs for TURN server usage: `tail -f /var/log/turnserver.log`
7. **Common symptom**: If seeing random ports like 44925 instead of 10110-10115, TURN relay is not working
8. **Port constraint failure**: Connections will fail if trying to use ports outside 10110-10115 (they are not accessible from internet)

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
- `gpuserver/api/management_api.py` (modified)
- `gpuserver/webrtc_streamer.py` (modified)

Recent commits focus on WebRTC video integration and session management improvements.

以后所有的临时文件、测试文件、和无关的md文件放到temp文件夹里

所有问题都用中文回答