import os
import re
import html
import zipfile
import asyncio
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse
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
from texts import (
    BACK_BTN, BTNS, t,
    get_main_menu_kb, get_degree_kb, get_field_kb,
    get_country_kb, get_has_lang_kb, get_lang_type_kb, get_only_back_kb
)

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

ACADEMIC_KEYWORDS = [
    'phd', 'ph.d', 'master', 'msc', 'postdoc', 'post-doc', 'doctoral', 'doctorate',
    'scholarship', 'fellowship', 'fully funded', 'funding', 'stipend', 'tuition',
    'university', 'professor', 'supervisor', 'faculty', 'department', 'laboratory', 'lab',
    'research assistant', 'teaching assistant', 'graduate', 'admission', 'apply', 'application',
    'deadline', 'position', 'vacancy', 'candidate', 'cv', 'resume', 'transcript', 'sop',
    'دکتری', 'دکترا', 'کارشناسی ارشد', 'ارشد', 'پست داک', 'پست‌داک', 'فاند', 'فول فاند',
    'بورسیه', 'پوزیشن', 'اپلای', 'دانشگاه', 'استاد', 'ددلاین', 'پذیرش', 'تحصیلی', 'پژوهشی'
]

# Bilingual skill map: canonical_name -> [English & Persian variants]
BILINGUAL_SKILLS = {
    'Python': ['python', 'پایتون'],
    'Java': ['java', 'جاوا'],
    'SQL': ['sql', 'اس کیو ال', 'پایگاه داده', 'دیتابیس'],
    'Flutter': ['flutter', 'فلاتر'],
    'Dart': ['dart', 'دارت'],
    'Machine Learning': ['machine learning', 'یادگیری ماشین'],
    'Deep Learning': ['deep learning', 'یادگیری عمیق'],
    'AI': ['artificial intelligence', 'هوش مصنوعی'],
    'NLP': ['nlp', 'natural language processing', 'پردازش زبان طبیعی'],
    'Data Analysis': ['data analysis', 'data analytics', 'تحلیل داده', 'داده کاوی', 'داده‌کاوی'],
    'Cloud': ['cloud', 'رایانش ابری', 'ابر'],
    'Docker': ['docker', 'داکر'],
    'Git': ['git', 'گیت', 'گیت‌هاب', 'گیت هاب'],
    'C++': ['c++', 'سی پلاس پلاس'],
    'MATLAB': ['matlab', 'متلب'],
    'BI': ['power bi', 'business intelligence', 'هوش تجاری'],
    'ERP': ['erp', 'برنامه‌ریزی منابع سازمانی'],
    'Agile/Scrum': ['agile', 'scrum', 'اجایل', 'اسکرام'],
    'Software Engineering': ['software engineering', 'مهندسی نرم‌افزار', 'مهندسی نرم افزار'],
}

PENDING_BATCHES = {}
BATCH_TASKS = {}

