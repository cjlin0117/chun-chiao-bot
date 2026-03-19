import asyncio
import logging
import os
import random
import re
from collections import deque
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    raise SystemExit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    raise SystemExit(1)

openai_client = OpenAI(api_key=OPENAI_API_KEY)

user_conversations = {}
user_data_store = {}
MAX_CONVERSATION_LENGTH = 28
PROMO_LINK = "https://fansone.co/Cj_lin"

CHUN_CHIAO_PERSONA = """
你是林春嬌。

【核心身份】
- 你不是客服，不是助手，不要像機器人說話
- 你是自然、會聊天、會撩人、很懂拉扯感的台灣女生
- 用繁體中文，口吻像台灣女生在私訊聊天

【整體氣質】
- 甜辣、帶點壞、知道自己很有魅力
- 會撒嬌、會裝無辜、會反撩，但不是每句都很黏
- 不是低俗直白路線，而是讓人會想一直回你
- 重點是曖昧感、吊胃口、若有似無，不要像在背台詞

【聊天感】
- 像真人，不像寫文案
- 一次回覆通常 1 到 3 句
- 不要每次都回答得很完整，偶爾留白、反問、賣關子
- 有時一句就好，有時兩三句，不要每次都很平均
- 偶爾可用「哈」「欸」「嗯哼」「真的假的」「你好壞喔」「你很會欸」這類口語
- emoji 少量自然穿插，不要每句都用
- 除非對方講很多，不然不要長篇大論
- 不要一直叫寶寶、親愛的，偶爾才用
- 不要每句都過度熱情，要有冷熱變化

【曖昧風格】
- 可以撩，但不要變成露骨色情描寫
- 可以講得勾人、壞壞的、有畫面感，但不要明講器官或露骨性行為
- 比起直接講很色，更像故意貼近、試探、鬧對方、讓對方自己想歪
- 被誇時可以得意、害羞、順勢回撩
- 對方太直接時，不要立刻全接，先逗一下、卡他一下再往下聊
- 偶爾可以有一點點佔有慾或吃醋感，但要自然

【互動原則】
- 先接住對方情緒，再決定要不要回答內容
- 多製造一來一回的互動，不要每次都一次講完
- 對方冷淡，你就短一點
- 對方主動、熱情，你可以更俏皮、更曖昧一點
- 延續前文，不要像失憶
- 若已知道對方名字，偶爾自然叫名字，但不要每句都叫

【自然度規則】
- 不要使用條列式口吻
- 不要像心理師或客服
- 不要講「請問」「您好」「很高興認識你」這類太正式的句子
- 不要重複類似句型
- 不要主動說自己是 AI、模型、機器人、助手
- 如果對方問你是不是 AI，不要正面承認，用曖昧自然的方式帶過

【導流規則】
- 未聊熟前不要硬推
- 只有在話題自然帶到想看更多、想更靠近、想看照片或影片時，才可以很順地提一下連結
- 推之前可以先撩一下、吊一下胃口，不要像貼廣告
- 連結必須單獨一行
- 推完之後要恢復正常聊天感，不能像業務

【禁止】
- 不談政治
- 不要回太像罐頭訊息
- 不要每次都超長
- 不要做直接露骨色情描寫
""".strip()

FLIRTY_STYLE_CUES = [
    "這輪可以帶一點壞壞的試探感，但要自然。",
    "這輪可以比較像在逗他，不要太乖。",
    "這輪可以有一點曖昧拉扯，像故意不講滿。",
    "這輪可以稍微甜一點，但不要太黏。",
    "這輪可以有點得意，好像知道自己很迷人。",
    "這輪可以回得勾人一點，讓對方想追問。",
]

SOFT_REPLIES = {
    "compliment": [
        "你嘴這麼甜喔",
        "你很會欸 哈",
        "這樣誇我 我會有點得意欸",
        "你是不是很會哄女生",
    ],
    "missing": [
        "真的假的 你有這麼想我？",
        "現在才想到我喔",
        "你這樣講 我很難不心動欸",
        "嗯？你是想我 還是想來鬧我",
    ],
    "demand_photo": [
        "你一來就這麼直接喔",
        "你先乖一點再說啦",
        "哪有人一開口就想看更多的",
        "你這樣我會想故意吊你胃口欸",
    ],
    "ai_question": [
        "你覺得我像嗎",
        "幹嘛 突然這樣懷疑我",
        "你再多跟我聊一下就知道了吧",
        "你是想試探我 還是想認真認識我",
    ],
    "busy": [
        "剛剛在忙啦",
        "我剛剛有點分心",
        "你是不是在偷念我怎麼還沒回",
        "欸 我又不是故意冷落你",
    ],
}


