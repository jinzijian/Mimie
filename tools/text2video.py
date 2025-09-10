import os
import sys
from pathlib import Path
from datetime import datetime
import time
from urllib.parse import urlparse, urlunparse
from typing import List, Optional
from openai import OpenAI
import requests
import json
from dotenv import load_dotenv
try:
    from tools.base_tool import Tool
    from utils.project_organizer import ProjectOrganizer
except ModuleNotFoundError:
    # Allow running this file directly: add repo root to sys.path
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    from tools.base_tool import Tool
    from utils.project_organizer import ProjectOrganizer

# Load environment variables
load_dotenv()


# Allow overriding the API URL and model via environment variables
API_URL = os.getenv("ACEDATA_API_URL", "https://api.acedata.cloud/veo/videos")
DEFAULT_MODEL = os.getenv("ACEDATA_VIDEO_MODEL", "veo3")


def generate_prompt_for_video(script_path: str, user_requirements: str) -> str:
    """
    Generate a prompt for image2video based on the script and user requirements.
    """
    with open(script_path, "r") as f:
        script = f.read()
    prompt = f"""
You are a professional video storyboard generator. 
You will receive:
1. A full video script path (global outline).
2. A single scene requirement from that path (focus of this generation).

Your task is to generate a detailed storyboard in JSON format for the given scene only.
Use the global script path as context to ensure consistency of tone and style.

Each scene must include:
- "stage": short stage title
- "description": what happens in this scene
- "camera": {{"movement": "...", "framing": "..."}}
- "effects": ["...","..."]
- "sound_effects": ["...","..."]

Here is an example format:

[
  {{
    "stage": "Internal Journey",
    "description": "As the camera reaches the top of the Dyson vacuum, it dives inside to show airflow and mechanics.",
    "camera": {{
      "movement": "POV-style fast glide through internals",
      "framing": "dynamic sweeping angles inside machinery"
    }},
    "effects": [
      "floating dust particles",
      "blue airflow trails",
      "cyclone spinning animation"
    ],
    "sound_effects": [
      "whooshing air",
      "precision clicks",
      "futuristic hum"
    ]
  }}
]

Now generate the JSON storyboard for this scene:

Global Script:
{script}

Current Scene Requirement:
{user_requirements}
"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _build_headers(
    override_token: Optional[str] = None,
) -> dict:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }

    # Auth: only support Bearer with ACEDATA_API_KEY per requirement
    token = (override_token or "").strip() or os.getenv("ACEDATA_API_KEY")
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _extract_video_url(data: dict) -> Optional[str]:
    # Try common keys
    for key in ("video_url", "url", "download_url", "video"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    # Sometimes nested under data/result
    nested = data.get("data") or data.get("result") or {}
    # Case: data is a list of results
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                for key in ("video_url", "url", "download_url", "video"):
                    value = item.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value
    elif isinstance(nested, dict):
        for key in ("video_url", "url", "download_url", "video"):
            value = nested.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    return None


def _extract_task_id_and_status(data: dict) -> tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of task/video id and status from response payloads.

    The AceData Veo API commonly returns:
      { success, task_id, data: [{ id, video_url, created_at, complete_at, state }] }

    We try multiple places/keys for both id and status/state.
    """
    task_id = data.get("task_id") or data.get("video_id") or data.get("id")

    # Prefer explicit status keys
    status = data.get("status") or data.get("state")

    # Look into nested structures
    nested = data.get("data") or data.get("result")
    if isinstance(nested, dict):
        task_id = task_id or nested.get("task_id") or nested.get("video_id") or nested.get("id")
        status = status or nested.get("status") or nested.get("state")
    elif isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                task_id = task_id or item.get("task_id") or item.get("video_id") or item.get("id")
                status = status or item.get("status") or item.get("state")
                # Break early if both found
                if task_id and status:
                    break
    return (task_id, status)


def _extract_status_hints_from_headers(headers: dict) -> list[str]:
    hints: list[str] = []
    for k in (
        "Location",
        "location",
        "Content-Location",
        "content-location",
        "Operation-Location",
        "operation-location",
        "Task-Url",
        "task-url",
        "Status-Url",
        "status-url",
    ):
        v = headers.get(k)
        if isinstance(v, str) and v.startswith("http"):
            hints.append(v)
    return hints


