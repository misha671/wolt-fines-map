import os
import json
import threading
import requests
from flask import Flask
from datetime import datetime
from base64 import b64encode
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, 
    MessageHandler, 
    CommandHandler, 
    filters, 
    ContextTypes, 
    CallbackQueryHandler, 
    PicklePersistence
)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

CHANNEL_USERNAME = "@woltwarn"
CHANNEL_ID = -1003410531789
TARGET_THREAD_ID = 2
WEBAPP_URL = "https://misha671.github.io/wolt-fines-map/"

GITHUB_USERNAME = "misha671"
GITHUB_REPO = "wolt-fines-map"
GITHUB_FILE = "locations.json"
SUPER_ADMIN_ID = 913627492

# --- FLASK SERVER ---
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
    print(f"⚠️ No region match for: {latitude}, {longitude}")
    return None

def upload_to_github(data):
    try:
        print(f"\n{'='*60}")
        print(f"🔄 GITHUB UPLOAD START")
        print(f"{'='*60}")
        print(f"Locations to upload: {len(data.get('locations', []))}")
        
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        print(f"📡 GET {url}")
        res = requests.get(url, headers=headers, timeout=10)
        print(f"Response: {res.status_code}")
        
        if res.status_code == 200:
            sha = res.json().get("sha")
            print(f"✅ File exists, SHA: {sha[:10]}...")
        elif res.status_code == 404:
            sha = None
            print(f"⚠️ File not found, will create new")
        else:
            print(f"❌ Unexpected response: {res.text[:200]}")
            return
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        payload = {
            "message": f"Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": b64encode(content.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        
        print(f"📤 PUT to GitHub...")
        res = requests.put(url, headers=headers, json=payload, timeout=10)
        print(f"Response: {res.status_code}")
        
        if res.status_code in [200, 201]:
            print(f"✅ SUCCESS! GitHub updated")
            print(f"🔗 https://github.com/{GITHUB_USERNAME}/{GITHUB_REPO}/blob/main/{GITHUB_FILE}")
        else:
            print(f"❌ FAILED: {res.text[:200]}")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

async def save_data(context):
    locations = context.bot_data.get('locations', [])
    data = {
        'locations': locations,
        'updated_at': datetime.now().isoformat(),
        'total_count': len(locations)
    }
    print(f"💾 Saving data to GitHub: {len(locations)} locations")
    upload_to_github(data)

# --- ХЕНДЛЕРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем зарегистрирован ли пользователь
    users = context.bot_data.setdefault('users', {})
    
    if user_id in users:
        # Пользователь уже зарегистрирован - показываем меню
        await show_menu(update, context)
    else:
        # Новый пользователь - регистрация
        context.bot_data.setdefault('temp_regions', {})[user_id] = set()
        await update.message.reply_text(
            "👋 Привет! Выбери регионы для уведомлений:",
            reply_markup=InlineKeyboardMarkup(build_keyboard(set(), "reg"))
        )

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
    
    if prefix == "reg":
        kb.append([InlineKeyboardButton("✅ Готово", callback_data="reg_done")])
    else:
        kb.append([InlineKeyboardButton("✅ Сохранить", callback_data="set_done")])
    return kb

async def show_menu(update, context):
    uid = update.effective_user.id
    kb = [
        [InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ]
    
    if uid == SUPER_ADMIN_ID or uid in context.bot_data.get('admins', set()):
        kb.append([InlineKeyboardButton("👑 Админ", callback_data="admin")])
    
    msg = update.callback_query.message if update.callback_query else update.message
    
    # Создаём кнопку меню снизу
    reply_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Меню")]],
        resize_keyboard=True
    )
    
    await msg.reply_text(
        "Главное меню:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    
    # Отправляем отдельно кнопку меню
    if not update.callback_query:
        await update.message.reply_text(
            "Используй кнопку ниже для быстрого доступа:",
            reply_markup=reply_kb
        )

async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 📍 Меню"""
    if update.message.text == "📍 Меню":
        await show_menu(update, context)

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление админа - /addadmin USER_ID"""
    uid = update.effective_user.id
    
    # Только супер-админ может добавлять админов
    if uid != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Только супер-админ может добавлять админов")
        return
    
    # Проверяем аргументы
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "❌ Неправильный формат\n\n"
            "Используй: <code>/addadmin USER_ID</code>\n"
            "Пример: <code>/addadmin 123456789</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID должен быть числом")
        return
    
    # Добавляем админа
    admins = context.bot_data.setdefault('admins', set())
    
    if new_admin_id in admins:
        await update.message.reply_text(f"⚠️ Пользователь <code>{new_admin_id}</code> уже является админом", parse_mode='HTML')
        return
    
    if new_admin_id == SUPER_ADMIN_ID:
        await update.message.reply_text("⚠️ Это супер-админ, он и так имеет все права")
        return
    
    admins.add(new_admin_id)
    await update.message.reply_text(
        f"✅ Пользователь <code>{new_admin_id}</code> добавлен в админы\n\n"
        f"Всего админов: {len(admins)}",
        parse_mode='HTML'
    )
    
    print(f"👮 Super-admin {uid} added admin {new_admin_id}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление админа - /removeadmin USER_ID"""
    uid = update.effective_user.id
    
    # Только супер-админ может удалять админов
    if uid != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Только супер-админ может удалять админов")
        return
    
    # Проверяем аргументы
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "❌ Неправильный формат\n\n"
            "Используй: <code>/removeadmin USER_ID</code>\n"
            "Пример: <code>/removeadmin 123456789</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID должен быть числом")
        return
    
    # Удаляем админа
    admins = context.bot_data.get('admins', set())
    
    if admin_id not in admins:
        await update.message.reply_text(f"⚠️ Пользователь <code>{admin_id}</code> не является админом", parse_mode='HTML')
        return
    
    admins.remove(admin_id)
    await update.message.reply_text(
        f"✅ Пользователь <code>{admin_id}</code> удалён из админов\n\n"
        f"Всего админов: {len(admins)}",
        parse_mode='HTML'
    )
    
    print(f"👮 Super-admin {uid} removed admin {admin_id}")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"\n{'='*60}")
    print(f"📍 LOCATION RECEIVED")
    print(f"{'='*60}")
    
    post = update.channel_post or update.message
    
    if not post:
        print("❌ No post")
        return
    
    if not post.location:
        print("❌ No location")
        return
    
    print(f"Chat ID: {post.chat.id}")
    print(f"Chat Type: {post.chat.type}")
    print(f"Message ID: {post.message_id}")
    print(f"From User: {post.from_user.first_name if post.from_user else 'None'}")
    print(f"Location: {post.location.latitude}, {post.location.longitude}")
    
    if hasattr(post, 'message_thread_id') and post.message_thread_id:
        print(f"Thread ID: {post.message_thread_id}")
    
    # ✅ ПРИНИМАЕМ ГЕОМЕТКИ ИЗ ЛЮБОГО КАНАЛА И ЛИЧНЫХ СООБЩЕНИЙ
    is_valid_chat = (
        post.chat.type in ['supergroup', 'group', 'private', 'channel']
    )
    
    if not is_valid_chat:
        print(f"⚠️ Wrong chat type: {post.chat.type}")
        return
    
    print(f"✅ Chat OK")
    
    loc = {
        'latitude': post.location.latitude,
        'longitude': post.location.longitude,
        'timestamp': datetime.now().isoformat(),
        'user': post.from_user.first_name if post.from_user else "Admin",
        'message_id': post.message_id
    }
    
    print(f"\n📝 Location object:")
    print(json.dumps(loc, indent=2, ensure_ascii=False))
    
    context.bot_data.setdefault('locations', []).append(loc)
    context.bot_data['locations'] = context.bot_data['locations'][-200:]
    
    print(f"\n💾 Total in memory: {len(context.bot_data['locations'])}")
    
    print(f"\n🔄 Saving to GitHub...")
    await save_data(context)
    
    print(f"\n📢 Notifying users...")
    await notify_users(context, loc)
    
    print(f"{'='*60}\n")

async def notify_users(context, loc_data):
    print(f"📢 NOTIFY START")
    
    rid = get_location_region(loc_data['latitude'], loc_data['longitude'])
    
    if not rid:
        print("⚠️ No region - skipping notifications")
        return
    
    r_name = REGIONS[rid]['name']
    time_str = datetime.fromisoformat(loc_data['timestamp']).strftime('%H:%M')
    
    users = context.bot_data.get('users', {})
    print(f"👥 Users: {len(users)}")
    
    sent = 0
    for uid, udata in users.items():
        notifications_on = udata.get('notifications', False)
        has_region = rid in udata.get('regions', [])
        
        print(f"\nUser {uid}:")
        print(f"  Notifications: {notifications_on}")
        print(f"  Has region: {has_region}")
        
        if notifications_on and has_region:
            try:
                # ✅ СНАЧАЛА ГЕОЛОКАЦИЯ
                await context.bot.send_location(
                    chat_id=uid,
                    latitude=loc_data['latitude'],
                    longitude=loc_data['longitude']
                )
                
                # ✅ ПОТОМ ТЕКСТ
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
                
                sent += 1
                print(f"  ✅ Sent")
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
        else:
            print(f"  ⏭ Skip")
    
    print(f"\n📊 Sent to {sent}/{len(users)} users")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid, data = query.from_user.id, query.data

    if data.startswith("reg_") and data != "reg_done":
        rid = data[4:]
        temp = context.bot_data.setdefault('temp_regions', {}).setdefault(uid, set())
        temp.remove(rid) if rid in temp else temp.add(rid)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(build_keyboard(temp, "reg"))
        )
    
    elif data == "reg_done":
        sel = list(context.bot_data.setdefault('temp_regions', {}).pop(uid, []))
        context.bot_data.setdefault('users', {})[uid] = {
            'regions': sel,
            'notifications': True
        }
        print(f"✅ User {uid} registered: {sel}")
        await query.edit_message_text("✅ Настройка завершена! Нажми /start для открытия меню")

    elif data == "settings":
        udata = context.bot_data.setdefault('users', {}).get(uid, {})
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
        users = context.bot_data.setdefault('users', {})
        if uid in users:
            users[uid]['notifications'] = not users[uid].get('notifications')
        await button_handler(update, context)

    elif data == "set_regs":
        current = set(context.bot_data.setdefault('users', {}).get(uid, {}).get('regions', []))
        context.bot_data.setdefault('temp_regions', {})[uid] = current
        await query.edit_message_text(
            "Выбери регионы:",
            reply_markup=InlineKeyboardMarkup(build_keyboard(current, "setreg"))
        )
    
    elif data.startswith("setreg_"):
        rid = data[7:]
        temp = context.bot_data.setdefault('temp_regions', {}).setdefault(uid, set())
        temp.remove(rid) if rid in temp else temp.add(rid)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(build_keyboard(temp, "setreg"))
        )
    
    elif data == "set_done":
        sel = list(context.bot_data.setdefault('temp_regions', {}).pop(uid, []))
        context.bot_data.setdefault('users', {})[uid]['regions'] = sel
        await query.edit_message_text("✅ Регионы обновлены!")
        await show_menu(update, context)

    elif data == "admin":
        # Админ панель
        if uid != SUPER_ADMIN_ID and uid not in context.bot_data.get('admins', set()):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        total_users = len(context.bot_data.get('users', {}))
        total_locations = len(context.bot_data.get('locations', []))
        total_admins = len(context.bot_data.get('admins', set()))
        
        txt = (
            f"👑 <b>Админ панель</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"📍 Меток сохранено: {total_locations}\n"
            f"👮 Админов: {total_admins}\n"
        )
        
        kb = [
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("🗑 Удалить все метки", callback_data="admin_clear_locations")],
            [InlineKeyboardButton("👮 Управление админами", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("« Назад", callback_data="main")]
        ]
        
        await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "admin_stats":
        # Детальная статистика
        users = context.bot_data.get('users', {})
        
        # Считаем по регионам
        region_stats = {}
        for uid, udata in users.items():
            for region in udata.get('regions', []):
                region_stats[region] = region_stats.get(region, 0) + 1
        
        stats_text = "\n".join([
            f"• {REGIONS[rid]['name']}: {count} чел."
            for rid, count in sorted(region_stats.items(), key=lambda x: -x[1])
        ])
        
        txt = (
            f"📊 <b>Статистика по регионам</b>\n\n"
            f"{stats_text if stats_text else 'Нет данных'}"
        )
        
        kb = [[InlineKeyboardButton("« Назад", callback_data="admin")]]
        await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "admin_clear_locations":
        # Подтверждение удаления
        if uid != SUPER_ADMIN_ID and uid not in context.bot_data.get('admins', set()):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        total = len(context.bot_data.get('locations', []))
        txt = (
            f"⚠️ <b>Подтверждение удаления</b>\n\n"
            f"Вы уверены что хотите удалить <b>все {total} меток</b>?\n\n"
            f"Это действие нельзя отменить!"
        )
        
        kb = [
            [InlineKeyboardButton("✅ Да, удалить все", callback_data="admin_clear_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="admin")]
        ]
        
        await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "admin_clear_confirm":
        # Выполняем удаление
        if uid != SUPER_ADMIN_ID and uid not in context.bot_data.get('admins', set()):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        deleted_count = len(context.bot_data.get('locations', []))
        context.bot_data['locations'] = []
        
        # Сохраняем пустой список в GitHub
        await save_data(context)
        
        txt = f"✅ Удалено {deleted_count} меток\n\nДанные обновлены в GitHub"
        
        kb = [[InlineKeyboardButton("« Назад в админку", callback_data="admin")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))
        
        print(f"🗑️ Admin {uid} deleted all {deleted_count} locations")
    
    elif data == "admin_manage_admins":
        # Управление админами (только для супер-админа)
        if uid != SUPER_ADMIN_ID:
            await query.answer("❌ Только для супер-админа", show_alert=True)
            return
        
        admins = context.bot_data.get('admins', set())
        
        if admins:
            admins_list = "\n".join([f"• ID: <code>{admin_id}</code>" for admin_id in admins])
            txt = f"👮 <b>Список админов</b>\n\n{admins_list}\n\n"
        else:
            txt = "👮 <b>Список админов</b>\n\nАдминов пока нет\n\n"
        
        txt += "Для добавления админа отправь команду:\n<code>/addadmin USER_ID</code>\n\n"
        txt += "Для удаления админа отправь команду:\n<code>/removeadmin USER_ID</code>"
        
        kb = [[InlineKeyboardButton("« Назад", callback_data="admin")]]
        await query.edit_message_text(txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif data == "main":
        await show_menu(update, context)

# --- ЗАПУСК ---
def main():
    print(f"\n{'='*60}")
    print(f"🚀 BOT STARTING")
    print(f"{'='*60}")
    print(f"Bot Token: {'SET' if BOT_TOKEN else 'MISSING'}")
    print(f"GitHub Token: {'SET' if GITHUB_TOKEN else 'MISSING'}")
    print(f"Channel: {CHANNEL_ID}")
    print(f"Admin: {SUPER_ADMIN_ID}")
    print(f"{'='*60}\n")
    
    # ✅ УДАЛЯЕМ WEBHOOK
    print("🗑️ Deleting webhook...")
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        response = requests.post(url, timeout=10)
        if response.status_code == 200:
            print("✅ Webhook deleted")
        else:
            print(f"⚠️ Webhook deletion failed: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Error deleting webhook: {e}")
    
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Настройка персистентности
    persistence = PicklePersistence(filepath="bot_data.pickle")
    
    # Создание приложения
    app = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()
    
    # Регистрация хендлеров
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_button_handler))  # Для кнопки меню
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    print("🤖 Bot started!")
    print(f"📊 Flask on port {os.environ.get('PORT', 10000)}")
    print(f"🎯 Listening for locations\n")
    
    # ✅ ЗАПУСК POLLING (НЕ WEBHOOK!)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
