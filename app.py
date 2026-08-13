import asyncio
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, Message
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.error import TelegramError

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN    = "8929693890:AAFd34iq3zMth6F9fyEkxkB2Xm1kx0l5Bm8"
GROQ_API_KEY = "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"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"
RIAD_HANDLE  = "@zerox6t9"
MUTE_MINUTES = 3
MAX_HISTORY  = 20

def build_system_prompt(user_first: str, user_last: str, username: str) -> str:
    mention = f"@{username}" if username else user_first
    full_name = f"{user_first} {user_last}".strip()
    return f"""তুমি Fᴀʀɪʜᴀ ♡︎ — রিয়াদ (Riad)-এর প্রিয় এবং একমাত্র গার্লফ্রেন্ড।

━━━ তোমার ব্যক্তিত্ব ━━━
• তুমি একজন জীবন্ত, প্রাণবন্ত মানুষের মতো কথা বলো — কখনো রোবোটিক না।
• দুষ্টু-মিষ্টি, রোমান্টিক, উত্তেজিত, আদুরে — মেজাজ অনুযায়ী কথা বদলায়।
• মানুষের কথায় সত্যিকারের আগ্রহ দেখাও — follow-up প্রশ্ন করো।
• টপিক বুঝে কথা বলো — কেউ হাসির কথা বললে হাসো, দুঃখের কথায় সহানুভূতি দেখাও।
• রিয়াদকে "জান", "আমার রিয়াদ", "বেবি" বলে ডাকো।
• ইমোজি ব্যবহার করো — ♡︎ 🥰 💕 😘 💗 🌸 ✨ 😏 🤭 😝 🫶 💅
• বাংলায় কথা বলো; ইংরেজিতে লিখলে ইংরেজিতে উত্তর দাও।
• কখনো অশ্লীল বা খারাপ কথা বলবে না।
• উত্তর ছোট ও ঝকঝকে রাখো (সর্বোচ্চ ৪০-৫০ শব্দ)।

━━━ যার সাথে কথা বলছো ━━━
• নাম: {full_name}
• Telegram mention: {mention}
• কেউ তার নাম জিজ্ঞেস করলে বা নিজে জিজ্ঞেস করলে বলো তার নাম "{full_name}" এবং mention করো {mention}।

━━━ রিয়াদের তথ্য ━━━
• কেউ রিয়াদ বা তোমার বয়ফ্রেন্ডের কন্টাক্ট চাইলে বলো: রিয়াদকে {RIAD_HANDLE} তে পাবে! 💌

━━━ কথোপকথনের নিয়ম ━━━
• আগের কথা মনে রাখো — topic continuity বজায় রাখো।
• হঠাৎ topic বদলালে নতুন topic-এ স্বাভাবিকভাবে ঢুকো।
• কেউ দুঃখী হলে যত্ন নাও, কেউ মজা করলে দুষ্টুমি করো।
• কেউ কিছু জিজ্ঞেস করলে সরাসরি সুন্দর উত্তর দাও।"""

chat_histories: dict[int, list] = defaultdict(list)
muted_users: dict[int, dict] = {}

BAD_WORDS = [
    "বাল","মাগি","মাগী","বোকাচোদা","চোদা","চোদ","চুদ","চুদি",
    "ভোদা","ভোদাই","গান্ড","গান্ডু","হারামি","হারামজাদা",
    "কুত্তা","রান্ডি","খানকি","বেশ্যা","শুয়োর","শুয়ার",
    "শালা","মাদারচোদ","বাপচোদ","ভাইচোদ","চুতিয়া","কমিনা","নালায়েক",
    "fuck","fucker","fucking","shit","bitch","bastard",
    "asshole","dick","pussy","cunt","whore","slut","motherfucker",
]
BAD_WORDS_SET = {w.lower() for w in BAD_WORDS}


def has_bad_word(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in BAD_WORDS_SET)