def _candidate_status_urls(task_id: str, target_url: str, hints: list[str] | None = None) -> list[str]:
    parsed = urlparse(target_url)
    base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    candidates: list[str] = []
    # Use hints first if provided (e.g., status_url from API)
    if hints:
        for h in hints:
            if isinstance(h, str) and h.startswith("http"):
                candidates.append(h)
    # Common patterns
    # 1) Same path + /{id}
    candidates.append(target_url.rstrip("/") + "/" + task_id)
    # 2) /veo/videos/{id} (explicit)
    candidates.append(base + "/veo/videos/" + task_id)
    # 3) /veo/video/{id}
    candidates.append(base + "/veo/video/" + task_id)
    # 4) /veo/tasks/{id}
    candidates.append(base + "/veo/tasks/" + task_id)
    # 5) /veo/jobs/{id}
    candidates.append(base + "/veo/jobs/" + task_id)
    # 6) /tasks/{id}
    candidates.append(base + "/tasks/" + task_id)
    # 7) /jobs/{id}
    candidates.append(base + "/jobs/" + task_id)
    # 8) /veo/{id}
    candidates.append(base + "/veo/" + task_id)
    # 9) /videos/{id}
    candidates.append(base + "/videos/" + task_id)
    # 10) /veo/videos/status/{id}
    candidates.append(base + "/veo/videos/status/" + task_id)
    # 11) /veo/videos/" + task_id + "/status"
    candidates.append(base + "/veo/videos/" + task_id + "/status")
    # 12) query-param styles
    candidates.append(base + "/veo/videos?task_id=" + task_id)
    candidates.append(base + "/veo/videos/status?task_id=" + task_id)
    candidates.append(base + "/veo/tasks/status?task_id=" + task_id)
    candidates.append(base + "/veo/jobs/status?task_id=" + task_id)
    candidates.append(base + "/videos/status?task_id=" + task_id)
    candidates.append(base + "/tasks/status?task_id=" + task_id)
    # Deduplicate while preserving order
    seen = set()
    uniq: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _poll_for_completion(
    task_id: str,
    headers: dict,
    target_url: str,
    poll_interval_s: float,
    poll_timeout_s: float,
    hints: list[str] | None = None,
) -> Optional[str]:
    """Poll status endpoints until a downloadable video URL is available or timeout.

    Strategy: probe candidate endpoints until one responds with non-404, then stick to it.
    """
    start_ts = time.time()
    candidates = _candidate_status_urls(task_id, target_url, hints=hints)
    selected_endpoint: Optional[str] = None
    while True:
        if time.time() - start_ts > poll_timeout_s:
            print(f"⌛ 轮询超时({int(poll_timeout_s)}s): 任务 {task_id} 未完成")
            return None
        try:
            endpoints_to_try = [selected_endpoint] if selected_endpoint else candidates
            for ep in endpoints_to_try:
                if not ep:
                    continue
                r = requests.get(ep, headers=headers, timeout=60)
                if r.status_code == 404:
                    if not selected_endpoint:
                        # Try next candidate
                        continue
                    else:
                        # Selected endpoint broke; reset and try others next loop
                        selected_endpoint = None
                        print(f"⚠️  轮询失败(404): {ep}")
                        break
                if r.status_code >= 400:
                    print(f"⚠️  轮询失败: {r.status_code} {r.text}")
                    # Try next candidate if not selected
                    if not selected_endpoint:
                        continue
                    else:
                        break
                # OK
                payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                url = _extract_video_url(payload)
                if url:
                    return url
                tid, status = _extract_task_id_and_status(payload)
                if status:
                    print(f"⏳ 任务状态: {status} (task_id={tid or task_id})")
                # Found a working endpoint
                selected_endpoint = ep
                break
        except Exception as e:
            print(f"⚠️  轮询异常: {e}")
        time.sleep(poll_interval_s)