async def post_init_setup(application: Application) -> None:
    commands = [
        BotCommand("start", "🏠 Start / شروع ربات"),
        BotCommand("menu", "🏠 Main Menu / منوی اصلی"),
        BotCommand("lang", "🌐 Language / تغییر زبان")
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

def get_user_lang(user_id: int) -> str:
    db = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
        return user.language if (user and user.language in ('fa', 'en')) else 'fa'
    except Exception as e:
        print(f"get_user_lang error: {e}")
        return 'fa'
    finally:
        db.close()

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
        print(f"update_user_db error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def is_back(text: str) -> bool:
    return text in (BACK_BTN['fa'], BACK_BTN['en'])

def is_academic_position(text: str) -> bool:
    if not text or len(text.strip()) < 25:
        return False
    l_text = text.lower()
    score = sum(1 for kw in ACADEMIC_KEYWORDS if kw in l_text)
    return score >= 2

def is_general_listing_url(url: str, page_title: str = "") -> bool:
    try:
        parsed = urlparse(url.strip())
        path = parsed.path.strip('/').lower()
        if not path or path in ['en', 'fa', 'home', 'index.html', 'index.php']:
            return True
        generic_paths = {
            'jobs', 'careers', 'vacancies', 'positions', 'scholarships',
            'opportunities', 'search', 'find-a-phd', 'phd-positions',
            'open-positions', 'all-jobs', 'listings', 'fellowships', 'grants'
        }
        segments = [s for s in path.split('/') if s]
        if len(segments) == 1 and segments[0] in generic_paths:
            return True
        l_title = (page_title or "").lower()
        portal_phrases = [
            'search engine', 'global opportunity', 'find scholarships',
            'all scholarships', 'job board', 'browse jobs', 'open positions list'
        ]
        if any(p in l_title for p in portal_phrases):
            return True
    except Exception:
        pass
    return False

def extract_position_title(text: str, lang: str = 'fa') -> str:
    default_title = "Academic Position" if lang == 'en' else "موقعیت تحصیلی"
    if not text:
        return default_title
    bullet_prefixes = ('•', '-', '*', '▪', '▫', '🔹', '🔸', '✅', '❌', '✔', '1.', '2.', '3.')
    skip_phrases = ['مدرک کارشناسی', 'مدارک مورد نیاز', 'شرایط اپلای', 'نحوه اپلای', 'لینک اپلای', 'requirements', 'how to apply']

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("http", "@", "#")) or line.startswith(bullet_prefixes):
            continue
        clean_line = re.sub(r'https?://\S+', '', line).strip()
        if len(clean_line) < 6 or any(p in clean_line.lower() for p in skip_phrases):
            continue
        return clean_line[:110] + ("..." if len(clean_line) > 110 else "")
    return default_title

def extract_resume_text(file_path: str) -> str:
    """استخراج متن رزومه فارسی یا انگلیسی از فایل‌های PDF و DOCX"""
    if not file_path or not os.path.exists(file_path):
        return ""
    lower_path = file_path.lower()
    if lower_path.endswith(".pdf") and HAS_PYPDF:
        try:
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages).lower()
        except Exception as e:
            print(f"PDF read error: {e}")
            return ""
    elif lower_path.endswith(".docx"):
        try:
            with zipfile.ZipFile(file_path) as z:
                xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            texts = [elem.text for elem in tree.iter() if elem.text]
            return " ".join(texts).lower()
        except Exception as e:
            print(f"DOCX read error: {e}")
            return ""
    return ""

def parse_deadline(text: str):
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
            return evaluate_date(datetime(int(m1.group(3)), months[m1.group(1)], int(m1.group(2))), m1.group(0).title())
        except ValueError:
            pass

    m2 = re.search(rf'(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_pattern})\.?,?\s+(202[4-9])', l_text)
    if m2:
        try:
            return evaluate_date(datetime(int(m2.group(3)), months[m2.group(2)], int(m2.group(1))), m2.group(0).title())
        except ValueError:
            pass

    m3 = re.search(r'(202[4-9])[-/](\d{1,2})[-/](\d{1,2})', l_text)
    if m3:
        try:
            return evaluate_date(datetime(int(m3.group(1)), int(m3.group(2)), int(m3.group(3))), m3.group(0))
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

def normalize_degree_key(deg_str: str) -> str:
    d = (deg_str or "").lower()
    if any(k in d for k in ['postdoc', 'پست']): return 'postdoc'
    if any(k in d for k in ['phd', 'دکتر']): return 'phd'
    if any(k in d for k in ['master', 'ارشد']): return 'master'
    if any(k in d for k in ['bachelor', 'کارشناسی']): return 'bachelor'
    return ''

