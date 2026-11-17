import os
import re
import html
import asyncio
import traceback
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, 
    InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
from telegram.request import HTTPXRequest
from database import init_db, SessionLocal, UserProfile, Position

# پاک کردن پروکسی‌های کش شده محیطی
for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(k, None)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

os.makedirs("resumes", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

# ⚙️ تنظیمات لینک‌های شخصی
SUPPORT_TELEGRAM_ID = "HaniehSaedi"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@HonisHub"

# تعریف مراحل ساخت پروفایل
(
    RESUME, DEGREE, FIELD, CUSTOM_FIELD, 
    COUNTRY, CUSTOM_COUNTRY, HAS_LANG, 
    LANG_TYPE, CUSTOM_LANG_TYPE, LANG_SCORE
) = range(10)

BACK_BTN = "🔙 بازگشت به منو اصلی"

# ----------------- کیبوردهای منو و مراحل (مجهز به اموجی) -----------------
MAIN_MENU_KEYBOARD = [
    ['📤 ارسال پوزیشن', '👤 پروفایل من'],
    ['💾 پوزیشن های ذخیره شده', '✅ پوزیشن های اپلای شده'],
    ['💬 پشتیبانی', "▶️ یوتیوب Honi's Hub"],
    ['✨ بهبود رزومه (به‌زودی)', '📝 نگارش انگیزه نامه (به‌زودی)']
]

DEGREE_KEYBOARD = [
    ['🎓 کارشناسی', '🎓 کارشناسی ارشد'],
    ['🎓 دکتری', '🎓 پست دکتری'],
    [BACK_BTN]
]

FIELD_KEYBOARD = [
    ['💻 مهندسی کامپیوتر و IT', '📊 علوم داده و هوش مصنوعی', '⚡ مهندسی برق'],
    ['⚙️ مهندسی مکانیک', '🏗 مهندسی عمران', '🧪 مهندسی شیمی و مواد'],
    ['🧬 پزشکی و زیست‌شناسی', '💊 شیمی و داروسازی', '🏛 معماری و شهرسازی'],
    ['✏️ رشته‌ام در لیست نیست (تایپ می‌کنم)'],
    [BACK_BTN]
]

COUNTRY_KEYBOARD = [
    ['🌐 همه کشورها'],
    ['آمریکا 🇺🇸', 'استرالیا 🇦🇺', 'کانادا 🇨🇦'],
    ['نیوزلند 🇳🇿', 'فنلاند 🇫🇮', 'آلمان 🇩🇪'],
    ['انگلیس 🇬🇧', 'اسپانیا 🇪🇸', 'سوئد 🇸🇪'],
    ['🌍 کشور هدفم در لیست نیست (تایپ می‌کنم)'],
    [BACK_BTN]
]

HAS_LANG_KEYBOARD = [
    ['✅ دارم', '❌ ندارم'],
    [BACK_BTN]
]

LANG_TYPE_KEYBOARD = [
    ['🇬🇧 IELTS', '🇺🇸 TOEFL'],
    ['🗣 مدرک زبان دیگری دارم'],
    [BACK_BTN]
]

ONLY_BACK_KEYBOARD = [[BACK_BTN]]

# ----------------- تنظیم دکمه دائمی Start کنار کادر چت -----------------
async def post_init_setup(application: Application) -> None:
    commands = [
        BotCommand("start", "🔄 شروع ربات / ساخت و ویرایش پروفایل"),
        BotCommand("menu", "🏠 نمایش دکمه‌های منو اصلی"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

# ----------------- تابع کمکی ذخیره ایمن در دیتابیس -----------------
def update_user_db(user_id: int, **kwargs) -> bool:
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
        if not user:
            user = UserProfile(telegram_id=user_id)
            db.add(user)
        for k, v in kwargs.items():
            setattr(user, k, v)
        db.commit()
        return True
    except Exception as e:
        print(f"⚠️ خطا در ذخیره دیتابیس: {e}")
        db.rollback()
        return False
    finally:
        db.close()

# ----------------- مدیریت خطای سراسری -----------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("⚠️ خطای پیش‌بینی نشده در ربات رخ داد:")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    
    error_msg = (
        "⚠️ متاسفانه در پردازش این پیام خطای موقتی پیش آمد، اما ربات کاملاً فعال است! 🔄\n"
        "👇 لطفاً دوباره تلاش کن یا از دکمه‌های منوی اصلی استفاده کن:"
    )
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                error_msg,
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
            )
    except Exception:
        pass

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "✅ اطلاعاتت با موفقیت ذخیره شد! 💾\n\n"
        "🏠 <b>منوی اصلی دستیار هوشمند اپلای:</b>\n"
        "✨ می‌تونی روی <b>«📤 ارسال پوزیشن»</b> بزنی یا از سایر دکمه‌های زیر استفاده کنی:",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )
    return ConversationHandler.END

# ----------------- توابع مراحل ثبت پروفایل -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    welcome_text = (
        "سلام حانیه! 👋🎓 من دستیار هوشمند اپلای تحصیلی هستم.\n\n"
        "✨ برای شروع، اول باهم پروفایلت رو می سازیم تا پوزیشن‌ها رو بر اساس شرایط خودت ارزیابی کنیم.\n\n"
        "📄 لطفاً فایل رزومه (PDF یا Word) خودت رو برام بفرست:"
    )
    await update.message.reply_text(
        welcome_text, 
        reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
    )
    return RESUME

