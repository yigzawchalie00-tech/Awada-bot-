"""
Awada Church Telegram Bot
Amharic-language bot for church content (songs, books, lyrics, hall info, feedback).
Admin panel at /admin.
Runs on Render free tier (web service) using aiohttp for the HTTP port + python-telegram-bot.
"""

import asyncio
import os
import logging
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
import psycopg
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "1766103612"))
DATABASE_URL = os.environ["DATABASE_URL"]

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_conn():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lyrics (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hall_posts (
                id SERIAL PRIMARY KEY,
                caption TEXT,
                media_type TEXT,
                file_id TEXT,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                message TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()

# ─── Conversation states ───────────────────────────────────────────────────────

(
    ADMIN_MENU,
    ADD_SONG_TITLE, ADD_SONG_FILE,
    ADD_BOOK_TITLE, ADD_BOOK_FILE,
    ADD_LYRIC_TITLE, ADD_LYRIC_FILE,
    ADD_HALL_CAPTION, ADD_HALL_MEDIA,
    FEEDBACK_TEXT,
    BROADCAST_TEXT,
    REPLY_TO_USER,
    BULK_SONG_TITLE, BULK_SONG_FILES,
    BULK_BOOK_TITLE, BULK_BOOK_FILES,
) = range(16)

# ─── Main menu ─────────────────────────────────────────────────────────────────

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎵 መዝሙር"),  KeyboardButton("📖 Books")],
        [KeyboardButton("📝 የመዝሙር ግጥሞች"), KeyboardButton("🏛 አዳራሻችን")],
        [KeyboardButton("💬 አስተያየት"), KeyboardButton("❓ Help")],
    ],
    resize_keyboard=True
)


def register_user(user):
    try:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO users (id, username, first_name)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE
                   SET username=EXCLUDED.username, first_name=EXCLUDED.first_name""",
                (user.id, user.username, user.first_name)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"register_user failed: {e}")


async def auto_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Silently register any user who sends any message — runs before all handlers."""
    if update.effective_user:
        register_user(update.effective_user)


# ─── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await update.message.reply_text(
        "🙏 እንኳን ደህና መጡ!\nወደ አዋዳ ቤተ ክርስቲያን ቴሌግራም ቦት\n\nከዚህ በታች ካሉት ምርጫዎች ይምረጡ:",
        reply_markup=MAIN_MENU
    )


# ─── 🎵 Songs ──────────────────────────────────────────────────────────────────

