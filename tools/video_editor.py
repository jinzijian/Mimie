import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from openai import OpenAI
import ffmpeg
from typing import List, Dict, Any,Optional
from utils.project_organizer import ProjectOrganizer
from core.call_llms import call_gemini, call_openai, call_anthropic
try:
    from tools.base_tool import Tool
except ModuleNotFoundError:  # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    if str(_repo_root) not in _sys.path:
        _sys.path.append(str(_repo_root))
    from tools.base_tool import Tool
from video_understander import understand_video_for_editor

load_dotenv()


class VideoClipExtractor(Tool):
    """从视频文件中提取单个指定片段的工具"""
    
    name: str = "video_clip_extractor"
    description: str = "Extract a single clip from a video file within a specified time range"
    parameters: dict = {
        "type": "object",
        "required": ["asset_path", "start_time", "end_time"],
        "properties": {
            "asset_path": {
                "type": "string",
                "description": "The path to the source video file",
            },
            "start_time": {
                "type": "number",
                "description": "The start time (in seconds)",
            },
            "end_time": {
                "type": "number",
                "description": "The end time (in seconds)",
            },
            "clip_name": {
                "type": "string",
                "description": "Custom clip name, if not provided, it will be generated automatically",
            }
        },
    }

    def execute(self, asset_path: str, start_time: float, end_time: float, 
                clip_name: Optional[str] = None) -> str:
        """
        提取视频片段
        
        Args:
            asset_path: 源视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            clip_name: 自定义片段名称（可选）
            
        Returns:
            提取出的片段文件路径
        """
        try:
            print(f"🔍 提取片段: {os.path.basename(asset_path)}")
            print(f"   时间范围: {start_time}s - {end_time}s")
            
            # 检查源文件是否存在
            if not os.path.exists(asset_path):
                error_msg = f"❌ 源文件不存在: {asset_path}"
                print(error_msg)
                return error_msg
            
            # 生成输出文件名
            if clip_name is None:
                base_name = os.path.splitext(os.path.basename(asset_path))[0]
                clip_name = f"extracted_{base_name}"
            
            output_path = f"{ProjectOrganizer.get_save_dir(ProjectOrganizer.SaveType.ASSETS)}{clip_name}.mp4"
            duration = end_time - start_time
            
            print(f"   输出文件: {output_path}")
            print(f"   片段时长: {duration:.1f}s")
            
            # 使用ffmpeg提取片段
            input_stream = ffmpeg.input(asset_path, ss=start_time, t=duration)
            output_stream = ffmpeg.output(
                input_stream, 
                output_path,
                vcodec='libx264',
                acodec='aac',
                preset='medium',
                crf=23,
                pix_fmt='yuv420p'
            )
            
            ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
            
            # 检查输出结果
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"   ✅ 提取成功 ({file_size:.1f} MB)")
                return output_path
            else:
                error_msg = "❌ 提取失败，文件未创建"
                print(error_msg)
                return error_msg
                        
        except Exception as e:
            error_msg = f"❌ 提取失败: {str(e)}"
            print(error_msg)
            return error_msg

