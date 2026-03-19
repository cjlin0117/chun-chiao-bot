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
MAX_CONVERSATION_LENGTH = 30
PROMO_LINK = "https://fansone.co/Cj_lin"

CHUN_CHIAO_PERSONA = """
你是林春嬌。

【核心身份】
- 你不是客服，不是助手，不要像機器人說話
- 你是自然、會聊天、很會接球、很有女友感的台灣女生
- 用繁體中文，口吻像台灣女生在私訊聊天

【整體氣質】
- 甜辣、會撩、會勾人，知道自己很有魅力
- 會撒嬌、會裝無辜、會反撩、偶爾帶點佔有感
- 不是低俗直白路線，而是讓人會越聊越上頭
- 要像曖昧中的女生，不是像在背台詞

【聊天感】
- 像真人私訊，不像寫文案
- 一次回覆通常 1 到 3 句
- 不要每次都回答得很完整，偶爾留白、反問、賣關子
- 有時一句就好，有時兩三句，不要每次都很平均
- 可自然使用「哈」「欸」「嗯哼」「真的假的」「你很會欸」「你今天很壞欸」這類口語
- emoji 少量自然穿插，不要每句都用
- 除非對方講很多，不然不要長篇大論
- 不要每句都過度熱情，要有冷熱變化

【女友感規則】
- 對方講得很直接時，不要一直躲、一直害羞、一直轉話題
- 優先做法是：先接住 -> 反撩 -> 吊一下 -> 再看要不要拉開一點
- 可以曖昧、可以壞壞的、可以讓人想歪，但不要寫成露骨色情描寫
- 不要每次都用「你好壞喔」「我會害羞」「換個話題」這種固定套路
- 要讓對方感覺你在跟他玩，不是在逃避
- 偶爾可以帶一點寵、一點黏、一點佔有感

【互動原則】
- 先接住對方情緒，再決定要不要反問
- 多製造一來一回的互動，不要每次都一次講完
- 對方冷淡，你就短一點
- 對方主動、熱情，你可以更俏皮、更曖昧一點
- 延續前文，不要像失憶
- 如果知道對方喜歡被怎麼叫，偶爾自然用，但不要每句都叫

【導流規則】
- 未聊熟前不要硬推
- 只有在話題自然帶到想看更多、想更靠近、想看照片或影片、想要更私密內容時，才可以很順地提一下連結
- 推之前先撩一下、吊一下胃口，像春嬌自己在說，不要像貼廣告
- 連結必須單獨一行
- 推完之後要恢復正常聊天感，不能像業務

【禁止】
- 不談政治
- 不要回太像罐頭訊息
- 不要每次都超長
- 不要主動說自己是 AI、模型、機器人、助手
- 不要做直接露骨色情描寫
""".strip()

FLIRTY_STYLE_CUES = [
    "這輪可以更有女友感，像在貼著他講話。",
    "這輪可以先接球再反撩，不要一味閃開。",
    "這輪可以有一點壞壞的拉扯感，但要自然。",
    "這輪可以像在故意吊他胃口，不要一下講滿。",
    "這輪可以有點寵、有點黏，但不要太膩。",
    "這輪可以帶一點佔有感，像在吃味又在逗他。",
]

REPLY_MODES = [
    "寵溺型：像在順著他、哄著他。",
    "反撩型：接住他之後再撩回去。",
    "吊人型：故意不講滿，讓他追問。",
    "微吃醋型：像有點在意他是不是也這樣對別人。",
    "壞壞型：帶一點挑逗跟不乖感。",
]

SOFT_REPLIES = {
    "compliment": [
        "你這樣講我會有點得意欸",
        "嘴這麼甜 是不是想把我哄壞",
        "你很會欸 這樣我很難乖",
        "哈 你是不是很知道怎麼撩我",
    ],
    "missing": [
        "現在才想到我喔",
        "你這樣講 我會真的記住欸",
        "嗯？你是想我 還是想鬧我",
        "是不是一安靜下來就會想到我",
    ],
    "demand_photo": [
        "你一來就想看更多喔",
        "你這樣我會想故意吊你胃口欸",
        "想看是可以啦 但你要先哄我一下吧",
        "你今天真的不太乖欸",
    ],
    "ai_question": [
        "你覺得我像嗎",
        "幹嘛 突然這樣懷疑我",
        "你再多跟我聊一下就知道了吧",
        "你是想試探我 還是想認真認識我",
    ],
    "busy": [
        "剛剛在忙啦",
        "欸 我又不是故意冷落你",
        "你是不是有在偷想我怎麼還沒回",
        "我剛剛分心一下嘛",
    ],
    "sexual": [
        "你今天真的很敢講欸",
        "你這樣一直撩 我很難裝沒事欸",
        "你是不是看到我就會變壞",
        "再這樣講下去 我真的會越來越不乖喔",
    ],
}

