import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask, request, jsonify
from threading import Thread
from datetime import datetime
import base64
from io import BytesIO

# ================= CONFIG =================
BOT_TOKEN = '8626144455:AAE4OmHD5UW_hQdcTL9ZgeieW0gLHcFMjvk'
ADMIN_ID = 1924277344
MONGO_URI = 'mongodb+srv://hrkunalkumar:<db_password>@cluster0.u2jgbk5.mongodb.net/?appName=Cluster0'
UPI_ID = 'vipseller@nyes'
DEFAULT_JOIN_LINK = 'https://t.me/+lHsXAECaA6ZkZWJl'  # CHANGE THIS

# Initialize
bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['telegram_miniapp']
payments_db = db['payments']
plans_db = db['plans']

# Default plans
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

# Insert default plans if empty
if plans_db.count_documents({}) == 0:
    for p in DEFAULT_PLANS:
        plans_db.insert_one(p)

# ================= FLASK APP =================
flask_app = Flask(__name__)

@flask_app.route('/plans', methods=['GET'])
def get_plans():
    plans = list(plans_db.find({}, {'_id': 0}))
    return jsonify(plans)

@flask_app.route('/submit_payment', methods=['POST'])
def submit_payment():
    try:
        data = request.json
        user_id = data.get('user_id')
        plan_name = data.get('plan_name')
        price = data.get('price')
        screenshot_base64 = data.get('screenshot')
        
        # Save to database
        payment = {
            'user_id': user_id,
            'plan_name': plan_name,
            'price': price,
            'status': 'pending',
            'created_at': datetime.utcnow()
        }
        result = payments_db.insert_one(payment)
        payment_id = str(result.inserted_id)
        
        # Save screenshot as file or just store (simplified)
        # Notify admin
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{payment_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{payment_id}")
        )
        
        bot.send_message(
            ADMIN_ID,
            f"🔔 New Payment\nUser: {user_id}\nPlan: {plan_name}\nAmount: ₹{price}",
            reply_markup=markup
        )
        
        # Send screenshot if provided
        if screenshot_base64:
            img_data = base64.b64decode(screenshot_base64)
            bot.send_photo(ADMIN_ID, photo=BytesIO(img_data))
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)

# ================= BOT COMMANDS =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id, 
        "Welcome to VIP Store!\nUse the button below to open store.",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🛒 Open Store", web_app={"url": "https://your-vercel-url.vercel.app"})
        ))

@bot.message_handler(commands=['plans'])
def list_plans(message):
    if message.from_user.id != ADMIN_ID:
        return
    plans = list(plans_db.find({}, {'_id': 0}))
    text = "📋 Plans:\n\n"
    for p in plans:
        text += f"• {p['name']} - ₹{p['price']}\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=['addplan'])
def add_plan(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        msg = message.text.split(maxsplit=1)[1]
        name, price = msg.rsplit(',', 1)
        price = int(price.strip())
        name = name.strip()
        plans_db.insert_one({"name": name, "price": price})
        bot.send_message(ADMIN_ID, f"✅ Added: {name} - ₹{price}")
    except:
        bot.send_message(ADMIN_ID, "Usage: /addplan Plan Name, 199")

@bot.message_handler(commands=['delplan'])
def del_plan(message):
    if message.from_user.id != ADMIN_ID:
        return
    plans = list(plans_db.find({}))
    if not plans:
        bot.send_message(ADMIN_ID, "No plans")
        return
    markup = InlineKeyboardMarkup()
    for p in plans:
        markup.add(InlineKeyboardButton(p['name'], callback_data=f"del_{p['name']}"))
    bot.send_message(ADMIN_ID, "Select plan to delete:", reply_markup=markup)

@bot.message_handler(commands=['setlink'])
def set_link(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        link = message.text.split(maxsplit=1)[1]
        global DEFAULT_JOIN_LINK
        DEFAULT_JOIN_LINK = link
        bot.send_message(ADMIN_ID, f"✅ Link updated: {link}")
    except:
        bot.send_message(ADMIN_ID, "Usage: /setlink https://t.me/joinchat/xyz")

@bot.message_handler(commands=['pending'])
def pending(message):
    if message.from_user.id != ADMIN_ID:
        return
    pending_list = list(payments_db.find({"status": "pending"}))
    if not pending_list:
        bot.send_message(ADMIN_ID, "No pending payments")
        return
    for p in pending_list:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{p['_id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{p['_id']}")
        )
        bot.send_message(ADMIN_ID, f"User: {p['user_id']}\nPlan: {p['plan_name']}\n₹{p['price']}", reply_markup=markup)

# ================= CALLBACKS =================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data.startswith('approve_'):
        payment_id = call.data.split('_')[1]
        payments_db.update_one({"_id": payment_id}, {"$set": {"status": "approved"}})
        bot.send_message(call.message.chat.id, f"✅ Approved")
        bot.answer_callback_query(call.id, "Approved")
        
    elif call.data.startswith('reject_'):
        payment_id = call.data.split('_')[1]
        payments_db.update_one({"_id": payment_id}, {"$set": {"status": "rejected"}})
        bot.send_message(call.message.chat.id, f"❌ Rejected")
        bot.answer_callback_query(call.id, "Rejected")
        
    elif call.data.startswith('del_'):
        plan_name = call.data.split('_', 1)[1]
        plans_db.delete_one({"name": plan_name})
        bot.edit_message_text(f"✅ Deleted {plan_name}", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Deleted")

# ================= MAIN =================
if __name__ == '__main__':
    # Start Flask in background
    Thread(target=run_flask, daemon=True).start()
    # Start bot
    print("Bot started successfully!")
    bot.infinity_polling(timeout=10)
