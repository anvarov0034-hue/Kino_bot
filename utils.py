import re
from telegram.constants import ParseMode

async def check_user_subscription(bot, user_id, required_channels):
    """
    Foydalanuvchi majburiy kanallarga a'zo ekanligini tekshiradi (Async).
    Qaytaradi: A'zo bo'lmagan kanallar ro'yxati.
    """
    not_subscribed = []

    for channel in required_channels:
        channel_id = channel['channel_id']
        try:
            # Telegram API orqali tekshirish (Await shart!)
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)

            # Agar foydalanuvchi chiqib ketgan, haydalgan yoki a'zo bo'lmasa
            if member.status in ['left', 'kicked', 'banned']:
                not_subscribed.append(channel)
        except Exception as e:
            # Agar bot kanalga admin bo'lmasa yoki xatolik bo'lsa
            # Xavfsizlik uchun a'zo emas deb hisoblaymiz
            print(f"Error checking subscription for {channel_id}: {e}")
            not_subscribed.append(channel)

    return not_subscribed

def format_channels_list(channels):
    """
    A'zo bo'lish kerak bo'lgan kanallar ro'yxatini chiroyli matn qilib qaytaradi.
    """
    text = "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"

    for channel in channels:
        username = channel.get('channel_username')
        # Agar username bo'lsa @ bilan, bo'lmasa link qilib ko'rsatamiz
        if username:
            if username.startswith('@'):
                link = username
            else:
                link = f"@{username}"
            text += f"➕ {link}\n"
        else:
            # Username yo'q bo'lsa (yopiq kanal), ID ko'rsatilmaydi, lekin admin to'g'irlashi kerak
            text += f"➕ <a href=\"tg://user?id={str(channel['channel_id'])[4:]}\">Kanalga o'tish</a>\n"

    text += "\n✅ <i>Obuna bo'lgach, «Tekshirish» tugmasini bosing.</i>"
    return text

def clean_caption(caption, bot_username):
    """
    Captiondagi barcha havolalarni va begona usernamelarni
    bot usernamega almashtiradi.
    """
    if not caption:
        return f"\n\n🤖 {bot_username}"

    # 1. Havolalar (http, https, t.me) ni bot usernamega almashtirish
    # Regex: http yoki https bilan boshlanib, bo'sh joygacha davom etadigan so'zlar
    text = re.sub(r'(https?://\S+|t\.me/\S+)', bot_username, caption)

    # 2. @mentions ni almashtirish (lekin botning o'zini o'zgartirmaslik kerak)
    # Regex: @ bilan boshlanadigan, lekin bizning bot username bo'lmagan so'zlar
    # Eslatma: Bu yerda oddiygina barcha @soz larni almashtiramiz
    text = re.sub(r'@(?!\s)[a-zA-Z0-9_]+', bot_username, text)

    # Ortiqcha bo'shliqlarni tozalash
    text = text.strip()

    # Oxiriga bot usernamesini chiroyli qilib qo'shish (agar matn ichida bo'lmasa)
    if bot_username not in text:
        text += f"\n\n🤖 {bot_username}"

    return text

def format_movie_info(movie):
    """
    Admin panel yoki qidiruv uchun kino haqida qisqa ma'lumot
    """
    return (
        f"🎬 <b>{movie['video_name']}</b>\n"
        f"🆔 Kod: <code>{movie['movie_code']}</code>\n"
        f"👁 Ko'rishlar: {movie['views']}"
    )
