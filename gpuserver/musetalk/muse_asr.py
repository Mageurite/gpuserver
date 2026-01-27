"""
MuseASR - 音频特征提取模块
照搬 try/lip-sync/museasr.py 的架构
"""
import time
import numpy as np
import queue
from queue import Queue
import logging

logger = logging.getLogger(__name__)


class MuseASR:
    """音频特征提取器 - 照搬 try 的架构"""
    
    def __init__(self, fps, batch_size, audio_processor, stride_left=4, stride_right=4):
        """
        Args:
            fps: 帧率，50fps 表示 20ms 每帧
            batch_size: 批量大小
            audio_processor: Whisper 音频处理器
            stride_left: 左边上下文帧数
            stride_right: 右边上下文帧数
        """
        self.fps = fps  # 50fps = 20ms per audio chunk
        self.sample_rate = 16000
        self.chunk = self.sample_rate // self.fps  # 320 samples per chunk (20ms)
        
        self.batch_size = batch_size
        self.audio_processor = audio_processor
        
        # 输入队列 - 接收 TTS 的音频 chunks
        self.input_queue = Queue()
        
        # 输出队列 - 保存音频帧用于后续播放
        self.output_queue = Queue()
        
        # 特征队列 - 保存 whisper 特征用于推理
        # try 中是 mp.Queue(2)，小容量让生产者等待消费者
        self.feat_queue = Queue(maxsize=2)
        
        # 音频帧缓存（用于特征提取）
        self.frames = []
        self.stride_left_size = stride_left
        self.stride_right_size = stride_right
        
    def put_audio_frame(self, audio_chunk, eventpoint=None):
        """接收音频帧 - 由 TTS 调用"""
        self.input_queue.put((audio_chunk, eventpoint))
    
    def get_audio_frame(self):
        """
        获取音频帧
        Returns:
            (frame, type, eventpoint)
            - frame: 音频数据 (320 samples, float32)
            - type: 0=正常语音, 1=静音
            - eventpoint: 事件点
        """
        try:
            frame, eventpoint = self.input_queue.get(block=True, timeout=0.01)
            frame_type = 0  # 正常语音
        except queue.Empty:
            frame = np.zeros(self.chunk, dtype=np.float32)
            frame_type = 1  # 静音
            eventpoint = None
        return frame, frame_type, eventpoint
    
    def warm_up(self):
        """预热 - 填充初始帧"""
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame, frame_type, eventpoint = self.get_audio_frame()
            self.frames.append(audio_frame)
            self.output_queue.put((audio_frame, frame_type, eventpoint))
        # 丢弃左边的帧（它们只用于上下文）
        for _ in range(self.stride_left_size):
            self.output_queue.get()
    
    def run_step(self):
        """
        运行一步特征提取
        - 读取 batch_size*2 个音频帧
        - 提取 whisper 特征
        - 生成 batch_size 个特征 chunk
        """
        # 读取 batch_size*2 个音频帧
        for _ in range(self.batch_size * 2):
            audio_frame, frame_type, eventpoint = self.get_audio_frame()
            self.frames.append(audio_frame)
            # 同时放入输出队列（用于后续音频播放）
            self.output_queue.put((audio_frame, frame_type, eventpoint))
        
        # 检查是否有足够的帧进行特征提取
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return
        
        # 拼接音频帧
        inputs = np.concatenate(self.frames)
        
        # 提取 whisper 特征
        whisper_feature = self.audio_processor.audio2feat(inputs)
        
        # 转换为 chunks（每个 chunk 对应一个视频帧）
        whisper_chunks = self.audio_processor.feature2chunks(
            feature_array=whisper_feature,
            fps=self.fps / 2,  # 25fps 视频
            batch_size=self.batch_size,
            start=self.stride_left_size / 2
        )
        
        # 放入特征队列
        self.feat_queue.put(whisper_chunks)
        
        # 只保留上下文帧
        self.frames = self.frames[-(self.stride_left_size + self.stride_right_size):]
    
    def flush(self):
        """清空队列"""
        self.input_queue.queue.clear()
        self.output_queue.queue.clear()
        while not self.feat_queue.empty():
            try:
                self.feat_queue.get_nowait()
            except queue.Empty:
                break
        self.frames = []
