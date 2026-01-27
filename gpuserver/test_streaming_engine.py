#!/usr/bin/env python3
"""
测试流式 TTS + Lip-Sync 引擎

使用方法:
    cd /workspace/gpuserver
    PYTHONPATH=/workspace/gpuserver:$PYTHONPATH python test_streaming_engine.py

测试内容:
1. 流式TTS - 验证音频分块输出
2. 完整流式处理 - TTS + ASR + MuseTalk推理
3. 延迟测试 - 测量首帧延迟
"""

import os
import sys
import time
import asyncio
import logging

# 设置路径
sys.path.insert(0, '/workspace/gpuserver')
os.environ['MUSETALK_BASE'] = '/workspace/MuseTalk'

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_tts_only():
    """测试独立的TTS功能"""
    print("\n" + "="*60)
    print("测试 1: 独立 TTS 测试")
    print("="*60)
    
    import edge_tts
    import asyncio
    
    async def run_tts():
        text = "你好，我是你的虚拟导师。今天我们来学习一个有趣的话题。"
        voice = "zh-CN-XiaoxiaoNeural"
        
        t_start = time.time()
        communicate = edge_tts.Communicate(text, voice)
        
        chunk_count = 0
        first_chunk_time = None
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunk_count += 1
                if first_chunk_time is None:
                    first_chunk_time = time.time() - t_start
                    print(f"  ⚡ 首个音频块: {first_chunk_time:.3f}s")
                    
        total_time = time.time() - t_start
        print(f"  ✅ TTS完成: {total_time:.3f}s, 共 {chunk_count} 个音频块")
        
    asyncio.run(run_tts())


def test_streaming_tts_worker():
    """测试流式TTS Worker"""
    print("\n" + "="*60)
    print("测试 2: StreamingTTSWorker 测试")
    print("="*60)
    
    from threading import Event
    from musetalk.streaming_engine import StreamingTTSWorker
    import numpy as np
    
    class MockParent:
        def __init__(self):
            self.audio_chunks = []
            self.first_chunk_time = None
            self.start_time = None
            
        def put_audio_frame(self, chunk, eventpoint=None):
            if self.first_chunk_time is None:
                self.first_chunk_time = time.time() - self.start_time
                print(f"  ⚡ 首个音频帧: {self.first_chunk_time:.3f}s")
            self.audio_chunks.append((chunk, eventpoint))
            
            if eventpoint and eventpoint.get('status') == 'end':
                print(f"  ✅ TTS结束标记收到")
    
    parent = MockParent()
    quit_event = Event()
    
    # 创建TTS Worker
    tts_worker = StreamingTTSWorker(parent, fps=50, voice="zh-CN-XiaoxiaoNeural")
    tts_worker.start(quit_event)
    
    # 发送文本
    text = "这是一个流式TTS测试。音频将被分成20毫秒的小块输出。"
    parent.start_time = time.time()
    tts_worker.put_text(text)
    
    # 等待完成
    time.sleep(5)
    
    # 停止
    quit_event.set()
    time.sleep(0.5)
    
    print(f"  📊 收到 {len(parent.audio_chunks)} 个音频帧")
    if parent.audio_chunks:
        total_samples = sum(len(c[0]) for c in parent.audio_chunks)
        duration = total_samples / 16000
        print(f"  📊 总音频时长: {duration:.2f}s")


