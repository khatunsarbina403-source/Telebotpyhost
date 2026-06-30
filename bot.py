"""
================================================================================
 TASHAN GAME DEMO ACCOUNT SELLER BOT
================================================================================
A complete, production-ready Telegram bot built with pyTelegramBotAPI (telebot)
for selling demo "Tashan Game" accounts.

FEATURES
--------
USER SIDE:
    - /start welcome message with a dynamic "Buy" button and a "Chat with
      Admin" button.
    - Buy flow: shows QR code + price, collects a 12-digit UTR number, saves
      it as "Pending" and notifies the Admin.
    - Chat with Admin: forwards user messages to Admin; Admin replies by
      simply replying to the forwarded message and the bot routes the reply
      back to the correct user automatically.

ADMIN SIDE (only the configured ADMIN_ID can access this, via /admin):
    - Set QR Code (photo upload, saved permanently as a Telegram file_id)
    - Set Account Credentials (stock of demo accounts: username/password/link)
    - Set Price (instantly reflected to users)
    - Pending UTRs (Approve / Pending / Reject each submission)
    - Set Button Name (renames the user-facing Buy button)
    - Users (stats: total, today joined, blocked, approved/pending/rejected)
    - Block / Unblock User
    - Blocked Users list
    - Broadcast a message to every active (non-blocked) user
    - Exit (closes the Admin keyboard)

STORAGE
-------
Everything is persisted using simple JSON files inside the ./data folder so
that all information survives a bot restart.

SETUP
-----
    1. pip install pyTelegramBotAPI
    2. Fill in BOT_TOKEN and ADMIN_ID below.
    3. python bot.py
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

# Your Telegram Bot Token (get it from @BotFather)
BOT_TOKEN = "7876309219:AAFylui-Lh4h3UUew-eIwHD9fa-DHnC-_OA"

# The ONLY Telegram numeric user ID that is allowed to open the Admin Panel.
# You can get your numeric ID from a bot like @userinfobot.
ADMIN_ID = 6525785749

bot = telebot.TeleBot(BOT_TOKEN)

# ==============================================================================
# SECTION 2: DATABASE (JSON FILE) SETUP
# ==============================================================================

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
UTRS_FILE = os.path.join(DATA_DIR, "utrs.json")
CHAT_MAP_FILE = os.path.join(DATA_DIR, "chat_map.json")

# A lock so that simultaneous read/write operations from multiple threads
# (Telegram updates can be processed in worker threads) do not corrupt files.
file_lock = threading.Lock()


def load_json(path, default):
    """Load JSON data from a file. Returns `default` if the file is missing
    or corrupted."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    return default


def save_json(path, data):
    """Save JSON data to a file in a thread-safe way."""
    with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------------
# In-memory data, loaded once at startup and kept in sync with the JSON
# files every time something changes.
# ------------------------------------------------------------------------

# users: { "<user_id>": {user_id, username, first_name, join_date,
#                         join_time, status} }
users = load_json(USERS_FILE, {})

# accounts: [ {username, password, link}, ... ]  -> stock of demo accounts
accounts = load_json(ACCOUNTS_FILE, [])

# settings: {price, button_name, qr_file_id}
settings = load_json(
    SETTINGS_FILE,
    {"price": "₹199", "button_name": "TASHAN GAME", "qr_file_id": ""},
)

# utrs: { "<utr_id>": {user_id, username, first_name, utr, date, time,
#                       status} }    status -> Pending / Approved / Rejected
utrs = load_json(UTRS_FILE, {})

# chat_map: { "<forwarded_message_id_in_admin_chat>": user_id }
# Used to route Admin replies back to the correct user.
chat_map = load_json(CHAT_MAP_FILE, {})


def save_users():
    save_json(USERS_FILE, users)


def save_accounts():
    save_json(ACCOUNTS_FILE, accounts)


def save_settings():
    save_json(SETTINGS_FILE, settings)


def save_utrs():
    save_json(UTRS_FILE, utrs)


def save_chat_map():
    save_json(CHAT_MAP_FILE, chat_map)


