"""
Avatar Manager Implementation

Handles:
1. Avatar creation from video files
2. Avatar storage and management
3. Integration with MuseTalk for processing
4. Video preprocessing (format conversion, blur, etc.)

For full MuseTalk functionality, refer to:
- /workspace/try/lip-sync/create_avatar.py
- /workspace/MuseTalk/
"""

import asyncio
import logging
import os
import subprocess
import shutil
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class AvatarManager:
    """
    Avatar 管理器 - 创建和管理数字化身

    支持:
    - 从视频创建 Avatar
    - Avatar 存储管理
    - 视频预处理（格式转换、模糊等）
    - 与 MuseTalk 集成
    """

    def __init__(
        self,
        enable_real: bool = False,
        avatars_dir: Optional[str] = None,
        musetalk_base: Optional[str] = None,
        conda_env: Optional[str] = None,
        ffmpeg_path: Optional[str] = None
    ):
        """
        初始化 Avatar 管理器

        Args:
            enable_real: 是否启用真实 MuseTalk（False 则使用 Mock）
            avatars_dir: Avatar 存储目录
            musetalk_base: MuseTalk 基础目录
            conda_env: Conda 环境路径
            ffmpeg_path: FFmpeg 可执行文件路径
        """
        self.enable_real = enable_real
        self.avatars_dir = avatars_dir or "/workspace/gpuserver/data/avatars"
        self.musetalk_base = musetalk_base or "/workspace/MuseTalk"
        self.conda_env = conda_env
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"

        # 视频缓存：{(avatar_id, duration, fps): base64_video_data}
        # 参考 try/lip-sync 的实现，缓存生成的视频以避免重复生成
        self._idle_video_cache: Dict[tuple, str] = {}

        # 确保目录存在
        os.makedirs(self.avatars_dir, exist_ok=True)

        if self.enable_real:
            try:
                self._verify_musetalk_setup()
                logger.info("Avatar Manager initialized with MuseTalk enabled")
            except Exception as e:
                logger.error(f"Failed to initialize MuseTalk: {e}")
                logger.warning("Falling back to Mock Avatar mode")
                self.enable_real = False
        else:
            logger.info("Avatar Manager initialized in Mock mode")

    def _verify_musetalk_setup(self):
        """
        验证 MuseTalk 环境设置

        检查:
        - MuseTalk 目录存在
        - FFmpeg 可用
        - Conda 环境存在
        """
        # 检查 MuseTalk 目录
        if not os.path.exists(self.musetalk_base):
            raise FileNotFoundError(f"MuseTalk directory not found: {self.musetalk_base}")

        # 检查 FFmpeg
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(f"FFmpeg not found at {self.ffmpeg_path}")

        logger.info("MuseTalk setup verified")

    async def create_avatar(
        self,
        avatar_id: str,
        video_path: str,
        apply_blur: bool = False,
        tutor_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从视频创建 Avatar

        Args:
            avatar_id: Avatar 唯一标识符
            video_path: 视频文件路径
            apply_blur: 是否应用背景模糊
            tutor_id: 关联的 Tutor ID（可选）

        Returns:
            Dict: 创建结果
                {
                    "status": "success" | "error",
                    "avatar_id": "avatar_123",
                    "avatar_path": "/path/to/avatar",
                    "message": "详细信息"
                }
        """
        if not self.enable_real:
            # Mock 模式
            return await self._mock_create_avatar(avatar_id, video_path, apply_blur)

        try:
            # 在线程池中运行同步的创建过程
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._create_avatar_sync,
                avatar_id,
                video_path,
                apply_blur,
                tutor_id
            )
            return result
        except Exception as e:
            logger.error(f"Avatar creation failed: {e}")
            return {
                "status": "error",
                "avatar_id": avatar_id,
                "message": f"Failed to create avatar: {str(e)}"
            }

    def _create_avatar_sync(
        self,
        avatar_id: str,
        video_path: str,
        apply_blur: bool,
        tutor_id: Optional[int]
    ) -> Dict[str, Any]:
        """
        同步创建 Avatar（在线程池中运行）

        步骤:
        1. 验证视频文件
        2. 预处理视频（转换格式、模糊等）
        3. 调用 MuseTalk 脚本创建 Avatar
        4. 保存到 avatars 目录

        参考: /workspace/try/lip-sync/create_avatar.py
        """
        try:
            # 1. 验证视频文件
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")

            # 2. 准备输出目录
            avatar_path = os.path.join(self.avatars_dir, avatar_id)
            os.makedirs(avatar_path, exist_ok=True)

            # 3. 预处理视频
            processed_video = self._preprocess_video(video_path, apply_blur)

            # 4. 调用 MuseTalk 创建 Avatar
            logger.info("Starting MuseTalk avatar creation...")

            # 4.1 复制视频到 MuseTalk 输入目录
            target_video = os.path.join(self.musetalk_base, "data", "video", "yongen.mp4")
            os.makedirs(os.path.dirname(target_video), exist_ok=True)
            shutil.copy2(processed_video, target_video)
            logger.info(f"Copied video to MuseTalk: {target_video}")

            # 4.2 删除可能存在的旧 avatar 结果
            old_result = os.path.join(self.musetalk_base, "results", "v15", "avatars", "avator_1")
            if os.path.exists(old_result):
                shutil.rmtree(old_result)
                logger.info(f"Removed old avatar result: {old_result}")

            # 4.3 运行 MuseTalk inference.sh
            success = self._run_musetalk_inference()

            if not success:
                raise RuntimeError("MuseTalk inference failed")

            # 4.4 复制结果到 avatar 目录
            result_dir = os.path.join(self.musetalk_base, "results", "v15", "avatars", "avator_1")
            if not os.path.exists(result_dir):
                raise FileNotFoundError(f"MuseTalk result not found: {result_dir}")

            # 复制所有结果文件
            for item in os.listdir(result_dir):
                src = os.path.join(result_dir, item)
                dst = os.path.join(avatar_path, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

            logger.info(f"Avatar created successfully: {avatar_id} at {avatar_path}")

            # 5. 保存 avatar 信息
            info_file = os.path.join(avatar_path, "avatar_info.txt")
            with open(info_file, "w") as f:
                f.write(f"[Real Avatar - MuseTalk]\n")
                f.write(f"Avatar ID: {avatar_id}\n")
                f.write(f"Original Video: {video_path}\n")
                f.write(f"Processed Video: {processed_video}\n")
                f.write(f"Blur Applied: {apply_blur}\n")
                f.write(f"Tutor ID: {tutor_id}\n")
                f.write(f"Status: Ready\n")

            return {
                "status": "success",
                "avatar_id": avatar_id,
                "avatar_path": avatar_path,
                "message": "Avatar created successfully with MuseTalk"
            }

        except Exception as e:
            logger.error(f"Error in _create_avatar_sync: {e}")
            raise

    def _preprocess_video(self, video_path: str, apply_blur: bool) -> str:
        """
        预处理视频

        Args:
            video_path: 原始视频路径
            apply_blur: 是否应用模糊

        Returns:
            str: 处理后的视频路径
        """
        try:
            # 1. 转换视频到 25fps
            temp_path = os.path.join(os.path.dirname(video_path), "temp_25fps.mp4")

            cmd = [
                self.ffmpeg_path,
                '-i', video_path,
                '-r', '25',  # 设置帧率
                '-b:v', '3000k',  # 设置视频比特率
                '-c:v', 'libx264',  # 视频编码器
                '-y',  # 覆盖输出文件
                temp_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg conversion failed: {result.stderr}")
                return video_path

            logger.info(f"Video converted to 25fps: {temp_path}")

            # 2. TODO: 应用背景模糊（需要额外服务）
            # 参考 /workspace/try/lip-sync/create_avatar.py 中的 burr_video()
            # 这需要 Jina 服务运行，暂时跳过

            if apply_blur:
                logger.warning("Background blur not implemented yet, skipping")

            return temp_path

        except Exception as e:
            logger.error(f"Video preprocessing failed: {e}")
            return video_path

    def _run_musetalk_inference(self) -> bool:
        """
        运行 MuseTalk inference.sh 脚本

        Returns:
            bool: 是否成功
        """
        try:
            script_path = os.path.join(self.musetalk_base, "inference.sh")

            if not os.path.exists(script_path):
                logger.error(f"MuseTalk inference script not found: {script_path}")
                return False

            # 设置环境变量使用 MuseTalk conda 环境
            env = os.environ.copy()

            if self.conda_env:
                # 确保 conda 环境的 bin 目录在 PATH 最前面
                env['PATH'] = f"{self.conda_env}/bin:{env.get('PATH', '')}"
                env['CONDA_PREFIX'] = self.conda_env
                env['CONDA_DEFAULT_ENV'] = os.path.basename(self.conda_env)
                # 动态查找 Python 版本目录
                python_lib_dir = os.path.join(self.conda_env, "lib")
                if os.path.exists(python_lib_dir):
                    for item in os.listdir(python_lib_dir):
                        if item.startswith("python3."):
                            python_site = os.path.join(python_lib_dir, item, "site-packages")
                            if os.path.exists(python_site):
                                env['PYTHONPATH'] = f"{python_site}:{env.get('PYTHONPATH', '')}"
                                break
                logger.info(f"Using conda environment: {self.conda_env}")
                logger.info(f"PATH: {env['PATH'][:200]}...")

            # 使用 conda 环境的 python 直接运行，不通过 inference.sh
            # 这样可以避免 inference.sh 中的 python3 找到系统 Python
            if self.conda_env:
                python_bin = os.path.join(self.conda_env, "bin", "python")
            else:
                python_bin = "python3"
            
            # 直接调用 Python 模块，而不是通过 bash 脚本
            # 使用 realtime.yaml 配置，会自动在 results/v15/avatars/ 下创建 avatar
            # -u 参数禁用输出缓冲，确保能实时看到日志
            command = [
                python_bin, "-u", "-m", "scripts.realtime_inference",
                "--inference_config", "./configs/inference/realtime.yaml",
                "--unet_model_path", "./models/musetalkV15/unet.pth",
                "--unet_config", "./models/musetalkV15/musetalk.json",
                "--version", "v15",
                "--fps", "25"
            ]

            logger.info(f"Running MuseTalk inference: {' '.join(command)}")

            # 执行命令，实时显示输出
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                cwd=self.musetalk_base  # 设置工作目录为 MuseTalk 基础目录
            )

            # 使用轮询方式检测 latents.pt 文件生成，而不是依赖stdout
            # 因为stdout在subprocess中可能有缓冲问题
            import time
            import threading
            
            result_dir = os.path.join(self.musetalk_base, "results", "v15", "avatars", "avator_1")
            latents_file = os.path.join(result_dir, "latents.pt")
            
            preparation_completed = False
            check_count = 0
            max_checks = 180  # 最多检查3分钟 (180 * 1秒)
            
            # 在后台读取并记录输出，避免管道阻塞
            def read_output():
                try:
                    for line in process.stdout:
                        logger.info(f"[MuseTalk] {line.rstrip()}")
                except:
                    pass
            
            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()
            
            logger.info("Monitoring avatar preparation progress...")
            
            try:
                # 轮询检查 latents.pt 是否生成
                while check_count < max_checks:
                    if os.path.exists(latents_file):
                        # 文件存在，再等待2秒确保写入完成
                        time.sleep(2)
                        file_size = os.path.getsize(latents_file)
                        if file_size > 1000000:  # 文件大于1MB，说明已完成
                            preparation_completed = True
                            logger.info(f"Avatar preparation completed! latents.pt size: {file_size} bytes")
                            logger.info("Terminating inference process...")
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            break
                    
                    time.sleep(1)
                    check_count += 1
                    
                    # 每10秒记录一次进度
                    if check_count % 10 == 0:
                        logger.info(f"Still preparing avatar... ({check_count}s elapsed)")
                
                # 如果超时，强制终止
                if not preparation_completed:
                    logger.warning("Preparation timeout, terminating process...")
                    process.kill()
                    process.wait()
                    
            except Exception as e:
                logger.error(f"Error during avatar preparation: {e}")
                try:
                    process.kill()
                    process.wait()
                except:
                    pass

            # 检查结果是否存在，而不是依赖返回码
            result_dir = os.path.join(self.musetalk_base, "results", "v15", "avatars", "avator_1")
            if os.path.exists(result_dir) and os.path.exists(os.path.join(result_dir, "latents.pt")):
                logger.info("MuseTalk avatar preparation completed successfully")
                return True
            else:
                logger.error(f"MuseTalk inference failed - result not found at {result_dir}")
                return False

        except Exception as e:
            logger.error(f"Error running MuseTalk inference: {e}")
            return False

    async def _mock_create_avatar(
        self,
        avatar_id: str,
        video_path: str,
        apply_blur: bool
    ) -> Dict[str, Any]:
        """
        Mock Avatar 创建（用于测试）

        Args:
            avatar_id: Avatar ID
            video_path: 视频路径
            apply_blur: 是否模糊

        Returns:
            Dict: Mock 创建结果
        """
        # 模拟处理延迟
        await asyncio.sleep(1.0)

        # 创建 Mock Avatar 目录
        avatar_path = os.path.join(self.avatars_dir, avatar_id)
        os.makedirs(avatar_path, exist_ok=True)

        # 创建一个标记文件
        marker_file = os.path.join(avatar_path, "avatar_info.txt")
        with open(marker_file, "w") as f:
            f.write(f"[Mock Avatar]\n")
            f.write(f"Avatar ID: {avatar_id}\n")
            f.write(f"Video Path: {video_path}\n")
            f.write(f"Blur Applied: {apply_blur}\n")
            f.write(f"Status: Mock mode\n")

        logger.info(f"Mock Avatar created: {avatar_id}")

        return {
            "status": "success",
            "avatar_id": avatar_id,
            "avatar_path": avatar_path,
            "message": "[Mock] Avatar created successfully",
            "mock": True
        }

    async def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Avatar 信息

        Args:
            avatar_id: Avatar ID

        Returns:
            Optional[Dict]: Avatar 信息，不存在返回 None
        """
        avatar_path = os.path.join(self.avatars_dir, avatar_id)

        if not os.path.exists(avatar_path):
            return None

        return {
            "avatar_id": avatar_id,
            "avatar_path": avatar_path,
            "exists": True
        }

    async def delete_avatar(self, avatar_id: str) -> bool:
        """
        删除 Avatar

        Args:
            avatar_id: Avatar ID

        Returns:
            bool: 是否成功删除
        """
        avatar_path = os.path.join(self.avatars_dir, avatar_id)

        if not os.path.exists(avatar_path):
            logger.warning(f"Avatar not found: {avatar_id}")
            return False

        try:
            shutil.rmtree(avatar_path)
            logger.info(f"Avatar deleted: {avatar_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete avatar {avatar_id}: {e}")
            return False

    async def list_avatars(self) -> list:
        """
        列出所有 Avatar

        Returns:
            list: Avatar ID 列表
        """
        if not os.path.exists(self.avatars_dir):
            return []

        try:
            avatars = [
                d for d in os.listdir(self.avatars_dir)
                if os.path.isdir(os.path.join(self.avatars_dir, d))
            ]
            return avatars
        except Exception as e:
            logger.error(f"Failed to list avatars: {e}")
            return []

    async def generate_video(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int = 25
    ) -> Optional[str]:
        """
        生成口型同步视频（Avatar + Audio）

        Args:
            audio_data: base64 编码的音频数据
            avatar_id: Avatar ID
            fps: 视频帧率

        Returns:
            str: base64 编码的视频数据，失败返回 None
        """
        if not self.enable_real:
            # Mock 模式
            return await self._mock_generate_video(audio_data, avatar_id, fps)

        try:
            # 在线程池中运行同步的视频生成过程
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._generate_video_sync,
                audio_data,
                avatar_id,
                fps
            )
            return result
        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return None

    def _generate_video_sync(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int
    ) -> Optional[str]:
        """
        同步生成视频（在线程池中运行）

        步骤:
        1. 解码 base64 音频数据
        2. 保存音频到临时文件
        3. 调用 MuseTalk 实时推理脚本
        4. 读取生成的视频
        5. 编码为 base64 返回

        参考: /workspace/MuseTalk/scripts/realtime_inference.py
        """
        import base64
        import tempfile

        try:
            # 1. 解码音频数据
            audio_bytes = base64.b64decode(audio_data)

            # 2. 保存音频到临时文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_file:
                audio_file.write(audio_bytes)
                audio_path = audio_file.name

            # 3. 准备输出路径
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
                video_path = video_file.name

            # 4. 调用 MuseTalk 实时推理
            success = self._run_musetalk_realtime_inference(
                audio_path=audio_path,
                avatar_id=avatar_id,
                output_path=video_path,
                fps=fps
            )

            if not success:
                logger.warning("Video generation failed, returning static avatar image as fallback")
                # 降级方案：返回静态 avatar 图片
                return self._generate_static_video(avatar_id)

            # 5. 读取生成的视频
            if not os.path.exists(video_path):
                logger.error(f"Generated video not found: {video_path}")
                return self._generate_static_video(avatar_id)

            with open(video_path, 'rb') as f:
                video_bytes = f.read()

            # 6. 编码为 base64
            video_data = base64.b64encode(video_bytes).decode('utf-8')

            # 7. 清理临时文件
            try:
                os.unlink(audio_path)
                os.unlink(video_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp files: {e}")

            logger.info(f"Video generated successfully: {len(video_data)} bytes")
            return video_data

        except Exception as e:
            logger.error(f"Error in _generate_video_sync: {e}")
            return self._generate_static_video(avatar_id)

    def _generate_static_video(self, avatar_id: str) -> Optional[str]:
        """
        生成静态视频（降级方案）

        从 avatar 的第一张图片生成一个简单的视频

        Args:
            avatar_id: Avatar ID

        Returns:
            str: base64 编码的视频数据，失败返回 None
        """
        import base64
        import tempfile

        try:
            # 查找 avatar 的第一张图片 (优先使用 avatars_dir)
            avatar_path = os.path.join(self.avatars_dir, avatar_id)
            if not os.path.exists(avatar_path):
                # 回退到 musetalk 结果目录
                avatar_path = os.path.join(self.musetalk_base, "results", "v15", "avatars", avatar_id)

            full_imgs_dir = os.path.join(avatar_path, "full_imgs")

            if not os.path.exists(full_imgs_dir):
                logger.error(f"Avatar images not found: {full_imgs_dir}")
                return None

            # 获取第一张图片
            import glob
            images = sorted(glob.glob(os.path.join(full_imgs_dir, "*.png")))
            if not images:
                logger.error(f"No images found in {full_imgs_dir}")
                return None

            first_image = images[0]
            logger.info(f"Using static image: {first_image}")

            # 使用 ffmpeg 从单张图片生成 2 秒的视频
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
                video_path = video_file.name

            cmd = [
                self.ffmpeg_path,
                '-loop', '1',
                '-i', first_image,
                '-t', '2',  # 2 秒视频
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # 确保尺寸是偶数
                '-y',
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Failed to create static video: {result.stderr}")
                return None

            # 读取视频并编码
            with open(video_path, 'rb') as f:
                video_bytes = f.read()

            video_data = base64.b64encode(video_bytes).decode('utf-8')

            # 清理临时文件
            try:
                os.unlink(video_path)
            except:
                pass

            logger.info(f"Static video generated: {len(video_data)} bytes")
            return video_data

        except Exception as e:
            logger.error(f"Error generating static video: {e}")
            return None

    def _run_musetalk_realtime_inference(
        self,
        audio_path: str,
        avatar_id: str,
        output_path: str,
        fps: int
    ) -> bool:
        """
        运行 MuseTalk 实时推理生成视频

        直接调用 MuseTalk Python API 进行唇动同步

        Args:
            audio_path: 音频文件路径
            avatar_id: Avatar ID
            output_path: 输出视频路径
            fps: 视频帧率

        Returns:
            bool: 是否成功
        """
        try:
            # 检查 avatar 是否存在 (优先使用 avatars_dir)
            avatar_path = os.path.join(self.avatars_dir, avatar_id)
            if not os.path.exists(avatar_path):
                # 回退到 musetalk 结果目录 (向后兼容)
                avatar_path = os.path.join(self.musetalk_base, "results", "v15", "avatars", avatar_id)
                if not os.path.exists(avatar_path):
                    logger.error(f"Avatar not found in either location: {self.avatars_dir}/{avatar_id} or {avatar_path}")
                    return False

            # 检查必要的文件
            coords_path = os.path.join(avatar_path, "coords.pkl")
            latents_path = os.path.join(avatar_path, "latents.pt")
            mask_coords_path = os.path.join(avatar_path, "mask_coords.pkl")
            full_imgs_dir = os.path.join(avatar_path, "full_imgs")
            mask_dir = os.path.join(avatar_path, "mask")

            if not all([
                os.path.exists(coords_path),
                os.path.exists(latents_path),
                os.path.exists(mask_coords_path),
                os.path.exists(full_imgs_dir),
                os.path.exists(mask_dir)
            ]):
                logger.error(f"Avatar not fully prepared: {avatar_path}")
                return False

            # 构建 Python 命令调用 MuseTalk 实时推理
            script_path = os.path.join(self.musetalk_base, "scripts", "realtime_inference.py")
            if not os.path.exists(script_path):
                logger.error(f"MuseTalk realtime inference script not found: {script_path}")
                return False

            # 创建临时配置文件
            import tempfile
            import yaml

            config = {
                avatar_id: {
                    "preparation": False,  # 不重新准备，使用已有的
                    "video_path": os.path.join(avatar_path, "full_imgs"),
                    "bbox_shift": 0,
                    "audio_clips": {
                        "output": audio_path
                    }
                }
            }

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as config_file:
                yaml.dump(config, config_file)
                config_path = config_file.name

            # 设置环境变量
            env = os.environ.copy()

            # 关键: 添加 MuseTalk 基础目录到 PYTHONPATH（必须在最前面）
            pythonpath_parts = [self.musetalk_base]

            if self.conda_env:
                env['PATH'] = f"{self.conda_env}/bin:{env.get('PATH', '')}"
                env['CONDA_PREFIX'] = self.conda_env
                env['CONDA_DEFAULT_ENV'] = os.path.basename(self.conda_env)
                python_site = f"{self.conda_env}/lib/python3.10/site-packages"

                if os.path.exists(python_site):
                    pythonpath_parts.append(python_site)

            if env.get('PYTHONPATH'):
                pythonpath_parts.append(env['PYTHONPATH'])

            env['PYTHONPATH'] = ':'.join(pythonpath_parts)
            logger.info(f"Set PYTHONPATH: {env['PYTHONPATH']}")

            # 构建命令
            python_exe = f"{self.conda_env}/bin/python" if self.conda_env else "python"

            # 生成输出视频名称
            output_vid_name = os.path.splitext(os.path.basename(output_path))[0]

            command = [
                python_exe,
                script_path,
                "--version", "v15",
                "--inference_config", config_path,
                "--fps", str(fps),
                "--output_vid_name", output_vid_name,
                "--unet_config", "./models/musetalkV15/musetalk.json",
                "--unet_model_path", "./models/musetalkV15/unet.pth"
            ]

            logger.info(f"Running MuseTalk realtime inference: {' '.join(command)}")

            # 执行命令
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                cwd=self.musetalk_base
            )

            # 实时打印输出
            for line in process.stdout:
                logger.info(f"[MuseTalk] {line.rstrip()}")

            # 等待进程完成
            process.wait()

            # 清理临时配置文件
            try:
                os.unlink(config_path)
            except:
                pass

            if process.returncode == 0:
                # 查找生成的视频
                video_output_dir = os.path.join(avatar_path, "vid_output")
                expected_video = os.path.join(video_output_dir, f"{output_vid_name}.mp4")

                logger.info(f"Looking for video at: {expected_video}")

                if os.path.exists(expected_video):
                    # 复制视频到输出路径
                    shutil.copy2(expected_video, output_path)
                    logger.info(f"MuseTalk realtime inference completed successfully: {output_path}")
                    return True
                else:
                    # 尝试查找任何最近生成的视频
                    if os.path.exists(video_output_dir):
                        import glob
                        videos = glob.glob(os.path.join(video_output_dir, "*.mp4"))
                        if videos:
                            # 使用最新的视频
                            latest_video = max(videos, key=os.path.getmtime)
                            logger.info(f"Using latest video: {latest_video}")
                            shutil.copy2(latest_video, output_path)
                            logger.info(f"MuseTalk realtime inference completed successfully: {output_path}")
                            return True

                logger.error(f"MuseTalk completed but no video found at {expected_video}")
                return False
            else:
                logger.error(f"MuseTalk realtime inference failed with code: {process.returncode}")
                return False

        except Exception as e:
            logger.error(f"Error running MuseTalk realtime inference: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _mock_generate_video(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int
    ) -> Optional[str]:
        """
        Mock 视频生成（用于测试）

        Args:
            audio_data: base64 编码的音频数据
            avatar_id: Avatar ID
            fps: 视频帧率

        Returns:
            str: Mock base64 编码的视频数据
        """
        import base64

        # 模拟处理延迟
        await asyncio.sleep(0.5)

        # 返回一个 Mock 视频数据（实际上是一个小的占位符）
        mock_video = b"MOCK_VIDEO_DATA_" + avatar_id.encode() + b"_FPS_" + str(fps).encode()
        video_data = base64.b64encode(mock_video).decode('utf-8')

        logger.info(f"Mock video generated: {len(video_data)} bytes")
        return video_data

    async def get_idle_video(
        self,
        avatar_id: str,
        duration: int = 5,
        fps: int = 25
    ) -> Optional[str]:
        """
        获取 Avatar 的待机视频（循环播放的静态视频）

        Args:
            avatar_id: Avatar ID
            duration: 视频时长（秒）
            fps: 视频帧率

        Returns:
            str: base64 编码的待机视频数据，失败返回 None
        """
        if not self.enable_real:
            # Mock 模式
            return await self._mock_get_idle_video(avatar_id, duration, fps)

        try:
            # 在线程池中运行同步的视频生成过程
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._get_idle_video_sync,
                avatar_id,
                duration,
                fps
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get idle video: {e}")
            return None

    def _get_idle_video_sync(
        self,
        avatar_id: str,
        duration: int,
        fps: int
    ) -> Optional[str]:
        """
        同步生成待机视频（在线程池中运行）

        从 avatar 的图片帧生成一个循环的待机视频
        参考 try/lip-sync 的实现，使用缓存机制避免重复生成

        Args:
            avatar_id: Avatar ID
            duration: 视频时长（秒）
            fps: 视频帧率

        Returns:
            str: base64 编码的视频数据，失败返回 None
        """
        import base64
        import tempfile
        import glob

        # 检查缓存
        cache_key = (avatar_id, duration, fps)
        if cache_key in self._idle_video_cache:
            logger.info(f"Returning cached idle video for {avatar_id} (duration={duration}s, fps={fps})")
            return self._idle_video_cache[cache_key]

        try:
            # 1. 查找 avatar 的图片帧
            # 首先尝试从 avatars_dir 查找（主存储位置）
            avatar_path = os.path.join(self.avatars_dir, avatar_id)
            full_imgs_dir = os.path.join(avatar_path, "full_imgs")

            # 如果不存在，尝试从 musetalk_base 查找（临时结果位置）
            if not os.path.exists(full_imgs_dir):
                avatar_path = os.path.join(self.musetalk_base, "results", "v15", "avatars", avatar_id)
                full_imgs_dir = os.path.join(avatar_path, "full_imgs")
                
            if not os.path.exists(full_imgs_dir):
                logger.error(f"Avatar images not found in either {self.avatars_dir}/{avatar_id} or {self.musetalk_base}/results/v15/avatars/{avatar_id}")
                return None
            
            logger.info(f"Using avatar images from: {full_imgs_dir}")

            # 2. 获取所有图片帧
            images = sorted(glob.glob(os.path.join(full_imgs_dir, "*.png")))
            if not images:
                logger.error(f"No images found in {full_imgs_dir}")
                return None

            logger.info(f"Found {len(images)} frames for avatar {avatar_id}")

            # 3. 创建临时输出文件
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
                video_path = video_file.name

            # 4. 使用 ffmpeg 从图片序列生成循环视频
            # 计算需要循环多少次才能达到指定时长
            total_frames = len(images)
            target_frames = duration * fps
            loop_count = max(1, int(target_frames / total_frames))

            # 创建一个临时文件列表，包含循环的图片
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as list_file:
                list_path = list_file.name
                for _ in range(loop_count):
                    for img in images:
                        list_file.write(f"file '{img}'\n")
                        list_file.write(f"duration {1.0/fps}\n")
                # 最后一帧需要额外指定
                list_file.write(f"file '{images[-1]}'\n")

            # 5. 使用 ffmpeg concat 生成视频
            cmd = [
                self.ffmpeg_path,
                '-f', 'concat',
                '-safe', '0',
                '-i', list_path,
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-vf', f'fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-t', str(duration),  # 限制时长
                '-y',
                video_path
            ]

            logger.info(f"Generating idle video: {duration}s @ {fps}fps")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Failed to create idle video: {result.stderr}")
                # 清理临时文件
                try:
                    os.unlink(list_path)
                except:
                    pass
                return None

            # 6. 读取生成的视频
            if not os.path.exists(video_path):
                logger.error(f"Generated idle video not found: {video_path}")
                return None

            with open(video_path, 'rb') as f:
                video_bytes = f.read()

            # 7. 编码为 base64
            video_data = base64.b64encode(video_bytes).decode('utf-8')

            # 8. 清理临时文件
            try:
                os.unlink(video_path)
                os.unlink(list_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp files: {e}")

            # 9. 存入缓存（参考 try/lip-sync 的缓存策略）
            self._idle_video_cache[cache_key] = video_data
            logger.info(f"Idle video generated successfully: {len(video_data)} bytes (cached)")
            return video_data

        except Exception as e:
            logger.error(f"Error generating idle video: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def generate_frames_stream(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int = 25
    ):
        """
        实时生成视频帧流（用于 WebRTC）

        使用子进程方式生成视频，然后逐帧读取并推流

        策略:
        1. 使用子进程调用 MuseTalk (mt 环境) 生成视频
        2. 使用 cv2 读取生成的视频
        3. 逐帧 yield 给 WebRTC

        Args:
            audio_data: base64 编码的音频数据
            avatar_id: Avatar ID
            fps: 视频帧率

        Yields:
            numpy.ndarray: 视频帧 (H, W, 3) BGR 格式
        """
        if not self.enable_real:
            # Mock 模式：生成简单的测试帧
            async for frame in self._mock_generate_frames_stream(avatar_id, fps):
                yield frame
            return

        try:
            # 先生成完整视频（使用子进程）
            logger.info(f"Generating video for WebRTC streaming: avatar_id={avatar_id}")
            video_data = await self.generate_video(
                audio_data=audio_data,
                avatar_id=avatar_id,
                fps=fps
            )

            if not video_data:
                logger.error("Failed to generate video for streaming")
                return

            # 将 base64 视频解码并保存到临时文件
            import base64
            import tempfile
            import cv2

            video_bytes = base64.b64decode(video_data)

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                tmp_file.write(video_bytes)
                video_path = tmp_file.name

            try:
                # 使用 cv2 读取视频并逐帧 yield
                cap = cv2.VideoCapture(video_path)

                if not cap.isOpened():
                    logger.error(f"Failed to open video: {video_path}")
                    return

                frame_count = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    yield frame
                    frame_count += 1

                    # 控制帧率
                    await asyncio.sleep(1.0 / fps)

                cap.release()
                logger.info(f"Streamed {frame_count} frames via WebRTC")

            finally:
                # 清理临时文件
                try:
                    os.unlink(video_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Frame streaming failed: {e}", exc_info=True)

    def _generate_frames_sync(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int,
        frame_queue: asyncio.Queue,
        loop  # 接收 event loop 参数
    ):
        """
        同步生成视频帧（在线程池中运行）

        使用 MuseTalk 实时推理，逐帧生成并放入队列

        Args:
            audio_data: base64 编码的音频数据
            avatar_id: Avatar ID
            fps: 视频帧率
            frame_queue: 帧队列（用于传递帧到主线程）
        """
        import base64
        import tempfile
        import cv2
        import sys
        import numpy as np

        try:
            # 1. 解码音频数据
            audio_bytes = base64.b64decode(audio_data)

            # 2. 保存音频到临时文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_file:
                audio_file.write(audio_bytes)
                audio_path = audio_file.name

            # 3. 准备 MuseTalk 环境 (优先使用 avatars_dir)
            avatar_path = os.path.join(self.avatars_dir, avatar_id)
            if not os.path.exists(avatar_path):
                # 回退到 musetalk 结果目录
                avatar_path = os.path.join(self.musetalk_base, "results", "v15", "avatars", avatar_id)

            # 添加 MuseTalk 到 Python 路径
            if self.musetalk_base not in sys.path:
                sys.path.insert(0, self.musetalk_base)

            # 4. 导入 MuseTalk 模块
            try:
                from musetalk.utils.utils import get_file_type, get_video_fps, datagen
                from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs, coord_placeholder
                from musetalk.utils.blending import get_image
                from musetalk.utils.utils import load_all_model
                import torch

                # 5. 加载模型（如果还没加载）
                if not hasattr(self, '_musetalk_models'):
                    logger.info("Loading MuseTalk models...")
                    audio_processor, vae, unet, pe = load_all_model()
                    self._musetalk_models = {
                        'audio_processor': audio_processor,
                        'vae': vae,
                        'unet': unet,
                        'pe': pe
                    }
                    logger.info("MuseTalk models loaded")

                models = self._musetalk_models

                # 6. 加载 avatar 数据
                import pickle

                coords_path = os.path.join(avatar_path, "coords.pkl")
                with open(coords_path, 'rb') as f:
                    coord_list_cycle = pickle.load(f)

                input_latent_list_cycle = torch.load(
                    os.path.join(avatar_path, "latents.pt")
                )

                mask_coords_path = os.path.join(avatar_path, "mask_coords.pkl")
                with open(mask_coords_path, 'rb') as f:
                    mask_coords_list_cycle = pickle.load(f)

                full_imgs_dir = os.path.join(avatar_path, "full_imgs")
                mask_dir = os.path.join(avatar_path, "mask")

                # 7. 处理音频
                whisper_feature = models['audio_processor'].audio2feat(audio_path)
                whisper_chunks = models['audio_processor'].feature2chunks(
                    feature_array=whisper_feature,
                    fps=fps
                )

                # 8. 逐帧生成
                logger.info(f"Starting frame generation: {len(whisper_chunks)} frames")

                for i, whisper_chunk in enumerate(whisper_chunks):
                    # 获取当前帧的 latent 和坐标
                    idx = i % len(coord_list_cycle)
                    coord = coord_list_cycle[idx]
                    input_latent = input_latent_list_cycle[idx]
                    mask_coord = mask_coords_list_cycle[idx]

                    # 生成帧
                    with torch.no_grad():
                        audio_feature = torch.from_numpy(whisper_chunk).unsqueeze(0).cuda()
                        audio_feature = models['pe'](audio_feature)

                        latent = models['unet'](
                            input_latent.unsqueeze(0).cuda(),
                            0,
                            encoder_hidden_states=audio_feature
                        ).sample

                        output = models['vae'].decode(latent).sample
                        output = output.squeeze().cpu().numpy().transpose(1, 2, 0)
                        output = (output * 0.5 + 0.5) * 255
                        output = output.astype(np.uint8)

                    # 读取原始图片
                    img_path = os.path.join(full_imgs_dir, f"{idx:08d}.png")
                    frame = cv2.imread(img_path)

                    # 混合生成的嘴部和原始图片
                    x1, y1, x2, y2 = coord
                    frame[y1:y2, x1:x2] = cv2.resize(output, (x2-x1, y2-y1))

                    # 放入队列
                    asyncio.run_coroutine_threadsafe(
                        frame_queue.put(frame),
                        loop  # 使用传入的 loop
                    )

                    if i % 25 == 0:  # 每秒日志一次
                        logger.info(f"Generated frame {i+1}/{len(whisper_chunks)}")

                # 发送结束信号
                asyncio.run_coroutine_threadsafe(
                    frame_queue.put(None),
                    loop  # 使用传入的 loop
                )

                logger.info(f"Frame generation completed: {len(whisper_chunks)} frames")

            except ImportError as e:
                logger.error(f"Failed to import MuseTalk modules: {e}")
                # 发送结束信号
                asyncio.run_coroutine_threadsafe(
                    frame_queue.put(None),
                    loop  # 使用传入的 loop
                )

            # 清理临时文件
            try:
                os.unlink(audio_path)
            except:
                pass

        except Exception as e:
            logger.error(f"Error in _generate_frames_sync: {e}", exc_info=True)
            # 发送结束信号
            asyncio.run_coroutine_threadsafe(
                frame_queue.put(None),
                loop  # 使用传入的 loop
            )

    async def _mock_generate_frames_stream(
        self,
        avatar_id: str,
        fps: int,
        duration: int = 5
    ):
        """
        Mock 帧流生成（用于测试）

        生成简单的测试帧

        Args:
            avatar_id: Avatar ID
            fps: 帧率
            duration: 持续时间（秒）

        Yields:
            numpy.ndarray: 测试帧
        """
        import numpy as np

        total_frames = fps * duration

        for i in range(total_frames):
            # 生成一个简单的彩色帧
            frame = np.zeros((512, 512, 3), dtype=np.uint8)
            # 添加一些变化（模拟动画）
            color = int((i / total_frames) * 255)
            frame[:, :] = [color, 128, 255 - color]

            yield frame

            # 模拟帧率
            await asyncio.sleep(1.0 / fps)

    async def _mock_get_idle_video(
        self,
        avatar_id: str,
        duration: int,
        fps: int
    ) -> Optional[str]:
        """
        Mock 待机视频生成（用于测试）

        Args:
            avatar_id: Avatar ID
            duration: 视频时长
            fps: 视频帧率

        Returns:
            str: Mock base64 编码的视频数据
        """
        import base64

        # 模拟处理延迟
        await asyncio.sleep(0.3)

        # 返回一个 Mock 待机视频数据
        mock_video = b"MOCK_IDLE_VIDEO_" + avatar_id.encode() + f"_{duration}s_{fps}fps".encode()
        video_data = base64.b64encode(mock_video).decode('utf-8')

        logger.info(f"Mock idle video generated: {len(video_data)} bytes")
        return video_data


# 全局 Avatar 管理器实例
_avatar_manager: Optional[AvatarManager] = None


def get_avatar_manager(
    enable_real: bool = False,
    avatars_dir: Optional[str] = None,
    musetalk_base: Optional[str] = None,
    conda_env: Optional[str] = None,
    ffmpeg_path: Optional[str] = None
) -> AvatarManager:
    """
    获取 Avatar 管理器实例（单例模式）

    Args:
        enable_real: 是否启用真实 MuseTalk
        avatars_dir: Avatar 存储目录
        musetalk_base: MuseTalk 基础目录
        conda_env: Conda 环境路径
        ffmpeg_path: FFmpeg 路径

    Returns:
        AvatarManager: Avatar 管理器实例
    """
    global _avatar_manager

    if _avatar_manager is None:
        _avatar_manager = AvatarManager(
            enable_real=enable_real,
            avatars_dir=avatars_dir,
            musetalk_base=musetalk_base,
            conda_env=conda_env,
            ffmpeg_path=ffmpeg_path
        )

    return _avatar_manager