def test_full_streaming_engine():
    """测试完整的流式引擎"""
    print("\n" + "="*60)
    print("测试 3: 完整流式引擎测试 (TTS + ASR + MuseTalk)")
    print("="*60)
    
    # 检查Avatar是否存在
    avatars_dir = "/workspace/gpuserver/data/avatars"
    if not os.path.exists(avatars_dir):
        print("  ❌ Avatar目录不存在，跳过此测试")
        return
        
    avatars = [d for d in os.listdir(avatars_dir) if os.path.isdir(os.path.join(avatars_dir, d))]
    if not avatars:
        print("  ❌ 没有找到Avatar，跳过此测试")
        return
        
    avatar_id = avatars[0]
    avatar_path = os.path.join(avatars_dir, avatar_id)
    print(f"  使用Avatar: {avatar_id}")
    
    # 检查Avatar数据完整性
    required_files = ['latents.pt', 'coords.pkl', 'mask_coords.pkl', 'full_imgs', 'mask']
    missing = [f for f in required_files if not os.path.exists(os.path.join(avatar_path, f))]
    if missing:
        print(f"  ❌ Avatar数据不完整，缺少: {missing}")
        return
    
    print("  📦 Avatar数据完整")
    
    # 测试引擎创建
    print("  🔄 正在加载模型（可能需要30-60秒）...")
    
    from musetalk.streaming_engine import StreamingLipSyncEngine
    
    t_start = time.time()
    engine = StreamingLipSyncEngine(
        avatar_id=avatar_id,
        avatar_path=avatar_path,
        batch_size=8,
        fps=50,
        voice="zh-CN-XiaoxiaoNeural"
    )
    
    try:
        engine.setup()
        setup_time = time.time() - t_start
        print(f"  ✅ 引擎初始化: {setup_time:.1f}s")
        
        engine.start()
        print("  ✅ 引擎已启动")
        
        # 测试文本处理
        text = "你好，这是一个测试。"
        print(f"  🎤 发送文本: {text}")
        
        t_start = time.time()
        
        async def process():
            frame_count = 0
            first_frame_time = None
            
            async for video_frame, audio_samples in engine.process_text(text):
                if first_frame_time is None:
                    first_frame_time = time.time() - t_start
                    print(f"  ⚡ 首帧延迟: {first_frame_time:.3f}s")
                    
                frame_count += 1
                
                if frame_count % 10 == 0:
                    print(f"  📊 已生成 {frame_count} 帧...")
                    
            total_time = time.time() - t_start
            print(f"  ✅ 完成: {frame_count} 帧, 总耗时 {total_time:.2f}s")
            if frame_count > 0:
                print(f"  📊 平均帧率: {frame_count/total_time:.1f} fps")
                
        asyncio.run(process())
        
    finally:
        engine.stop()
        print("  ✅ 引擎已停止")


def test_latency_comparison():
    """对比测试：串行 vs 流式处理的延迟"""
    print("\n" + "="*60)
    print("测试 4: 延迟对比测试")
    print("="*60)
    
    import edge_tts
    
    text = "这是一个延迟测试文本，用于对比串行和流式处理的首帧延迟差异。"
    
    # 1. 串行处理（传统方式）
    print("\n  [串行处理]")
    t_start = time.time()
    
    async def serial_process():
        # TTS生成完整音频
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
        
    audio = asyncio.run(serial_process())
    tts_time = time.time() - t_start
    print(f"    TTS完成: {tts_time:.3f}s")
    print(f"    (此后还需要等待MuseTalk处理完整音频)")
    
    # 2. 流式处理（新方式）
    print("\n  [流式处理]")
    print("    TTS边生成边发送，首帧延迟仅取决于:")
    print("    - TTS首块延迟 (~0.3s)")
    print("    - ASR特征提取 (~0.2s)")
    print("    - MuseTalk首批推理 (~0.5s)")
    print("    - 预期首帧延迟: ~1.0-1.5s")
    
    print("\n  📊 理论延迟对比:")
    print(f"    串行: TTS({tts_time:.1f}s) + MuseTalk(~2s) = ~{tts_time+2:.1f}s 首帧")
    print(f"    流式: ~1.0-1.5s 首帧 (提升 {(tts_time+2-1.5)/(tts_time+2)*100:.0f}%)")


def main():
    print("="*60)
    print("  流式 TTS + Lip-Sync 引擎测试")
    print("="*60)
    
    # 测试1: 独立TTS
    try:
        test_tts_only()
    except Exception as e:
        print(f"  ❌ 测试1失败: {e}")
    
    # 测试2: StreamingTTSWorker
    try:
        test_streaming_tts_worker()
    except Exception as e:
        print(f"  ❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试3: 完整流式引擎
    try:
        test_full_streaming_engine()
    except Exception as e:
        print(f"  ❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试4: 延迟对比
    try:
        test_latency_comparison()
    except Exception as e:
        print(f"  ❌ 测试4失败: {e}")
    
    print("\n" + "="*60)
    print("  测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