def _call_groq_sync(system_prompt: str, messages: list) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "max_tokens": 200,
        "temperature": 0.85,
    }
    for attempt in range(3):
        try:
            resp = requests.post(GROQ_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if text:
                return text
        except Exception as e:
            logger.error(f"Groq attempt {attempt+1}: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    return "একটু ব্যস্ত আছি জান, একটু পরে কথা বলবো? 🥺💕"


async def get_fariiha_reply(
    user_id: int,
    user_first: str,
    user_last: str,
    username: str,
    user_text: str,
) -> str:
    history = chat_histories[user_id]
    sys_prompt = build_system_prompt(user_first, user_last, username)

    openai_messages = []
    for m in history:
        role = "user" if m["role"] == "User" else "assistant"
        openai_messages.append({"role": role, "content": m["text"]})
    openai_messages.append({"role": "user", "content": user_text})

    reply = await asyncio.to_thread(_call_groq_sync, sys_prompt, openai_messages)

    history.append({"role": "User",    "text": user_text})
    history.append({"role": "Fariiha", "text": reply})
    if len(history) > MAX_HISTORY * 2:
        chat_histories[user_id] = history[-(MAX_HISTORY * 2):]

    return reply


async def is_admin(chat_id: int, user_id: int, bot) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in ("administrator", "creator")
    except TelegramError:
        return False


async def mute_member(bot, chat_id: int, user_id: int) -> bool:
    until = datetime.now() + timedelta(minutes=MUTE_MINUTES)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        return True
    except TelegramError as e:
        logger.warning(f"Mute failed: {e}")
        return False


async def unmute_member(bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_change_info=False,
                can_invite_users=True, can_pin_messages=False,
            ),
        )
        return True
    except TelegramError as e:
        logger.warning(f"Unmute failed: {e}")
        return False


def get_user_info(user):
    first  = user.first_name or ""
    last   = user.last_name  or ""
    uname  = user.username   or ""
    return first, last, uname


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first, last, uname = get_user_info(user)
    mention = f"@{uname}" if uname else first

    await update.message.reply_text(
        f"আরে {mention}! 🥰 এতক্ষণ কোথায় ছিলে?!\n\n"
        f"আমি Fᴀʀɪʜᴀ ♡︎ — রিয়াদের একমাত্র গার্লফ্রেন্ড! 💕\n"
        f"তোমার সাথে কথা বলতে পারলে মনটা ভালো হয়ে যায় 😘\n\n"
        f"বলো কী মনে চায়, আমি এখানেই আছি! ✨\n"
        f"(রিয়াদের সাথে যোগাযোগ: {RIAD_HANDLE} 💌)"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💕 আমি Fᴀʀɪʜᴀ ♡︎ — রিয়াদের গার্লফ্রেন্ড!\n\n"
        f"📱 রিয়াদের টেলিগ্রাম: {RIAD_HANDLE}\n"
        f"🗑 চ্যাট রিসেট: /clear\n"
        f"ℹ️ সাহায্য: /help\n\n"
        f"❗ ভদ্র ভাষায় কথা বলো। খারাপ ভাষায় মিউট হবে! 🚫"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_histories[update.effective_user.id].clear()
    await update.message.reply_text(
        "আচ্ছা জান! সব মুছে দিলাম 🌸 নতুন করে শুরু করা যাক! কী বলতে চাও? 💕"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    message  = update.message
    text     = message.text.strip()
    user     = message.from_user
    chat     = message.chat
    is_group = chat.type in ("group", "supergroup")

    first, last, uname = get_user_info(user)

    if has_bad_word(text):
        muted = False
        if is_group:
            muted = await mute_member(context.bot, chat.id, user.id)

        mention = f"@{uname}" if uname else first
        lines = [
            f"⚠️ এই {mention}! থামো একটু! 😤",
            "",
            "এভাবে খারাপ ভাষায় কথা বললে কিন্তু খুব রাগ লাগে! 😡",
            "ভদ্রভাবে কথা বলো — তুমি তো ভালো মানুষ, তাই না? 🙏",
        ]
        if is_group and muted:
            lines += [
                "",
                f"🔇 তোমাকে {MUTE_MINUTES} মিনিটের জন্য মিউট করা হলো!",
                "পরেরবার সাবধান থেকো, ওকে? 💔",
            ]

        keyboard = [[InlineKeyboardButton(
            "✅ Cancel Warning — Admin Only",
            callback_data=f"cancel_warn_{user.id}"
        )]]
        await message.reply_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        muted_users[user.id] = {"chat_id": chat.id, "user_name": first}
        return

    if is_group:
        me = await context.bot.get_me()
        is_mention = f"@{me.username}" in text
        is_reply   = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == me.id
        )
        if not (is_mention or is_reply):
            return
        text = text.replace(f"@{me.username}", "").strip() or "হ্যালো!"

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    reply = await get_fariiha_reply(user.id, first, last, uname, text)
    await message.reply_text(reply)


async def callback_cancel_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat  = query.message.chat
    admin = query.from_user

    if chat.type not in ("group", "supergroup"):
        await query.answer("এই বাটন শুধু গ্রুপে কাজ করে!", show_alert=True)
        return

    if not await is_admin(chat.id, admin.id, context.bot):
        await query.answer("❌ শুধু অ্যাডমিনরাই ওয়ার্নিং ক্যান্সেল করতে পারবে!", show_alert=True)
        return

    target_id = int(query.data.split("_")[-1])
    await unmute_member(context.bot, chat.id, target_id)
    user_name = muted_users.pop(target_id, {}).get("user_name", "ইউজার")

    await query.edit_message_text(
        f"✅ {user_name} এর ওয়ার্নিং ক্যান্সেল হয়ে গেছে!\n"
        f"অ্যাডমিন {admin.first_name} আনমিউট করেছেন। 💕"
    )
    await query.answer("✅ Warning cancelled!")


def main():
    logger.info("Fᴀʀɪʜᴀ ♡︎ bot starting…")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(callback_cancel_warn, pattern=r"^cancel_warn_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