def analyze_position(text: str, user: UserProfile, lang: str = 'fa') -> dict:
    urls = list(dict.fromkeys([u.rstrip(').,;:]') for u in re.findall(r'(https?://[^\s<>"]+)', text)]))
    best_url = pick_best_apply_url(urls)
    title = extract_position_title(text, lang)
    l_text = text.lower()
    resume_text = extract_resume_text(user.resume_file_path)

    details = []
    match_count = 0
    deadline_str, is_expired, is_near = parse_deadline(text)

    # 1. Degree
    degree_map = {
        'phd': (['phd', 'ph.d', 'doctoral', 'doctorate', 'دکتری', 'دکترا'], {'fa': 'دکتری', 'en': 'PhD'}),
        'master': (['master', 'msc', 'm.sc', 'ارشد', 'کارشناسی ارشد'], {'fa': 'کارشناسی ارشد', 'en': 'Master'}),
        'postdoc': (['postdoc', 'post-doc', 'پست داک', 'پست‌داک', 'پست دکتری'], {'fa': 'پست دکتری', 'en': 'Postdoc'}),
        'bachelor': (['bachelor', 'bsc', 'undergraduate', 'کارشناسی'], {'fa': 'کارشناسی', 'en': 'Bachelor'})
    }
    pos_deg_keys = [k for k, (kws, _) in degree_map.items() if any(kw in l_text for kw in kws)]
    user_deg_raw = (user.target_degrees or "").strip()
    user_deg_key = normalize_degree_key(user_deg_raw)

    if pos_deg_keys:
        pos_deg_labels = [degree_map[k][1][lang] for k in pos_deg_keys]
        if user_deg_key in pos_deg_keys:
            match_count += 1
            if lang == 'en':
                details.append(f"🎓 <b>Degree:</b> Matches your target ({html.escape(user_deg_raw)}) ✅")
            else:
                details.append(f"🎓 <b>مقطع تحصیلی:</b> با هدف شما ({html.escape(user_deg_raw)}) کاملاً مطابقت دارد ✅")
        else:
            if lang == 'en':
                details.append(f"🎓 <b>Degree:</b> This position is for {' / '.join(pos_deg_labels)}, which doesn't match your target ({html.escape(user_deg_raw)}) ❌")
            else:
                details.append(f"🎓 <b>مقطع تحصیلی:</b> این پوزیشن برای {' / '.join(pos_deg_labels)} است و با هدف شما ({html.escape(user_deg_raw)}) همخوانی ندارد ❌")

    # 2. Field
    field_keywords = {
        ('کامپیوتر', 'computer', 'it'): ['computer', 'software', 'ai', 'artificial intelligence', 'machine learning', 'data', 'cyber', 'computing', 'کامپیوتر', 'نرم‌افزار', 'نرم افزار', 'هوش مصنوعی'],
        ('علوم داده', 'data', 'ai'): ['data', 'machine learning', 'ai', 'analytics', 'deep learning', 'علوم داده', 'هوش مصنوعی'],
        ('برق', 'electrical'): ['electrical', 'electronics', 'control', 'signal', 'برق', 'کنترل'],
        ('مکانیک', 'mechanical'): ['mechanical', 'robotics', 'thermal', 'مکانیک'],
        ('عمران', 'civil'): ['civil', 'structural', 'عمران'],
        ('شیمی', 'chemical', 'chemistry'): ['chemical', 'materials', 'chemistry', 'شیمی'],
        ('پزشکی', 'medicine', 'biology'): ['medical', 'biology', 'biomedical', 'bio', 'پزشکی', 'زیست'],
        ('معماری', 'architecture'): ['architecture', 'urban', 'معماری']
    }
    user_field = (user.target_field or "").strip()
    matched_field_kws = []
    for f_keys, kws in field_keywords.items():
        if any(fk in user_field.lower() for fk in f_keys):
            matched_field_kws = [k for k in kws if k in l_text]
            break

    if matched_field_kws:
        match_count += 1
        if lang == 'en':
            details.append(f"📚 <b>Field:</b> Relevant to «{html.escape(user_field)}» ({', '.join(matched_field_kws[:3])}) ✅")
        else:
            details.append(f"📚 <b>رشته تحصیلی:</b> مرتبط با حوزه «{html.escape(user_field)}» ({', '.join(matched_field_kws[:3])}) ✅")
    else:
        if lang == 'en':
            details.append(f"📚 <b>Field:</b> Keywords for «{html.escape(user_field)}» were not found in this position ❌")
        else:
            details.append(f"📚 <b>رشته تحصیلی:</b> کلیدواژه‌های رشته شما ({html.escape(user_field)}) در متن این پوزیشن پیدا نشد ❌")

    # 3. Bilingual Resume skills match (supports Persian & English CVs)
    if resume_text:
        shared_skills = []
        for skill_name, variants in BILINGUAL_SKILLS.items():
            in_cv = any(v in resume_text for v in variants)
            in_pos = any(v in l_text for v in variants)
            if in_cv and in_pos:
                shared_skills.append(skill_name)
        if shared_skills:
            match_count += 1
            if lang == 'en':
                details.append(f"📄 <b>CV Match:</b> Shared skills found in your resume ({', '.join(shared_skills[:5])}) ✅")
            else:
                details.append(f"📄 <b>تطابق با رزومه:</b> مهارت‌های مشترک ({', '.join(shared_skills[:5])}) در رزومه‌ات وجود دارد ✅")

    # 4. Language certificate
    if any(k in l_text for k in ['بدون مدرک', 'no ielts', 'waived', 'without ielts']):
        match_count += 1
        details.append("🗣 <b>Language:</b> No language certificate required ✅" if lang == 'en' else "🗣 <b>مدرک زبان:</b> بدون نیاز به مدرک زبان ✅")
    elif user.has_language_cert:
        match_count += 1
        if lang == 'en':
            details.append(f"🗣 <b>Language:</b> You have a certificate ({html.escape(user.language_score or '')}) ✅")
        else:
            details.append(f"🗣 <b>مدرک زبان:</b> دارای مدرک ({html.escape(user.language_score or '')}) ✅")
    else:
        if lang == 'en':
            details.append("🗣 <b>Language:</b> Your profile has no IELTS/TOEFL score, which may be required ❌")
        else:
            details.append("🗣 <b>مدرک زبان:</b> پروفایل شما فاقد مدرک IELTS/TOEFL است و احتمالاً برای اپلای نیاز خواهد بود ❌")

    is_eligible = (not is_expired) and (match_count >= 1)

    if is_expired:
        status_line = "❌ Not Eligible (Deadline Passed)" if lang == 'en' else "❌ غیرقابل اپلای (ددلاین گذشته است)"
        deadline_line = (
            f"❌ Unfortunately, the application deadline has passed ({html.escape(deadline_str)})"
            if lang == 'en'
            else f"❌ متاسفانه ددلاین اپلای این پوزیشن گذشته است ({html.escape(deadline_str)})"
        )
    else:
        if lang == 'en':
            status_line = "✅ Eligible to Apply" if is_eligible else "⚠️ Needs Review (Profile Mismatch)"
            if deadline_str:
                deadline_line = f"⚠️ ⏳ Deadline: {html.escape(deadline_str)} — Closing soon!" if is_near else f"⏳ Deadline: {html.escape(deadline_str)}"
            else:
                deadline_line = "⏳ Deadline: Not specified (Check website)"
        else:
            status_line = "✅ قابل اپلای برای شما" if is_eligible else "⚠️ نیازمند بررسی بیشتر (عدم تطابق با پروفایل)"
            if deadline_str:
                deadline_line = f"⚠️ ⏳ ددلاین دارد ({html.escape(deadline_str)}) — ددلاین نزدیک است!" if is_near else f"⏳ ددلاین دارد ({html.escape(deadline_str)})"
            else:
                deadline_line = "⏳ ددلاین: نامشخص (بررسی در سایت)"

    return {
        "title": title,
        "best_url": best_url,
        "status_line": status_line,
        "deadline_line": deadline_line,
        "details_str": "\n\n".join(details),
        "dl": deadline_str or ("Not specified" if lang == 'en' else "نامشخص (بررسی در سایت)")
    }

