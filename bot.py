import os
import logging
import asyncio
import re
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.constants import ParseMode

# O'zingizdagi mavjud fayllardan import qilamiz
from database import Database
from utils import (
    check_user_subscription,
    format_channels_list
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv('ADMIN_ID').split(',')]
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
BOT_USERNAME = "@AF_kino_bot"  # O'zingizni bot usernameni shu yerga yozing

# Initialize database
db = Database()

# Conversation states
WAITING_FOR_VIDEO = 1
WAITING_FOR_CHANNEL_ID = 2
WAITING_FOR_CHANNEL_USERNAME = 3
WAITING_FOR_DELETE_CODE = 4

# Admin tugmalari matnlari
BTN_ADD_MOVIE = "➕ Kino qo'shish"
BTN_DEL_MOVIE = "🗑 Kino o'chirish"
BTN_STATS = "📊 Statistika"
BTN_LIST_MOVIES = "🎬 Kinolar ro'yxati"
BTN_MANAGE_CHANNELS = "📢 Kanallar boshqaruvi"
BTN_ADD_CHANNEL = "➕ Kanal qo'shish"
BTN_BACK = "◀️ Orqaga"

# ===== HELPER FUNCTIONS =====

def get_admin_keyboard():
    """Admin uchun Reply Keyboard"""
    keyboard = [
        [KeyboardButton(BTN_ADD_MOVIE), KeyboardButton(BTN_DEL_MOVIE)], # O'chirish tugmasi qo'shildi
        [KeyboardButton(BTN_STATS), KeyboardButton(BTN_LIST_MOVIES)],
        [KeyboardButton(BTN_MANAGE_CHANNELS)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
def clean_caption(text):
    """
    Captiondagi link va usernamelarni tozalab, o'rniga BOT_USERNAME qo'yadi.
    """
    if not text:
        return f"{BOT_USERNAME}"

    # 1. Havolalar (http, https, t.me) ni almashtirish
    text = re.sub(r'(https?://\S+|t\.me/\S+)', BOT_USERNAME, text)

    # 2. Boshqa username (@channel) larni almashtirish (bot o'zinikidan tashqari)
    # Bu regex matn ichidagi @bilan boshlanadigan so'zlarni topadi
    text = re.sub(r'@(?!\s)[a-zA-Z0-9_]+', BOT_USERNAME, text)

    return text

def get_next_movie_code():
    """Navbatdagi kino kodini raqam shaklida qaytaradi (1, 2, 3...)"""
    # Bazadagi kinolar sonini olib, unga 1 qo'shamiz
    # Agar bazada oxirgi IDni olish imkoni bo'lsa, o'shani ishlatish to'g'riroq bo'ladi
    # Hozircha sodda yechim:
    count = db.get_movies_count()
    return str(count + 1)

# ===== USER HANDLERS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user

    # Add user to database
    db.add_user(user.id)
    db.update_user_activity(user.id)

    # Check if admin
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            f"👋 Assalomu alaykum, Admin!\n\n"
            f"🎬 <b>Boshqaruv Paneli</b>\n",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    else:
        # Check subscription
        required_channels = db.get_required_channels()
        if required_channels:
            not_subscribed = await check_user_subscription(context.bot, user.id, required_channels)
            if not_subscribed:
                message = format_channels_list(not_subscribed)
                keyboard = [[InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subs")]]
                await update.message.reply_text(
                    message,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    disable_web_page_preview=True
                )
                return

        await update.message.reply_text(
            f"👋 Assalomu alaykum <b>{user.first_name}</b>!\n\n"
            f"🎬 Kino kodini yuboring (masalan: <code>45</code>)\n"
            f"yoki kino nomini yozing.",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove()
        )

async def check_subs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    # Bazani thread orqali chaqiramiz (tezyurar usul)
    required_channels = await asyncio.to_thread(db.get_required_channels)

    if required_channels:
        # ASOSIY TUZATISH: Bu yerda await qo'shildi
        not_subscribed = await check_user_subscription(context.bot, user.id, required_channels)
        if not_subscribed:
            await query.message.reply_text(
                "❌ Hali hamma kanallarga a'zo bo'lmadingiz!",
                # ephemeral=True eski versiyalarda xato berishi mumkin, shuning uchun olib tashladim
            )
            return

    await query.message.delete()
    await query.message.reply_text("✅ Obuna tasdiqlandi!")
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip() if update.message.text else ""

    if user.id == ADMIN_ID and text in [BTN_ADD_MOVIE, BTN_STATS, BTN_LIST_MOVIES, BTN_MANAGE_CHANNELS]:
        return

    # Bazani async to_thread orqali chaqiramiz (Bot qotib qolmasligi uchun)
    await asyncio.to_thread(db.update_user_activity, user.id)

    required_channels = await asyncio.to_thread(db.get_required_channels)
    if required_channels and user.id != ADMIN_ID:
        # ASOSIY TUZATISH: Bu yerda await qo'shildi
        not_subscribed = await check_user_subscription(context.bot, user.id, required_channels)
        if not_subscribed:
            message = format_channels_list(not_subscribed)
            keyboard = [[InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subs")]]
            await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    if text.isdigit():
        movie_code = text
        # Bazani async to_thread orqali chaqiramiz
        movie = await asyncio.to_thread(db.get_movie_by_code, movie_code)

        if movie:
            try:
                # utils dagi clean_caption dan foydalanamiz
                from utils import clean_caption
                original_caption = movie.get('caption', '')
                caption = clean_caption(original_caption, BOT_USERNAME)

                await context.bot.send_video(
                    chat_id=user.id,
                    video=movie['video_id'],
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                # Ko'rishlar sonini async chaqiramiz
                asyncio.create_task(asyncio.to_thread(db.increment_views, movie_code))
            except Exception as e:
                logger.error(f"Error: {e}")
        else:
            await update.message.reply_text("❌ Kino topilmadi.")
    else:
        # Qidiruvni async chaqiramiz
        movies = await asyncio.to_thread(db.search_movie_by_name, text)
        if movies:
            # ... (qidiruv natijalarini chiqarish kodini shu yerda qoldiring)
            pass
# ===== ADMIN HANDLERS =====

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistikani ko'rsatish"""
    if update.effective_user.id != ADMIN_ID: return

    total_users = db.get_users_count()
    total_movies = db.get_movies_count()
    active_today = db.get_active_users_today()

    msg = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {total_users}\n"
        f"⚡️ Bugun faol: {active_today}\n"
        f"🎬 Kinolar soni: {total_movies}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def admin_list_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kinolar ro'yxati"""
    if update.effective_user.id != ADMIN_ID: return

    movies = db.get_all_movies(20)
    if not movies:
        await update.message.reply_text("📭 Kinolar yo'q")
        return

    text = "🎬 <b>Oxirgi 20 ta kino:</b>\n\n"
    for m in movies:
        text += f"• {m['video_name']} (Kod: <code>{m['movie_code']}</code>)\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def admin_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanallar menyusi"""
    if update.effective_user.id != ADMIN_ID: return

    channels = db.get_all_channels()
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    keyboard = []

    if channels:
        for ch in channels:
            text += f"• {ch.get('channel_username', 'ID: ' + str(ch['channel_id']))}\n"
            # O'chirish tugmasi
            keyboard.append([InlineKeyboardButton(f"🗑 O'chirish: {ch.get('channel_username', 'ID')}", callback_data=f"del_ch_{ch['channel_id']}")])
    else:
        text += "Kanallar yo'q."

    # --- O'ZGARGAYOTGAN JOY: Qo'shish tugmasini inline qilib qo'shamiz ---
    keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_new_channel")])
    # --------------------------------------------------------------------

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
# ===== DELETE MOVIE CONVERSATION =====

async def start_delete_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'chirish jarayonini boshlash"""
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END

    await update.message.reply_text(
        "🗑 <b>Kino o'chirish</b>\n\n"
        "O'chirmoqchi bo'lgan kino KODINI yuboring (masalan: 45).\n"
        "❌ Bekor qilish: /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_FOR_DELETE_CODE

async def receive_delete_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kod kelganda o'chirish"""
    code = update.message.text.strip()

    # Bazadan o'chiramiz (Async chaqiramiz)
    is_deleted = await asyncio.to_thread(db.delete_movie, code)

    if is_deleted:
        await update.message.reply_text(
            f"✅ <b>Kino o'chirildi!</b>\n"
            f"Kod: {code}\n\n"
            f"<i>Eslatma: Kanalga joylangan post o'chmaydi, lekin botdan qidirganda chiqmaydi.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            f"❌ <b>Xatolik!</b>\n"
            f"Bunday kodli kino topilmadi: {code}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )

    return ConversationHandler.END

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return

    data = query.data
    if data.startswith("del_ch_"):
        channel_id = int(data.split("_")[-1])
        if db.delete_channel(channel_id):
            await query.answer("Kanal o'chirildi!")
            await query.message.delete()
        else:
            await query.answer("Xatolik!")

# ===== ADD MOVIE CONVERSATION =====

async def start_add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END

    await update.message.reply_text(
        "🎬 <b>Kino qo'shish</b>\n\n"
        "Kinoni (video fayl) yuboring.\n"
        "Tagiga yozilgan caption (izoh) saqlanib qoladi va linklar tozalanadi.\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_FOR_VIDEO

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Video borligini tekshirish
    if not update.message.video:
        await update.message.reply_text("❌ Iltimos, video yuboring! Yoki bekor qilish uchun /cancel ni bosing.")
        return WAITING_FOR_VIDEO

    video = update.message.video
    file_id = video.file_id

    # 1. Nomni aniqlash
    raw_caption = update.message.caption or ""
    if raw_caption:
        # Nom sifatida captionning birinchi qatorini olamiz
        video_name = raw_caption.split('\n')[0][:100]
    else:
        video_name = video.file_name or "Nomsiz kino"

    # 2. Captionni tozalash
    from utils import clean_caption
    clean_text = clean_caption(raw_caption, BOT_USERNAME)

    try:
        # 3. Kino kodini olish
        movie_code = await asyncio.to_thread(get_next_movie_code)

        # 4. Bazaga saqlash
        success = await asyncio.to_thread(db.add_movie, movie_code, file_id, video_name, clean_text)

        if success:
             # Kanalga yuborish
            channel_caption = f"{clean_text}\n\n🆔 Kod: {movie_code}\n🤖 {BOT_USERNAME}"

            await context.bot.send_video(
                chat_id=CHANNEL_ID,
                video=file_id,
                caption=channel_caption,
                parse_mode=ParseMode.HTML
            )

            # Admin uchun javob (Menyuni chiqarmaymiz, keyingi videoni kutamiz)
            await update.message.reply_text(
                f"✅ <b>Kino qo'shildi!</b>\n\n"
                f"🆔 Kod: <code>{movie_code}</code>\n"
                f"🎬 Nom: {video_name}\n\n"
                f"<i>Kanalga joylandi.</i>\n"
                f"➡️ <b>Navbatdagi videoni yuborishingiz mumkin...</b>\n"
                f"❌ To'xtatish uchun: /cancel",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove() # Klaviatura yo'qoladi, admin ketma-ket tashlayveradi
            )
            # MUHIM O'ZGARISH: END emas, WAITING_FOR_VIDEO qaytadi
            return WAITING_FOR_VIDEO

        else:
            await update.message.reply_text("❌ Bazaga yozishda xatolik! Qaytadan urinib ko'ring.", reply_markup=ReplyKeyboardRemove())
            return WAITING_FOR_VIDEO

    except Exception as e:
        logger.error(f"Add movie error: {e}")
        await update.message.reply_text(f"❌ Xatolik: {e}\nDavom etishingiz mumkin.", reply_markup=ReplyKeyboardRemove())
        return WAITING_FOR_VIDEO
async def start_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END

    # Agar tugma orqali kelgan bo'lsa
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "📢 <b>Kanal qo'shish</b>\n\n"
            "Kanal ID sini yuboring (masalan: -100123456789).",
            parse_mode=ParseMode.HTML
        )
    # Agar matn orqali kelgan bo'lsa (eski usul qolishi uchun)
    else:
        await update.message.reply_text(
            "📢 <b>Kanal qo'shish</b>\n\n"
            "Kanal ID sini yuboring (masalan: -100123456789).",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove()
        )

    return WAITING_FOR_CHANNEL_ID
async def receive_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        c_id = int(update.message.text)
        context.user_data['new_ch_id'] = c_id
        await update.message.reply_text("Endi kanal usernamesini yuboring (masalan: @kinolar):")
        return WAITING_FOR_CHANNEL_USERNAME
    except:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak!")
        return WAITING_FOR_CHANNEL_ID

async def receive_channel_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text
    c_id = context.user_data['new_ch_id']

    if db.add_channel(c_id, username):
        await update.message.reply_text(f"✅ Kanal qo'shildi: {username}", reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text("❌ Xatolik!", reply_markup=get_admin_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        reply_markup = get_admin_keyboard()
    else:
        reply_markup = ReplyKeyboardRemove()

    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=reply_markup)
    return ConversationHandler.END

# ===== MAIN =====

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Admin Conversations
    movie_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_ADD_MOVIE}$") & filters.User(ADMIN_ID), start_add_movie)],
        states={
            WAITING_FOR_VIDEO: [MessageHandler(filters.VIDEO, receive_video)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
        )

    channel_conv = ConversationHandler(
            entry_points=[
                # Eski matnli buyruq
                MessageHandler(filters.Regex(f"^{BTN_ADD_CHANNEL}$") & filters.User(ADMIN_ID), start_add_channel),
                # --- YANGI QO'SHILGAN QATOR: Inline tugma uchun ---
                CallbackQueryHandler(start_add_channel, pattern="^add_new_channel$")
            ],
            states={
                WAITING_FOR_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_id)],
                WAITING_FOR_CHANNEL_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_user)]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
    # Delete Movie Conversation
    del_movie_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_DEL_MOVIE}$") & filters.User(ADMIN_ID), start_delete_movie)],
        states={
            WAITING_FOR_DELETE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_delete_code)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )


    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_subs_callback, pattern="^check_subs$"))
    application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern="^del_ch_"))
    # Buni boshqa handlerlar qatoriga qo'shing
    application.add_handler(del_movie_conv)
    # Admin Menu Handlers
    application.add_handler(movie_conv)
    application.add_handler(channel_conv) # Agar ishlatmoqchi bo'lsangiz
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_STATS}$") & filters.User(ADMIN_ID), admin_stats))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_LIST_MOVIES}$") & filters.User(ADMIN_ID), admin_list_movies))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_MANAGE_CHANNELS}$") & filters.User(ADMIN_ID), admin_manage_channels))

    # General Message Handler (Must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi...")
    application.run_polling()

if __name__ == '__main__':
    main()
