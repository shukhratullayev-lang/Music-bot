import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import yt_dlp

BOT_TOKEN = "8732426720:AAHOB5F8irHkAfboBPt5V5bEdU-ZaT1v5iQ"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

SEARCH_CACHE = {}

def format_duration(seconds: int) -> str:
    if not seconds:
        return "0:00"
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"

@dp.message(F.text)
async def search_music(message: Message):
    query = message.text.strip()
    if query.startswith("/"):
        return

    search_term = f"ytsearch5:{query} audio"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'socket_timeout': 30,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }

    status_msg = await message.answer("🔍 Qidirilmoqda...")

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_term, download=False))
            
        results = info.get('entries', [])
        
        if not results:
            await status_msg.edit_text("❌ Qo'shiq topilmadi.")
            return

        SEARCH_CACHE[message.from_user.id] = results
        
        text = "<b>🔍 Qidiruv natijasi:</b>\n\n"
        keyboard_buttons = []
        
        for i, item in enumerate(results[:5], 1):
            title = item.get('title', 'Nomaʼlum')
            duration = format_duration(item.get('duration', 0))
            text += f"<b>{i}.</b> {title} <code>({duration})</code>\n"
            keyboard_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"dl_{i-1}"))

        keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        await status_msg.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Qidirishda xatolik: {e}")
        await status_msg.edit_text("⚠️ Qidirishda xatolik yuz berdi. Qaytadan urinib ko'ring.")

@dp.callback_query(F.data.startswith("dl_"))
async def download_music(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in SEARCH_CACHE:
        await callback.answer("Eski natija, qaytadan qo'shiq qidiring!", show_alert=True)
        return

    index = int(callback.data.split("_")[1])
    results = SEARCH_CACHE[user_id]
    
    if index >= len(results):
        await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return

    item = results[index]
    url = item.get('url') or f"https://www.youtube.com/watch?v={item.get('id')}"
    title = item.get('title', 'audio')

    await callback.message.edit_text(f"📥 <b>{title}</b> yuklab olinmoqda, biroz kuting...")

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }

    try:
        loop = asyncio.get_event_loop()
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dict)
                return os.path.splitext(filename)[0] + ".mp3"

        file_path = await loop.run_in_executor(None, download)

        if os.path.exists(file_path):
            from aiogram.types import FSInputFile
            audio_file = FSInputFile(file_path)
            await callback.message.answer_audio(audio=audio_file, caption=f"🎵 {title}")
            await callback.message.delete()
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await callback.message.edit_text("❌ Faylni yuklab bo'lmadi.")

    except Exception as e:
        logger.error(f"Yuklashda xatolik: {e}")
        await callback.message.edit_text("⚠️ Yuklab olishda xatolik yuz berdi.")

# Render port talabini bajarish uchun aiohttp web server
async def handle(request):
    return web.Response(text="Bot is running!")

from aiohttp import web

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
