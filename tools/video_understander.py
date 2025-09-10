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
from utils.project_organizer import ProjectOrganizer
# Load environment variables
load_dotenv()


def understand_video(video_path: str, model_name: str = "gemini-2.5-pro") -> str:
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
    
    # Analysis prompt
    prompt = [
        "Please provide a comprehensive analysis of this video content. ",
        "Analyze the video in the following structure:",
        "",
        "## PART 1: OVERALL VIDEO ANALYSIS",
        "",
        "### 1. Technical Quality Assessment",
        "- Video resolution and clarity",
        "- Frame rate and smoothness", 
        "- Any visual distortions, artifacts, or quality issues",
        "- Continuity and coherence between scenes",
        "- Camera stability and focus quality",
        "- Audio quality and synchronization",
        "",
        "### 2. Visual Content Overview",
        "- Main subjects: people, objects, environments",
        "- Visual style, color palette, and aesthetics", 
        "- Camera movements and shot compositions",
        "- Lighting and visual effects",
        "",
        "### 3. Content Summary",
        "- What happens in the video?",
        "- Main actions, events, and narrative flow",
        "- Key characters and their roles",
        "- Overall purpose and message of the video",
        "",
        "### 4. Audio Analysis (if present)",
        "- Dialogue, narration, or speech content",
        "- Background music and sound effects",
        "- Audio quality and clarity",
        "",
        "### 5. Text and UI Elements",
        "- Any text, captions, or subtitles",
        "- User interface elements",
        "- Graphics and overlays",
        "",
        "## PART 2: SECOND-BY-SECOND BREAKDOWN",
        "",
        "Provide a detailed timeline analysis describing what happens in each second of the video:",
        "",
        "Second 0-1: [Description]",
        "Second 1-2: [Description]",
        "Second 2-3: [Description]",
        "... (continue for the entire video duration)",
        "",
        "For each second, describe:",
        "- Visual elements and actions",
        "- Any audio or dialogue",
        "- Scene transitions or changes",
        "- Notable events or movements",
        "",
        "Please be thorough and detailed so someone who hasn't seen the video can understand exactly what happens moment by moment.",
        video_file
    ]
    
    try:
        # Generate analysis
        response = model.generate_content(prompt, request_options={'timeout': 2400})
        result = response.text
        ProjectOrganizer.save(ProjectOrganizer.SaveType.UNDERSTANDINGS, result, f"video_understanding_{Path(video_path).name}.txt")
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
    

def understand_video_for_editor(video_path: str, model_name: str = "gemini-2.5-pro") -> str:
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
    
    # Analysis prompt
    prompt = [
        "Please provide a comprehensive analysis of this video content. ",
        "Analyze the video in the following structure:",
        "",
        "Video: <video_path>",
        "SECOND-BY-SECOND BREAKDOWN",
        "",
        "Provide a detailed timeline analysis describing what happens in each second of the video:",
        "",
        "Second 0-1: [Description]",
        "Second 1-2: [Description]",
        "Second 2-3: [Description]",
        "... (continue for the entire video duration)",
        "",
        "For each second, describe:",
        "- Visual elements and actions",
        "- Any audio or dialogue",
        "- Scene transitions or changes",
        "- Notable events or movements",
        "",
        "Please be thorough and detailed so someone who hasn't seen the video can understand exactly what happens moment by moment. Only output the final results.",
        video_file
    ]
    
    try:
        # Generate analysis
        response = model.generate_content(prompt, request_options={'timeout': 2400})
        result = response.text
        ProjectOrganizer.save(ProjectOrganizer.SaveType.UNDERSTANDINGS, result, f"video_understanding_{Path(video_path).name}.txt")
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
class VideoUnderstander(Tool):
    name: str = "video_understander"
    description: str = "Analyze video content using Gemini and return a detailed understanding."
    parameters: dict = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
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