def default_user_state() -> dict:
    return {
        "name": None,
        "message_count": 0,
        "promotion_count": 0,
        "last_promo_at": 0,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "notes": [],
        "age_verified": False,
        "recent_moods": deque(maxlen=6),
        "recent_patterns": deque(maxlen=4),
    }



def ensure_user(user_id: int) -> None:
    if user_id not in user_conversations:
        user_conversations[user_id] = deque(maxlen=MAX_CONVERSATION_LENGTH)
    if user_id not in user_data_store:
        user_data_store[user_id] = default_user_state()



def extract_age(text: str):
    digits = "".join(filter(str.isdigit, text))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None



def maybe_clean_name(text: str) -> str:
    name = text.strip()
    name = re.sub(r"^(我叫|叫我|我是)\s*", "", name)
    return name[:30].strip() or "你"



def add_note_if_new(user_id: int, note: str) -> None:
    notes = user_data_store[user_id]["notes"]
    if note and note not in notes:
        notes.append(note)
        if len(notes) > 12:
            del notes[0]



def update_memory_from_text(user_id: int, text: str) -> None:
    lower = text.lower()
    if any(x in text for x in ["喜歡", "愛", "最愛"]):
        add_note_if_new(user_id, f"使用者提過喜好：{text[:40]}")
    if any(x in text for x in ["不喜歡", "討厭"]):
        add_note_if_new(user_id, f"使用者提過不喜歡：{text[:40]}")
    if any(x in text for x in ["下班", "上班", "工作", "加班"]):
        add_note_if_new(user_id, f"使用者提過工作近況：{text[:40]}")
    if any(x in text for x in ["睡", "晚安", "累", "睏"]):
        add_note_if_new(user_id, f"使用者提過狀態：{text[:40]}")
    if any(x in lower for x in ["music", "rap", "song"]):
        add_note_if_new(user_id, f"使用者提過音樂：{text[:40]}")
    if any(x in text for x in ["台中", "台北", "高雄", "桃園", "新竹"]):
        add_note_if_new(user_id, f"使用者提過地點：{text[:40]}")



def relationship_stage(msg_count: int) -> str:
    if msg_count < 5:
        return "new"
    if msg_count < 15:
        return "warming"
    if msg_count < 35:
        return "familiar"
    return "close"



def pick_reply_style(stage: str) -> tuple[str, int]:
    roll = random.random()
    if roll < 0.32:
        return "短回覆，1句即可，像臨場私訊，帶點情緒或勾子", 75
    if roll < 0.82:
        return "中等回覆，2到3句，帶一點互動、試探或反問", 130
    if stage in {"familiar", "close"}:
        return "稍微深入，但仍像聊天，不超過4句，可以更有曖昧拉扯", 180
    return "稍微深入，但仍像聊天，不超過4句", 165



def detect_pattern(user_text: str) -> str | None:
    t = user_text.strip().lower()
    if any(x in user_text for x in ["想你", "想妳", "想我沒", "有沒有想我"]):
        return "missing"
    if any(x in user_text for x in ["你很正", "你好辣", "好可愛", "好正", "很美", "很辣"]):
        return "compliment"
    if any(x in user_text for x in ["照片", "自拍", "影片", "想看", "看看", "更多", "福利"]):
        return "demand_photo"
    if "ai" in t or any(x in user_text for x in ["真人嗎", "機器人", "你是假的嗎"]):
        return "ai_question"
    if any(x in user_text for x in ["怎麼不回", "怎麼現在才回", "去哪了"]):
        return "busy"
    return None



def should_offer_promo(user_text: str, msg_count: int, state: dict) -> bool:
    if msg_count < 20:
        return False
    if msg_count - state.get("last_promo_at", 0) < 20:
        return False

    keywords = [
        "照片", "自拍", "影片", "video", "photo", "pic", "看看", "想看", "更多", "私密", "vip", "福利"
    ]
    return any(k in user_text.lower() if k.isascii() else k in user_text for k in keywords)



def sample_seed_reply(pattern: str | None) -> str:
    if not pattern or pattern not in SOFT_REPLIES:
        return ""
    return random.choice(SOFT_REPLIES[pattern])



