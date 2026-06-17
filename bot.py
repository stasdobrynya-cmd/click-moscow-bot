import os
import time
import json
import requests
import feedparser
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHANNEL = "@click_Moscow"
MY_ID = 5183537335

RUN_MODE = os.getenv("RUN_MODE", "news")
MAX_POSTS_PER_RUN = 5

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

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
    "бутово", "митино", "крылатское", "кунцево", "строгино",
    "химки", "балашиха", "мытищи", "люберцы", "красногорск", "реутов",
    "королев", "одинцово", "долгопрудный", "домодедово", "подольск",
    "щелково", "видное", "лобня", "сергиев посад", "электросталь"
]

SEEN_FILE = "seen_links.txt"
SEEN_TITLES_FILE = "seen_titles.txt"
PUBLISHED_FILE = "published_posts.jsonl"


def now_moscow():
    return datetime.now(MOSCOW_TZ)


def load_seen_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except FileNotFoundError:
        return set()


seen_links = load_seen_file(SEEN_FILE)
seen_titles = load_seen_file(SEEN_TITLES_FILE)


def send_message(chat_id, text):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=30
        )
        result = response.json()

        if result.get("ok"):
            print("Сообщение отправлено")
            return result

        print("Telegram ошибка:", result)

    except Exception as e:
        print("Ошибка отправки сообщения:", e)

    return None


def send_photo(chat_id, image_url, caption):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": image_url,
                "caption": caption
            },
            timeout=60
        )
        result = response.json()

        if result.get("ok"):
            print("Фото с постом отправлено")
            return result

        print("Telegram ошибка при фото:", result)

    except Exception as e:
        print("Ошибка отправки фото:", e)

    return None


def ask_groq(prompt, max_tokens=220, temperature=0.8):
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
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=40
        )

        print("Groq status:", response.status_code)
        data = response.json()

        if response.status_code != 200:
            print("Groq ошибка:", data)
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


def get_category(title):
    title_lower = title.lower()

    if any(word in title_lower for word in ["квартира", "жилье", "жильё", "пентхаус", "недвижимость", "новостройка", "дом", "застройщик", "район"]):
        return "🏢 Недвижимость", "#Недвижимость #Москва"

    if any(word in title_lower for word in ["метро", "мцд", "мцк", "дорог", "транспорт", "автобус", "поезд", "водител", "пробк", "такси"]):
        return "🚗 Транспорт", "#Дороги #Москва"

    if any(word in title_lower for word in ["дтп", "пожар", "полиция", "задерж", "происшеств", "авар", "нападен", "разбил"]):
        return "🚨 Происшествия", "#Происшествия #Москва"

    if any(word in title_lower for word in ["собянин", "мэр", "мэрия", "департамент"]):
        return "🏛 Власть", "#Москва #Власть"

    if any(word in title_lower for word in ["парк", "парки", "пляж", "пляжи", "зона отдыха", "отдых", "купание", "вднх", "сокольники", "зарядье", "горького", "коломенское", "царицыно"]):
        return "🌳 Городская жизнь", "#Отдых #Москва"

    if any(word in title_lower for word in ["фестиваль", "концерт", "выставка", "театр", "музей", "артист", "звезд", "шоу", "кино", "певец", "певица"]):
        return "🎭 Афиша и звёзды", "#Афиша #Москва"

    if any(word in title_lower for word in ["открыли", "открылся", "строительство", "реконструкция", "запустили"]):
        return "🏗 Город", "#Город #Москва"

    if any(word in title_lower for word in ["бизнес", "инвестиции", "экономика", "ипотек", "банк", "деньги", "кредит", "цены"]):
        return "💸 Деньги", "#Деньги #Москва"

    if any(word in title_lower for word in ["погода", "ливень", "жара", "снег", "мороз", "дожд", "туман"]):
        return "🌦 Погода", "#Погода #Москва"

    if any(word in title_lower for word in ["врач", "здоров", "шоколад", "еда", "ресторан", "отношен", "женщин", "мужчин", "психолог"]):
        return "⭐ Лайфстайл", "#Лайфстайл #Москва"

    return "🏙 Москва и область", "#Москва #МосковскаяОбласть"


def get_news_batch(limit=5):
    news_list = []

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

            news_list.append({
                "title": title_original,
                "summary": summary_original,
                "link": link
            })

            if len(news_list) >= limit:
                return news_list

    return news_list


