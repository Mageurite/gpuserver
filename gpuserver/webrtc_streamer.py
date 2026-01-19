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


class AvatarVideoTrack(VideoStreamTrack):
    """
    Custom video track that streams avatar frames in real-time
    """

    def __init__(self, idle_frames=None):
        super().__init__()
        self.frame_queue = asyncio.Queue(maxsize=30)  # Buffer up to 30 frames
        self._timestamp = 0
        self._frame_count = 0
        self.idle_frames = idle_frames or []  # 待机视频帧列表
        self.idle_frame_index = 0  # 当前待机帧索引
        self.is_streaming = False  # 是否正在流式传输对话视频

    async def recv(self):
        """
        Receive next video frame

        Returns:
            VideoFrame: Next frame to send to client
        """
        try:
            # 尝试从队列获取帧（非阻塞）
            frame_data = await asyncio.wait_for(
                self.frame_queue.get(),
                timeout=0.04  # 40ms = 25fps
            )

            if frame_data is None:
                # End of stream signal
                raise StopAsyncIteration

            # 标记为正在流式传输
            self.is_streaming = True

            # Convert numpy array to VideoFrame
            frame = VideoFrame.from_ndarray(frame_data, format="bgr24")
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, 25)  # 25 fps

            self._timestamp += 1
            self._frame_count += 1

            return frame

        except asyncio.TimeoutError:
            # 队列为空，使用待机视频帧
            if self.idle_frames and len(self.idle_frames) > 0:
                # 循环播放待机视频
                idle_frame = self.idle_frames[self.idle_frame_index]
                self.idle_frame_index = (self.idle_frame_index + 1) % len(self.idle_frames)

                frame = VideoFrame.from_ndarray(idle_frame, format="bgr24")
                frame.pts = self._timestamp
                frame.time_base = fractions.Fraction(1, 25)
                self._timestamp += 1

                # 如果之前在流式传输，现在切换回待机
                if self.is_streaming:
                    logger.info("Switching back to idle video")
                    self.is_streaming = False

                return frame
            else:
                # 没有待机帧，发送黑屏
                black_frame = np.zeros((512, 512, 3), dtype=np.uint8)
                frame = VideoFrame.from_ndarray(black_frame, format="bgr24")
                frame.pts = self._timestamp
                frame.time_base = fractions.Fraction(1, 25)
                self._timestamp += 1
                return frame

    async def add_frame(self, frame: np.ndarray):
        """
        Add a frame to the streaming queue

        Args:
            frame: numpy array (H, W, 3) in BGR format
        """
        try:
            await self.frame_queue.put(frame)
        except asyncio.QueueFull:
            logger.warning("Frame queue full, dropping frame")

    def set_idle_frames(self, frames: list):
        """
        Set idle video frames for looping

        Args:
            frames: List of numpy arrays (H, W, 3) in BGR format
        """
        self.idle_frames = frames
        self.idle_frame_index = 0
        logger.info(f"Set {len(frames)} idle frames for WebRTC track")

    async def end_stream(self):
        """Signal end of stream"""
        await self.frame_queue.put(None)


