import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask, request, jsonify
from threading import Thread
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)

# ================= CONFIG =================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8626144455:AAE4OmHD5UW_hQdcTL9ZgeieW0gLHcFMjvk')  # Or use env var
ADMIN_ID = int(os.getenv('ADMIN_ID', '1924277344'))
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://hrkunalkumar:YOUR_PASSWORD@cluster0.u2jgbk5.mongodb.net/?retryWrites=true&w=majority')
UPI_ID = os.getenv('UPI_ID', 'vipseller@nyes')
DEFAULT_JOIN_LINK = os.getenv('DEFAULT_JOIN_LINK', 'https://t.me/your_channel')  # Change to your group invite link

# Initialize bot and DB
bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['telegram_miniapp']
payments_db = db['payments']
plans_db = db['plans']

# Default plans (you can also add/remove via /addplan)
DEFAULT_PLANS = [
    {"name": "🔥 10 Groups", "price": 199},
    {"name": "⚡ 20 Groups", "price": 249},
    {"name": "✨ 30 Groups", "price": 299},
    {"name": "💎 50 Groups", "price": 349},
    {"name": "👑 100 Groups", "price": 399},
    {"name": "🏆 150 Groups", "price": 449},
    {"name": "🦁 200 Groups", "price": 499},
    {"name": "❇️ All in one pack", "price": 999},
]

# Initialize plans in DB if empty
if plans_db.count_documents({}) == 0:
    for p in DEFAULT_PLANS:
        plans_db.insert_one(p)

# ================= FLASK API FOR MINI APP =================
flask_app = Flask(__name__)

@flask_app.route('/plans', methods=['GET'])
def get_plans():
    """Return list of plans as JSON"""
    plans = list(plans_db.find({}, {'_id': 0}))
    return jsonify(plans)

@flask_app.route('/submit_payment', methods=['POST'])
def submit_payment():
    """Mini app sends user_id, plan_name, price, screenshot (base64)"""
    data = request.json
    user_id = data.get('user_id')
    plan_name = data.get('plan_name')
    price = data.get('price')
    screenshot_base64 = data.get('screenshot')  # image as base64 string

    if not user_id or not plan_name or not screenshot_base64:
        return jsonify({'error': 'Missing data'}), 400

    # Save pending payment in DB
    payment = {
        'user_id': user_id,
        'plan_name': plan_name,
        'price': price,
        'screenshot': screenshot_base64,  # store base64 temporarily
        'status': 'pending',
        'created_at': datetime.utcnow()
    }
    result = payments_db.insert_one(payment)
    payment_id = str(result.inserted_id)

    # Notify admin with inline buttons
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{payment_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{payment_id}")
    )
    bot.send_message(
        ADMIN_ID,
        f"🔔 *New Payment Proof*\n\n"
        f"User ID: `{user_id}`\n"
        f"Plan: {plan_name}\n"
        f"Amount: ₹{price}\n"
        f"Payment ID: `{payment_id}`",
        parse_mode="Markdown",
        reply_markup=markup
    )
    # Also send the screenshot image (decode from base64)
    import base64
    from io import BytesIO
    img_data = base64.b64decode(screenshot_base64)
    bot.send_photo(ADMIN_ID, photo=BytesIO(img_data), caption="Screenshot received.")

    return jsonify({'status': 'ok', 'payment_id': payment_id})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port, debug=False)

# ================= BOT COMMANDS & CALLBACKS =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(ADMIN_ID,
            "👑 *Admin Panel*\n\n"
            "/plans - View all plans\n"
            "/addplan - Add a new plan\n"
            "/delplan - Delete a plan\n"
            "/setlink <url> - Set default join link\n"
            "/pending - Show pending payments",
            parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id,
            "Welcome! Please open the Mini App to purchase plans.",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🚀 Open Store", web_app={"url": "https://your-miniapp-url.vercel.app"})
            ))

