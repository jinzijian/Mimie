"""
Simple Image Understanding Function

One function to understand image content with model and file path.
"""

import google.generativeai as genai
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from utils.project_organizer import ProjectOrganizer
# Support running as a script without package context
try:
    from tools.base_tool import Tool
except ModuleNotFoundError:  # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    if str(_repo_root) not in _sys.path:
        _sys.path.append(str(_repo_root))
    from tools.base_tool import Tool

# Load environment variables
load_dotenv()


def understand_image(image_path: str, model_name: str = "gemini-2.5-pro") -> str:
    """
    Understand image content with detailed analysis.

    Args:
        image_path: Path to the image file
        model_name: Gemini model to use (default: gemini-2.5-pro)

    Returns:
        Detailed image content analysis
    """
    # Configure API Key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set!")

    genai.configure(api_key=api_key)

    print(f"Understanding image: {Path(image_path).name} with model: {model_name}")

    # Upload image
    print("Uploading image...")
    image_file = genai.upload_file(path=image_path)
    print("Upload initiated. Waiting for processing if needed...")

    # Wait for processing (images are usually fast, but handle consistently)
    while hasattr(image_file, "state") and getattr(image_file.state, "name", "") == "PROCESSING":
        print("Image is still processing. Waiting 3 seconds...")
        time.sleep(3)
        image_file = genai.get_file(image_file.name)

    if hasattr(image_file, "state") and getattr(image_file.state, "name", "") == "FAILED":
        try:
            genai.delete_file(image_file.name)
        except Exception:
            pass
        raise Exception(f"Image processing failed for {image_path}")

    print("Image ready. Analyzing...")

    # Create model
    model = genai.GenerativeModel(model_name)

    # Analysis prompt
    prompt = [
        "Please analyze this image comprehensively.",
        "Follow this structure:",
        "",
        "## PART 1: OVERALL IMAGE ANALYSIS",
        "",
        "### 1. Technical Quality",
        "- Resolution, clarity, focus, noise, compression artifacts",
        "- Lighting, exposure, contrast, white balance",
        "",
        "### 2. Visual Content Overview",
        "- Main subjects (people, objects, environment)",
        "- Scene description and context",
        "- Actions or implied actions",
        "",
        "### 3. Composition",
        "- Framing, rule of thirds, perspective, depth",
        "- Color palette and visual style",
        "",
        "### 4. Text and Symbols (OCR)",
        "- Any visible text, logos, UI elements",
        "",
        "### 5. Safety and Sensitive Content",
        "- Note any potentially sensitive or unsafe elements",
        "",
        "### 6. Usefulness",
        "- What this image could be used for (e.g., ads, tutorials, social, documentation)",
        "",
        "Provide a clear, professional, and concise analysis.",
        image_file,
    ]

    try:
        # Generate analysis
        response = model.generate_content(prompt, request_options={"timeout": 600})
        result = response.text
        ProjectOrganizer.save(ProjectOrganizer.SaveType.UNDERSTANDINGS, result, f"image_understanding_{Path(image_path).name}.txt")
        print(f"Analysis completed for {Path(image_path).name}")

        # Clean up
        try:
            genai.delete_file(image_file.name)
            print("Cleaned up remote file")
        except Exception:
            pass

        return result

    except Exception as e:
        # Clean up on error
        try:
            genai.delete_file(image_file.name)
        except Exception:
            pass

        error_msg = f"Error analyzing image {Path(image_path).name}: {str(e)}"
        print(error_msg)
        return error_msg
class ImageUnderstander(Tool):
    name: str = "understand_image"
    description: str = "Analyze image content using Gemini and return a detailed understanding."
    parameters: dict = {
        "type": "object",
        "required": ["image_path"],
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Local path to the image file to be analyzed.",
            },
            "model_name": {
                "type": "string",
                "description": "Gemini model name (default: gemini-2.5-pro)",
                "default": "gemini-2.5-pro"
            }
        }
    }

    def execute(self, image_path: str, model_name: str = "gemini-2.5-pro") -> str:
        try:
            return understand_image(image_path=image_path, model_name=model_name)
        except Exception as e:
            return f"❌ Error during image understanding: {e}"
        

class ImageVerifier(Tool):
    name: str = "image_verifier"
    description: str = "Check if the image is valid and meets the requirements."
    parameters: dict = {
        "type": "object",
        "required": ["image_path"],
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Local path to the image file to be analyzed.",
            },
            "model_name": {
                "type": "string",
                "description": "Gemini model name (default: gemini-2.5-pro)",
                "default": "gemini-2.5-pro"
            }
        }
    }

    def execute(self, image_path: str, model_name: str = "gemini-2.5-pro") -> str:
        try:
            return understand_image(image_path=image_path, model_name=model_name)
        except Exception as e:
            return f"❌ Error during image understanding: {e}"



if __name__ == "__main__":
    # Simple example usage
    image_path = "/Users/alexkim/Desktop/Clippie/example/sample.jpg"

    if Path(image_path).exists():
        result = understand_image(image_path)
        print("\n" + "=" * 50)
        print("IMAGE ANALYSIS RESULT:")
        print("=" * 50)
        print(result)
    else:
        print(f"Image file not found: {image_path}")
        print("Please update the image_path variable with an actual image file.")