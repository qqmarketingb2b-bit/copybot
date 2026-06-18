import os

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_CODE       = os.environ.get("ADMIN_CODE", "ADMIN_SECRET_2024")

CLAUDE_MODEL     = "claude-opus-4-20250514"
MAX_TOKENS       = 15000
MAX_FILE_SIZE_MB = 10
MAX_ACTIVE_TASKS = 0   # 0 = без ограничений

ROLE_ADMIN    = "admin"
ROLE_SUBADMIN = "subadmin"
ROLE_EMPLOYEE = "employee"

ROLE_LABELS = {
    ROLE_ADMIN:    "Администратор",
    ROLE_SUBADMIN: "Суб-Админ",
    ROLE_EMPLOYEE: "Сотрудник",
}
ADMIN_ROLES = {ROLE_ADMIN, ROLE_SUBADMIN}

# ── Языки перевода ───────────────────────────────────────────────────
# code: (флаг/эмодзи, название на русском, инструкция по локализации тона)
LANGUAGES = {
    "uk": ("🇺🇦", "Украинский",
        "Переведи на украинский язык так, как реально общаются носители — естественная разговорная лексика, "
        "актуальные обороты, без буквальных калек с русского. Если контекст digital/gaming — используй принятые "
        "в украинской интернет-среде термины и заимствования, где это естественно."),
    "ru": ("🇷🇺", "Русский",
        "Переведи на русский язык, сохраняя естественный современный стиль письма, как пишут носители "
        "в деловой и интернет-среде. Избегай канцеляризмов и буквального переноса конструкций из оригинала."),
    "en": ("🇬🇧", "Английский",
        "Translate into natural, fluent English as written by native speakers in business and digital media. "
        "Avoid literal translation artifacts — rewrite idioms and structure so it reads as originally written in English."),
    "pt-br": ("🇧🇷", "Португальский (Бразилия)",
        "Traduza para português brasileiro coloquial e natural, como escrevem nativos brasileiros em conteúdo digital. "
        "Use expressões e tom típicos do Brasil, evite construções que pareçam tradução literal ou português europeu."),
    "es-latam": ("🌎", "Испанский (LatAm)",
        "Traduce al español latinoamericano neutro, con el tono y las expresiones que usan los hispanohablantes "
        "de Latinoamérica en contenido digital. Evita modismos exclusivos de España; prioriza un tono cercano y natural."),
    "fr-af": ("🌍", "Французский (Африка)",
        "Traduis en français tel qu'il est couramment écrit et compris en Afrique francophone, avec un ton naturel "
        "et accessible pour ce public, en évitant les tournures trop métropolitaines ou littéraires."),
    "tr": ("🇹🇷", "Турецкий",
        "Metni doğal ve akıcı bir Türkçeyle çevir; dijital içerik okuyan Türk hedef kitlenin günlük kullandığı "
        "ton ve ifadeleri kullan, kelimesi kelimesine çeviri hissi vermesin."),
    "hi": ("🇮🇳", "Хинди (Индия)",
        "इस टेक्स्ट का अनुवाद स्वाभाविक, आधुनिक हिंदी में करें जैसा भारतीय पाठक डिजिटल कंटेंट में पढ़ने के आदी हैं। "
        "शब्द-दर-शब्द अनुवाद जैसा महसूस न हो, टोन सहज और बोलचाल का रखें।"),
}

(
    ST_WAIT_CODE,
    ST_MAIN_MENU,

    ST_WAIT_PROJECT,
    ST_WAIT_FORMAT,
    ST_WAIT_TZ,
    ST_CHATTING,

    ST_TASKS_MENU,

    ST_WAIT_TRANSLATE_LANG,
    ST_WAIT_SEO_CHOICE,

    ST_ADMIN_MENU,

    ST_ADD_USER_WAIT_USERNAME,
    ST_ADD_USER_WAIT_ROLE,

    ST_ADD_PROJECT_NAME,
    ST_ADD_PROJECT_TOV,
    ST_ADD_PROJECT_FORMATS,
    ST_ADD_PROJECT_EXAMPLES,

    ST_EDIT_PROJECT_MENU,
    ST_EDIT_PROJECT_TOV,
    ST_EDIT_PROJECT_FORMAT_MENU,
    ST_EDIT_PROJECT_EXAMPLES,

    ST_ADD_FORMAT_NAME,
    ST_ADD_FORMAT_EMOJI,
    ST_ADD_FORMAT_INSTRUCTION,
) = range(23)