def build_position_buttons(pos_id: int, best_url: str, lang: str, include_save: bool = True) -> InlineKeyboardMarkup:
    btn = []
    if best_url and best_url.startswith("http"):
        btn.append([InlineKeyboardButton(t(lang, 'btn_apply'), url=best_url)])
    else:
        btn.append([InlineKeyboardButton(t(lang, 'btn_no_link'), callback_data="no_link")])

    if include_save:
        btn.append([
            InlineKeyboardButton(t(lang, 'btn_applied'), callback_data=f"applied_{pos_id}"),
            InlineKeyboardButton(t(lang, 'btn_save'), callback_data=f"save_{pos_id}")
        ])
        btn.append([InlineKeyboardButton(t(lang, 'btn_delete'), callback_data=f"delete_{pos_id}")])
    else:
        btn.append([
            InlineKeyboardButton(t(lang, 'btn_applied'), callback_data=f"applied_{pos_id}"),
            InlineKeyboardButton(t(lang, 'btn_delete'), callback_data=f"delete_{pos_id}")
        ])
    return InlineKeyboardMarkup(btn)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    try:
        if isinstance(update, Update) and update.effective_message:
            lang = get_user_lang(update.effective_user.id) if update.effective_user else 'fa'
            await update.effective_message.reply_text(
                t(lang, 'error_generic'),
                reply_markup=ReplyKeyboardMarkup(get_main_menu_kb(lang), resize_keyboard=True)
            )
    except Exception:
        pass

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
    has_lang = bool(user and user.language in ('fa', 'en'))
    lang = user.language if has_lang else None
    db.close()

    if not has_lang:
        kb = [[
            InlineKeyboardButton("🇮🇷 فارسی", callback_data="setlang_fa"),
            InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")
        ]]
        await update.message.reply_text(t('fa', 'choose_lang'), reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    return await show_main_menu(update, context, lang=lang)

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[
        InlineKeyboardButton("🇮🇷 فارسی", callback_data="setlang_fa"),
        InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")
    ]]
    await update.message.reply_text(t('fa', 'choose_lang'), reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str = None) -> int:
    lang = lang or get_user_lang(update.effective_user.id)
    msg_target = update.message or update.callback_query.message
    await msg_target.reply_text(
        t(lang, 'welcome_menu'),
        reply_markup=ReplyKeyboardMarkup(get_main_menu_kb(lang), resize_keyboard=True),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def _download_resume_bg(bot, file_id: str, file_path: str):
    """دانلود رزومه در پس‌زمینه تا ربات بدون تاخیر به کاربر پاسخ دهد"""
    try:
        file = await bot.get_file(file_id)
        await file.download_to_drive(file_path)
    except Exception as e:
        print(f"Background resume download error: {e}")

async def get_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    if update.message.text and is_back(update.message.text.strip()):
        return await show_main_menu(update, context, lang)
    if not update.message.document:
        await update.message.reply_text(
            t(lang, 'send_resume_prompt'),
            reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True)
        )
        return RESUME

    doc = update.message.document
    user_id = update.message.from_user.id
    safe_filename = re.sub(r'[^\w\.-]', '_', doc.file_name or "resume.pdf")
    file_path = f"data/resumes/{user_id}_{safe_filename}"

    if not update_user_db(user_id, resume_file_id=doc.file_id, resume_file_path=file_path):
        await update.message.reply_text(t(lang, 'save_error'))
        return RESUME

    # دانلود در پس‌زمینه (بدون معطل کردن کاربر و بدون خطای تایم‌اوت)
    asyncio.create_task(_download_resume_bg(context.bot, doc.file_id, file_path))

    await update.message.reply_text(
        t(lang, 'ask_degree'),
        reply_markup=ReplyKeyboardMarkup(get_degree_kb(lang), resize_keyboard=True)
    )
    return DEGREE