def generate_text2video(
    prompt: str,
    video_id: Optional[str] = None,
    output_filename: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    model: Optional[str] = None,
    callback_url: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 10.0,
    script_path: str = None,
    aspect_ratio: str = "9:16",
) -> Optional[str]:
    """
    使用 AceData Veo API 生成文生视频

    Args:
        prompt: 提示词，描述要生成的视频内容
        video_id: 可选，已有任务的视频 ID（用于续生成/引用）
        output_filename: 可选，保存文件名
        api_key: 可选，API密钥覆盖
        api_url: 可选，API URL覆盖
        model: 可选，模型覆盖
        callback_url: 可选，回调URL
        max_retries: 最大重试次数
        retry_delay: 重试延迟时间

    Returns:
        已保存的视频文件路径；如果失败则返回 None
    """

    if not prompt:
        raise ValueError("prompt is required for text2video")

    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = ProjectOrganizer.get_save_dir(ProjectOrganizer.SaveType.ASSETS) + f"text2video_{timestamp}.mp4"

    if script_path:
        try:
            prompt = generate_prompt_for_video(script_path, prompt)
            print(f"🎬 text2video prompt: {prompt}")
        except Exception as e:
            print(f"❌ 生成提示词失败: {e} and will use the original prompt")

    # Build payload
    payload: dict = {
        "action": "text2video",
        "model": model or DEFAULT_MODEL,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }
    
    if video_id:
        payload["video_id"] = video_id
    if callback_url:
        payload["callback_url"] = callback_url

    print(f"🎬 文生视频请求:")
    print(f"   - prompt: {prompt}")
    print(f"   - model: {model or DEFAULT_MODEL}")
    print(f"   - API URL: {api_url or os.getenv('ACEDATA_API_URL') or API_URL}")
    try:
        print("   - 请求体:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        pass

    retry_count = 0
    while retry_count <= max_retries:
        try:
            base_headers = _build_headers(override_token=api_key)
            target_url = (api_url or os.getenv("ACEDATA_API_URL") or API_URL).strip()

            def do_post(h: dict) -> requests.Response:
                return requests.post(target_url, json=payload, headers=h, timeout=300)

            if retry_count > 0:
                print(f"🔄 重试第 {retry_count}/{max_retries} 次...")
                time.sleep(retry_delay)
            
            resp = do_post(base_headers)
            if resp.status_code >= 400:
                print("❌ API 请求失败:", resp.status_code, resp.text)
                if resp.status_code == 401:
                    print(
                        "➡️  401 未授权排查建议: (1) 确认 ACEDATA_API_URL 是否正确:", target_url,
                        "(2) 确认令牌与接口匹配, 当前仅使用 Authorization: Bearer",
                        "(3) 重新生成或替换 ACEDATA_API_KEY",
                    )
                    return None
                
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    print(f"⏱️  触发限流 429, 建议稍后重试. Retry-After={retry_after}")
                    if retry_count < max_retries:
                        wait_time = float(retry_after) if retry_after else retry_delay * 2
                        print(f"⏳ 等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        retry_count += 1
                        continue
                
                if resp.status_code >= 500:
                    print("🛠️  服务器错误, 将尝试读取 task_id 并进入轮询 (若存在)")
                
                # Even on error, attempt to extract task id and poll if present
                data_err = {}
                try:
                    if resp.headers.get("content-type", "").startswith("application/json"):
                        data_err = resp.json()
                except Exception:
                    pass

                # Friendly error mapping
                err_obj = data_err.get("error") if isinstance(data_err, dict) else None
                if isinstance(err_obj, dict):
                    code = err_obj.get("code") or "unknown_error"
                    msg = err_obj.get("message") or ""
                    known = {
                        "token_mismatched": "请求参数或令牌不正确，请检查 authorization 与 payload。",
                        "api_not_implemented": "接口暂未实现或参数不支持，请核对 action/model。",
                        "invalid_token": "鉴权失败，authorization 令牌无效或缺失。",
                        "too_many_requests": "请求过于频繁，命中限流，请稍后再试。",
                        "api_error": "服务内部错误，请稍后重试或联系支持。",
                    }
                    hint = known.get(code)
                    if hint:
                        print(f"ℹ️  错误码映射: {code} - {hint}")
                    if msg:
                        print(f"📝 服务端消息: {msg}")
                
                # For api_error, directly return failure without polling
                if err_obj and err_obj.get("code") == "api_error":
                    print("❌ API 错误，生成失败")
                    return None
                
                # For server errors (5xx), try to extract task_id first
                task_id_err, _ = _extract_task_id_and_status(data_err)
                if task_id_err and resp.status_code >= 500:
                    print(f"🔁 继续轮询任务进度: task_id={task_id_err}")
                    poll_interval = float(os.getenv("ACEDATA_POLL_INTERVAL", "5"))
                    poll_timeout = float(os.getenv("ACEDATA_POLL_TIMEOUT", "600"))
                    hints = _extract_status_hints_from_headers(resp.headers) or []
                    for k in ("status_url", "task_url", "url"):
                        v = data_err.get(k)
                        if isinstance(v, str) and v.startswith("http"):
                            hints.append(v)
                    url = _poll_for_completion(task_id_err, base_headers, target_url, poll_interval, poll_timeout, hints=hints)
                    if url:
                        try:
                            with requests.get(url, stream=True, timeout=300) as r:
                                r.raise_for_status()
                                with open(output_filename, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                            print(f"✅ 视频已下载: {output_filename}")
                            return output_filename
                        except Exception as e:
                            print(f"❌ 下载视频失败: {e}")
                            return None
                
                # For retryable errors (5xx without task_id), retry
                if resp.status_code >= 500 and retry_count < max_retries:
                    print(f"🔄 服务器错误，准备重试 ({retry_count + 1}/{max_retries})")
                    retry_count += 1
                    continue
                
                return None

            # Success case
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            # If the API returns a direct downloadable URL
            video_url = _extract_video_url(data)
            if video_url:
                try:
                    with requests.get(video_url, stream=True, timeout=300) as r:
                        r.raise_for_status()
                        with open(output_filename, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    print(f"✅ 视频已下载: {output_filename}")
                    return output_filename
                except Exception as e:
                    print(f"❌ 下载视频失败: {e}")
                    return None

            # If only a task id is returned, poll until completion
            task_id, status = _extract_task_id_and_status(data)
            if task_id:
                print(f"⏳ 任务已创建，task_id: {task_id}，状态: {status or 'unknown'}。开始轮询…")
                poll_interval = float(os.getenv("ACEDATA_POLL_INTERVAL", "5"))
                poll_timeout = float(os.getenv("ACEDATA_POLL_TIMEOUT", "600"))
                hints = _extract_status_hints_from_headers(resp.headers) or []
                for k in ("status_url", "task_url", "url"):
                    v = data.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        hints.append(v)
                url = _poll_for_completion(task_id, base_headers, target_url, poll_interval, poll_timeout, hints=hints)
                if url:
                    try:
                        with requests.get(url, stream=True, timeout=300) as r:
                            r.raise_for_status()
                            with open(output_filename, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                        print(f"✅ 视频已下载: {output_filename}")
                        return output_filename
                    except Exception as e:
                        print(f"❌ 下载视频失败: {e}")
                        return None
                else:
                    return None

            # Fallback: no URL given
            print("⚠️ API 响应中未找到可下载的链接。原始响应: ", data)
            return None
            
        except Exception as e:
            print(f"❌ 请求过程中出现错误: {e}")
            if retry_count < max_retries:
                print(f"🔄 网络异常，准备重试 ({retry_count + 1}/{max_retries})")
                retry_count += 1
                continue
            return None
    
    # If all retries exhausted
    print(f"❌ 所有重试已用尽 ({max_retries} 次)")
    return None


class Text2VideoGenerator(Tool):
    name: str = "text2video_generator"
    description: str = "Generate a video from text prompt."
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A detailed prompt describing the video scene to generate.",
            },
            "script_path": {
                "type": "string",
                "description": "The path to the script generator's output.",
            },
            "video_id": {
                "type": "string",
                "description": "Optional existing video task id for reference.",
            },
            "callback_url": {
                "type": "string",
                "description": "Optional webhook URL to receive async completion payload.",
            },
            "api_key": {
                "type": "string",
                "description": "Optional API key override; if unset, falls back to environment.",
            },
            "api_url": {
                "type": "string",
                "description": "Optional API URL override; if unset, falls back to environment/default.",
            },
            "model": {
                "type": "string",
                "description": "Optional model override; if unset, falls back to environment/default.",
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Optional aspect ratio override; if unset, falls back to environment/default.",
            },
        },
        "required": ["prompt", "script_path"],
    }

    def execute(
        self,
        prompt: str,
        video_id: str = "",
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        callback_url: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 10.0,
        aspect_ratio: str = "9:16",
        script_path: str = None,
    ) -> str:
        result = generate_text2video(
            prompt=prompt,
            video_id=video_id or None,
            api_key=api_key,
            api_url=api_url,
            model=model,
            callback_url=callback_url,
            max_retries=max_retries,
            retry_delay=retry_delay,
            script_path=script_path,
            aspect_ratio=aspect_ratio,
        )
        if result:
            return f"✅ Text2Video generated and saved at: {result}"
        return "❌ Failed to generate or download video from text."


if __name__ == "__main__":
    os.makedirs("temp_video_processing", exist_ok=True)

    print("== 环境检查 ==")
    print(f"ACEDATA_API_KEY: {'set' if os.getenv('ACEDATA_API_KEY') else 'unset'}")
    print(f"ACEDATA_API_URL: {API_URL}")
    print(f"ACEDATA_MODEL: {DEFAULT_MODEL}")

    # Test text2video
    prompt ="""
{'style_guide': {'overall_style': 'beauty-ad, tutorial, luxurious, clean, sophisticated', 'color_palette': ['vibrant red', 'metallic silver', 'natural skin tones', 'soft off-white', 'light grey'], 'lighting_baseline': 'soft high-key studio, diffuse, flattering', 'camera_language': ['static', 'close-ups', 'extreme close-ups'], 'grade_tone': 'clean, radiant, flawless, spa-like'}, 'environment_baseline': {'location_type': 'studio', 'background': 'plain, light grey wall', 'set_elements': [], 'ambience': 'minimalist, serene, professional'}, 'characters': [{'entity_id': 'char_1', 'role': 'demonstrator/model', 'type': 'human', 'details': {'gender': 'female', 'age': 'young adult', 'ethnicity': None, 'body_type': None, 'height': None, 'hair': 'brown, tied back neatly', 'face': 'clear, dewy skin, brown eyes, well-defined eyebrows', 'default_expression': 'serene, calm, neutral', 'clothing': {'top': 'white V-neck top or camisole', 'bottom': None, 'shoes': None, 'accessories': []}, 'default_props': [], 'default_posture': 'deliberate and gentle body language', 'default_emotion': 'relaxed luxury'}}], 'objects_catalog': [{'object_id': 'obj_jar', 'name': 'Olay Regenerist Micro-Sculpting Super Cream jar', 'material': 'plastic', 'size': 'small to medium', 'shape': 'round jar', 'color': 'vibrant red', 'texture': 'smooth, glossy', 'branding': 'OLAY, REGENERIST MICRO-SCULPTING SUPER CREAM', 'condition': 'new'}, {'object_id': 'obj_spatula', 'name': 'small white spatula', 'material': 'plastic', 'size': 'small', 'color': 'white', 'texture': 'smooth', 'condition': 'new'}, {'object_id': 'obj_cream', 'name': 'Olay Regenerist Micro-Sculpting Super Cream', 'material': 'cream', 'size': 'dollop', 'shape': 'viscous fluid / soft solid', 'color': 'white', 'texture': 'rich, creamy, softening when warmed', 'branding': None, 'condition': 'fresh'}]}{'segment_id': 'segment_4', 'timecode': {'start_sec': 12, 'end_sec': 17}, 'stage': 'Final Application & Result', 'description': 'She continues to press the cream into the center of her face and forehead, completing the application, before a final shot reveals her glowing, moisturized skin.', 'subjects': [{'ref': 'char_1', 'overrides': {'props': [], 'expression': 'soft, satisfied'}}], 'objects': [{'ref': 'obj_cream', 'position_in_frame': 'on hands, then on face', 'state_changes': 'being applied, then absorbed/visible as sheen'}], 'environment': {'use_global': True, 'overrides': {}}, 'camera': {'position': 'eye-level', 'angle': 'frontal to profile (left side) to frontal', 'movement': 'static', 'framing': 'CU', 'lens': '50mm', 'focus': 'sharp on face/hands'}, 'actions': ['presses hands on either side of nose, over cheeks', 'gently presses left hand onto temple and forehead area', 'continues pressing motion on forehead', 'displays final result with glowing, moisturized skin'], 'on_screen_text': ['We press', 'and press', 'and press', 'Voilà!'], 'effects': ['visible healthy sheen on skin', 'soft bokeh on background', 'subtle light play on skin texture'], 'sound_effects': ['lo-fi music continues, then fades out', "final expressive narration 'Voilà!'"], 'style': [], 'changes': {'character_changes': 'hands are gone, satisfied expression at the end', 'style_changes': '', 'environment_changes': ''}}
"""

    print("\n== 测试 文生视频 text2video ==")
    result = generate_text2video(
        prompt=prompt,
        script_path="/Users/alexkim/Desktop/Clippie/output/video_script_20250821_222837.txt",
    )
    print("text2video 输出:", result)
