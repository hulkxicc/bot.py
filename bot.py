import telebot
import sqlite3
import threading
import os
from flask import Flask
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ================= 1. BOT SOZLAMALARI =================
TOKEN = '8009128157:AAEZ3LgwEooM9QB7F4xzpFDl9XapORh7WgE'
ADMIN_ID = '7356340513'
LOYIHA_HAVOLASI = "https://openbudget.uz/boards/initiatives/initiative/55/74807204-f411-47f9-b7c0-e1fd650f9be2"

# Pul hisob-kitobi uchun sozlamalar (Kerak bo'lganda shu yerdan o'zgartirasiz)
TOLOV_SUMMASI = 30000  # Matematik hisoblash uchun raqam
TOLOV_MATNI = "30 000 so'm" # Ekranda ko'rsatish uchun matn

bot = telebot.TeleBot(TOKEN)

# ================= 2. MA'LUMOTLAR BAZASI =================
conn = sqlite3.connect('openbudget.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS votes (phone TEXT PRIMARY KEY, user_id INTEGER, status TEXT)''')
conn.commit()
user_states = {}

# ================= 3. ASOSIY MENYU TUGMALARI =================
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📥 Ovoz berish"))
    markup.row(KeyboardButton("💳 Hamyon"), KeyboardButton("📱 Ovoz bergan raqamlarim"))
    return markup

