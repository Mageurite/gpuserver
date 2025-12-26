# MuseTalk / Avatar 模块集成说明

> 更新时间：2025-12-24
> 状态：✅ 基础集成完成

## 📋 概述

MuseTalk / Avatar 模块已集成到 GPU Server，用于支持教师端创建数字化身（Avatar）功能。

## 🏗️ 架构

### 模块结构

```
gpuserver/
├── musetalk/
│   ├── __init__.py
│   └── avatar_manager.py      # Avatar 管理器
├── management_api.py           # 包含 Avatar API 接口
├── config.py                   # MuseTalk 配置
└── temp/tests/test_musetalk.py # 测试文件
```

### 核心组件

1. **AvatarManager** (`musetalk/avatar_manager.py`)
   - Avatar 创建和管理
   - 视频预处理
   - 与 MuseTalk 集成

2. **Management API** (`management_api.py`)
   - 提供 REST API 接口
   - 支持视频上传和路径创建
   - Avatar CRUD 操作

## 📡 API 接口

### 1. 创建 Avatar（从路径）

```http
POST /v1/avatars
Content-Type: application/json

{
  "avatar_id": "avatar_teacher_1",
  "video_path": "/path/to/video.mp4",
  "apply_blur": false,
  "tutor_id": 1
}
```

**响应**：
```json
{
  "status": "success",
  "avatar_id": "avatar_teacher_1",
  "avatar_path": "/workspace/gpuserver/data/avatars/avatar_teacher_1",
  "message": "Avatar created successfully"
}
```

### 2. 创建 Avatar（上传文件）

```http
POST /v1/avatars/upload
Content-Type: multipart/form-data

avatar_id: avatar_teacher_2
apply_blur: false
tutor_id: 1
video_file: [binary video file]
```

### 3. 获取 Avatar 信息

```http
GET /v1/avatars/{avatar_id}
```

### 4. 列出所有 Avatar

```http
GET /v1/avatars
```

**响应**：
```json
{
  "total": 2,
  "avatars": [
    "avatar_teacher_1",
    "avatar_teacher_2"
  ]
}
```

### 5. 删除 Avatar

```http
DELETE /v1/avatars/{avatar_id}
```

## ⚙️ 配置

### 环境变量

在 `.env` 文件中配置：

```bash
# MuseTalk / Avatar 配置
# 是否启用 MuseTalk（如果为 false，则使用 Mock 模式）
ENABLE_MUSETALK=false

# Avatar 存储目录
AVATARS_DIR=/workspace/gpuserver/data/avatars

# MuseTalk 基础目录
MUSETALK_BASE=/workspace/MuseTalk

# MuseTalk Conda 环境路径（可选）
MUSETALK_CONDA_ENV=

# FFmpeg 路径
FFMPEG_PATH=ffmpeg
```

### 工作模式

#### Mock 模式（默认，开发测试用）

```bash
ENABLE_MUSETALK=false
```

- 不需要 MuseTalk 环境
- 快速创建测试 Avatar
- 适合开发和测试

#### 真实模式（生产环境）

```bash
ENABLE_MUSETALK=true
MUSETALK_BASE=/workspace/MuseTalk
MUSETALK_CONDA_ENV=/workspace/conda_envs/mt
FFMPEG_PATH=/workspace/MuseTalk/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg
```

**要求**：
- MuseTalk 已安装和配置
- FFmpeg 可用
- 相关模型文件已下载

## 🚀 使用流程

### 教师端创建 Avatar

1. **上传视频文件**
   - 教师在 Web 界面上传视频
   - 视频要求：MP4 格式，包含人脸正面

2. **调用 GPU Server API**
   ```javascript
   // Web Server 调用 GPU Server
   POST http://gpu-server:9000/v1/avatars/upload
   ```

3. **Avatar 创建**
   - GPU Server 处理视频
   - 生成 Avatar 数据
   - 存储到 avatars 目录

4. **保存到数据库**
   - Web Server 将 avatar_id 保存到 Tutor 记录
   - 关联 Tutor 和 Avatar

### 学生端使用 Avatar

1. **创建会话**
   - Web Server 创建会话时传递 tutor_id
   - GPU Server 加载对应的 Avatar

2. **实时对话**
   - WebSocket 连接建立
   - AI 生成回复
   - TTS 合成语音
   - MuseTalk 生成唇形同步视频（如果启用）