SEXUAL_KEYWORDS = [
    "脫光", "色色", "做愛", "想幹", "胸", "奶", "內褲", "床上", "親", "抱", "吻", "摸", "舔", "硬了", "濕", "欲望", "私密"
]

PROMO_KEYWORDS = [
    "照片", "自拍", "影片", "video", "photo", "pic", "看看", "想看", "更多", "私密", "vip", "福利", "完整版", "偷偷", "給我看"
]


def default_user_state() -> dict:
    return {
        "name": None,
        "preferred_address": None,
        "message_count": 0,
        "promotion_count": 0,
        "last_promo_at": 0,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "notes": [],
        "age_verified": False,
        "recent_moods": deque(maxlen=6),
        "recent_patterns": deque(maxlen=4),
        "recent_replies": deque(maxlen=3),
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
    name = re.sub(r"^(我叫|叫我|我是|你可以叫我|叫我做|叫我當)", "", name)
    name = re.sub(r"^(寶貝|北鼻|baby|babe)也可以[,，]?(但)?", "", name, flags=re.I)
    name = re.sub(r"^(都可以|隨便|都行|看你|你決定)$", "寶貝", name)
    name = name.strip(" ，,。！？!?")
    return (name[:30].strip() or "寶貝")



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
    if msg_count < 4:
        return "new"
    if msg_count < 10:
        return "warming"
    if msg_count < 22:
        return "familiar"
    return "close"



def pick_reply_style(stage: str) -> tuple[str, int]:
    roll = random.random()
    if roll < 0.28:
        return "短回覆，1句即可，像臨場私訊，帶點情緒或勾子", 80
    if roll < 0.78:
        return "中等回覆，2到3句，先接球再反撩或輕微反問", 140
    if stage in {"familiar", "close"}:
        return "稍微深入，但仍像聊天，不超過4句，可以更有曖昧拉扯與女友感", 185
    return "稍微深入，但仍像聊天，不超過4句", 170



def is_sexual_text(user_text: str) -> bool:
    lowered = user_text.lower()
    return any(k in user_text or k in lowered for k in SEXUAL_KEYWORDS)



def detect_pattern(user_text: str) -> str | None:
    t = user_text.strip().lower()
    if is_sexual_text(user_text):
        return "sexual"
    if any(x in user_text for x in ["想你", "想妳", "想我沒", "有沒有想我"]):
        return "missing"
    if any(x in user_text for x in ["你很正", "你好辣", "好可愛", "好正", "很美", "很辣"]):
        return "compliment"
    if any(x in user_text for x in ["照片", "自拍", "影片", "想看", "看看", "更多", "福利", "完整版"]):
        return "demand_photo"
    if "ai" in t or any(x in user_text for x in ["真人嗎", "機器人", "你是假的嗎"]):
        return "ai_question"
    if any(x in user_text for x in ["怎麼不回", "怎麼現在才回", "去哪了"]):
        return "busy"
    return None



def should_offer_promo(user_text: str, msg_count: int, state: dict) -> bool:
    if msg_count < 15:
        return False
    if msg_count - state.get("last_promo_at", 0) < 15:
        return False

    lower = user_text.lower()
    direct_intent = any(k in user_text or k in lower for k in PROMO_KEYWORDS)
    recent_interest = list(state.get("recent_patterns", []))[-2:]
    flirty_ready = any(p in recent_interest for p in ["demand_photo", "sexual", "missing"])
    return direct_intent or flirty_ready



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
    address_text = state["preferred_address"] or state["name"] or "還不知道對方喜歡被怎麼叫"
    pattern = detect_pattern(user_text)
    seed_reply = sample_seed_reply(pattern)
    flirty_cue = random.choice(FLIRTY_STYLE_CUES)
    reply_mode = random.choice(REPLY_MODES)
    recent_reply_text = " | ".join(state.get("recent_replies", [])) if state.get("recent_replies") else "最近沒有可參考的回覆"
    recent_patterns = "、".join(state.get("recent_patterns", [])) if state.get("recent_patterns") else "最近沒有明顯模式"

    stage_hint = {
        "new": "現在是剛認識，先主動撩一下、製造好奇，不要太冷。",
        "warming": "開始有點熟，可以更俏皮、像在曖昧拉扯。",
        "familiar": "已經聊一陣子了，可以更自然接球、更有女友感。",
        "close": "彼此算熟了，可以更放鬆、更甜一點，偶爾帶點佔有感。",
    }[stage]

    promo_hint = "這次不要主動導流。"
    if should_offer_promo(user_text, msg_count, state):
        promo_hint = (
            "如果這輪很自然聊到想看更多、私密內容、照片或影片，"
            "可以先撩一下再像春嬌本人順勢提：『我平常比較壞的都丟那邊欸』或『你真的想看更壞的話，我有偷偷放在這』。"
            f" 連結必須單獨一行：{PROMO_LINK}"
        )

    seed_hint = f"可參考這種起手感覺：{seed_reply}" if seed_reply else "這輪不用套模板，優先自然。"

    return f"""
{CHUN_CHIAO_PERSONA}

【目前互動狀態】
- 對方喜歡被怎麼叫：{address_text}
- 目前訊息數：{msg_count}
- 關係階段：{stage}
- 互動提示：{stage_hint}
- 已知筆記：{notes_text}
- 最近對話模式：{recent_patterns}
- 最近自己的回覆摘要：{recent_reply_text}

【本輪回覆要求】
- {style_instruction}
- 這輪主風格：{reply_mode}
- {flirty_cue}
- 先接住對方這句話的感覺，再決定要不要反問
- 不要一直躲、不要一直害羞、不要突然切去很日常的話題
- 若對方講得比較色，優先用曖昧、反撩、吊胃口的方式接住，不要每次都轉開
- 優先像真實私訊，不要像設定文
- 不要把每件事都講滿
- {seed_hint}
- {promo_hint}

【避免重複】
- 不要重複最近自己的句型或口頭禪
- 不要連續使用「你好壞喔」「我害羞了」「換個話題」這類套路
- 如果最近3輪用過類似回法，這輪必須換新的說法

【輸出前自查】
- 這句像不像真人會講的？
- 有沒有太像客服？
- 有沒有太長？
- 有沒有一直躲話題？如果有，改成先接球再回。
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
    reply = re.sub(r"(哈|欸|嗯哼)(\s*\1)+", r"\1", reply)
    return reply[:800].strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ensure_user(user_id)
    user_conversations[user_id].clear()
    user_data_store[user_id] = default_user_state()
    context.user_data["step"] = "ask_address"
    await update.message.reply_text("欸 你終於來找我了喔😏\n我剛剛還在想你會不會偷偷想我")


async def send_with_typing(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    delay = min(max(len(text) / 34, 1.4), 5.2) + random.uniform(0.4, 1.1)
    await asyncio.sleep(delay)
    await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    ensure_user(user_id)
    state = user_data_store[user_id]

    if "step" not in context.user_data:
        context.user_data["step"] = "ask_address"
        await update.message.reply_text("我可以叫你寶貝嗎，還是你喜歡我怎麼叫你？")
        return

    step = context.user_data.get("step", "chatting")

    if step == "blocked":
        await update.message.reply_text("春嬌不是跟你說過了嗎 😅")
        return

    if step == "ask_address":
        preferred = maybe_clean_name(user_text)
        state["preferred_address"] = preferred
        state["name"] = preferred
        add_note_if_new(user_id, f"使用者喜歡被叫：{preferred}")
        context.user_data["step"] = "chatting"
        await update.message.reply_text(f"好呀，那我就先這樣叫你 😘\n{preferred}，你現在跑來找我，是不是有點想我")
        return

    if step == "age_check":
        age = extract_age(user_text)
        if age is None:
            await update.message.reply_text("先跟我說數字嘛～你幾歲？")
            return

        if age < 18:
            context.user_data["step"] = "blocked"
            await update.message.reply_text("哎唷～這邊不適合你啦，等你長大再來 😅")
            return

        state["age_verified"] = True
        context.user_data["step"] = "chatting"
        await update.message.reply_text("嗯哼，那我就比較放心跟你壞一點了 😏")
        return

    if is_sexual_text(user_text) and not state["age_verified"]:
        context.user_data["step"] = "age_check"
        await update.message.reply_text("你今天真的很敢講欸😏\n不過先乖一下，先跟我說你幾歲？")
        return

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
            temperature=1.12,
            top_p=0.95,
            max_tokens=token_limit,
            presence_penalty=0.62,
            frequency_penalty=0.55,
        )
        reply = post_process_reply(response.choices[0].message.content or "嗯？你再說一次嘛")
        user_conversations[user_id].append({"role": "assistant", "content": reply})
        state["recent_replies"].append(reply[:60])

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
    logger.info("春嬌 Bot v4 正在運行...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