async def get_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text and update.message.text.strip() == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    doc = update.message.document
    if not doc:
        await update.message.reply_text(
            "⚠️ فایلی دریافت نشد! 📄 لطفاً رزومه‌ات رو حتماً به صورت فایل (PDF یا Word) آپلود کن:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return RESUME
        
    wait_msg = await update.message.reply_text("⏳ لطفاً منتظر بمانید... در حال دریافت و ثبت فایل رزومه شما 📄")
        
    user_id = update.message.from_user.id
    safe_filename = re.sub(r'[^\w\.-]', '_', doc.file_name or "resume.pdf")
    file_path = f"resumes/{user_id}_{safe_filename}"
    
    saved = update_user_db(user_id, resume_file_id=doc.file_id, resume_file_path=file_path)
    if not saved:
        await wait_msg.delete()
        await update.message.reply_text("⚠️ خطایی در ذخیره اطلاعات رخ داد. 🔄 لطفاً یک بار دیگر فایل را ارسال کن.")
        return RESUME

    try:
        file = await asyncio.wait_for(context.bot.get_file(doc.file_id), timeout=12.0)
        await asyncio.wait_for(file.download_to_drive(file_path), timeout=15.0)
    except Exception as e:
        print(f"ℹ️ فایل در تلگرام ثبت شد اما دانلود لوکال رد شد: {e}")
    
    await wait_msg.delete()
    await update.message.reply_text(
        "✅ فایل رزومه با موفقیت دریافت شد 🎉\n\n"
        "🎓 مقطع مورد نظرت رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(DEGREE_KEYBOARD, resize_keyboard=True)
    )
    return DEGREE

async def get_degree(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    clean_degree = text.replace("🎓", "").strip()
    update_user_db(update.message.from_user.id, target_degrees=clean_degree)
    
    await update.message.reply_text(
        "📚 رشته مورد نظرت رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(FIELD_KEYBOARD, resize_keyboard=True)
    )
    return FIELD

async def get_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    if "رشته‌ام در لیست نیست" in text:
        await update.message.reply_text(
            "✍️ نام رشته مورد نظرت رو تایپ و ارسال کن:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return CUSTOM_FIELD
        
    clean_field = re.sub(r'^[^\w\s]+\s*', '', text).strip()
    update_user_db(update.message.from_user.id, target_field=clean_field)
    return await ask_country(update, context)

async def get_custom_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    update_user_db(update.message.from_user.id, target_field=text)
    return await ask_country(update, context)

async def ask_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🌍 کشور هدفت رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(COUNTRY_KEYBOARD, resize_keyboard=True)
    )
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    if "در لیست نیست" in text:
        await update.message.reply_text(
            "✍️🌍 نام کشور یا کشورهای هدفت رو تایپ کن:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return CUSTOM_COUNTRY
        
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context)

async def get_custom_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🗣 مدرک زبان انگلیسی داری؟",
        reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True)
    )
    return HAS_LANG

async def get_has_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = (update.message.text or "").strip()
    if answer == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    if answer in ['دارم', '✅ دارم']:
        update_user_db(update.message.from_user.id, has_language_cert=True)
        await update.message.reply_text(
            "🏅 نوع مدرک رو انتخاب کن:",
            reply_markup=ReplyKeyboardMarkup(LANG_TYPE_KEYBOARD, resize_keyboard=True)
        )
        return LANG_TYPE
    elif answer in ['ندارم', '❌ ندارم']:
        update_user_db(update.message.from_user.id, has_language_cert=False, language_score="ندارد ❌")
        return await finish_profile(update, context)
    else:
        await update.message.reply_text(
            "⚠️ لطفاً یکی از دو دکمه «✅ دارم» یا «❌ ندارم» رو انتخاب کن:",
            reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True)
        )
        return HAS_LANG

