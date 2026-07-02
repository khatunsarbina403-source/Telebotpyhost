"""
================================================================================
 TASHAN GAME DEMO ACCOUNT SELLER BOT (UPDATED WITH PHONE SYSTEM)
================================================================================
"""

import telebot
from telebot import types
import json
import os
import threading
from datetime import datetime, date

# ==============================================================================
# SECTION 1: CONFIGURATION
# ==============================================================================

BOT_TOKEN = "7876309219:AAFylui-Lh4h3UUew-eIwHD9fa-DHnC-_OA"
ADMIN_ID = 6525785749

bot = telebot.TeleBot(BOT_TOKEN)

# ==============================================================================
# SECTION 2: DATABASE SETUP
# ==============================================================================

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
UTRS_FILE = os.path.join(DATA_DIR, "utrs.json")
CHAT_MAP_FILE = os.path.join(DATA_DIR, "chat_map.json")

file_lock = threading.Lock()

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

users = load_json(USERS_FILE, {})
accounts = load_json(ACCOUNTS_FILE, [])
settings = load_json(SETTINGS_FILE, {"price": "₹199", "button_name": "TASHAN GAME", "qr_file_id": ""})
utrs = load_json(UTRS_FILE, {})
chat_map = load_json(CHAT_MAP_FILE, {})

def save_users(): save_json(USERS_FILE, users)
def save_accounts(): save_json(ACCOUNTS_FILE, accounts)
def save_settings(): save_json(SETTINGS_FILE, settings)
def save_utrs(): save_json(UTRS_FILE, utrs)
def save_chat_map(): save_json(CHAT_MAP_FILE, chat_map)

# ==============================================================================
# SECTION 3: RUNTIME STATE
# ==============================================================================
user_state = {}
admin_state = {"step": None, "data": {}}

def reset_admin_state():
    admin_state["step"] = None
    admin_state["data"] = {}

# ==============================================================================
# SECTION 4: HELPERS
# ==============================================================================

def get_or_create_user(message):
    uid = str(message.from_user.id)
    now = datetime.now()
    if uid not in users:
        users[uid] = {
            "user_id": message.from_user.id,
            "username": message.from_user.username or "N/A",
            "first_name": message.from_user.first_name or "N/A",
            "phone": None, # Phone number initial state
            "join_date": now.strftime("%Y-%m-%d"),
            "join_time": now.strftime("%H:%M:%S"),
            "status": "active",
        }
        save_users()
    return users[uid]

def is_blocked(user_id):
    record = users.get(str(user_id))
    return bool(record and record.get("status") == "blocked")

def safe_send(chat_id, text, **kwargs):
    try:
        bot.send_message(chat_id, text, **kwargs)
        return True
    except:
        return False

# ==============================================================================
# SECTION 5: KEYBOARDS (REARRANGED ADMIN KEYBOARD)
# ==============================================================================

def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(types.KeyboardButton(settings.get("button_name", "TASHAN GAME")))
    kb.add(types.KeyboardButton("💬 Chat with Admin"))
    return kb

def phone_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("✅Demo Account", request_contact=True))
    return kb