# ==============================================================================
# SECTION 3: RUNTIME STATE (NOT PERSISTED)
# ==============================================================================

# Per-user conversation state, e.g. "awaiting_utr" or "chat_mode"
user_state = {}

# Admin's current multi-step flow, e.g. "set_price", "set_account_username"
admin_state = {"step": None, "data": {}}


def reset_admin_state():
    """Clear any in-progress admin multi-step flow."""
    admin_state["step"] = None
    admin_state["data"] = {}


# ==============================================================================
# SECTION 4: HELPER / UTILITY FUNCTIONS
# ==============================================================================

def get_or_create_user(message):
    """Register a user on first contact, or refresh their cached
    username/first name on every subsequent contact."""
    uid = str(message.from_user.id)
    now = datetime.now()
    if uid not in users:
        users[uid] = {
            "user_id": message.from_user.id,
            "username": message.from_user.username or "N/A",
            "first_name": message.from_user.first_name or "N/A",
            "join_date": now.strftime("%Y-%m-%d"),
            "join_time": now.strftime("%H:%M:%S"),
            "status": "active",
        }
        save_users()
    else:
        changed = False
        new_username = message.from_user.username or "N/A"
        new_first_name = message.from_user.first_name or "N/A"
        if users[uid].get("username") != new_username:
            users[uid]["username"] = new_username
            changed = True
        if users[uid].get("first_name") != new_first_name:
            users[uid]["first_name"] = new_first_name
            changed = True
        if changed:
            save_users()
    return users[uid]


def is_blocked(user_id):
    """Return True if the given user is currently blocked."""
    record = users.get(str(user_id))
    return bool(record and record.get("status") == "blocked")


def new_utr_id():
    """Generate a unique ID for a UTR submission using a millisecond
    timestamp -- always increasing and unique enough for this use case."""
    return str(int(datetime.now().timestamp() * 1000))


def safe_send(chat_id, text, **kwargs):
    """Send a message but never let a failed delivery (e.g. user blocked
    the bot) crash the whole bot. Returns True/False for success."""
    try:
        bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception:
        return False


# ==============================================================================
# SECTION 5: KEYBOARDS
# ==============================================================================

ADMIN_MENU_BUTTONS = [
    "➕ Set QR Code",
    "📥 Set Account Credentials",
    "💰 Set Price",
    "📝 Pending UTRs",
    "✏️ Set Button Name",
    "👥 Users",
    "🚫 Block User",
    "✅ Unblock User",
    "📋 Blocked Users",
    "📢 Broadcast",
    "🔙 Exit",
]

CHAT_BUTTON_TEXT = "💬 Chat with Admin"


def main_menu_keyboard():
    """Build the regular user's reply keyboard. The Buy button label is
    always read live from `settings`, so it updates automatically the
    moment the Admin changes it."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(types.KeyboardButton(settings.get("button_name", "TASHAN GAME")))
    kb.add(types.KeyboardButton(CHAT_BUTTON_TEXT))
    return kb


def admin_menu_keyboard():
    """Build the Admin's reply keyboard with two buttons per row."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(*[types.KeyboardButton(t) for t in ADMIN_MENU_BUTTONS])
    return kb


def utr_action_keyboard(utr_id):
    """Inline keyboard attached to each pending UTR notification."""
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve:{utr_id}"),
        types.InlineKeyboardButton("⏳ Pending", callback_data=f"pending:{utr_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"reject:{utr_id}"),
    )
    return kb


