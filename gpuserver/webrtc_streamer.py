"""
WebRTC Real-time Video Streamer

Provides real-time video streaming using WebRTC for avatar responses.
This allows for low-latency, frame-by-frame video transmission.

Architecture:
- Signaling: WebSocket (port 9001) via frp tunnel to Web Server (port 19001)
- Media: WebRTC with custom STUN/TURN server (coturn on port 10110)
- TURN server handles NAT traversal and relay on ports 10110-10115
"""

import asyncio
import logging
import uuid
import re
import os
import time
from datetime import datetime
from typing import Optional, Dict
import numpy as np
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack, RTCIceServer, RTCConfiguration
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame, AudioFrame
import fractions
import socket
import base64
import io
import av

logger = logging.getLogger(__name__)

# 延迟加载配置，避免循环导入
_config = None

def get_webrtc_config():
    """获取WebRTC配置"""
    global _config
    if _config is None:
        from config import settings
        _config = {
            'public_ip': settings.webrtc_public_ip,
            'port_min': settings.webrtc_port_min,
            'port_max': settings.webrtc_port_max,
            'stun_server': settings.webrtc_stun_server,
            'turn_server': getattr(settings, 'webrtc_turn_server', 'turn:51.161.209.200:10110'),
            'turn_server_local': getattr(settings, 'webrtc_turn_server_local', 'turn:127.0.0.1:10110'),
            'turn_username': getattr(settings, 'webrtc_turn_username', 'vtuser'),
            'turn_password': getattr(settings, 'webrtc_turn_password', 'vtpass'),
        }
    return _config


# 全局共享启动时间 - 确保音视频同步
_shared_start_time = None
# 全局数据就绪事件 - 当 process_frames_worker 开始推送时设置
_data_ready_event = None
# 是否已触发同步
_sync_triggered = False


def trigger_av_sync():
    """触发音视频同步 - 由 process_frames_worker 在推送第一帧时调用"""
    global _shared_start_time, _data_ready_event, _sync_triggered
    
    if _sync_triggered:
        return
    
    _sync_triggered = True
    _shared_start_time = time.time()
    
    if _data_ready_event:
        # 使用 call_soon_threadsafe 在事件循环中设置事件
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(_data_ready_event.set)
        except:
            pass
    
    logger.info(f"🎬 AV sync triggered at {_shared_start_time}")