async def get_degree(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    update_user_db(update.message.from_user.id, target_degrees=text.replace("🎓", "").strip())
    await update.message.reply_text(t(lang, 'ask_field'), reply_markup=ReplyKeyboardMarkup(get_field_kb(lang), resize_keyboard=True))
    return FIELD

async def get_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    if text in (BTNS['custom_field']['fa'], BTNS['custom_field']['en']):
        await update.message.reply_text(t(lang, 'type_field'), reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True))
        return CUSTOM_FIELD
    update_user_db(update.message.from_user.id, target_field=re.sub(r'^[^\w\s]+\s*', '', text).strip())
    return await ask_country(update, context, lang)

async def get_custom_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    update_user_db(update.message.from_user.id, target_field=text)
    return await ask_country(update, context, lang)

async def ask_country(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    await update.message.reply_text(t(lang, 'ask_country'), reply_markup=ReplyKeyboardMarkup(get_country_kb(lang), resize_keyboard=True))
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    if text in (BTNS['custom_country']['fa'], BTNS['custom_country']['en']):
        await update.message.reply_text(t(lang, 'type_country'), reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True))
        return CUSTOM_COUNTRY
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context, lang)

async def get_custom_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    update_user_db(update.message.from_user.id, target_countries=text)
    return await ask_language(update, context, lang)

