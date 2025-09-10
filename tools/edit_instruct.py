import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from openai import OpenAI
try:
    from tools.base_tool import Tool
except ModuleNotFoundError:  # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    if str(_repo_root) not in _sys.path:
        _sys.path.append(str(_repo_root))
    from tools.base_tool import Tool

from core.call_llms import call_gemini, call_openai, call_anthropic
load_dotenv()




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

class EditInstructGenerator(Tool):
    name: str = "edit_instruct_generator"
    description: str = "Generate editing instructions based on video understanding and user requirements."
    parameters: dict = {
        "type": "object",
        "required": ["video_understanding_text_path", "user_requirements"],
        "properties": {
            "video_understanding_text_path": {
                "type": "string",
                "description": "Path to the text file containing video understanding.",
            },
            "user_requirements": {
                "type": "string",
                "description": "User's script and structure requirements.",
            },
        },
    }

    def execute(self, video_understanding_text_path: str, user_requirements: str) -> str:
        return generate_edit_instructions(video_understanding_text_path, user_requirements)



if __name__ == "__main__":
    with open("./workdir/understandings/comprehensive_understanding_for_assets.txt", "r") as f:
        video_understanding_text = f.read()
    with open("./new_script.txt", "r") as f:
        user_requirements = f.read()
    generate_edit_instructions(video_understanding_text, user_requirements)