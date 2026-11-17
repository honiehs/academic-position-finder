import os
import re
import html
import traceback
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, 
    InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
from database import init_db, SessionLocal, UserProfile, Position

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

os.makedirs("data/resumes", exist_ok=True)
os.makedirs("data/screenshots", exist_ok=True)

SUPPORT_TELEGRAM_ID = "HaniehSaedi"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@HonisHub"

(RESUME, DEGREE, FIELD, CUSTOM_FIELD, COUNTRY, CUSTOM_COUNTRY, HAS_LANG, LANG_TYPE, CUSTOM_LANG_TYPE, LANG_SCORE) = range(10)
BACK_BTN = "🔙 بازگشت به منو اصلی"

MAIN_MENU_KEYBOARD = [
    ['📤 ارسال پوزیشن', '👤 پروفایل من'],
    ['💾 پوزیشن های ذخیره شده', '✅ پوزیشن های اپلای شده'],
    ['💬 پشتیبانی', "▶️ یوتیوب Honi's Hub"],
    ['✨ بهبود رزومه (به‌زودی)', '📝 نگارش انگیزه نامه (به‌زودی)']
]
DEGREE_KEYBOARD = [['🎓 کارشناسی', '🎓 کارشناسی ارشد'], ['🎓 دکتری', '🎓 پست دکتری'], [BACK_BTN]]
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
HAS_LANG_KEYBOARD = [['✅ بله', '❌ خیر'], [BACK_BTN]]
LANG_TYPE_KEYBOARD = [['🇬🇧 IELTS', '🇺🇸 TOEFL'], ['🗣 مدرک زبان دیگری دارم'], [BACK_BTN]]
ONLY_BACK_KEYBOARD = [[BACK_BTN]]

# کلیدواژه‌های تشخیص پوزیشن تحصیلی (رایگان و بدون نیاز به API)
ACADEMIC_KEYWORDS = [
    'phd', 'ph.d', 'master', 'msc', 'postdoc', 'post-doc', 'doctoral', 'doctorate',
    'scholarship', 'fellowship', 'fully funded', 'funding', 'stipend', 'tuition',
    'university', 'professor', 'supervisor', 'faculty', 'department', 'laboratory', 'lab',
    'research assistant', 'teaching assistant', 'graduate', 'admission', 'apply', 'application',
    'deadline', 'position', 'vacancy', 'candidate', 'cv', 'resume', 'transcript', 'sop',
    'دکتری', 'دکترا', 'کارشناسی ارشد', 'ارشد', 'پست داک', 'پست‌داک', 'فاند', 'فول فاند',
    'بورسیه', 'پوزیشن', 'اپلای', 'دانشگاه', 'استاد', 'ددلاین', 'پذیرش', 'تحصیلی', 'پژوهشی'
]

