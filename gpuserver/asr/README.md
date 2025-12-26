# ASR Module

自动语音识别（Automatic Speech Recognition）模块，用于将音频转换为文本。

## 功能特性

- 支持 OpenAI Whisper 模型
- 支持多种音频格式（WAV, MP3, OGG, WebM 等）
- 支持中文和英文识别
- 支持 CUDA 加速
- 支持 Mock 模式（用于测试）

## 安装依赖

```bash
pip install openai-whisper soundfile
```

## 配置

在 `.env` 文件中配置 ASR：

```bash
# Whisper 模型: tiny, base, small, medium, large
ASR_MODEL=base

# 是否启用 ASR（如果为 false，则使用 Mock 模式）
ENABLE_ASR=true

# ASR 设备: cuda 或 cpu
ASR_DEVICE=cuda

# ASR 默认语言: zh (中文), en (英文)
ASR_LANGUAGE=zh
```

## Whisper 模型说明

| 模型 | 大小 | 速度 | 准确率 | 适用场景 |
|------|------|------|--------|----------|
| tiny | 39M | 最快 | 较低 | 快速测试 |
| base | 74M | 快 | 中等 | 开发环境 |
| small | 244M | 中等 | 较高 | 生产环境 |
| medium | 769M | 慢 | 高 | 高质量需求 |
| large | 1550M | 最慢 | 最高 | 最高质量需求 |

## 使用示例

### 在 AIEngine 中使用

```python
from ai_models import get_ai_engine

# 获取 AI 引擎
engine = get_ai_engine(tutor_id=1)

# 转录音频（audio_data 是 base64 编码的音频）
transcription = await engine.process_audio(audio_data)
print(f"转录结果: {transcription}")
```

### 直接使用 ASR Engine

```python
from asr import get_asr_engine
import base64

# 获取 ASR 引擎
asr_engine = get_asr_engine(
    model_name="base",
    enable_real=True,
    device="cuda"
)

# 读取音频文件
with open("audio.wav", "rb") as f:
    audio_bytes = f.read()
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

# 转录
text = await asr_engine.transcribe(audio_base64, language="zh")
print(f"转录结果: {text}")
```

## 工作流程

1. **接收音频**: 从 WebSocket 接收 base64 编码的音频数据
2. **解码音频**: 将 base64 解码为原始音频字节
3. **保存临时文件**: Whisper 需要文件路径，因此保存到临时文件
4. **调用 Whisper**: 使用 Whisper 模型进行转录
5. **返回文本**: 提取并返回转录的文本
6. **清理临时文件**: 删除临时文件

## Mock 模式

当 `ENABLE_ASR=false` 时，ASR 引擎会使用 Mock 模式，返回固定的测试文本，用于：
- 在没有 GPU 的环境中测试
- 在开发环境中快速测试
- 在 Whisper 模型未安装时降级

## 性能优化

1. **使用较小的模型**: 在开发环境使用 `tiny` 或 `base` 模型
2. **启用 CUDA**: 设置 `ASR_DEVICE=cuda` 使用 GPU 加速
3. **使用 FP16**: 在 CUDA 设备上自动启用 FP16 加速
4. **异步处理**: 使用线程池处理同步的 Whisper 调用，避免阻塞事件循环

## 故障排除

### 1. Whisper 模型加载失败

**问题**: 提示 "whisper package not installed"

**解决**: 安装 openai-whisper

```bash
pip install openai-whisper
```

### 2. CUDA 错误

**问题**: 提示 CUDA 相关错误

**解决**: 使用 CPU 模式

```bash
# 在 .env 中设置
ASR_DEVICE=cpu
```

### 3. 音频格式不支持

**问题**: 音频格式无法识别

**解决**: Whisper 支持多种格式，但确保音频文件完整且未损坏。可以使用 ffmpeg 转换：

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 output.wav
```

### 4. 降级到 Mock 模式

如果 ASR 出现问题，系统会自动降级到 Mock 模式，可以在日志中看到：

```
Falling back to Mock ASR mode
```

## 未来改进

- [ ] 支持 Faster Whisper（更快的推理速度）
- [ ] 支持流式识别（边说边转录）
- [ ] 支持多语言自动检测
- [ ] 支持自定义词汇表（提高专业术语识别准确率）
- [ ] 支持 VAD（语音活动检测）