class AvatarVideoTrack(VideoStreamTrack):
    """
    Custom video track - 完全照搬 try/lip-sync/webrtc.py PlayerStreamTrack
    
    关键改动：
    1. 队列存储 (frame, eventpoint) 元组
    2. next_timestamp() 控制帧率
    3. recv() 使用 sleep 等待，保持节奏
    4. 与 AvatarAudioTrack 共享 _start 时间确保同步
    """

    def __init__(self, idle_frames=None):
        super().__init__()
        # 队列存储 (frame, eventpoint) 元组 - 照搬 try
        self._queue = asyncio.Queue()
        
        self._timestamp = None
        self._start = None
        self.current_frame_count = 0
        
        self.idle_frames = idle_frames or []
        self.idle_frame_index = 0
        
        # 时间常量 - 与 try 完全一致
        self.VIDEO_PTIME = 0.040  # 40ms = 25fps
        self.VIDEO_CLOCK_RATE = 90000
        self.VIDEO_TIME_BASE = fractions.Fraction(1, self.VIDEO_CLOCK_RATE)
        
        # 统计
        self.framecount = 0
        self.lasttime = time.perf_counter()
        self.totaltime = 0
        
        # 数据开始标志 - 收到实际数据前不推进时间戳
        self._data_started = False

    async def next_timestamp(self):
        """
        计算下一帧的时间戳
        """
        global _shared_start_time
        
        # 如果还没收到实际数据，等待并返回时间戳 0
        if not self._data_started:
            await asyncio.sleep(self.VIDEO_PTIME)
            return 0, self.VIDEO_TIME_BASE
        
        if self._timestamp is not None:
            self._timestamp += int(self.VIDEO_PTIME * self.VIDEO_CLOCK_RATE)
            self.current_frame_count += 1
            
            # 计算需要等待的时间
            wait = self._start + self.current_frame_count * self.VIDEO_PTIME - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
        else:
            # 使用共享启动时间确保音视频同步
            self._start = _shared_start_time if _shared_start_time else time.time()
            self._timestamp = 0
            logger.info(f"📺 Video track sync start: {self._start}")
        
        return self._timestamp, self.VIDEO_TIME_BASE
    
    async def recv(self):
        """
        接收下一帧 - 收到实际数据前用 idle frame，收到后开始同步
        """
        # 尝试从队列获取帧
        try:
            item = self._queue.get_nowait()
            
            if isinstance(item, tuple):
                frame, eventpoint = item
            else:
                frame = item
            
            if frame is not None:
                # 收到实际数据，标记开始
                if not self._data_started:
                    self._data_started = True
                    logger.info("📺 Video: First real frame received, starting sync")
            else:
                frame = self._get_idle_frame()
            
        except asyncio.QueueEmpty:
            frame = self._get_idle_frame()
        
        # 计算时间戳
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        
        # 统计 FPS
        self.totaltime += (time.perf_counter() - self.lasttime)
        self.framecount += 1
        self.lasttime = time.perf_counter()
        
        if self.framecount == 100:
            logger.info(f"📺 Video avg fps: {self.framecount/self.totaltime:.2f}")
            self.framecount = 0
            self.totaltime = 0
        
        return frame
    
    def _get_idle_frame(self):
        """获取 idle frame"""
        if self.idle_frames and len(self.idle_frames) > 0:
            idle_frame = self.idle_frames[self.idle_frame_index]
            self.idle_frame_index = (self.idle_frame_index + 1) % len(self.idle_frames)
            return VideoFrame.from_ndarray(idle_frame, format="bgr24")
        else:
            return VideoFrame.from_ndarray(np.zeros((512, 512, 3), dtype=np.uint8), format="bgr24")

    def set_idle_frames(self, frames: list):
        """设置待机帧"""
        self.idle_frames = frames
        self.idle_frame_index = 0
        logger.info(f"Set {len(frames)} idle frames for WebRTC track")
    
    async def end_stream(self):
        """结束流"""
        await self._queue.put((None, None))


class AvatarAudioTrack(AudioStreamTrack):
    """
    Audio track - 照搬 try/lip-sync/webrtc.py PlayerStreamTrack (audio)
    """

    def __init__(self):
        super().__init__()
        # 队列存储 (frame, eventpoint) 元组 - 照搬 try
        self._queue = asyncio.Queue()
        
        self._timestamp = None
        self._start = None
        self.current_frame_count = 0
        
        # 时间常量 - 与 try 完全一致
        self.AUDIO_PTIME = 0.020  # 20ms
        self.SAMPLE_RATE = 16000
        self.AUDIO_TIME_BASE = fractions.Fraction(1, self.SAMPLE_RATE)
        
        # 数据开始标志 - 收到实际数据前不推进时间戳
        self._data_started = False
    
    async def next_timestamp(self):
        """计算下一帧的时间戳 - 与视频同步"""
        global _shared_start_time
        
        # 如果还没收到实际数据，等待并返回时间戳 0
        if not self._data_started:
            await asyncio.sleep(self.AUDIO_PTIME)
            return 0, self.AUDIO_TIME_BASE
        
        if self._timestamp is not None:
            self._timestamp += int(self.AUDIO_PTIME * self.SAMPLE_RATE)
            self.current_frame_count += 1
            
            # 计算需要等待的时间
            wait = self._start + self.current_frame_count * self.AUDIO_PTIME - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
        else:
            # 使用共享启动时间确保音视频同步
            self._start = _shared_start_time if _shared_start_time else time.time()
            self._timestamp = 0
            logger.info(f"🔊 Audio track sync start: {self._start}")
        
        return self._timestamp, self.AUDIO_TIME_BASE
    
    async def recv(self):
        """接收下一个音频帧 - 收到实际数据前用静音，收到后开始同步"""
        # 尝试从队列获取帧
        try:
            item = self._queue.get_nowait()
            
            if isinstance(item, tuple):
                frame, eventpoint = item
            else:
                frame = item
            
            if frame is not None:
                # 收到实际数据，标记开始
                if not self._data_started:
                    self._data_started = True
                    logger.info("🔊 Audio: First real frame received, starting sync")
            else:
                frame = self._get_silence_frame()
            
        except asyncio.QueueEmpty:
            frame = self._get_silence_frame()
        
        # 计算时间戳
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame
    
    def _get_silence_frame(self):
        """获取静音帧"""
        silence = np.zeros(320, dtype=np.int16)
        frame = AudioFrame(format='s16', layout='mono', samples=320)
        frame.planes[0].update(silence.tobytes())
        frame.sample_rate = 16000
        return frame