async def get_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    if 'مدرک زبان دیگری دارم' in text:
        await update.message.reply_text(
            "✍️🗣 نام مدرک زبانتو بنویس:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return CUSTOM_LANG_TYPE
        
    clean_lang = text.replace("🇬🇧", "").replace("🇺🇸", "").strip()
    context.user_data['lang_type'] = clean_lang
    await update.message.reply_text(
        "🔢🏆 نمره زبانت رو وارد کن:",
        reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
    )
    return LANG_SCORE

async def get_custom_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    context.user_data['lang_type'] = text
    await update.message.reply_text(
        "🔢🏆 نمره زبانت رو وارد کن:",
        reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
    )
    return LANG_SCORE

async def get_lang_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    score = (update.message.text or "").strip()
    if score == BACK_BTN:
        return await back_to_main_menu(update, context)
        
    lang_type = context.user_data.get('lang_type', 'مدرک زبان')
    full_score = f"{lang_type} (نمره: {score}) ✅"
    update_user_db(update.message.from_user.id, has_language_cert=True, language_score=full_score)
    return await finish_profile(update, context)

async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
        summary = (
            "🎉 <b>پروفایل اپلای تو با موفقیت تکمیل و ذخیره شد!</b> ✨\n\n"
            f"🎓 <b>مقطع:</b> {html.escape(user.target_degrees or 'ثبت نشده')}\n"
            f"📚 <b>رشته:</b> {html.escape(user.target_field or 'ثبت نشده')}\n"
            f"🌍 <b>کشور هدف:</b> {html.escape(user.target_countries or 'ثبت نشده')}\n"
            f"🗣 <b>مدرک زبان:</b> {html.escape(user.language_score or 'ثبت نشده')}\n"
            f"📄 <b>فایل رزومه:</b> {'دریافت شده ✔️' if user.resume_file_id else 'ثبت نشده ❌'}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 <b>حالا آماده‌ام!</b> روی دکمه <b>«📤 ارسال پوزیشن»</b> بزن یا از سایر دکمه‌های منوی اصلی استفاده کن:"
        )
    finally:
        db.close()
        
    await update.message.reply_text(
        summary, 
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )
    return ConversationHandler.END

# ----------------- مدیریت دکمه‌های منوی اصلی -----------------
async def prompt_send_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 لینک پوزیشن و یا پست پوزیشن مورد نظر را فوروارد کنید تا مطابق پروفایل شما بررسی کنم:\n\n"
        "📎 <b>لینک / متن / عکس پوزیشن را ارسال کنید</b> 👇✨",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )

async def check_and_handle_profile_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = SessionLocal()
    try:
        user_id = update.message.from_user.id
        user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
        
        if not user or not user.resume_file_id or not user.target_degrees:
            await update.message.reply_text(
                "📭 پروفایل تو هنوز کامل نیست! بیا با هم از اول بسازیمش 🛠️\n\n"
                "📄 لطفاً فایل رزومه (PDF یا Word) خودت رو برام بفرست:",
                reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
            )
            return RESUME
            
        profile_card = (
            "👤 <b>پروفایل اپلای من</b> ✨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📄 <b>وضعیت رزومه:</b> آپلود شده ✔️\n"
            f"🎓 <b>مقطع هدف:</b> {html.escape(user.target_degrees)}\n"
            f"📚 <b>رشته تحصیلی:</b> {html.escape(user.target_field or 'ثبت نشده')}\n"
            f"🌍 <b>کشورهای مقصد:</b> {html.escape(user.target_countries or 'ثبت نشده')}\n"
            f"🗣 <b>وضعیت زبان:</b> {html.escape(user.language_score or 'ندارد ❌')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>برای ویرایش و ثبت مجدد اطلاعات از ابتدا، روی دکمه زیر کلیک کن:</i> 👇"
        )
    finally:
        db.close()
    
    inline_btn = [[InlineKeyboardButton("🔄 ویرایش مجدد پروفایل از ابتدا", callback_data="edit_profile")]]
    await update.message.reply_text(
        profile_card,
        reply_markup=InlineKeyboardMarkup(inline_btn),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def start_from_inline_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔄 شروع ویرایش پروفایل!\n\n"
        "📄 لطفاً فایل رزومه جدید (PDF یا Word) خودت رو برام بفرست:",
        reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
    )
    return RESUME

async def show_saved_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("⏳ لطفاً منتظر بمانید... در حال بارگذاری پوزیشن‌های ذخیره‌شده 📂")
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
        if not user:
            await wait_msg.delete()
            await update.message.reply_text("⚠️ ابتدا از بخش «👤 پروفایل من» اطلاعاتت رو ثبت کن.")
            return
            
        saved_list = db.query(Position).filter(Position.user_id == user.id, Position.status == "Saved").all()
        await wait_msg.delete()
        
        if not saved_list:
            await update.message.reply_text("📭 هنوز هیچ پوزیشنی رو برای بعد ذخیره نکردی! 💾")
            return
            
        await update.message.reply_text(f"💾 <b>شما {len(saved_list)} پوزیشن ذخیره‌شده برای اپلای دارید:</b> 👇", parse_mode="HTML")
        for p in saved_list:
            link_display = f"<a href='{html.escape(p.extracted_link)}'>🌐 مشاهده لینک پوزیشن</a>" if p.extracted_link and p.extracted_link.startswith("http") else "بدون لینک مستقیم"
            msg = (
                f"📌 <b>پوزیشن شماره #{p.id}</b>\n"
                f"⏳ <b>ددلاین:</b> {html.escape(p.deadline or 'نامشخص')}\n"
                f"🔗 <b>لینک:</b> {link_display}\n\n"
                f"📋 <b>خلاصه تحلیل و نیازمندی‌ها:</b>\n{p.requirements}"
            )
            btns = []
            if p.extracted_link and p.extracted_link.startswith("http"):
                btns.append([InlineKeyboardButton("🚀 ورود به لینک و اپلای", url=p.extracted_link)])
            btns.append([
                InlineKeyboardButton("✅ اپلای کردم!", callback_data=f"applied_{p.id}"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"delete_{p.id}")
            ])
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode="HTML", disable_web_page_preview=True)
    finally:
        db.close()

