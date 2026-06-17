import os
import time
import requests
import feedparser
from urllib.parse import quote

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ТОЛЬКО_ЕСЛИ_ЗАПУСКАЕШЬ_НЕ_В_GITHUB")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHANNEL = "@click_Moscow"
MY_ID = 5183537335

SOURCES = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/moscow/index.xml",
    "https://www.m24.ru/rss.xml",
]

LOCAL_KEYWORDS = [
    "москва", "москве", "москвы", "москов", "столице", "столичный",
    "подмосков", "московская область",
    "мкад", "ттк", "садовое кольцо", "мцд", "мцк", "метро",
    "вднх", "сокольники", "зарядье", "парк горького", "коломенское", "царицыно",
    "цао", "свао", "вао", "ювао", "юао", "юзао", "зао", "сзао", "сао",
    "арбат", "тверской", "хамовники", "пресня", "замоскворечье", "марьино",
    "бутово", "митине", "митино", "крылатское", "кунцево", "строгино",
    "химки", "балашиха", "мытищи", "люберцы", "красногорск", "реутов",
    "королев", "одинцово", "долгопрудный", "домодедово", "подольск",
    "щелково", "видное", "лобня", "сергиев посад", "электросталь"
]

SEEN_FILE = "seen_links.txt"
SEEN_TITLES_FILE = "seen_titles.txt"


def load_seen_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except FileNotFoundError:
        return set()


seen_links = load_seen_file(SEEN_FILE)
seen_titles = load_seen_file(SEEN_TITLES_FILE)


def send_message(chat_id, text):
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=data,
            timeout=30
        )
        result = response.json()

        if result.get("ok"):
            print("Сообщение отправлено")
            return result

        print("Telegram ответил ошибкой:", result)

    except Exception as e:
        print("Ошибка отправки сообщения:", e)

    return None


def send_photo(chat_id, image_url, caption):
    data = {
        "chat_id": chat_id,
        "photo": image_url,
        "caption": caption
    }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json=data,
            timeout=60
        )
        result = response.json()

        if result.get("ok"):
            print("Фото с постом отправлено")
            return result

        print("Telegram ответил ошибкой при отправке фото:", result)

    except Exception as e:
        print("Ошибка отправки фото:", e)

    return None


def ask_groq(prompt, max_tokens=180, temperature=0.7):
    if not GROQ_API_KEY:
        print("Groq API key не найден")
        return None

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=40
        )

        print("Groq status:", response.status_code)
        data = response.json()

        if response.status_code != 200:
            print("Groq ответил ошибкой:", data)
            return None

        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print("Ошибка Groq:", e)
        return None


def normalize_title(title):
    text = title.lower()

    for symbol in [".", ",", ":", ";", "!", "?", "«", "»", '"', "'", "-", "—", "(", ")"]:
        text = text.replace(symbol, " ")

    stop_words = [
        "в", "на", "о", "об", "и", "а", "по", "для", "из", "с", "со", "у",
        "к", "от", "до", "за", "над", "под", "при", "про", "это", "как",
        "назвали", "названа", "назван", "рассказали", "сообщили"
    ]

    return set(word for word in text.split() if len(word) > 3 and word not in stop_words)


def is_duplicate_title(new_title):
    new_words = normalize_title(new_title)

    for old_title in seen_titles:
        old_words = normalize_title(old_title)

        if not new_words or not old_words:
            continue

        common_words = new_words.intersection(old_words)
        similarity = len(common_words) / max(len(new_words), len(old_words))

        if similarity >= 0.5:
            return True

    return False


def get_latest_news():
    for source in SOURCES:
        print("Проверяю источник:", source)

        feed = feedparser.parse(source)
        print("Источник:", source, "новостей найдено:", len(feed.entries))

        for entry in feed.entries:
            title_original = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary_original = getattr(entry, "summary", "")

            if not title_original or not link:
                continue

            title = title_original.lower()
            summary = summary_original.lower()
            text_for_check = title + " " + summary

            print("Проверяю новость:", title)

            if not any(word in text_for_check for word in LOCAL_KEYWORDS):
                print("Пропущено:", title)
                continue

            if link in seen_links:
                print("Пропущено как уже опубликованная ссылка:", title)
                continue

            if is_duplicate_title(title_original):
                print("Пропущено как дубль по смыслу:", title)
                continue

            print("Найдена подходящая новость:", title)

            seen_links.add(link)
            seen_titles.add(title_original)

            with open(SEEN_FILE, "a", encoding="utf-8") as f:
                f.write(link + "\n")

            with open(SEEN_TITLES_FILE, "a", encoding="utf-8") as f:
                f.write(title_original + "\n")

            return title_original, summary_original

    return None


