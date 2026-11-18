import os
import re
import html
import asyncio
import traceback
from datetime import datetime
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

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

os.makedirs("data/resumes", exist_ok=True)
os.makedirs("data/screenshots", exist_ok=True)

SUPPORT_TELEGRAM_ID = "HaniehSaedi"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@HanizHub"

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

ACADEMIC_KEYWORDS = [
    'phd', 'ph.d', 'master', 'msc', 'postdoc', 'post-doc', 'doctoral', 'doctorate',
    'scholarship', 'fellowship', 'fully funded', 'funding', 'stipend', 'tuition',
    'university', 'professor', 'supervisor', 'faculty', 'department', 'laboratory', 'lab',
    'research assistant', 'teaching assistant', 'graduate', 'admission', 'apply', 'application',
    'deadline', 'position', 'vacancy', 'candidate', 'cv', 'resume', 'transcript', 'sop',
    'دکتری', 'دکترا', 'کارشناسی ارشد', 'ارشد', 'پست داک', 'پست‌داک', 'فاند', 'فول فاند',
    'بورسیه', 'پوزیشن', 'اپلای', 'دانشگاه', 'استاد', 'ددلاین', 'پذیرش', 'تحصیلی', 'پژوهشی'
]

PENDING_BATCHES = {}
BATCH_TASKS = {}

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
    if not text or len(text.strip()) < 25:
        return False
    l_text = text.lower()
    score = sum(1 for kw in ACADEMIC_KEYWORDS if kw in l_text)
    return score >= 2

def extract_position_title(text: str) -> str:
    """استخراج نام کامل موقعیت تحصیلی از متن آگهی"""
    if not text:
        return "موقعیت تحصیلی"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title_keywords = [
        'phd', 'ph.d', 'master', 'msc', 'postdoc', 'doctoral', 'scholarship',
        'fellowship', 'position', 'research', 'hiring', 'vacancy',
        'دکتری', 'دکترا', 'ارشد', 'پست داک', 'پست‌داک', 'بورسیه', 'پوزیشن', 'فاند', 'استاد'
    ]
    candidates = []
    for line in lines:
        if line.startswith("http") or line.startswith("@") or line.startswith("#"):
            continue
        clean_line = re.sub(r'https?://\S+', '', line).strip()
        if len(clean_line) < 6:
            continue
        candidates.append(clean_line)
        if any(k in clean_line.lower() for k in title_keywords):
            return clean_line[:120] + ("..." if len(clean_line) > 120 else "")
    if candidates:
        first = candidates[0]
        return first[:120] + ("..." if len(first) > 120 else "")
    return "موقعیت تحصیلی"

def extract_resume_text(file_path: str) -> str:
    if not file_path or not os.path.exists(file_path):
        return ""
    if file_path.lower().endswith(".pdf") and HAS_PYPDF:
        try:
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages).lower()
        except Exception:
            return ""
    return ""