async def post_init_setup(application: Application) -> None:
    commands = [
        BotCommand("start", "🏠 شروع ربات و منوی اصلی"),
        BotCommand("menu", "🏠 نمایش منوی اصلی")
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

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
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def is_academic_position(text: str) -> bool:
    """بررسی هوشمند برای تشخیص اینکه متن واقعاً مربوط به پوزیشن تحصیلی است یا خیر"""
    if not text or len(text.strip()) < 25:
        return False
    l_text = text.lower()
    score = sum(1 for kw in ACADEMIC_KEYWORDS if kw in l_text)
    # حداقل ۲ کلیدواژه مرتبط باید در متن (یا متن استخراج‌شده از لینک/عکس) وجود داشته باشد
    return score >= 2

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطای موقتی پیش آمد. لطفاً دوباره تلاش کن:",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
            )
    except Exception:
        pass

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش منوی اصلی در /start، /menu و دکمه بازگشت"""
    await update.message.reply_text(
        "سلام! 👋🎓 به دستیار هوشمند اپلای خوش آمدی.\n\n🏠 <b>منوی اصلی:</b>",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def get_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN:
        return await show_main_menu(update, context)
    if not update.message.document:
        await update.message.reply_text(
            "⚠️ لطفاً فایل رزومه (PDF یا Word) ارسال کن:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return RESUME
        
    wait_msg = await update.message.reply_text("⏳ در حال دریافت فایل رزومه...")
    doc = update.message.document
    user_id = update.message.from_user.id
    safe_filename = re.sub(r'[^\w\.-]', '_', doc.file_name or "resume.pdf")
    file_path = f"data/resumes/{user_id}_{safe_filename}"
    
    if not update_user_db(user_id, resume_file_id=doc.file_id, resume_file_path=file_path):
        await wait_msg.edit_text("⚠️ خطا در ذخیره. دوباره تلاش کن.")
        return RESUME

    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(file_path)
    except Exception:
        pass
    
    await wait_msg.delete()
    await update.message.reply_text(
        "✅ رزومه دریافت شد\n\n🎓 مقطع مورد نظرت رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(DEGREE_KEYBOARD, resize_keyboard=True)
    )
    return DEGREE

async def get_degree(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_degrees=update.message.text.replace("🎓", "").strip())
    await update.message.reply_text("📚 رشته رو انتخاب کن:", reply_markup=ReplyKeyboardMarkup(FIELD_KEYBOARD, resize_keyboard=True))
    return FIELD

async def get_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    if "در لیست نیست" in update.message.text:
        await update.message.reply_text("✍️ نام رشته رو تایپ کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_FIELD
    update_user_db(update.message.from_user.id, target_field=re.sub(r'^[^\w\s]+\s*', '', update.message.text).strip())
    return await ask_country(update, context)

async def get_custom_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_field=update.message.text.strip())
    return await ask_country(update, context)

async def ask_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🌍 کشور هدفت رو انتخاب کن:", reply_markup=ReplyKeyboardMarkup(COUNTRY_KEYBOARD, resize_keyboard=True))
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    if "در لیست نیست" in update.message.text:
        await update.message.reply_text("✍️ نام کشور رو تایپ کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_COUNTRY
    update_user_db(update.message.from_user.id, target_countries=update.message.text.strip())
    return await ask_language(update, context)

async def get_custom_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_countries=update.message.text.strip())
    return await ask_language(update, context)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🗣 مدرک زبان داری؟", reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True))
    return HAS_LANG

async def get_has_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    if 'بله' in update.message.text:
        update_user_db(update.message.from_user.id, has_language_cert=True)
        await update.message.reply_text("🏅 نوع مدرک:", reply_markup=ReplyKeyboardMarkup(LANG_TYPE_KEYBOARD, resize_keyboard=True))
        return LANG_TYPE
    elif 'خیر' in update.message.text:
        update_user_db(update.message.from_user.id, has_language_cert=False, language_score="ندارد ❌")
        return await finish_profile(update, context)
    else:
        await update.message.reply_text("⚠️ لطفاً یکی از گزینه‌های «✅ بله» یا «❌ خیر» را انتخاب کن:", reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True))
        return HAS_LANG

async def get_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    if 'دیگری' in update.message.text:
        await update.message.reply_text("✍️ نام مدرک:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_LANG_TYPE
    context.user_data['lang_type'] = update.message.text.replace("🇬🇧", "").replace("🇺🇸", "").strip()
    await update.message.reply_text("🔢 نمره زبانت رو وارد کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
    return LANG_SCORE

async def get_custom_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    context.user_data['lang_type'] = update.message.text.strip()
    await update.message.reply_text("🔢 نمره زبانت رو وارد کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
    return LANG_SCORE

async def get_lang_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN: return await show_main_menu(update, context)
    update_user_db(
        update.message.from_user.id,
        has_language_cert=True,
        language_score=f"{context.user_data.get('lang_type', '')} (نمره: {update.message.text.strip()}) ✅"
    )
    return await finish_profile(update, context)

async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
    msg = (
        f"🎉 <b>پروفایل با موفقیت تکمیل شد!</b>\n\n"
        f"🎓 <b>مقطع:</b> {html.escape(user.target_degrees or '-')}\n"
        f"📚 <b>رشته:</b> {html.escape(user.target_field or '-')}\n"
        f"🌍 <b>کشور هدف:</b> {html.escape(user.target_countries or '-')}\n"
        f"🗣 <b>زبان:</b> {html.escape(user.language_score or '-')}"
    )
    db.close()
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True), parse_mode="HTML")
    return ConversationHandler.END

async def prompt_send_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📎 <b>پوزیشن تحصیلی را ارسال کنید</b> 👇\n\n"
        "• فوروارد از کانال‌های تلگرام\n"
        "• متن کپی‌شده\n"
        "• اسکرین‌شات از لینکدین یا سایت\n"
        "• لینک مستقیم پوزیشن",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )

async def check_and_handle_profile_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
    db.close()
    
    # اگر پروفایل وجود نداشت یا ناقص بود، ساخت پروفایل را شروع کن
    if not user or not user.target_degrees or not user.target_field:
        await update.message.reply_text(
            "📭 هنوز پروفایلت کامل نشده است.\n\n📄 لطفاً فایل رزومه (PDF/Word) خودت رو بفرست:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return RESUME
    
    # اگر پروفایل کامل بود، خلاصه را نمایش بده
    resume_name = os.path.basename(user.resume_file_path) if user.resume_file_path else "ثبت شده"
    await update.message.reply_text(
        f"👤 <b>پروفایل من</b>\n\n"
        f"📄 <b>رزومه:</b> {html.escape(resume_name)}\n"
        f"🎓 <b>مقطع:</b> {html.escape(user.target_degrees)}\n"
        f"📚 <b>رشته:</b> {html.escape(user.target_field)}\n"
        f"🌍 <b>کشور هدف:</b> {html.escape(user.target_countries or '-')}\n"
        f"🗣 <b>زبان:</b> {html.escape(user.language_score or '-')}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ویرایش پروفایل", callback_data="edit_profile")]]),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def start_from_inline_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "📄 فایل رزومه جدید رو بفرست:",
        reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
    )
    return RESUME

async def show_saved_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = db.query(UserProfile).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        db.close()
        return await update.message.reply_text("📭 هیچ پوزیشنی ذخیره نکردی!")
    saved = db.query(Position).filter(Position.user_id == user.id, Position.status == "Saved").all()
    db.close()
    if not saved:
        return await update.message.reply_text("📭 هیچ پوزیشنی ذخیره نکردی!")
    for p in saved:
        btn = [[InlineKeyboardButton("🚀 اپلای", url=p.extracted_link)]] if p.extracted_link and p.extracted_link.startswith("http") else []
        btn.append([InlineKeyboardButton("✅ اپلای کردم", callback_data=f"applied_{p.id}"), InlineKeyboardButton("🗑 حذف", callback_data=f"delete_{p.id}")])
        await update.message.reply_text(f"📌 <b>#{p.id}</b> | ⏳ {html.escape(p.deadline or '')}\n{p.requirements}", reply_markup=InlineKeyboardMarkup(btn), parse_mode="HTML")

async def show_applied_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = db.query(UserProfile).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        db.close()
        return await update.message.reply_text("📭 لیست اپلای شده‌ها خالیست!")
    applied = db.query(Position).filter(Position.user_id == user.id, Position.status == "Applied").all()
    db.close()
    if not applied:
        return await update.message.reply_text("📭 لیست اپلای شده‌ها خالیست!")
    msg = "✅ <b>اپلای شده‌ها:</b>\n" + "\n".join([f"🎓 #{p.id} | ⏳ {html.escape(p.deadline or '')}" for p in applied])
    await update.message.reply_text(msg, parse_mode="HTML")

async def fetch_webpage_content(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.extract()
            return f"{soup.title.string if soup.title else ''}\n{soup.get_text(separator=' ', strip=True)[:4000]}"
    except Exception:
        return ""

async def extract_text_from_screenshot(file_path: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    "https://api.ocr.space/parse/image",
                    data={"apikey": "helloworld", "language": "eng", "OCREngine": "2"},
                    files={"file": ("img.jpg", f, "image/jpeg")}
                )
                if resp.status_code == 200 and resp.json().get("ParsedResults"):
                    return resp.json()["ParsedResults"][0].get("ParsedText", "").strip()
    except Exception:
        pass
    return ""

def analyze_position(text: str, user: UserProfile, src: str) -> dict:
    urls = list(dict.fromkeys([u.rstrip(').,;:]') for u in re.findall(r'(https?://[^\s<>"]+)', text)]))
    l_text = text.lower()
    match = []
    up = []
    reqs = ["• 📄 <b>CV</b>", "• 🎓 <b>Transcripts</b>"]
    
    if any(k in l_text for k in ['بدون مدرک', 'no ielts', 'waived']):
        match.append("🗣 <b>زبان:</b> بدون مدرک زبان ✅")
    elif user.has_language_cert:
        match.append(f"🗣 <b>زبان:</b> {html.escape(user.language_score)} ✅")
    else:
        up.append("🗣 <b>زبان:</b> نیاز به IELTS/TOEFL ❌")

    if any(k in l_text for k in ['sop', 'cover letter', 'motivation letter']):
        reqs.append("• 📝 <b>SOP / Cover Letter</b> ⭐️")
    if any(k in l_text for k in ['reference', 'recommendation']):
        reqs.append("• 📧 <b>References</b>")
    
    dl = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+202[6-9]', l_text)
    deadline = dl.group(0).title() if dl else "بررسی در سایت"

    st = "🟢 بسیار مناسب ✨" if len(match) >= 1 else "🟡 قابل اپلای"
    return {"urls": urls, "match": st, "m_str": "\n".join(match) or "-", "u_str": "\n".join(up) or "-", "r_str": "\n".join(reqs), "dl": deadline}

async def handle_router_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or msg.caption or "").strip()
    
    if text == '📤 ارسال پوزیشن': return await prompt_send_position(update, context)
    elif text == '💾 پوزیشن های ذخیره شده': return await show_saved_positions(update, context)
    elif text == '✅ پوزیشن های اپلای شده': return await show_applied_positions(update, context)
    elif text == '💬 پشتیبانی': return await msg.reply_text(f"پشتیبانی: @{SUPPORT_TELEGRAM_ID}")
    elif "▶️" in text: return await msg.reply_text(f"کانال: {YOUTUBE_CHANNEL_URL}")
    elif 'بهبود' in text or 'نگارش' in text: return await msg.reply_text("🚧 به‌زودی فعال می‌شود!")
    elif text == BACK_BTN: return await show_main_menu(update, context)

    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == msg.from_user.id).first()
    if not user or not user.target_degrees:
        db.close()
        return await msg.reply_text("⚠️ پروفایل کامل نیست. ابتدا روی «👤 پروفایل من» کلیک کن.")

    wait = await msg.reply_text("⏳ در حال بررسی و پردازش پوزیشن...")
    src = "متن / فوروارد"
    combined_text = text

    # ۱. اگر عکس بود (هم متن/کپشن را می‌خواند و هم متن داخل عکس را استخراج و به آن اضافه می‌کند)
    if msg.photo:
        src = "عکس و متن" if text else "عکس"
        try:
            img_p = f"data/screenshots/{msg.from_user.id}.jpg"
            file = await context.bot.get_file(msg.photo[-1].file_id)
            await file.download_to_drive(img_p)
            ocr_txt = await extract_text_from_screenshot(img_p)
            if ocr_txt:
                combined_text = f"{text}\n{ocr_txt}".strip()
        except Exception as e:
            print(f"Photo download/OCR error: {e}")

    # ۲. اگر لینک بود
    urls = re.findall(r'(https?://[^\s<>"]+)', combined_text)
    if len(urls) >= 1 and len(text.split()) <= 5 and not msg.photo:
        src = "لینک"
        content = await fetch_webpage_content(urls[0])
        combined_text = f"{combined_text}\n{content}".strip()

    # ۳. اعتبارسنجی اینکه واقعاً پوزیشن تحصیلی است یا خیر
    if not is_academic_position(combined_text):
        await wait.delete()
        db.close()
        return await msg.reply_text(
            "⚠️ لطفاً پیام ارسالی را مجدداً بررسی کنید و فقط پوزیشن اپلای تحصیلی را ارسال کنید:"
        )

    an = analyze_position(combined_text, user, src)
    pos = Position(
        user_id=user.id,
        raw_text=combined_text[:3000],
        extracted_link=an['urls'][0] if an['urls'] else "",
        requirements=an['r_str'],
        deadline=an['dl']
    )
    db.add(pos)
    db.commit()
    
    rep = (
        f"📊 <b>گزارش (#{pos.id})</b> | {src}\n"
        f"🎯 <b>نتیجه:</b> {an['match']}\n━━━━━━━━━\n"
        f"✅ <b>منطبق:</b>\n{an['m_str']}\n"
        f"🚀 <b>ارتقا:</b>\n{an['u_str']}\n━━━━━━━━━\n"
        f"📋 <b>مدارک:</b>\n{an['r_str']}\n"
        f"⏳ <b>ددلاین:</b> {html.escape(an['dl'])}"
    )
    
    btn = [[InlineKeyboardButton("🚀 اپلای", url=an['urls'][0])]] if an['urls'] else []
    btn.append([InlineKeyboardButton("💾 ذخیره", callback_data=f"save_{pos.id}"), InlineKeyboardButton("✅ انجام شد", callback_data=f"applied_{pos.id}")])
    btn.append([InlineKeyboardButton("❌ حذف", callback_data=f"delete_{pos.id}")])

    await wait.delete()
    await msg.reply_text(rep, reply_markup=InlineKeyboardMarkup(btn), parse_mode="HTML", disable_web_page_preview=True)
    db.close()

async def handle_pos_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "edit_profile":
        return
    await q.answer("⏳...")
    act, p_id = q.data.split("_")
    db = SessionLocal()
    p = db.query(Position).filter(Position.id == int(p_id)).first()
    if p:
        if act == "save": p.status = "Saved"
        elif act == "applied": p.status = "Applied"
        elif act == "delete": db.delete(p)
        db.commit()
        await q.edit_message_text(q.message.text_html + f"\n\n✅ <b>عملیات {act} انجام شد!</b>", parse_mode="HTML")
    db.close()

def main():
    init_db()
    PROXY_URL = "https://academicpositionfinder.honiehsaedii.workers.dev"

    app = (
        Application.builder()
        .token(TOKEN)
        .base_url(f"{PROXY_URL}/bot")
        .base_file_url(f"{PROXY_URL}/file/bot")
        .post_init(post_init_setup)
        .build()
    )
    
    cv_h = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^👤'), check_and_handle_profile_btn),
            CallbackQueryHandler(start_from_inline_edit, pattern='^edit_profile$')
        ],
        states={
            RESUME: [MessageHandler(filters.Regex(f'^{BACK_BTN}$'), show_main_menu), MessageHandler(filters.ALL & ~filters.COMMAND, get_resume)],
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
            MessageHandler(filters.Regex(f'^{BACK_BTN}$'), show_main_menu),
            CommandHandler('start', show_main_menu),
            CommandHandler('menu', show_main_menu)
        ],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler('start', show_main_menu))
    app.add_handler(CommandHandler('menu', show_main_menu))
    app.add_handler(cv_h)
    app.add_handler(CallbackQueryHandler(handle_pos_btn))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION | filters.PHOTO) & ~filters.COMMAND, handle_router_message))
    app.add_error_handler(global_error_handler)
    
    print("🚀 ربات در حالت Production آماده است!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()