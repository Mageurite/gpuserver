"""
MuseRealEngine - 完全照搬 try/lip-sync 架构

关键架构：
1. TTS 独立线程 - 接收文本队列，生成音频推送到 ASR
2. 推理线程 - 从 feat_queue 获取特征，批量推理
3. 处理线程 - 从 res_frame_queue 获取结果，推送到 WebRTC
4. 主循环 - 调用 asr.run_step()
"""

import os
import sys
import time
import copy
import glob
import pickle
import queue
from queue import Queue
from threading import Thread, Event
import asyncio

import cv2
import numpy as np
import torch

from av import AudioFrame, VideoFrame

import logging
logger = logging.getLogger("gpuserver_base_real")


def mirror_index(size, index):
    """镜像索引"""
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1


class TTSWorker:
    """TTS 工作线程 - 照搬 try/lip-sync/ttsreal.py EdgeTTS"""
    
    def __init__(self, parent, voice="zh-CN-XiaoxiaoNeural", rate="+30%", pitch="+0Hz"):
        self.parent = parent
        self.voice = voice
        self.rate = rate  # 语速: "+0%", "+30%", "+50%" 等
        self.pitch = pitch  # 音调: "+0Hz", "+10Hz" 等
        self.sample_rate = 16000
        self.chunk = 320  # 20ms @ 16kHz
        
        self.msgqueue = Queue()
        self.running = False
        self.thread = None
        self.loop = None
    
    def put_msg_txt(self, msg, eventpoint=None):
        """发送文本到队列"""
        if len(msg) > 0:
            self.msgqueue.put((msg, eventpoint))
    
    def flush(self):
        """清空队列"""
        self.msgqueue.queue.clear()
    
    def start(self, quit_event):
        """启动 TTS 线程"""
        self.running = True
        self.thread = Thread(target=self._process_tts, args=(quit_event,), daemon=True)
        self.thread.start()
        logger.info("TTS worker started")
    
    def _process_tts(self, quit_event):
        """TTS 处理线程"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            while not quit_event.is_set():
                try:
                    msg = self.msgqueue.get(block=True, timeout=0.5)
                except queue.Empty:
                    continue
                
                # 执行 TTS
                self.loop.run_until_complete(self._txt_to_audio(msg))
        finally:
            self.loop.close()
            logger.info("TTS worker stopped")
    
    async def _txt_to_audio(self, msg):
        """异步流式 TTS - 使用 ffmpeg 解码完整 MP3"""
        import edge_tts
        import tempfile
        import subprocess
        
        text, eventpoint = msg
        logger.info(f"[TTS] Processing (rate={self.rate}): {text[:60]}...")
        
        t_start = time.time()
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
        
        try:
            # 收集所有 MP3 数据
            mp3_data = b""
            first_chunk_time = None
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - t_start
                        logger.info(f"[TTS] First chunk: {first_chunk_time:.3f}s")
                    mp3_data += chunk["data"]
            
            if not mp3_data:
                logger.warning("[TTS] No audio data received")
                return
            
            # 用 ffmpeg 解码 MP3 到 PCM
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(mp3_data)
                mp3_path = f.name
            
            try:
                cmd = [
                    'ffmpeg', '-y', '-i', mp3_path,
                    '-ar', str(self.sample_rate),
                    '-ac', '1',
                    '-f', 's16le',
                    '-'
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                
                if result.returncode != 0:
                    logger.error(f"[TTS] ffmpeg error: {result.stderr.decode()[:200]}")
                    return
                
                # 转换为 float32
                pcm_data = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                
                logger.info(f"[TTS] Decoded {len(pcm_data)} samples ({len(pcm_data)/self.sample_rate:.2f}s)")
                
                # 分块发送
                idx = 0
                while idx < len(pcm_data):
                    audio_chunk = pcm_data[idx:idx + self.chunk]
                    
                    # 填充最后一块
                    if len(audio_chunk) < self.chunk:
                        audio_chunk = np.concatenate([
                            audio_chunk,
                            np.zeros(self.chunk - len(audio_chunk), dtype=np.float32)
                        ])
                    
                    self.parent.put_audio_frame(audio_chunk, eventpoint)
                    idx += self.chunk
                
            finally:
                import os
                os.unlink(mp3_path)
            
            logger.info(f"[TTS] Complete: {time.time() - t_start:.3f}s")
            
        except Exception as e:
            logger.error(f"[TTS] Error: {e}")


class MuseRealEngine:
    """MuseTalk 实时引擎 - 完全照搬 try 架构"""
    
    def __init__(self, avatar_id, batch_size=8, fps=50, model=None, avatar=None):
        """
        Args:
            avatar_id: Avatar 标识符
            batch_size: 批量大小
            fps: 帧率 (50fps = 20ms per audio chunk)
            model: 预加载的模型 (vae, unet, pe, timesteps, audio_processor)
            avatar: 预加载的 avatar 数据
        """
        self.avatar_id = avatar_id
        self.batch_size = batch_size
        self.fps = fps
        
        # 使用预加载的模型
        if model:
            self.vae, self.unet, self.pe, self.timesteps, self.audio_processor = model
            self._loaded = True
        else:
            self.vae = None
            self.unet = None
            self.pe = None
            self.timesteps = None
            self.audio_processor = None
            self._loaded = False
        
        # 使用预加载的 Avatar 数据
        if avatar:
            (self.frame_list_cycle, self.mask_list_cycle, self.coord_list_cycle,
             self.mask_coords_list_cycle, self.input_latent_list_cycle) = avatar
        else:
            self.frame_list_cycle = []
            self.mask_list_cycle = []
            self.coord_list_cycle = []
            self.mask_coords_list_cycle = []
            self.input_latent_list_cycle = []
        
        # ASR
        self.asr = None
        
        # TTS
        self.tts = None
        
        # WebRTC tracks (用于音频直接推送)
        self.audio_track = None
        self.loop = None
        
        # 结果队列
        self.res_frame_queue = Queue(maxsize=batch_size * 4)
        
        # 控制事件
        self.render_event = Event()
        self.quit_event = Event()
        
        # 线程
        self.inference_thread = None
        self.process_thread = None
        
        logger.info(f"[{avatar_id}] MuseRealEngine initialized (model_preloaded={model is not None})")
    
    def load_models(self):
        """加载模型"""
        if self._loaded:
            return
        
        logger.info(f"[{self.avatar_id}] Loading models...")
        
        musetalk_base = os.environ.get('MUSETALK_BASE', '/workspace/MuseTalk')
        if musetalk_base not in sys.path:
            sys.path.insert(0, musetalk_base)
        
        old_cwd = os.getcwd()
        os.chdir(musetalk_base)
        
        try:
            from musetalk.utils.utils import load_all_model
            from musetalk.whisper.audio2feature import Audio2Feature
            
            # 加载模型
            unet_path = os.path.join(musetalk_base, "models", "musetalkV15", "unet.pth")
            unet_config = os.path.join(musetalk_base, "models", "musetalkV15", "musetalk.json")
            self.vae, self.unet, self.pe = load_all_model(
                unet_model_path=unet_path,
                unet_config=unet_config
            )
            
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.timesteps = torch.tensor([0], device=device)
            
            # 加载 audio_processor
            self.audio_processor = Audio2Feature(
                whisper_model_type="tiny",
                model_path="tiny"
            )
            
            # 转换为半精度
            self.pe = self.pe.half()
            self.vae.vae = self.vae.vae.half()
            self.unet.model = self.unet.model.half()
            
            logger.info(f"[{self.avatar_id}] Models loaded on {device}")
            
        finally:
            os.chdir(old_cwd)
        
        self._loaded = True
    
    def load_avatar(self, avatar_path):
        """加载 Avatar 数据"""
        logger.info(f"[{self.avatar_id}] Loading avatar from {avatar_path}")
        
        full_imgs_path = os.path.join(avatar_path, "full_imgs")
        coords_path = os.path.join(avatar_path, "coords.pkl")
        latents_path = os.path.join(avatar_path, "latents.pt")
        mask_path = os.path.join(avatar_path, "mask")
        mask_coords_path = os.path.join(avatar_path, "mask_coords.pkl")
        
        # 加载 latents
        self.input_latent_list_cycle = torch.load(latents_path)
        
        # 加载 coords
        with open(coords_path, 'rb') as f:
            self.coord_list_cycle = pickle.load(f)
        
        # 加载图像
        input_img_list = glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
        input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        self.frame_list_cycle = [cv2.imread(img) for img in input_img_list]
        
        # 加载 mask coords
        with open(mask_coords_path, 'rb') as f:
            self.mask_coords_list_cycle = pickle.load(f)
        
        # 加载 masks
        input_mask_list = glob.glob(os.path.join(mask_path, '*.[jpJP][pnPN]*[gG]'))
        input_mask_list = sorted(input_mask_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        self.mask_list_cycle = [cv2.imread(img) for img in input_mask_list]
        
        logger.info(f"[{self.avatar_id}] Avatar loaded: {len(self.frame_list_cycle)} frames")
    
    def setup_asr(self):
        """设置 ASR 模块"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "muse_asr",
            os.path.join(os.path.dirname(__file__), "muse_asr.py")
        )
        muse_asr_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(muse_asr_module)
        MuseASR = muse_asr_module.MuseASR
        
        self.asr = MuseASR(
            fps=self.fps,
            batch_size=self.batch_size,
            audio_processor=self.audio_processor,
            stride_left=2,  # 减少前置上下文，加快首帧
            stride_right=2  # 减少后置上下文
        )
        self.asr.warm_up()
        logger.info(f"[{self.avatar_id}] ASR ready")
    
    def setup_tts(self, voice="zh-CN-XiaoxiaoNeural", rate="+30%", pitch="+0Hz"):
        """设置 TTS 模块"""
        self.tts = TTSWorker(self, voice=voice, rate=rate, pitch=pitch)
        logger.info(f"[{self.avatar_id}] TTS ready (rate={rate})")
    
    def put_audio_frame(self, audio_chunk, eventpoint=None):
        """接收音频帧 - 由 TTS 调用"""
        if self.asr:
            self.asr.put_audio_frame(audio_chunk, eventpoint)
    
    def put_msg_txt(self, msg, eventpoint=None):
        """发送文本到 TTS"""
        if self.tts:
            self.tts.put_msg_txt(msg, eventpoint)
    
    @torch.no_grad()
    def inference_worker(self):
        """推理线程 - 照搬 try/lip-sync/musereal.py inference()"""
        logger.info(f"[{self.avatar_id}] Inference thread started")
        
        length = len(self.input_latent_list_cycle)
        index = 0
        count = 0
        counttime = 0
        
        while self.render_event.is_set():
            try:
                whisper_chunks = self.asr.feat_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            
            is_all_silence = True
            audio_frames = []
            for _ in range(self.batch_size * 2):
                frame, frame_type, eventpoint = self.asr.output_queue.get()
                audio_frames.append((frame, frame_type, eventpoint))
                if frame_type == 0:
                    is_all_silence = False
            
            if is_all_silence:
                for i in range(self.batch_size):
                    self.res_frame_queue.put((
                        None,
                        mirror_index(length, index),
                        audio_frames[i*2:i*2+2]
                    ))
                    index += 1
            else:
                t = time.perf_counter()
                
                whisper_batch = np.stack(whisper_chunks)
                latent_batch = []
                for i in range(self.batch_size):
                    idx = mirror_index(length, index + i)
                    latent = self.input_latent_list_cycle[idx]
                    latent_batch.append(latent)
                latent_batch = torch.cat(latent_batch, dim=0)
                
                audio_feature_batch = torch.from_numpy(whisper_batch)
                audio_feature_batch = audio_feature_batch.to(
                    device=self.unet.device,
                    dtype=self.unet.model.dtype
                )
                audio_feature_batch = self.pe(audio_feature_batch)
                latent_batch = latent_batch.to(dtype=self.unet.model.dtype)
                
                pred_latents = self.unet.model(
                    latent_batch,
                    self.timesteps,
                    encoder_hidden_states=audio_feature_batch
                ).sample
                
                recon = self.vae.decode_latents(pred_latents)
                
                counttime += (time.perf_counter() - t)
                count += self.batch_size
                if count >= 100:
                    logger.info(f"[{self.avatar_id}] Avg infer fps: {count/counttime:.2f}")
                    count = 0
                    counttime = 0
                
                for i, res_frame in enumerate(recon):
                    self.res_frame_queue.put((
                        res_frame,
                        mirror_index(length, index),
                        audio_frames[i*2:i*2+2]
                    ))
                    index += 1
        
        logger.info(f"[{self.avatar_id}] Inference thread stopped")
    
    def paste_back_frame(self, pred_frame, idx):
        """将推理结果贴回原图"""
        musetalk_base = os.environ.get('MUSETALK_BASE', '/workspace/MuseTalk')
        if musetalk_base not in sys.path:
            sys.path.insert(0, musetalk_base)
        from musetalk.utils.blending import get_image_blending
        
        bbox = self.coord_list_cycle[idx]
        ori_frame = copy.deepcopy(self.frame_list_cycle[idx])
        x1, y1, x2, y2 = bbox
        
        res_frame = cv2.resize(pred_frame.astype(np.uint8), (x2-x1, y2-y1))
        mask = self.mask_list_cycle[idx]
        mask_crop_box = self.mask_coords_list_cycle[idx]
        
        combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
        return combine_frame
    
    def process_frames_worker(self, loop, audio_track, video_track):
        """处理帧线程 - 使用预缓冲策略减少卡顿"""
        logger.info(f"[{self.avatar_id}] Process frames thread started")
        
        PREBUFFER_FRAMES = 3  # 预缓冲帧数 (3帧 = 120ms @ 25fps)
        frame_count = 0
        sync_triggered = False
        
        while not self.quit_event.is_set():
            try:
                res_frame, idx, audio_frames = self.res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            
            frame_count += 1
            
            # 预缓冲：等积累足够帧数后再触发播放
            if not sync_triggered and frame_count >= PREBUFFER_FRAMES:
                sync_triggered = True
                logger.info(f"[{self.avatar_id}] Prebuffer ready ({PREBUFFER_FRAMES} frames), starting playback")
                try:
                    import sys
                    if 'webrtc_streamer' in sys.modules:
                        sys.modules['webrtc_streamer'].trigger_av_sync()
                    else:
                        from webrtc_streamer import trigger_av_sync
                        trigger_av_sync()
                except Exception as e:
                    logger.warning(f"Failed to trigger AV sync: {e}")
            
            # 全是静音
            if audio_frames[0][1] != 0 and audio_frames[1][1] != 0:
                combine_frame = self.frame_list_cycle[idx]
            else:
                if res_frame is not None:
                    try:
                        combine_frame = self.paste_back_frame(res_frame, idx)
                    except Exception as e:
                        logger.warning(f"paste_back_frame error: {e}")
                        continue
                else:
                    combine_frame = self.frame_list_cycle[idx]
            
            # 推送视频帧
            image = combine_frame
            image[0, :] &= 0xFE
            new_frame = VideoFrame.from_ndarray(image, format="bgr24")
            asyncio.run_coroutine_threadsafe(
                video_track._queue.put((new_frame, None)),
                loop
            )
            
            # 推送音频帧（与视频同步）
            for audio_frame_data in audio_frames:
                frame, frame_type, eventpoint = audio_frame_data
                frame_int16 = (frame * 32767).astype(np.int16)
                
                new_frame = AudioFrame(format='s16', layout='mono', samples=frame_int16.shape[0])
                new_frame.planes[0].update(frame_int16.tobytes())
                new_frame.sample_rate = 16000
                
                asyncio.run_coroutine_threadsafe(
                    audio_track._queue.put((new_frame, eventpoint)),
                    loop
                )
        
        logger.info(f"[{self.avatar_id}] Process frames thread stopped")
    
    def start(self, loop, audio_track, video_track):
        """启动引擎 - 照搬 try 的 render() 方法"""
        logger.info(f"[{self.avatar_id}] Starting engine...")
        
        if not self._loaded:
            raise RuntimeError("Models not loaded")
        if self.asr is None:
            raise RuntimeError("ASR not setup")
        
        # 保存引用，用于音频直接推送
        self.loop = loop
        self.audio_track = audio_track
        
        self.quit_event.clear()
        self.render_event.set()
        
        # 启动 TTS 线程
        if self.tts:
            self.tts.start(self.quit_event)
        
        # 启动处理帧线程
        self.process_thread = Thread(
            target=self.process_frames_worker,
            args=(loop, audio_track, video_track),
            daemon=True
        )
        self.process_thread.start()
        
        # 启动推理线程
        self.inference_thread = Thread(
            target=self.inference_worker,
            daemon=True
        )
        self.inference_thread.start()
        
        logger.info(f"[{self.avatar_id}] Engine started")
    
    def run_asr_loop(self, quit_event, video_track):
        """ASR 主循环 - 照搬 try 的 render() 主循环"""
        while not quit_event.is_set() and not self.quit_event.is_set():
            self.asr.run_step()
            
            # 背压控制
            if video_track._queue.qsize() >= 1.5 * self.batch_size:
                time.sleep(0.04 * video_track._queue.qsize() * 0.8)
    
    def stop(self):
        """停止引擎"""
        logger.info(f"[{self.avatar_id}] Stopping engine...")
        
        self.render_event.clear()
        self.quit_event.set()
        
        if self.inference_thread:
            self.inference_thread.join(timeout=2)
        if self.process_thread:
            self.process_thread.join(timeout=2)
        
        # 清空队列
        while not self.res_frame_queue.empty():
            try:
                self.res_frame_queue.get_nowait()
            except queue.Empty:
                break
        
        if self.asr:
            self.asr.flush()
        if self.tts:
            self.tts.flush()
        
        logger.info(f"[{self.avatar_id}] Engine stopped")