def parse_deadline(text: str):
    """بازگرداندن (متن ددلاین، آیا گذشته است، آیا نزدیک است)"""
    l_text = text.lower()
    months = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    month_pattern = "|".join(months.keys())
    now = datetime.now()

    def evaluate_date(dt: datetime, label: str):
        is_expired = dt < now
        is_near = (not is_expired) and ((dt - now).days <= 14)
        return label, is_expired, is_near

    m1 = re.search(rf'({month_pattern})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(202[4-9])', l_text)
    if m1:
        try:
            dt = datetime(int(m1.group(3)), months[m1.group(1)], int(m1.group(2)))
            return evaluate_date(dt, m1.group(0).title())
        except ValueError:
            pass

    m2 = re.search(rf'(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pattern})\.?,?\s+(202[4-9])', l_text)
    if m2:
        try:
            dt = datetime(int(m2.group(3)), months[m2.group(2)], int(m2.group(1)))
            return evaluate_date(dt, m2.group(0).title())
        except ValueError:
            pass

    m3 = re.search(r'(202[4-9])[-/](\d{1,2})[-/](\d{1,2})', l_text)
    if m3:
        try:
            dt = datetime(int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
            return evaluate_date(dt, m3.group(0))
        except ValueError:
            pass

    return None, False, False

def pick_best_apply_url(urls: list) -> str:
    if not urls:
        return ""
    priority_keys = ['apply', 'career', 'job', 'vacancy', 'vacancies', 'admission', 'lnkd.in', 'portal', 'application']
    for u in urls:
        if any(k in u.lower() for k in priority_keys):
            return u
    return urls[0]

def extract_telegram_urls(msg) -> list:
    urls = []
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for ent in entities:
        if ent.type == "text_link" and ent.url:
            urls.append(ent.url)
    return urls

def is_same_ad(group: dict, item: dict) -> bool:
    """تشخیص اینکه دو پیام پشت سر هم مربوط به یک آگهی هستند یا دو آگهی مجزا"""
    if group['media_group_id'] and item['media_group_id'] and group['media_group_id'] == item['media_group_id']:
        return True
    if group['urls'] and item['urls'] and (group['urls'] & item['urls']):
        return True
    if (not item['is_complete_ad']) or (not group['is_complete_ad']):
        return True

    w1 = set(re.findall(r'[a-zA-Z0-9\u0600-\u06FF]{4,}', group['text'].lower()))
    w2 = set(re.findall(r'[a-zA-Z0-9\u0600-\u06FF]{4,}', item['text'].lower()))
    if w1 and w2:
        overlap = len(w1 & w2) / min(len(w1), len(w2))
        if overlap >= 0.45:
            return True
    return False

def analyze_position(text: str, user: UserProfile) -> dict:
    urls = list(dict.fromkeys([u.rstrip(').,;:]') for u in re.findall(r'(https?://[^\s<>"]+)', text)]))
    best_url = pick_best_apply_url(urls)
    title = extract_position_title(text)
    l_text = text.lower()
    resume_text = extract_resume_text(user.resume_file_path)

    details = []
    match_count = 0

    deadline_str, is_expired, is_near = parse_deadline(text)

    # ۱. مقطع تحصیلی
    degree_map = {
        'دکتری': ['phd', 'ph.d', 'doctoral', 'doctorate', 'دکتری', 'دکترا'],
        'کارشناسی ارشد': ['master', 'msc', 'm.sc', 'ارشد', 'کارشناسی ارشد'],
        'پست دکتری': ['postdoc', 'post-doc', 'پست داک', 'پست‌داک', 'پست دکتری'],
        'کارشناسی': ['bachelor', 'bsc', 'undergraduate', 'کارشناسی']
    }
    pos_degrees = [deg for deg, kws in degree_map.items() if any(k in l_text for k in kws)]
    user_deg = (user.target_degrees or "").strip()
    if pos_degrees:
        if user_deg in pos_degrees:
            match_count += 1
            details.append(f"🎓 <b>مقطع تحصیلی:</b> با هدف شما ({html.escape(user_deg)}) کاملاً مطابقت دارد ✅")
        else:
            details.append(f"🎓 <b>مقطع تحصیلی:</b> این پوزیشن برای {' / '.join(pos_degrees)} است و با هدف شما ({html.escape(user_deg)}) همخوانی ندارد ❌")

    # ۲. رشته تحصیلی
    field_keywords = {
        'کامپیوتر': ['computer', 'software', 'ai', 'artificial intelligence', 'machine learning', 'data', 'cyber', 'computing', 'کامپیوتر', 'نرم‌افزار', 'نرم افزار', 'هوش مصنوعی'],
        'علوم داده': ['data', 'machine learning', 'ai', 'analytics', 'deep learning', 'علوم داده', 'هوش مصنوعی'],
        'برق': ['electrical', 'electronics', 'control', 'signal', 'برق', 'کنترل'],
        'مکانیک': ['mechanical', 'robotics', 'thermal', 'مکانیک'],
        'عمران': ['civil', 'structural', 'عمران'],
        'شیمی': ['chemical', 'materials', 'chemistry', 'شیمی'],
        'پزشکی': ['medical', 'biology', 'biomedical', 'bio', 'پزشکی', 'زیست'],
        'معماری': ['architecture', 'urban', 'معماری']
    }
    user_field = (user.target_field or "").strip()
    matched_field_kws = []
    for f_key, kws in field_keywords.items():
        if f_key in user_field:
            matched_field_kws = [k for k in kws if k in l_text]
            break

    if matched_field_kws:
        match_count += 1
        details.append(f"📚 <b>رشته تحصیلی:</b> مرتبط با حوزه «{html.escape(user_field)}» ({', '.join(matched_field_kws[:3])}) ✅")
    else:
        details.append(f"📚 <b>رشته تحصیلی:</b> کلیدواژه‌های رشته شما ({html.escape(user_field)}) در متن این پوزیشن پیدا نشد ❌")

    # ۳. تطابق با رزومه
    if resume_text:
        tech_skills = ['python', 'java', 'sql', 'flutter', 'dart', 'machine learning', 'deep learning', 'nlp', 'data analysis', 'cloud', 'docker', 'git', 'c++', 'matlab', 'bi', 'erp', 'agile', 'scrum', 'fuzzy']
        shared_skills = [sk for sk in tech_skills if sk in resume_text and sk in l_text]
        if shared_skills:
            match_count += 1
            details.append(f"📄 <b>تطابق با رزومه:</b> مهارت‌های مشترک ({', '.join(shared_skills[:5])}) در رزومه‌ات وجود دارد ✅")

    # ۴. مدرک زبان
    if any(k in l_text for k in ['بدون مدرک', 'no ielts', 'waived', 'without ielts']):
        match_count += 1
        details.append("🗣 <b>مدرک زبان:</b> بدون نیاز به مدرک زبان ✅")
    elif user.has_language_cert:
        match_count += 1
        details.append(f"🗣 <b>مدرک زبان:</b> دارای مدرک ({html.escape(user.language_score or '')}) ✅")
    else:
        details.append("🗣 <b>مدرک زبان:</b> پروفایل شما فاقد مدرک IELTS/TOEFL است و احتمالاً برای اپلای نیاز خواهد بود ❌")

    is_eligible = (not is_expired) and (match_count >= 1)

    if is_expired:
        status_line = "❌ غیرقابل اپلای (ددلاین گذشته است)"
        deadline_line = f"❌ متاسفانه ددلاین اپلای این پوزیشن گذشته است ({html.escape(deadline_str)})"
    else:
        status_line = "✅ قابل اپلای برای شما" if is_eligible else "⚠️ نیازمند بررسی بیشتر (عدم تطابق با پروفایل)"
        if deadline_str:
            if is_near:
                deadline_line = f"⚠️ ⏳ ددلاین دارد ({html.escape(deadline_str)}) — ددلاین نزدیک است!"
            else:
                deadline_line = f"⏳ ددلاین دارد ({html.escape(deadline_str)})"
        else:
            deadline_line = "⏳ ددلاین: نامشخص (بررسی در سایت)"

    details_str = "\n\n".join(details)

    return {
        "title": title,
        "best_url": best_url,
        "status_line": status_line,
        "deadline_line": deadline_line,
        "details_str": details_str,
        "dl": deadline_str or "نامشخص (بررسی در سایت)"
    }

def build_position_buttons(pos_id: int, best_url: str, include_save: bool = True) -> InlineKeyboardMarkup:
    """ساخت دکمه‌های شیشه‌ای یکسان برای گزارش پوزیشن و لیست ذخیره شده‌ها"""
    btn = []
    if best_url and best_url.startswith("http"):
        btn.append([InlineKeyboardButton("🚀 لینک اپلای پوزیشن", url=best_url)])
    else:
        btn.append([InlineKeyboardButton("🚫 لینک در دسترس نیست", callback_data="no_link")])

    if include_save:
        btn.append([
            InlineKeyboardButton("✅ اپلای کردم", callback_data=f"applied_{pos_id}"),
            InlineKeyboardButton("💾 ذخیرش کن", callback_data=f"save_{pos_id}")
        ])
        btn.append([InlineKeyboardButton("🗑 حذف پوزیشن", callback_data=f"delete_{pos_id}")])
    else:
        btn.append([
            InlineKeyboardButton("✅ اپلای کردم", callback_data=f"applied_{pos_id}"),
            InlineKeyboardButton("🗑 حذف پوزیشن", callback_data=f"delete_{pos_id}")
        ])
    return InlineKeyboardMarkup(btn)

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
    await update.message.reply_text(
        "سلام! 👋🎓 به دستیار هوشمند اپلای خوش آمدی.\n\n🏠 <b>منوی اصلی:</b>",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def get_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text and update.message.text.strip() == BACK_BTN:
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
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_degrees=text.replace("🎓", "").strip())
    await update.message.reply_text("📚 رشته رو انتخاب کن:", reply_markup=ReplyKeyboardMarkup(FIELD_KEYBOARD, resize_keyboard=True))
    return FIELD

async def get_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    if text == '✏️ رشته‌ام در لیست نیست (تایپ می‌کنم)':
        await update.message.reply_text("✍️ نام رشته رو تایپ کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_FIELD
    update_user_db(update.message.from_user.id, target_field=re.sub(r'^[^\w\s]+\s*', '', text).strip())
    return await ask_country(update, context)

async def get_custom_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_field=text)
    return await ask_country(update, context)

async def ask_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🌍 کشور هدفت رو انتخاب کن:", reply_markup=ReplyKeyboardMarkup(COUNTRY_KEYBOARD, resize_keyboard=True))
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    if text == '🌍 کشور هدفم در لیست نیست (تایپ می‌کنم)':
        await update.message.reply_text("✍️ نام کشور رو تایپ کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_COUNTRY
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context)

async def get_custom_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🗣 مدرک زبان داری؟", reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True))
    return HAS_LANG

async def get_has_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    if text == '✅ بله':
        update_user_db(update.message.from_user.id, has_language_cert=True)
        await update.message.reply_text("🏅 نوع مدرک:", reply_markup=ReplyKeyboardMarkup(LANG_TYPE_KEYBOARD, resize_keyboard=True))
        return LANG_TYPE
    elif text == '❌ خیر':
        update_user_db(update.message.from_user.id, has_language_cert=False, language_score="ندارد ❌")
        return await finish_profile(update, context)
    else:
        await update.message.reply_text(
            "⚠️ لطفاً یکی از گزینه‌های «✅ بله» یا «❌ خیر» را انتخاب کن:",
            reply_markup=ReplyKeyboardMarkup(HAS_LANG_KEYBOARD, resize_keyboard=True)
        )
        return HAS_LANG

async def get_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    if text == '🗣 مدرک زبان دیگری دارم':
        await update.message.reply_text("✍️ نام مدرک:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
        return CUSTOM_LANG_TYPE
    context.user_data['lang_type'] = text.replace("🇬🇧", "").replace("🇺🇸", "").strip()
    await update.message.reply_text("🔢 نمره زبانت رو وارد کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
    return LANG_SCORE

async def get_custom_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    context.user_data['lang_type'] = text
    await update.message.reply_text("🔢 نمره زبانت رو وارد کن:", reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True))
    return LANG_SCORE

async def get_lang_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK_BTN:
        return await show_main_menu(update, context)
    update_user_db(
        update.message.from_user.id,
        has_language_cert=True,
        language_score=f"{context.user_data.get('lang_type', '')} (نمره: {text}) ✅"
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
        "📎 <b>لطفا پوزیشن تحصیلی مورد نظر خود را ارسال کنید:</b> 👇\n\n"
        "<b>فرمت های مورد تایید:</b>\n"
        "• متن کپی شده\n"
        "• عکس/اسکرین شات\n"
        "• لینک مستقیم\n"
        "• فوروارد از کانال تلگرام",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True),
        parse_mode="HTML"
    )

async def check_and_handle_profile_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
    db.close()

    if not user or not user.target_degrees or not user.target_field:
        await update.message.reply_text(
            "📭 هنوز پروفایلت کامل نشده است.\n\n📄 لطفاً فایل رزومه (PDF/Word) خودت رو بفرست:",
            reply_markup=ReplyKeyboardMarkup(ONLY_BACK_KEYBOARD, resize_keyboard=True)
        )
        return RESUME

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
        return await update.message.reply_text("📭 هنوز هیچ پوزیشنی ذخیره نکردی!")
    saved = db.query(Position).filter(Position.user_id == user.id, Position.status == "Saved").all()
    if not saved:
        db.close()
        return await update.message.reply_text("📭 هنوز هیچ پوزیشنی ذخیره نکردی!")

    cards = []
    for p in saved:
        if p.raw_text:
            an = analyze_position(p.raw_text, user)
            title = an['title']
            deadline_line = an['deadline_line']
            details_str = an['details_str']
            link = p.extracted_link or an['best_url']
        else:
            title = "موقعیت تحصیلی"
            deadline_line = f"⏳ ددلاین: {html.escape(p.deadline or 'نامشخص')}"
            details_str = p.requirements or ""
            link = p.extracted_link or ""

        text_msg = (
            f"📌 <b>پوزیشن #{p.id}</b>\n"
            f"🏷 <b>{html.escape(title)}</b>\n"
            f"{deadline_line}\n\n"
            f"{details_str}"
        )
        cards.append((text_msg, build_position_buttons(p.id, link, include_save=False)))

    db.close()
    for text_msg, markup in cards:
        await update.message.reply_text(
            text_msg,
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

async def show_applied_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = db.query(UserProfile).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        db.close()
        return await update.message.reply_text("📭 لیست اپلای شده‌ها خالیست!")
    applied = db.query(Position).filter(Position.user_id == user.id, Position.status == "Applied").all()
    if not applied:
        db.close()
        return await update.message.reply_text("📭 لیست اپلای شده‌ها خالیست!")

    lines = []
    for p in applied:
        title = extract_position_title(p.raw_text) if p.raw_text else "موقعیت تحصیلی"
        lines.append(f"🎓 <b>پوزیشن #{p.id}</b> — {html.escape(title)}\n⏳ {html.escape(p.deadline or 'نامشخص')}")
    db.close()
    await update.message.reply_text("✅ <b>پوزیشن‌های اپلای شده:</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

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

async def process_batch_after_delay(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """جمع‌آوری پیام‌های فورواردی، ادغام پیام‌های مربوط به یک آگهی، و ارسال گزارش مجزا برای هر آگهی متفاوت"""
    try:
        await asyncio.sleep(2.5)
    except asyncio.CancelledError:
        return

    messages = PENDING_BATCHES.pop(user_id, [])
    BATCH_TASKS.pop(user_id, None)
    if not messages:
        return

    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
    if not user or not user.target_degrees:
        db.close()
        await context.bot.send_message(chat_id, "⚠️ پروفایل کامل نیست. ابتدا روی «👤 پروفایل من» کلیک کن.")
        return

    total = len(messages)
    wait = await context.bot.send_message(
        chat_id,
        f"⏳ در حال بررسی و تحلیل {total} پیام ارسالی..." if total > 1 else "⏳ در حال بررسی و تحلیل پوزیشن..."
    )

    extracted_items = []
    for idx, msg in enumerate(messages, start=1):
        text = (msg.text or msg.caption or "").strip()
        hidden_urls = extract_telegram_urls(msg)
        combined_text = text

        if hidden_urls:
            combined_text = f"{combined_text}\n" + "\n".join(hidden_urls)

        if msg.photo:
            try:
                img_p = f"data/screenshots/{user_id}_{idx}.jpg"
                file = await context.bot.get_file(msg.photo[-1].file_id)
                await file.download_to_drive(img_p)
                ocr_txt = await extract_text_from_screenshot(img_p)
                if ocr_txt:
                    combined_text = f"{combined_text}\n{ocr_txt}".strip()
            except Exception as e:
                print(f"Photo download/OCR error: {e}")

        urls = list(dict.fromkeys([u.rstrip(').,;:]') for u in re.findall(r'(https?://[^\s<>"]+)', combined_text)]))
        if len(urls) >= 1 and len(text.split()) <= 5 and not msg.photo:
            content = await fetch_webpage_content(urls[0])
            combined_text = f"{combined_text}\n{content}".strip()

        extracted_items.append({
            "text": combined_text,
            "urls": set(urls),
            "media_group_id": msg.media_group_id,
            "is_complete_ad": is_academic_position(combined_text)
        })

    ad_groups = []
    for item in extracted_items:
        if ad_groups and is_same_ad(ad_groups[-1], item):
            ad_groups[-1]['text'] = f"{ad_groups[-1]['text']}\n\n{item['text']}".strip()
            ad_groups[-1]['urls'].update(item['urls'])
            ad_groups[-1]['is_complete_ad'] = ad_groups[-1]['is_complete_ad'] or item['is_complete_ad']
        else:
            ad_groups.append(item)

    valid_sent = 0
    for grp in ad_groups:
        full_text = grp['text']
        if not is_academic_position(full_text):
            continue

        an = analyze_position(full_text, user)
        pos = Position(
            user_id=user.id,
            raw_text=full_text[:3000],
            extracted_link=an['best_url'],
            requirements=an['details_str'],
            deadline=an['dl']
        )
        db.add(pos)
        db.commit()

        rep = (
            f"📊 <b>گزارش یکپارچه پوزیشن تحصیلی</b>\n"
            f"{an['status_line']}\n"
            f"{an['deadline_line']}\n\n"
            f"📌 <b>پوزیشن #{pos.id}</b>\n"
            f"🏷 <b>{html.escape(an['title'])}</b>\n\n"
            f"{an['details_str']}"
        )

        await context.bot.send_message(
            chat_id,
            rep,
            reply_markup=build_position_buttons(pos.id, an['best_url'], include_save=True),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        valid_sent += 1

    await wait.delete()

    if valid_sent == 0:
        await context.bot.send_message(
            chat_id,
            "⚠️ لطفاً پیام ارسالی را مجدداً بررسی کنید و فقط پوزیشن اپلای تحصیلی را ارسال کنید:"
        )

    db.close()

async def handle_router_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or msg.caption or "").strip()

    if text == '📤 ارسال پوزیشن':
        return await prompt_send_position(update, context)
    elif text == '💾 پوزیشن های ذخیره شده':
        return await show_saved_positions(update, context)
    elif text == '✅ پوزیشن های اپلای شده':
        return await show_applied_positions(update, context)
    elif text == '💬 پشتیبانی':
        return await msg.reply_text(f"پشتیبانی: @{SUPPORT_TELEGRAM_ID}")
    elif text == "▶️ یوتیوب Honi's Hub":
        return await msg.reply_text(f"کانال: {YOUTUBE_CHANNEL_URL}")
    elif text in ['✨ بهبود رزومه (به‌زودی)', '📝 نگارش انگیزه نامه (به‌زودی)']:
        return await msg.reply_text("🚧 به‌زودی فعال می‌شود!")
    elif text == BACK_BTN:
        return await show_main_menu(update, context)

    user_id = msg.from_user.id
    chat_id = msg.chat_id
    PENDING_BATCHES.setdefault(user_id, []).append(msg)

    if user_id in BATCH_TASKS:
        BATCH_TASKS[user_id].cancel()

    BATCH_TASKS[user_id] = asyncio.create_task(process_batch_after_delay(user_id, chat_id, context))

async def handle_pos_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "edit_profile":
        return
    if q.data == "no_link":
        await q.answer("🚫 لینک اپلای برای این پوزیشن در دسترس نیست.", show_alert=True)
        return

    await q.answer("⏳...")
    act, p_id = q.data.split("_")
    db = SessionLocal()
    p = db.query(Position).filter(Position.id == int(p_id)).first()
    if p:
        if act == "save":
            p.status = "Saved"
            action_label = "ذخیره شد 💾"
        elif act == "applied":
            p.status = "Applied"
            action_label = "در لیست اپلای شده‌ها ثبت شد ✅"
        elif act == "delete":
            db.delete(p)
            action_label = "حذف شد 🗑"
        else:
            action_label = "انجام شد ✅"
        db.commit()
        await q.edit_message_text(q.message.text_html + f"\n\n✅ <b>پوزیشن {action_label}</b>", parse_mode="HTML")
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
            MessageHandler(filters.Regex('^👤 پروفایل من$'), check_and_handle_profile_btn),
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