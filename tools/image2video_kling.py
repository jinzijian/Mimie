import os
import sys
from pathlib import Path
from datetime import datetime
import time
from typing import Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

try:
    from tools.base_tool import Tool
    from tools.supabase_image_uploader import upload_image_to_public_url
except ModuleNotFoundError:
    # Allow running this file directly: add repo root to sys.path
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    from tools.base_tool import Tool
    from tools.supabase_image_uploader import upload_image_to_public_url

# Load environment variables
load_dotenv()

# Kling API configuration
KLING_API_URL = "https://api.acedata.cloud/kling/videos"
DEFAULT_MODEL = "kling-v1-6"

# Timeout configurations
CONNECT_TIMEOUT = 300 # seconds
READ_TIMEOUT = 300    # seconds
TOTAL_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


def _create_robust_session() -> requests.Session:
    """Create a session with retry logic and connection pooling"""
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        backoff_factor=1,
        raise_on_status=False
    )
    
    # Configure adapter with retry strategy
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def _build_kling_headers(api_key: Optional[str] = None) -> dict:
    """Build headers for Kling API requests"""
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }
    
    # Use provided API key or fall back to environment variables
    # Check multiple possible environment variable names
    token = (api_key or 
             os.getenv("KLING_API_KEY") or 
             os.getenv("ACEDATA_KLING_API_KEY") or 
             "6da7c9d71de048c696e6c3c57114e23b")
    
    if token:
        headers["authorization"] = f"Bearer {token}"
    
    return headers


def _convert_image_to_url(image_input: Union[str, Path]) -> str:
    """Convert image path to URL if needed"""
    image_str = str(image_input)
    
    # If already a URL, return as is
    if image_str.startswith(('http://', 'https://')):
        return image_str
    
    # If local path, upload to get URL
    image_path = Path(image_str)
    if not image_path.exists():
        raise ValueError(f"图片文件不存在: {image_str}")
    
    print(f"📤 正在上传图片: {image_str}")
    upload_result = upload_image_to_public_url(str(image_path))
    
    if not upload_result.get("ok"):
        error_msg = upload_result.get("error", "未知错误")
        raise ValueError(f"图片上传失败 {image_str}: {error_msg}")
    
    uploaded_url = upload_result.get("url")
    if not uploaded_url:
        raise ValueError(f"图片上传成功但未返回URL: {image_str}")
    
    print(f"✅ 图片上传成功: {uploaded_url}")
    return uploaded_url