@bot.message_handler(commands=['plans'])
def list_plans_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    plans = list(plans_db.find({}, {'_id': 0}))
    if not plans:
        bot.send_message(ADMIN_ID, "No plans found. Use /addplan")
        return
    text = "📋 *Current Plans*\n\n"
    for p in plans:
        text += f"• {p['name']} – ₹{p['price']}\n"
    bot.send_message(ADMIN_ID, text, parse_mode="Markdown")

@bot.message_handler(commands=['addplan'])
def add_plan_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    msg = bot.send_message(ADMIN_ID, "Send plan details in format: `Name, Price`\nExample: `Gold Pack, 499`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_add_plan)

def process_add_plan(message):
    try:
        name, price = message.text.split(',')
        price = int(price.strip())
        name = name.strip()
        plans_db.insert_one({"name": name, "price": price})
        bot.send_message(ADMIN_ID, f"✅ Plan {name} added!")
    except:
        bot.send_message(ADMIN_ID, "❌ Invalid format. Use: `Name, Price`")

@bot.message_handler(commands=['delplan'])
def del_plan_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    plans = list(plans_db.find({}, {'_id': 0}))
    if not plans:
        bot.send_message(ADMIN_ID, "No plans to delete.")
        return
    markup = InlineKeyboardMarkup()
    for p in plans:
        markup.add(InlineKeyboardButton(f"{p['name']} - ₹{p['price']}", callback_data=f"del_{p['name']}"))
    bot.send_message(ADMIN_ID, "Select plan to delete:", reply_markup=markup)

@bot.message_handler(commands=['setlink'])
def set_link_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(ADMIN_ID, "Usage: `/setlink https://t.me/joinchat/xyz`", parse_mode="Markdown")
        return
    link = args[1]
    db.settings.update_one({"_id": "join_link"}, {"$set": {"url": link}}, upsert=True)
    bot.send_message(ADMIN_ID, f"✅ Default join link updated to {link}")

@bot.message_handler(commands=['pending'])
def pending_payments(message):
    if message.from_user.id != ADMIN_ID: return
    pending = list(payments_db.find({"status": "pending"}))
    if not pending:
        bot.send_message(ADMIN_ID, "No pending payments.")
        return
    for p in pending:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{p['_id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{p['_id']}")
        )
        bot.send_message(ADMIN_ID, f"User: `{p['user_id']}`\nPlan: {p['plan_name']}\nAmount: ₹{p['price']}", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_payment(call):
    payment_id = call.data.split('_')[1]
    payment = payments_db.find_one({"_id": payment_id})
    if not payment or payment['status'] != 'pending':
        bot.answer_callback_query(call.id, "Payment already processed.")
        return
    # Update status
    payments_db.update_one({"_id": payment_id}, {"$set": {"status": "approved"}})
    # Get join link
    settings = db.settings.find_one({"_id": "join_link"})
    join_link = settings['url'] if settings else DEFAULT_JOIN_LINK
    # Send link to user
    bot.send_message(payment['user_id'], f"🎉 *Payment Approved!*\n\nYour join link: {join_link}\n\nThank you for purchasing!", parse_mode="Markdown")
    bot.edit_message_text(f"✅ Approved payment {payment_id}", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Approved and link sent.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_payment(call):
    payment_id = call.data.split('_')[1]
    payment = payments_db.find_one({"_id": payment_id})
    if not payment or payment['status'] != 'pending':
        bot.answer_callback_query(call.id, "Payment already processed.")
        return
    payments_db.update_one({"_id": payment_id}, {"$set": {"status": "rejected"}})
    bot.send_message(payment['user_id'], "❌ Your payment was rejected. Please contact admin.")
    bot.edit_message_text(f"❌ Rejected payment {payment_id}", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Rejected.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_plan(call):
    plan_name = call.data.split('_', 1)[1]
    plans_db.delete_one({"name": plan_name})
    bot.edit_message_text(f"🗑 Deleted {plan_name}", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Plan deleted.")

# ================= RUN BOTH =================
if __name__ == '__main__':
    # Start Flask server in background
    Thread(target=run_flask).start()
    # Start bot polling
    bot.remove_webhook()
    print("Bot and API server running...")
    bot.infinity_polling(timeout=20)
