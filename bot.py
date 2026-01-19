import os
import json
import threading
import requests
from flask import Flask
from datetime import datetime
from base64 import b64encode
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    MessageHandler, 
    CommandHandler, 
    filters, 
    ContextTypes, 
    CallbackQueryHandler, 
    PicklePersistence
)

# --- КОНФИГУРАЦИЯ (Берем из настроек Render) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Константы проекта
CHANNEL_USERNAME = "@woltwarn"
CHANNEL_ID = -1003410531789
TARGET_THREAD_ID = 2
WEBAPP_URL = "https://misha671.github.io/wolt-fines-map/"

GITHUB_USERNAME = "misha671"
GITHUB_REPO = "wolt-fines-map"
GITHUB_FILE = "locations.json"
SUPER_ADMIN_ID = 913627492

# --- FLASK SERVER (Для UptimeRobot) ---
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot is running!", 200

@server.route('/health')
def health_check():
    return {"status": "ok", "message": "I am alive!"}, 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

# --- РЕГИОНЫ ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def get_location_region(latitude, longitude):
    for r_id, r_data in REGIONS.items():
        if calculate_distance(latitude, longitude, *r_data['coords']) <= r_data['radius']:
            return r_id
    return None

def upload_to_github(data):
    try:
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        payload = {
            "message": f"Update: {datetime.now().strftime('%H:%M:%S')}",
            "content": b64encode(content.encode()).decode(),
        }
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except Exception as e: print(f"❌ GitHub Error: {e}")

async def save_data(context):
    locations = context.bot_data.get('locations', [])
    data = {'locations': locations, 'updated_at': datetime.now().isoformat()}
    upload_to_github(data)

# --- ХЕНДЛЕРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in context.bot_data.get('users', {}):
        context.bot_data.setdefault('temp_regions', {})[user_id] = set()
        await update.message.reply_text("👋 Привет! Выбери регионы для уведомлений:", 
            reply_markup=InlineKeyboardMarkup(build_keyboard(set(), "reg")))
    else: await show_menu(update, context)

def build_keyboard(selected, prefix):
    kb, row = [], []
    for r_id, r_data in REGIONS.items():
        mark = "✅ " if r_id in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{r_data['name']}", callback_data=f"{prefix}_{r_id}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    if prefix == "reg": kb.append([InlineKeyboardButton("✅ Готово", callback_data="reg_done")])
    else: kb.append([InlineKeyboardButton("✅ Сохранить", callback_data="set_done")])
    return kb

async def show_menu(update, context):
    uid = update.effective_user.id
    kb = [[InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))],
          [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]]
    if uid == SUPER_ADMIN_ID or uid in context.bot_data.get('admins', set()):
        kb.append([InlineKeyboardButton("👑 Админ", callback_data="admin")])
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text("Главное меню:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post or update.message
    if not post or not post.location: return
    if post.chat.id != CHANNEL_ID: return

    loc = {'latitude': post.location.latitude, 'longitude': post.location.longitude,
           'timestamp': datetime.now().isoformat(), 'user': post.from_user.first_name if post.from_user else "Admin"}
    
    context.bot_data.setdefault('locations', []).append(loc)
    context.bot_data['locations'] = context.bot_data['locations'][-200:]
    await save_data(context)
    await notify_users(context, loc)

async def notify_users(context, loc_data):
    """ОТПРАВКА В ФОРМАТЕ СКРИНШОТА"""
    rid = get_location_region(loc_data['latitude'], loc_data['longitude'])
    if not rid: return
    
    r_name = REGIONS[rid]['name']
    time_str = datetime.fromisoformat(loc_data['timestamp']).strftime('%H:%M:%S')
    
    for uid, udata in context.bot_data.get('users', {}).items():
        if udata.get('notifications') and rid in udata.get('regions', []):
            try:
                # 1. Сначала карта
                await context.bot.send_location(chat_id=uid, latitude=loc_data['latitude'], longitude=loc_data['longitude'])
                # 2. Потом текст с кнопкой
                msg = (f"🚨 Новая метка в районе {r_name}!\n"
                       f"Она появиться на карте в течении 30 секунд\n"
                       f"👤 {loc_data['user']}\n"
                       f"🕐 {time_str}")
                kb = [[InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))]]
                await context.bot.send_message(chat_id=uid, text=msg, reply_markup=InlineKeyboardMarkup(kb))
            except: pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid, data = query.from_user.id, query.data

    if data.startswith("reg_") and data != "reg_done":
        rid = data[4:]
        temp = context.bot_data['temp_regions'][uid]
        temp.remove(rid) if rid in temp else temp.add(rid)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(build_keyboard(temp, "reg")))
    
    elif data == "reg_done":
        sel = list(context.bot_data['temp_regions'].pop(uid, []))
        context.bot_data.setdefault('users', {})[uid] = {'regions': sel, 'notifications': True}
        await query.edit_message_text("✅ Настройка завершена! Жми /start")

    elif data == "settings":
        udata = context.bot_data['users'].get(uid, {})
        notif = "✅" if udata.get('notifications') else "❌"
        txt = f"⚙️ Настройки\nУведомления: {notif}\nРегионов: {len(udata.get('regions', []))}"
        kb = [[InlineKeyboardButton("📍 Изменить регионы", callback_data="set_regs")],
              [InlineKeyboardButton("🔔 Вкл/Выкл", callback_data="notif_toggle")],
              [InlineKeyboardButton("« Назад", callback_data="main")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "notif_toggle":
        context.bot_data['users'][uid]['notifications'] = not context.bot_data['users'][uid].get('notifications')
        await button_handler(update, context) # Обновить меню

    elif data == "main": await show_menu(update, context)

# --- ЗАПУСК ---
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    persistence = PicklePersistence(filepath="bot_data.pickle")
    app = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.LOCATION & filters.Chat(CHANNEL_ID), handle_location))
    app.add_handler(MessageHandler(filters.LOCATION & filters.ChatType.PRIVATE, handle_location))
    
    print("🤖 Бот запущен...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