def _extract_video_url_from_response(data: dict) -> Optional[str]:
    """Extract video URL from API response"""
    # Try common keys for video URL
    for key in ("video_url", "url", "download_url", "video"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    
    # Check nested data structures
    nested = data.get("data") or data.get("result") or {}
    if isinstance(nested, dict):
        for key in ("video_url", "url", "download_url", "video"):
            value = nested.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    elif isinstance(nested, list) and nested:
        for item in nested:
            if isinstance(item, dict):
                for key in ("video_url", "url", "download_url", "video"):
                    value = item.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value
    
    return None


def _extract_task_id_from_response(data: dict) -> Optional[str]:
    """Extract task ID from API response"""
    # Try common keys for task ID
    task_id = data.get("task_id") or data.get("id") or data.get("video_id")
    
    # Check nested structures
    nested = data.get("data") or data.get("result")
    if isinstance(nested, dict):
        task_id = task_id or nested.get("task_id") or nested.get("id") or nested.get("video_id")
    elif isinstance(nested, list) and nested:
        for item in nested:
            if isinstance(item, dict):
                task_id = task_id or item.get("task_id") or item.get("id") or item.get("video_id")
                if task_id:
                    break
    
    return task_id


def _poll_kling_task(
    task_id: str,
    headers: dict,
    session: Optional[requests.Session] = None,
    poll_interval: float = 5.0,
    poll_timeout: float = 600.0
) -> Optional[str]:
    """Poll Kling task until completion and return video URL"""
    start_time = time.time()
    status_url = f"{KLING_API_URL}/{task_id}"
    
    if session is None:
        session = _create_robust_session()
    
    print(f"⏳ 开始轮询任务: {task_id}")
    
    while True:
        if time.time() - start_time > poll_timeout:
            print(f"⌛ 轮询超时({int(poll_timeout)}s): 任务 {task_id} 未完成")
            return None
        
        try:
            response = session.get(status_url, headers=headers, timeout=TOTAL_TIMEOUT)
            
            if response.status_code == 404:
                print(f"⚠️ 任务不存在: {task_id}")
                return None
            
            if response.status_code >= 400:
                print(f"⚠️ 轮询失败: {response.status_code} {response.text}")
                time.sleep(poll_interval)
                continue
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            # Check if video is ready
            video_url = _extract_video_url_from_response(data)
            if video_url:
                print(f"✅ 视频生成完成: {video_url}")
                return video_url
            
            # Check status
            status = data.get("status") or data.get("state", "processing")
            print(f"⏳ 任务状态: {status}")
            
            # Check for completion or failure
            if status in ["completed", "success", "finished"]:
                video_url = _extract_video_url_from_response(data)
                if video_url:
                    return video_url
                else:
                    print("⚠️ 任务完成但未找到视频URL")
                    return None
            elif status in ["failed", "error", "cancelled"]:
                print(f"❌ 任务失败: {status}")
                return None
            
        except requests.exceptions.ConnectTimeout:
            print(f"⚠️ 连接超时，正在重试...")
        except requests.exceptions.ReadTimeout:
            print(f"⚠️ 读取超时，正在重试...")
        except requests.exceptions.Timeout as e:
            print(f"⚠️ 轮询超时: {e}")
        except Exception as e:
            print(f"⚠️ 轮询异常: {e}")
        
        time.sleep(poll_interval)


def generate_kling_image2video(
    prompt: str,
    start_image_url: str,
    mode: str = "pro",
    aspect_ratio: str = "9:16",
    duration: int = 5,
    model: str = DEFAULT_MODEL,
    output_filename: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 10.0,
) -> Optional[str]:
    """
    使用 Kling API 生成图生视频
    
    Args:
        prompt: 提示词，描述要生成的视频内容
        start_image_url: 起始图像URL或本地路径
        mode: 生成模式 ("pro" 或 "standard")
        aspect_ratio: 视频比例 ("9:16", "16:9", "1:1" 等)
        duration: 视频时长（秒）
        model: 使用的模型 (默认 "kling-v1-6")
        output_filename: 输出文件名
        api_key: API密钥
        max_retries: 最大重试次数
        retry_delay: 重试延迟
        
    Returns:
        保存的视频文件路径，失败返回 None
    """
    
    if not prompt:
        raise ValueError("prompt is required for Kling image2video")
    
    if not start_image_url:
        raise ValueError("start_image_url is required for Kling image2video")
    
    # Convert image path to URL if needed
    try:
        image_url = _convert_image_to_url(start_image_url)
    except ValueError as e:
        print(f"❌ 图片处理失败: {e}")
        return None
    
    # Generate output filename if not provided
    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"kling_image2video_{timestamp}.mp4"
    
    # Build request payload
    payload = {
        "action": "image2video",
        "model": model,
        "prompt": prompt,
        "start_image_url": image_url,
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
    }
    
    print(f"🎬 Kling图生视频请求:")
    print(f"   - prompt: {prompt}")
    print(f"   - start_image_url: {image_url}")
    print(f"   - model: {model}")
    print(f"   - mode: {mode}")
    print(f"   - aspect_ratio: {aspect_ratio}")
    print(f"   - duration: {duration}s")
    
    # Create robust session for all requests
    session = _create_robust_session()
    
    retry_count = 0
    while retry_count <= max_retries:
        try:
            headers = _build_kling_headers(api_key)
            
            if retry_count > 0:
                print(f"🔄 重试第 {retry_count}/{max_retries} 次...")
                time.sleep(retry_delay)
            
            # Make API request with shorter timeout to fail faster
            print(f"📡 发送请求到: {KLING_API_URL}")
            response = session.post(KLING_API_URL, json=payload, headers=headers, timeout=TOTAL_TIMEOUT)
            
            if response.status_code >= 400:
                print(f"❌ API 请求失败: {response.status_code} {response.text}")
                
                if response.status_code == 401:
                    print("➡️ 401 未授权: 请检查 KLING_API_KEY 是否正确")
                    return None
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    print(f"⏱️ 触发限流 429, 建议稍后重试. Retry-After={retry_after}")
                    if retry_count < max_retries:
                        wait_time = float(retry_after) if retry_after else retry_delay * 2
                        print(f"⏳ 等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        retry_count += 1
                        continue
                
                # For server errors, try to extract task_id and poll
                if response.status_code >= 500:
                    try:
                        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                        task_id = _extract_task_id_from_response(data)
                        if task_id:
                            print(f"🔁 继续轮询任务进度: task_id={task_id}")
                            video_url = _poll_kling_task(task_id, headers, session)
                            if video_url:
                                return _download_video(video_url, output_filename, session)
                    except Exception:
                        pass
                
                # Retry for server errors
                if response.status_code >= 500 and retry_count < max_retries:
                    retry_count += 1
                    continue
                
                return None
            
            # Success case
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            # Check for immediate video URL
            video_url = _extract_video_url_from_response(data)
            if video_url:
                return _download_video(video_url, output_filename, session)
            
            # Check for task ID to poll
            task_id = _extract_task_id_from_response(data)
            if task_id:
                print(f"⏳ 任务已创建: {task_id}，开始轮询...")
                video_url = _poll_kling_task(task_id, headers, session)
                if video_url:
                    return _download_video(video_url, output_filename, session)
                else:
                    return None
            
            # Fallback
            print("⚠️ API 响应中未找到可用的视频URL或任务ID")
            print("原始响应:", data)
            return None
            
        except requests.exceptions.ConnectTimeout:
            print(f"❌ 连接超时 (超过 {CONNECT_TIMEOUT}s)")
            if retry_count < max_retries:
                retry_count += 1
                continue
            return None
        except requests.exceptions.ReadTimeout:
            print(f"❌ 读取超时 (超过 {READ_TIMEOUT}s)")
            if retry_count < max_retries:
                retry_count += 1
                continue
            return None
        except requests.exceptions.Timeout as e:
            print(f"❌ 请求超时: {e}")
            if retry_count < max_retries:
                retry_count += 1
                continue
            return None
        except Exception as e:
            print(f"❌ 请求过程中出现错误: {e}")
            if retry_count < max_retries:
                retry_count += 1
                continue
            return None
    
    print(f"❌ 所有重试已用尽 ({max_retries} 次)")
    return None


def _download_video(video_url: str, output_filename: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """Download video from URL"""
    if session is None:
        session = _create_robust_session()
    
    try:
        print(f"📥 正在下载视频: {video_url}")
        # Use a longer timeout for downloading since videos can be large
        download_timeout = (CONNECT_TIMEOUT, 300)  # 5 minutes for reading
        
        with session.get(video_url, stream=True, timeout=download_timeout) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            if total_size > 0:
                print(f"📁 文件大小: {total_size / (1024*1024):.1f} MB")
            
            downloaded = 0
            with open(output_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Show progress for large files
                        if total_size > 0 and downloaded % (1024*1024) == 0:  # Every MB
                            progress = (downloaded / total_size) * 100
                            print(f"📥 下载进度: {progress:.1f}%")
                            
        print(f"✅ 视频已下载: {output_filename}")
        return output_filename
    except requests.exceptions.ConnectTimeout:
        print(f"❌ 下载连接超时 (超过 {CONNECT_TIMEOUT}s)")
        return None
    except requests.exceptions.ReadTimeout:
        print(f"❌ 下载读取超时 (超过 300s)")
        return None
    except requests.exceptions.Timeout as e:
        print(f"❌ 下载超时: {e}")
        return None
    except Exception as e:
        print(f"❌ 下载视频失败: {e}")
        return None


class KlingImage2VideoGenerator(Tool):
    name: str = "kling_image2video_generator"
    description: str = "Generate a video from an image and text prompt using Kling AI. Supports various aspect ratios, durations."
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A detailed prompt describing the video scene to generate.",
            },
            "start_image_url": {
                "type": "string",
                "description": "Starting image URL or local file path. Local files will be automatically uploaded.",
            },
            "mode": {
                "type": "string",
                "enum": ["pro", "standard"],
                "default": "pro",
                "description": "Generation mode. 'pro' for higher quality, 'standard' for faster processing.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["9:16", "16:9", "1:1"],
                "default": "9:16",
                "description": "Video aspect ratio.",
            },
            "duration": {
                "type": "integer",
                "minimum": 5,
                "maximum": 10,
                "default": 5,
                "description": "Video duration in seconds.",
            },
            "model": {
                "type": "string",
                "default": "kling-v1-6",
                "description": "Model to use for generation.",
            },
            "api_key": {
                "type": "string",
                "description": "Optional API key override; if unset, falls back to environment KLING_API_KEY.",
            },
        },
        "required": ["prompt", "start_image_url"],
    }

    def execute(
        self,
        prompt: str,
        start_image_url: str,
        mode: str = "pro",
        aspect_ratio: str = "9:16",
        duration: int = 10,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
    ) -> str:
        result = generate_kling_image2video(
            prompt=prompt,
            start_image_url=start_image_url,
            mode=mode,
            aspect_ratio=aspect_ratio,
            duration=duration,
            model=model,
            api_key=api_key,
        )
        
        if result:
            return f"✅ Kling Image2Video generated and saved at: {result}"
        return "❌ Failed to generate or download video using Kling."


if __name__ == "__main__":
    # Test the tool
    os.makedirs("temp_video_processing", exist_ok=True)
    
    print("== Kling API 环境检查 ==")
    api_key_names = ["KLING_API_KEY", "ACEDATA_KLING_API_KEY"]
    for key_name in api_key_names:
        key_value = os.getenv(key_name)
        print(f"{key_name}: {'set' if key_value else 'unset'}")
        if key_value:
            print(f"  {key_name} (前4位): {key_value[:4]}...")
    print(f"API URL: {KLING_API_URL}")
    print(f"Default Model: {DEFAULT_MODEL}")
    print(f"连接超时: {CONNECT_TIMEOUT}s")
    print(f"读取超时: {READ_TIMEOUT}s")
    
    # Test with the example from curl
    prompt = "a model wearing a clothe and showing off the clothe as an advertisement"
    image_url = "https://i.ibb.co/Fb8qc2X2/4c5ae35547e0.png"
    
    print("\n== 测试 Kling 图生视频 ==")
    result = generate_kling_image2video(
        prompt=prompt,
        start_image_url=image_url,
        mode="pro",
        aspect_ratio="9:16",
        duration=5,
        output_filename="temp_video_processing/test_kling_image2video.mp4",
    )
    print("Kling image2video 输出:", result)