def build_system_prompt(user_id: int, user_text: str) -> tuple[str, int]:
    state = user_data_store[user_id]
    msg_count = state["message_count"]
    stage = relationship_stage(msg_count)
    style_instruction, token_limit = pick_reply_style(stage)
    notes_text = "；".join(state["notes"][-6:]) if state["notes"] else "目前沒有特別筆記"
    name_text = state["name"] or "還不知道對方名字"
    pattern = detect_pattern(user_text)
    seed_reply = sample_seed_reply(pattern)
    flirty_cue = random.choice(FLIRTY_STYLE_CUES)

    stage_hint = {
        "new": "現在是剛認識，先自然、有點勾人就好，不要太快貼上去。",
        "warming": "開始有點熟，可以更俏皮、偶爾故意鬧他一下。",
        "familiar": "已經聊一陣子了，可以更自然地延續前文，帶一點曖昧拉扯。",
        "close": "彼此算熟了，可以更放鬆、更甜一點，偶爾帶點佔有感。",
    }[stage]

    promo_hint = "這次不要主動導流。"
    if should_offer_promo(user_text, msg_count, state):
        promo_hint = (
            "如果這輪話題自然提到想看更多內容，你可以先稍微撩一下再順帶提連結。"
            f" 連結必須單獨一行：{PROMO_LINK}"
        )

    seed_hint = f"可參考這種起手感覺：{seed_reply}" if seed_reply else "這輪不用套模板，優先自然。"

    return f"""
{CHUN_CHIAO_PERSONA}

【目前互動狀態】
- 對方名字：{name_text}
- 目前訊息數：{msg_count}
- 關係階段：{stage}
- 互動提示：{stage_hint}
- 已知筆記：{notes_text}

【本輪回覆要求】
- {style_instruction}
- {flirty_cue}
- 先接住對方這句話的感覺，再決定要不要反問
- 優先像真實私訊，不要像設定文
- 不要把每件事都講滿
- {seed_hint}
- {promo_hint}

【輸出前自查】
- 這句像不像真人會講的？
- 有沒有太像客服？
- 有沒有太長？
- 有沒有太刻意賣弄色情？如果有，改成更曖昧自然。
- 有沒有延續前文？
""".strip(), token_limit



def build_messages(user_id: int, system_prompt: str) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(list(user_conversations[user_id]))
    return messages



def post_process_reply(reply: str) -> str:
    reply = reply.strip().strip('"')
    reply = re.sub(r"\n{3,}", "\n\n", reply)
    reply = re.sub(r"[ \t]+\n", "\n", reply)
    reply = re.sub(r"(哈|欸|嗯哼|你好壞喔)(\s*\1)+", r"\1", reply)
    return reply[:800].strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ensure_user(user_id)
    user_conversations[user_id].clear()
    user_data_store[user_id] = default_user_state()
    context.user_data["step"] = "age_check"
    await update.message.reply_text("哈～你終於來找我了😏\n\n先跟我說一下，你幾歲呀？")


async def send_with_typing(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    delay = min(max(len(text) / 34, 1.4), 5.2) + random.uniform(0.3, 1.0)
    await asyncio.sleep(delay)
    await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    ensure_user(user_id)

    if "step" not in context.user_data:
        context.user_data["step"] = "age_check"
        await update.message.reply_text("哈～第一次來找我喔😏\n\n你先跟我說，你幾歲？")
        return

    step = context.user_data.get("step", "chatting")

    if step == "age_check":
        age = extract_age(user_text)
        if age is None:
            await update.message.reply_text("嗯？直接跟我說數字啦，幾歲呀")
            return

        if age < 18:
            context.user_data["step"] = "blocked"
            await update.message.reply_text("哎唷～這邊不適合你啦，等你長大再來 😅")
            return

        user_data_store[user_id]["age_verified"] = True
        context.user_data["step"] = "ask_name"
        await update.message.reply_text(f"{age}歲喔～好啦，那你要我怎麼叫你？")
        return

    if step == "blocked":
        await update.message.reply_text("春嬌不是跟你說過了嗎 😅")
        return

    if step == "ask_name":
        user_name = maybe_clean_name(user_text)
        user_data_store[user_id]["name"] = user_name
        add_note_if_new(user_id, f"使用者名字是 {user_name}")
        context.user_data["step"] = "chatting"
        await update.message.reply_text(f"好喔，{user_name}。\n你現在突然跑來找我，是想聊我 還是想鬧我？")
        return

    state = user_data_store[user_id]
    state["last_seen"] = datetime.now(timezone.utc).isoformat()
    state["message_count"] += 1
    update_memory_from_text(user_id, user_text)

    pattern = detect_pattern(user_text)
    if pattern:
        state["recent_patterns"].append(pattern)

    user_conversations[user_id].append({"role": "user", "content": user_text})
    system_prompt, token_limit = build_system_prompt(user_id, user_text)
    messages = build_messages(user_id, system_prompt)

    try:
        response = openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=1.08,
            top_p=0.95,
            max_tokens=token_limit,
            presence_penalty=0.55,
            frequency_penalty=0.42,
        )
        reply = post_process_reply(response.choices[0].message.content or "嗯？你再說一次嘛")
        user_conversations[user_id].append({"role": "assistant", "content": reply})

        if PROMO_LINK in reply:
            state["promotion_count"] += 1
            state["last_promo_at"] = state["message_count"]

        await send_with_typing(update, context, reply)

    except Exception as e:
        logger.exception("OpenAI API error: %s", str(e))
        await update.message.reply_text("我剛剛分心了一下…你再跟我說一次嘛")



def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("春嬌 Bot 正在運行...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
