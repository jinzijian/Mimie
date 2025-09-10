"""
Simple Video Understanding Function

One function to understand video content with model and file path.
"""

import google.generativeai as genai
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from tools.base_tool import Tool

# Load environment variables
load_dotenv()


def understand_video(script_path: str, video_path: str, model_name: str = "gemini-2.5-pro") -> str:
    """
    Understand video content with detailed analysis.
    
    Args:
        video_path: Path to the video file
        model_name: Gemini model to use (default: gemini-2.5-pro)
        
    Returns:
        Detailed video content analysis
    """
    # Configure API Key
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set!")
    
    genai.configure(api_key=api_key)
    
    print(f"Understanding video: {Path(video_path).name} with model: {model_name}")
    
    # Upload video
    print(f"Uploading video...")
    video_file = genai.upload_file(path=video_path)
    print(f"Upload initiated. Waiting for processing...")
    
    # Wait for processing
    while video_file.state.name == "PROCESSING":
        print(f"Video is still processing. Waiting 15 seconds...")
        time.sleep(15)
        video_file = genai.get_file(video_file.name)
    
    if video_file.state.name == "FAILED":
        try:
            genai.delete_file(video_file.name)
        except:
            pass
        raise Exception(f"Video processing failed for {video_path}")
    
    print(f"Video processed successfully. Analyzing...")
    
    # Create model
    model = genai.GenerativeModel(model_name)
    with open(script_path, "r", encoding="utf-8") as f:
        script_text = f.read()
    print(f"Script text: {script_text}")
    
    # Analysis prompt
    prompt = [
    "You are a video QA and script alignment expert.",
    "",
    "TASK:",
    "1. Read the provided SCRIPT (see below).",
    "2. Watch the provided VIDEO and determine which part of the script it corresponds to.",
    "3. Evaluate how well the video matches the script requirements.",
    "4. Check for distortions or artifacts in the generated video.",
    "",
    "## SCRIPT",
    script_text,
    "",
    "## PART 1: SCENE ALIGNMENT",
    "- Identify which scene or lines of the script this video most closely matches.",
    "- Quote the relevant script excerpt.",
    "- Evaluate requirement-by-requirement (visuals, camera motion, on-screen text, audio, transitions, branding).",
    "- For each requirement: explain if it is satisfied, partially satisfied, or failed, with evidence from the video.",
    "",
    "## PART 2: DISTORTION & ARTIFACT DETECTION",
    "Check for common generation issues:",
    "- Geometry: warped anatomy, fused limbs, distorted objects.",
    "- Texture: logo/print deformation, text instability, strange patterns.",
    "- Temporal: flicker, sudden jumps, inconsistent frames.",
    "- Semantic: mismatch with script content, wrong props/actions, lip-sync issues.",
    "",
    "## PART 3: SCORING (Informal)",
    "- Script alignment: low / medium / high",
    "- Visual quality: low / medium / high",
    "- Distortion severity: none / minor / moderate / severe",
    "",
    "## PART 4: CONCLUSION",
    "- Provide an overall judgment of whether the video is acceptable.",
    "- List the key problems and give recommendations for improvement.",
    "",
    "Please give a clear, detailed written report. Start with English, and add a brief Chinese summary at the end.",
    "",
    video_file
    ]
    
    try:
        # Generate analysis
        response = model.generate_content(prompt, request_options={'timeout': 2400})
        result = response.text
        
        print(f"Analysis completed for {Path(video_path).name}")
        
        # Clean up
        try:
            genai.delete_file(video_file.name)
            print(f"Cleaned up remote file")
        except:
            pass
        
        return result
        
    except Exception as e:
        # Clean up on error
        try:
            genai.delete_file(video_file.name)
        except:
            pass
        
        error_msg = f"Error analyzing video {Path(video_path).name}: {str(e)}"
        print(error_msg)
        return error_msg

class VideoVerifier(Tool):
    name: str = "video_verifier"
    description: str = "Check if the video is valid and meets the requirements."
    parameters: dict = {
        "type": "object",
        "required": ["script_path", "video_path"],
        "properties": {
            "script_path": {
                "type": "string",
                "description": "Local path to the script file to be analyzed.",
            },
            "video_path": {
                "type": "string",
                "description": "Local path to the video file to be analyzed.",
            },
            "model_name": {
                "type": "string",
                "description": "Gemini model name (default: gemini-2.5-pro)",
                "default": "gemini-2.5-pro"
            }
        }
    }

    def execute(self, video_path: str, model_name: str = "gemini-2.5-pro") -> str:
        try:
            return understand_video(video_path=video_path, model_name=model_name)
        except Exception as e:
            return f"❌ Error during video understanding: {e}"


if __name__ == "__main__":
    # Simple example usage
    video_path = "/Users/alexkim/Desktop/Clippie/example/gogomarket/media_library/00_end_card_video_with_audio.mp4"
    
    if Path(video_path).exists():
        result = understand_video(video_path)
        print("\n" + "="*50)
        print("VIDEO ANALYSIS RESULT:")
        print("="*50)
        print(result)
    else:
        print(f"Video file not found: {video_path}")
        print("Please update the video_path variable with an actual video file.")