class AvatarAudioTrack(AudioStreamTrack):
    """
    Custom audio track that streams TTS audio in real-time
    """

    def __init__(self):
        super().__init__()
        self.frame_queue = asyncio.Queue(maxsize=200)  # 缓冲约 4 秒
        self._timestamp = 0
        self._sample_rate = 48000  # WebRTC 标准采样率
        self._samples_per_frame = 960  # 20ms @ 48kHz

    async def recv(self):
        """
        Receive next audio frame (每 20ms 调用一次)

        Returns:
            AudioFrame: 960 samples @ 48kHz, s16, mono
        """
        try:
            # 尝试从队列获取音频数据
            audio_samples = await asyncio.wait_for(
                self.frame_queue.get(),
                timeout=0.02  # 20ms
            )

            if audio_samples is None:
                # End of stream signal
                raise StopAsyncIteration

            # 创建 AudioFrame
            frame = AudioFrame(format='s16', layout='mono', samples=self._samples_per_frame)
            frame.sample_rate = self._sample_rate
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, self._sample_rate)

            # 填充音频数据
            frame.planes[0].update(audio_samples.tobytes())

            self._timestamp += self._samples_per_frame

            return frame

        except asyncio.TimeoutError:
            # 队列为空,发送静音帧
            silence = np.zeros(self._samples_per_frame, dtype=np.int16)
            frame = AudioFrame(format='s16', layout='mono', samples=self._samples_per_frame)
            frame.sample_rate = self._sample_rate
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, self._sample_rate)
            frame.planes[0].update(silence.tobytes())

            self._timestamp += self._samples_per_frame

            return frame

    async def add_audio_chunk(self, audio_samples: np.ndarray):
        """
        Add audio samples to the streaming queue

        Args:
            audio_samples: numpy array (960,) dtype=int16
        """
        try:
            await self.frame_queue.put(audio_samples)
        except asyncio.QueueFull:
            logger.warning("Audio queue full, dropping chunk")


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
        # 获取WebRTC配置
        config = get_webrtc_config()

        # 配置 TURN 服务器（GPU服务器端使用本地地址）
        # GPU服务器在Docker容器内，使用127.0.0.1连接本地TURN服务器
        # 前端使用公网地址连接TURN服务器
        ice_servers = [
            RTCIceServer(
                urls=[config['stun_server']],
            ),
            RTCIceServer(
                urls=[config['turn_server_local']],  # 使用本地TURN地址
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
        logger.info(f"  TURN server (local): {config['turn_server_local']}")
        logger.info(f"  TURN server (public): {config['turn_server']}")
        logger.info(f"  TURN username: {config['turn_username']}")
        logger.info(f"  Port range: {config['port_min']}-{config['port_max']}")
        logger.info(f"  Note: GPU server uses local TURN, frontend uses public TURN")

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
                    # 这样可以强制使用 TURN 服务器，避免 aiortc 的随机端口问题
                    if 'typ relay' not in candidate_str:
                        logger.info(f"Skipping non-relay candidate: {candidate_str[:60]}...")
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
                    logger.info(f"Sent ICE candidate to client for session {session_id}: {candidate_str[:60]}...")

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
        lines = sdp.split('\n')
        modified_lines = []

        for line in lines:
            if line.startswith('a=candidate'):
                # 只保留 typ relay 的 candidates
                if 'typ relay' in line:
                    modified_lines.append(line)
                    logger.debug(f"Keeping relay candidate: {line}")
                else:
                    logger.debug(f"Removing non-relay candidate: {line}")
            else:
                modified_lines.append(line)

        sdp = '\n'.join(modified_lines)
        logger.info(f"Modified SDP: replaced IPs with {public_ip}, removed non-relay candidates")
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
        # Create peer connection if not exists
        if session_id not in self.connections:
            await self.create_peer_connection(session_id, idle_frames=idle_frames, websocket=websocket)

        pc = self.connections[session_id]

        # Set remote description (offer)
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await pc.setRemoteDescription(offer)

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

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

    async def stream_audio(self, session_id: str, audio_base64: str):
        """
        Stream audio to WebRTC audio track

        Args:
            session_id: Session identifier
            audio_base64: base64 encoded audio (MP3 or WAV)
        """
        if session_id not in self.audio_tracks:
            logger.warning(f"Audio track not found for session {session_id}")
            return

        try:
            # 解码 base64
            audio_bytes = base64.b64decode(audio_base64)

            # 使用 PyAV 解码音频
            container = av.open(io.BytesIO(audio_bytes))
            audio_stream = container.streams.audio[0]

            # 重采样到 48kHz, s16, mono
            resampler = av.audio.resampler.AudioResampler(
                format='s16',
                layout='mono',
                rate=48000
            )

            audio_track = self.audio_tracks[session_id]

            # 处理所有音频帧
            chunk_count = 0
            total_duration = 0.0
            for packet in container.demux(audio_stream):
                for frame in packet.decode():
                    # 重采样
                    resampled_frames = resampler.resample(frame)

                    for resampled_frame in resampled_frames:
                        # 转换为 numpy array
                        audio_data = resampled_frame.to_ndarray()[0]  # (samples,)

                        # 分块为 960 samples (20ms)
                        for i in range(0, len(audio_data), 960):
                            chunk = audio_data[i:i+960]
                            if len(chunk) == 960:
                                await audio_track.add_audio_chunk(chunk)
                                chunk_count += 1
                                # 每个chunk是20ms
                                total_duration += 0.02
                                # 添加20ms延迟，让音频推送与实际时长同步
                                await asyncio.sleep(0.02)

            logger.info(f"Audio streaming completed for session {session_id}: {chunk_count} chunks, {total_duration:.2f}s")

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
        if session_id in self.video_tracks:
            await self.video_tracks[session_id].end_stream()
            del self.video_tracks[session_id]

        if session_id in self.audio_tracks:
            del self.audio_tracks[session_id]

        if session_id in self.connections:
            await self.connections[session_id].close()
            del self.connections[session_id]

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
