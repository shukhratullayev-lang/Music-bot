import os
import glob
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import yt_dlp

BOT_TOKEN = "8732426720:AAH7YNVEXM9Ag03HmUXHJGG9y3Byt-TsXy4"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

SEARCH_CACHE = {}

def format_duration(seconds: int) -> str:
    if not seconds:
        return ""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"

@dp.message(F.text)
async def search_music(message: Message):
    query = message.text.strip()
    if query.startswith("/"):
        return
        
    # Qidiruvni tezlashtirish va aniqligini oshirish uchun 'audio' so'zi qo'shildi
    search_term = f"ytsearch5:{query} audio"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_term, download=False))

        results = info.get('entries', [])

        if not results:
            await message.answer("❌ Qo'shiq topilmadi.")
            return

        user_id = message.from_user.id
        SEARCH_CACHE[user_id] = results

        text_lines = [f"<b>🔍 Qidiruv natijasi: {query}</b>\n"]
        row1 = []
        row2 = []

        for idx, track in enumerate(results, start=1):
            title = track.get('title', 'Noma\'lum')
            for word in ['Official Music Video', 'Official Video', 'Lyrics', '(Official Audio)', 'Official']:
                title = title.replace(word, '')
            title = title.strip(' -|')
            
            duration = format_duration(track.get('duration', 0))
            
            text_lines.append(f"<b>{idx}.</b> <i>{title}</i> {duration}")
            
            btn = InlineKeyboardButton(text=str(idx), callback_data=f"dl_{idx-1}")
            if len(row1) < 5:
                row1.append(btn)
            else:
                row2.append(btn)

        keyboard = []
        if row1:
            keyboard.append(row1)
        if row2:
            keyboard.append(row2)

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer("\n".join(text_lines), reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Qidiruvda xatolik: {e}")
        await message.answer("⚠️ Qidiruvda xatolik yuz berdi.")

@dp.callback_query(F.data.startswith("dl_"))
async def download_music(callback: CallbackQuery):
    await callback.answer("⚡ Tez yuklanmoqda...", show_alert=False)

    user_id = callback.from_user.id
    idx = int(callback.data.split("_")[1])

    if user_id not in SEARCH_CACHE or idx >= len(SEARCH_CACHE[user_id]):
        await callback.message.answer("⚠️ Ma'lumot eskirgan, qo'shiqni qaytadan qidiring.")
        return

    track = SEARCH_CACHE[user_id][idx]
    video_id = track.get('id')
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    title = track.get('title', 'Audio')
    for word in ['Official Music Video', 'Official Video', 'Lyrics', '(Official Audio)', 'Official']:
        title = title.replace(word, '')
    title = title.strip(' -|')

    outtmpl = os.path.join(DOWNLOAD_DIR, f"%(id)s.%(ext)s")
    
    # Kichik hajmli va tez yuklanadigan formatga sozlandi
    ydl_opts = {
        'format': 'worstaudio[ext=m4a]/bestaudio[ext=m4a]/worstaudio/best',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        loop = asyncio.get_event_loop()
        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        await loop.run_in_executor(None, download_sync)

        file_path = None
        for ext in ['m4a', 'mp3', 'webm', 'opus']:
            possible_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
            if os.path.exists(possible_path):
                file_path = possible_path
                break
        
        if not file_path:
            files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
            if files:
                file_path = max(files, key=os.path.getctime)

        if file_path and os.path.exists(file_path):
            audio = FSInputFile(file_path)
            await callback.message.answer_audio(
                audio=audio, 
                title=title,
                caption=f"🎧 {title}"
            )
            os.remove(file_path)
        else:
            await callback.message.answer("⚠️ Faylni yuklab bo'lmadi.")

    except Exception as e:
        logger.error(f"Yuklashda xatolik: {e}")
        await callback.message.answer("⚠️ Yuklab olishda xatolik yuz berdi.")

async def main():
    print("⚡ Bot tezkor rejimda ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())