class WebRTCStreamer:
    """
    WebRTC Streamer for real-time avatar video

    Manages WebRTC peer connections and video streaming.
    """

    def __init__(self):
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.video_tracks: Dict[str, AvatarVideoTrack] = {}
        self.audio_tracks: Dict[str, AvatarAudioTrack] = {}  # 音频轨道字典
        self.websockets: Dict[str, any] = {}  # Store WebSocket connections for sending ICE candidates
        logger.info("WebRTC Streamer initialized with custom STUN/TURN server")

    async def create_peer_connection(self, session_id: str, idle_frames=None, websocket=None) -> RTCPeerConnection:
        """
        Create a new WebRTC peer connection

        Args:
            session_id: Session identifier
            idle_frames: Optional list of idle video frames for looping
            websocket: WebSocket connection for sending ICE candidates

        Returns:
            RTCPeerConnection: New peer connection
        """
        # 重置共享启动时间和数据就绪事件 - 确保每个新连接的音视频同步
        global _shared_start_time, _data_ready_event, _sync_triggered
        _shared_start_time = None
        _data_ready_event = asyncio.Event()
        _sync_triggered = False
        
        # 获取WebRTC配置
        config = get_webrtc_config()

        # 配置 TURN 服务器
        # ⚠️ 关键：GPU服务器必须使用本地 TURN 地址 (127.0.0.1)
        # 因为 GPU 服务器在 Docker 容器内，无法从内部连接到自己的公网 IP
        local_turn = config['turn_server_local']  # turn:127.0.0.1:10110
        ice_servers = [
            RTCIceServer(
                urls=[config['stun_server']],
            ),
            RTCIceServer(
                urls=[local_turn],  # 使用本地 TURN 地址
                username=config['turn_username'],
                credential=config['turn_password']
            )
        ]

        # aiortc 的 RTCConfiguration 只支持 iceServers 和 bundlePolicy
        configuration = RTCConfiguration(
            iceServers=ice_servers
        )

        logger.info(f"WebRTC configuration for session {session_id}:")
        logger.info(f"  STUN server: {config['stun_server']}")
        logger.info(f"  TURN server (GPU local): {local_turn}")
        logger.info(f"  TURN server (frontend): {config['turn_server']}")
        logger.info(f"  TURN username: {config['turn_username']}")
        logger.info(f"  Port range: {config['port_min']}-{config['port_max']}")

        pc = RTCPeerConnection(configuration=configuration)
        self.connections[session_id] = pc

        # Store WebSocket for sending ICE candidates
        if websocket:
            self.websockets[session_id] = websocket

        # 预声明 transceiver (避免动态添加导致 SDP 协商失败)
        video_transceiver = pc.addTransceiver('video', direction='sendrecv')
        audio_transceiver = pc.addTransceiver('audio', direction='sendrecv')

        # 创建视频轨道
        video_track = AvatarVideoTrack(idle_frames=idle_frames)
        self.video_tracks[session_id] = video_track

        # 创建音频轨道
        audio_track = AvatarAudioTrack()
        self.audio_tracks[session_id] = audio_track

        # 替换 transceiver 的 sender track
        video_transceiver.sender.replaceTrack(video_track)
        audio_transceiver.sender.replaceTrack(audio_track)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"WebRTC connection state: {pc.connectionState}")
            
            # 通知前端连接状态变化
            if session_id in self.websockets:
                try:
                    await self.websockets[session_id].send_json({
                        "type": "webrtc_state",
                        "state": pc.connectionState,
                        "timestamp": datetime.now().isoformat()
                    })
                    logger.info(f"Sent WebRTC state to frontend: {pc.connectionState}")
                except Exception as e:
                    logger.error(f"Failed to send WebRTC state: {e}")
            
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await self.close_connection(session_id)

        @pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            logger.info(f"ICE gathering state: {pc.iceGatheringState}")

        logger.info(f"WebRTC peer connection created for session {session_id}")
        return pc

    async def _send_ice_candidates_from_sdp(self, sdp: str, session_id: str, websocket):
        """
        Extract ICE candidates from SDP and send them to the client

        aiortc includes ICE candidates in the SDP answer, but browsers
        expect to receive them via onicecandidate events. This method
        extracts candidates from SDP and sends them separately.

        Args:
            sdp: SDP string containing ICE candidates
            session_id: Session identifier
            websocket: WebSocket connection for sending candidates
        """
        try:
            lines = sdp.split('\n')
            sdp_mline_index = -1
            sdp_mid = None

            for line in lines:
                # Track media line index
                if line.startswith('m='):
                    sdp_mline_index += 1

                # Extract mid from a=mid line
                if line.startswith('a=mid:'):
                    sdp_mid = line.split(':', 1)[1].strip()

                # Extract ICE candidates
                if line.startswith('a=candidate:'):
                    candidate_str = line[2:]  # Remove 'a=' prefix

                    # Log full candidate for debugging
                    logger.info(f"Full candidate from SDP: {candidate_str}")

                    # 只发送 relay 类型的 candidates 到前端
                    # 原因：只有 10110-10115 端口被映射到公网，其他端口无法从外部访问
                    if 'typ relay' not in candidate_str:
                        logger.info(f"Skipping non-relay candidate (port not accessible): {candidate_str[:60]}...")
                        continue

                    # Send candidate to client
                    await websocket.send_json({
                        "type": "webrtc_ice_candidate",
                        "candidate": {
                            "candidate": candidate_str,
                            "sdpMLineIndex": sdp_mline_index,
                            "sdpMid": sdp_mid
                        }
                    })
                    logger.info(f"Sent relay ICE candidate to client for session {session_id}: {candidate_str[:60]}...")

            logger.info(f"Finished sending ICE candidates for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to extract and send ICE candidates: {e}")

    def _modify_sdp_for_public_ip(self, sdp: str) -> str:
        """
        修改SDP，将内网IP替换为公网IP，并只保留relay类型的candidates

        Args:
            sdp: 原始SDP字符串

        Returns:
            str: 修改后的SDP字符串
        """
        config = get_webrtc_config()
        public_ip = config['public_ip']

        # 替换 c= 行中的IP地址
        # c=IN IP4 192.168.x.x -> c=IN IP4 51.161.209.200
        sdp = re.sub(r'c=IN IP4 \d+\.\d+\.\d+\.\d+', f'c=IN IP4 {public_ip}', sdp)

        # 过滤candidates：只保留relay类型，移除host和srflx类型
        # 原因：只有 10110-10115 端口被映射到公网，其他端口（如 39498）无法访问
        lines = sdp.split('\n')
        modified_lines = []

        for line in lines:
            if line.startswith('a=candidate'):
                # 只保留 typ relay 的 candidates
                if 'typ relay' in line:
                    modified_lines.append(line)
                    logger.debug(f"Keeping relay candidate: {line}")
                else:
                    logger.debug(f"Removing non-relay candidate (inaccessible port): {line}")
            else:
                modified_lines.append(line)

        sdp = '\n'.join(modified_lines)
        logger.info(f"Modified SDP: replaced IPs with {public_ip}, kept only relay candidates")
        return sdp

    async def handle_offer(
        self,
        session_id: str,
        offer_sdp: str,
        idle_frames=None,
        websocket=None
    ) -> str:
        """
        Handle WebRTC offer from client

        Args:
            session_id: Session identifier
            offer_sdp: SDP offer from client
            idle_frames: Optional list of idle video frames for looping
            websocket: WebSocket connection for sending ICE candidates

        Returns:
            str: SDP answer
        """
        # Check if connection exists and is still open
        if session_id in self.connections:
            pc = self.connections[session_id]
            # If connection is closed, clean it up first
            if pc.connectionState == "closed" or pc.signalingState == "closed":
                logger.info(f"Cleaning up closed connection for session {session_id}")
                await self.close_connection(session_id)
        
        # Create peer connection if not exists (or was just cleaned up)
        if session_id not in self.connections:
            await self.create_peer_connection(session_id, idle_frames=idle_frames, websocket=websocket)

        pc = self.connections[session_id]

        # Set remote description (offer)
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await pc.setRemoteDescription(offer)

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # 等待 ICE gathering 完成（确保获取到所有candidates包括TURN relay）
        # 如果 gathering 状态已经是 'complete'，这个循环会立即退出
        max_wait = 5  # 最多等待5秒
        waited = 0
        while pc.iceGatheringState != "complete" and waited < max_wait:
            await asyncio.sleep(0.1)
            waited += 0.1
        
        if pc.iceGatheringState != "complete":
            logger.warning(f"ICE gathering not complete after {max_wait}s, proceeding anyway")
        else:
            logger.info(f"ICE gathering completed in {waited:.2f}s")

        # 修改SDP以使用公网IP
        modified_sdp = self._modify_sdp_for_public_ip(pc.localDescription.sdp)

        # Extract and send ICE candidates from SDP to client
        # aiortc includes ICE candidates in the SDP, but browsers expect them separately
        if websocket:
            await self._send_ice_candidates_from_sdp(modified_sdp, session_id, websocket)

        logger.info(f"WebRTC answer created for session {session_id}")
        return modified_sdp

    async def add_ice_candidate(
        self,
        session_id: str,
        candidate: dict
    ):
        """
        Add ICE candidate from client

        Args:
            session_id: Session identifier
            candidate: ICE candidate data (RTCIceCandidate object or dict)
        """
        if session_id in self.connections:
            pc = self.connections[session_id]
            try:
                # 从前端传来的candidate可能是一个对象，需要提取字段
                if isinstance(candidate, dict):
                    # 如果是字典，提取candidate字段
                    candidate_str = candidate.get('candidate')
                    sdp_mid = candidate.get('sdpMid')
                    sdp_mline_index = candidate.get('sdpMLineIndex')
                else:
                    # 如果已经是字符串或对象，直接使用
                    candidate_str = str(candidate)
                    sdp_mid = None
                    sdp_mline_index = None

                # 使用aiortc的candidate_from_sdp解析candidate字符串
                from aiortc.sdp import candidate_from_sdp
                ice_candidate = candidate_from_sdp(candidate_str)

                # 设置sdpMid和sdpMLineIndex
                ice_candidate.sdpMid = sdp_mid
                ice_candidate.sdpMLineIndex = sdp_mline_index

                await pc.addIceCandidate(ice_candidate)
                logger.info(f"ICE candidate added for session {session_id}: {candidate_str[:50] if candidate_str else 'None'}...")
            except Exception as e:
                logger.error(f"Failed to add ICE candidate for session {session_id}: {e}")
                logger.error(f"Candidate data: {candidate}")
        else:
            logger.warning(f"No connection found for session {session_id} when adding ICE candidate")

    async def stream_frame(self, session_id: str, frame: np.ndarray):
        """
        Stream a single frame to the client

        Args:
            session_id: Session identifier
            frame: numpy array (H, W, 3) in BGR format
        """
        if session_id in self.video_tracks:
            video_track = self.video_tracks[session_id]
            await video_track.add_frame(frame)
        else:
            logger.warning(f"No video track found for session {session_id}")

    async def prepare_audio_chunks(self, audio_base64: str) -> list:
        """
        预先准备音频 chunks（用于同步推送）
        与 try 的实现保持一致：16kHz, 320 samples/chunk

        Args:
            audio_base64: base64 encoded audio (MP3 or WAV)

        Returns:
            list: 音频 chunk 列表，每个 chunk 是 320 samples (20ms @ 16kHz) 的 numpy array
        """
        try:
            # 解码 base64
            audio_bytes = base64.b64decode(audio_base64)

            # 使用 PyAV 解码音频
            container = av.open(io.BytesIO(audio_bytes))
            audio_stream = container.streams.audio[0]

            # 重采样到 16kHz, s16, mono（与 try 保持一致）
            resampler = av.audio.resampler.AudioResampler(
                format='s16',
                layout='mono',
                rate=16000  # 16kHz
            )

            chunks = []
            for packet in container.demux(audio_stream):
                for frame in packet.decode():
                    # 重采样
                    resampled_frames = resampler.resample(frame)

                    for resampled_frame in resampled_frames:
                        # 转换为 numpy array
                        audio_data = resampled_frame.to_ndarray()[0]  # (samples,)

                        # 分块为 320 samples (20ms @ 16kHz)
                        for i in range(0, len(audio_data), 320):
                            chunk = audio_data[i:i+320]
                            if len(chunk) == 320:
                                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Failed to prepare audio chunks: {e}", exc_info=True)
            return []

    async def stream_audio(self, session_id: str, audio_base64: str):
        """
        Stream audio to WebRTC audio track（独立推送，用于非同步场景）

        Args:
            session_id: Session identifier
            audio_base64: base64 encoded audio (MP3 or WAV)
        """
        if session_id not in self.audio_tracks:
            logger.warning(f"Audio track not found for session {session_id}")
            return

        try:
            audio_track = self.audio_tracks[session_id]
            logger.info(f"[Audio] Starting audio preparation for {session_id}, audio_base64 length: {len(audio_base64)}")
            
            chunks = await self.prepare_audio_chunks(audio_base64)
            
            logger.info(f"[Audio] Prepared {len(chunks)} chunks for {session_id}")
            
            # 逐个推送 chunks
            for i, chunk in enumerate(chunks):
                await audio_track.add_audio_chunk(chunk)
                if i == 0:
                    logger.info(f"[Audio] ⚡ First chunk pushed")
                if (i + 1) % 50 == 0:
                    logger.info(f"[Audio] 📤 Pushed {i + 1}/{len(chunks)} chunks")

            logger.info(f"[Audio] ✅ Completed: {len(chunks)} chunks (~{len(chunks) * 20}ms)")

        except Exception as e:
            logger.error(f"Failed to stream audio: {e}", exc_info=True)

    def set_idle_frames(self, session_id: str, frames: list):
        """
        Set idle video frames for a session

        Args:
            session_id: Session identifier
            frames: List of numpy arrays (H, W, 3) in BGR format
        """
        if session_id in self.video_tracks:
            video_track = self.video_tracks[session_id]
            video_track.set_idle_frames(frames)
        else:
            logger.warning(f"No video track found for session {session_id}")

    async def close_connection(self, session_id: str):
        """
        Close WebRTC connection

        Args:
            session_id: Session identifier
        """
        # 检查连接是否存在（避免重复关闭导致 KeyError）
        if session_id not in self.connections:
            logger.debug(f"Connection {session_id} already closed or not found")
            return
        
        if session_id in self.video_tracks:
            track = self.video_tracks[session_id]
            if hasattr(track, 'end_stream'):
                try:
                    await track.end_stream()
                except Exception as e:
                    logger.debug(f"Error ending video stream: {e}")
            del self.video_tracks[session_id]

        if session_id in self.audio_tracks:
            del self.audio_tracks[session_id]

        if session_id in self.connections:
            await self.connections[session_id].close()
            del self.connections[session_id]
        
        # 清理 WebSocket 引用
        if session_id in self.websockets:
            del self.websockets[session_id]

        logger.info(f"WebRTC connection closed for session {session_id}")


# Global WebRTC streamer instance
_webrtc_streamer: Optional[WebRTCStreamer] = None


def get_webrtc_streamer() -> WebRTCStreamer:
    """
    Get global WebRTC streamer instance (singleton)

    Returns:
        WebRTCStreamer: Global streamer instance
    """
    global _webrtc_streamer

    if _webrtc_streamer is None:
        _webrtc_streamer = WebRTCStreamer()
        logger.info("WebRTC streamer initialized")

    return _webrtc_streamer
