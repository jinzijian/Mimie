
"""
Script Generator Tool

Generates video scripts based on user requirements with customizable prompts.
Takes user video requirements as input and outputs structured video scripts.
"""

from pathlib import Path
from openai import OpenAI
import base64
import os
import json
from typing import Any, Dict
from dotenv import load_dotenv
import datetime
import litellm
# Support running as a script without package context
try:
    from tools.base_tool import Tool
    from utils.project_organizer import ProjectOrganizer
except ModuleNotFoundError:  # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    if str(_repo_root) not in _sys.path:
        _sys.path.append(str(_repo_root))
    from tools.base_tool import Tool
    from utils.project_organizer import ProjectOrganizer

# Load environment variables from .env file
load_dotenv()

# 模型配置 - 可以在这里简单修改使用的模型
MODEL_NAME = "gemini/gemini-2.5-pro"  # 改成 "gpt-4" 或其他模型来切换

class ScriptGenerator(Tool):
    """Tool for generating video scripts based on user requirements"""
    
    def __init__(self, custom_prompt: str = None):
        """
        Initialize the Script Generator
        
        Args:
            custom_prompt: Optional custom prompt to prepend to user requirements
        """
        super().__init__(
            name="script_generator",
            description="Generate video scripts based on user requirements and text description of existing user-provided videos or images",
            parameters={
                "type": "object",
                "properties": {
                    "user_requirements": {
                        "type": "string",
                        "description": "User's requirements and description for the video"
                    },
                    "current_assets": {
                        "type": "string",
                        "description": "Text description of existing user-provided videos or images"
                    },
                    "video_duration": {
                        "type": "integer",
                        "description": "Desired video duration in seconds (default: 30)"
                    },
                    "video_style": {
                        "type": "string",
                        "description": "Style of video (e.g., 'commercial', 'educational', 'promotional', 'storytelling')"
                    }
                },
                "required": ["user_requirements", "video_duration", "video_style"]
            }
        )
        
    def execute(self, **kwargs) -> str:
        """Generate a video script based on user requirements and save to txt file
        
        Returns:
            Absolute path to the saved txt file, or error JSON if failed
        """
        user_requirements = kwargs.get('user_requirements', '')
        current_assets = kwargs.get('current_assets', '')
        video_duration = kwargs.get('video_duration', 30)
        video_style = kwargs.get('video_style', 'promotional')
        
        if not user_requirements:
            error_message = "User requirements are required to generate a script"
            return json.dumps({"error": error_message})
            
        # Construct the full prompt
        system_prompt = f"""
Generate a detailed video script.

Write it in natural language, NOT JSON format.

Step 1 — Determine the overall **visual style**:
- Base the style decision on the user's requested **video type** (e.g., TikTok ad, cinematic promo, tutorial) and **product category** (e.g., clothing, cosmetics, tech gadget, game).
- General rules:
  - Physical / tangible consumer products (clothes, food, cosmetics, household items) → prefer **realistic / live-action style**.
  - Digital products, entertainment IPs, or products where user explicitly requests a creative aesthetic (anime, Y2K, cyberpunk, surreal) → use a **stylized / creative style**.
  - If ambiguous, default to realistic but allow subtle stylistic elements that fit the product's brand.

Step 2 — Write the video script:
- Structure the ad as a **mini story arc** with a clear beginning, middle, and ending:
  - Opening (hook/attention grab).
  - Development (product experience, features, or emotional build-up).
  - Climax & Closing (brand reveal, slogan, or call to action).
- Explicitly align every scene's description with the chosen style.
- Ensure smooth logical continuity: 
  - The ending frame of one scene should naturally connect to the starting frame of the next (through shared shapes, motions, objects, or perspectives).
  - Transitions should feel intentional (e.g., a motion continues, an object is carried over, lighting shifts consistently).
- Keep each scene concise and controlled within 8 seconds.
- Incorporate user requirements (duration, product features, style hints, target audience).
- Always consider available assets/materials (user-provided videos, images, or reference footage).
- Minimize the need for difficult-to-generate new assets: prioritize reusing or recombining provided materials.

- Overall description: A concise but vivid summary of the shot.
    - Subject: The main subject(s) of the shot.  
        * ALWAYS be highly detailed.  
        * For people: include gender, approximate age, ethnicity, body type, height, hairstyle, facial features, clothing (top, bottom, shoes), accessories (glasses, jewelry, bag, watch), props they hold, facial expression, posture, and emotional vibe.  
        * For animals: include species, breed, color, size, fur/skin/feather details, accessories (collar, leash), expression or behavior.  
        * For objects/scenes: include material, size, shape, color, texture, notable features, condition (new, old, worn), placement in the environment.  
        * If multiple subjects exist, describe EACH ONE in full detail separately (do not summarize them as a group).
    - Action: What the subject(s) is/are doing (clear verbs like walking, typing, looking up).
    - Style: Specific creative style keywords (e.g., cinematic, sci-fi, film noir, anime, product-ad).
    - Camera positioning and motion: [Optional] Camera angle and movement (e.g., dolly-in, aerial, handheld, pan left).
    - Composition: [Optional] Framing of the shot (e.g., wide shot, medium close-up, two-shot).
    - Focus and lens effects: [Optional] Lens type and focus (e.g., shallow focus, wide-angle 24mm, macro shot).
    - Ambiance: [Optional] Mood from color/light (e.g., neon-lit night, golden hour warm tones, rainy and gloomy).

    
Output format:
- First, state the **Chosen Style** (Realistic / Stylized, with 1–2 words explanation why).
- Then, write the scene-by-scene script with clear continuity and a strong beginning and ending.
"""

        try:
            # 使用 LiteLLM 调用配置的模型
            response = litellm.completion(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Create a {video_duration}-second {video_style} video script based on: {user_requirements} and current assets: {current_assets}"}
                ],
                temperature=0.7,
                max_tokens=8000,
                api_key=os.getenv("GOOGLE_API_KEY")  # 复用现有的 GOOGLE_API_KEY
            )
            
            script_content = response.choices[0].message.content
            
            # Generate timestamp-based filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"video_script_{timestamp}.txt"
            
            file_path = ProjectOrganizer.save(ProjectOrganizer.SaveType.SCRIPTS, script_content, filename)

            # Return only the absolute path
            absolute_path = str(Path(file_path).resolve())
            
            return absolute_path
                
        except Exception as e:
            error_message = f"Failed to generate script: {str(e)}"
            return json.dumps({"error": error_message})


# Create default instance
script_generator = ScriptGenerator()

def generate_script(user_requirements: str, current_assets: str = "", **kwargs) -> str:
    """
    Convenience function to generate a video script and save to txt file
    
    Args:
        user_requirements: User's description of what they want in the video
        current_assets: Description of existing assets available
        **kwargs: Additional parameters like video_duration, video_style
        
    Returns:
        Absolute path to the saved txt file
    """
    generator = ScriptGenerator()
    return generator.execute(
        user_requirements=user_requirements,
        current_assets=current_assets,
        **kwargs
    )


if __name__ == "__main__":
    # Test the script generator
    test_requirements = "Create a 30-second promotional video for a new cat scratching post that looks like famous artworks"
    result = generate_script(
        user_requirements=test_requirements,
        current_assets="",
        video_style="commercial",
        video_duration=30
    )
    print("Generated script and saved to file at:")
    print(result)
