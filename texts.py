BACK_BTN = {
    'fa': "🔙 بازگشت به منو اصلی",
    'en': "🔙 Back to Main Menu"
}

BTNS = {
    'send_pos': {'fa': '📤 ارسال پوزیشن', 'en': '📤 Send Position'},
    'profile': {'fa': '👤 پروفایل من', 'en': '👤 My Profile'},
    'saved': {'fa': '💾 پوزیشن های ذخیره شده', 'en': '💾 Saved Positions'},
    'applied': {'fa': '✅ پوزیشن های اپلای شده', 'en': '✅ Applied Positions'},
    'support': {'fa': '💬 پشتیبانی', 'en': '💬 Support'},
    'youtube': {'fa': "▶️ یوتیوب Honi's Hub", 'en': "▶️ Honi's Hub YouTube"},
    'cv_soon': {'fa': '✨ بهبود رزومه (به‌زودی)', 'en': '✨ CV Review (Soon)'},
    'sop_soon': {'fa': '📝 نگارش انگیزه نامه (به‌زودی)', 'en': '📝 SOP Writing (Soon)'},
    'yes': {'fa': '✅ بله', 'en': '✅ Yes'},
    'no': {'fa': '❌ خیر', 'en': '❌ No'},
    'custom_field': {'fa': '✏️ رشته‌ام در لیست نیست (تایپ می‌کنم)', 'en': '✏️ My field is not listed (Type it)'},
    'custom_country': {'fa': '🌍 کشور هدفم در لیست نیست (تایپ می‌کنم)', 'en': '🌍 My country is not listed (Type it)'},
    'other_lang': {'fa': '🗣 مدرک زبان دیگری دارم', 'en': '🗣 Other language certificate'},
}

def get_main_menu_kb(lang: str):
    return [
        [BTNS['send_pos'][lang], BTNS['profile'][lang]],
        [BTNS['saved'][lang], BTNS['applied'][lang]],
        [BTNS['support'][lang], BTNS['youtube'][lang]],
        [BTNS['cv_soon'][lang], BTNS['sop_soon'][lang]]
    ]

def get_degree_kb(lang: str):
    if lang == 'en':
        return [['🎓 Bachelor', '🎓 Master'], ['🎓 PhD', '🎓 Postdoc'], [BACK_BTN['en']]]
    return [['🎓 کارشناسی', '🎓 کارشناسی ارشد'], ['🎓 دکتری', '🎓 پست دکتری'], [BACK_BTN['fa']]]

def get_field_kb(lang: str):
    if lang == 'en':
        return [
            ['💻 Computer Engineering & IT', '📊 Data Science & AI', '⚡ Electrical Engineering'],
            ['⚙️ Mechanical Engineering', '🏗 Civil Engineering', '🧪 Chemical & Materials'],
            ['🧬 Medicine & Biology', '💊 Chemistry & Pharmacy', '🏛 Architecture & Urban'],
            [BTNS['custom_field']['en']],
            [BACK_BTN['en']]
        ]
    return [
        ['💻 مهندسی کامپیوتر و IT', '📊 علوم داده و هوش مصنوعی', '⚡ مهندسی برق'],
        ['⚙️ مهندسی مکانیک', '🏗 مهندسی عمران', '🧪 مهندسی شیمی و مواد'],
        ['🧬 پزشکی و زیست‌شناسی', '💊 شیمی و داروسازی', '🏛 معماری و شهرسازی'],
        [BTNS['custom_field']['fa']],
        [BACK_BTN['fa']]
    ]

def get_country_kb(lang: str):
    if lang == 'en':
        return [
            ['🌐 All Countries'],
            ['USA 🇺🇸', 'Australia 🇦🇺', 'Canada 🇨🇦'],
            ['New Zealand 🇳🇿', 'Finland 🇫🇮', 'Germany 🇩🇪'],
            ['UK 🇬🇧', 'Spain 🇪🇸', 'Sweden 🇸🇪'],
            [BTNS['custom_country']['en']],
            [BACK_BTN['en']]
        ]
    return [
        ['🌐 همه کشورها'],
        ['آمریکا 🇺🇸', 'استرالیا 🇦🇺', 'کانادا 🇨🇦'],
        ['نیوزلند 🇳🇿', 'فنلاند 🇫🇮', 'آلمان 🇩🇪'],
        ['انگلیس 🇬🇧', 'اسپانیا 🇪🇸', 'سوئد 🇸🇪'],
        [BTNS['custom_country']['fa']],
        [BACK_BTN['fa']]
    ]

def get_has_lang_kb(lang: str):
    return [[BTNS['yes'][lang], BTNS['no'][lang]], [BACK_BTN[lang]]]

def get_lang_type_kb(lang: str):
    return [['🇬🇧 IELTS', '🇺🇸 TOEFL'], [BTNS['other_lang'][lang]], [BACK_BTN[lang]]]

def get_only_back_kb(lang: str):
    return [[BACK_BTN[lang]]]

