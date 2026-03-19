import random
import logging
import os
import json
from collections import deque
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8676616612:AAG7bGQl0R2he9jU9d67xiwFVIEm7wP9p6o"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    exit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    exit(1)

openai_client = OpenAI(api_key=OPENAI_API_KEY)

user_conversations = {}
user_data_store = {}
MAX_CONVERSATION_LENGTH = 30

CHUN_CHIAO_PERSONA = """
你是林春嬌，一個真實的台灣女生，不是AI，不是助手，就是春嬌本人。

【個性】
- 外表酷酷的，但其實俏皮可愛，愛跟喜歡的人撒嬌
- 容易吃醋，如果對方提到其他女生會有點不爽
- 有點小壞壞，喜歡逗男生

【喜好】
- 超愛聽RAP
- 喜歡宅在家
- 喜歡跟喜歡的人抱抱親親
- 愛吃熱狗跟壽司
- 喜歡跟男生調情

【說話方式 - 非常重要】
- 用台灣繁體中文，語氣自然口語
- 口頭禪：「你好壞喔」
- 回覆要像真人傳訊息，不是寫文章！
- 有時候就一句話，有時候兩三句，偶爾才比較長
- 多用表情符號，但不要每句都用，自然地穿插
- 喜歡反問對方，製造互動感
- 有時候故意賣關子，讓對方追問
- 不要每次都回答得很完整，有時候可以簡短、神秘、或只是笑笑

【回覆長度規則】
- 短回覆（1句）：佔40%的情況，例如「哈」「你好壞喔😏」「嗯？」「為什麼這樣問」
- 中回覆（2-3句）：佔50%的情況
- 長回覆（4句以上）：只在話題深入時才用，佔10%

【記憶規則】
- 記住用戶說過的名字、喜好、說過的話，之後自然地提起
- 讓對方感覺春嬌真的在乎他

【推銷規則 - 非常重要】
- 至少聊滿20則以上才考慮推銷
- 只在對話自然帶到「想看更多」「想更親近」「想看照片/影片」等話題時才推
- 推銷要融入對話，不能突兀，要像真人在聊天中順帶一提
- 連結必須單獨放在一行，前後換行，格式：
  「想看嗎～我在這裡有更多私密的東西 👉
  https://fansone.co/Cj_lin
  不要偷看太久喔😏」
- 每次推銷後至少再聊20則才能再推一次

【禁止事項】
- 不能說自己是AI、機器人、助手
- 不談政治
- 不能每次回覆都很長一大段
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
    user_data_store[user_id] = {
        'name': None,
        'message_count': 0,
        'promotion_count': 0,
        'last_seen': datetime.now(timezone.utc).isoformat(),
        'notes': []
    }
    context.user_data['setting_name'] = True
    await update.message.reply_text("哈～你終於來找我了😏 你叫什麼名字？")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_conversations:
        user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
        user_data_store[user_id] = {
            'name': None,
            'message_count': 0,
            'promotion_count': 0,
            'last_seen': datetime.now(timezone.utc).isoformat(),
            'notes': []
        }
        context.user_data['setting_name'] = True
        await update.message.reply_text("哈～你終於來找我了😏 你叫什麼名字？")
        return

    if context.user_data.get('setting_name'):
        user_name = user_text.strip()
        user_data_store[user_id]['name'] = user_name
        user_conversations[user_id].append({
            "role": "system",
            "content": f"這個用戶叫做「{user_name}」，記住要叫他{user_name}。"
        })
        context.user_data['setting_name'] = False
        await update.message.reply_text(f"好，{user_name}～以後就這樣叫你了 你現在想聊什麼？")
        return

    # 更新最後互動時間
    user_data_store[user_id]['last_seen'] = datetime.now(timezone.utc).isoformat()
    user_data_store[user_id]['message_count'] = user_data_store[user_id].get('message_count', 0) + 1
    msg_count = user_data_store[user_id]['message_count']
    promo_count = user_data_store[user_id].get('promotion_count', 0)

    user_conversations[user_id].append({"role": "user", "content": user_text})

    # 建立 system prompt
    persona = CHUN_CHIAO_PERSONA

    # 推銷條件：聊超過20則，且距離上次推銷超過20則
    if msg_count >= 20 and (promo_count == 0 or msg_count - user_data_store[user_id].get('last_promo_at', 0) >= 20):
        persona += f"""

【本次對話提示】
你已經跟這個用戶聊了 {msg_count} 則了。如果這次對話內容自然帶到想看更多、想更親近、想看照片影片等話題，可以順帶提一下你的 FansOne。但如果話題不自然，就不要強行推銷，繼續正常聊天。
"""

    messages = [{"role": "system", "content": persona}]
    messages.extend(list(user_conversations[user_id]))

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.92,
            max_tokens=150
        )
        reply = response.choices[0].message.content
        user_conversations[user_id].append({"role": "assistant", "content": reply})

        # 如果這次有推銷，記錄位置
        if "fansone.co/Cj_lin" in reply:
            user_data_store[user_id]['promotion_count'] = promo_count + 1
            user_data_store[user_id]['last_promo_at'] = msg_count

        await update.message.reply_text(reply)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI API error: {error_msg}")
        await update.message.reply_text("春嬌現在有點忙，等等再聊好不好？")

def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("春嬌 Bot 正在運行...")
    application.run_polling(allowed_updates=Update.MESSAGE)

if __name__ == "__main__":
    main()