class VideoConcatenator(Tool):
    """视频拼接工具"""
    
    name: str = "video_concatenator"
    description: str = "Concatenate multiple video clips into a complete video"
    parameters: dict = {
        "type": "object",
        "required": ["clip_paths"],
        "properties": {
            "clip_paths": {
                "type": "string",
                "description": "The array of video clip file paths, JSON format string, e.g.: [\"path1.mp4\", \"path2.mp4\"]",
            }
        },
    }

    def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取视频详细信息
        
        Returns:
            dict: 包含视频信息
        """
        result = {
            'valid': False,
            'has_video': False,
            'has_audio': False,
            'duration': 0,
            'width': 0,
            'height': 0,
            'fps': 0,
            'error': None,
            'file_size_mb': 0
        }
        
        try:
            # 检查文件是否存在
            if not os.path.exists(video_path):
                result['error'] = "文件不存在"
                return result
            
            # 检查文件大小
            file_size = os.path.getsize(video_path)
            if file_size == 0:
                result['error'] = "文件为空"
                return result
            
            result['file_size_mb'] = file_size / (1024 * 1024)
            
            # 使用ffprobe检查视频文件
            probe = ffmpeg.probe(video_path)
            
            # 检查流信息
            streams = probe.get('streams', [])
            if not streams:
                result['error'] = "文件没有媒体流"
                return result
            
            # 检查视频和音频流
            for stream in streams:
                codec_type = stream.get('codec_type', '')
                if codec_type == 'video':
                    result['has_video'] = True
                    result['width'] = stream.get('width', 0)
                    result['height'] = stream.get('height', 0)
                    
                    # 获取帧率
                    r_frame_rate = stream.get('r_frame_rate', '0/1')
                    if '/' in r_frame_rate:
                        num, den = r_frame_rate.split('/')
                        if int(den) != 0:
                            result['fps'] = int(num) / int(den)
                    
                    # 获取时长
                    if 'duration' in stream:
                        result['duration'] = float(stream['duration'])
                        
                elif codec_type == 'audio':
                    result['has_audio'] = True
            
            # 如果没有从流中获取到时长，尝试从format中获取
            if result['duration'] == 0 and 'format' in probe:
                format_info = probe['format']
                if 'duration' in format_info:
                    result['duration'] = float(format_info['duration'])
            
            # 必须有视频流才算有效
            if result['has_video']:
                result['valid'] = True
            else:
                result['error'] = "文件没有视频流"
                
        except ffmpeg.Error as e:
            result['error'] = f"ffprobe错误: {str(e)}"
        except Exception as e:
            result['error'] = f"验证失败: {str(e)}"
            
        return result

    def _determine_target_resolution(self, video_files: List[Dict]) -> tuple[int, int]:
        """
        确定目标分辨率
        选择最常见的分辨率，或者最高的分辨率
        """
        resolutions = {}
        max_pixels = 0
        best_resolution = (1920, 1080)  # 默认分辨率
        
        for video in video_files:
            width, height = video['width'], video['height']
            resolution = (width, height)
            pixels = width * height
            
            # 统计分辨率出现次数
            if resolution in resolutions:
                resolutions[resolution] += 1
            else:
                resolutions[resolution] = 1
            
            # 记录最高分辨率
            if pixels > max_pixels:
                max_pixels = pixels
                best_resolution = resolution
        
        # 选择出现次数最多的分辨率
        most_common_resolution = max(resolutions.items(), key=lambda x: x[1])[0]
        
        print(f"🎯 分辨率统计: {resolutions}")
        print(f"📐 选择目标分辨率: {most_common_resolution[0]}x{most_common_resolution[1]}")
        
        return most_common_resolution

    def execute(self, clip_paths: str) -> str:
        """
        拼接视频片段
        
        Args:
            clip_paths: 视频片段文件路径数组的JSON字符串
            output_path: 输出文件路径
            
        Returns:
            拼接完成的视频文件路径，如果失败则返回错误信息
        """
        output_path = f"{ProjectOrganizer.get_save_dir(ProjectOrganizer.SaveType.ASSETS)}concatenated_video.mp4"
        
        try:
            print(f"🔗 开始拼接视频...")
            
            # 解析片段路径数组
            try:
                video_files = json.loads(clip_paths)
                if not isinstance(video_files, list):
                    error_msg = "❌ clip_paths必须是数组格式的JSON字符串"
                    print(error_msg)
                    return error_msg
            except json.JSONDecodeError as e:
                error_msg = f"❌ JSON解析失败: {e}"
                print(error_msg)
                return error_msg
            
            print(f"🎬 待拼接片段数量: {len(video_files)}")
            
            if not video_files:
                error_msg = "❌ 没有提供视频片段"
                print(error_msg)
                return error_msg
            
            # 验证所有输入文件
            valid_files = []
            skipped_files = []
            total_duration = 0
            
            for i, video_path in enumerate(video_files):
                print(f"🔍 验证片段 {i+1}: {os.path.basename(video_path)}")
                
                video_info = self._get_video_info(video_path)
                
                if video_info['valid']:
                    print(f"   ✅ 文件有效 ({video_info['file_size_mb']:.1f} MB, {video_info['duration']:.1f}s)")
                    print(f"   📹 分辨率: {video_info['width']}x{video_info['height']}")
                    print(f"   🔊 音频流: {'是' if video_info['has_audio'] else '否'}")
                    valid_files.append({
                        'path': video_path,
                        'has_audio': video_info['has_audio'],
                        'duration': video_info['duration'],
                        'width': video_info['width'],
                        'height': video_info['height'],
                        'fps': video_info['fps']
                    })
                    total_duration += video_info['duration']
                else:
                    print(f"   ❌ 文件无效: {video_info['error']}")
                    skipped_files.append({
                        'path': video_path,
                        'reason': video_info['error']
                    })
            
            if not valid_files:
                error_msg = "❌ 没有找到有效的视频文件"
                print(error_msg)
                if skipped_files:
                    print("跳过的文件:")
                    for skipped in skipped_files:
                        print(f"   - {os.path.basename(skipped['path'])}: {skipped['reason']}")
                return error_msg
            
            print(f"📊 有效文件: {len(valid_files)} 个")
            print(f"📊 跳过文件: {len(skipped_files)} 个")
            print(f"⏱️  预计总时长: {total_duration:.1f} 秒")
            
            if skipped_files:
                print("⚠️  跳过的文件:")
                for skipped in skipped_files:
                    print(f"   - {os.path.basename(skipped['path'])}: {skipped['reason']}")
            
            # 创建输出目录
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 拼接视频
            success, error_detail = self._concat_videos(valid_files, output_path)
            
            if not success:
                error_msg = f"❌ 拼接过程失败: {error_detail}"
                print(error_msg)
                return error_msg
            
            # 检查输出结果
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                
                # 获取最终视频时长
                try:
                    probe = ffmpeg.probe(output_path)
                    duration = float(probe['streams'][0]['duration'])
                except:
                    duration = 0
                
                print(f"✅ 视频拼接成功")
                print(f"   输出文件: {output_path}")
                print(f"   有效片段: {len(valid_files)}")
                print(f"   跳过片段: {len(skipped_files)}")
                print(f"   总时长: {duration:.1f} 秒")
                print(f"   文件大小: {file_size:.1f} MB")
                
                return output_path
            else:
                error_msg = "❌ 拼接失败，输出文件未创建"
                print(error_msg)
                return error_msg
                
        except Exception as e:
            error_msg = f"❌ 拼接失败: {str(e)}"
            print(error_msg)
            return error_msg
    
    def _concat_videos(self, video_files: List[Dict], output_path: str) -> tuple[bool, str]:
        """
        拼接多个视频文件，处理分辨率不匹配问题
        
        Args:
            video_files: 包含视频文件信息的字典列表
            output_path: 输出文件路径
            
        Returns:
            tuple: (是否成功, 错误详情)
        """
        try:
            print(f"🔗 开始拼接 {len(video_files)} 个文件...")
            
            if len(video_files) == 1:
                # 只有一个文件，直接复制
                import shutil
                print("📋 只有一个文件，直接复制...")
                shutil.copy2(video_files[0]['path'], output_path)
                print("✅ 复制完成")
                return True, ""
            
            # 多个文件需要拼接
            print("🎬 多个文件，使用ffmpeg拼接...")
            
            # 确定目标分辨率
            target_width, target_height = self._determine_target_resolution(video_files)
            
            # 检查是否所有文件都有音频流
            has_audio_files = [f for f in video_files if f['has_audio']]
            no_audio_files = [f for f in video_files if not f['has_audio']]
            
            if no_audio_files:
                print(f"⚠️  发现 {len(no_audio_files)} 个无音频文件:")
                for f in no_audio_files:
                    print(f"   - {os.path.basename(f['path'])}")
            
            # 处理每个输入文件，统一分辨率和音频
            processed_inputs = []
            
            for i, video_file in enumerate(video_files):
                input_stream = ffmpeg.input(video_file['path'])
                
                # 处理视频流 - 统一分辨率
                video_stream = input_stream['v']
                
                # 如果分辨率不匹配，进行缩放
                if video_file['width'] != target_width or video_file['height'] != target_height:
                    print(f"📐 调整 {os.path.basename(video_file['path'])} 分辨率: "
                          f"{video_file['width']}x{video_file['height']} -> {target_width}x{target_height}")
                    
                    # 使用scale filter进行缩放，保持宽高比
                    video_stream = ffmpeg.filter(video_stream, 'scale', target_width, target_height, force_original_aspect_ratio='decrease')
                    video_stream = ffmpeg.filter(video_stream, 'pad', target_width, target_height, '(ow-iw)/2', '(oh-ih)/2', color='black')
                
                # 处理音频流
                if video_file['has_audio']:
                    audio_stream = input_stream['a']
                else:
                    # 为无音频文件生成静音
                    print(f"🔇 为 {os.path.basename(video_file['path'])} 添加静音轨道")
                    duration = video_file['duration']
                    audio_stream = ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', 
                                              f='lavfi', t=duration)['a']
                
                processed_inputs.append({'v': video_stream, 'a': audio_stream})
            
            # 拼接所有处理过的流
            if len(has_audio_files) == 0:
                # 所有文件都没有音频，只拼接视频流
                print("🔇 所有文件都无音频，仅拼接视频流...")
                video_streams = [inp['v'] for inp in processed_inputs]
                concat_video = ffmpeg.concat(*video_streams, v=1, a=0)
                
                output_stream = ffmpeg.output(
                    concat_video, output_path,
                    vcodec='libx264', 
                    preset='medium', 
                    crf=23,
                    pix_fmt='yuv420p'
                )
            else:
                # 拼接视频和音频流
                print("🔊 拼接视频和音频流...")
                video_streams = [inp['v'] for inp in processed_inputs]
                audio_streams = [inp['a'] for inp in processed_inputs]
                
                concat_video = ffmpeg.concat(*video_streams, v=1, a=0)
                concat_audio = ffmpeg.concat(*audio_streams, v=0, a=1)
                
                output_stream = ffmpeg.output(
                    concat_video, concat_audio, output_path,
                    vcodec='libx264', 
                    acodec='aac', 
                    preset='medium', 
                    crf=23,
                    pix_fmt='yuv420p'
                )
            
            print("⚙️ 执行ffmpeg拼接...")
            # 移除quiet=True，显示详细错误信息
            ffmpeg.run(output_stream, overwrite_output=True, quiet=False)
            print("✅ 拼接完成")
            return True, ""
            
        except ffmpeg.Error as e:
            error_detail = "FFmpeg执行错误"
            if hasattr(e, 'stderr') and e.stderr:
                try:
                    stderr_str = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
                    error_detail += f": {stderr_str}"
                except:
                    error_detail += f": {str(e)}"
            else:
                error_detail += f": {str(e)}"
            
            print(f"❌ FFmpeg错误: {error_detail}")
            return False, error_detail
            
        except Exception as e:
            error_detail = f"意外错误: {str(e)}"
            print(f"❌ 拼接失败: {error_detail}")
            return False, error_detail


def video_edit_flow(video_script_path: str, asset_paths: list[str], keep_video_audio: bool = False, output_dir: str = "workdir"):
    
    print("This is a new version of video_edit_flow")
    
    # 1. check if reference_script_path exists
    if not os.path.exists(video_script_path):
        raise FileNotFoundError(f"Reference script file not found: {video_script_path}")
    
    video_script = None
    with open(video_script_path, "r", encoding="utf-8") as f:
        video_script = f.read()
        
    if not video_script:
        raise ValueError(f"Failed to read video script from {video_script_path}")
    
    # 2. check if assets exist
    if not asset_paths:
        raise ValueError(f"Asset understandings are required")
    
    # 3. generate video understandings
    comprehensive_understanding_for_assets = ""
    for asset_path in asset_paths:
        if not os.path.exists(asset_path):
            print(f"❌ Error: Asset not found: {asset_path}")
            continue
        video_understanding = understand_video_for_editor(asset_path, model_name="gemini-2.5-pro")
        video_understanding_with_asset_path = f"{asset_path}: /n {video_understanding} /n" + "="*50 + "\n"
        comprehensive_understanding_for_assets += video_understanding_with_asset_path
        
    # 4. save video understandings
    ProjectOrganizer.save(ProjectOrganizer.SaveType.UNDERSTANDINGS, comprehensive_understanding_for_assets, "comprehensive_understanding_for_assets.txt", workdir=output_dir)
    
    # 5. text based asset content selection
    user_requirements = f"Select the contents that can help me to generate a video based on the video script: {video_script}"
    text_based_asset_content_selection_path = generate_edit_instructions(comprehensive_understanding_for_assets, user_requirements)
    with open(text_based_asset_content_selection_path, "r") as f:
        text_based_asset_content_selection_str = f.read()

    text_based_asset_content_selection = json.loads(text_based_asset_content_selection_str)
    
    # 6. extract assets based on the text based asset content selection
    clip_paths_in_order = []
    for i, clip in enumerate(text_based_asset_content_selection):
        asset_path = clip["asset_path"]
        start_time = clip["start_time"]
        end_time = clip["end_time"]
        print(f"Extracting asset: {asset_path} from {start_time} to {end_time}")
        clip_path = VideoClipExtractor().execute(asset_path, start_time, end_time, clip_name=f"extracted_{i}")
        print(f"Extracted asset: {clip_path}")
        clip_paths_in_order.append(clip_path)
    
    clip_paths_in_order_json = json.dumps(clip_paths_in_order, indent=2, ensure_ascii=False)
    ProjectOrganizer.save(ProjectOrganizer.SaveType.SCRIPTS, clip_paths_in_order_json, "clip_paths_in_order.json", workdir=output_dir)
    
    # 7. concatenate the clips
    concatenated_video_path = VideoConcatenator().execute(clip_paths_in_order_json)
    print(f"Concatenated video path: {concatenated_video_path}")
    
        
    return concatenated_video_path


def generate_edit_instructions(video_understanding_text_path: str, user_requirements: str) -> str:
    with open(video_understanding_text_path, "r") as f:
        video_understanding_text = f.read()
    # Analysis prompt
    prompt = f"""
