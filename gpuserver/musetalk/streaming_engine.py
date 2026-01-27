"""
Streaming Lip-Sync Engine - 统一的流式TTS+Lip-Sync引擎

核心架构：
1. TTS Worker - 接收文本，流式生成音频（20ms chunks）
2. MuseASR - 接收音频chunks，提取Whisper特征
3. Inference Worker - 从特征队列批量推理，生成视频帧
4. 输出 - 音频帧 + 视频帧 同步输出

数据流:
    text → TTS → audio_chunks → ASR → whisper_features → Inference → video_frames
                     ↓                                                    ↓
               audio_output_queue                                  video_output_queue

参考实现: /workspace/gpuserver/musetalk/base_real.py
"""

import os
import sys
import time
import copy
import glob
import pickle
import asyncio
from queue import Queue, Empty
from threading import Thread, Event
from typing import Optional, AsyncIterator, Tuple
from enum import Enum
import logging

import cv2
import numpy as np
import torch

logger = logging.getLogger(__name__)

# MuseTalk 路径
MUSETALK_BASE = os.environ.get('MUSETALK_BASE', '/workspace/MuseTalk')


def mirror_index(size: int, index: int) -> int:
    """镜像索引 - 实现视频帧的来回循环"""
    turn = index // size
    res = index % size
    return res if turn % 2 == 0 else size - res - 1


class TTSState(Enum):
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


