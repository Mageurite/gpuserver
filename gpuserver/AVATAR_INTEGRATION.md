# Avatar (MuseTalk) 集成文档

本文档说明如何使用真实的 MuseTalk 进行 Avatar 生成。

## 📋 功能概述

Avatar Manager 支持两种模式：
1. **Mock 模式**：快速测试，不生成真实视频
2. **Real 模式**：使用 MuseTalk 生成真实的数字人 Avatar

## 🔧 配置

### 1. 环境变量配置

在 `.env` 文件中配置：

```bash
# Avatar/MuseTalk Configuration
ENABLE_AVATAR=true                                           # 启用真实 MuseTalk
AVATARS_DIR=/workspace/gpuserver/data/avatars                # Avatar 存储目录
MUSETALK_BASE=/workspace/MuseTalk                            # MuseTalk 基础目录
MUSETALK_CONDA_ENV=/workspace/conda_envs/mt                  # MuseTalk Conda 环境
FFMPEG_PATH=/workspace/MuseTalk/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg  # FFmpeg 路径
```

**重要说明**：
- `ENABLE_AVATAR=true`：启用真实 MuseTalk 处理
- `ENABLE_AVATAR=false`：使用 Mock 模式（仅保存视频文件，不生成 Avatar）

### 2. 验证环境

确保以下组件存在：

```bash
# 检查 MuseTalk 目录
ls -la /workspace/MuseTalk/inference.sh

# 检查 MuseTalk Conda 环境
ls -la /workspace/conda_envs/mt/bin/python

# 检查 FFmpeg
/workspace/MuseTalk/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg -version
```

## 📝 API 使用

### 1. 上传视频创建 Avatar

```bash
curl -X POST "http://localhost:9000/v1/avatars/upload" \
  -F "avatar_id=avatar_tutor_10" \
  -F "tutor_id=10" \
  -F "apply_blur=false" \
  -F "video_file=@/path/to/your/video.mp4"
```

**参数说明**：
- `avatar_id`：Avatar 唯一标识符（必填）
- `tutor_id`：关联的 Tutor ID（可选）
- `apply_blur`：是否应用背景模糊（默认 false）
- `video_file`：视频文件（必填）

**响应示例**：
```json
{
  "status": "success",
  "avatar_id": "avatar_tutor_10",
  "avatar_path": "/workspace/gpuserver/data/avatars/avatar_tutor_10",
  "message": "Avatar created successfully with MuseTalk"
}
```

### 2. 从文件路径创建 Avatar

```bash
curl -X POST "http://localhost:9000/v1/avatars/create" \
  -H "Content-Type: application/json" \
  -d '{
    "avatar_id": "avatar_tutor_10",
    "video_path": "/path/to/video.mp4",
    "apply_blur": false,
    "tutor_id": 10
  }'
```

### 3. 获取 Avatar 信息

```bash
curl "http://localhost:9000/v1/avatars/avatar_tutor_10"
```

### 4. 列出所有 Avatar

```bash
curl "http://localhost:9000/v1/avatars"
```

### 5. 删除 Avatar

```bash
curl -X DELETE "http://localhost:9000/v1/avatars/avatar_tutor_10"
```

## 🔄 Avatar 创建流程

当 `ENABLE_AVATAR=true` 时，创建流程如下：

### 1. 视频预处理
- 转换视频到 25fps（MuseTalk 要求）
- 可选：应用背景模糊（需要额外服务，目前未实现）

### 2. MuseTalk 处理
- 复制预处理后的视频到 `MuseTalk/data/video/yongen.mp4`
- 清理旧的 Avatar 结果
- 运行 `MuseTalk/inference.sh v1.5 realtime`
- 使用 MuseTalk conda 环境 (`/workspace/conda_envs/mt`)

### 3. 结果保存
- 从 `MuseTalk/results/v15/avatars/avator_1/` 复制结果
- 保存到 `avatars/{avatar_id}/`
- 创建 `avatar_info.txt` 记录元数据

## 📂 Avatar 目录结构

创建成功后，Avatar 目录结构如下：

```
/workspace/gpuserver/data/avatars/avatar_tutor_10/
├── avatar_info.txt          # Avatar 元数据
├── full_imgs/               # 完整图像序列
├── coords.pkl               # 坐标数据
├── latents.pt               # 潜在特征
└── ...                      # 其他 MuseTalk 生成的文件
```

## 🐛 故障排查

### 问题 1: MuseTalk inference 失败

**检查步骤**：
```bash
# 1. 验证 MuseTalk 环境
ls -la /workspace/MuseTalk/inference.sh

# 2. 检查 Conda 环境
/workspace/conda_envs/mt/bin/python --version

# 3. 手动运行测试
cd /workspace/MuseTalk
bash inference.sh v1.5 realtime
```

### 问题 2: FFmpeg 转换失败

**检查步骤**：
```bash
# 验证 FFmpeg
/workspace/MuseTalk/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg -version

# 测试视频转换
/workspace/MuseTalk/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg \
  -i input.mp4 -r 25 -b:v 3000k -c:v libx264 -y output.mp4
```

### 问题 3: 仍然是 Mock 模式

**原因**：
- `.env` 中 `ENABLE_AVATAR=false`
- 或者没有重启服务

**解决方法**：
```bash
# 1. 修改 .env
vim .env
# 设置 ENABLE_AVATAR=true

# 2. 重启服务
./restart_all.sh

# 3. 验证配置
curl http://localhost:9000/health
```

## 📊 性能说明

MuseTalk Avatar 创建是一个**耗时操作**：
- 视频预处理：1-5 秒
- MuseTalk 推理：根据视频长度和硬件，可能需要几分钟到十几分钟
- 结果复制：1-2 秒

**建议**：
- 在生产环境中使用异步任务队列（如 Celery）
- 为用户提供进度反馈
- 考虑在创建过程中返回任务 ID，允许轮询状态

## 🔗 相关文档

- [MuseTalk 原始实现](../../try/lip-sync/create_avatar.py)
- [Avatar Manager 源码](musetalk/avatar_manager.py)
- [GPU Server README](README.md)

---

**最后更新**: 2025-12-26