async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    await update.message.reply_text(t(lang, 'ask_has_lang'), reply_markup=ReplyKeyboardMarkup(get_has_lang_kb(lang), resize_keyboard=True))
    return HAS_LANG

async def get_has_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    if text in (BTNS['yes']['fa'], BTNS['yes']['en']):
        update_user_db(update.message.from_user.id, has_language_cert=True)
        await update.message.reply_text(t(lang, 'ask_lang_type'), reply_markup=ReplyKeyboardMarkup(get_lang_type_kb(lang), resize_keyboard=True))
        return LANG_TYPE
    elif text in (BTNS['no']['fa'], BTNS['no']['en']):
        update_user_db(update.message.from_user.id, has_language_cert=False, language_score=t(lang, 'no_cert_val'))
        return await finish_profile(update, context, lang)
    else:
        await update.message.reply_text(
            t(lang, 'invalid_yes_no'),
            reply_markup=ReplyKeyboardMarkup(get_has_lang_kb(lang), resize_keyboard=True)
        )
        return HAS_LANG

async def get_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    if text in (BTNS['other_lang']['fa'], BTNS['other_lang']['en']):
        await update.message.reply_text(t(lang, 'type_lang_name'), reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True))
        return CUSTOM_LANG_TYPE
    context.user_data['lang_type'] = text.replace("🇬🇧", "").replace("🇺🇸", "").strip()
    await update.message.reply_text(t(lang, 'ask_lang_score'), reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True))
    return LANG_SCORE

async def get_custom_lang_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    context.user_data['lang_type'] = text
    await update.message.reply_text(t(lang, 'ask_lang_score'), reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True))
    return LANG_SCORE

async def get_lang_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    text = update.message.text.strip()
    if is_back(text):
        return await show_main_menu(update, context, lang)
    score_str = t(lang, 'score_fmt', type=context.user_data.get('lang_type', ''), score=text)
    update_user_db(update.message.from_user.id, has_language_cert=True, language_score=score_str)
    return await finish_profile(update, context, lang)

async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
    msg = t(
        lang, 'profile_done',
        deg=html.escape(user.target_degrees or '-'),
        field=html.escape(user.target_field or '-'),
        country=html.escape(user.target_countries or '-'),
        lang_score=html.escape(user.language_score or '-')
    )
    db.close()
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(get_main_menu_kb(lang), resize_keyboard=True), parse_mode="HTML")
    return ConversationHandler.END

async def prompt_send_position(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    await update.message.reply_text(
        t(lang, 'prompt_send_pos'),
        reply_markup=ReplyKeyboardMarkup(get_main_menu_kb(lang), resize_keyboard=True),
        parse_mode="HTML"
    )

async def check_and_handle_profile_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == update.message.from_user.id).first()
    db.close()

    if not user or not user.target_degrees or not user.target_field:
        await update.message.reply_text(
            t(lang, 'profile_incomplete'),
            reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True)
        )
        return RESUME

    resume_name = os.path.basename(user.resume_file_path) if user.resume_file_path else ("Uploaded" if lang == 'en' else "ثبت شده")
    other_lang = 'en' if lang == 'fa' else 'fa'
    kb = [
        [InlineKeyboardButton(t(lang, 'btn_edit_profile'), callback_data="edit_profile")],
        [InlineKeyboardButton(t(lang, 'btn_change_lang'), callback_data=f"setlang_{other_lang}")]
    ]
    await update.message.reply_text(
        t(
            lang, 'profile_view',
            resume=html.escape(resume_name),
            deg=html.escape(user.target_degrees),
            field=html.escape(user.target_field),
            country=html.escape(user.target_countries or '-'),
            lang_score=html.escape(user.language_score or '-')
        ),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def start_from_inline_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(update.effective_user.id)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        t(lang, 'upload_new_resume'),
        reply_markup=ReplyKeyboardMarkup(get_only_back_kb(lang), resize_keyboard=True)
    )
    return RESUME

