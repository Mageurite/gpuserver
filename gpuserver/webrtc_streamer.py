"""
WebRTC Real-time Video Streamer

Provides real-time video streaming using WebRTC for avatar responses.
This allows for low-latency, frame-by-frame video transmission.
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict
import numpy as np
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame

logger = logging.getLogger(__name__)


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
            frame.time_base = "1/25"  # 25 fps

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
                frame.time_base = "1/25"
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
                frame.time_base = "1/25"
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


class WebRTCStreamer:
    """
    WebRTC Streamer for real-time avatar video

    Manages WebRTC peer connections and video streaming.
    """

    def __init__(self):
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.video_tracks: Dict[str, AvatarVideoTrack] = {}

    async def create_peer_connection(self, session_id: str, idle_frames=None) -> RTCPeerConnection:
        """
        Create a new WebRTC peer connection

        Args:
            session_id: Session identifier
            idle_frames: Optional list of idle video frames for looping

        Returns:
            RTCPeerConnection: New peer connection
        """
        pc = RTCPeerConnection()
        self.connections[session_id] = pc

        # Create video track with idle frames
        video_track = AvatarVideoTrack(idle_frames=idle_frames)
        self.video_tracks[session_id] = video_track

        # Add video track to connection
        pc.addTrack(video_track)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"WebRTC connection state: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await self.close_connection(session_id)

        logger.info(f"WebRTC peer connection created for session {session_id}")
        return pc

    async def handle_offer(
        self,
        session_id: str,
        offer_sdp: str,
        idle_frames=None
    ) -> str:
        """
        Handle WebRTC offer from client

        Args:
            session_id: Session identifier
            offer_sdp: SDP offer from client
            idle_frames: Optional list of idle video frames for looping

        Returns:
            str: SDP answer
        """
        # Create peer connection if not exists
        if session_id not in self.connections:
            await self.create_peer_connection(session_id, idle_frames=idle_frames)

        pc = self.connections[session_id]

        # Set remote description (offer)
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await pc.setRemoteDescription(offer)

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logger.info(f"WebRTC answer created for session {session_id}")
        return pc.localDescription.sdp

    async def add_ice_candidate(
        self,
        session_id: str,
        candidate: dict
    ):
        """
        Add ICE candidate from client

        Args:
            session_id: Session identifier
            candidate: ICE candidate data
        """
        if session_id in self.connections:
            pc = self.connections[session_id]
            # Note: aiortc handles ICE candidates automatically
            logger.debug(f"ICE candidate received for session {session_id}")

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
