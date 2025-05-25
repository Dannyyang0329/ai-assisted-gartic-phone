# ArtFlow - AI 繪畫接龍遊戲 🎨

<div align="center">
  <img src="https://img.shields.io/badge/Django-4.2+-brightgreen.svg" alt="Django">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/AI-Google%20Gemini-orange.svg" alt="AI">
  <img src="https://img.shields.io/badge/WebSocket-支援-lightgrey.svg" alt="WebSocket">
</div>

ArtFlow 是一款創新的線上多人 AI 輔助繪畫接龍遊戲，結合了人類創意與 AI 技術的完美融合。玩家們可以透過網路即時協作，輪流進行題目創作、繪畫、猜測等環節，創造出充滿驚喜和趣味的故事集。無論您是繪畫高手還是初學者，AI 都能協助您完成精彩的作品！

## ✨ 主要特色

### 🎮 遊戲核心功能
- **多人即時對戰**：支援多位玩家同時在線，透過 WebSocket 實現即時同步
- **AI 智能輔助**：
  - 🤖 AI 自動生成創意繪畫題目
  - 🎨 AI 根據文字描述生成畫作
  - 🔍 AI 智能猜測畫作內容
- **接力創作模式**：題目→繪畫→猜測→繪畫的循環，創造獨特故事本
- **AI 機器人玩家**：可添加 AI 機器人參與遊戲，確保遊戲流暢進行

### 🎨 強大的繪圖工具
- **多種繪圖工具**：筆刷、橡皮擦、填色桶、線條、矩形、圓形
- **色彩系統**：調色盤 + 自訂顏色選擇器
- **筆刷設定**：可調整線條粗細
- **撤銷/重做**：支援多步驟操作回復
- **清除畫布**：一鍵清空重新開始

### 🏠 完整的房間系統
- **等待室功能**：
  - 建立或加入遊戲房間
  - 邀請好友加入（分享房間連結）
  - 新增/移除 AI 機器人玩家
  - 房主控制遊戲開始
- **即時聊天**：房間內文字聊天功能
- **玩家管理**：即時顯示玩家狀態和進度

### 📱 現代化使用者體驗
- **響應式設計**：支援桌機、平板、手機等各種螢幕尺寸
- **美觀動畫效果**：使用 GSAP 和 CSS 動畫提升視覺體驗
- **直觀操作介面**：簡潔友善的使用者界面
- **即時狀態更新**：遊戲進度、玩家狀態即時同步

## 🛠️ 技術架構

### 後端技術棧
- **Web 框架**：Django 4.2+
- **即時通訊**：Django Channels (WebSocket)
- **AI 整合**：Google Gemini API
- **資料庫**：SQLite（可擴展至 PostgreSQL/MySQL）
- **翻譯服務**：Google 翻譯 API

### 前端技術棧
- **核心技術**：HTML5, CSS3, JavaScript (ES6+)
- **動畫庫**：
  - GSAP (GreenSock Animation Platform) - 高級動畫效果
  - Animate.css - CSS 動畫
- **畫布繪圖**：HTML5 Canvas API
- **字體**：Google Fonts (Noto Sans TC, Poppins)

### AI 模型服務
- **Google Gemini 2.0 Flash**：文字生成、圖像生成
- **Google Gemini 1.5 Flash**：文字翻譯、圖像理解

## 🚀 安裝與部署

### 環境需求
- Python 3.8 或以上版本
- Node.js（如需前端構建工具）
- Google Gemini API 金鑰

### 1. 複製專案
```bash
git clone <repository_url>
cd ArtFlow
```

### 2. 建立虛擬環境
```bash
# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 安裝依賴套件
```bash
pip install -r requirements.txt
```

**主要依賴套件：**
```
Django>=4.2.0
django-channels>=4.0.0
google-generativeai>=0.3.0
Pillow>=10.0.0
python-dotenv>=1.0.0
```

### 4. 環境變數設定
在專案根目錄建立 `.env` 檔案：

```env
# Google Gemini API 金鑰（支援多組金鑰輪替）
API_KEY0=your_gemini_api_key_1
API_KEY1=your_gemini_api_key_2
API_KEY2=your_gemini_api_key_3
API_KEY3=your_gemini_api_key_4
API_KEY4=your_gemini_api_key_5

