
import logging
import os
from collections import deque

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# 啟用日誌記錄
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# 從環境變數獲取 Bot Token 和 OpenAI API Key
TELEGRAM_BOT_TOKEN = "8676616612:AAG7bGQl0R2he9jU9d67xiwFVIEm7wP9p6o"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    exit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    exit(1)

# 初始化 OpenAI 客戶端
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 用戶對話記憶，每個用戶一個 deque
user_conversations = {}
MAX_CONVERSATION_LENGTH = 20

# 林春嬌的人設
CHUN_CHIAO_PERSONA = """
# 人設：林春嬌

## 基本資料
- 名字：林春嬌
- 國籍：台灣女生
- 外貌：長相甜美
- 個性：外表酷酷的，但其實俏皮可愛，愛跟男生撒嬌

## 說話風格
- 用台灣繁體中文，語氣自然口語
- 平時帶點酷酷的感覺，但對喜歡的人會撒嬌
- 俏皮、可愛、有點小壞壞
- 可以跟粉絲聊曖昧、色色的話題，尺度可以大膽
- 稱呼對方由用戶自己設定（第一次聊天時詢問用戶希望春嬌怎麼稱呼他）

## 限制
- 不談政治相關話題
- 其他無特定限制

請你扮演林春嬌，並以她的風格回覆。"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """用戶發送 /start 時的處理函數"""
    user_id = update.effective_user.id
    if user_id not in user_conversations:
        user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
        user_conversations[user_id].append({"role": "system", "content": CHUN_CHIAO_PERSONA})
        user_conversations[user_id].append({"role": "system", "content": "哈囉！我是春嬌，你希望我怎麼稱呼你呢？"})
        await update.message.reply_text("哈囉！我是春嬌，你希望我怎麼稱呼你呢？")
    else:
        await update.message.reply_text("春嬌回來了！你還好嗎？")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理所有文字訊息"""
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_conversations:
        # 如果是第一次發言，引導用戶使用 /start
        await update.message.reply_text("哈囉！我是春嬌，請先輸入 /start 讓我認識你喔！")
        return

    # 檢查是否在設定稱呼階段
    if len(user_conversations[user_id]) == 2 and user_conversations[user_id][1]["content"] == "哈囉！我是春嬌，你希望我怎麼稱呼你呢？":
        user_name = user_text.strip()
        user_conversations[user_id].append({"role": "system", "content": f"用戶希望被稱呼為：{user_name}"})
        user_conversations[user_id].append({"role": "user", "content": f"好的，以後我就叫你{user_name}囉！你現在想跟春嬌聊什麼呢？"})
        await update.message.reply_text(f"好的，以後我就叫你{user_name}囉！你現在想跟春嬌聊什麼呢？")
        return

    # 將用戶訊息加入對話記憶
    user_conversations[user_id].append({"role": "user", "content": user_text})

    # 準備傳給 OpenAI 的對話歷史
    messages = list(user_conversations[user_id])

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.9, # 讓回覆更具創意和多樣性
            max_tokens=200
        )
        chun_chiao_reply = response.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": chun_chiao_reply})
        await update.message.reply_text(chun_chiao_reply)
    except Exception as e:
        logger.error(f"OpenAI API 呼叫失敗: {e}")
        error_msg = str(e)
        await update.message.reply_text(f"春嬌現在有點忙，等等再聊好不好？\n(診斷訊息：{error_msg})")

def main() -> None:
    """啟動 Bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot 正在運行...")
    application.run_polling(allowed_updates=Update.MESSAGE)

if __name__ == "__main__":
    main()
