import os
from openai import OpenAI
from google import genai
import anthropic

def call_anthropic(prompt: str, model="claude-sonnet-4-20250514") -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.completions.create(
        model=model,
        prompt=f"{anthropic.HUMAN_PROMPT} {prompt}{anthropic.AI_PROMPT}",
        max_tokens=1000,
        temperature=0.7,
        top_p=1,
        stop_sequences=[anthropic.HUMAN_PROMPT],
    )
    return response.completion


def call_openai(prompt: str, model="gpt-5") -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def call_gemini(prompt: str, model="gemini-2.5-pro") -> str:
    """
    Function that wraps Gemini 2.5 Flash API call
    Uses the google.genai client approach
    
    Args:
        prompt: Text prompt to send to the model
        
    Returns:
        Generated text response
    """
    try:
        # The client gets the API key from the environment variable `GEMINI_API_KEY`.
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        response = client.models.generate_content(
            model=model, contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error calling Gemini Flash: {str(e)}"