# ==============================================================================
# SECTION 6: /start COMMAND (USER)
# ==============================================================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    get_or_create_user(message)

    if is_blocked(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 You have been blocked by Admin.")
        return

    # A fresh /start always cancels any half-finished flow (buy / chat).
    user_state.pop(message.from_user.id, None)

    welcome_text = (
        "👋 Welcome to *Tashan Game Store*!\n\n"
        "🎮 Get a premium DEMO Tashan Game account instantly after payment.\n"
        f"💰 Current Price: {settings.get('price', 'N/A')}\n\n"
        "Tap a button below to get started 👇"
    )
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ==============================================================================
# SECTION 7: /admin COMMAND (ADMIN ONLY)
# ==============================================================================

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    # Strict check: only the configured ADMIN_ID may ever see this panel.
    if message.from_user.id != ADMIN_ID:
        return  # Silently ignore - do not reveal the admin command exists.

    reset_admin_state()
    bot.send_message(
        message.chat.id,
        "🛠️ <b>Admin Panel</b>\n\nSelect an option below:",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


# ==============================================================================
# SECTION 8: MASTER TEXT MESSAGE DISPATCHER
# ==============================================================================
# IMPORTANT: This handler is registered AFTER the /start and /admin command
# handlers above, so those commands are always caught first. Everything that
# is not a recognised command lands here.

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id

    # ---------------------------------------------------------------
    # 1) Admin replying (via Telegram "Reply") to a forwarded chat
    #    message -> route the reply back to the correct user.
    # ---------------------------------------------------------------
    if user_id == ADMIN_ID and message.reply_to_message:
        handle_admin_chat_reply(message)
        return

    # ---------------------------------------------------------------
    # 2) Admin is mid multi-step flow (set price, set account, etc.)
    # ---------------------------------------------------------------
    if user_id == ADMIN_ID and admin_state["step"]:
        handle_admin_step(message)
        return

    # ---------------------------------------------------------------
    # 3) Admin pressed one of the Admin Panel buttons.
    # ---------------------------------------------------------------
    if user_id == ADMIN_ID and message.text in ADMIN_MENU_BUTTONS:
        handle_admin_menu(message)
        return

    # ---------------------------------------------------------------
    # 4) Anything else from the Admin while not in a flow -> ignore.
    # ---------------------------------------------------------------
    if user_id == ADMIN_ID:
        return

    # ---------------------------------------------------------------
    # 5) Regular user traffic.
    # ---------------------------------------------------------------
    handle_user_text(message)


# ==============================================================================
# SECTION 9: REGULAR USER TEXT HANDLING (BUY / CHAT)
# ==============================================================================

def handle_user_text(message):
    user_id = message.from_user.id
    get_or_create_user(message)

    # Blocked users cannot do anything at all.
    if is_blocked(user_id):
        bot.send_message(message.chat.id, "🚫 You have been blocked by Admin.")
        return

    text = message.text.strip()
    state = user_state.get(user_id)

    # ---------------- Waiting for a UTR number ----------------
    if state == "awaiting_utr":
        process_utr_submission(message)
        return

    # ---------------- In "chat with admin" mode ----------------
    if state == "chat_mode":
        forward_to_admin(message)
        return

    # ---------------- Buy button pressed ----------------
    if text == settings.get("button_name", "TASHAN GAME"):
        start_buy_flow(message)
        return

    # ---------------- Chat with Admin button pressed ----------------
    if text == CHAT_BUTTON_TEXT:
        user_state[user_id] = "chat_mode"
        bot.send_message(
            message.chat.id,
            "💬 You're now chatting with Admin.\n"
            "Type your message and it will be forwarded to Admin.\n"
            "Admin will reply here shortly.",
        )
        return

    # ---------------- Anything else ----------------
    bot.send_message(
        message.chat.id,
        "🤖 Please use the buttons below to continue.",
        reply_markup=main_menu_keyboard(),
    )


def start_buy_flow(message):
    """Show the QR code + price and ask the user for their UTR number."""
    user_id = message.from_user.id

    if not settings.get("qr_file_id"):
        bot.send_message(
            message.chat.id,
            "⚠️ QR Code is not set up yet. Please contact Admin via "
            f"'{CHAT_BUTTON_TEXT}'.",
        )
        return

    caption = (
        f"💰 <b>Price:</b> {settings.get('price', 'N/A')}\n\n"
        "1️⃣ Scan the QR Code above and complete the payment.\n"
        "2️⃣ Reply here with your <b>12-digit UTR Number</b>.\n\n"
        "📌 Make sure the UTR number is correct before submitting."
    )
    bot.send_photo(
        message.chat.id,
        settings["qr_file_id"],
        caption=caption,
        parse_mode="HTML",
    )
    user_state[user_id] = "awaiting_utr"


def process_utr_submission(message):
    """Validate and store a submitted UTR number, then notify Admin."""
    user_id = message.from_user.id
    utr_text = message.text.strip()

    if not (utr_text.isdigit() and len(utr_text) == 12):
        bot.send_message(
            message.chat.id,
            "❌ Invalid UTR Number.\n"
            "Please send a valid *12-digit* UTR Number.",
            parse_mode="Markdown",
        )
        return  # Stay in "awaiting_utr" state so the user can retry.

    user_record = users.get(str(user_id), {})
    utr_id = new_utr_id()
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

    bot.send_message(
        message.chat.id,
        "✅ Your UTR has been submitted!\n"
        "🕒 Please wait while Admin verifies your payment.",
    )

    # Notify Admin with action buttons.
    notify_admin_of_utr(utrs[utr_id])


def notify_admin_of_utr(record):
    text = format_utr_details(record)
    try:
        bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="HTML",
            reply_markup=utr_action_keyboard(record["utr_id"]),
        )
    except Exception:
        pass


def format_utr_details(record):
    return (
        "🆕 <b>New UTR Submission</b>\n\n"
        f"👤 User ID: <code>{record['user_id']}</code>\n"
        f"🔖 Username: @{record.get('username', 'N/A')}\n"
        f"📛 Name: {record.get('first_name', 'N/A')}\n"
        f"💳 UTR: <code>{record['utr']}</code>\n"
        f"📅 Date: {record['date']}\n"
        f"⏰ Time: {record['time']}\n"
        f"📊 Status: {record['status']}"
    )


def forward_to_admin(message):
    """Forward a user's chat message to Admin and remember which user it
    came from, so a later Admin reply can be routed back correctly."""
    try:
        forwarded = bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        chat_map[str(forwarded.message_id)] = message.from_user.id
        save_chat_map()
        bot.send_message(message.chat.id, "✅ Message sent to Admin.")
    except Exception:
        bot.send_message(
            message.chat.id, "⚠️ Could not deliver your message. Please try again."
        )


# ==============================================================================
# SECTION 10: PHOTO HANDLING (QR UPLOAD / CHAT PHOTOS)
# ==============================================================================

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id

    # Admin replying to a forwarded chat message with a photo.
    if user_id == ADMIN_ID and message.reply_to_message:
        handle_admin_chat_reply(message)
        return

    # Admin is uploading the new QR Code.
    if user_id == ADMIN_ID and admin_state["step"] == "set_qr":
        file_id = message.photo[-1].file_id  # highest resolution
        settings["qr_file_id"] = file_id
        save_settings()
        reset_admin_state()
        bot.send_message(
            message.chat.id,
            "✅ QR Code updated! All users will now see the latest QR Code.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    if user_id == ADMIN_ID:
        return  # Admin sent a random photo outside of any flow.

    # Regular user sending a photo while chatting with Admin.
    get_or_create_user(message)
    if is_blocked(user_id):
        bot.send_message(message.chat.id, "🚫 You have been blocked by Admin.")
        return

    if user_state.get(user_id) == "chat_mode":
        forward_to_admin(message)
    else:
        bot.send_message(
            message.chat.id,
            "🤖 Please use the buttons below to continue.",
            reply_markup=main_menu_keyboard(),
        )


# ==============================================================================
# SECTION 11: ADMIN CHAT REPLY ROUTING
# ==============================================================================

def handle_admin_chat_reply(message):
    """When Admin replies to a forwarded message, send that reply to the
    original user using copy_message (works for text, photos, etc.)."""
    replied_id = str(message.reply_to_message.message_id)
    target_user_id = chat_map.get(replied_id)

    if not target_user_id:
        bot.send_message(
            message.chat.id,
            "⚠️ Could not find the original user for this message.",
        )
        return

    try:
        bot.copy_message(target_user_id, message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "✅ Reply sent to user.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Failed to send reply to user.")


# ==============================================================================
# SECTION 12: ADMIN MENU BUTTON ACTIONS
# ==============================================================================

def handle_admin_menu(message):
    text = message.text

    if text == "➕ Set QR Code":
        admin_state["step"] = "set_qr"
        bot.send_message(message.chat.id, "📷 Please send the new QR Code image.")

    elif text == "📥 Set Account Credentials":
        admin_state["step"] = "set_account_username"
        admin_state["data"] = {}
        bot.send_message(message.chat.id, "👤 Send the account *Username*:", parse_mode="Markdown")

    elif text == "💰 Set Price":
        admin_state["step"] = "set_price"
        bot.send_message(
            message.chat.id,
            f"💰 Current price: {settings.get('price')}\nSend the new price:",
        )

    elif text == "📝 Pending UTRs":
        show_pending_utrs(message)

    elif text == "✏️ Set Button Name":
        admin_state["step"] = "set_button_name"
        bot.send_message(
            message.chat.id,
            f"✏️ Current button name: {settings.get('button_name')}\n"
            "Send the new button name:",
        )

    elif text == "👥 Users":
        show_user_stats(message)

    elif text == "🚫 Block User":
        admin_state["step"] = "block_user"
        bot.send_message(message.chat.id, "🚫 Send the User ID to block:")

    elif text == "✅ Unblock User":
        admin_state["step"] = "unblock_user"
        bot.send_message(message.chat.id, "✅ Send the User ID to unblock:")

    elif text == "📋 Blocked Users":
        show_blocked_users(message)

    elif text == "📢 Broadcast":
        admin_state["step"] = "broadcast"
        bot.send_message(message.chat.id, "📢 Send the message you want to broadcast to all users:")

    elif text == "🔙 Exit":
        reset_admin_state()
        bot.send_message(
            message.chat.id,
            "🔙 Admin Panel closed. Send /admin to reopen it.",
            reply_markup=types.ReplyKeyboardRemove(),
        )


# ==============================================================================
# SECTION 13: ADMIN MULTI-STEP FLOWS
# ==============================================================================

def handle_admin_step(message):
    step = admin_state["step"]
    text = message.text.strip()

    # ---------------- Set QR Code (expects a photo, not text) ----------------
    if step == "set_qr":
        bot.send_message(message.chat.id, "📷 Please send a *photo* for the QR Code.", parse_mode="Markdown")
        return

    # ---------------- Set Account Credentials (3-step flow) ----------------
    if step == "set_account_username":
        admin_state["data"]["username"] = text
        admin_state["step"] = "set_account_password"
        bot.send_message(message.chat.id, "🔑 Send the account *Password*:", parse_mode="Markdown")
        return

    if step == "set_account_password":
        admin_state["data"]["password"] = text
        admin_state["step"] = "set_account_link"
        bot.send_message(message.chat.id, "🔗 Send the *Login Link*:", parse_mode="Markdown")
        return

    if step == "set_account_link":
        admin_state["data"]["link"] = text
        accounts.append(
            {
                "username": admin_state["data"]["username"],
                "password": admin_state["data"]["password"],
                "link": admin_state["data"]["link"],
            }
        )
        save_accounts()
        reset_admin_state()
        bot.send_message(
            message.chat.id,
            f"✅ Account added successfully!\n📦 Total stock available: {len(accounts)}",
            reply_markup=admin_menu_keyboard(),
        )
        return

    # ---------------- Set Price ----------------
    if step == "set_price":
        settings["price"] = text
        save_settings()
        reset_admin_state()
        bot.send_message(
            message.chat.id,
            f"✅ Price updated to: {settings['price']}",
            reply_markup=admin_menu_keyboard(),
        )
        return

    # ---------------- Set Button Name ----------------
    if step == "set_button_name":
        if not text:
            bot.send_message(message.chat.id, "❌ Button name cannot be empty. Try again:")
            return
        settings["button_name"] = text
        save_settings()
        reset_admin_state()
        bot.send_message(
            message.chat.id,
            f"✅ Buy button renamed to: {text}\n"
            "The user keyboard will update automatically.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    # ---------------- Block User ----------------
    if step == "block_user":
        target_id = extract_user_id(text)
        if target_id is None:
            bot.send_message(message.chat.id, "❌ Invalid User ID. Send a numeric ID:")
            return
        uid_str = str(target_id)
        if uid_str not in users:
            bot.send_message(message.chat.id, "❌ User not found in database.")
        else:
            users[uid_str]["status"] = "blocked"
            save_users()
            bot.send_message(message.chat.id, f"🚫 User {target_id} has been blocked.")
            safe_send(target_id, "🚫 You have been blocked by Admin.")
        reset_admin_state()
        bot.send_message(message.chat.id, "Select an option below:", reply_markup=admin_menu_keyboard())
        return

    # ---------------- Unblock User ----------------
    if step == "unblock_user":
        target_id = extract_user_id(text)
        if target_id is None:
            bot.send_message(message.chat.id, "❌ Invalid User ID. Send a numeric ID:")
            return
        uid_str = str(target_id)
        if uid_str not in users:
            bot.send_message(message.chat.id, "❌ User not found in database.")
        else:
            users[uid_str]["status"] = "active"
            save_users()
            bot.send_message(message.chat.id, f"✅ User {target_id} has been unblocked.")
            safe_send(target_id, "✅ You have been unblocked by Admin. Send /start to continue.")
        reset_admin_state()
        bot.send_message(message.chat.id, "Select an option below:", reply_markup=admin_menu_keyboard())
        return

    # ---------------- Broadcast ----------------
    if step == "broadcast":
        run_broadcast(message)
        reset_admin_state()
        return


def extract_user_id(text):
    """Safely parse a numeric Telegram user ID from admin input."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    return None


# ==============================================================================
# SECTION 14: PENDING UTRs
# ==============================================================================

def show_pending_utrs(message):
    pending = [r for r in utrs.values() if r["status"] == "Pending"]

    if not pending:
        bot.send_message(message.chat.id, "📭 No pending UTRs right now.")
        return

    bot.send_message(message.chat.id, f"📝 You have {len(pending)} pending UTR(s):")
    for record in pending:
        bot.send_message(
            message.chat.id,
            format_utr_details(record),
            parse_mode="HTML",
            reply_markup=utr_action_keyboard(record["utr_id"]),
        )


# ==============================================================================
# SECTION 15: CALLBACK QUERIES (APPROVE / PENDING / REJECT)
# ==============================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    # Only the Admin may use these buttons.
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Unauthorized.")
        return

    try:
        action, utr_id = call.data.split(":", 1)
    except ValueError:
        bot.answer_callback_query(call.id)
        return

    record = utrs.get(utr_id)
    if not record:
        bot.answer_callback_query(call.id, "⚠️ This UTR no longer exists.")
        return

    if action == "approve":
        approve_utr(call, record)
    elif action == "pending":
        mark_utr_pending(call, record)
    elif action == "reject":
        reject_utr(call, record)
    else:
        bot.answer_callback_query(call.id)


def approve_utr(call, record):
    if record["status"] == "Approved":
        bot.answer_callback_query(call.id, "Already approved.")
        return

    if not accounts:
        bot.answer_callback_query(call.id, "⚠️ No stock available!", show_alert=True)
        safe_send(ADMIN_ID, "⚠️ No accounts in stock! Please add accounts via 'Set Account Credentials'.")
        return

    account = accounts.pop(0)
    save_accounts()

    record["status"] = "Approved"
    save_utrs()

    account_text = (
        "✅ <b>Payment Approved!</b>\n\n"
        "Here is your demo account:\n"
        f"👤 Username: <code>{account['username']}</code>\n"
        f"🔑 Password: <code>{account['password']}</code>\n"
        f"🔗 Login Link: {account['link']}\n\n"
        "🎮 Enjoy your game!"
    )
    delivered = safe_send(record["user_id"], account_text, parse_mode="HTML")

    try:
        bot.edit_message_text(
            format_utr_details(record) + ("\n\n✅ Account delivered." if delivered else "\n\n⚠️ Could not deliver (user blocked bot)."),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
        )
    except Exception:
        pass

    bot.answer_callback_query(call.id, "✅ Approved & account sent.")


def mark_utr_pending(call, record):
    record["status"] = "Pending"
    save_utrs()

    pending_text = (
        "🕒 Your UTR is Pending.\n"
        "Please wait.\n"
        "If you have any problem, reply in chat.\n"
        "Reply Time: Within 24 Hours."
    )
    safe_send(record["user_id"], pending_text)

    try:
        bot.edit_message_text(
            format_utr_details(record) + "\n\n🕒 Reminder sent to user.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=utr_action_keyboard(record["utr_id"]),
        )
    except Exception:
        pass

    bot.answer_callback_query(call.id, "🕒 Marked as Pending.")


def reject_utr(call, record):
    record["status"] = "Rejected"
    save_utrs()

    reject_text = "❌ Payment Not Found.\nPlease check your payment and submit again."
    safe_send(record["user_id"], reject_text)

    try:
        bot.edit_message_text(
            format_utr_details(record) + "\n\n❌ User notified of rejection.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
        )
    except Exception:
        pass

    bot.answer_callback_query(call.id, "❌ Rejected.")


# ==============================================================================
# SECTION 16: USERS / STATS
# ==============================================================================

def show_user_stats(message):
    total_users = len(users)
    today_str = date.today().strftime("%Y-%m-%d")
    today_joined = sum(1 for u in users.values() if u.get("join_date") == today_str)
    blocked_count = sum(1 for u in users.values() if u.get("status") == "blocked")

    approved_count = sum(1 for r in utrs.values() if r["status"] == "Approved")
    pending_count = sum(1 for r in utrs.values() if r["status"] == "Pending")
    rejected_count = sum(1 for r in utrs.values() if r["status"] == "Rejected")

    text = (
        "👥 <b>User Statistics</b>\n\n"
        f"👤 Total Users: {total_users}\n"
        f"🆕 Today's Joined Users: {today_joined}\n"
        f"🚫 Blocked Users: {blocked_count}\n\n"
        f"✅ Approved Payments: {approved_count}\n"
        f"⏳ Pending Payments: {pending_count}\n"
        f"❌ Rejected Payments: {rejected_count}\n\n"
        f"📦 Accounts in Stock: {len(accounts)}"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")


# ==============================================================================
# SECTION 17: BLOCK / UNBLOCK / BLOCKED USERS LIST
# ==============================================================================

def show_blocked_users(message):
    blocked = [u for u in users.values() if u.get("status") == "blocked"]

    if not blocked:
        bot.send_message(message.chat.id, "📋 No blocked users.")
        return

    lines = [f"📋 <b>Blocked Users ({len(blocked)})</b>\n"]
    for u in blocked:
        lines.append(
            f"🆔 <code>{u['user_id']}</code> | @{u.get('username', 'N/A')} | {u.get('first_name', 'N/A')}"
        )
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")


# ==============================================================================
# SECTION 18: BROADCAST
# ==============================================================================

def run_broadcast(message):
    broadcast_text = message.text
    success = 0
    failed = 0

    bot.send_message(message.chat.id, "📢 Broadcasting... please wait.")

    for uid_str, u in users.items():
        if u.get("status") == "blocked":
            continue  # Ignore blocked users.
        if int(uid_str) == ADMIN_ID:
            continue
        if safe_send(int(uid_str), broadcast_text):
            success += 1
        else:
            failed += 1

    report = (
        "📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Total Success: {success}\n"
        f"❌ Total Failed: {failed}"
    )
    bot.send_message(message.chat.id, report, parse_mode="HTML", reply_markup=admin_menu_keyboard())


# ==============================================================================
# SECTION 19: ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    print("🤖 Tashan Game Bot is starting...")
    print(f"📦 Loaded {len(users)} users, {len(accounts)} accounts in stock, {len(utrs)} UTR records.")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
