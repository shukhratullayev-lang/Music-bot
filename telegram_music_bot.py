import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ.get("8732426720:AAGtKFquKQWy91z7XndBQw37T1_x7HlLpXU")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

PORT = int(os.environ.get("PORT", "10000"))

# Render odatda buni beradi
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not RENDER_EXTERNAL_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL is not set!")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_EXTERNAL_URL.rstrip("/") + WEBHOOK_PATH

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

executor = ThreadPoolExecutor(max_workers=5)

# user_id -> search results
SEARCH_CACHE = {}


# =========================================================
# HELPERS
# =========================================================

def format_duration(seconds):
    if not seconds:
        return "0:00"

    try:
        seconds = int(float(seconds))
    except (ValueError, TypeError):
        return "0:00"

    minutes = seconds // 60
    secs = seconds % 60

    return f"{minutes}:{secs:02d}"


# =========================================================
# START
# =========================================================

@dp.message(F.text == "/start")
async def start_command(message: Message):

    await message.answer(
        "🎵 <b>Welcome to Music Bot!</b>\n\n"
        "Send me a song title or artist name and I will search SoundCloud."
    )


# =========================================================
# SEARCH
# =========================================================

@dp.message(F.text)
async def search_music(message: Message):

    query = message.text.strip()

    if not query or query.startswith("/"):
        return

    status_msg = await message.answer("🔎 Searching...")

    search_term = f"scsearch5:{query}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "socket_timeout": 30,
        "skip_download": True,
    }

    try:

        loop = asyncio.get_running_loop()

        def search():

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(
                    search_term,
                    download=False
                )

        info = await loop.run_in_executor(
            executor,
            search
        )

        results = info.get("entries", [])

        results = [
            x for x in results
            if x and x.get("webpage_url")
        ]

        if not results:

            await status_msg.edit_text(
                "❌ No tracks found.\n\n"
                "Try another song or artist."
            )

            return

        # faqat 5 ta natija
        results = results[:5]

        SEARCH_CACHE[message.from_user.id] = results

        text = "🎵 <b>Search Results</b>\n\n"

        buttons = []

        for i, item in enumerate(results):

            title = item.get("title", "Unknown")

            duration = format_duration(
                item.get("duration")
            )

            # Telegram HTML muammosidan saqlanish uchun
            title = (
                title
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            text += (
                f"<b>{i + 1}.</b> "
                f"{title} "
                f"<i>({duration})</i>\n"
            )

            buttons.append(
                InlineKeyboardButton(
                    text=str(i + 1),
                    callback_data=f"dl:{i}"
                )
            )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[buttons]
        )

        await status_msg.edit_text(
            text,
            reply_markup=keyboard
        )

    except Exception as e:

        logger.exception("Search error")

        await status_msg.edit_text(
            "❌ Search error.\n"
            "Please try again."
        )


# =========================================================
# DOWNLOAD
# =========================================================

@dp.callback_query(F.data.startswith("dl:"))
async def download_music(callback: CallbackQuery):

    user_id = callback.from_user.id

    results = SEARCH_CACHE.get(user_id)

    if not results:

        await callback.answer(
            "Search session expired. Search again.",
            show_alert=True
        )

        return

    try:
        index = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):

        await callback.answer(
            "Invalid selection.",
            show_alert=True
        )

        return

    if index < 0 or index >= len(results):

        await callback.answer(
            "Invalid track.",
            show_alert=True
        )

        return

    item = results[index]

    url = item.get("webpage_url")

    title = item.get(
        "title",
        "audio"
    )

    if not url:

        await callback.message.edit_text(
            "❌ Track URL not found."
        )

        return

    await callback.answer()

    await callback.message.edit_text(
        f"⬇️ <b>Downloading...</b>\n\n"
        f"{title}"
    )

    # filename
    output_template = os.path.join(
        DOWNLOAD_DIR,
        "%(id)s.%(ext)s"
    )

    ydl_opts = {
        "format": "bestaudio/best",

        "outtmpl": output_template,

        "quiet": True,
        "no_warnings": True,

        "socket_timeout": 60,

        # Postprocessing yo'q.
        # Shu bilan ffmpeg majburiy bo'lmaydi.
        "noplaylist": True,

        "retries": 3,

        "fragment_retries": 3,
    }

    try:

        loop = asyncio.get_running_loop()

        def download():

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(
                    url,
                    download=True
                )

                filename = ydl.prepare_filename(info)

                return filename

        file_path = await loop.run_in_executor(
            executor,
            download
        )

        if not os.path.exists(file_path):

            raise FileNotFoundError(
                "Downloaded file does not exist"
            )

        logger.info(
            "Downloaded: %s",
            file_path
        )

        await callback.message.answer_audio(
            audio=FSInputFile(file_path),
            caption=f"🎵 {title}"
        )

        await callback.message.delete()

        # delete local file
        try:
            os.remove(file_path)
        except Exception:
            logger.warning(
                "Could not remove file: %s",
                file_path
            )

    except yt_dlp.utils.DownloadError as e:

        error_text = str(e)

        logger.error(
            "yt-dlp download error: %s",
            error_text
        )

        # DRM bo'lsa
        if "DRM" in error_text or "drm" in error_text:

            await callback.message.edit_text(
                "❌ This track is DRM protected "
                "and cannot be downloaded.\n\n"
                "Please choose another track."
            )

        else:

            await callback.message.edit_text(
                "❌ Failed to download this track.\n\n"
                "Please choose another result."
            )

    except Exception as e:

        logger.exception(
            "Download error"
        )

        await callback.message.edit_text(
            "❌ Download failed.\n"
            "Please try another track."
        )


# =========================================================
# WEB SERVER
# =========================================================

async def health_check(request):

    return web.Response(
        text="Music Bot is running! 🎵"
    )


# =========================================================
# STARTUP / SHUTDOWN
# =========================================================

async def on_startup(app):

    logger.info(
        "Setting Telegram webhook: %s",
        WEBHOOK_URL
    )

    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )

    logger.info(
        "Webhook successfully configured."
    )


async def on_shutdown(app):

    logger.info(
        "Removing Telegram webhook..."
    )

    await bot.delete_webhook()

    await bot.session.close()

    executor.shutdown(
        wait=False
    )


# =========================================================
# MAIN
# =========================================================

def main():

    app = web.Application()

    # Render health check
    app.router.add_get(
        "/",
        health_check
    )

    # Telegram webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )

    webhook_handler.register(
        app,
        path=WEBHOOK_PATH
    )

    setup_application(
        app,
        dp,
        bot=bot
    )

    app.on_startup.append(
        on_startup
    )

    app.on_shutdown.append(
        on_shutdown
    )

    logger.info(
        "Starting web server on port %s",
        PORT
    )

    web.run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":
    main()
