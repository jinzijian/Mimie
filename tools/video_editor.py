"""
Video Editor Tool for Agent
A tool that can be called by an agent to assemble video ads from script and media files.
"""

import ffmpeg
import os
import json
import shutil
import subprocess
import re
from typing import List, Dict, Optional, Tuple, Any, Union
from tools.base_tool import Tool

def video_editor_tool(
    script: Union[str, List[Dict]], 
    media_library_path: str,
    output_filename: str = "final_video.mp4",
    temp_dir: str = "temp_video_processing"
) -> Dict[str, Any]:
    """
    Video editing tool that can be called by an agent.
    
    Args:
        script: Can be:
               - Path to a JSON file containing the script
               - JSON string 
               - List of shot dictionaries with format:
                 [{"clip_id": 1, "description": "...", "start_in_clip": 0, 
                   "duration": 5.0, "transition_to_next": "fade", "transition_duration": 1.0}, ...]
        media_library_path: Path to directory containing video files named like "01_filename.mp4"
        output_filename: Name of the final output video file (can include path)
        temp_dir: Temporary directory for processing (will be cleaned up)
    
    Returns:
        Dict with keys:
        - success: bool - Whether the operation succeeded
        - output_file: str - Path to the generated video file
        - duration: float - Duration of the final video in seconds
        - message: str - Status message
        - errors: List[str] - Any errors encountered
    """
    
    # Configuration
    STANDARD_FRAME_RATE = 30
    STANDARD_VCODEC = 'libx264'
    STANDARD_PIX_FMT = 'yuv420p'
    STANDARD_ACODEC = 'aac'
    STANDARD_AUDIO_RATE = '48000'
    DEFAULT_TRANSITION_DURATION = 1.0
    TARGET_RESOLUTION = (720, 1280)  # 9:16 vertical format
    
    errors = []
    
    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(f"Created output directory: {output_dir}")
        
        # Parse script based on input type
        if isinstance(script, str):
            # Check if it's a file path (ends with .json)
            if script.lower().endswith('.json'):
                if not os.path.exists(script):
                    return {
                        "success": False,
                        "output_file": None,
                        "duration": 0,
                        "message": f"Script file not found: {script}",
                        "errors": [f"File not found: {script}"]
                    }
                
                try:
                    with open(script, 'r', encoding='utf-8') as f:
                        ad_shot_list = json.load(f)
                except (IOError, OSError) as e:
                    return {
                        "success": False,
                        "output_file": None,
                        "duration": 0,
                        "message": f"Failed to read script file: {e}",
                        "errors": [str(e)]
                    }
            else:
                # Treat as JSON string
                ad_shot_list = json.loads(script)
        else:
            # Treat as list
            ad_shot_list = script
            
        if not isinstance(ad_shot_list, list):
            return {
                "success": False,
                "output_file": None,
                "duration": 0,
                "message": "Script must be a list of shot dictionaries",
                "errors": ["Invalid script format"]
            }
            
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "output_file": None,
            "duration": 0,
            "message": f"Failed to parse script JSON: {e}",
            "errors": [str(e)]
        }
    
    # Validate media library path
    if not os.path.exists(media_library_path):
        return {
            "success": False,
            "output_file": None,
            "duration": 0,
            "message": f"Media library path not found: {media_library_path}",
            "errors": [f"Path not found: {media_library_path}"]
        }
    
    
    
    # Helper functions
    def find_clip_by_name(clip_name, case_sensitive=False):
        """
        Find video file by name in media library
        
        Args:
            clip_name: Name or partial name to search for
            exact_match: If True, requires exact filename match (excluding extension)
            case_sensitive: If True, performs case-sensitive search
        
        Returns:
            Full path to the video file if found, None otherwise
        """
        try:
            search_name = clip_name if case_sensitive else clip_name.lower()
            
            for filename in os.listdir(media_library_path):
                if not filename.lower().endswith(".mp4"):
                    continue
                    
                
                compare_name = filename if case_sensitive else filename.lower()
                
                if compare_name == search_name:
                    return os.path.join(media_library_path, filename)
                        
        except FileNotFoundError:
            return None
        return None

    def get_video_info(file_path):
        """Get basic video file information"""
        try:
            probe = ffmpeg.probe(file_path)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            audio_info = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
            return {
                'duration': float(probe['format']['duration']),
                'has_audio': audio_info is not None,
                'width': int(video_info['width']),
                'height': int(video_info['height']),
                'r_frame_rate': video_info.get('r_frame_rate', f'{STANDARD_FRAME_RATE}/1')
            }
        except Exception as e:
            errors.append(f"Failed to get video info for {file_path}: {e}")
            return None

    def detect_black_borders(file_path):
        """Detect black borders and return crop parameters"""
        try:
            cmd = [
                'ffmpeg', '-i', file_path,
                '-vf', 'cropdetect=24:16:0',
                '-f', 'null', '-', '-t', '10'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            lines = result.stderr.split('\n')
            crop_params = None
            
            for line in lines:
                if 'crop=' in line:
                    match = re.search(r'crop=(\d+:\d+:\d+:\d+)', line)
                    if match:
                        crop_params = match.group(1)
            
            if crop_params:
                w, h, x, y = map(int, crop_params.split(':'))
                video_info = get_video_info(file_path)
                if video_info:
                    orig_w, orig_h = video_info['width'], video_info['height']
                    crop_area = w * h
                    orig_area = orig_w * orig_h
                    crop_ratio = crop_area / orig_area
                    
                    max_border = max(x, y, orig_w - (x + w), orig_h - (y + h))
                    
                    if crop_ratio < 0.98 or max_border >= 2:
                        return crop_params
                        
            return None
            
        except Exception as e:
            errors.append(f"Black border detection failed for {file_path}: {e}")
            return None

    def apply_video_processing(input_stream, crop_params=None, target_resolution=None):
        """Apply video processing filters"""
        stream = input_stream
        
        if crop_params:
            w, h, x, y = map(int, crop_params.split(':'))
            stream = stream.filter('crop', w, h, x, y)
        
        if target_resolution:
            target_w, target_h = target_resolution
            stream = stream.filter('scale', target_w, target_h, force_original_aspect_ratio='decrease')
            stream = stream.filter('pad', target_w, target_h, '(ow-iw)/2', '(oh-ih)/2', 'black')
        
        return stream

    # Main processing
    try:
        # Setup temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        # Process clips
        processed_clips = []
        processed_clips_info = []
        total_processed_duration = 0

        print(f"Processing {len(ad_shot_list)} clips...")

        for i, shot in enumerate(ad_shot_list):
            shot_desc = shot.get("description", f"Shot_{i+1}")[:30]
            source_clip_path = find_clip_by_name(shot['file'])

            if not source_clip_path:
                error_msg = f"Clip ID {shot['clip_id']} not found in media library"
                errors.append(error_msg)
                continue

            video_info = get_video_info(source_clip_path)
            if not video_info:
                error_msg = f"Cannot read video info for clip {source_clip_path}"
                errors.append(error_msg)
                continue

            print(f"Processing clip {i+1}: {shot_desc}")
            
            # Detect black borders
            crop_params = detect_black_borders(source_clip_path)
            
            output_path = os.path.join(temp_dir, f"clip_{i+1:02d}.mp4")
            
            try:
                input_stream = ffmpeg.input(source_clip_path, ss=shot['start_in_clip'], t=shot['duration'])
                video_stream = input_stream['v']
                audio_stream = input_stream['a'] if video_info['has_audio'] else None
                
                # Apply video processing
                video_stream = apply_video_processing(
                    video_stream, 
                    crop_params=crop_params, 
                    target_resolution=TARGET_RESOLUTION
                )
                
                output_options = {
                    'vcodec': STANDARD_VCODEC,
                    'r': STANDARD_FRAME_RATE,
                    'pix_fmt': STANDARD_PIX_FMT,
                    'preset': 'medium',
                    'crf': 23
                }
                
                if video_info['has_audio'] and audio_stream is not None:
                    output_options.update({
                        'acodec': STANDARD_ACODEC,
                        'ar': STANDARD_AUDIO_RATE,
                        'audio_bitrate': '128k'
                    })
                    stream = ffmpeg.output(video_stream, audio_stream, output_path, **output_options)
                else:
                    stream = ffmpeg.output(video_stream, output_path, **output_options)

                ffmpeg.run(stream, overwrite_output=True, quiet=True)

                output_info = get_video_info(output_path)
                if output_info:
                    actual_duration = output_info['duration']
                    total_processed_duration += actual_duration
                    processed_clips.append(output_path)
                    processed_clips_info.append(output_info)

            except ffmpeg.Error as e:
                error_msg = f"Failed to process clip {i+1}: {e.stderr.decode() if e.stderr else 'Unknown error'}"
                errors.append(error_msg)

        if not processed_clips:
            return {
                "success": False,
                "output_file": None,
                "duration": 0,
                "message": "No clips were successfully processed",
                "errors": errors
            }

        # Concatenate clips
        print(f"Concatenating {len(processed_clips)} clips...")
        
        # Check audio status
        clips_audio_status = [info['has_audio'] for info in processed_clips_info]
        all_have_audio = all(clips_audio_status)
        any_have_audio = any(clips_audio_status)
        
        # Use file list concatenation method (more reliable)
        try:
            if any_have_audio and not all_have_audio:
                # For mixed audio streams, normalize clips first by adding silent audio to video-only clips
                print("Normalizing clips for mixed audio streams...")
                normalized_clips = []
                
                for i, (clip_path, has_audio) in enumerate(zip(processed_clips, clips_audio_status)):
                    if has_audio:
                        # Clip already has audio, copy as-is
                        normalized_clips.append(clip_path)
                    else:
                        # Create version with silent audio
                        normalized_path = os.path.join(temp_dir, f"normalized_clip_{i+1:02d}.mp4")
                        input_video = ffmpeg.input(clip_path)
                        
                        # Get the duration of the video
                        clip_info = get_video_info(clip_path)
                        duration = clip_info['duration'] if clip_info else 1.0
                        
                        # Create silent audio with same duration as video
                        output_args_norm = {
                            'vcodec': 'copy',  # Copy video stream as-is
                            'acodec': STANDARD_ACODEC,
                            'ar': STANDARD_AUDIO_RATE,
                            'ac': 2,  # Stereo audio
                            't': duration
                        }
                        
                        ffmpeg.output(
                            input_video['v'], 
                            ffmpeg.filter('anullsrc', channel_layout='stereo', sample_rate=STANDARD_AUDIO_RATE),
                            normalized_path,
                            **output_args_norm
                        ).overwrite_output().run(quiet=True)
                        
                        normalized_clips.append(normalized_path)
                
                clips_to_use = normalized_clips
                use_audio_in_output = True
            else:
                clips_to_use = processed_clips
                use_audio_in_output = any_have_audio
            
            # Create file list for concatenation
            filelist_path = os.path.join(temp_dir, "filelist.txt")
            with open(filelist_path, 'w', encoding='utf-8') as f:
                for clip_f in clips_to_use:
                    f.write(f"file '{os.path.abspath(clip_f)}'\n")
            
            output_args_filelist = {
                'vcodec': STANDARD_VCODEC, 
                'pix_fmt': STANDARD_PIX_FMT, 
                'r': STANDARD_FRAME_RATE
            }
            if use_audio_in_output:
                output_args_filelist.update({
                    'acodec': STANDARD_ACODEC, 
                    'audio_bitrate': '192k', 
                    'ar': STANDARD_AUDIO_RATE
                })

            ffmpeg.input(filelist_path, format='concat', safe=0).output(
                output_filename, **output_args_filelist
            ).overwrite_output().run(quiet=True)

        except ffmpeg.Error as e:
            return {
                "success": False,
                "output_file": None,
                "duration": 0,
                "message": f"Video concatenation failed: {str(e)}",
                "errors": errors + [str(e)]
            }

        # Get final video info
        final_info = get_video_info(output_filename)
        if not final_info:
            return {
                "success": False,
                "output_file": None,
                "duration": 0,
                "message": "Failed to generate final video",
                "errors": errors + ["Cannot read final video info"]
            }

        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        return {
            "success": True,
            "output_file": os.path.abspath(output_filename),
            "duration": final_info['duration'],
            "message": f"Video successfully created: {output_filename}",
            "errors": errors
        }

    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
        return {
            "success": False,
            "output_file": None,
            "duration": 0,
            "message": f"Video processing failed: {str(e)}",
            "errors": errors + [str(e)]
        }
class VideoEditor(Tool):
    name: str = "video_editor"
    description: str = "Assemble a video ad using the provided script and media files."
    parameters: dict = {
        "type": "object",
        "required": ["script"],
        "properties": {
            "script": {
                "type": "string",
                "description": "Script content as a JSON string. Expected format: '[{\"file\": \"filename.mp4\", \"start_in_clip\": 0, \"duration\": 5.0, \"description\": \"scene description\"}, ...]'",
            },
            "media_library_path": {
                "type": "string",
                "description": "Path to folder containing video assets",
            },
            "output_filename": {
                "type": "string",
                "description": "Name (or path) of the output video file. Default is 'final_video.mp4'",
            },
        },
    }

    def execute(self, script: str, media_library_path: str, output_filename: str = "final_video.mp4") -> str:
        result = video_editor_tool(
            script=script,
            media_library_path=media_library_path,
            output_filename=output_filename
        )
        
        if result["success"]:
            return f"✅ Video created at: {result['output_file']} (Duration: {result['duration']:.1f}s)"
        else:
            return f"❌ Failed to create video: {result['message']}\nErrors: {result['errors']}"

# Example usage
if __name__ == "__main__":
    print("Video Editor Tool - Example Usage")
    print("=" * 40)
    
    # Example 1: Using JSON file (recommended)
    print("\n📁 Example 1: Using JSON file path")
    result1 = video_editor_tool(
        script="/Users/alexkim/Desktop/Clippie/example/gogomarket/script/ad_script.json",  # JSON file path
        media_library_path="/Users/alexkim/Desktop/Clippie/example/gogomarket/media_library",
        output_filename="/Users/alexkim/Desktop/Clippie/output/my_video.mp4"
    )
    print("Result:", json.dumps(result1, indent=2))
    
