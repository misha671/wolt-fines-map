import os
import json
import threading
import requests
from flask import Flask
from datetime import datetime, timedelta
from base64 import b64encode
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes, CallbackQueryHandler, PicklePersistence

# --- КОНФИГУРАЦИЯ ---
# Токены берем из настроек Render (Environment Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Остальные настройки
CHANNEL_USERNAME = "@woltwarn"
CHANNEL_ID = -1003410531789
TARGET_THREAD_ID = 2
WEBAPP_URL = "https://misha671.github.io/wolt-fines-map/"

GITHUB_USERNAME = "misha671"
GITHUB_REPO = "wolt-fines-map"
GITHUB_FILE = "locations.json"
SUPER_ADMIN_ID = 913627492

# Путь для сохранения данных (На платном Render мы примонтируем диск в папку /data)
# Если папка /data существует (на сервере), сохраняем туда. Если нет (локально) - в корень.
DATA_PATH = "/data/bot_data.pickle" if os.path.exists("/data") else "bot_data.pickle"

# --- FLASK SERVER (Для Web Service) ---
# --- FLASK SERVER (Для предотвращения "засыпания") ---
app = Flask(__name__)

@app.route('/')
def home():
    # Ответ для захода через браузер
    return "Bot is running! Keep me awake, please.", 200

@app.route('/health')
def health():
    # Специальный ответ для UptimeRobot
    return {"status": "ok", "message": "I am alive!"}, 200

def run_flask():
    # Render сам назначит нужный порт
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- ВАШ КОД (РЕГИОНЫ И ЛОГИКА) ---

REGIONS = {
    'tel_aviv': {'name': 'Тель-Авив', 'coords': (32.0853, 34.7818), 'radius': 8},
    'rishon': {'name': 'Ришон ле-Цион', 'coords': (31.9730, 34.7925), 'radius': 7},
    'bat_yam': {'name': 'Бат-Ям', 'coords': (32.0178, 34.7478), 'radius': 5},
    'ramat_gan': {'name': 'Рамат-Ган', 'coords': (32.0806, 34.8239), 'radius': 5},
    'holon': {'name': 'Холон', 'coords': (32.0167, 34.7667), 'radius': 5},
    'givatayim': {'name': 'Гиватаим', 'coords': (32.0706, 34.8106), 'radius': 4},
    'petach_tikva': {'name': 'Петах-Тиква', 'coords': (32.0900, 34.8878), 'radius': 7},
    'netanya': {'name': 'Нетания', 'coords': (32.3314, 34.8467), 'radius': 6},
    'herzliya': {'name': 'Герцлия', 'coords': (32.1661, 34.8367), 'radius': 5},
    'raanana': {'name': 'Раанана', 'coords': (32.1858, 34.8706), 'radius': 5},
    'kfar_saba': {'name': 'Кфар-Саба', 'coords': (32.1764, 34.9064), 'radius': 5},
    'haifa': {'name': 'Хайфа', 'coords': (32.7940, 34.9896), 'radius': 10},
    'jerusalem': {'name': 'Иерусалим', 'coords': (31.7683, 35.2137), 'radius': 10},
    'beersheba': {'name': 'Беэр-Шева', 'coords': (31.2518, 34.7913), 'radius': 8},
    'ashdod': {'name': 'Ашдод', 'coords': (31.8044, 34.6553), 'radius': 6},
    'ashkelon': {'name': 'Ашкелон', 'coords': (31.6688, 34.5742), 'radius': 6}
}

def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def get_location_region(latitude, longitude):
    for region_id, region_data in REGIONS.items():
        region_lat, region_lon = region_data['coords']
        if calculate_distance(latitude, longitude, region_lat, region_lon) <= region_data['radius']:
            return region_id
    return None

async def save_data_to_file(context: ContextTypes.DEFAULT_TYPE):
    # Эта функция теперь отвечает только за отправку на GitHub,
    # так как локальное сохранение делает PicklePersistence автоматически
    try:
        locations = context.bot_data.get('locations', [])
        data = {
            'locations': locations,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(locations)
        }
        
        # Загружаем на GitHub (для карты)
        if GITHUB_TOKEN:
            upload_to_github(data)
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False

def upload_to_github(data):
    try:
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        sha = None
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                sha = resp.json()["sha"]
        except: pass
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        payload = {
            "message": f"Update: {datetime.now().strftime('%H:%M:%S')}",
            "content": b64encode(content.encode()).decode(),
        }
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except Exception as e:
        print(f"❌ GitHub Error: {e}")