def get_category(title):
    title_lower = title.lower()

    if any(word in title_lower for word in ["квартира", "жилье", "жильё", "пентхаус", "недвижимость", "новостройка", "дом", "застройщик"]):
        return "🏢 Недвижимость", "#Москва #Недвижимость"

    if any(word in title_lower for word in ["метро", "мцд", "мцк", "дорог", "транспорт", "автобус", "поезд", "водител"]):
        return "🚇 Транспорт", "#Москва #Транспорт"

    if any(word in title_lower for word in ["дтп", "пожар", "полиция", "задерж", "происшеств", "авар", "нападен"]):
        return "🚨 Происшествия", "#Москва #Происшествия"

    if any(word in title_lower for word in ["собянин", "мэр", "мэрия"]):
        return "🏛 Городская власть", "#Москва #Мэрия"

    if any(word in title_lower for word in ["парк", "парки", "пляж", "пляжи", "зона отдыха", "отдых", "купание", "вднх", "сокольники", "зарядье", "горького", "коломенское", "царицыно"]):
        return "🌳 Парки и отдых", "#Москва #Отдых"

    if any(word in title_lower for word in ["фестиваль", "концерт", "выставка", "театр", "музей", "звезд", "артист"]):
        return "🎭 Афиша и городская жизнь", "#Москва #Афиша"

    if any(word in title_lower for word in ["открыли", "открылся", "строительство", "реконструкция"]):
        return "🏗 Город", "#Москва #Город"

    if any(word in title_lower for word in ["бизнес", "инвестиции", "экономика", "ипотек"]):
        return "💼 Бизнес и деньги", "#Москва #Бизнес"

    if any(word in title_lower for word in ["погода", "ливень", "жара", "снег", "мороз"]):
        return "🌤 Погода", "#Москва #Погода"

    return "🏙 Москва и область", "#Москва #МосковскаяОбласть"


def generate_ai_title(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Ты редактор городского Telegram-канала Click Moscow.

Создай короткий цепляющий заголовок.

Правила:
- до 12 слов
- без кликбейта
- по существу
- только русский язык
- без кавычек
- без точки в конце
- можно использовать один эмодзи в начале

Категория: {category}
Оригинальный заголовок: {title}
Текст новости: {base_text}

Ответь только заголовком.
"""

    ai_title = ask_groq(prompt, max_tokens=80, temperature=0.8)

    if not ai_title:
        return f"🔥 {title}"

    return ai_title.replace('"', "").replace("«", "").replace("»", "").strip()


def rewrite_with_ai(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Перепиши новость для Telegram-канала Click Moscow.

Правила:
- не придумывай факты
- используй только информацию из текста ниже
- максимум 2 предложения
- простой русский язык
- без ссылок
- без хэштегов
- без заголовков
- 40-80 слов

Категория: {category}
Новость:
{base_text}
"""

    text = ask_groq(prompt, max_tokens=180, temperature=0.7)

    if not text:
        return base_text

    return text


def generate_image_prompt(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Create an English image prompt for an AI image generator.

Rules:
- realistic photojournalism
- Moscow atmosphere
- modern editorial news style
- no text
- no logos
- no flags unless directly needed
- one short paragraph
- do not mention Telegram

Category: {category}
News title: {title}
News text: {base_text}
"""

    image_prompt = ask_groq(prompt, max_tokens=120, temperature=0.8)

    if not image_prompt:
        image_prompt = f"Realistic Moscow city news photo, {category}, {title}, modern editorial style, no text, no logos"

    return image_prompt


def generate_image_url(title, summary, category):
    image_prompt = generate_image_prompt(title, summary, category)
    encoded_prompt = quote(image_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"


def create_post(title, summary):
    category, hashtags = get_category(title)

    ai_title = generate_ai_title(title, summary, category)
    clean_summary = rewrite_with_ai(title, summary, category)

    if len(clean_summary) > 350:
        clean_summary = clean_summary[:350].strip() + "..."

    post = (
        f"{category}\n"
        f"{'━' * 20}\n\n"
        f"{ai_title}\n\n"
        f"📝 Кратко:\n"
        f"{clean_summary}\n\n"
        f"{hashtags} #ClickMoscow\n\n"
        f"🔔 Подписывайтесь на Click Moscow"
    )

    return post, category


def send_news_for_approval():
    result = get_latest_news()

    if not result:
        send_message(MY_ID, "Не смог найти новости в источниках.")
        return

    title, summary = result

    created = create_post(title, summary)

    if not created:
        send_message(MY_ID, "Новость не подходит под московские категории.")
        return

    post, category = created

    image_url = generate_image_url(title, summary, category)

    result = send_photo(CHANNEL, image_url, post)

    if not result:
        send_message(CHANNEL, post)

    send_message(MY_ID, "✅ Новость опубликована в канал.")


send_news_for_approval()