# Django 密鑰
SECRET_KEY=your_django_secret_key

# 除錯模式（生產環境請設為 False）
DEBUG=True

# 允許的主機
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 5. 資料庫初始化
```bash
# 建立資料庫遷移檔案
python manage.py makemigrations

# 執行資料庫遷移
python manage.py migrate

# 建立超級使用者（可選）
python manage.py createsuperuser
```

### 6. 啟動開發伺服器
```bash
python manage.py runserver
```

成功啟動後，請在瀏覽器開啟：`http://127.0.0.1:8000/`

## 🎮 遊戲玩法指南

### 第一步：進入大廳
1. 在首頁輸入您的使用者 ID（暱稱）
2. 選擇：
   - **建立新房間**：輸入房間名稱建立新遊戲
   - **加入現有房間**：輸入現有房間名稱加入遊戲

### 第二步：等待室準備
1. **邀請好友**：複製房間連結分享給朋友
2. **調整設定**：
   - 新增 AI 機器人玩家（建議 2-6 名玩家）
   - 移除不需要的 AI 機器人
3. **開始遊戲**：房主點擊「開始遊戲」按鈕

### 第三步：遊戲流程

#### 🎯 出題階段（第一輪）
- 每位玩家輪流提出創意繪畫題目
- AI 也會自動生成有趣的題目
- 題目範例：「在太空中吃火鍋的企鵝」

#### 🎨 繪畫階段
- 根據上一位玩家的題目進行繪畫
- 使用提供的繪圖工具創作
- **AI 輔助功能**：每位玩家有限次數的 AI 繪畫輔助
- 完成後提交作品

#### 🔍 猜測階段
- 觀看上一位玩家的畫作
- 猜測畫作想要表達的內容
- AI 也會參與猜測，增加趣味性

#### 🔄 循環進行
- 繪畫→猜測→繪畫，持續數個回合
- 每個玩家的題目都會形成一條故事線

### 第四步：結果欣賞
1. **故事本展示**：查看每條故事線的完整發展
2. **翻頁瀏覽**：房主可控制故事本翻頁
3. **同步觀看**：所有玩家同步觀看結果

## 🎨 繪圖工具使用說明

### 基本工具
- **✏️ 筆刷**：自由繪製線條和圖案
- **🧽 橡皮擦**：擦除不需要的部分
- **🪣 填色桶**：大面積填充顏色
- **📏 線條工具**：繪製直線
- **⬜ 矩形工具**：繪製矩形和正方形
- **⭕ 圓形工具**：繪製圓形和橢圓

### 進階功能
- **🎨 調色盤**：10 種預設顏色快速選擇
- **🌈 自訂顏色**：色彩選擇器自由調色
- **📏 筆刷粗細**：滑桿調整線條寬度
- **↶ 撤銷/重做**：支援多步驟操作
- **🗑️ 清除畫布**：一鍵清空重新開始

### AI 輔助繪畫
- 每位玩家有限次數的 AI 輔助（通常 2-3 次）
- 輸入詳細描述，AI 會生成對應圖像
- 可在 AI 生成的基礎上繼續手動編輯

## 📁 專案結構

```
ArtFlow/
├── 📁 game/                           # Django 主應用
│   ├── 📁 migrations/                 # 資料庫遷移檔案
│   ├── 📁 static/                     # 靜態檔案
│   │   ├── 📁 css/                    # 樣式表
│   │   │   ├── style.css              # 主要樣式
│   │   │   ├── room.css               # 遊戲房間樣式
│   │   │   ├── waiting_room.css       # 等待室樣式
│   │   │   └── decorations.css        # 裝飾元素樣式
│   │   └── 📁 js/                     # JavaScript 檔案
│   │       ├── script.js              # 首頁邏輯
│   │       ├── room_game.js           # 遊戲房間邏輯
│   │       └── waiting_room.js        # 等待室邏輯
│   ├── 📁 templates/                  # HTML 模板
│   │   ├── 📁 game/                   # 遊戲相關模板
│   │   │   ├── index.html             # 首頁
│   │   │   ├── room.html              # 遊戲房間
│   │   │   └── waiting_room.html      # 等待室
│   │   └── 📁 registration/           # 註冊相關模板
│   │       └── register.html          # 使用者註冊
│   ├── 📄 llm_client.py               # AI 模型客戶端
│   ├── 📄 consumers.py                # WebSocket 處理器
│   ├── 📄 models.py                   # 資料庫模型
│   ├── 📄 views.py                    # 視圖處理器
│   └── 📄 urls.py                     # URL 路由
├── 📁 ArtFlow/                        # Django 專案設定
│   ├── 📄 settings.py                 # 專案設定
│   ├── 📄 urls.py                     # 主要 URL 路由
│   ├── 📄 wsgi.py                     # WSGI 伺服器
│   └── 📄 asgi.py                     # ASGI 伺服器（WebSocket）
├── 📄 manage.py                       # Django 管理腳本
├── 📄 requirements.txt                # 依賴套件清單
├── 📄 .env                            # 環境變數（需自建）
└── 📄 README.md                       # 專案說明文件
```

