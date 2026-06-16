import time
import requests
import feedparser

BOT_TOKEN = "8202418690:AAFAxas3OpdWT7_LbZhOTSdNxcUJc-L-8c4"
OPENAI_API_KEY = "ПОКА_МОЖНО_ОСТАВИТЬ_ПУСТЫМ"

CHANNEL = "@click_Moscow"
MY_ID = 5183537335

SOURCES = [
    "https://lenta.ru/rss/news",
    "https://ria.ru/export/rss2/moscow/index.xml",
    "https://www.m24.ru/rss.xml",
]

MOSCOW_KEYWORDS = [
    "мэрия",
    "мосгордума",
    "департамент транспорта",
    "московское метро",
    "аэропорт шереметьево",
    "внуково",
    "домодедово",
    "замоскворечье",
    "тверской",
    "арбат""москва",
    "москве",
    "москвы",
    "московский",
    "московская",
    "московской",
    "московскую",
    "московские",
    "московских",
    "подмосковье",
    "подмосковья",
    "подмосковный",
    "химки",
    "балашиха",
    "мытищи",
    "люберцы",
    "красногорск",
    "реутов",
    "королев",
    "одинцово",
    "долгопрудный",
    "домодедово",
    "подольск",
    "щелково",
    "видное",
    "лобня",
    "сергиев посад",
    "электросталь",
    "мцд",
    "мцк",
    "метро",
    "собянин",
    "росси"
]
last_update_id = 0
pending_post = None
SEEN_FILE = "seen_links.txt"

try:
    with open(SEEN_FILE, "r") as f:
        seen_links = set(line.strip() for line in f.readlines())
except FileNotFoundError:
    seen_links = set()

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

        time.sleep(30)

    print("Не удалось отправить сообщение после 5 попыток")
    return None

def get_latest_news():
    for source in SOURCES:
        print("Проверяю источник:", source)

        feed = feedparser.parse(source)

        print("Источник:", source, "новостей найдено:", len(feed.entries))

        for entry in feed.entries:
            title = entry.title
            link = entry.link
            summary = getattr(entry, "summary", "")

            title = title.lower()
            summary = summary.lower()
            text_for_check = title + " " + summary

            print("Проверяю новость:", title)

            if not any(word in text_for_check for word in MOSCOW_KEYWORDS):
                print("Пропущено:", title)
                continue

            if link not in seen_links:
                print("Найдена подходящая новость:", title)

                seen_links.add(link)

                with open(SEEN_FILE, "a") as f:
                    f.write(link + "\n")

                return title, link

    return None, None


def rewrite_news(title, link):
    title_lower = title.lower()

    if any(word in title_lower for word in ["метро", "мцд", "мцк", "дорог", "транспорт", "автобус", "поезд"]):
        category = "🚇 Транспорт"
        hashtags = "#Москва #Транспорт"
    elif any(word in title_lower for word in ["дтп", "пожар", "полиция", "задерж", "происшеств", "авар", "нападен"]):
        category = "🚔 Происшествия"
        hashtags = "#Москва #Происшествия"
    elif any(word in title_lower for word in ["собянин", "мэр", "мэрия"]):
        category = "🏛️ Городская власть"
        hashtags = "#Москва #Мэрия"
    elif any(word in title_lower for word in ["парк", "парки", "пляж", "пляжи","зона отдыха", "отдых", "купание","вднх", "сокольник","зарядье", "горького","коломенское", "царицыно"]):
        category = "🌳 Парки и отдых"
        hashtags = "#Москва #Отдых"
    else:
        return None

    return (
        f"{category}\n\n"
        f"🚨 {title}\n\n"
        f"👉 Подробности по ссылке ниже.\n\n"
        f"🔗 {link}\n\n"
        f"{hashtags} #ClickMoscow"
    )

def send_news_for_approval():
    global pending_post

    title, link = get_latest_news()

    if not title:
        send_message(MY_ID, "Не смог найти новости в источниках.")
        return

    post = rewrite_news(title, link)

    if not post:
        send_message(MY_ID, "Новость не подходит под московские категории.")
        return

    pending_post = post

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Опубликовать", "callback_data": "publish"},
                {"text": "❌ Пропустить", "callback_data": "skip"}
            ]
        ]
    }

    send_message(
        MY_ID,
        f"{post}\n\nОпубликовать в канал?",
        keyboard
    )


def check_buttons():
    global last_update_id, pending_post

    try:
        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 5}
        ).json()
    except Exception as e:
        print("Ошибка Telegram, пробую позже:", e)
        time.sleep(30)
        return

    for update in response.get("result", []):
        last_update_id = update["update_id"]

        if "callback_query" not in update:
            continue

        callback = update["callback_query"]
        data = callback["data"]
        callback_id = callback["id"]

        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback_id}
            )
        except Exception as e:
            print("Не смог ответить на кнопку:", e)

        if data == "publish":
            if pending_post:
                result = send_message(CHANNEL, pending_post)

                if result and result.get("ok"):
                 send_message(MY_ID, "✅ Опубликовано в канал.")
                 pending_post = None
                else:
                    send_message(MY_ID, "⚠️ Не удалось опубликовать в канал. Попробуй нажать кнопку ещё раз.")
            else:
                send_message(MY_ID, "Нет новости для публикации.")

        elif data == "skip":
            pending_post = None
            send_message(MY_ID, "❌ Новость пропущена.")
#send_message(MY_ID, "🤖 Бот запущен. Буду проверять новости каждые 15 минут.")

# Одноразовый запуск для GitHub Actions
send_news_for_approval()