async def show_saved_positions(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    db = SessionLocal()
    user = db.query(UserProfile).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        db.close()
        return await update.message.reply_text(t(lang, 'saved_empty'))
    saved = db.query(Position).filter(Position.user_id == user.id, Position.status == "Saved").all()
    if not saved:
        db.close()
        return await update.message.reply_text(t(lang, 'saved_empty'))

    cards = []
    for p in saved:
        if p.raw_text:
            an = analyze_position(p.raw_text, user, lang)
            deadline_line, details_str = an['deadline_line'], an['details_str']
            link = p.extracted_link or an['best_url']
        else:
            deadline_line = f"⏳ {html.escape(p.deadline or '-')}"
            details_str = p.requirements or ""
            link = p.extracted_link or ""

        text_msg = (
            f"{t(lang, 'pos_num', id=p.id)}\n"
            f"{deadline_line}\n\n"
            f"{details_str}"
        )
        cards.append((text_msg, build_position_buttons(p.id, link, lang, include_save=False)))

    db.close()
    for text_msg, markup in cards:
        await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

async def show_applied_positions(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    db = SessionLocal()
    user = db.query(UserProfile).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        db.close()
        return await update.message.reply_text(t(lang, 'applied_empty'))
    applied = db.query(Position).filter(Position.user_id == user.id, Position.status == "Applied").all()
    if not applied:
        db.close()
        return await update.message.reply_text(t(lang, 'applied_empty'))

    lines = []
    for p in applied:
        title = extract_position_title(p.raw_text, lang) if p.raw_text else ("Academic Position" if lang == 'en' else "موقعیت تحصیلی")
        lines.append(f"🎓 <b>#{p.id}</b> — {html.escape(title)}\n⏳ {html.escape(p.deadline or '-')}")
    db.close()
    await update.message.reply_text(t(lang, 'applied_header') + "\n\n".join(lines), parse_mode="HTML")

async def fetch_webpage_content(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return "", ""
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.extract()
            h1 = soup.find("h1")
            page_title = (h1.get_text(strip=True) if h1 else (soup.title.string.strip() if soup.title and soup.title.string else ""))
            body_text = soup.get_text(separator=' ', strip=True)[:4000]
            return page_title, f"{page_title}\n{body_text}"
    except Exception:
        return "", ""

async def extract_text_from_screenshot(file_path: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
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
    try:
        await asyncio.sleep(1.2)
    except asyncio.CancelledError:
        return

    messages = PENDING_BATCHES.pop(user_id, [])
    BATCH_TASKS.pop(user_id, None)
    if not messages:
        return

    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.telegram_id == user_id).first()
    lang = user.language if (user and user.language in ('fa', 'en')) else 'fa'

    if not user or not user.target_degrees:
        db.close()
        await context.bot.send_message(chat_id, t(lang, 'need_profile'))
        return

    total = len(messages)
    wait = await context.bot.send_message(
        chat_id,
        t(lang, 'processing_many', n=total) if total > 1 else t(lang, 'processing_one')
    )

    extracted_items = []
    general_url_detected = False

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
            if is_general_listing_url(urls[0]):
                general_url_detected = True
                continue
            page_title, content = await fetch_webpage_content(urls[0])
            if is_general_listing_url(urls[0], page_title):
                general_url_detected = True
                continue
            combined_text = f"{content}\n{combined_text}".strip()

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

        an = analyze_position(full_text, user, lang)
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
            f"{t(lang, 'report_header')}\n"
            f"{an['status_line']}\n"
            f"{an['deadline_line']}\n\n"
            f"{t(lang, 'pos_num', id=pos.id)}\n\n"
            f"{an['details_str']}"
        )

        await context.bot.send_message(
            chat_id,
            rep,
            reply_markup=build_position_buttons(pos.id, an['best_url'], lang, include_save=True),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        valid_sent += 1

    try:
        await wait.delete()
    except Exception:
        pass

    if general_url_detected and valid_sent == 0:
        await context.bot.send_message(chat_id, t(lang, 'general_url_err'), parse_mode="HTML")
    elif valid_sent == 0:
        await context.bot.send_message(chat_id, t(lang, 'not_academic_err'))

    db.close()

async def handle_router_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or msg.caption or "").strip()
    lang = get_user_lang(msg.from_user.id)

    if text in (BTNS['send_pos']['fa'], BTNS['send_pos']['en']):
        return await prompt_send_position(update, context, lang)
    elif text in (BTNS['saved']['fa'], BTNS['saved']['en']):
        return await show_saved_positions(update, context, lang)
    elif text in (BTNS['applied']['fa'], BTNS['applied']['en']):
        return await show_applied_positions(update, context, lang)
    elif text in (BTNS['support']['fa'], BTNS['support']['en']):
        return await msg.reply_text(
            t(lang, 'support_msg'),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, 'support_btn'), url=f"https://t.me/{SUPPORT_TELEGRAM_ID}")]])
        )
    elif text in (BTNS['youtube']['fa'], BTNS['youtube']['en']):
        return await msg.reply_text(
            t(lang, 'youtube_msg'),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, 'youtube_btn'), url=YOUTUBE_CHANNEL_URL)]])
        )
    elif text in (BTNS['cv_soon']['fa'], BTNS['cv_soon']['en'], BTNS['sop_soon']['fa'], BTNS['sop_soon']['en']):
        return await msg.reply_text(t(lang, 'coming_soon'))
    elif is_back(text):
        return await show_main_menu(update, context, lang)

    user_id = msg.from_user.id
    chat_id = msg.chat_id
    PENDING_BATCHES.setdefault(user_id, []).append(msg)

    if user_id in BATCH_TASKS:
        BATCH_TASKS[user_id].cancel()

    BATCH_TASKS[user_id] = asyncio.create_task(process_batch_after_delay(user_id, chat_id, context))

