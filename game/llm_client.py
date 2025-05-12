import io
import re
import os
import base64
import logging
import google.genai as genai

from PIL import Image
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

PROMPT_FOLDER_PATH = os.path.join(os.path.dirname(__file__), "prompts")

# --- Helper Functions for Image Data Conversion ---
def image_bytes_to_data_url(image_bytes, mime_type="image/png"):
    """Converts image bytes to a base64 data URL."""
    try:
        base64_encoded_data = base64.b64encode(image_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{base64_encoded_data}"
    except Exception as e:
        logger.error(f"Error converting image bytes to data URL: {e}")
        return None

def data_url_to_image_bytes(data_url):
    """Converts a base64 data URL to image bytes and detects MIME type."""
    try:
        header, encoded_data = data_url.split(',', 1)
        mime_match = re.search(r'data:(image/[a-zA-Z+]+);base64', header)
        if not mime_match:
            logger.error("Invalid data URL header format.")
            return None, None
        
        mime_type = mime_match.group(1)
        image_bytes = base64.b64decode(encoded_data)
        return image_bytes, mime_type
    except Exception as e:
        logger.error(f"Error converting data URL to image bytes: {e}")
        return None, None

class LLMClient:
    def __init__(self):
        # Load environment variables from .env file
        self.current_api_key_index = 0
        self.api_key_list = self._init_api_key()
        if not self.api_key_list or len(self.api_key_list) == 0:
            raise ValueError("API_KEY_X environment variable not set.")
        
        # Read the prompt file
        self.text2text_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_initial_prompt.txt")
        self.text2img_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_drawing_prompt.txt")
        self.img2text_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_guessing_prompt.txt")
        assert os.path.exists(self.text2text_prompt_path), f"Prompt file not found: {self.text2text_prompt_path}"
        assert os.path.exists(self.text2img_prompt_path), f"Prompt file not found: {self.text2img_prompt_path}"
        assert os.path.exists(self.img2text_prompt_path), f"Prompt file not found: {self.img2text_prompt_path}"
        with open(self.text2text_prompt_path, "r") as f:
            self.text2text_prompt = f.read()
        with open(self.text2img_prompt_path, "r") as f:
            self.text2img_prompt = f.read()
        with open(self.img2text_prompt_path, "r") as f:
            self.img2text_prompt = f.read()

        # Setup Safety Settings
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # Initialize the client
        self._init_client()
    
    def _init_api_key(self, max_key_number: int = 5):
        key_list = []
        for i in range(max_key_number):
            key = os.getenv(f"API_KEY{i}")
            if key:
                key_list.append(key)
        return key_list

    def _init_client(self):
        api_key = self.api_key_list[self.current_api_key_index]
        self.client = genai.Client(api_key=api_key)

    def generate_text_from_text(self, prompt_text=None, model_name="gemini-2.0-flash"):
        config = genai.types.GenerateContentConfig(
            safety_settings=self.safety_settings,
            temperature=0.9,
            top_p=0.95,
            top_k=40,
            max_output_tokens=24,
        )
        response = self.client.models.generate_content(
            model=model_name,
            config=config,
            contents=prompt_text if prompt_text else self.text2text_prompt
        )
        return response.text

    def generate_image_bytes_from_text(self, text, model_name="gemini-2.0-flash-preview-image-generation"):
        prompt_text = self.text2img_prompt.replace("{text_description}", text)
        response = self.client.models.generate_content(
            model=model_name,
            contents=prompt_text,
            config=genai.types.GenerateContentConfig(
                safety_settings=self.safety_settings,
                response_modalities=['TEXT', 'IMAGE'],
            )
        )
        image_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
        return image_bytes


    def generate_text_from_image_bytes(self, image_bytes, prompt_text=None, mime_type="image/png", model_name="gemini-2.0-flash"):
        """Generates text from a given image (bytes) and text prompt."""
        image_part = genai.types.from_bytes(
            data=image_bytes,
            mime_type=mime_type,
        )
        config = genai.types.GenerateContentConfig(
            safety_settings=self.safety_settings,
            temperature=0.9,
            top_p=0.95,
            top_k=40,
            max_output_tokens=64,
        )
        response = self.client.models.generate_content(
            model=model_name,
            config=config,
            contents=[
                prompt_text if prompt_text else self.img2text_prompt,
                image_part,
            ]
        )
        return response.text