def is_admin(user_id, context):
    if user_id == SUPER_ADMIN_ID: return True
    return user_id in context.bot_data.get('admins', set())

# --- ХЕНДЛЕРЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users = context.bot_data.get('users', {})
    if user_id not in users:
        await show_registration(update, context)
    else:
        await show_main_menu(update, context, user_id)

async def show_registration(update, context):
    user_id = update.effective_user.id
    if 'temp_regions' not in context.bot_data: context.bot_data['temp_regions'] = {}
    context.bot_data['temp_regions'][user_id] = set()
    text = "👋 Добро пожаловать!\n📍 Выберите регионы работы:"
    keyboard = build_regions_keyboard(set(), "reg")
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

def build_regions_keyboard(selected_regions, prefix):
    keyboard = []
    row = []
    for region_id, region_data in REGIONS.items():
        check = "✅ " if region_id in selected_regions else ""
        row.append(InlineKeyboardButton(f"{check}{region_data['name']}", callback_data=f"{prefix}_{region_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    if prefix == "reg":
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="reg_done")])
        keyboard.append([InlineKeyboardButton("⏭ Пропустить", callback_data="reg_skip")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Сохранить", callback_data="set_region_done")])
        keyboard.append([InlineKeyboardButton("🗑 Очистить все", callback_data="set_region_clear")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="settings")])
    return keyboard

async def show_main_menu(update, context, user_id):
    keyboard = [
        [InlineKeyboardButton("🗺 Открыть карту штрафов", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ]
    if is_admin(user_id, context):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin")])
    await update.message.reply_text("Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Логика регистрации и настроек
    if data.startswith("reg_") and data not in ["reg_done", "reg_skip"]:
        region = data[4:]
        if 'temp_regions' not in context.bot_data: context.bot_data['temp_regions'] = {}
        if user_id not in context.bot_data['temp_regions']: context.bot_data['temp_regions'][user_id] = set()
        
        if region in context.bot_data['temp_regions'][user_id]:
            context.bot_data['temp_regions'][user_id].discard(region)
        else:
            context.bot_data['temp_regions'][user_id].add(region)
            
        selected = context.bot_data['temp_regions'][user_id]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(build_regions_keyboard(selected, "reg")))
        return

    if data == "reg_done":
        selected = context.bot_data.get('temp_regions', {}).get(user_id, set())
        if not selected:
            await query.answer("Выберите регион!")
            return
        if 'users' not in context.bot_data: context.bot_data['users'] = {}
        context.bot_data['users'][user_id] = {'regions': list(selected), 'notifications': True, 'registered_at': datetime.now().isoformat()}
        if user_id in context.bot_data.get('temp_regions', {}): del context.bot_data['temp_regions'][user_id]
        await query.edit_message_text("✅ Настройка завершена! Уведомления включены.\nМеню: /start")
        return

    if data == "reg_skip":
        if 'users' not in context.bot_data: context.bot_data['users'] = {}
        context.bot_data['users'][user_id] = {'regions': [], 'notifications': False, 'registered_at': datetime.now().isoformat()}
        await query.edit_message_text("✅ Настройка завершена (без уведомлений).\nМеню: /start")
        return

    if data == "settings":
        await show_settings(query, context, user_id)
        return

    if data == "settings_region":
        user_regions = set(context.bot_data['users'].get(user_id, {}).get('regions', []))
        await query.edit_message_text("Выберите регионы:", reply_markup=InlineKeyboardMarkup(build_regions_keyboard(user_regions, "set_region")))
        return
        
    if data.startswith("set_region_") and data not in ["set_region_done", "set_region_clear"]:
        region = data[11:]
        user_data = context.bot_data['users'].get(user_id, {})
        regions = set(user_data.get('regions', []))
        if region in regions: regions.discard(region)
        else: regions.add(region)
        context.bot_data['users'][user_id]['regions'] = list(regions)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(build_regions_keyboard(regions, "set_region")))
        return

    if data == "set_region_done":
        await show_settings(query, context, user_id)
        return

    if data == "set_region_clear":
        context.bot_data['users'][user_id]['regions'] = []
        await show_settings(query, context, user_id)
        return

    if data == "settings_notif_toggle":
        curr = context.bot_data['users'][user_id].get('notifications', False)
        context.bot_data['users'][user_id]['notifications'] = not curr
        await show_settings(query, context, user_id)
        return
        
    if data == "back_main":
        await show_main_menu(update, context, user_id)
        return

    # Админка
    if data == "admin" and is_admin(user_id, context):
        keyboard = [
            [InlineKeyboardButton("🗑 Удалить все точки", callback_data="admin_clear")],
            [InlineKeyboardButton("📥 Экспорт", callback_data="admin_export")],
            [InlineKeyboardButton("« Назад", callback_data="back_main")]
        ]
        await query.edit_message_text(f"Админ панель.\nТочек: {len(context.bot_data.get('locations', []))}\nПользователей: {len(context.bot_data.get('users', {}))}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "admin_clear" and is_admin(user_id, context):
        context.bot_data['locations'] = []
        await save_data_to_file(context) # Обновит GitHub
        await query.answer("Все точки удалены")
        await show_main_menu(update, context, user_id)
        return

    if data == "admin_export" and is_admin(user_id, context):
        await export_data(query, context)
        return

async def show_settings(query, context, user_id):
    user_data = context.bot_data['users'].get(user_id, {})
    notif = "✅ Вкл" if user_data.get('notifications') else "🔕 Выкл"
    regions_count = len(user_data.get('regions', []))
    text = f"⚙️ Настройки\n🔔 Уведомления: {notif}\n📍 Регионов: {regions_count}"
    keyboard = [
        [InlineKeyboardButton("📍 Изменить регионы", callback_data="settings_region")],
        [InlineKeyboardButton("🔔 Вкл/Выкл уведомления", callback_data="settings_notif_toggle")],
        [InlineKeyboardButton("« Назад", callback_data="back_main")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post or update.message
    if not post or not post.location: return
    if post.chat.username != "woltwarn" or post.message_thread_id != TARGET_THREAD_ID: return

    loc_data = {
        'latitude': post.location.latitude,
        'longitude': post.location.longitude,
        'timestamp': datetime.now().isoformat(),
        'user': post.from_user.first_name if post.from_user else "Канал",
        'message_id': post.message_id
    }

    if 'locations' not in context.bot_data: context.bot_data['locations'] = []
    # Проверка дублей
    if not any(l.get('message_id') == loc_data['message_id'] for l in context.bot_data['locations']):
        context.bot_data['locations'].append(loc_data)
        # Храним 200 последних
        if len(context.bot_data['locations']) > 200:
            context.bot_data['locations'] = context.bot_data['locations'][-200:]
        
        await save_data_to_file(context) # Обновление GitHub
        await notify_users(context, loc_data)

async def notify_users(context, location_data):
    users = context.bot_data.get('users', {})
    region = get_location_region(location_data['latitude'], location_data['longitude'])
    if not region: return
    
    region_name = REGIONS[region]['name']
    for uid, udata in users.items():
        if udata.get('notifications') and region in udata.get('regions', []):
            try:
                await context.bot.send_location(chat_id=uid, latitude=location_data['latitude'], longitude=location_data['longitude'])
                await context.bot.send_message(
                    chat_id=uid, 
                    text=f"🚨 Новая метка: {region_name}\nКарта: {WEBAPP_URL}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗺 Карта", web_app=WebAppInfo(url=WEBAPP_URL))]])
                )
            except: pass

async def export_data(query, context):
    import io
    data = json.dumps(context.bot_data, default=str, indent=2, ensure_ascii=False)
    f = io.BytesIO(data.encode())
    f.name = 'backup.json'
    await context.bot.send_document(chat_id=query.from_user.id, document=f)

async def add_admin(update, context):
    if update.effective_user.id != SUPER_ADMIN_ID: return
    try:
        new_id = int(context.args[0])
        if 'admins' not in context.bot_data: context.bot_data['admins'] = set()
        context.bot_data['admins'].add(new_id)
        await update.message.reply_text(f"Админ {new_id} добавлен")
    except: await update.message.reply_text("Ошибка. Формат: /addadmin ID")

async def remove_admin(update, context):
    if update.effective_user.id != SUPER_ADMIN_ID: return
    try:
        aid = int(context.args[0])
        context.bot_data['admins'].discard(aid)
        await update.message.reply_text(f"Админ {aid} удален")
    except: pass

async def stats(update, context):
    await update.message.reply_text(f"Статистика:\nПользователей: {len(context.bot_data.get('users', {}))}\nТочек: {len(context.bot_data.get('locations', []))}")

async def reset(update, context):
    uid = update.effective_user.id
    if uid in context.bot_data.get('users', {}):
        del context.bot_data['users'][uid]
        await update.message.reply_text("Сброшено. Жмите /start")

def main():
    # Запуск Flask в фоне
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Настройка постоянного хранилища (Render Disk)
    persistence = PicklePersistence(filepath=DATA_PATH)
    
    app = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    print(f"🤖 Bot started. Storage path: {DATA_PATH}")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
