import os
import telebot
from telebot import types
from datetime import date

BOT_TOKEN = "7876309219:AAE340woHrN-UudoVO2T22zzcdIvaQO2pWQ"
ADMIN_ID = int(os.environ.get("6525785749"))

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------- GLOBAL STATE ----------------
qr_code_file_id = None
price = 20
button_name = "TASHAN GAME"          # <-- dynamic button name (changeable by admin)
tashan_accounts = []

pending_utrs = {}                    # user_id -> {"utr":, "name":, "time":}
user_ids = set()
user_msg_map = {}

users = {}                           # user_id -> {"name":, "join_date": date, "blocked": bool}
blocked_users = set()


# ---------------- HELPERS ----------------
def is_blocked(chat_id):
    return chat_id in blocked_users


def get_admin_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Set QR Code", "📥 Set Account Credentials")
    markup.add("💰 Set Price", "✏️ Set Button Name")
    markup.add("📝 Pending UTRs", "👥 Users")
    markup.add("🚫 Block User", "✅ Unblock User")
    markup.add("📃 Blocked Users List", "📢 Broadcast")
    markup.add("🔙 Exit")
    return markup


def register_user(message):
    uid = message.chat.id
    if uid not in users:
        users[uid] = {
            "name": message.from_user.first_name or "User",
            "join_date": date.today(),
            "blocked": False,
        }
    user_ids.add(uid)


# ---------------- START ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    if is_blocked(message.chat.id):
        return  # blocked user -> bot completely silent, can't use /start

    register_user(message)
    uname = message.from_user.first_name or "User"
    msg = (
        f"👋 Welcome {uname}!\n\n"
        f"📢 We provide demo accounts for *{button_name}*.\n\n"
        f"💡 *How it works:*\n"
        f"1️⃣ Click '{button_name}'\n"
        f"2️⃣ Pay ₹{price}\n"
        f"3️⃣ Submit 12-digit UTR\n"
        f"4️⃣ Get approved & receive login"
    )

    reply_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    reply_markup.row(button_name, "💬 Chat with Admin")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=reply_markup)


# ---------------- TASHAN BUTTON (dynamic name) ----------------
@bot.message_handler(func=lambda m: m.text == button_name)
def buy_tashan_handler(message):
    if is_blocked(message.chat.id):
        return

    caption = f"💰 Price: ₹{price}\n📤 Pay & send your 12-digit UTR"
    if qr_code_file_id:
        bot.send_photo(message.chat.id, qr_code_file_id, caption=caption)
    else:
        bot.send_message(message.chat.id, caption)
    bot.register_next_step_handler(message, handle_utr)


def handle_utr(message):
    if is_blocked(message.chat.id):
        return

    uid = message.chat.id
    name = message.from_user.first_name or "User"
    utr_text = message.text.strip() if message.text else "N/A"

    pending_utrs[uid] = {
        "utr": utr_text,
        "name": name,
        "time": message.date,
    }

    bot.send_message(
        uid,
        "✅ Your UTR has been received.\n"
        "⏳ UTR number pending, please wait.\n"
        "❓ Any problem? Chat with admin.\n"
        "⏰ Minimum reply time: 24 hours."
    )
    bot.send_message(
        ADMIN_ID,
        f"🆕 New UTR Submitted!\n👤 Name: {name}\n🆔 ID: {uid}\n💳 UTR: {utr_text}"
    )


# ---------------- CHAT WITH ADMIN ----------------
@bot.message_handler(func=lambda m: m.text == "💬 Chat with Admin")
def chat_with_admin_button(message):
    if is_blocked(message.chat.id):
        return
    bot.send_message(message.chat.id, "📝 Send your message for Admin:")
    bot.register_next_step_handler(message, forward_to_admin)


def forward_to_admin(message):
    if is_blocked(message.chat.id):
        return
    forwarded = bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    user_msg_map[forwarded.message_id] = message.chat.id
    bot.send_message(message.chat.id, "✅ Message sent to Admin. Please wait for reply.")


@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.reply_to_message)
def admin_reply_handler(message):
    reply_msg = message.reply_to_message
    original_msg_id = reply_msg.message_id

    for fwd_msg_id, uid in user_msg_map.items():
        if fwd_msg_id == original_msg_id:
            try:
                bot.send_message(uid, f"💬 Admin: {message.text}")
                bot.send_message(ADMIN_ID, "✅ Reply sent to user.")
                return
            except Exception:
                bot.send_message(ADMIN_ID, "❌ Failed to send reply.")
                return
    bot.send_message(ADMIN_ID, "⚠️ Couldn't find user to reply.")


# ---------------- ADMIN PANEL ----------------
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "🛠 Admin Panel", reply_markup=get_admin_markup())


