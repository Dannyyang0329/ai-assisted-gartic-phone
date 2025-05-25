import io
import re
import os
import base64
import logging
import asyncio
import google.genai as genai

from PIL import Image
from dotenv import load_dotenv
# from googletrans import Translator

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
        # self.text2text_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_initial_prompt.txt")
        # self.text2img_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_drawing_prompt.txt")
        # self.img2text_prompt_path = os.path.join(PROMPT_FOLDER_PATH, "bot_guessing_prompt.txt")
        # assert os.path.exists(self.text2text_prompt_path), f"Prompt file not found: {self.text2text_prompt_path}"
        # assert os.path.exists(self.text2img_prompt_path), f"Prompt file not found: {self.text2img_prompt_path}"
        # assert os.path.exists(self.img2text_prompt_path), f"Prompt file not found: {self.img2text_prompt_path}"
        # with open(self.text2text_prompt_path, "r", encoding='utf-8') as f:
        #     self.text2text_prompt = f.read()
        # with open(self.text2img_prompt_path, "r", encoding='utf-8') as f:
        #     self.text2img_prompt = f.read()
        # with open(self.img2text_prompt_path, "r", encoding='utf-8') as f:
        #     self.img2text_prompt = f.read()

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

    def translate_to_english(self, text, model_name="gemini-1.5-flash"):
        config = genai.types.GenerateContentConfig(
            system_instruction=(
                "You're a professional translator. Your task is to translate the given text into English.\n"
                "Please translate the following text into English. The text is in Traditional Chinese.\n"
            ),
            safety_settings=self.safety_settings,
            temperature=0.2,
            max_output_tokens=24,
        )
        response = self.client.models.generate_content(
            model=model_name,
            config=config,
            contents="Please translate the following text into English:\n" + text
        )
        return response.text
    # def translate_to_english(self, text):
    #     translator = Translator()
    #     translated = translator.translate(text, dest='en')
    #     return translated.text

    def generate_text_from_text(self, prompt_text="請產生一個創意繪畫題目", model_name="gemini-2.0-flash"):
        config = genai.types.GenerateContentConfig(
            system_instruction=(
                "你是一位創意繪畫題目的設計師，擅長結合物品、想像力、卡通概念，發想出具有趣味、畫面感的主題。\n"
                "請盡力避免每次輸出都與前次或常見的主題相似，發想出獨特且令人驚豔的題目。"
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
            contents=(
                "In this game similar to Gartic Phone, it's your turn to come up with a drawing prompt.\n"
                "You need to think of a short and fun drawing topic that the next player can illustrate.\n"
                "Please come up with a prompt that is unexpected and creative, yet concise — something that challenges the player to think. The prompt should be like a visual brain teaser, or a combination of two unrelated things.\n"
                "The following topics are overused and should not be repeated:\n"
                "熱氣球、雲朵、星星、貓、狗、鯨魚、章魚、恐龍、仙人掌、企鵝、珍珠耳環、在月球上、跳芭蕾舞、火箭升空、戴假髮、戴墨鏡、穿西裝、吃滷肉飯、外星人、太空人。\n"
                "You're encouraged to include elements with semantic contradiction or strong visual contrast, to make the scene more challenging and interesting.\n"
                "This prompt must be completely different from the one you just generated. Please approach it from a brand new perspective.\n"
                "Choose elements from different domains (for example: office, spaceship, school campus, kitchen, sports field, battlefield, dream world, etc.).\n"
                "Please imagine that you are a different person each time you come up with a prompt (for example: an elementary school student, an engineer, a chef, a Martian, etc.).\n"
                "Please make sure the prompt is written in Traditional Chinese and is no more than 20 characters long.\n"
                "The following are some examples:\n"
                "老奶奶在開跑車,\n"
                "演唱會,\n"
                "海灘衝浪,\n"
                "一台超大冰箱,\n"
                "機器人在煮拉麵,\n"
                "雨中的紙飛機,\n"
                "車水馬龍的紐約市,\n"
                "壞掉的電視機,\n"
                "口渴的小明在跑馬拉松,\n"
                "Your prompt:"
            )
        )
        return response.text

    def generate_image_bytes_from_text(self, text, model_name="gemini-2.0-flash-preview-image-generation"):
        # prompt_text = self.text2img_prompt.replace("{text_description}", text)
        text = self.translate_to_english(text)
        print("Translated text:", text)
        response = self.client.models.generate_content(
            model=model_name,
            contents=(
                "You are an AI drawing robot, specializing in creating images based on user descriptions.\n"
                "The style of images you generate should look like they were drawn by a human in a short amount of time using simple drawing tools (e.g., MS Paint). The style should be simple, cute, childlike, or pixelated.\n"
                "Please avoid generating images that are overly realistic, intricate, or highly detailed, and ensure the content faithfully represents the user's description.\n"
                "Important: Never include prompt text or logos in the images.\n"
                "Here you will receive a description of an image. Your task is to create an image based on this description. \n"
                "The prompt will be written in Chinese, and you should first convert it to English, then draw the image by the English prompt.\n"
                "Please draw an image based on the following description, in a simple, cute style, like a child drew it with MS Paint:"
                f"{text}"
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
                # (
                #     "你是一個 AI 評論員。你的任務是根據提供的圖片，用一句繁體中文來描述它。你的描述需要盡可能幽默風趣，讓人會心一笑。\n"
                #     "請針對以下圖片，給出你的幽默描述：\n",
                # ),
                (
                    "你是一個你畫我猜的玩家，你的任務是猜提供的圖片原本的敘述。你的描述需要盡可能幽默風趣，讓人會心一笑。\n"
                    "請用繁體中文回答，並用15字以內的一句話來描述圖片。請注意你的敘述不能是太抽象的句子，而是一個具體的事物。範例：「睡覺的貓咪」、「一片森林」\n"
                    "請針對以下圖片，給出你的猜測答案：\n",
                ),
                image_part,
            ]
        )
        return response.text

    def generate_image_from_image(self, image_bytes, prompt_text=None, mime_type="image/png", model_name="gemini-2.0-flash-preview-image-generation"):
        image = Image.open(io.BytesIO(image_bytes))

        translated_text = self.translate_to_english(prompt_text)
        processed_text = f"{translated_text}. Keep the same minimal line doodle style."
        response = self.client.models.generate_content(
            model=model_name,
            contents=[image, processed_text],
            config=genai.types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
            )
        )

        image_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
        return image_bytes