TEXTS = {
    'choose_lang': "🌐 لطفاً زبان خود را انتخاب کنید:\nPlease select your preferred language:",
    'welcome_menu': {
        'fa': "سلام! 👋🎓 به دستیار هوشمند اپلای خوش آمدی.\n\n🏠 <b>منوی اصلی:</b>",
        'en': "Welcome to Academic Position Finder! 👋🎓\n\n🏠 <b>Main Menu:</b>"
    },
    'error_generic': {
        'fa': "⚠️ خطای موقتی پیش آمد. لطفاً دوباره تلاش کن:",
        'en': "⚠️ A temporary error occurred. Please try again:"
    },
    'send_resume_prompt': {
        'fa': "⚠️ لطفاً فایل رزومه (PDF یا Word) ارسال کن:",
        'en': "⚠️ Please upload your resume/CV file (PDF or Word):"
    },
    'receiving_resume': {
        'fa': "⏳ در حال دریافت فایل رزومه...",
        'en': "⏳ Receiving your resume..."
    },
    'save_error': {
        'fa': "⚠️ خطا در ذخیره. دوباره تلاش کن.",
        'en': "⚠️ Error saving data. Please try again."
    },
    'ask_degree': {
        'fa': "✅ رزومه دریافت شد\n\n🎓 مقطع مورد نظرت رو انتخاب کن:",
        'en': "✅ Resume received!\n\n🎓 Select your target degree:"
    },
    'ask_field': {
        'fa': "📚 رشته رو انتخاب کن:",
        'en': "📚 Select your field of study:"
    },
    'type_field': {
        'fa': "✍️ نام رشته رو تایپ کن:",
        'en': "✍️ Type your field of study:"
    },
    'ask_country': {
        'fa': "🌍 کشور هدفت رو انتخاب کن:",
        'en': "🌍 Select your target country:"
    },
    'type_country': {
        'fa': "✍️ نام کشور رو تایپ کن:",
        'en': "✍️ Type your target country:"
    },
    'ask_has_lang': {
        'fa': "🗣 مدرک زبان داری؟",
        'en': "🗣 Do you have a language certificate (IELTS/TOEFL)?"
    },
    'invalid_yes_no': {
        'fa': "⚠️ لطفاً یکی از گزینه‌های «✅ بله» یا «❌ خیر» را انتخاب کن:",
        'en': "⚠️ Please choose «✅ Yes» or «❌ No»:"
    },
    'ask_lang_type': {
        'fa': "🏅 نوع مدرک:",
        'en': "🏅 Select certificate type:"
    },
    'type_lang_name': {
        'fa': "✍️ نام مدرک:",
        'en': "✍️ Type the certificate name:"
    },
    'ask_lang_score': {
        'fa': "🔢 نمره زبانت رو وارد کن:",
        'en': "🔢 Enter your score:"
    },
    'no_cert_val': {'fa': "ندارد ❌", 'en': "None ❌"},
    'score_fmt': {'fa': "{type} (نمره: {score}) ✅", 'en': "{type} (Score: {score}) ✅"},
    'profile_done': {
        'fa': "🎉 <b>پروفایل با موفقیت تکمیل شد!</b>\n\n🎓 <b>مقطع:</b> {deg}\n📚 <b>رشته:</b> {field}\n🌍 <b>کشور هدف:</b> {country}\n🗣 <b>زبان:</b> {lang_score}",
        'en': "🎉 <b>Profile completed successfully!</b>\n\n🎓 <b>Degree:</b> {deg}\n📚 <b>Field:</b> {field}\n🌍 <b>Target Country:</b> {country}\n🗣 <b>Language:</b> {lang_score}"
    },
    'profile_incomplete': {
        'fa': "📭 هنوز پروفایلت کامل نشده است.\n\n📄 لطفاً فایل رزومه (PDF/Word) خودت رو بفرست:",
        'en': "📭 Your profile is incomplete.\n\n📄 Please upload your resume/CV (PDF/Word):"
    },
    'profile_view': {
        'fa': "👤 <b>پروفایل من</b>\n\n📄 <b>رزومه:</b> {resume}\n🎓 <b>مقطع:</b> {deg}\n📚 <b>رشته:</b> {field}\n🌍 <b>کشور هدف:</b> {country}\n🗣 <b>زبان:</b> {lang_score}",
        'en': "👤 <b>My Profile</b>\n\n📄 <b>Resume:</b> {resume}\n🎓 <b>Degree:</b> {deg}\n📚 <b>Field:</b> {field}\n🌍 <b>Target Country:</b> {country}\n🗣 <b>Language:</b> {lang_score}"
    },
    'btn_edit_profile': {'fa': "🔄 ویرایش پروفایل", 'en': "🔄 Edit Profile"},
    'btn_change_lang': {'fa': "🌐 تغییر زبان (English)", 'en': "🌐 Change Language (فارسی)"},
    'upload_new_resume': {
        'fa': "📄 فایل رزومه جدید رو بفرست:",
        'en': "📄 Upload your new resume/CV:"
    },
    'prompt_send_pos': {
        'fa': "📎 <b>لطفا پوزیشن تحصیلی مورد نظر خود را ارسال کنید:</b> 👇\n\n<b>فرمت های مورد تایید:</b>\n• متن کپی شده\n• عکس/اسکرین شات\n• لینک مستقیم\n• فوروارد از کانال تلگرام",
        'en': "📎 <b>Please send your target academic position:</b> 👇\n\n<b>Supported formats:</b>\n• Copied text\n• Image / Screenshot\n• Direct URL\n• Forwarded Telegram post"
    },
    'need_profile': {
        'fa': "⚠️ پروفایل کامل نیست. ابتدا روی «👤 پروفایل من» کلیک کن.",
        'en': "⚠️ Your profile is incomplete. Please click «👤 My Profile» first."
    },
    'saved_empty': {'fa': "📭 هنوز هیچ پوزیشنی ذخیره نکردی!", 'en': "📭 You haven't saved any positions yet!"},
    'applied_empty': {'fa': "📭 لیست اپلای شده‌ها خالیست!", 'en': "📭 Your applied positions list is empty!"},
    'applied_header': {'fa': "✅ <b>پوزیشن‌های اپلای شده:</b>\n\n", 'en': "✅ <b>Applied Positions:</b>\n\n"},
    'support_msg': {
        'fa': "💬 برای ارتباط با پشتیبانی و طرح سوالات، روی دکمه زیر کلیک کنید:",
        'en': "💬 Click the button below to contact support:"
    },
    'support_btn': {'fa': "💬 ارتباط با پشتیبانی", 'en': "💬 Contact Support"},
    'youtube_msg': {
        'fa': "▶️ برای مشاهده ویدیوهای آموزشی اپلای و بورسیه، وارد کانال یوتیوب شوید:",
        'en': "▶️ Visit Honi's Hub YouTube channel for academic application guides:"
    },
    'youtube_btn': {'fa': "▶️ ورود به کانال یوتیوب", 'en': "▶️ Open YouTube Channel"},
    'coming_soon': {'fa': "🚧 به‌زودی فعال می‌شود!", 'en': "🚧 Coming soon!"},
    'processing_one': {'fa': "⏳ در حال بررسی و تحلیل پوزیشن...", 'en': "⏳ Analyzing position..."},
    'processing_many': {'fa': "⏳ در حال بررسی و تحلیل {n} پیام ارسالی...", 'en': "⏳ Analyzing {n} messages..."},
    'general_url_err': {
        'fa': "⚠️ <b>این لینک مربوط به صفحه اصلی یا لیست کلی پوزیشن‌هاست!</b>\n\nلطفاً وارد صفحه خود پوزیشن مورد نظرت شو و <b>لینک مستقیم همان یک پوزیشن</b> را برایم بفرست تا دقیق تحلیلش کنم. 🎯",
        'en': "⚠️ <b>This looks like a homepage or general job board!</b>\n\nPlease open the specific position page and send me the <b>direct link to that single position</b> for an accurate analysis. 🎯"
    },
    'not_academic_err': {
        'fa': "⚠️ لطفاً پیام ارسالی را مجدداً بررسی کنید و فقط پوزیشن اپلای تحصیلی را ارسال کنید:",
        'en': "⚠️ Please double-check your message and send only valid academic positions (PhD/Master/Postdoc):"
    },
    'report_header': {'fa': "📊 <b>گزارش یکپارچه پوزیشن تحصیلی</b>", 'en': "📊 <b>Academic Position Analysis Report</b>"},
    'pos_num': {'fa': "📌 <b>پوزیشن #{id}</b>", 'en': "📌 <b>Position #{id}</b>"},
    'btn_apply': {'fa': "🚀 لینک اپلای پوزیشن", 'en': "🚀 Apply Link"},
    'btn_no_link': {'fa': "🚫 لینک در دسترس نیست", 'en': "🚫 Link Not Available"},
    'no_link_alert': {'fa': "🚫 لینک اپلای برای این پوزیشن در دسترس نیست.", 'en': "🚫 No application link available for this position."},
    'btn_applied': {'fa': "✅ اپلای کردم", 'en': "✅ Applied"},
    'btn_save': {'fa': "💾 ذخیرش کن", 'en': "💾 Save"},
    'btn_delete': {'fa': "🗑 حذف پوزیشن", 'en': "🗑 Delete"},
    'act_saved': {'fa': "✅ <b>پوزیشن ذخیره شد 💾</b>", 'en': "✅ <b>Position saved 💾</b>"},
    'act_applied': {'fa': "✅ <b>پوزیشن در لیست اپلای شده‌ها ثبت شد ✅</b>", 'en': "✅ <b>Marked as Applied ✅</b>"},
    'act_deleted': {'fa': "✅ <b>پوزیشن حذف شد 🗑</b>", 'en': "✅ <b>Position deleted 🗑</b>"},
}

def t(lang: str, key: str, **kwargs) -> str:
    val = TEXTS[key]
    text = val.get(lang, val['fa']) if isinstance(val, dict) else val
    return text.format(**kwargs) if kwargs else text