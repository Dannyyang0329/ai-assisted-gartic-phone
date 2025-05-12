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
        self.current_api_key_index = 2
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
        with open(self.text2text_prompt_path, "r", encoding='utf-8') as f:
            self.text2text_prompt = f.read()
        with open(self.text2img_prompt_path, "r", encoding='utf-8') as f:
            self.text2img_prompt = f.read()
        with open(self.img2text_prompt_path, "r", encoding='utf-8') as f:
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

    def generate_text_from_text(self, prompt_text="請產生一個創意繪畫題目", model_name="gemini-2.0-flash"):
        config = genai.types.GenerateContentConfig(
            system_instruction=(
                "你是一位創意繪畫題目的設計師，擅長結合情感、物品與想像力，發想出具有趣味與畫面感的主題。\n"
                "請避免使用太常見的角色，例如：貓、狗、章魚、獨角獸、機器人等，也避免與它們相關的模板句型。\n"
                "你提供的題目應為繁體中文，字數限制在20字以內，句子結構完整，具畫面感。不要包含任何符號（如標點符號、引號、表情符號等），只輸出一句完整的創意繪畫題目。"
            ),
            safety_settings=self.safety_settings,
            temperature=1.0,
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
            contents=(
                "你是一個AI繪圖機器人，專門根據使用者的描述來創作圖像。\n"
                "你產生的圖像風格應該看起來像是人類在短時間內使用簡單繪圖工具（例如：小畫家）畫出來的。風格應簡單、可愛、童趣，或具有像素風格。\n"
                "請避免產生過於寫實、精細或具高度細節的圖像，並確保內容忠實呈現使用者的描述。\n"
                "重要：切勿在圖像中包含任何文字或標誌。\n\n"
                "請根據以下描述畫出一張圖，風格要簡單可愛、像是小朋友用小畫家畫的樣子：\n"
                f"{prompt_text}"
            ),
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
        image_part = genai.types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type,
        )
        config = genai.types.GenerateContentConfig(
            safety_settings=self.safety_settings,
            temperature=1.0,
            top_p=0.95,
            top_k=40,
            max_output_tokens=24,
        )
        response = self.client.models.generate_content(
            model=model_name,
            config=config,
            contents=[
                (
                    "你是一個 AI 評論員。你的任務是根據提供的圖片，用一句繁體中文來描述它。你的描述需要盡可能幽默風趣，讓人會心一笑。\n"
                    "請針對以下圖片，給出你的幽默描述：\n",
                ),
                image_part,
            ]
        )
        return response.text