# ================= 4. BOT MANTIQI =================
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    user_states.pop(chat_id, None) # Xotirani tozalash
    
    bot.send_message(
        chat_id, 
        "👋 Salom! Ochiq byudjet ovoz yig'ish botiga xush kelibsiz.\n\n"
        f"💰 Har bir tasdiqlangan ovoz uchun to'lov: {TOLOV_MATNI}\n"
        "💳 _Pulni yechib olish uchun kamida 2 ta ovoz yig'ishingiz kerak._\n\n"
        "👇 Pastdagi menyudan kerakli bo'limni tanlang:", 
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# --------- MENYUDAGI TUGMALAR ---------
@bot.message_handler(func=lambda message: message.text in ["📥 Ovoz berish", "💳 Hamyon", "📱 Ovoz bergan raqamlarim"])
def handle_menu(message):
    chat_id = message.chat.id
    text = message.text
    user_states.pop(chat_id, None) 
    
    # 1. OVOZ BERISH BO'LIMI
    if text == "📥 Ovoz berish":
        msg = f"👉 Ovoz bermoqchi bo'lgan telefon raqamingizni kiriting (Masalan: +998901234567):"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        user_states[chat_id] = {'step': 'waiting_phone'}
        
    # 2. HAMYON BO'LIMI
    elif text == "💳 Hamyon":
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='completed'", (chat_id,))
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='paid'", (chat_id,))
        paid_count = cursor.fetchone()[0]
        
        total_money = count * TOLOV_SUMMASI
        pul_formati = f"{total_money:,}".replace(',', ' ') 
        
        msg = (
            f"💳 Sizning hamyoningiz:\n\n"
            f"✅ Tasdiqlangan (yangi) ovozlar: {count} ta\n"
            f"💰 Hamyondagi jami pul: {pul_formati} so'm\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️\n"
            f"💸 Avval to'lab berilgan ovozlar: {paid_count} ta"
        )
        
        if count >= 2:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💸 Pulni yechib olish", callback_data="withdraw"))
            bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            msg += "\n\n*(Pulni kartaga o'tkazish uchun hamyoningizda kamida 2 ta ovoz bo'lishi kerak)*"
            bot.send_message(chat_id, msg, parse_mode="Markdown")
            
    # 3. RAQAMLAR BO'LIMI
    elif text == "📱 Ovoz bergan raqamlarim":
        cursor.execute("SELECT phone, status FROM votes WHERE user_id=?", (chat_id,))
        numbers = cursor.fetchall()
if not numbers:
            bot.send_message(chat_id, "Siz hali hech qanday raqamdan ovoz bermagansiz.")
else:
    num_list = ""
    for n in numbers:
                holat = "To'langan ✅" if n[1] == 'paid' else "Hamyonda 🕒"
                num_list += f"📞 {n[0]} - _{holat}_\n"
                
bot.send_message(chat_id, f"Siz kiritgan raqamlar ro'yxati:\n\n{num_list}", parse_mode="Markdown")

# --------- PUL YECHISH JARAYONI ---------
@bot.callback_query_handler(func=lambda call: call.data == 'withdraw')
def handle_withdraw(call):
    chat_id = call.message.chat.id
    
    cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='completed'", (chat_id,))
    count = cursor.fetchone()[0]
    
    if count >= 2:
        bot.delete_message(chat_id, call.message.message_id) 
        bot.send_message(chat_id, "💳 Iltimos, pulni tashlab berishimiz uchun plastik karta raqamingizni yozib yuboring:")
        user_states[chat_id] = {'step': 'waiting_withdraw_card', 'count': count}
    else:
        bot.answer_callback_query(call.id, "Sizda yetarli ovoz yo'q!", show_alert=True)
        
    # Tugma bosilgandagi "yuklanmoqda" animatsiyasini to'xtatish
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_withdraw_card')
def handle_withdraw_card(message):
    chat_id = message.chat.id
    card_info = message.text
    count = user_states[chat_id].get('count')
    
    total_money = count * TOLOV_SUMMASI
    pul_formati = f"{total_money:,}".replace(',', ' ')
    
    # Bazani yangilaymiz (pullarni to'langan statusiga o'tkazamiz, shunda hamyon 0 ga tushadi)
    cursor.execute("UPDATE votes SET status='paid' WHERE user_id=? AND status='completed'", (chat_id,))
    conn.commit()
    
    # Adminga to'liq xabar yuborish
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {chat_id}"
    admin_msg = (
        f"💸 YANGI TO'LOV SO'ROVI KELDI!\n\n"
        f"👤 Foydalanuvchi: {username}\n"
        f"✅ Tasdiqlangan ovozlar: {count} ta\n"
        f"💰 To'lanishi kerak: {pul_formati} so'm\n"
        f"💳 Karta raqami: {card_info}\n\n"
        f"Iltimos, pulni o'tkazing."
    )
    bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    
    # Foydalanuvchiga javob qaytarish
bot.send_message(
        chat_id, 
        "✅ So'rovingiz adminga yuborildi! Tez orada pul kartangizga tushirib beriladi.\n\n"
        "🔄 _Sizning hamyoningiz balansi Nol (0) holatiga tushirildi._ Yana ovoz yig'ishda davom etishingiz mumkin!", 
        parse_mode="Markdown"
    )
user_states.pop(chat_id, None)

# --------- OVOZ BERISH VA SKRINSHOTLAR ---------
@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_phone')
def handle_phone(message):
    chat_id = message.chat.id
    phone = message.text.strip()
    
    cursor.execute("SELECT * FROM votes WHERE phone=?", (phone,))
    if cursor.fetchone():
        bot.send_message(chat_id, "❌ Bu telefon raqamdan allaqachon ovoz berilgan!\nBoshqa yangi raqam kiritish uchun menyudan '📥 Ovoz berish' ni bosing.")
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
        return bot.send_message(chat_id, "Iltimos, avval menyudan '📥 Ovoz berish' tugmasini bosing va telefon raqamingizni kiriting.")

    step = state_data.get('step')
    phone = state_data.get('phone')
if step == 'waiting_photo_1':
        state_data['photo_1'] = message.message_id
        state_data['step'] = 'waiting_photo_2'
        bot.send_message(chat_id, "✅ 1-skrinshot qabul qilindi!\n\nEndi ovoz muvaffaqiyatli berilganini ko'rsatuvchi 2-skrinshotni yuboring:")

elif step == 'waiting_photo_2':
        state_data['photo_2'] = message.message_id
        state_data['step'] = 'waiting_photo_3'
        bot.send_message(chat_id, "✅ 2-skrinshot qabul qilindi!\n\nVa nihoyat, telefoningizga Ochiq byudjetdan kelgan SMS xabarni (Tabriklaymiz, ovozingiz qabul qilindi) skrinshot qilib, 3-rasm sifatida yuboring:")

elif step == 'waiting_photo_3':
        photo_1 = state_data.get('photo_1')
        photo_2 = state_data.get('photo_2')
        photo_3 = message.message_id

try:
            cursor.execute("INSERT INTO votes (phone, user_id, status) VALUES (?, ?, ?)", (phone, chat_id, 'completed'))
            conn.commit()
except sqlite3.IntegrityError:
            bot.send_message(chat_id, "❌ Xatolik: Bu raqam allaqachon ro'yxatdan o'tgan!")
return user_states.pop(chat_id, None)

        username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {chat_id}"
        admin_text = (
            f"🔔 Yangi ovoz tasdiqlash uchun keldi!\n"
            f"📱 Raqam: {phone}\n"
            f"👤 Telegram: {username}\n"
            f"*(Bu ovoz foydalanuvchining hamyoniga tushdi)*"
        )
        bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        bot.forward_message(ADMIN_ID, chat_id, photo_1)
        bot.forward_message(ADMIN_ID, chat_id, photo_2)
        bot.forward_message(ADMIN_ID, chat_id, photo_3)

        bot.send_message(
            chat_id, 
            f"🎉 Tabriklaymiz! Barcha 3 ta skrinshot qabul qilindi va pul Hamyoningizga tushdi.\n\n"
            f"Menyudan '💳 Hamyon' bo'limiga o'tib, balansingizni ko'rishingiz mumkin.",
            parse_mode="Markdown"
        )
        user_states.pop(chat_id, None)

# ================= 5. RENDER UCHUN SOXTA VEB-SERVER =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot muvaffaqiyatli ishlayapti! (Render serverida)"

def run_bot():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