## 🔧 進階設定

### WebSocket 設定
確保 `settings.py` 中 ASGI 應用程式已正確設定：

```python
ASGI_APPLICATION = 'ArtFlow.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}
```

### 資料庫配置（生產環境）
```python
# PostgreSQL 範例
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'artflow_db',
        'USER': 'your_db_user',
        'PASSWORD': 'your_db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### AI 模型設定
LLMClient 支援多組 API 金鑰輪替使用，提高系統穩定性：

```python
# 在 .env 檔案中設定
API_KEY0=key1
API_KEY1=key2
API_KEY2=key3
```

## 🐛 故障排除

### 常見問題

**1. WebSocket 連線失敗**
```bash
# 檢查 Django Channels 是否正確安裝
pip install channels

# 確認 ASGI 設定正確
python manage.py runserver
```

**2. AI 圖像生成失敗**
- 檢查 Google Gemini API 金鑰是否有效
- 確認網路連線正常
- 查看 API 配額是否足夠

**3. 靜態檔案載入問題**
```bash
# 收集靜態檔案
python manage.py collectstatic
```

**4. 資料庫遷移錯誤**
```bash
# 重置遷移
python manage.py migrate --fake-initial
```

### 日誌除錯
在 `settings.py` 中啟用詳細日誌：

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'debug.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

## 🚀 部署指南

### 生產環境部署

**1. 環境變數設定**
```env
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

**2. 靜態檔案設定**
```python
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
```

**3. 使用 Gunicorn + Nginx**
```bash
# 安裝 Gunicorn
pip install gunicorn

# 啟動服務
gunicorn ArtFlow.asgi:application -k uvicorn.workers.UvicornWorker
```

## 🤝 貢獻指南

我們歡迎社群貢獻！請按照以下步驟：

1. **Fork** 此專案
2. 建立您的功能分支：`git checkout -b feature/AmazingFeature`
3. 提交您的更改：`git commit -m 'Add some AmazingFeature'`
4. 推送到分支：`git push origin feature/AmazingFeature`
5. 開啟一個 **Pull Request**

### 開發規範
- 遵循 PEP 8 Python 程式碼風格
- 新功能請附上單元測試
- 提交訊息請使用繁體中文
- 重大更改請先開 Issue 討論

## 📝 更新日誌

### v1.0.0 (2024-12)
- ✨ 初始版本發布
- 🎮 完整的多人遊戲系統
- 🤖 AI 輔助繪畫功能
- 📱 響應式設計支援
- 🔄 即時 WebSocket 通訊

### 未來計劃
- 🎨 更多繪圖工具和濾鏡
- 🏆 積分和排行榜系統
- 📷 作品匯出和分享功能
- 🌐 多語言支援
- 🎵 背景音樂和音效
- 📊 遊戲統計和分析

## 📄 授權條款

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案。

## 👥 開發團隊

- **專案維護者**：[您的名字]
- **AI 整合**：Google Gemini API
- **前端設計**：現代化響應式設計
- **後端架構**：Django + Channels

## 🙏 致謝

- 感謝 Google 提供強大的 Gemini AI API
- 感謝 Django 和 Channels 社群
- 感謝所有測試玩家的寶貴意見
- 特別感謝開源社群的無私貢獻

---

<div align="center">
  <p>🎨 讓創意自由流動，與 AI 共創美好 🤖</p>
  <p>如有任何問題，歡迎開啟 Issue 或聯繫開發團隊！</p>
</div>
