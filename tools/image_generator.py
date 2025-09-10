
from pathlib import Path
from openai import OpenAI
import base64
import os
from datetime import datetime
from typing import List
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


class ImageGenerator(Tool):
    name: str = "image_generator"
    description: str = "text to image generator"
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text prompt describing the image to generate.",
            },
            "size": {
                "type": "string",
                "description": "Image size, e.g., 1024x1024, 512x512.",
            },
            "n": {
                "type": "integer",
                "description": "Number of images to generate (1-4).",
            },
            "api_key": {
                "type": "string",
                "description": "Optional. OpenAI API key. If not provided, will use OPENAI_API_KEY environment variable.",
            },
            "model": {
                "type": "string",
                "description": "Model for image generation. Defaults to gpt-image-1.",
            },
        },
        "required": ["prompt"],
    }

    def execute(self, **kwargs) -> str:
        prompt: str = kwargs.get("prompt", "").strip()
        size: str = (kwargs.get("size") or "1024x1024").strip()
        n: int = int(kwargs.get("n") or 1)
        api_key: str | None = kwargs.get("api_key")
        model: str = (kwargs.get("model") or "gpt-image-1").strip()

        if not prompt:
            return "No prompt provided."
        if n < 1:
            n = 1
        if n > 4:
            n = 4

        try:
            client = OpenAI(api_key=api_key) if api_key else OpenAI()
            result = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                n=n,
            )

            saved_files: List[str] = []
            for idx, data_item in enumerate(result.data, start=1):
                image_bytes: bytes | None = None
                if hasattr(data_item, "url") and data_item.url:
                    import requests
                    resp = requests.get(data_item.url)
                    if resp.status_code == 200:
                        image_bytes = resp.content
                    else:
                        continue
                elif hasattr(data_item, "b64_json") and data_item.b64_json:
                    image_bytes = base64.b64decode(data_item.b64_json)
                else:
                    continue

                suffix = f"_{idx}" if n > 1 else ""
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = ProjectOrganizer.save(ProjectOrganizer.SaveType.ASSETS, image_bytes, f"image_generator_{suffix}_{timestamp}.png")
                saved_files.append(str(file_path))

            if not saved_files:
                return "Error: No image data returned from API"

            if len(saved_files) == 1:
                return f"Image generated and saved to: {saved_files[0]}"
            return "Images generated and saved to: " + ", ".join(saved_files)

        except Exception as e:
            return f"Error generating image: {str(e)}"


if __name__ == "__main__":
    print("🖼️  ImageGenerator Tool Test")
    print("=" * 50)
    gen = ImageGenerator()
    out = gen.execute(
        prompt=(
            "A fluffy orange and white long-haired cat standing on hind legs, wearing a"
            " tiny bow tie, photorealistic, studio lighting"
        ),
        output_path=str(Path("temp_image_generation") / "cat_with_bowtie.png"),
        size="1024x1024",
        n=1,
    )
    print(out)
