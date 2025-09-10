from datetime import datetime
from pathlib import Path
from openai import OpenAI
import base64
import os
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
# Load environment variables from .env file
load_dotenv()

class ImageEditor(Tool):
    name: str = "image_editor"
    description: str = (
        "image to image generator, edit current image"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file to edit (PNG format recommended).",
            },
            "prompt": {
                "type": "string",
                "description": "Text description of the desired changes to the image.",
            },
            "mask_path": {
                "type": "string",
                "description": "Optional. Path to a mask image file (PNG with transparency) indicating which areas to edit.",
            },
            "api_key": {
                "type": "string",
                "description": "Optional. OpenAI API key. If not provided, will use OPENAI_API_KEY environment variable.",
            },
        },
        "required": ["image_path", "prompt"],
    }

    def execute(self, **kwargs) -> str:
        image_path = kwargs.get("image_path", "")
        prompt = kwargs.get("prompt", "")
        mask_path = kwargs.get("mask_path")
        api_key = kwargs.get("api_key")
        
        if not image_path:
            return "No image path provided."
        if not prompt:
            return "No prompt provided."
            
        # Validate image file exists
        image_file = Path(image_path)
        if not image_file.exists():
            return f"Image file does not exist: {image_path}"
            
        # Validate mask file if provided
        if mask_path:
            mask_file = Path(mask_path)
            if not mask_file.exists():
                return f"Mask file does not exist: {mask_path}"
        
        try:
            # Initialize OpenAI client
            # Use provided API key or fall back to environment variable
            client = OpenAI(api_key=api_key) if api_key else OpenAI()
            
            # Prepare the edit request
            edit_params = {
                "model": "gpt-image-1",  # Use gpt-image-1 for image editing
                "image": open(image_path, "rb"),
                "prompt": prompt
            }
            
            # Add mask if provided
            if mask_path:
                edit_params["mask"] = open(mask_path, "rb")
            
            # Make the API call
            result = client.images.edit(**edit_params)
            
            # Get the image data (URL or base64)
            if hasattr(result.data[0], 'url') and result.data[0].url:
                # Download from URL
                import requests
                response = requests.get(result.data[0].url)
                if response.status_code == 200:
                    image_bytes = response.content
                else:
                    return f"Error downloading image from URL: {response.status_code}"
            elif hasattr(result.data[0], 'b64_json') and result.data[0].b64_json:
                # Decode base64
                image_base64 = result.data[0].b64_json
                image_bytes = base64.b64decode(image_base64)
            else:
                return "Error: Unable to get image data from API response"
            
            # Save the edited image
            output_path = ProjectOrganizer.save(ProjectOrganizer.SaveType.ASSETS, image_bytes, f"image_editor_{Path(image_path).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                
            # Close file handles
            edit_params["image"].close()
            if mask_path:
                edit_params["mask"].close()
                
            return f"Image successfully edited and saved to: {output_path}"
            
        except Exception as e:
            return f"Error editing image: {str(e)}"


if __name__ == "__main__":
    """
    Test the ImageEditor tool with cat_staring_at_painting.png
    """
    import sys
    from pathlib import Path
    
    print("🎨 ImageEditor Tool Test")
    print("=" * 50)
    
    # Initialize the tool
    editor = ImageEditor()
    
    # Test image path
    input_image = "/Users/alexkim/Desktop/Clippie/S28250723cb5-5A-1.jpeg"
    
    # Check if input file exists
    if not Path(input_image).exists():
        print(f"❌ Input image not found: {input_image}")
        sys.exit(1)
    
    # Test cases
    test_cases = [
        {
            "name": "一个美女穿着这件衣服",
            "prompt": "一个美女模特穿着这件衣服",
            "output": "/Users/alexkim/Desktop/Clippie/temp_image_generation/clothe_test.png"
        }
    ]
    
    # Run tests
    success_count = 0
    org_verification_needed = False
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Prompt: {test_case['prompt']}")
        print(f"Output: {Path(test_case['output']).name}")
        
        try:
            result = editor.execute(
                image_path=input_image,
                prompt=test_case['prompt'],
                output_path=test_case['output']
            )
            
            print(f"Result: {result}")
            
            # Check if organization verification is needed
            if "organization must be verified" in result.lower():
                org_verification_needed = True
                print("⚠️  Organization verification required for gpt-image-1")
                break
            
            # Check if output was created
            if Path(test_case['output']).exists():
                print("✅ Success!")
                success_count += 1
            else:
                print("⚠️  Output file not created")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 30)
    
    print()
    print(f"📊 Results: {success_count}/{len(test_cases)} tests passed")
    
    if org_verification_needed:
        print("🔐 Organization Verification Required")
        print("To use gpt-image-1 model:")
        print("1. Go to: https://platform.openai.com/settings/organization/general")
        print("2. Click on 'Verify Organization'")
        print("3. Wait up to 15 minutes for access to propagate")
        print()
        print("Alternative: Use dall-e-2 model (change model parameter)")
    elif success_count == len(test_cases):
        print("🎉 All tests passed!")
    elif success_count > 0:
        print("⚠️  Some tests passed")
    else:
        print("❌ All tests failed")
        if not os.getenv('OPENAI_API_KEY'):
            print("💡 Tip: Make sure OPENAI_API_KEY is set in your .env file")
