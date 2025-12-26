# GPU Server Avatar API 接口验证

## ✅ GPU Server 端已实现的接口

### 1. 创建 Avatar（从路径）
```http
POST /v1/avatars
Content-Type: application/json

{
  "avatar_id": "avatar_tutor_123",
  "video_path": "/path/to/video.mp4",
  "apply_blur": false,
  "tutor_id": 123
}
```

**响应**：
```json
{
  "status": "success",
  "avatar_id": "avatar_tutor_123",
  "avatar_path": "/workspace/gpuserver/data/avatars/avatar_tutor_123",
  "message": "[Mock] Avatar created successfully",
  "mock": true
}
```

### 2. 创建 Avatar（上传文件）
```http
POST /v1/avatars/upload
Content-Type: multipart/form-data

avatar_id: avatar_tutor_456
apply_blur: false
tutor_id: 456
video_file: [binary]
```

### 3. 列出所有 Avatar
```http
GET /v1/avatars
```

**响应**：
```json
{
  "total": 2,
  "avatars": ["avatar_tutor_123", "avatar_tutor_456"]
}
```

### 4. 获取 Avatar 信息
```http
GET /v1/avatars/{avatar_id}
```

### 5. 删除 Avatar
```http
DELETE /v1/avatars/{avatar_id}
```

## 🔗 Web Server 集成说明

Web Server 需要调用 GPU Server 的这些接口。根据 Web Server 的反馈，需要：

### Web Server 端需要实现的部分

1. **在 Tutor 创建时上传视频到 GPU Server**

```python
# Web Server: app_backend/app/routers/admin.py

@router.post("/tutors")
async def create_tutor(
    name: str = Form(...),
    description: str = Form(...),
    avatar_video: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # 1. 创建 Tutor 记录
    tutor = Tutor(name=name, description=description)
    db.add(tutor)
    db.commit()
    db.refresh(tutor)

    # 2. 如果上传了 Avatar 视频，调用 GPU Server
    if avatar_video:
        avatar_id = f"avatar_tutor_{tutor.id}"

        # 调用 GPU Server 的 /v1/avatars/upload 接口
        import httpx
        async with httpx.AsyncClient() as client:
            files = {"video_file": (avatar_video.filename, avatar_video.file, avatar_video.content_type)}
            data = {
                "avatar_id": avatar_id,
                "apply_blur": False,
                "tutor_id": tutor.id
            }

            response = await client.post(
                f"{settings.ENGINE_URL}/v1/avatars/upload",  # GPU Server URL
                files=files,
                data=data,
                timeout=300.0  # Avatar 创建可能需要时间
            )

            if response.status_code == 201:
                result = response.json()
                # 保存 avatar_id 到 Tutor 表
                tutor.avatar_id = result["avatar_id"]
                db.commit()

    return tutor
```

2. **数据库 Schema 添加 avatar_id 字段**

```python
# Web Server: app_backend/app/models.py

class Tutor(Base):
    __tablename__ = "tutors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    avatar_id = Column(String, nullable=True)  # 新增字段
    created_at = Column(DateTime, default=datetime.utcnow)
```

3. **创建会话时传递 avatar_id**

```python
# Web Server 创建会话时
tutor = db.query(Tutor).filter(Tutor.id == tutor_id).first()

# 调用 GPU Server 创建会话
session_response = await client.post(
    f"{settings.ENGINE_URL}/v1/sessions",
    json={
        "tutor_id": tutor_id,
        "student_id": student_id,
        "avatar_id": tutor.avatar_id  # 传递 avatar_id（如果存在）
    }
)
```

## 🧪 测试接口

### 使用 curl 测试（需要启动 GPU Server）

```bash
# 1. 启动 GPU Server
cd /workspace/gpuserver
python3 unified_server.py

# 2. 在另一个终端测试

# 健康检查
curl http://localhost:9000/health

# 列出 Avatar
curl http://localhost:9000/v1/avatars

# 创建 Avatar（Mock 模式）
curl -X POST http://localhost:9000/v1/avatars \
  -H "Content-Type: application/json" \
  -d '{
    "avatar_id": "avatar_test_1",
    "video_path": "/tmp/test.mp4",
    "apply_blur": false,
    "tutor_id": 1
  }'

# 上传视频创建 Avatar
curl -X POST http://localhost:9000/v1/avatars/upload \
  -F "avatar_id=avatar_test_2" \
  -F "apply_blur=false" \
  -F "tutor_id=2" \
  -F "video_file=@/path/to/video.mp4"

# 获取 Avatar 信息
curl http://localhost:9000/v1/avatars/avatar_test_1

# 删除 Avatar
curl -X DELETE http://localhost:9000/v1/avatars/avatar_test_1
```

## 📝 总结

**GPU Server 端**：✅ 已完成
- 所有 Avatar API 接口已实现
- Mock 模式测试通过
- 支持视频上传和路径创建

**Web Server 端**：需要实现
1. 在 Tutor 创建页面添加视频上传表单
2. 调用 GPU Server 的 `/v1/avatars/upload` 接口
3. 数据库添加 `avatar_id` 字段
4. 创建会话时传递 `avatar_id`

**GPU Server 无需额外工作**，接口已就绪！
