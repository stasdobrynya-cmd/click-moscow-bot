import os
import time
import requests
import feedparser

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


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False
    }

    if keyboard:
        data["reply_markup"] = keyboard

    for attempt in range(3):
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
            print("Ошибка отправки, попытка", attempt + 1, e)

        time.sleep(5)

    print("Не удалось отправить сообщение")
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

    words = [word for word in text.split() if len(word) > 3 and word not in stop_words]
    return set(words)


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

            return title_original, link, summary_original

    return None

def rewrite_with_ai(title, summary, category):
    if not OPENROUTER_API_KEY:
        print("OpenRouter API key не найден")
        return summary.strip() if summary.strip() else "Подробности можно открыть по кнопке ниже."

    prompt = f"""
Перепиши новость для Telegram-канала Click Moscow.

Стиль:
- коротко
- по-человечески
- без воды
- 2 предложения
- только по-русски
- без ссылок
- без хэштегов
- без заголовка

Категория: {category}
Заголовок: {title}
Описание: {summary}
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/stasdobrynya-cmd/click-moscow-bot",
                "X-Title": "Click Moscow Bot"
            },
            json={
                "model": "openrouter/auto",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 180,
                "temperature": 0.7
            },
            timeout=40
        )

        print("OpenRouter status:", response.status_code)

        data = response.json()

        if response.status_code != 200:
            print("OpenRouter ответил ошибкой:", data)
            return summary.strip() if summary.strip() else "Подробности можно открыть по кнопке ниже."

        text = data["choices"][0]["message"]["content"].strip()

        if not text:
            return summary.strip() if summary.strip() else "Подробности можно открыть по кнопке ниже."

        return text

    except Exception as e:
        print("Ошибка ИИ-рерайта:", e)
        return summary.strip() if summary.strip() else "Подробности можно открыть по кнопке ниже."

def rewrite_news(title, link, summary):
    title_lower = title.lower()

    if any(word in title_lower for word in ["квартира", "жилье", "жильё", "пентхаус", "недвижимость", "новостройка", "дом", "застройщик"]):
        category = "🏢 Недвижимость"
        hashtags = "#Москва #Недвижимость"

    elif any(word in title_lower for word in ["метро", "мцд", "мцк", "дорог", "транспорт", "автобус", "поезд"]):
        category = "🚇 Транспорт"
        hashtags = "#Москва #Транспорт"

    elif any(word in title_lower for word in ["дтп", "пожар", "полиция", "задерж", "происшеств", "авар", "нападен"]):
        category = "🚨 Происшествия"
        hashtags = "#Москва #Происшествия"

    elif any(word in title_lower for word in ["собянин", "мэр", "мэрия"]):
        category = "🏛 Городская власть"
        hashtags = "#Москва #Мэрия"

    elif any(word in title_lower for word in ["парк", "парки", "пляж", "пляжи", "зона отдыха", "отдых", "купание", "вднх", "сокольники", "зарядье", "горького", "коломенское", "царицыно"]):
        category = "🌳 Парки и отдых"
        hashtags = "#Москва #Отдых"

    elif any(word in title_lower for word in ["фестиваль", "концерт", "выставка", "театр", "музей"]):
        category = "🎭 Афиша"
        hashtags = "#Москва #Афиша"

    elif any(word in title_lower for word in ["открыли", "открылся", "строительство", "реконструкция"]):
        category = "🏗 Город"
        hashtags = "#Москва #Город"

    elif any(word in title_lower for word in ["бизнес", "инвестиции", "экономика"]):
        category = "💼 Бизнес"
        hashtags = "#Москва #Бизнес"

    elif any(word in title_lower for word in ["погода", "ливень", "жара", "снег", "мороз"]):
        category = "🌤 Погода"
        hashtags = "#Москва #Погода"

    else:
        if not any(word in title_lower for word in ["москва", "москве", "москвы", "москов", "подмосков", "московская область"]):
            return None

        category = "🏙 Москва и область"
        hashtags = "#Москва #МосковскаяОбласть"

    clean_summary = rewrite_with_ai(title, summary, category)

    if not clean_summary:
        clean_summary = "Подробности можно открыть по кнопке ниже."

    if len(clean_summary) > 350:
        clean_summary = clean_summary[:350].strip() + "..."

    return (
        f"{category}\n"
        f"{'━' * 20}\n\n"
        f"🔥 {title.upper()}\n\n"
        f"📝 Кратко:\n"
        f"{clean_summary}\n\n"
        f"{hashtags} #ClickMoscow\n\n"
        f"🔔 Подписывайтесь на Click Moscow"
    )


def send_news_for_approval():
    result = get_latest_news()

    if not result:
        send_message(MY_ID, "Не смог найти новости в источниках.")
        return

    title, link, summary = result

    post = rewrite_news(title, link, summary)

    if not post:
        send_message(MY_ID, "Новость не подходит под московские категории.")
        return

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "📖 Читать подробнее",
                    "url": link
                }
            ]
        ]
    }

    send_message(CHANNEL, post, keyboard)
    send_message(MY_ID, "✅ Новость опубликована в канал.")


send_news_for_approval()
