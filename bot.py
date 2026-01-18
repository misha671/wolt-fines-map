from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import json
from datetime import datetime, timedelta
import os
import requests
from base64 import b64encode

BOT_TOKEN = "8594027179:AAHDMDX_uplAlZY14tC9WmULqq8i4rERtbM"
CHANNEL_USERNAME = "@woltwarn"
CHANNEL_ID = -1003410531789
TARGET_THREAD_ID = 2
WEBAPP_URL = "https://misha671.github.io/wolt-fines-map/"

GITHUB_TOKEN = "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"
GITHUB_USERNAME = "misha671"
GITHUB_REPO = "wolt-fines-map"
GITHUB_FILE = "locations.json"

async def save_data_to_file(context: ContextTypes.DEFAULT_TYPE):
      try:
                locations = context.bot_data.get('locations', [])

        data = {
                      'locations': locations,
                      'updated_at': datetime.now().isoformat(),
                      'total_count': len(locations)
        }

        with open('locations.json', 'w', encoding='utf-8') as f:
                      json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ Локальный файл: locations.json ({len(locations)} точек)")

        if GITHUB_TOKEN != "ВСТАВЬТЕ_ВАШ_GITHUB_ТОКЕН":
                      success = upload_to_github(data)
                      if success:
                                        print(f"✅ GitHub обновлён!")
        else:
                print(f"⚠️ GitHub не обновлён")
        else:
            print(f"⚠️ GitHub токен не настроен")

                  return True

except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def upload_to_github(data):
      try:
                url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"

        headers = {
                      "Authorization": f"token {GITHUB_TOKEN}",
                      "Accept": "application/vnd.github.v3+json"
        }

        try:
                      response = requests.get(url, headers=headers)
                      sha = response.json()["sha"] if response.status_code == 200 else None
                  except:
            sha = None

        content = json.dumps(data, ensure_ascii=False, indent=2)
        content_encoded = b64encode(content.encode()).decode()

        payload = {
                      "message": f"🤖 Auto-update: {datetime.now().strftime('%H:%M:%S')}",
                      "content": content_encoded,
        }

        if sha:
                      payload["sha"] = sha

        response = requests.put(url, headers=headers, json=payload)
        return response.status_code in [200, 201]

except Exception as e:
        print(f"❌ GitHub ошибка: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
      keyboard = [
                [InlineKeyboardButton("🗺 Открыть карту штрафов", web_app=WebAppInfo(url=WEBAPP_URL))]
      ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
              "👋 Привет! Нажми кнопку ниже, чтобы открыть карту штрафов за последние 4 часа.",
              reply_markup=reply_markup
    )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
      post = update.channel_post or update.message

    if not post or not post.location:
              return

    chat = post.chat
    message_thread_id = post.message_thread_id

    print(f"\n{'='*60}")
    print(f"📍 Получена геолокация!")

    if chat.username != "woltwarn":
              print(f"⚠️ Пропускаем")
              print(f"{'='*60}\n")
              return

    if message_thread_id != TARGET_THREAD_ID:
              print(f"⚠️ Другой топик")
              print(f"{'='*60}\n")
              return

    user_name = post.from_user.first_name if post.from_user else "Канал"

    location_data = {
              'latitude': post.location.latitude,
              'longitude': post.location.longitude,
              'timestamp': datetime.now().isoformat(),
              'user': user_name,
              'message_id': post.message_id
    }

    print(f"✅ Координаты: {location_data['latitude']}, {location_data['longitude']}")
    print(f"   Пользователь: {user_name}")

    if 'locations' not in context.bot_data:
              context.bot_data['locations'] = []

    if not any(loc.get('message_id') == location_data['message_id'] for loc in context.bot_data['locations']):
              context.bot_data['locations'].append(location_data)

        if len(context.bot_data['locations']) > 200:
                      context.bot_data['locations'] = context.bot_data['locations'][-200:]

        print(f"📊 Всего: {len(context.bot_data['locations'])} точек")

        await save_data_to_file(context)

    print(f"{'='*60}\n")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
      locations = context.bot_data.get('locations', [])

    now = datetime.now()
    four_hours_ago = now - timedelta(hours=4)

    recent = [loc for loc in locations if datetime.fromisoformat(loc['timestamp']) > four_hours_ago]

    message = (
              f"📊 Статистика:\n\n"
              f"Канал: @woltwarn\n"
              f"Топик: Штрафы (ID: {TARGET_THREAD_ID})\n\n"
              f"Всего точек: {len(locations)}\n"
              f"За 4 часа: {len(recent)}\n"
              f"GitHub: {'✅ Работает' if GITHUB_TOKEN != 'ВСТАВЬТЕ_ВАШ_GITHUB_ТОКЕН' else '❌ Не настроен'}"
    )

    await update.message.reply_text(message)

def main():
      print("="*60)
    print("🤖 Wolt Fines Bot")
    print("="*60)
    print(f"Канал: {CHANNEL_USERNAME}")
    print(f"Топик: {TARGET_THREAD_ID}")
    print(f"Mini App: {WEBAPP_URL}")
    print(f"GitHub: {GITHUB_USERNAME}/{GITHUB_REPO}")
    print(f"GitHub Token: {'✅ Настроен' if GITHUB_TOKEN != 'ВСТАВЬТЕ_ВАШ_GITHUB_ТОКЕН' else '❌ НЕ НАСТРОЕН'}")
    print("="*60)
    print("\n✅ Бот запущен!")
    print("💡 Каждая новая геолокация автоматически загружается на GitHub\n")

    from telegram.ext import PicklePersistence

    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))

    try:
              application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
except Exception as e:
        print(f"\n❌ Ошибка: {e}")

if __name__ == '__main__':
      main()