def admin_menu_keyboard():
    """Behtar tarike se arrange kiya gaya Admin Keyboard"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Group 1: Account & Payment Settings
    btn1 = types.KeyboardButton("➕ Set QR Code")
    btn2 = types.KeyboardButton("💰 Set Price")
    btn3 = types.KeyboardButton("📥 Set Account Credentials")
    btn4 = types.KeyboardButton("✏️ Set Button Name")
    
    # Group 2: Management
    btn5 = types.KeyboardButton("📝 Pending UTRs")
    btn6 = types.KeyboardButton("👥 Users")
    
    # Group 3: User Control
    btn7 = types.KeyboardButton("🚫 Block User")
    btn8 = types.KeyboardButton("✅ Unblock User")
    btn9 = types.KeyboardButton("📋 Blocked Users")
    btn10 = types.KeyboardButton("📢 Broadcast")
    
    # Group 4: Exit
    btn11 = types.KeyboardButton("🔙 Exit")
    
    kb.add(btn1, btn2)
    kb.add(btn3, btn4)
    kb.add(btn5, btn6)
    kb.add(btn7, btn8)
    kb.add(btn9, btn10)
    kb.add(btn11)
    return kb

def utr_action_keyboard(utr_id):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve:{utr_id}"),
        types.InlineKeyboardButton("⏳ Pending", callback_data=f"pending:{utr_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"reject:{utr_id}"),
    )
    return kb

# ==============================================================================
# SECTION 6: HANDLERS
# ==============================================================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user = get_or_create_user(message)
    if is_blocked(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 You have been blocked.")
        return

    # Check if phone number exists
    if not user.get("phone"):
        bot.send_message(
            message.chat.id, 
            "👋 Welcome! Please click the button below to share your phone number and register.", 
            reply_markup=phone_keyboard()
        )
        return

    bot.send_message(
        message.chat.id,
        f"👋 Welcome back!\n💰 Current Price: {settings.get('price')}",
        reply_markup=main_menu_keyboard(),
    )

@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    uid = str(message.from_user.id)
    if uid in users and message.contact:
        users[uid]["phone"] = message.contact.phone_number
        save_users()
        bot.send_message(
            message.chat.id, 
            "✅Free Demo Account Ki Liye Admin ko Message Gya Hai please Wait kariye Ager Demo Account Apko nhi Mila to Samajh lo Koi or ne Win kar liya or hai Bar bar request doge to Dairect block🚫 And Paid Demo Account Buy karna Hai to Abhi manu Mein Click karke Buy kar Sakte ho✅!", 
            reply_markup=main_menu_keyboard()
        )

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    reset_admin_state()
    bot.send_message(message.chat.id, "🛠️ <b>Admin Panel</b>", parse_mode="HTML", reply_markup=admin_menu_keyboard())

# ==============================================================================
# SECTION 7: UTR PROCESSING (WITH PHONE IN ADMIN ALERT)
# ==============================================================================

def format_utr_details(record):
    user_record = users.get(str(record['user_id']), {})
    user_phone = user_record.get("phone", "Not Shared")
    
    return (
        "🆕 <b>New UTR Submission</b>\n\n"
        f"👤 User ID: <code>{record['user_id']}</code>\n"
        f"📱 <b>Phone:</b> <code>{user_phone}</code>\n" # Only Admin sees this
        f"🔖 Username: @{record.get('username', 'N/A')}\n"
        f"📛 Name: {record.get('first_name', 'N/A')}\n"
        f"💳 UTR: <code>{record['utr']}</code>\n"
        f"📅 Date: {record['date']} | Time: {record['time']}\n"
        f"📊 Status: {record['status']}"
    )

def process_utr_submission(message):
    user_id = message.from_user.id
    utr_text = message.text.strip()

    if not (utr_text.isdigit() and len(utr_text) == 12):
        bot.send_message(message.chat.id, "❌ Invalid UTR. Please send 12-digit number.")
        return

    user_record = users.get(str(user_id), {})
    utr_id = str(int(datetime.now().timestamp() * 1000))
    now = datetime.now()

    utrs[utr_id] = {
        "utr_id": utr_id,
        "user_id": user_id,
        "username": user_record.get("username", "N/A"),
        "first_name": user_record.get("first_name", "N/A"),
        "utr": utr_text,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "status": "Pending",
    }
    save_utrs()
    user_state.pop(user_id, None)

    bot.send_message(message.chat.id, "✅ UTR submitted! Admin will verify soon.")
    
    # Notify Admin
    try:
        bot.send_message(
            ADMIN_ID, 
            format_utr_details(utrs[utr_id]), 
            parse_mode="HTML", 
            reply_markup=utr_action_keyboard(utr_id)
        )
    except: pass

# ==============================================================================
# SECTION 8: MASTER DISPATCHER & ADMIN STEPS (REST OF THE LOGIC)
# ==============================================================================

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    
    # 1. Admin Chat Reply
    if user_id == ADMIN_ID and message.reply_to_message:
        replied_id = str(message.reply_to_message.message_id)
        target = chat_map.get(replied_id)
        if target:
            bot.copy_message(target, message.chat.id, message.message_id)
            bot.send_message(message.chat.id, "✅ Reply sent.")
        return

    # 2. Admin Logic
    if user_id == ADMIN_ID:
        if admin_state["step"]:
            handle_admin_step(message)
            return
        
        # Admin Buttons
        if message.text == "➕ Set QR Code":
            admin_state["step"] = "set_qr"
            bot.send_message(message.chat.id, "📷 Send QR Photo:")
        elif message.text == "💰 Set Price":
            admin_state["step"] = "set_price"
            bot.send_message(message.chat.id, "💰 Enter Price:")
        elif message.text == "📥 Set Account Credentials":
            admin_state["step"] = "acc_user"
            bot.send_message(message.chat.id, "👤 Enter Account Username:")
        elif message.text == "✏️ Set Button Name":
            admin_state["step"] = "set_btn"
            bot.send_message(message.chat.id, "✏️ Enter Button Name:")
        elif message.text == "📝 Pending UTRs":
            pending = [r for r in utrs.values() if r["status"] == "Pending"]
            if not pending: bot.send_message(message.chat.id, "📭 No pending UTRs.")
            for r in pending: bot.send_message(ADMIN_ID, format_utr_details(r), parse_mode="HTML", reply_markup=utr_action_keyboard(r["utr_id"]))
        elif message.text == "👥 Users":
            total = len(users)
            bot.send_message(message.chat.id, f"👥 Total Users: {total}\n📦 Stock: {len(accounts)}", parse_mode="HTML")
        elif message.text == "🚫 Block User":
            admin_state["step"] = "block"
            bot.send_message(message.chat.id, "🚫 Send User ID to block:")
        elif message.text == "📢 Broadcast":
            admin_state["step"] = "bc"
            bot.send_message(message.chat.id, "📢 Send message to broadcast:")
        elif message.text == "🔙 Exit":
            bot.send_message(message.chat.id, "Admin Closed.", reply_markup=types.ReplyKeyboardRemove())
        return

    # 3. User Logic
    user_record = get_or_create_user(message)
    if is_blocked(user_id): return
    
    if not user_record.get("phone"):
        bot.send_message(message.chat.id, "Please share phone number first.", reply_markup=phone_keyboard())
        return

    if user_state.get(user_id) == "awaiting_utr":
        process_utr_submission(message)
    elif user_state.get(user_id) == "chat_mode":
        forwarded = bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        chat_map[str(forwarded.message_id)] = user_id
        save_chat_map()
        bot.send_message(message.chat.id, "✅ Sent to Admin.")
    elif message.text == settings.get("button_name", "TASHAN GAME"):
        if not settings.get("qr_file_id"):
            bot.send_message(message.chat.id, "QR not set.")
            return
        bot.send_photo(message.chat.id, settings["qr_file_id"], caption=f"Price: {settings['price']}\nSend 12-digit UTR:")
        user_state[user_id] = "awaiting_utr"
    elif message.text == "💬 Chat with Admin":
        user_state[user_id] = "chat_mode"
        bot.send_message(message.chat.id, "💬 Chat Started. Type your message:")

def handle_admin_step(message):
    step = admin_state["step"]
    text = message.text
    if step == "set_price":
        settings["price"] = text
        save_settings()
        bot.send_message(message.chat.id, "✅ Price Updated.")
    elif step == "acc_user":
        admin_state["data"]["u"] = text
        admin_state["step"] = "acc_pass"
        bot.send_message(message.chat.id, "🔑 Enter Password:")
        return
    elif step == "acc_pass":
        admin_state["data"]["p"] = text
        admin_state["step"] = "acc_link"
        bot.send_message(message.chat.id, "🔗 Enter Login Link:")
        return
    elif step == "acc_link":
        accounts.append({"username": admin_state["data"]["u"], "password": admin_state["data"]["p"], "link": text})
        save_accounts()
        bot.send_message(message.chat.id, "✅ Account Added.")
    elif step == "set_btn":
        settings["button_name"] = text
        save_settings()
        bot.send_message(message.chat.id, "✅ Button Renamed.")
    elif step == "block":
        if text in users:
            users[text]["status"] = "blocked"
            save_users()
            bot.send_message(message.chat.id, "🚫 Blocked.")
    elif step == "bc":
        for u in users: safe_send(int(u), text)
        bot.send_message(message.chat.id, "📢 Broadcast Sent.")
    
    reset_admin_state()

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    if message.from_user.id == ADMIN_ID and admin_state["step"] == "set_qr":
        settings["qr_file_id"] = message.photo[-1].file_id
        save_settings()
        reset_admin_state()
        bot.send_message(message.chat.id, "✅ QR Code Updated.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.from_user.id != ADMIN_ID: return
    action, utr_id = call.data.split(":")
    record = utrs.get(utr_id)
    if not record: return

    if action == "approve":
        if not accounts:
            bot.answer_callback_query(call.id, "⚠️ No Stock!", show_alert=True)
            return
        acc = accounts.pop(0)
        save_accounts()
        record["status"] = "Approved"
        save_utrs()
        text = f"✅ <b>Approved!</b>\n👤 User: {acc['username']}\n🔑 Pass: {acc['password']}\n🔗 Link: {acc['link']}"
        safe_send(record["user_id"], text, parse_mode="HTML")
        bot.edit_message_text(format_utr_details(record), call.message.chat.id, call.message.message_id, parse_mode="HTML")
    elif action == "reject":
        record["status"] = "Rejected"
        save_utrs()
        safe_send(record["user_id"], "❌ Payment Rejected.")
        bot.edit_message_text(format_utr_details(record), call.message.chat.id, call.message.message_id, parse_mode="HTML")
    elif action == "pending":
        safe_send(record["user_id"], "🕒 Your payment is under verification.")
        bot.answer_callback_query(call.id, "Marked Pending")

if __name__ == "__main__":
    print("🤖 Tashan Game Bot Running...")
    bot.infinity_polling(skip_pending=True)