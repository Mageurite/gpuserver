"""
TTS Worker - 文本转语音模块
照搬 try/lip-sync/ttsreal.py 的架构
"""
import time
import asyncio
import numpy as np
import resampy
import soundfile as sf
from io import BytesIO
from queue import Queue
from threading import Thread
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class State(Enum):
    RUNNING = 0
    PAUSE = 1


class TTSWorker:
    """
    TTS 工作器 - 照搬 try 的架构
    
    数据流:
    put_msg_txt(text) → msgqueue
                         ↓
    process_tts thread → Edge TTS → audio chunks (20ms)
                         ↓
    parent.put_audio_frame(chunk) → ASR
    """
    
    def __init__(self, parent, fps=50, voice="zh-CN-XiaoxiaoNeural"):
        """
        Args:
            parent: 父对象，需要有 put_audio_frame() 方法
            fps: 帧率 (50fps = 20ms per chunk)
            voice: TTS 语音
        """
        self.parent = parent
        self.fps = fps
        self.sample_rate = 16000
        self.chunk = self.sample_rate // fps  # 320 samples per chunk
        self.voice = voice
        
        self.msgqueue = Queue()
        self.state = State.RUNNING
        
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # 线程和事件循环
        self.thread = None
        self.loop = None
        self.quit_event = None
    
    def put_msg_txt(self, msg, eventpoint=None):
        """添加文本到队列"""
        if len(msg) > 0:
            self.msgqueue.put((msg, eventpoint))
    
    def flush(self):
        """清空队列"""
        self.msgqueue.queue.clear()
        self.state = State.PAUSE
        self.audio_buffer = np.array([], dtype=np.float32)
    
    def start(self, quit_event):
        """启动 TTS 线程"""
        self.quit_event = quit_event
        self.thread = Thread(target=self._process_tts, daemon=True)
        self.thread.start()
        logger.info("TTS worker started")
    
    def _process_tts(self):
        """TTS 处理线程"""
        # 创建事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            while not self.quit_event.is_set():
                try:
                    msg = self.msgqueue.get(block=True, timeout=1)
                    self.state = State.RUNNING
                except:
                    continue
                
                # 执行 TTS
                self.loop.run_until_complete(self._txt_to_audio(msg))
        finally:
            self.loop.close()
            logger.info("TTS worker stopped")
    
    async def _txt_to_audio(self, msg):
        """异步 TTS 转换 - 照搬 try 的 EdgeTTS"""
        import edge_tts
        
        text, textevent = msg
        t_start = time.time()
        logger.info(f"[TTS] Starting for: {text[:50]}...")
        
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            
            first_chunk = True
            chunk_count = 0
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio" and self.state == State.RUNNING:
                    chunk_data = chunk["data"]
                    chunk_count += 1
                    
                    if first_chunk:
                        elapsed = time.time() - t_start
                        logger.info(f"[TTS] First chunk: {elapsed:.3f}s")
                        first_chunk = False
                    
                    # 处理音频块
                    await self._process_audio_chunk(
                        chunk_data, text, textevent,
                        is_first=(chunk_count == 1)
                    )
            
            # 处理缓冲区剩余
            if len(self.audio_buffer) > 0:
                eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                padding = np.zeros(self.chunk - len(self.audio_buffer), dtype=np.float32)
                final_chunk = np.concatenate([self.audio_buffer, padding])
                self.parent.put_audio_frame(final_chunk, eventpoint)
                self.audio_buffer = np.array([], dtype=np.float32)
            else:
                eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)
            
            total_time = time.time() - t_start
            logger.info(f"[TTS] Complete: {total_time:.3f}s, chunks: {chunk_count}")
            
        except Exception as e:
            logger.exception(f"[TTS] Error: {e}")
            eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
            self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)
    
    async def _process_audio_chunk(self, chunk_data, text, textevent, is_first):
        """处理音频块"""
        try:
            # 解码音频
            audio_io = BytesIO(chunk_data)
            stream, sample_rate = sf.read(audio_io)
            stream = stream.astype(np.float32)
            
            # 单声道
            if stream.ndim > 1:
                stream = stream[:, 0]
            
            # 重采样到 16kHz
            if sample_rate != self.sample_rate and len(stream) > 0:
                stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)
            
            # 加入缓冲区
            self.audio_buffer = np.concatenate([self.audio_buffer, stream])
            
            # 发送完整 chunk
            idx = 0
            while len(self.audio_buffer) >= self.chunk and self.state == State.RUNNING:
                eventpoint = None
                if is_first and idx == 0:
                    eventpoint = {'status': 'start', 'text': text, 'msgevent': textevent}
                    is_first = False
                
                chunk_to_send = self.audio_buffer[:self.chunk]
                self.parent.put_audio_frame(chunk_to_send, eventpoint)
                
                self.audio_buffer = self.audio_buffer[self.chunk:]
                idx += 1
                
        except Exception as e:
            logger.exception(f"[TTS] Error processing chunk: {e}")
