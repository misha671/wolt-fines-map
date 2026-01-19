import os
import json
import requests
from flask import Flask, request
from datetime import datetime
from base64 import b64encode
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    PicklePersistence
)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://wolt-fines-map.onrender.com")  # Твой URL на Render

CHANNEL_USERNAME = "@woltwarn"
CHANNEL_ID = -1003410531789
TARGET_THREAD_ID = 2
WEBAPP_URL = "https://misha671.github.io/wolt-fines-map/"

GITHUB_USERNAME = "misha671"
GITHUB_REPO = "wolt-fines-map"
GITHUB_FILE = "locations.json"
SUPER_ADMIN_ID = 913627492

# --- FLASK + BOT APPLICATION ---
server = Flask(__name__)
application = None

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

# --- ФУНКЦИИ ---
def calculate_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def get_location_region(latitude, longitude):
    for r_id, r_data in REGIONS.items():
        dist = calculate_distance(latitude, longitude, *r_data['coords'])
        if dist <= r_data['radius']:
            print(f"📍 Region: {r_data['name']} (dist: {dist:.2f}km)")
            return r_id
    print(f"⚠️ No region match")
    return None

def upload_to_github(data):
    try:
        print(f"🔄 GitHub upload: {len(data.get('locations', []))} locations")
        
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        sha = res.json().get("sha") if res.status_code == 200 else None
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        payload = {
            "message": f"Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": b64encode(content.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        
        res = requests.put(url, headers=headers, json=payload, timeout=10)
        
        if res.status_code in [200, 201]:
            print(f"✅ GitHub updated")
        else:
            print(f"❌ GitHub error: {res.status_code}")
        
    except Exception as e:
        print(f"❌ Exception: {e}")

async def save_data(context):
    locations = context.bot_data.get('locations', [])
    data = {
        'locations': locations,
        'updated_at': datetime.now().isoformat(),
        'total_count': len(locations)
    }
    upload_to_github(data)

# --- ХЕНДЛЕРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in context.bot_data.get('users', {}):
        context.bot_data.setdefault('temp_regions', {})[user_id] = set()
        await update.message.reply_text(
            "👋 Привет! Выбери регионы для уведомлений:",
            reply_markup=InlineKeyboardMarkup(build_keyboard(set(), "reg"))
        )
    else:
        await show_menu(update, context)

def build_keyboard(selected, prefix):
    kb, row = [], []
    for r_id, r_data in REGIONS.items():
        mark = "✅ " if r_id in selected else ""
        row.append(InlineKeyboardButton(
            f"{mark}{r_data['name']}",
            callback_data=f"{prefix}_{r_id}"
        ))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    
    kb.append([InlineKeyboardButton(
        "✅ Готово" if prefix == "reg" else "✅ Сохранить",
        callback_data=f"{prefix}_done"
    )])
    return kb

async def show_menu(update, context):
    uid = update.effective_user.id
    kb = [
        [InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ]
    
    if uid == SUPER_ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 Админ", callback_data="admin")])
    
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text("Главное меню:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"\n📍 LOCATION RECEIVED")
    
    post = update.channel_post or update.message
    
    if not post or not post.location:
        return
    
    print(f"Chat: {post.chat.id}, Location: {post.location.latitude}, {post.location.longitude}")
    
    is_valid = post.chat.id == CHANNEL_ID or post.chat.type == 'private'
    
    if not is_valid:
        print(f"⚠️ Wrong chat")
        return
    
    loc = {
        'latitude': post.location.latitude,
        'longitude': post.location.longitude,
        'timestamp': datetime.now().isoformat(),
        'user': post.from_user.first_name if post.from_user else "Admin",
        'message_id': post.message_id
    }
    
    context.bot_data.setdefault('locations', []).append(loc)
    context.bot_data['locations'] = context.bot_data['locations'][-200:]
    
    print(f"💾 Saved. Total: {len(context.bot_data['locations'])}")
    
    await save_data(context)
    await notify_users(context, loc)

async def notify_users(context, loc_data):
    print(f"📢 Notifying users")
    
    rid = get_location_region(loc_data['latitude'], loc_data['longitude'])
    
    if not rid:
        return
    
    r_name = REGIONS[rid]['name']
    time_str = datetime.fromisoformat(loc_data['timestamp']).strftime('%H:%M')
    
    users = context.bot_data.get('users', {})
    sent = 0
    
    for uid, udata in users.items():
        if udata.get('notifications') and rid in udata.get('regions', []):
            try:
                msg = (
                    f"🚨 <b>Новая метка!</b>\n\n"
                    f"📍 Район: <b>{r_name}</b>\n"
                    f"👤 Отправил: {loc_data['user']}\n"
                    f"🕐 Время: {time_str}\n\n"
                    f"⏱ Метка появится на карте в течение 30 секунд"
                )
                
                kb = [[InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))]]
                
                await context.bot.send_message(
                    chat_id=uid,
                    text=msg,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                
                await context.bot.send_location(
                    chat_id=uid,
                    latitude=loc_data['latitude'],
                    longitude=loc_data['longitude']
                )
                
                sent += 1
                
            except Exception as e:
                print(f"❌ Error sending to {uid}: {e}")
    
    print(f"📊 Sent to {sent} users")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid, data = query.from_user.id, query.data

    if data.startswith("reg_") and data != "reg_done":
        rid = data[4:]
        temp = context.bot_data['temp_regions'][uid]
        temp.remove(rid) if rid in temp else temp.add(rid)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(build_keyboard(temp, "reg"))
        )
    
    elif data == "reg_done":
        sel = list(context.bot_data['temp_regions'].pop(uid, []))
        context.bot_data.setdefault('users', {})[uid] = {
            'regions': sel,
            'notifications': True
        }
        await query.edit_message_text("✅ Настройка завершена! Жми /start")

    elif data == "settings":
        udata = context.bot_data['users'].get(uid, {})
        notif = "✅ Включены" if udata.get('notifications') else "❌ Выключены"
        txt = (
            f"⚙️ <b>Настройки</b>\n\n"
            f"🔔 Уведомления: {notif}\n"
            f"📍 Регионов: {len(udata.get('regions', []))}"
        )
        kb = [
            [InlineKeyboardButton("📍 Изменить регионы", callback_data="set_regs")],
            [InlineKeyboardButton("🔔 Вкл/Выкл", callback_data="notif_toggle")],
            [InlineKeyboardButton("« Назад", callback_data="main")]
        ]
        await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif data == "notif_toggle":
        context.bot_data['users'][uid]['notifications'] = not context.bot_data['users'][uid].get('notifications')
        await button_handler(update, context)

    elif data == "set_regs":
        current = set(context.bot_data['users'][uid].get('regions', []))
        context.bot_data.setdefault('temp_regions', {})[uid] = current
        await query.edit_message_text(
            "Выбери регионы:",
            reply_markup=InlineKeyboardMarkup(build_keyboard(current, "setreg"))
        )
    
    elif data.startswith("setreg_"):
        rid = data[7:]
        temp = context.bot_data['temp_regions'][uid]
        temp.remove(rid) if rid in temp else temp.add(rid)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(build_keyboard(temp, "setreg"))
        )
    
    elif data == "set_done":
        sel = list(context.bot_data['temp_regions'].pop(uid, []))
        context.bot_data['users'][uid]['regions'] = sel
        await query.edit_message_text("✅ Регионы обновлены!")
        await show_menu(update, context)

    elif data == "main":
        await show_menu(update, context)

# --- FLASK ROUTES ---
@server.route('/')
def home():
    return "Bot is running!", 200

@server.route('/health')
def health_check():
    return {"status": "ok"}, 200

@server.route(f'/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    """Webhook для получения обновлений от Telegram"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return 'ok', 200
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return 'error', 500

# --- ЗАПУСК ---
def main():
    global application
    
    print(f"\n{'='*60}")
    print(f"🚀 BOT STARTING (WEBHOOK MODE)")
    print(f"{'='*60}")
    print(f"Bot Token: {'SET' if BOT_TOKEN else 'MISSING'}")
    print(f"GitHub Token: {'SET' if GITHUB_TOKEN else 'MISSING'}")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print(f"{'='*60}\n")
    
    # Создаём приложение
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .build()
    )
    
    # Регистрируем хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    # Устанавливаем webhook
    import asyncio
    asyncio.run(application.bot.set_webhook(
        url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        allowed_updates=["message", "channel_post", "callback_query"]
    ))
    
    print("✅ Webhook установлен")
    print(f"🎯 Webhook URL: {WEBHOOK_URL}/{BOT_TOKEN}")
    
    # Запускаем Flask
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Starting Flask on port {port}\n")
    server.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()