## 🧪 测试

### 运行测试

```bash
cd /workspace/gpuserver
PYTHONPATH=/workspace/gpuserver python3 temp/tests/test_musetalk.py
```

### 测试内容

- ✅ Mock Avatar 创建
- ✅ Avatar 管理（列表、获取、删除）
- ✅ API 接口验证

### 手动测试

```bash
# 1. 启动 GPU Server
cd /workspace/gpuserver
python3 unified_server.py

# 2. 测试 API（另一个终端）
# 列出 Avatar
curl http://localhost:9000/v1/avatars

# 创建 Avatar（Mock 模式）
curl -X POST http://localhost:9000/v1/avatars \
  -H "Content-Type: application/json" \
  -d '{
    "avatar_id": "test_avatar_1",
    "video_path": "/tmp/test.mp4",
    "apply_blur": false
  }'

# 获取 Avatar 信息
curl http://localhost:9000/v1/avatars/test_avatar_1

# 删除 Avatar
curl -X DELETE http://localhost:9000/v1/avatars/test_avatar_1
```

## 🔄 与 Web Server 集成

### 1. Web Server 端修改

在 Tutor 创建流程中添加 Avatar 上传：

```python
# app_backend/app/routers/admin.py

@router.post("/tutors")
async def create_tutor(
    name: str = Form(...),
    description: str = Form(...),
    avatar_video: UploadFile = File(None),  # 可选的视频文件
    db: Session = Depends(get_db)
):
    # 1. 创建 Tutor 记录
    tutor = Tutor(name=name, description=description)
    db.add(tutor)
    db.commit()

    # 2. 如果上传了视频，调用 GPU Server 创建 Avatar
    if avatar_video:
        avatar_id = f"avatar_tutor_{tutor.id}"

        # 调用 GPU Server API
        async with httpx.AsyncClient() as client:
            files = {"video_file": avatar_video.file}
            data = {
                "avatar_id": avatar_id,
                "tutor_id": tutor.id,
                "apply_blur": False
            }
            response = await client.post(
                f"{GPU_SERVER_URL}/v1/avatars/upload",
                files=files,
                data=data
            )

        # 3. 保存 avatar_id 到 Tutor
        if response.status_code == 201:
            tutor.avatar_id = avatar_id
            db.commit()

    return tutor
```

### 2. 数据库 Schema 更新

在 Tutor 表中添加 avatar_id 字段：

```python
class Tutor(Base):
    __tablename__ = "tutors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    avatar_id = Column(String, nullable=True)  # 新增
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 3. 会话创建时传递 Avatar

```python
# 创建会话时，从 Tutor 获取 avatar_id
tutor = db.query(Tutor).filter(Tutor.id == tutor_id).first()

session_data = {
    "tutor_id": tutor_id,
    "student_id": student_id,
    "avatar_id": tutor.avatar_id  # 传递给 GPU Server
}
```

## 📝 完整实现参考

完整的 MuseTalk 实现可参考：

- **参考代码**: `/workspace/try/lip-sync/`
  - `create_avatar.py` - Avatar 创建流程
  - `live_server.py` - MuseTalk 服务
  - `lip-sync.json` - 配置文件

- **MuseTalk 项目**: `/workspace/MuseTalk/`
  - 需要单独安装和配置
  - 参考 README.md

## ⚠️ 注意事项

1. **Mock vs 真实模式**
   - 开发测试使用 Mock 模式
   - 生产环境需要配置真实 MuseTalk

2. **资源需求**
   - 真实 MuseTalk 需要大量 GPU 资源
   - 建议使用独立的 GPU Server

3. **视频要求**
   - 包含清晰的人脸正面
   - 推荐 25fps
   - MP4 格式

4. **存储管理**
   - Avatar 数据占用存储空间
   - 需要定期清理不用的 Avatar

## 🎯 下一步

1. ✅ 基础 Avatar 模块已完成
2. ⏳ 集成到 Web Server 的 Tutor 创建流程
3. ⏳ 实现完整的 MuseTalk 调用（如果需要）
4. ⏳ 实现实时视频流传输（WebRTC）

---

**状态**: ✅ Mock 模式测试通过，API 接口完整
**最后更新**: 2025-12-24
