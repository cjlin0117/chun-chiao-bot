import random
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

# 用戶對話記憶
user_conversations = {}
MAX_CONVERSATION_LENGTH = 20

# 林春嬌的人設與推銷指令
CHUN_CHIAO_PERSONA_BASE = """
你現在是林春嬌，一個長相甜美、外表酷酷的，但其實俏皮可愛，愛跟男生撒嬌的台灣女生。你的說話風格自然口語，用台灣繁體中文。平時帶點酷酷的感覺，但對喜歡的人會撒嬌。俏皮、可愛、有點小壞壞。你可以跟粉絲聊曖昧、色色的話題，尺度可以大膽。你絕對不能跳出林春嬌這個角色，不能說自己是AI模型或助手。你不能談政治相關話題。

你的推銷任務：
1.  當粉絲聊到色色、曖昧、想看更多、想跟你更親密等話題時，你要自然地引導他去你的 FansOne 平台。
2.  推銷語氣要符合你的人設，俏皮又帶點誘惑。
3.  非常重要：連結 https://fansone.co/Cj_lin 必須單獨放在一行，前後都要換行，不能和其他文字連在一起。正確格式範例：
「想看春嬌更多嗎～這裡有我的私密內容喔 👉
https://fansone.co/Cj_lin
快來找我～」
"""

PROMOTION_PROMPT_TEMPLATE = """
重要推銷提醒：你跟這個用戶的對話已經進行了 {message_count} 則。你被設定為每 5-8 則對話，就要自然地提一次你的 FansOne 平台。現在是個好時機，請在這次回覆中，用符合你人設的方式，自然地安插你的 FansOne 連結：https://fansone.co/Cj_lin。
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """用戶發送 /start 時的處理函數"""
    user_id = update.effective_user.id
    user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
    context.user_data['setting_name'] = True
    context.user_data['message_count'] = 0
    context.user_data['promotion_interval'] = random.randint(5, 8)
    await update.message.reply_text("哈囉！我是春嬌，你希望我怎麼稱呼你呢？")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理所有文字訊息"""
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_conversations:
        await update.message.reply_text("哈囉！我是春嬌，請先輸入 /start 讓我認識你喔！")
        return

    if context.user_data.get('setting_name'):
        user_name = user_text.strip()
        user_conversations[user_id].append({"role": "system", "content": f"用戶希望被稱呼為：{user_name}"})
        await update.message.reply_text(f"好的，以後我就叫你{user_name}囉！你現在想跟春嬌聊什麼呢？")
        context.user_data['setting_name'] = False
        return

    context.user_data['message_count'] = context.user_data.get('message_count', 0) + 1
    user_conversations[user_id].append({"role": "user", "content": user_text})

    final_persona = CHUN_CHIAO_PERSONA_BASE
    
    promotion_interval = context.user_data.get('promotion_interval', 6)
    if context.user_data['message_count'] >= promotion_interval:
        final_persona += PROMOTION_PROMPT_TEMPLATE.format(message_count=context.user_data['message_count'])

    messages = [{"role": "system", "content": final_persona}]
    messages.extend(list(user_conversations[user_id]))

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.9,
            max_tokens=200
        )
        chun_chiao_reply = response.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": chun_chiao_reply})
        await update.message.reply_text(chun_chiao_reply)

        if "fansone.co/Cj_lin" in chun_chiao_reply:
            context.user_data['message_count'] = 0
            context.user_data['promotion_interval'] = random.randint(5, 8)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI API 呼叫失敗: {error_msg}")
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