async def show_applied_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("⏳ لطفاً منتظر بمانید... در حال دریافت لیست اپلای‌شده‌ها ✅")
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
        if not user:
            await wait_msg.delete()
            await update.message.reply_text("⚠️ ابتدا از بخش «👤 پروفایل من» اطلاعاتت رو ثبت کن.")
            return
            
        applied_list = db.query(Position).filter(Position.user_id == user.id, Position.status == "Applied").all()
        await wait_msg.delete()
        
        if not applied_list:
            await update.message.reply_text("📭 هنوز پوزیشنی رو به عنوان «اپلای شده» ثبت نکردی! 🎯")
            return
            
        msg = "🎉 <b>لیست پوزیشن‌هایی که با موفقیت اپلای کردی:</b>\n\n"
        for p in applied_list:
            link_display = f"<a href='{html.escape(p.extracted_link)}'>🌐 ورود به سایت دانشگاه</a>" if p.extracted_link and p.extracted_link.startswith("http") else "بدون لینک"
            msg += (
                f"🎓 <b>پوزیشن #{p.id}</b> ✅\n"
                f"⏳ ددلاین: {html.escape(p.deadline or 'نامشخص')}\n"
                f"🔗 لینک: {link_display}\n"
                "➖➖➖➖➖➖➖➖\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
    finally:
        db.close()

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = [[InlineKeyboardButton("💬 ارسال پیام مستقیم به پشتیبانی", url=f"https://t.me/{SUPPORT_TELEGRAM_ID}")]]
    await update.message.reply_text(
        "👩‍💻✨ برای ارتباط مستقیم، پرسیدن سوال یا گزارش مشکل، روی دکمه زیر کلیک کن تا وارد چت بشیم 👇:",
        reply_markup=InlineKeyboardMarkup(btn)
    )

async def show_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = [[InlineKeyboardButton("▶️ ورود به کانال یوتیوب Honi's Hub", url=YOUTUBE_CHANNEL_URL)]]
    await update.message.reply_text(
        "🎬✨ در کانال یوتیوب <b>Honi's Hub</b> تمام تجربیات، آموزش‌های اپلای، چک‌لیست مدارک و ولاگ‌های مسیر تحصیلی رو قرار میدم.\n\n"
        "🔔 همین الان از دکمه زیر وارد شو و سابسکرایب کن 👇:",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode="HTML"
    )

async def show_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    feature_name = html.escape(update.message.text or "")
    await update.message.reply_text(
        f"🚧✨ بخش <b>«{feature_name}»</b> جزو قابلیت‌های پیشرفته فاز بعدی (بهبود با هوش مصنوعی 🤖 و سیستم ATS) است و به‌زودی فعال می‌شود! 🚀",
        parse_mode="HTML"
    )

# ----------------- استخراج محتوا از لینک وب‌سایت و اسکرین‌شات -----------------
async def fetch_webpage_content(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.extract()
                title = soup.title.string if soup.title else ""
                body_text = soup.get_text(separator=' ', strip=True)
                return f"{title}\n{body_text[:4000]}"
    except Exception as e:
        print(f"ℹ️ عدم دسترسی مستقیم به محتوای لینک ({url}): {e}")
    return ""

async def extract_text_from_screenshot(file_path: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    "https://api.ocr.space/parse/image",
                    data={"apikey": "helloworld", "language": "eng", "OCREngine": "2"},
                    files={"file": ("screenshot.jpg", f, "image/jpeg")}
                )
            if resp.status_code == 200:
                data = resp.json()
                parsed = data.get("ParsedResults", [])
                if parsed:
                    return parsed[0].get("ParsedText", "").strip()
    except Exception as e:
        print(f"ℹ️ خطا در خواندن اسکرین‌شات: {e}")
    return ""

# ----------------- موتور هوشمند تطبیق پروفایل و تحلیل پوزیشن (خروجی HTML) -----------------
def analyze_position_content(text: str, user: UserProfile, source_type: str = "متن / پست") -> dict:
    raw_urls = re.findall(r'(https?://[^\s<>"]+)', text)
    urls = []
    for u in raw_urls:
        clean_u = u.rstrip(').,;:]')
        if clean_u not in urls:
            urls.append(clean_u)
            
    main_link = urls[0] if urls else None
    lower_text = text.lower()
    
    matched_items = []
    upgrade_items = []
    
    # ۱. بررسی تطابق مقطع تحصیلی
    user_deg = (user.target_degrees or "").replace("🎓", "").strip()
    deg_keywords = {
        'دکتری': ['phd', 'ph.d', 'doctoral', 'doctorate', 'دکتری', 'دکترا'],
        'کارشناسی ارشد': ['master', 'msc', 'm.sc', 'ms', 'ma', 'laurea magistrale', 'magistrale', 'ارشد', 'کارشناسی ارشد'],
        'کارشناسی': ['bachelor', 'bsc', 'ba', 'undergraduate', 'laurea triennale', 'کارشناسی', 'لیسانس'],
        'پست دکتری': ['postdoc', 'post-doc', 'postdoctoral', 'پست دکتری', 'پسادکتری']
    }
    
    detected_degrees = []
    for deg_name, kw_list in deg_keywords.items():
        if any(k in lower_text for k in kw_list):
            detected_degrees.append(deg_name)
            
    if not detected_degrees or user_deg in detected_degrees:
        deg_note = f"({user_deg} در متن پوزیشن پشتیبانی می‌شود ✔️)" if detected_degrees else f"(مناسب برای {user_deg} ✔️)"
        matched_items.append(f"🎓 <b>مقطع تحصیلی:</b> کاملاً منطبق با هدف شما {html.escape(deg_note)}")
    else:
        upgrade_items.append(f"⚠️ <b>عدم تطابق مقطع:</b> این پوزیشن برای «{' و '.join(detected_degrees)}» است، اما هدف پروفایل شما «{html.escape(user_deg)}» ثبت شده است.")

    # ۲. بررسی تطابق کشور مقصد
    user_country = (user.target_countries or "").strip()
    country_map = {
        'آمریکا 🇺🇸': ['usa', 'united states', 'america', 'آمریکا', 'امریکا'],
        'کانادا 🇨🇦': ['canada', 'کانادا'],
        'استرالیا 🇦🇺': ['australia', 'unsw', 'sydney', 'melbourne', 'استرالیا'],
        'آلمان 🇩🇪': ['germany', 'daad', 'آلمان', 'المان'],
        'ایتالیا 🇮🇹': ['italy', 'italiana', 'unipd', 'unibo', 'polimi', 'maeci', 'universitaly', 'ایتالیا', 'پادووا', 'بولونیا', 'میلان'],
        'فنلاند 🇫🇮': ['finland', 'aalto', 'helsinki', 'فنلاند'],
        'انگلیس 🇬🇧': ['uk', 'united kingdom', 'england', 'british', 'انگلیس', 'بریتانیا'],
        'سوئد 🇸🇪': ['sweden', 'kth', 'chalmers', 'سوئد'],
        'اسپانیا 🇪🇸': ['spain', 'اسپانیا'],
        'نیوزلند 🇳🇿': ['new zealand', 'نیوزلند'],
        'هلند 🇳🇱': ['netherlands', 'holland', 'tudelft', 'amsterdam', 'tu/e', 'asml', 'هلند', 'آمستردام'],
        'فرانسه 🇫🇷': ['france', 'فرانسه'],
        'اتریش 🇦🇹': ['austria', 'اتریش'],
        'سوئیس 🇨🇭': ['switzerland', 'eth', 'epfl', 'سوئیس']
    }
    
    detected_countries = []
    for c_name, kw_list in country_map.items():
        if any(k in lower_text for k in kw_list):
            detected_countries.append(c_name)
            
    if "همه کشورها" in user_country:
        c_label = "، ".join(detected_countries) if detected_countries else "بین‌المللی 🌐"
        matched_items.append(f"🌍 <b>کشور مقصد:</b> منطبق با پروفایل شما (مقصد پوزیشن: <b>{c_label}</b>)")
    elif detected_countries:
        if any(c.split()[0] in user_country for c in detected_countries):
            matched_items.append(f"🌍 <b>کشور مقصد:</b> منطبق با انتخاب شما (<b>{'، '.join(detected_countries)}</b>)")
        else:
            upgrade_items.append(f"🌍 <b>تفاوت کشور مقصد:</b> این پوزیشن برای «{'، '.join(detected_countries)}» است، اما هدف پروفایل شما «{html.escape(user_country)}» است.")
    else:
        matched_items.append(f"🌍 <b>کشور مقصد:</b> قابل بررسی برای مقصد انتخابی شما ({html.escape(user_country)})")

    # ۳. بررسی تطابق رشته و رزومه
    user_field = (user.target_field or "رشته شما").strip()
    if user.resume_file_id:
        matched_items.append("📄 <b>رزومه (CV):</b> فایل رزومه شما در پروفایل موجود و آماده ارسال است ✔️")
        upgrade_items.append(f"✨ <b>شخصی‌سازی رزومه (Tailoring):</b> توصیه می‌شود پیش از اپلای، مهارت‌های رزومه‌تان را با کلیدواژه‌های این پوزیشن در رشته «{html.escape(user_field)}» هماهنگ کنید.")
    else:
        upgrade_items.append("📄 <b>نقص رزومه:</b> هنوز فایل رزومه خود را آپلود نکرده‌اید ❌")

    # ۴. بررسی تطابق مدرک زبان
    no_lang_needed = any(k in lower_text for k in ['بدون مدرک', 'بدون زبان', 'no ielts', 'waived', 'بدون آیلتس', 'بدون نیاز به مدرک زبان'])
    
    if no_lang_needed:
        matched_items.append("🗣 <b>مدرک زبان:</b> عالی! 🎉 این پوزیشن امکان اپلای <b>بدون مدرک زبان (یا با گواهی تدریس به زبان انگلیسی)</b> دارد و ۱۰۰٪ مناسب شرایط شماست.")
    elif user.has_language_cert:
        matched_items.append(f"🗣 <b>مدرک زبان:</b> شما مدرک زبان دارید (<b>{html.escape(user.language_score)}</b>) و واجد شرایط هستید.")
        upgrade_items.append("🗣 <b>کنترل حدنصاب نمره (Cut-off):</b> در لینک دانشگاه چک کنید نمره هر ۴ مهارت شما بالاتر از حداقل درخواستی باشد.")
    else:
        upgrade_items.append("🗣 <b>نیاز به مدرک زبان:</b> در پروفایل شما «بدون مدرک زبان» ثبت شده است؛ اگر دانشگاه گواهی تدریس به زبان انگلیسی (MOI) قبول نمی‌کند، باید برای آزمون IELTS/TOEFL اقدام کنید 🎯")

    # ۵. لیست نیازمندی‌های اپلای
    reqs = [
        "• 📄 <b>رزومه آکادمیک (Academic CV)</b>",
        "• 🎓 <b>ترجمه رسمی دانشنامه و ریزنمرات (Official Transcripts)</b>"
    ]
    if any(k in lower_text for k in ['cover letter', 'motivation', 'sop', 'statement', 'انگیزه نامه', 'کاور لتر']):
        reqs.append("• 📝 <b>انگیزه‌نامه / کاور لتر (Motivation Letter / SOP)</b> - <i>مورد تاکید پوزیشن ⭐️</i>")
    else:
        reqs.append("• 📝 <b>انگیزه‌نامه / کاور لتر (SOP / Cover Letter)</b>")
        
    if any(k in lower_text for k in ['reference', 'recommendation', 'referee', 'توصیه نامه', 'رفرنس']):
        reqs.append("• 📧 <b>توصیه‌نامه علمی (Recommendation Letters)</b> - <i>ثبت ایمیل آکادمیک ۲ تا ۳ استاد و نسبت علمی</i>")
    else:
        reqs.append("• 📧 <b>توصیه‌نامه علمی (References):</b> حداقل ۲ استاد معرف")

    if any(k in lower_text for k in ['research proposal', 'پروپوزال', 'proposal']):
        reqs.append("• 🔬 <b>ریسرچ پروپوزال (Research Proposal)</b>")
        upgrade_items.append("🔬 <b>آماده‌سازی پروپوزال پژوهشی:</b> این پوزیشن به یک Research Proposal نیاز دارد.")

    # ۶. وضعیت استاد راهنما
    needs_sup = False
    if any(k in lower_text for k in ['supervisor', 'professor', 'faculty', 'pi', 'استاد راهنما', 'استاد']) or 'دکتری' in user_deg:
        needs_sup = True
        sup_text = "👨‍🏫 <b>وضعیت استاد راهنما:</b> نیاز به بررسی اساتید دپارتمان در سایت دانشگاه و مکاتبه با استاد راهنما (Supervisor) 📩"
        upgrade_items.append("👨‍🏫 <b>یافتن استاد راهنما:</b> از طریق لینک‌های زیر وارد صفحه دپارتمان شوید و اساتید هم‌زمینه با رزومه خود را پیدا کنید.")
    else:
        sup_text = "👨‍🏫 <b>وضعیت استاد راهنما:</b> اپلای از طریق سامانه مرکزی دانشگاه (بدون الزام اولیه به تایید استاد) 🏛️"

    # ۷. ددلاین
    deadline = "نیاز به بررسی در لینک رسمی دانشگاه 🔍"
    # تشخیص دقیق تاریخ‌هایی مثل January 22, 2027
    full_date_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+202[6-9]', lower_text)
    years = re.findall(r'(202[6-9]|۲۰۲[۶-۹])', text)
    months = re.findall(r'(january|february|march|april|may|june|july|august|september|october|november|december|ژانویه|فوریه|مارس|آوریل|می|ژوئن|جولای|آگوست|سپتامبر|اکتبر|نوامبر|دسامبر)', lower_text)
    
    if full_date_match:
        deadline = f"{full_date_match.group(0).title()} (فرصت اپلای باز است ✅)"
    elif months and years:
        deadline = f"{months[0].capitalize()} {years[0]} (فرصت اپلای باز است ✅)"
    elif years:
        deadline = f"سال تحصیلی {years[0]} (فرصت اپلای باز است ✅)"

    match_status = "🟢 بسیار مناسب و هم‌راستا با پروفایل شما ✨" if len(matched_items) >= 3 else "🟡 قابل اپلای (نیازمند تکمیل موارد ارتقا 🛠️)"

    return {
        "link": main_link,
        "all_links": urls,
        "source_type": source_type,
        "match_status": match_status,
        "matched_str": "\n".join(matched_items) if matched_items else "• موردی یافت نشد.",
        "upgrade_str": "\n".join(upgrade_items) if upgrade_items else "• پروفایل شما از هر نظر آماده اپلای است! 🎉",
        "reqs_str": "\n".join(reqs),
        "supervisor_info": sup_text,
        "needs_supervisor": needs_sup,
        "deadline": deadline
    }

async def handle_router_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or msg.caption or "").strip()
    
    # ۱. بررسی دکمه‌های منوی اصلی
    if text == '📤 ارسال پوزیشن':
        return await prompt_send_position(update, context)
    elif text == '💾 پوزیشن های ذخیره شده':
        return await show_saved_positions(update, context)
    elif text == '✅ پوزیشن های اپلای شده':
        return await show_applied_positions(update, context)
    elif text == '💬 پشتیبانی':
        return await show_support(update, context)
    elif text == "▶️ یوتیوب Honi's Hub":
        return await show_youtube(update, context)
    elif 'بهبود رزومه' in text or 'نگارش انگیزه نامه' in text:
        return await show_coming_soon(update, context)
    elif text == BACK_BTN:
        return await back_to_main_menu(update, context)

    # ۲. بررسی وجود پروفایل کاربر
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == msg.from_user.id).first()
        if not user or not user.target_degrees:
            await msg.reply_text(
                "⚠️ هنوز پروفایلت کامل نیست! لطفاً روی دکمه <b>«👤 پروفایل من»</b> بزن تا اول اطلاعاتت رو ثبت کنیم 👇",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
                parse_mode="HTML"
            )
            return

        source_type = "📝 پست تلگرامی / متن"
        wait_msg = await msg.reply_text(
            "⏳ <b>لطفاً منتظر بمانید...</b>\n"
            "🔍 در حال بررسی تطابق پوزیشن با پروفایل شما و استخراج نیازمندی‌ها 🤖✨",
            parse_mode="HTML"
        )

        # ۳. اگر کاربر تصویر یا اسکرین‌شات بدون متن فرستاده باشد
        if msg.photo and len(text) < 15:
            source_type = "🖼 تصویر / اسکرین‌شات (OCR)"
            await wait_msg.edit_text(
                "⏳ <b>لطفاً منتظر بمانید...</b>\n"
                "🖼 تصویر دریافت شد! در حال خواندن متن داخل عکس و تحلیل پوزیشن 🔍✨",
                parse_mode="HTML"
            )
            photo_file = await context.bot.get_file(msg.photo[-1].file_id)
            img_path = f"screenshots/{msg.from_user.id}_shot.jpg"
            await photo_file.download_to_drive(img_path)
            ocr_text = await extract_text_from_screenshot(img_path)
            if ocr_text:
                text = f"{text}\n{ocr_text}".strip()
            elif not text:
                await wait_msg.edit_text(
                    "⚠️ متاسفانه متن داخل این عکس واضح نبود 😕\n"
                    "📸 لطفاً تصویر واضح‌تری بفرستید یا متن/لینک پوزیشن را همراه آن ارسال کنید."
                )
                return

        if not text:
            await wait_msg.edit_text("⚠️ متنی برای تحلیل پیدا نشد! 📎 لطفاً لینک / متن / عکس پوزیشن را ارسال کنید.")
            return

        # ۴. اگر کاربر فقط یک لینک خالی فرستاده باشد، محتوای صفحه وب را می‌خوانیم
        urls_in_msg = re.findall(r'(https?://[^\s<>"]+)', text)
        if len(urls_in_msg) == 1 and len(text.split()) <= 3:
            source_type = "🌐 لینک مستقیم وب‌سایت"
            await wait_msg.edit_text(
                "⏳ <b>لطفاً منتظر بمانید...</b>\n"
                "🌐 در حال ورود به لینک وب‌سایت و استخراج اطلاعات پوزیشن 🔍✨",
                parse_mode="HTML"
            )
            web_content = await fetch_webpage_content(urls_in_msg[0])
            if web_content:
                text = f"{text}\n{web_content}"

        # ۵. تحلیل کامل و تطبیق با پروفایل
        analysis = analyze_position_content(text, user, source_type=source_type)
        
        main_url = analysis['link'] or "بدون لینک مستقیم"
        db_reqs_summary = f"🎯 وضعیت: {analysis['match_status']}\n{analysis['reqs_str']}"
        
        # رفع خطای TypeError: حذف آرگومان link و استفاده دقیق از ستون‌های جدول Position
        new_pos = Position(
            user_id=user.id,
            raw_text=text[:3000],
            extracted_link=main_url,
            requirements=db_reqs_summary,
            deadline=analysis['deadline'],
            needs_supervisor=analysis['needs_supervisor'],
            status="Pending"
        )
        db.add(new_pos)
        db.commit()
        pos_id = new_pos.id

        # ۶. ساخت کارت نمایشی بسیار تمیز و کاربرپسند (HTML) همراه با اموجی
        report = (
            f"📊 <b>گزارش ارزیابی و تطابق پوزیشن (#{pos_id})</b> ✨\n"
            f"📥 <b>نوع ورودی:</b> {analysis['source_type']}\n"
            f"🎯 <b>نتیجه ارزیابی:</b> {analysis['match_status']}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>موارد منطبق با پروفایل شما:</b>\n"
            f"{analysis['matched_str']}\n\n"
            "🚀 <b>مواردی که باید ارتقا دهید / آماده کنید:</b>\n"
            f"{analysis['upgrade_str']}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 <b>چک‌لیست مدارک مورد نیاز اپلای:</b>\n"
            f"{analysis['reqs_str']}\n\n"
            f"{analysis['supervisor_info']}\n\n"
            f"⏳ <b>ددلاین اپلای:</b> {html.escape(analysis['deadline'])}\n"
        )
        
        if analysis['all_links']:
            links_formatted = []
            for idx, u in enumerate(analysis['all_links'][:6], start=1):
                safe_u = html.escape(u)
                domain_match = re.findall(r'https?://(?:www\.)?([^/]+)', u)
                domain_name = domain_match[0] if domain_match else f"لینک {idx}"
                links_formatted.append(f"🔗 <a href='{safe_u}'>لینک {idx}: ورود به سامانه ({html.escape(domain_name)}) 🌐</a>")
            report += "\n🌐 <b>لینک‌های استخراج شده از این پوزیشن:</b>\n" + "\n".join(links_formatted) + "\n"

        report += "\n👇 <b>تصمیمت برای این پوزیشن چیه؟</b> 🤔"

        buttons = []
        if analysis['link']:
            buttons.append([InlineKeyboardButton("🚀 ورود به لینک اصلی و اپلای درجا", url=analysis['link'])])
            
        buttons.append([
            InlineKeyboardButton("💾 ذخیره برای بعد (دارای فرصت)", callback_data=f"save_{pos_id}"),
            InlineKeyboardButton("✅ اپلای کردم!", callback_data=f"applied_{pos_id}")
        ])
        buttons.append([InlineKeyboardButton("❌ حذف پوزیشن", callback_data=f"delete_{pos_id}")])

        try:
            await wait_msg.delete()
        except Exception:
            pass
            
        await msg.reply_text(
            report,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    finally:
        db.close()

async def handle_position_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "edit_profile":
        return
        
    await query.answer("⏳ لطفاً منتظر بمانید...")
    action, pos_id = query.data.split("_")
    pos_id = int(pos_id)
    
    db = SessionLocal()
    try:
        pos = db.query(Position).filter(Position.id == pos_id).first()
        if not pos:
            await query.edit_message_text("⚠️ این پوزیشن دیگر در دیتابیس وجود ندارد 🗑️")
            return

        if action == "save":
            pos.status = "Saved"
            db.commit()
            await query.edit_message_text(
                query.message.text_html + "\n\n💾 <b>وضعیت: در بخش «پوزیشن های ذخیره شده» قرار گرفت تا سر فرصت اپلای کنی! ✨</b>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        elif action == "applied":
            pos.status = "Applied"
            db.commit()
            await query.edit_message_text(
                query.message.text_html + "\n\n🎉 <b>وضعیت: به لیست «پوزیشن های اپلای شده» منتقل شد! موفق باشی! 🚀🎓</b>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        elif action == "delete":
            db.delete(pos)
            db.commit()
            await query.edit_message_text("🗑 این پوزیشن با موفقیت از لیست تو حذف شد ✔️")
    finally:
        db.close()

# ----------------- تست اتصال و اجرای اصلی -----------------
async def find_working_async_connection():
    test_url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    candidates = [
        ("بدون پروکسی (اتصال مستقیم)", None),
        ("پروکسی HTTP روی آی‌پی V2Box (پورت 10808)", "http://172.20.10.9:10808"),
        ("پروکسی SOCKS5 روی آی‌پی V2Box", "socks5://172.20.10.9:10808"),
        ("پروکسی HTTP روی لوکال‌هاست (پورت 10808)", "http://127.0.0.1:10808"),
    ]
    print("🔍 در حال بررسی اتصال به تلگرام...")
    for name, proxy in candidates:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=10.0) as client:
                res = await client.get(test_url)
                if res.status_code == 200:
                    print(f"✅ اتصال پایدار برقرار شد! ({name})")
                    return True, proxy
        except Exception:
            pass
    return False, None

def main():
    init_db()
    success, working_proxy = asyncio.run(find_working_async_connection())
    if not success:
        print("⚠️ خطا در اتصال به تلگرام! روشن بودن فیلترشکن را بررسی کن.")
        return

    if working_proxy:
        req_main = HTTPXRequest(proxy=working_proxy, connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
        req_updates = HTTPXRequest(proxy=working_proxy, connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
    else:
        req_main = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
        req_updates = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)

    app = (
        Application.builder()
        .token(TOKEN)
        .request(req_main)
        .get_updates_request(req_updates)
        .post_init(post_init_setup)
        .build()
    )
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^👤 پروفایل من$'), check_and_handle_profile_btn),
            CallbackQueryHandler(start_from_inline_edit, pattern='^edit_profile$')
        ],
        states={
            RESUME: [
                MessageHandler(filters.Regex(f'^{BACK_BTN}$'), back_to_main_menu),
                MessageHandler(filters.ALL & ~filters.COMMAND, get_resume)
            ],
            DEGREE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_degree)],
            FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_field)],
            CUSTOM_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_field)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_country)],
            CUSTOM_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_country)],
            HAS_LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_has_lang)],
            LANG_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lang_type)],
            CUSTOM_LANG_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_lang_type)],
            LANG_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lang_score)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{BACK_BTN}$'), back_to_main_menu),
            CommandHandler('cancel', back_to_main_menu),
            CommandHandler('menu', back_to_main_menu),
            CommandHandler('start', start)
        ],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('menu', back_to_main_menu))
    app.add_handler(CallbackQueryHandler(handle_position_buttons))
    
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION | filters.PHOTO) & ~filters.COMMAND, handle_router_message))
    
    app.add_error_handler(global_error_handler)
    
    print("🚀 ربات آماده است! پوزیشن را در تلگرام ارسال کن...")
    app.run_polling(bootstrap_retries=-1, drop_pending_updates=False)

if __name__ == '__main__':
    main()