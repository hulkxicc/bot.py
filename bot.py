import telebot
import sqlite3
import threading
import os
from flask import Flask

# --- 1. BOT SOZLAMALARI ---
TOKEN = '8009128157:AAEZ3LgwEooM9QB7F4xzpFDl9XapORh7WgE'
ADMIN_ID = '7356340513'
LOYIHA_HAVOLASI = "https://new.openbudget.uz/uz/initiative-budget/active-initiatives/55/74807204-f411-47f9-b7c0-e1fd650f9be2"

bot = telebot.TeleBot(TOKEN)

# --- 2. MA'LUMOTLAR BAZASI ---
conn = sqlite3.connect('openbudget.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS votes (phone TEXT PRIMARY KEY, user_id INTEGER, status TEXT)''')
conn.commit()
user_states = {}

# --- 3. BOT MANTIQI (Oldingi kod bilan bir xil) ---
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    text = (
        "Salom! Ovoz berish botiga xush kelibsiz.\n\n"
        "🔄 Siz xohlagancha turli xil telefon raqamlari orqali ovoz berishingiz mumkin. "
        "Lekin har bir raqamdan faqat 1 marta ovoz qabul qilinadi.\n\n"
        "👉 Ovoz bermoqchi bo'lgan telefon raqamingizni kiriting (Masalan: +998901234567):"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown")
    user_states[chat_id] = {'step': 'waiting_phone'}

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_phone')
def handle_phone(message):
    chat_id = message.chat.id
    phone = message.text.strip()
    
    cursor.execute("SELECT * FROM votes WHERE phone=?", (phone,))
    if cursor.fetchone():
        bot.send_message(chat_id, "❌ Bu telefon raqamdan allaqachon ovoz berilgan!\nBoshqa yangi raqam kiritish uchun /start ni bosing.")
        user_states.pop(chat_id, None)
    else:
        user_states[chat_id] = {'step': 'waiting_photo_1', 'phone': phone}
        text = f"✅ Raqam qabul qilindi: {phone}\n\n1️⃣ Quyidagi havola orqali saytga kiring va ovoz bering:\n{LOYIHA_HAVOLASI}\n\n2️⃣ Telefon raqam kiritilgan sahifaning 1-skrinshotini yuboring:"
        bot.send_message(chat_id, text)

@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    chat_id = message.chat.id
    state_data = user_states.get(chat_id)
    if not state_data:
        return bot.send_message(chat_id, "Iltimos, avval /start buyrug'ini bosing va telefon raqamingizni kiriting.")

    step = state_data.get('step')
    phone = state_data.get('phone')

    if step == 'waiting_photo_1':
        state_data['photo_1'] = message.message_id
        state_data['step'] = 'waiting_photo_2'
        bot.send_message(chat_id, "✅ 1-skrinshot qabul qilindi!\n\nEndi ovoz muvaffaqiyatli berilganini ko'rsatuvchi 2-skrinshotni yuboring:")

    elif step == 'waiting_photo_2':
        photo_1 = state_data.get('photo_1')
        photo_2 = message.message_id

        try:
            cursor.execute("INSERT INTO votes (phone, user_id, status) VALUES (?, ?, ?)", (phone, chat_id, 'completed'))
            conn.commit()
        except sqlite3.IntegrityError:
            bot.send_message(chat_id, "❌ Xatolik: Bu raqam allaqachon ro'yxatdan o'tgan!")
            return user_states.pop(chat_id, None)

        username = f"@{message.from_user.username}" if message.from_user.username else "Username yo'q"
        bot.send_message(ADMIN_ID, f"🔔 Yangi ovoz tasdiqlash uchun keldi!\n📱 Raqam: {phone}\n👤 Telegram: {username}")
        bot.forward_message(ADMIN_ID, chat_id, photo_1)
        bot.forward_message(ADMIN_ID, chat_id, photo_2)

        bot.send_message(chat_id, "🎉 Tabriklaymiz! Skrinshotlar va raqamingiz muvaffaqiyatli qabul qilindi.\nYana boshqa raqam bilan ovoz berish uchun /start ni bosing.")
        user_states.pop(chat_id, None)

# --- 4. RENDER UCHUN SOXTA VEB-SERVER VA ISHGA TUSHIRISH ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot muvaffaqiyatli ishlayapti! (Render serverida)"

def run_bot():
    bot.polling(none_stop=True)
if __name__ == '__main__':
    # Telegram botni alohida orqa fonda ishga tushiramiz
    threading.Thread(target=run_bot).start()
    # Veb-serverni ishga tushiramiz
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