class StreamingTTSWorker:
    """
    流式TTS工作器
    
    - 使用 Edge TTS 的 stream() 方法
    - 每20ms输出一个音频chunk
    - 支持中断和清空
    - 支持语速调整
    """
    
    def __init__(self, parent, fps: int = 50, voice: str = "zh-CN-XiaoxiaoNeural", 
                 rate: str = "+0%", pitch: str = "+0Hz"):
        """
        Args:
            parent: 父对象，需要有 put_audio_frame(chunk, eventpoint) 方法
            fps: 帧率 (50fps = 20ms/chunk)
            voice: TTS 语音
            rate: 语速调整，如 "+20%", "+50%", "-10%" 等
            pitch: 音调调整，如 "+10Hz", "-5Hz" 等
        """
        self.parent = parent
        self.fps = fps
        self.sample_rate = 16000
        self.chunk_size = self.sample_rate // fps  # 320 samples @ 50fps
        self.voice = voice
        self.rate = rate  # 语速: +20% 加速20%, -10% 减速10%
        self.pitch = pitch  # 音调
        
        self.text_queue = Queue()
        self.state = TTSState.IDLE
        self.audio_buffer = np.array([], dtype=np.float32)
        
        self.thread: Optional[Thread] = None
        self.loop = None
        self.quit_event: Optional[Event] = None
        
    def put_text(self, text: str, eventpoint: dict = None):
        """添加文本到队列"""
        if text and len(text.strip()) > 0:
            self.text_queue.put((text, eventpoint))
            
    def flush(self):
        """清空队列和缓冲区"""
        self.text_queue.queue.clear()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.state = TTSState.PAUSED
        
    def start(self, quit_event: Event):
        """启动TTS线程"""
        self.quit_event = quit_event
        self.state = TTSState.IDLE
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"[TTS] Worker started (voice={self.voice}, fps={self.fps})")
        
    def _run(self):
        """TTS处理线程"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            while not self.quit_event.is_set():
                try:
                    msg = self.text_queue.get(timeout=0.5)
                    self.state = TTSState.RUNNING
                except Empty:
                    continue
                    
                # 执行流式TTS
                self.loop.run_until_complete(self._stream_tts(msg))
                self.state = TTSState.IDLE
        finally:
            self.loop.close()
            logger.info("[TTS] Worker stopped")
            
    async def _stream_tts(self, msg: Tuple[str, dict]):
        """流式TTS转换 - 使用完整音频解码避免断续"""
        import edge_tts
        import tempfile
        import subprocess
        
        text, textevent = msg
        t_start = time.time()
        logger.info(f"[TTS] Starting (rate={self.rate}): {text[:50]}...")
        
        try:
            # 使用语速和音调参数
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
            
            # 收集所有 MP3 数据（Edge TTS 的流式 MP3 块不完整，需要累积）
            mp3_data = b""
            first_chunk_time = None
            
            async for chunk in communicate.stream():
                if self.state == TTSState.PAUSED:
                    logger.info("[TTS] Interrupted")
                    break
                    
                if chunk["type"] == "audio":
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - t_start
                        logger.info(f"[TTS] ⚡ First chunk in {first_chunk_time:.3f}s")
                    mp3_data += chunk["data"]
            
            if not mp3_data:
                logger.warning("[TTS] No audio data received")
                eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                self.parent.put_audio_frame(np.zeros(self.chunk_size, dtype=np.float32), eventpoint)
                return
            
            # 使用 ffmpeg 解码完整的 MP3 为 PCM
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(mp3_data)
                mp3_path = f.name
            
            try:
                # ffmpeg 解码为 16kHz 单声道 PCM
                cmd = [
                    'ffmpeg', '-y', '-i', mp3_path,
                    '-ar', '16000',  # 16kHz
                    '-ac', '1',      # 单声道
                    '-f', 's16le',   # 16-bit PCM
                    '-'              # 输出到 stdout
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                
                if result.returncode != 0:
                    logger.error(f"[TTS] ffmpeg error: {result.stderr.decode()[:200]}")
                    eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                    self.parent.put_audio_frame(np.zeros(self.chunk_size, dtype=np.float32), eventpoint)
                    return
                
                # 解析 PCM 数据
                pcm_data = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                
                logger.info(f"[TTS] Decoded {len(pcm_data)} samples ({len(pcm_data)/16000:.2f}s)")
                
                # 分块发送
                is_first = True
                idx = 0
                while idx < len(pcm_data):
                    chunk_to_send = pcm_data[idx:idx + self.chunk_size]
                    
                    # 如果最后一块不足，补零
                    if len(chunk_to_send) < self.chunk_size:
                        chunk_to_send = np.concatenate([
                            chunk_to_send,
                            np.zeros(self.chunk_size - len(chunk_to_send), dtype=np.float32)
                        ])
                    
                    eventpoint = None
                    if is_first:
                        eventpoint = {'status': 'start', 'text': text, 'msgevent': textevent}
                        is_first = False
                    
                    self.parent.put_audio_frame(chunk_to_send, eventpoint)
                    idx += self.chunk_size
                
                # 发送结束标记
                eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                self.parent.put_audio_frame(np.zeros(self.chunk_size, dtype=np.float32), eventpoint)
                
            finally:
                os.unlink(mp3_path)
                
            total_time = time.time() - t_start
            logger.info(f"[TTS] ✅ Complete: {total_time:.3f}s, {len(pcm_data)} samples")
            
        except Exception as e:
            logger.exception(f"[TTS] Error: {e}")
            eventpoint = {'status': 'error', 'text': text, 'msgevent': textevent, 'error': str(e)}
            self.parent.put_audio_frame(np.zeros(self.chunk_size, dtype=np.float32), eventpoint)
            
    async def _process_audio_data(self, chunk_data: bytes, text: str, textevent: dict, is_first: bool):
        """处理音频数据块"""
        import soundfile as sf
        import resampy
        from io import BytesIO
        import warnings
        
        try:
            # 使用 soundfile 解码（忽略警告）
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                audio_io = BytesIO(chunk_data)
                try:
                    stream, sample_rate = sf.read(audio_io)
                    stream = stream.astype(np.float32)
                except Exception:
                    # 解码失败，跳过这个块
                    return
            
            # 如果数据太短，跳过
            if len(stream) < 10:
                return
                
            # 转单声道
            if stream.ndim > 1:
                stream = stream[:, 0]
                
            # 重采样到16kHz
            if sample_rate != self.sample_rate and len(stream) > 0:
                stream = resampy.resample(stream, sample_rate, self.sample_rate)
                
            # 加入缓冲区
            self.audio_buffer = np.concatenate([self.audio_buffer, stream])
            
            # 发送完整的 chunks
            idx = 0
            while len(self.audio_buffer) >= self.chunk_size and self.state == TTSState.RUNNING:
                eventpoint = None
                if is_first and idx == 0:
                    eventpoint = {'status': 'start', 'text': text, 'msgevent': textevent}
                    is_first = False
                    
                chunk_to_send = self.audio_buffer[:self.chunk_size]
                self.parent.put_audio_frame(chunk_to_send, eventpoint)
                
                self.audio_buffer = self.audio_buffer[self.chunk_size:]
                idx += 1
                
        except Exception as e:
            # 静默忽略解码错误
            pass


class StreamingASR:
    """
    音频特征提取器
    
    - 接收TTS的音频chunks (20ms)
    - 提取Whisper特征
    - 输出特征chunks用于MuseTalk推理
    """
    
    def __init__(self, fps: int, batch_size: int, audio_processor, 
                 stride_left: int = 4, stride_right: int = 4):
        """
        Args:
            fps: 帧率 (50fps)
            batch_size: 批量大小
            audio_processor: Whisper音频处理器
            stride_left/right: 上下文帧数
        """
        self.fps = fps
        self.sample_rate = 16000
        self.chunk_size = self.sample_rate // fps  # 320 samples
        self.batch_size = batch_size
        self.audio_processor = audio_processor
        
        # 队列
        self.input_queue = Queue()  # 接收TTS音频
        self.output_queue = Queue()  # 音频帧输出（用于播放）
        self.feat_queue = Queue(maxsize=2)  # 特征队列（小容量实现背压）
        
        # 帧缓存
        self.frames = []
        self.stride_left_size = stride_left
        self.stride_right_size = stride_right
        
    def put_audio_frame(self, audio_chunk: np.ndarray, eventpoint: dict = None):
        """接收音频帧"""
        self.input_queue.put((audio_chunk, eventpoint))
        
    def get_audio_frame(self) -> Tuple[np.ndarray, int, dict]:
        """获取音频帧"""
        try:
            frame, eventpoint = self.input_queue.get(timeout=0.01)
            frame_type = 0  # 正常语音
        except Empty:
            frame = np.zeros(self.chunk_size, dtype=np.float32)
            frame_type = 1  # 静音
            eventpoint = None
        return frame, frame_type, eventpoint
        
    def warm_up(self):
        """预热 - 填充初始上下文帧"""
        for _ in range(self.stride_left_size + self.stride_right_size):
            frame, frame_type, eventpoint = self.get_audio_frame()
            self.frames.append(frame)
            self.output_queue.put((frame, frame_type, eventpoint))
        # 丢弃左边上下文帧
        for _ in range(self.stride_left_size):
            self.output_queue.get()
            
    def run_step(self):
        """
        运行一步特征提取
        - 读取 batch_size*2 个音频帧
        - 提取特征
        - 生成 batch_size 个特征chunk
        """
        # 读取 batch_size*2 个音频帧
        for _ in range(self.batch_size * 2):
            frame, frame_type, eventpoint = self.get_audio_frame()
            self.frames.append(frame)
            self.output_queue.put((frame, frame_type, eventpoint))
            
        # 检查帧数
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return
            
        # 拼接音频
        inputs = np.concatenate(self.frames)
        
        # 提取Whisper特征
        whisper_feature = self.audio_processor.audio2feat(inputs)
        
        # 转换为chunks
        whisper_chunks = self.audio_processor.feature2chunks(
            feature_array=whisper_feature,
            fps=self.fps / 2,  # 25fps视频
            batch_size=self.batch_size,
            start=self.stride_left_size / 2
        )
        
        # 放入特征队列
        self.feat_queue.put(whisper_chunks)
        
        # 保留上下文帧
        self.frames = self.frames[-(self.stride_left_size + self.stride_right_size):]
        
    def flush(self):
        """清空所有队列"""
        self.input_queue.queue.clear()
        self.output_queue.queue.clear()
        while not self.feat_queue.empty():
            try:
                self.feat_queue.get_nowait()
            except Empty:
                break
        self.frames = []


class StreamingLipSyncEngine:
    """
    统一的流式Lip-Sync引擎
    
    整合 TTS + ASR + MuseTalk推理 + 输出
    实现真正的流式处理，首帧延迟 < 2秒
    """
    
    def __init__(
        self,
        avatar_id: str,
        avatar_path: str,
        batch_size: int = 8,
        fps: int = 50,
        voice: str = "zh-CN-XiaoxiaoNeural",
        tts_rate: str = "+0%",
        tts_pitch: str = "+0Hz"
    ):
        """
        Args:
            avatar_id: Avatar标识
            avatar_path: Avatar数据路径
            batch_size: 批量大小
            fps: 音频帧率 (50fps = 20ms/chunk)
            voice: TTS语音
            tts_rate: TTS语速，如 "+20%", "+50%", "-10%"
            tts_pitch: TTS音调，如 "+10Hz", "-5Hz"
        """
        self.avatar_id = avatar_id
        self.avatar_path = avatar_path
        self.batch_size = batch_size
        self.fps = fps
        self.voice = voice
        self.tts_rate = tts_rate
        self.tts_pitch = tts_pitch
        
        # 模型（延迟加载）
        self.vae = None
        self.unet = None
        self.pe = None
        self.timesteps = None
        self.audio_processor = None
        self._models_loaded = False
        
        # Avatar数据
        self.frame_list_cycle = []
        self.mask_list_cycle = []
        self.coord_list_cycle = []
        self.mask_coords_list_cycle = []
        self.input_latent_list_cycle = []
        self._avatar_loaded = False
        
        # 组件
        self.tts: Optional[StreamingTTSWorker] = None
        self.asr: Optional[StreamingASR] = None
        
        # 输出队列
        self.video_frame_queue = Queue(maxsize=batch_size * 4)
        self.audio_frame_queue = Queue(maxsize=batch_size * 8)
        
        # 控制事件
        self.quit_event = Event()
        self.render_event = Event()
        
        # 线程
        self.inference_thread: Optional[Thread] = None
        self.asr_thread: Optional[Thread] = None
        
        logger.info(f"[{avatar_id}] StreamingLipSyncEngine initialized")
        
    def load_models(self):
        """加载MuseTalk模型"""
        if self._models_loaded:
            return
            
        logger.info(f"[{self.avatar_id}] Loading MuseTalk models...")
        
        # 确保 MuseTalk 路径在最前面
        if MUSETALK_BASE not in sys.path:
            sys.path.insert(0, MUSETALK_BASE)
        else:
            # 移到最前面
            sys.path.remove(MUSETALK_BASE)
            sys.path.insert(0, MUSETALK_BASE)
            
        # 清除可能的缓存模块
        import importlib
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith('musetalk') and 'streaming' not in mod_name:
                del sys.modules[mod_name]
            
        old_cwd = os.getcwd()
        os.chdir(MUSETALK_BASE)
        
        try:
            # 清除所有 musetalk 相关的模块缓存
            mods_to_remove = [k for k in sys.modules.keys() if k == 'musetalk' or k.startswith('musetalk.')]
            for mod in mods_to_remove:
                del sys.modules[mod]
            
            # 把 MuseTalk 放到 sys.path 最前面
            sys.path = [MUSETALK_BASE] + [p for p in sys.path if p != MUSETALK_BASE]
            
            logger.info(f"[{self.avatar_id}] sys.path[0] = {sys.path[0]}")
            
            from musetalk.utils.utils import load_all_model
            from musetalk.whisper.audio2feature import Audio2Feature
            
            # 加载模型
            self.vae, self.unet, self.pe = load_all_model()
            
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.timesteps = torch.tensor([0], device=device)
            
            # 加载音频处理器
            self.audio_processor = Audio2Feature(
                whisper_model_type="tiny",
                model_path="tiny"
            )
            
            # 转半精度
            self.pe = self.pe.half()
            self.vae.vae = self.vae.vae.half()
            self.unet.model = self.unet.model.half()
            
            self._models_loaded = True
            logger.info(f"[{self.avatar_id}] ✅ Models loaded on {device}")
            
        finally:
            os.chdir(old_cwd)
            
    def load_avatar(self):
        """加载Avatar数据"""
        if self._avatar_loaded:
            return
            
        logger.info(f"[{self.avatar_id}] Loading avatar from {self.avatar_path}")
        
        # 加载latents
        latents_path = os.path.join(self.avatar_path, "latents.pt")
        self.input_latent_list_cycle = torch.load(latents_path)
        
        # 加载coords
        coords_path = os.path.join(self.avatar_path, "coords.pkl")
        with open(coords_path, 'rb') as f:
            self.coord_list_cycle = pickle.load(f)
            
        # 加载图像
        full_imgs_path = os.path.join(self.avatar_path, "full_imgs")
        img_list = sorted(
            glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]')),
            key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
        )
        self.frame_list_cycle = [cv2.imread(img) for img in img_list]
        
        # 加载mask coords
        mask_coords_path = os.path.join(self.avatar_path, "mask_coords.pkl")
        with open(mask_coords_path, 'rb') as f:
            self.mask_coords_list_cycle = pickle.load(f)
            
        # 加载masks
        mask_path = os.path.join(self.avatar_path, "mask")
        mask_list = sorted(
            glob.glob(os.path.join(mask_path, '*.[jpJP][pnPN]*[gG]')),
            key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
        )
        self.mask_list_cycle = [cv2.imread(img) for img in mask_list]
        
        self._avatar_loaded = True
        logger.info(f"[{self.avatar_id}] ✅ Avatar loaded: {len(self.frame_list_cycle)} frames")
        
    def setup(self):
        """初始化所有组件"""
        # 加载模型和Avatar
        self.load_models()
        self.load_avatar()
        
        # 创建TTS（支持语速调整）
        self.tts = StreamingTTSWorker(
            self, 
            fps=self.fps, 
            voice=self.voice,
            rate=self.tts_rate,
            pitch=self.tts_pitch
        )
        
        # 创建ASR
        self.asr = StreamingASR(
            fps=self.fps,
            batch_size=self.batch_size,
            audio_processor=self.audio_processor,
            stride_left=4,
            stride_right=4
        )
        self.asr.warm_up()
        
        logger.info(f"[{self.avatar_id}] ✅ Setup complete")
        
    def put_audio_frame(self, audio_chunk: np.ndarray, eventpoint: dict = None):
        """接收TTS音频帧 - 传递给ASR"""
        if self.asr:
            self.asr.put_audio_frame(audio_chunk, eventpoint)
            
    def start(self):
        """启动引擎"""
        logger.info(f"[{self.avatar_id}] Starting engine...")
        
        if not self._models_loaded or not self._avatar_loaded:
            self.setup()
            
        self.quit_event.clear()
        self.render_event.set()
        
        # 启动TTS线程
        self.tts.start(self.quit_event)
        
        # 启动ASR线程
        self.asr_thread = Thread(target=self._asr_loop, daemon=True)
        self.asr_thread.start()
        
        # 启动推理线程
        self.inference_thread = Thread(target=self._inference_loop, daemon=True)
        self.inference_thread.start()
        
        logger.info(f"[{self.avatar_id}] ✅ Engine started")
        
    def _asr_loop(self):
        """ASR主循环"""
        logger.info(f"[{self.avatar_id}] ASR loop started")
        
        while not self.quit_event.is_set():
            self.asr.run_step()
            
            # 背压控制
            if self.video_frame_queue.qsize() >= self.batch_size * 2:
                time.sleep(0.02)
                
        logger.info(f"[{self.avatar_id}] ASR loop stopped")
        
    @torch.no_grad()
    def _inference_loop(self):
        """推理循环"""
        if MUSETALK_BASE not in sys.path:
            sys.path.insert(0, MUSETALK_BASE)
        from musetalk.utils.blending import get_image_blending
        
        logger.info(f"[{self.avatar_id}] Inference loop started")
        
        length = len(self.coord_list_cycle)
        index = 0
        count = 0
        counttime = 0
        
        while self.render_event.is_set():
            try:
                whisper_chunks = self.asr.feat_queue.get(timeout=1)
            except Empty:
                continue
                
            # 获取音频帧（用于同步）
            is_all_silence = True
            audio_frames = []
            for _ in range(self.batch_size * 2):
                frame, frame_type, eventpoint = self.asr.output_queue.get()
                audio_frames.append((frame, frame_type, eventpoint))
                if frame_type == 0:
                    is_all_silence = False
                    
            # 如果全是静音，使用原始帧
            if is_all_silence:
                for i in range(self.batch_size):
                    idx = mirror_index(length, index)
                    ori_frame = self.frame_list_cycle[idx].copy()
                    
                    # 输出视频帧
                    self.video_frame_queue.put(ori_frame)
                    
                    # 输出音频帧
                    for af in audio_frames[i*2:i*2+2]:
                        self.audio_frame_queue.put(af)
                        
                    index += 1
                continue
                
            # 有语音，进行推理
            t = time.perf_counter()
            
            whisper_batch = np.stack(whisper_chunks)
            latent_batch = []
            for i in range(self.batch_size):
                idx = mirror_index(length, index + i)
                latent = self.input_latent_list_cycle[idx]
                latent_batch.append(latent)
            latent_batch = torch.cat(latent_batch, dim=0)
            
            # 准备音频特征
            audio_feature_batch = torch.from_numpy(whisper_batch)
            audio_feature_batch = audio_feature_batch.to(
                device=self.unet.device,
                dtype=self.unet.model.dtype
            )
            audio_feature_batch = self.pe(audio_feature_batch)
            latent_batch = latent_batch.to(dtype=self.unet.model.dtype)
            
            # UNet推理
            pred_latents = self.unet.model(
                latent_batch,
                self.timesteps,
                encoder_hidden_states=audio_feature_batch
            ).sample
            
            # VAE解码
            recon = self.vae.decode_latents(pred_latents)
            
            counttime += (time.perf_counter() - t)
            count += self.batch_size
            if count >= 100:
                logger.info(f"[{self.avatar_id}] Avg infer fps: {count/counttime:.2f}")
                count = 0
                counttime = 0
                
            # 混合帧并输出
            for i, res_frame in enumerate(recon):
                idx = mirror_index(length, index)
                
                try:
                    # 帧混合
                    bbox = self.coord_list_cycle[idx]
                    ori_frame = self.frame_list_cycle[idx].copy()
                    x1, y1, x2, y2 = bbox
                    
                    res_frame_resized = cv2.resize(res_frame.astype(np.uint8), (x2-x1, y2-y1))
                    
                    combine_frame = get_image_blending(
                        ori_frame,
                        res_frame_resized,
                        bbox,
                        self.mask_list_cycle[idx],
                        self.mask_coords_list_cycle[idx]
                    )
                except Exception as e:
                    logger.warning(f"[{self.avatar_id}] Blending error: {e}")
                    combine_frame = self.frame_list_cycle[idx].copy()
                    
                # 输出视频帧
                self.video_frame_queue.put(combine_frame)
                
                # 输出音频帧
                for af in audio_frames[i*2:i*2+2]:
                    self.audio_frame_queue.put(af)
                    
                index += 1
                
        logger.info(f"[{self.avatar_id}] Inference loop stopped")
        
    def generate_stream(self, text: str) -> Tuple[AsyncIterator[np.ndarray], AsyncIterator[Tuple[np.ndarray, int, dict]]]:
        """
        流式生成视频和音频
        
        Args:
            text: 输入文本
            
        Returns:
            (video_iterator, audio_iterator): 视频帧和音频帧的异步迭代器
        """
        # 发送文本到TTS
        self.tts.put_text(text)
        
        async def video_stream():
            """视频帧流"""
            while True:
                try:
                    frame = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.video_frame_queue.get(timeout=2)
                    )
                    yield frame
                except Empty:
                    break
                    
        async def audio_stream():
            """音频帧流"""
            while True:
                try:
                    frame_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.audio_frame_queue.get(timeout=2)
                    )
                    yield frame_data
                except Empty:
                    break
                    
        return video_stream(), audio_stream()
        
    async def process_text(self, text: str) -> AsyncIterator[Tuple[np.ndarray, np.ndarray]]:
        """
        处理文本，生成同步的音视频帧
        
        Args:
            text: 输入文本
            
        Yields:
            (video_frame, audio_samples): BGR视频帧和音频采样
        """
        # 清空队列
        self._clear_queues()
        
        # 发送文本到TTS
        self.tts.put_text(text)
        logger.info(f"[{self.avatar_id}] Text sent to TTS: {text[:50]}...")
        
        # 等待第一帧
        first_frame_time = None
        frame_count = 0
        
        while True:
            try:
                # 获取视频帧
                video_frame = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.video_frame_queue.get(timeout=3)
                )
                
                # 获取对应的2个音频帧
                audio_frames = []
                for _ in range(2):
                    try:
                        af = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.audio_frame_queue.get(timeout=1)
                        )
                        audio_frames.append(af)
                    except Empty:
                        audio_frames.append((np.zeros(320, dtype=np.float32), 1, None))
                        
                if first_frame_time is None:
                    first_frame_time = time.time()
                    logger.info(f"[{self.avatar_id}] ⚡ First frame!")
                    
                # 合并音频
                audio_samples = np.concatenate([af[0] for af in audio_frames])
                
                yield video_frame, audio_samples
                frame_count += 1
                
                # 检查是否结束
                end_detected = False
                for af in audio_frames:
                    if af[2] and af[2].get('status') == 'end':
                        end_detected = True
                        break
                        
                if end_detected:
                    logger.info(f"[{self.avatar_id}] ✅ Stream complete: {frame_count} frames")
                    break
                    
            except Empty:
                # 超时，检查是否有更多数据
                if self.video_frame_queue.empty() and self.audio_frame_queue.empty():
                    logger.info(f"[{self.avatar_id}] Stream timeout, total: {frame_count} frames")
                    break
                    
    def _clear_queues(self):
        """清空所有队列"""
        while not self.video_frame_queue.empty():
            try:
                self.video_frame_queue.get_nowait()
            except Empty:
                break
        while not self.audio_frame_queue.empty():
            try:
                self.audio_frame_queue.get_nowait()
            except Empty:
                break
        if self.asr:
            self.asr.flush()
            
    def stop(self):
        """停止引擎"""
        logger.info(f"[{self.avatar_id}] Stopping engine...")
        
        self.render_event.clear()
        self.quit_event.set()
        
        if self.inference_thread:
            self.inference_thread.join(timeout=2)
        if self.asr_thread:
            self.asr_thread.join(timeout=2)
            
        self._clear_queues()
        
        if self.tts:
            self.tts.flush()
            
        logger.info(f"[{self.avatar_id}] ✅ Engine stopped")


# 全局引擎缓存
_streaming_engines: dict = {}


def get_streaming_engine(
    avatar_id: str,
    avatar_path: str,
    batch_size: int = 8,
    fps: int = 50,
    voice: str = "zh-CN-XiaoxiaoNeural",
    tts_rate: str = "+0%",
    tts_pitch: str = "+0Hz"
) -> StreamingLipSyncEngine:
    """
    获取或创建流式引擎实例
    
    Args:
        avatar_id: Avatar标识
        avatar_path: Avatar数据路径
        batch_size: 批量大小
        fps: 帧率
        voice: TTS语音
        tts_rate: TTS语速，如 "+20%", "+50%", "-10%"
        tts_pitch: TTS音调
        
    Returns:
        StreamingLipSyncEngine实例
    """
    global _streaming_engines
    
    if avatar_id not in _streaming_engines:
        engine = StreamingLipSyncEngine(
            avatar_id=avatar_id,
            avatar_path=avatar_path,
            batch_size=batch_size,
            fps=fps,
            voice=voice,
            tts_rate=tts_rate,
            tts_pitch=tts_pitch
        )
        engine.setup()
        engine.start()
        _streaming_engines[avatar_id] = engine
        logger.info(f"Created streaming engine for {avatar_id} (rate={tts_rate})")
        
    return _streaming_engines[avatar_id]


def warmup_streaming_engine(
    avatar_id: str,
    avatar_path: str,
    batch_size: int = 8,
    fps: int = 50,
    voice: str = "zh-CN-XiaoxiaoNeural"
):
    """
    预热流式引擎（在后台线程中）
    """
    import threading
    
    def warmup():
        try:
            logger.info(f"[Warmup] Starting streaming engine for {avatar_id}...")
            engine = get_streaming_engine(avatar_id, avatar_path, batch_size, fps, voice)
            logger.info(f"[Warmup] ✅ Streaming engine ready for {avatar_id}")
        except Exception as e:
            logger.error(f"[Warmup] Failed: {e}")
            
    thread = threading.Thread(target=warmup, daemon=True)
    thread.start()