# ---------------- ADMIN ACTIONS ----------------
@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID)
def admin_actions(message):
    text = message.text

    if text == "➕ Set QR Code":
        bot.send_message(message.chat.id, "📷 Send QR Code image:")
        bot.register_next_step_handler(message, save_qr)

    elif text == "📥 Set Account Credentials":
        bot.send_message(message.chat.id, "Send:\nusername: demo\npassword: pass\nlink: https://...")
        bot.register_next_step_handler(message, save_account)

    elif text == "💰 Set Price":
        bot.send_message(message.chat.id, "💰 Send new price:")
        bot.register_next_step_handler(message, set_price)

    elif text == "✏️ Set Button Name":
        bot.send_message(message.chat.id, f"✏️ Current button name: {button_name}\n\nSend new button name:")
        bot.register_next_step_handler(message, set_button_name)

    elif text == "📝 Pending UTRs":
        show_pending_utrs(message)

    elif text == "👥 Users":
        show_users_stats(message)

    elif text == "🚫 Block User":
        bot.send_message(message.chat.id, "🆔 Send the User ID to block:")
        bot.register_next_step_handler(message, block_user_step)

    elif text == "✅ Unblock User":
        bot.send_message(message.chat.id, "🆔 Send the User ID to unblock:")
        bot.register_next_step_handler(message, unblock_user_step)

    elif text == "📃 Blocked Users List":
        show_blocked_list(message)

    elif text == "📢 Broadcast":
        bot.send_message(message.chat.id, "📣 Send broadcast message:")
        bot.register_next_step_handler(message, broadcast)

    elif text == "🔙 Exit":
        bot.send_message(message.chat.id, "🔚 Admin Panel closed.\nSend /admin to open again.",
                          reply_markup=types.ReplyKeyboardRemove())


# ---------------- ADMIN ACTION HANDLERS ----------------
def save_qr(message):
    global qr_code_file_id
    if message.photo:
        qr_code_file_id = message.photo[-1].file_id
        bot.send_message(message.chat.id, "✅ QR Code saved successfully.", reply_markup=get_admin_markup())
    else:
        bot.send_message(message.chat.id, "❌ Please send a valid image.")


def save_account(message):
    tashan_accounts.append(message.text)
    bot.send_message(message.chat.id, "✅ Account credentials saved.", reply_markup=get_admin_markup())


def set_price(message):
    global price
    try:
        price = int(message.text.strip())
        bot.send_message(message.chat.id, f"✅ Price updated to ₹{price}", reply_markup=get_admin_markup())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid price. Send a number.")


def set_button_name(message):
    global button_name
    new_name = message.text.strip()
    if new_name:
        button_name = new_name
        bot.send_message(message.chat.id, f"✅ Button name updated to: {button_name}",
                          reply_markup=get_admin_markup())
    else:
        bot.send_message(message.chat.id, "❌ Invalid name.")


# ---- Pending UTRs (admin selects user -> notice sent) ----
def show_pending_utrs(message):
    if not pending_utrs:
        bot.send_message(message.chat.id, "✅ No pending UTRs right now.")
        return

    for uid, data in list(pending_utrs.items()):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📩 Send Pending Notice", callback_data=f"pending_{uid}"))
        bot.send_message(
            message.chat.id,
            f"👤 Name: {data['name']}\n🆔 ID: {uid}\n💳 UTR: {data['utr']}",
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("pending_"))
def handle_pending_callback(call):
    if call.message.chat.id != ADMIN_ID:
        return

    uid = int(call.data.split("_")[1])
    if uid in pending_utrs:
        try:
            bot.send_message(
                uid,
                "🆔 UTR Number Pending.\n"
                "⏳ Please wait, any problem? Chat with admin.\n"
                "⏰ Minimum reply time: 24 hours."
            )
            del pending_utrs[uid]
            bot.answer_callback_query(call.id, "✅ Notice sent to user.")
            bot.edit_message_text(
                f"✅ Pending notice sent to user {uid}.",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception:
            bot.answer_callback_query(call.id, "❌ Failed to send message.")
    else:
        bot.answer_callback_query(call.id, "⚠️ Already handled.")


# ---- Users stats ----
def show_users_stats(message):
    total = len(users)
    today = date.today()
    today_count = sum(1 for u in users.values() if u["join_date"] == today)
    blocked_count = len(blocked_users)

    text = (
        "📊 *User Statistics*\n\n"
        f"👤 Total Users: {total}\n"
        f"🆕 Today Joined: {today_count}\n"
        f"🚫 Blocked Users: {blocked_count}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ---- Block / Unblock ----
def block_user_step(message):
    try:
        uid = int(message.text.strip())
        blocked_users.add(uid)
        if uid in users:
            users[uid]["blocked"] = True
        bot.send_message(message.chat.id, f"✅ User {uid} has been blocked.", reply_markup=get_admin_markup())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid ID. Please send a numeric User ID.")


def unblock_user_step(message):
    try:
        uid = int(message.text.strip())
        if uid in blocked_users:
            blocked_users.remove(uid)
            if uid in users:
                users[uid]["blocked"] = False
            bot.send_message(message.chat.id, f"✅ User {uid} has been unblocked.", reply_markup=get_admin_markup())
        else:
            bot.send_message(message.chat.id, f"⚠️ User {uid} is not in blocked list.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid ID. Please send a numeric User ID.")


def show_blocked_list(message):
    if not blocked_users:
        bot.send_message(message.chat.id, "✅ No blocked users.")
        return
    text = "🚫 *Blocked Users:*\n\n" + "\n".join(
        f"🆔 {uid} - {users.get(uid, {}).get('name', 'Unknown')}" for uid in blocked_users
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ---- Broadcast ----
def broadcast(message):
    count = 0
    for uid in user_ids:
        if uid in blocked_users:
            continue
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            count += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ Broadcast sent to {count} users.", reply_markup=get_admin_markup())


# ---------------- RUN ----------------
if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