def generate_ai_title(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Ты редактор живого городского Telegram-паблика Click Moscow.

Создай короткий заголовок в стиле городского паблика.

Стиль:
- живой
- цепляющий
- не официальный
- можно один эмодзи в начале или конце
- без жёлтого кликбейта
- до 11 слов
- без кавычек
- без точки в конце

Примеры стиля:
📈 Число школьников с проблемами волос выросло в 4 раза
🚨 В Подмосковье разбился лёгкомоторный самолёт
💸 Москвичи стали реже брать ипотеку
🍷 Алкоголь могут запретить продавать до 21 года
💔 Москвички не хотят встречаться с мужчинами младше себя

Категория: {category}
Оригинальный заголовок: {title}
Новость: {base_text}

Ответь только заголовком.
"""

    ai_title = ask_groq(prompt, max_tokens=80, temperature=0.9)

    if not ai_title:
        return f"🔥 {title}"

    return ai_title.replace('"', "").replace("«", "").replace("»", "").strip()


def rewrite_with_ai(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Ты автор Telegram-паблика Click Moscow.

Напиши новость в живом стиле городского канала.

Правила:
- не официальный стиль СМИ
- не придумывай факты
- используй только информацию из новости ниже
- 2-3 коротких абзаца
- простой русский язык
- можно 1-2 эмодзи по смыслу
- без ссылок
- без хэштегов
- без заголовка
- не больше 650 символов

Стиль примеров:
"В Подмосковье произошёл инцидент с лёгкомоторным самолётом. Сейчас уточняется, есть ли пострадавшие. 🚨"

"Эксперты связывают рост проблемы с образом жизни и стрессом. Врачи советуют не игнорировать первые симптомы. 😟"

Категория: {category}

Новость:
{base_text}
"""

    text = ask_groq(prompt, max_tokens=240, temperature=0.85)

    if not text:
        return base_text

    return text


def generate_image_prompt(title, summary, category):
    base_text = summary.strip() if summary.strip() else title

    prompt = f"""
Create an English image prompt for an AI image generator.

Goal:
Make a vivid image for a Moscow Telegram city channel.

Style:
- viral social media news image
- emotional but realistic
- Moscow atmosphere
- bright, memorable, attention-grabbing
- realistic or meme-like if suitable
- no text
- no logos
- no watermark
- no distorted faces
- one short paragraph

Category: {category}
News title: {title}
News text: {base_text}
"""

    image_prompt = ask_groq(prompt, max_tokens=120, temperature=0.9)

    if not image_prompt:
        image_prompt = f"Viral Moscow city news image, {category}, {title}, realistic social media style, no text, no logos"

    return image_prompt


def generate_image_url(title, summary, category):
    image_prompt = generate_image_prompt(title, summary, category)
    encoded_prompt = quote(image_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"


def create_post(title, summary):
    category, hashtags = get_category(title)

    ai_title = generate_ai_title(title, summary, category)
    body = rewrite_with_ai(title, summary, category)

    if len(body) > 700:
        body = body[:700].strip() + "..."

    post = (
        f"{ai_title}\n\n"
        f"{body}\n\n"
        f"{hashtags} #ClickMoscow"
    )

    return post, category, ai_title


def save_published(title, ai_title, summary, category):
    record = {
        "date": now_moscow().strftime("%Y-%m-%d"),
        "time": now_moscow().strftime("%H:%M"),
        "title": title,
        "ai_title": ai_title,
        "summary": summary,
        "category": category
    }

    with open(PUBLISHED_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def publish_news_batch():
    news_list = get_news_batch(MAX_POSTS_PER_RUN)

    if not news_list:
        send_message(MY_ID, "Не смог найти новые подходящие новости.")
        return

    published_count = 0

    for item in news_list:
        title = item["title"]
        summary = item["summary"]

        created = create_post(title, summary)

        if not created:
            continue

        post, category, ai_title = created
        image_url = generate_image_url(title, summary, category)

        result = send_photo(CHANNEL, image_url, post)

        if not result:
            send_message(CHANNEL, post)

        save_published(title, ai_title, summary, category)
        published_count += 1

        time.sleep(5)

    send_message(MY_ID, f"✅ Опубликовано новостей: {published_count}")


def load_today_posts():
    today = now_moscow().strftime("%Y-%m-%d")
    posts = []

    try:
        with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if record.get("date") == today:
                        posts.append(record)
                except Exception:
                    continue
    except FileNotFoundError:
        return []

    return posts


def send_morning_digest():
    posts = load_today_posts()

    if not posts:
        send_message(MY_ID, "Для дайджеста пока нет опубликованных новостей.")
        return

    items = posts[-10:]

    raw_text = "\n".join(
        f"{i + 1}. {item.get('ai_title') or item.get('title')}"
        for i, item in enumerate(items)
    )

    prompt = f"""
Ты автор Telegram-паблика Click Moscow.

Сделай живой утренний дайджест.

Стиль:
- городской паблик
- легко читается
- не сухое СМИ
- 5-7 пунктов
- можно эмодзи
- без ссылок
- без хэштегов
- не придумывай факты

Новости:
{raw_text}
"""

    digest_text = ask_groq(prompt, max_tokens=450, temperature=0.85)

    if not digest_text:
        digest_text = raw_text

    post = (
        f"☀️ Что происходит в Москве к утру\n\n"
        f"{digest_text}\n\n"
        f"#Москва #Дайджест #ClickMoscow"
    )

    image_url = generate_image_url("Утренний дайджест Москвы", digest_text, "☀️ Дайджест")

    result = send_photo(CHANNEL, image_url, post)

    if not result:
        send_message(CHANNEL, post)

    send_message(MY_ID, "✅ Утренний дайджест опубликован.")


if RUN_MODE == "digest":
    send_morning_digest()
else:
    publish_news_batch()