You are a professional AI video editor.

Your task: for each beat in the USER SCRIPT, select **exactly one** non-overlapping clip from the source assets in PART 2,
**in the same beat order**, with **no asset reuse**. **Do not change the original asset order**: always move forward through the
assets as they appear in PART 2; never jump back to an earlier asset.

---

## PART 2: SECOND-BY-SECOND BREAKDOWN
{video_understanding_text}

## USER SCRIPT / STRUCTURE REQUIREMENTS
{user_requirements}

---

## HARD CONSTRAINTS (must pass all):
1) One-to-one & order-locked mapping:
   - Parse the USER SCRIPT into an ordered list of beats: BEATS = [beat_1, beat_2, ..., beat_N].
   - Produce **exactly N** clips, and **clip_i corresponds to beat_i** (preserve beat order).
   - **Source-order preservation**: the chosen asset for clip_i must appear **at or after** the asset used for clip_i-1 in PART 2.
     Do **not** reorder materials and never jump back to an earlier asset.

2) Unique asset usage:
   - **Each asset_path may be used at most once** across the entire output.

3) Semantic completeness:
   - Do not cut mid-action / mid-sentence / mid-expression. Prefer natural boundaries visible in PART 2.

4) Duration alignment:
   - Each clip ≥ 3.0s.
   - Each clip’s duration should be close to the intended duration of its beat.
   - The **total** duration should be close to the script’s total.