async def handle_pos_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id

    if q.data == "edit_profile":
        return

    if q.data.startswith("setlang_"):
        new_lang = q.data.split("_")[1]
        update_user_db(user_id, language=new_lang)
        await q.answer("✅ Language updated!" if new_lang == 'en' else "✅ زبان ذخیره شد!")
        try:
            await q.message.delete()
        except Exception:
            pass
        await show_main_menu(update, context, lang=new_lang)
        return

    lang = get_user_lang(user_id)
    if q.data == "no_link":
        await q.answer(t(lang, 'no_link_alert'), show_alert=True)
        return

    await q.answer("⏳...")
    act, p_id = q.data.split("_")
    db = SessionLocal()
    p = db.query(Position).filter(Position.id == int(p_id)).first()
    if p:
        if act == "save":
            p.status = "Saved"
            action_msg = t(lang, 'act_saved')
        elif act == "applied":
            p.status = "Applied"
            action_msg = t(lang, 'act_applied')
        elif act == "delete":
            db.delete(p)
            action_msg = t(lang, 'act_deleted')
        else:
            action_msg = "✅"
        db.commit()
        await q.edit_message_text(q.message.text_html + f"\n\n{action_msg}", parse_mode="HTML")
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

    back_regex = f"^({re.escape(BACK_BTN['fa'])}|{re.escape(BACK_BTN['en'])})$"
    profile_regex = f"^({re.escape(BTNS['profile']['fa'])}|{re.escape(BTNS['profile']['en'])})$"

    cv_h = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(profile_regex), check_and_handle_profile_btn),
            CallbackQueryHandler(start_from_inline_edit, pattern='^edit_profile$')
        ],
        states={
            RESUME: [MessageHandler(filters.Regex(back_regex), show_main_menu), MessageHandler(filters.ALL & ~filters.COMMAND, get_resume)],
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
            MessageHandler(filters.Regex(back_regex), show_main_menu),
            CommandHandler('start', cmd_start),
            CommandHandler('menu', show_main_menu),
            CommandHandler('lang', cmd_lang)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('menu', show_main_menu))
    app.add_handler(CommandHandler('lang', cmd_lang))
    app.add_handler(cv_h)
    app.add_handler(CallbackQueryHandler(handle_pos_btn))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION | filters.PHOTO) & ~filters.COMMAND, handle_router_message))
    app.add_error_handler(global_error_handler)

    print("🚀 Bilingual Bot is ready in Production!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()