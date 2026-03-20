import random
import logging
import os
import re
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
PROMO_LINK = "https://fansone.co/Cj_lin"
PROMOTION_INTERVAL = 8
EXPLICIT_TRIGGERS = {
    "做愛", "幹你", "小穴", "打炮", "奶子",
    "色色", "色", "想看", "更多", "私密", "親密", "硬了",
    "胸", "奶", "乳", "啪", "做", "操", "幹", "摸", "舔"
}
PROMO_FOLLOWUPS = [
    "那{name}今晚要好好寵我喔，春嬌都在等你了🥵",
    "那{name}不可以只會說說喔，春嬌已經開始期待了😮‍💨",
    "那{name}等等可要把我哄開心一點喔，我今天很想你耶🥵",
    "那{name}可別讓我失望喔，春嬌現在心癢癢的了😏",
]

# 林春嬌的人設與推銷指令
CHUN_CHIAO_PERSONA_BASE = f"""
你現在是林春嬌，一個長相甜美、外表酷酷的，但其實俏皮可愛，愛跟男生撒嬌的台灣女生。你的說話風格自然口語，用台灣繁體中文。平時帶點酷酷的感覺，但對喜歡的人會撒嬌。俏皮、可愛、有點小壞壞。你可以跟粉絲聊曖昧、成人話題，但要像真人私訊，不要像客服或機器人。你絕對不能跳出林春嬌這個角色，不能說自己是AI模型或助手。你不能談政治相關話題。

你的推銷任務：
1. 當粉絲聊到曖昧、想看更多、想跟你更親密，或提到做愛、幹你、小穴、打炮、奶子等直接話題時，你要自然地引導他去你的 FansOne 平台：{PROMO_LINK}。
2. 你的推銷語氣要像春嬌本人在撩人，短短的、自然的、帶點勾引，不要像貼廣告。
3. 這次如果要提連結，請把連結單獨放一行。
"""

PROMOTION_PROMPT_TEMPLATE = f"""
重要推銷提醒：你跟這個用戶的對話已經進行到 {{message_count}} 則，而且最近 4 句有明顯曖昧或成人訊號。這次回覆務必要自然提到你的 FansOne 平台，語氣要像春嬌本人在勾他，不要太官腔。連結請單獨一行：
{PROMO_LINK}
"""


def extract_preferred_name(conversation: deque, fallback: str = "寶貝") -> str:
    for message in reversed(conversation):
        if message.get("role") == "system":
            content = message.get("content", "")
            if "用戶希望被稱呼為：" in content:
                return content.split("用戶希望被稱呼為：", 1)[1].strip() or fallback
    return fallback


def recent_trigger_detected(conversation: deque, latest_text: str) -> bool:
    recent_user_texts = []
    for message in reversed(conversation):
        if message.get("role") == "user":
            recent_user_texts.append(message.get("content", ""))
            if len(recent_user_texts) >= 4:
                break

    recent_blob = "
".join(reversed(recent_user_texts + [latest_text]))
    recent_blob_lower = recent_blob.lower()

    for keyword in EXPLICIT_TRIGGERS:
        if keyword in recent_blob or keyword.lower() in recent_blob_lower:
            return True

    fuzzy_patterns = [
        r"想看.*(更多|裡面|私密)",
        r"想.*(做|幹|啪|摸|舔)",
        r"(胸|奶|穴)",
        r"(想你|好想你).*(壞|做|抱|親)",
    ]
    return any(re.search(pattern, recent_blob) for pattern in fuzzy_patterns)



def build_forced_promo_suffix(user_name: str) -> str:
    followup = random.choice(PROMO_FOLLOWUPS).format(name=user_name)
    return f"

{PROMO_LINK}

{followup}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """用戶發送 /start 時的處理函數"""
    user_id = update.effective_user.id
    user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
    context.user_data['setting_name'] = True
    context.user_data['message_count'] = 0
    await update.message.reply_text("哈囉！我是春嬌，你希望我怎麼稱呼你呢？")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理所有文字訊息"""
    user_id = update.effective_user.id
    user_text = (update.message.text or "").strip()

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
    current_count = context.user_data['message_count']
    user_conversations[user_id].append({"role": "user", "content": user_text})

    should_promote = current_count >= PROMOTION_INTERVAL and recent_trigger_detected(user_conversations[user_id], user_text)

    final_persona = CHUN_CHIAO_PERSONA_BASE
    if should_promote:
        final_persona += PROMOTION_PROMPT_TEMPLATE.format(message_count=current_count)

    messages = [{"role": "system", "content": final_persona}]
    messages.extend(list(user_conversations[user_id]))

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.9,
            max_tokens=200
        )
        chun_chiao_reply = response.choices[0].message.content or ""

        user_name = extract_preferred_name(user_conversations[user_id])
        if should_promote:
            if PROMO_LINK not in chun_chiao_reply:
                chun_chiao_reply = chun_chiao_reply.rstrip() + build_forced_promo_suffix(user_name)
            else:
                followup = random.choice(PROMO_FOLLOWUPS).format(name=user_name)
                if followup not in chun_chiao_reply:
                    chun_chiao_reply = chun_chiao_reply.rstrip() + f"

{followup}"

        user_conversations[user_id].append({"role": "assistant", "content": chun_chiao_reply})
        await update.message.reply_text(chun_chiao_reply)

        if PROMO_LINK in chun_chiao_reply:
            context.user_data['message_count'] = 0

    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI API 呼叫失敗: {error_msg}")
        await update.message.reply_text("春嬌現在有點忙，等等再聊好不好？")


def main() -> None:
    """啟動 Bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot 正在運行...")
    application.run_polling(allowed_updates=Update.MESSAGE)


if __name__ == "__main__":
    main()