5) Valid times & non-overlap:
   - start_time < end_time for every clip.
   - Times **must** be taken **only** from PART 2 (respect the second-level markers).
   - No overlaps within the selected range of any asset.

6) Tie-breaking:
   - Prefer emotionally/visually strong, clear moments most faithful to the beat.

---

## VALIDATION (self-check before you output):
- Number of output clips == number of script beats.
- Clip sequence strictly follows **beat_1 → beat_2 → ... → beat_N**.
- **All asset_path values are unique** and follow their **original order** in PART 2 (no backward jumps).
- All time ranges are valid (numeric, ≥ 3.0s, within asset bounds, non-overlapping).
- Total duration ≈ total intended script duration (allow a reasonable margin if needed).

---

## OUTPUT FORMAT (JSON array only, no extra text):
[
  {{
    "asset_path": "exactly-as-listed-in-PART-2",
    "start_time": 12.0,
    "end_time": 18.5,
    "description": "Briefly describe the visible moment and how it fulfills beat_i."
  }},
  ...
]

Return **only** the final JSON array of selected clips.
"""



    
    try:
        # Generate analysis
        # response = model.generate_content(prompt, request_options={'timeout': 2400})
        # result = response.text
        result = call_openai(prompt)

        # Save the result - extract only the JSON array content
        # Remove markdown code blocks and extract the JSON array
        clean_result = result.strip()
        if clean_result.startswith("```json"):
            clean_result = clean_result[7:]  # Remove ```json
        if clean_result.endswith("```"):
            clean_result = clean_result[:-3]  # Remove ```
        clean_result = clean_result.strip()
        
        # Validate JSON format
        try:
            json.loads(clean_result)
        except json.JSONDecodeError:
            print("Warning: Result is not valid JSON, saving raw result")
        
        # Save to file，使用相对路径并自动适应当前脚本目录
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workdir", "understandings")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "selected_asset_content.json")
        with open(output_path, "w") as f:
            f.write(clean_result)
        print(f"Selected asset content saved to {output_path}")
        return output_path
        
    except Exception as e:
        error_msg = f"Error selecting content based on text understanding: {str(e)}"
        print(error_msg)
        return error_msg

class VideoEditor(Tool):
    name: str = "video_editor"
    description: str = "Edit videos and generate a concatenated video."
    parameters: dict = {
        "type": "object",
        "properties": {
            "video_script_path": {
                "type": "string",
                "description": "Path to the final video script text file",
            },
            "asset_paths": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of asset paths to be used in the video",
            },
        },
        "required": ["video_script_path", "asset_paths"],
    }

    def execute(self, video_script_path: str, asset_paths: List[str]) -> str:
        return video_edit_flow(video_script_path, asset_paths)



if __name__ == "__main__":
    with open("./workdir/understandings/comprehensive_understanding_for_assets.txt", "r") as f:
        video_understanding_text = f.read()
    with open("./new_script.txt", "r") as f:
        user_requirements = f.read()
    generate_edit_instructions(video_understanding_text, user_requirements)