async def menu_songs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        rows = conn.execute("SELECT id, title FROM songs ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        await update.message.reply_text("🎵 ምንም መዝሙር አልተጨመረም።")
        return
    buttons = [[InlineKeyboardButton(r[1], callback_data=f"song:{r[0]}")] for r in rows]
    await update.message.reply_text("🎵 መዝሙሮች:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_song(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    song_id = int(query.data.split(":")[1])
    with get_conn() as conn:
        row = conn.execute("SELECT title, file_id FROM songs WHERE id=%s", (song_id,)).fetchone()
    if row:
        await query.message.reply_audio(audio=row[1], title=row[0])


# ─── 📖 Books ──────────────────────────────────────────────────────────────────

async def menu_books(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        rows = conn.execute("SELECT id, title FROM books ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        await update.message.reply_text("📖 ምንም መጽሐፍ አልተጨመረም።")
        return
    buttons = [[InlineKeyboardButton(r[1], callback_data=f"book:{r[0]}")] for r in rows]
    await update.message.reply_text("📖 መጽሐፍቶች:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split(":")[1])
    with get_conn() as conn:
        row = conn.execute("SELECT title, file_id FROM books WHERE id=%s", (book_id,)).fetchone()
    if row:
        await query.message.reply_document(document=row[1], filename=f"{row[0]}.pdf")


# ─── 📝 Lyrics ─────────────────────────────────────────────────────────────────

async def menu_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        rows = conn.execute("SELECT id, title FROM lyrics ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        await update.message.reply_text("📝 ምንም ግጥም አልተጨመረም።")
        return
    buttons = [[InlineKeyboardButton(r[1], callback_data=f"lyric:{r[0]}")] for r in rows]
    await update.message.reply_text("📝 የመዝሙር ግጥሞች:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_lyric(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lyric_id = int(query.data.split(":")[1])
    with get_conn() as conn:
        row = conn.execute("SELECT title, file_id FROM lyrics WHERE id=%s", (lyric_id,)).fetchone()
    if row:
        await query.message.reply_photo(photo=row[1], caption=row[0])


# ─── 🏛 Hall ───────────────────────────────────────────────────────────────────

async def menu_hall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT caption, media_type, file_id FROM hall_posts ORDER BY id DESC LIMIT 5"
        ).fetchall()
    if not rows:
        await update.message.reply_text("🏛 ምንም ልጥፍ አልተጨመረም።")
        return
    for caption, mtype, fid in rows:
        try:
            if mtype == "photo":
                await update.message.reply_photo(photo=fid, caption=caption)
            elif mtype == "video":
                await update.message.reply_video(video=fid, caption=caption)
            else:
                await update.message.reply_text(caption or "🏛 አዳራሻችን")
        except Exception as e:
            logger.warning(f"hall post send error: {e}")


# ─── 💬 Feedback ───────────────────────────────────────────────────────────────

async def menu_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 አስተያየትዎን ያስፍሩ:")
    return FEEDBACK_TEXT


async def receive_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feedback (user_id, username, message) VALUES (%s, %s, %s)",
            (user.id, user.username, text)
        )
        conn.commit()
    await update.message.reply_text("✅ አስተያየትዎ ተቀብሏል። ለዚህ ቦት አመሰግናለሁ!")

    # Forward to admin with reply button
    keyboard = [[InlineKeyboardButton("↩ መልስ ስጥ", callback_data=f"reply:{user.id}")]]
    name = user.first_name or user.username or str(user.id)
    await ctx.bot.send_message(
        ADMIN_ID,
        f"📨 አስተያየት ከ {name} (@{user.username}):\n\n{text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ─── ❓ Help ───────────────────────────────────────────────────────────────────

async def menu_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ እርዳታ\n\n"
        "🎵 መዝሙር — የቤተ ክርስቲያን መዝሙሮችን ያዳምጡ\n"
        "📖 Books — የቤተ ክርስቲያን መጽሐፍቶችን ያንብቡ\n"
        "📝 ግጥሞች — የመዝሙር ግጥሞች ፎቶ\n"
        "🏛 አዳራሻችን — የቤተ ክርስቲያን አዳራሽ መረጃ\n"
        "💬 አስተያየት — አስተያየትዎን ይላኩ\n\n"
        "ለጥያቄ አስተዳዳሪውን ያናግሩ።"
    )


# ─── Admin panel ───────────────────────────────────────────────────────────────

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ መዝሙር ጨምር",      "➕ Book ጨምር"],
        ["📦 Bulk መዝሙር ጨምር", "📦 Bulk Books ጨምር"],
        ["➕ ግጥም ጨምር",       "➕ Hall ልጥፍ ጨምር"],
        ["📋 Feedbacks ይመልከቱ","📢 Broadcast"],
        ["🔙 ወደ ዋና ምናሌ"],
    ],
    resize_keyboard=True
)


async def admin_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ ይህ ትዕዛዝ ለአስተዳዳሪ ብቻ ነው።")
        return ConversationHandler.END
    await update.message.reply_text("🔧 Admin Panel:", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


async def admin_menu_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "➕ መዝሙር ጨምር":
        await update.message.reply_text("🎵 የመዝሙሩን ስም ያስፍሩ:")
        return ADD_SONG_TITLE
    elif text == "➕ Book ጨምር":
        await update.message.reply_text("📖 የመጽሐፉን ስም ያስፍሩ:")
        return ADD_BOOK_TITLE
    elif text == "📦 Bulk መዝሙር ጨምር":
        await update.message.reply_text(
            "📦 Bulk መዝሙር — መጀመሪያ ርዕስ/prefix ያስፍሩ:\n"
            "(ለምሳሌ: 'ምስጋና' ካሉ → ምስጋና 1, ምስጋና 2, ... ይሆናል)"
        )
        return BULK_SONG_TITLE
    elif text == "📦 Bulk Books ጨምር":
        await update.message.reply_text(
            "📦 Bulk Books — መጀመሪያ ርዕስ/prefix ያስፍሩ:\n"
            "(ለምሳሌ: 'መጽሐፍ' ካሉ → መጽሐፍ 1, መጽሐፍ 2, ... ይሆናል)"
        )
        return BULK_BOOK_TITLE
    elif text == "➕ ግጥም ጨምር":
        await update.message.reply_text("📝 የግጥሙን ስም ያስፍሩ:")
        return ADD_LYRIC_TITLE
    elif text == "➕ Hall ልጥፍ ጨምር":
        await update.message.reply_text("🏛 የልጥፉን ካፕሽን ያስፍሩ (ወይም skip ይላኩ):")
        return ADD_HALL_CAPTION
    elif text == "📋 Feedbacks ይመልከቱ":
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT username, message, sent_at FROM feedback ORDER BY id DESC LIMIT 10"
            ).fetchall()
        if not rows:
            await update.message.reply_text("ምንም አስተያየት የለም።")
        else:
            for username, message, sent_at in rows:
                await update.message.reply_text(f"@{username}: {message}\n({sent_at})")
        return ADMIN_MENU
    elif text == "📢 Broadcast":
        await update.message.reply_text("📢 ለሁሉም ተጠቃሚዎች የሚላኩ ልጥፍ ያስፍሩ:")
        return BROADCAST_TEXT
    elif text == "🔙 ወደ ዋና ምናሌ":
        await update.message.reply_text("ዋና ምናሌ:", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return ADMIN_MENU


# ── Bulk songs ────────────────────────────────────────────────────────────────

async def bulk_song_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["bulk_song_prefix"] = update.message.text.strip()
    ctx.user_data["bulk_song_count"] = 0
    await update.message.reply_text(
        f"✅ Prefix: '{ctx.user_data['bulk_song_prefix']}'\n\n"
        "አሁን ሁሉንም የድምፅ ፋይሎች ይላኩ (ምንም ያህል).\n"
        "ሲጨርሱ /done ይላኩ።"
    )
    return BULK_SONG_FILES

async def bulk_song_files(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # /done ends the bulk session
    if update.message.text and update.message.text.strip() == "/done":
        count = ctx.user_data.get("bulk_song_count", 0)
        await update.message.reply_text(
            f"✅ {count} መዝሙሮች ተጨምረዋል!", reply_markup=ADMIN_KEYBOARD
        )
        return ADMIN_MENU

    if not update.message.audio and not update.message.voice:
        await update.message.reply_text("⚠️ ድምፅ ፋይል ይላኩ ወይም /done ይፃፉ።")
        return BULK_SONG_FILES

    fid = (update.message.audio or update.message.voice).file_id
    prefix = ctx.user_data.get("bulk_song_prefix", "መዝሙር")
    # Use the original filename as title if available, else prefix + number
    orig_name = ""
    if update.message.audio and update.message.audio.file_name:
        orig_name = os.path.splitext(update.message.audio.file_name)[0].strip()
    if not orig_name:
        ctx.user_data["bulk_song_count"] = ctx.user_data.get("bulk_song_count", 0) + 1
        orig_name = f"{prefix} {ctx.user_data['bulk_song_count']}"
    else:
        ctx.user_data["bulk_song_count"] = ctx.user_data.get("bulk_song_count", 0) + 1

    with get_conn() as conn:
        conn.execute("INSERT INTO songs (title, file_id) VALUES (%s, %s)", (orig_name, fid))
        conn.commit()
    await update.message.reply_text(f"✅ '{orig_name}' ተጨምሯል — ቀጥሉ ወይም /done ይፃፉ።")
    return BULK_SONG_FILES


# ── Bulk books ────────────────────────────────────────────────────────────────

async def bulk_book_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["bulk_book_prefix"] = update.message.text.strip()
    ctx.user_data["bulk_book_count"] = 0
    await update.message.reply_text(
        f"✅ Prefix: '{ctx.user_data['bulk_book_prefix']}'\n\n"
        "አሁን ሁሉንም PDF ፋይሎች ይላኩ (ምንም ያህል).\n"
        "ሲጨርሱ /done ይላኩ።"
    )
    return BULK_BOOK_FILES

async def bulk_book_files(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip() == "/done":
        count = ctx.user_data.get("bulk_book_count", 0)
        await update.message.reply_text(
            f"✅ {count} መጽሐፍቶች ተጨምረዋል!", reply_markup=ADMIN_KEYBOARD
        )
        return ADMIN_MENU

    if not update.message.document:
        await update.message.reply_text("⚠️ ሰነድ ፋይል ይላኩ ወይም /done ይፃፉ።")
        return BULK_BOOK_FILES

    fid = update.message.document.file_id
    prefix = ctx.user_data.get("bulk_book_prefix", "መጽሐፍ")
    orig_name = ""
    if update.message.document.file_name:
        orig_name = os.path.splitext(update.message.document.file_name)[0].strip()
    if not orig_name:
        ctx.user_data["bulk_book_count"] = ctx.user_data.get("bulk_book_count", 0) + 1
        orig_name = f"{prefix} {ctx.user_data['bulk_book_count']}"
    else:
        ctx.user_data["bulk_book_count"] = ctx.user_data.get("bulk_book_count", 0) + 1

    with get_conn() as conn:
        conn.execute("INSERT INTO books (title, file_id) VALUES (%s, %s)", (orig_name, fid))
        conn.commit()
    await update.message.reply_text(f"✅ '{orig_name}' ተጨምሯል — ቀጥሉ ወይም /done ይፃፉ።")
    return BULK_BOOK_FILES


# Add song
async def add_song_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["song_title"] = update.message.text
    await update.message.reply_text("🎵 አሁን የድምፅ ፋይሉን ይላኩ:")
    return ADD_SONG_FILE

async def add_song_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.audio and not update.message.voice:
        await update.message.reply_text("⚠️ እባክዎ ድምፅ ፋይል ይላኩ።")
        return ADD_SONG_FILE
    fid = (update.message.audio or update.message.voice).file_id
    title = ctx.user_data.get("song_title", "untitled")
    with get_conn() as conn:
        conn.execute("INSERT INTO songs (title, file_id) VALUES (%s, %s)", (title, fid))
        conn.commit()
    await update.message.reply_text(f"✅ '{title}' ተጨምሯል!", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


# Add book
async def add_book_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["book_title"] = update.message.text
    await update.message.reply_text("📖 አሁን PDF ፋይሉን ይላኩ:")
    return ADD_BOOK_FILE

async def add_book_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("⚠️ እባክዎ ሰነድ ፋይል ይላኩ።")
        return ADD_BOOK_FILE
    fid = update.message.document.file_id
    title = ctx.user_data.get("book_title", "untitled")
    with get_conn() as conn:
        conn.execute("INSERT INTO books (title, file_id) VALUES (%s, %s)", (title, fid))
        conn.commit()
    await update.message.reply_text(f"✅ '{title}' ተጨምሯል!", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


# Add lyric
async def add_lyric_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lyric_title"] = update.message.text
    await update.message.reply_text("📝 አሁን የግጥሙ ፎቶ ይላኩ:")
    return ADD_LYRIC_FILE

async def add_lyric_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ እባክዎ ፎቶ ይላኩ።")
        return ADD_LYRIC_FILE
    fid = update.message.photo[-1].file_id
    title = ctx.user_data.get("lyric_title", "untitled")
    with get_conn() as conn:
        conn.execute("INSERT INTO lyrics (title, file_id) VALUES (%s, %s)", (title, fid))
        conn.commit()
    await update.message.reply_text(f"✅ '{title}' ተጨምሯል!", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


# Add hall post
async def add_hall_caption(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    ctx.user_data["hall_caption"] = "" if text.lower() == "skip" else text
    await update.message.reply_text("🏛 አሁን ፎቶ ወይም ቪዲዮ ይላኩ (ወይም skip ላክ):")
    return ADD_HALL_MEDIA

async def add_hall_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caption = ctx.user_data.get("hall_caption", "")
    text = update.message.text or ""
    if text.lower() == "skip":
        mtype, fid = "text", None
    elif update.message.photo:
        mtype, fid = "photo", update.message.photo[-1].file_id
    elif update.message.video:
        mtype, fid = "video", update.message.video.file_id
    else:
        await update.message.reply_text("⚠️ ፎቶ ወይም ቪዲዮ ይላኩ፣ ወይም skip ይፃፉ።")
        return ADD_HALL_MEDIA
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO hall_posts (caption, media_type, file_id) VALUES (%s, %s, %s)",
            (caption, mtype, fid)
        )
        conn.commit()
    await update.message.reply_text("✅ Hall ልጥፍ ተጨምሯል!", reply_markup=ADMIN_KEYBOARD)
    return ADMIN_MENU


# Broadcast
async def broadcast_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    with get_conn() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    sent, failed = 0, 0
    for (uid,) in users:
        try:
            await ctx.bot.send_message(uid, f"📢 {text}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"✅ Broadcast ተልኳል!\nተሳካ: {sent} | አልተሳካም: {failed}",
        reply_markup=ADMIN_KEYBOARD
    )
    return ADMIN_MENU


# Reply to feedback sender
async def cb_reply_to_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    target_id = int(query.data.split(":")[1])
    ctx.user_data["reply_target"] = target_id
    await query.message.reply_text("↩ መልስዎን ያስፍሩ:")
    return REPLY_TO_USER

async def send_reply_to_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target_id = ctx.user_data.get("reply_target")
    if target_id:
        try:
            await ctx.bot.send_message(target_id, f"📨 ከአስተዳዳሪ:\n\n{update.message.text}")
            await update.message.reply_text("✅ መልስ ተልኳል!")
        except Exception as e:
            await update.message.reply_text(f"❌ መልስ አልተላከም: {e}")
    return ConversationHandler.END


# Cancel
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ተሰርዟል።", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ─── aiohttp web server (required by Render free tier) ────────────────────────

async def health(request):
    return web.Response(text="OK - Awada bot running")

async def self_ping_loop():
    """Ping own /ping endpoint every 10 minutes to prevent Render from sleeping."""
    port = int(os.environ.get("PORT", 10000))
    url = f"http://0.0.0.0:{port}/ping"
    await asyncio.sleep(30)  # wait for web server to start first
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    logger.info(f"[self-ping] {resp.status}")
        except Exception as e:
            logger.warning(f"[self-ping] failed: {e}")
        await asyncio.sleep(600)  # every 10 minutes


async def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/ping", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"[web] Listening on port {port}")


# ─── Main ──────────────────────────────────────────────────────────────────────

async def run():
    # Start web server first so Render sees an open port
    await start_web_server()
    asyncio.create_task(self_ping_loop())

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Auto-register every user silently on any message (runs first, non-blocking)
    app.add_handler(MessageHandler(filters.ALL, auto_register), group=-1)

    # Main menu handlers (plain text buttons)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🎵 መዝሙር$"), menu_songs))
    app.add_handler(MessageHandler(filters.Regex("^📖 Books$"), menu_books))
    app.add_handler(MessageHandler(filters.Regex("^📝 የመዝሙር ግጥሞች$"), menu_lyrics))
    app.add_handler(MessageHandler(filters.Regex("^🏛 አዳራሻችን$"), menu_hall))
    app.add_handler(MessageHandler(filters.Regex("^❓ Help$"), menu_help))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(cb_song,  pattern="^song:"))
    app.add_handler(CallbackQueryHandler(cb_book,  pattern="^book:"))
    app.add_handler(CallbackQueryHandler(cb_lyric, pattern="^lyric:"))

    # Feedback conversation
    feedback_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 አስተያየት$"), menu_feedback)],
        states={FEEDBACK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(feedback_conv)

    # Admin reply-to-user conversation (callback → reply)
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_reply_to_user, pattern="^reply:")],
        states={REPLY_TO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply_to_user)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(reply_conv)

    # Admin conversation
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU:       [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADD_SONG_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_song_title)],
            ADD_SONG_FILE:    [MessageHandler(filters.AUDIO | filters.VOICE, add_song_file)],
            ADD_BOOK_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_book_title)],
            ADD_BOOK_FILE:    [MessageHandler(filters.Document.ALL, add_book_file)],
            ADD_LYRIC_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lyric_title)],
            ADD_LYRIC_FILE:   [MessageHandler(filters.PHOTO, add_lyric_file)],
            ADD_HALL_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_hall_caption)],
            ADD_HALL_MEDIA:   [MessageHandler(filters.PHOTO | filters.VIDEO | filters.TEXT, add_hall_media)],
            BROADCAST_TEXT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
            BULK_SONG_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_song_title)],
            BULK_SONG_FILES:  [
                MessageHandler(filters.AUDIO | filters.VOICE, bulk_song_files),
                CommandHandler("done", bulk_song_files),
            ],
            BULK_BOOK_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_book_title)],
            BULK_BOOK_FILES:  [
                MessageHandler(filters.Document.ALL, bulk_book_files),
                CommandHandler("done", bulk_book_files),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(admin_conv)

    # Run bot using async context manager (works with Python 3.14, no get_event_loop)
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Keep running until cancelled
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(run())
