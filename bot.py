import telebot
import sqlite3
import threading
import os
from flask import Flask
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ================= 1. BOT SOZLAMALARI =================
TOKEN = '8009128157:AAE4i3zL0QU9s5YRF7hBr-NCdFc0ZHCK4_s'
ADMIN_ID = '7356340513'
LOYIHA_HAVOLASI = "https://openbudget.uz/boards/initiatives/initiative/55/74807204-f411-47f9-b7c0-e1fd650f9be2" 

# Pul hisob-kitobi uchun sozlamalar
TOLOV_SUMMASI = 30000  
TOLOV_MATNI = "30 000 so'm" 

bot = telebot.TeleBot(TOKEN)

# ================= 2. MA'LUMOTLAR BAZASI =================
conn = sqlite3.connect('openbudget.db', check_same_thread=False)
cursor = conn.cursor()
# Statuslar: 'pending' (tekshiruvda), 'completed' (tasdiqlangan), 'paid' (to'langan), 'rejected' (rad etilgan)
cursor.execute('''CREATE TABLE IF NOT EXISTS votes (
                    phone TEXT PRIMARY KEY, 
                    user_id INTEGER, 
                    status TEXT
                )''')
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
    
    # 1. OVOZ BERish BO'LIMI (Cheksiz raqam kiritish imkoniyati)
    if text == "📥 Ovoz berish":
        msg = f"👉 Ovoz bermoqchi bo'lgan **telefon raqamingizni kiriting** (Masalan: +998901234567):"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        user_states[chat_id] = {'step': 'waiting_phone'}
        
    # 2. HAMYON BO'LIMI
    elif text == "💳 Hamyon":
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='completed'", (chat_id,))
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='pending'", (chat_id,))
        pending_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id=? AND status='paid'", (chat_id,))
        paid_count = cursor.fetchone()[0]
        
        total_money = count * TOLOV_SUMMASI
        pul_formati = f"{total_money:,}".replace(',', ' ') 
        
        msg = (
            f"💳 **Sizning hamyoningiz:**\n\n"
            f"✅ Tasdiqlangan ovozlar: **{count} ta**\n"
            f"⏳ Tekshiruvdagi ovozlar: **{pending_count} ta**\n"
            f"💰 Hamyondagi yechib olish mumkin pul: **{pul_formati} so'm**\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️\n"
            f"💸 Avval to'lab berilgan ovozlar: {paid_count} ta"
        )
        
        if count >= 2:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💸 Pulni yechib olish", callback_data="withdraw"))
            bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            msg += "\n\n*(Pulni kartaga o'tkazish uchun hamyoningizda kamida 2 ta tasdiqlangan ovoz bo'lishi kerak)*"
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
                if n[1] == 'paid':
                    holat = "To'langan ✅"
                elif n[1] == 'completed':
                    holat = "Tasdiqlangan ✅"
                elif n[1] == 'rejected':
                    holat = "Rad etilgan ❌"
                else:
                    holat = "Tekshiruvda 🕒 (Admin 1 soat ichida tekshiradi)"
                num_list += f"📞 {n[0]} - _{holat}_\n"
                
            bot.send_message(chat_id, f"**Siz kiritgan raqamlar ro'yxati:**\n\n{num_list}", parse_mode="Markdown")

# --------- PUL YECHISH JARAYONI (Nolga aylanishi) ---------
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
        bot.answer_callback_query(call.id, "Sizda yetarli tasdiqlangan ovoz yo'q!", show_alert=True)
        
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_withdraw_card')
def handle_withdraw_card(message):
    chat_id = message.chat.id
    card_info = message.text
    count = user_states[chat_id].get('count')
    
    total_money = count * TOLOV_SUMMASI
    pul_formati = f"{total_money:,}".replace(',', ' ')
    
    # TO'LOV QILINGANDAN KEYIN HAMYONDAGI PUL NOLGA AYLANISHI (status 'paid' ga o'tadi)
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
        "🔄 _Hamyoningizdagi balans muvaffaqiyatli Nol (0) ga aylantirildi._", 
        parse_mode="Markdown"
    )
    user_states.pop(chat_id, None)

# --------- TELEFON VA 2 TA SKRINSHOTNI QABUL QILISH ---------
@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get('step') == 'waiting_phone')
def handle_phone(message):
    chat_id = message.chat.id
    phone = message.text.strip()
    
    cursor.execute("SELECT * FROM votes WHERE phone=?", (phone,))
    if cursor.fetchone():
        bot.send_message(chat_id, "❌ **Bu telefon raqam allaqachon ishlatilgan!**\nBoshqa raqam kiritish uchun menyudan '📥 Ovoz berish' ni bosing.")
        user_states.pop(chat_id, None)
    else:
        user_states[chat_id] = {'step': 'waiting_photo_1', 'phone': phone}
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 Ochiq byudjetni ochish", web_app=WebAppInfo(url=LOYIHA_HAVOLASI)))
        
        text = (
            f"✅ Raqam qabul qilindi: {phone}\n\n"
            f"1️⃣ Pastdagi tugmani bosing va saytda ovoz bering:\n"
            f"2️⃣ Saytda chiqadigan **'Muvaffaqiyatli. Hurmatli fuqaro ovozingiz tasdiqlanish jarayonida...'** degan yozuv bor 1-skrinshotni yuboring:"
        )
        bot.send_message(chat_id, text, reply_markup=markup)

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
        bot.send_message(
            chat_id, 
            "✅ 1-skrinshot qabul qilindi!\n\n"
            "⏳ **Admin ovozingizni 1 soat ichida tekshiradi.**\n\n"
            "📱 Endi oradan vaqt o'tgach telefoningizga SMS orqali keladigan **'Tabriklaymiz, hurmatli fuqaro, ovozingiz qabul qilindi'** degan 2-skrinshotni yuboring:"
        )

    elif step == 'waiting_photo_2':
        photo_1 = state_data.get('photo_1')
        photo_2 = message.message_id

        try:
            # Bazaga 'pending' (tekshiruvda) holatida saqlaymiz
            cursor.execute("INSERT INTO votes (phone, user_id, status) VALUES (?, ?, ?)", (phone, chat_id, 'pending'))
            conn.commit()
        except sqlite3.IntegrityError:
            bot.send_message(chat_id, "❌ Xatolik: Bu raqam allaqachon ro'yxatdan o'tgan!")
            return user_states.pop(chat_id, None)

        username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {chat_id}"
        
        # Admin uchun tasdiqlash tugmalari
        admin_markup = InlineKeyboardMarkup()
        admin_markup.row(
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{phone}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{phone}")
        )

        admin_text = (
            f"🔔 **Yangi ovoz tekshiruvga keldi!**\n"
            f"📱 Raqam: `{phone}`\n"
            f"👤 Foydalanuvchi: {username} (ID: {chat_id})\n\n"
            f"📸 Quyida foydalanuvchi yuborgan 2 ta skrinshot:"
        )
        bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        bot.forward_message(ADMIN_ID, chat_id, photo_1)
        bot.forward_message(ADMIN_ID, chat_id, photo_2, reply_markup=admin_markup)

        bot.send_message(
            chat_id, 
            f"🎉 **Barcha skrinshotlar qabul qilindi!**\n\n"
            f"🕒 Ovozingiz admin tomonidan tekshirilmoqda. Tasdiqlangach hamyoningizga pul qo'shiladi.\n\n"
            f"📥 *Yana boshqa raqamdan ovoz berish uchun '📥 Ovoz berish' tugmasini bosishingiz mumkin.*",
            parse_mode="Markdown"
        )
        user_states.pop(chat_id, None)

# --------- ADMIN UCHUN TASDIQLASH VA RAD ETISH TUGMALARI ---------
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve:') or call.data.startswith('reject:'))
def handle_admin_action(call):
    action, phone = call.data.split(':')
    chat_id = call.message.chat.id

    # Bazadan ushbu raqam egasining user_id sini topamiz
    cursor.execute("SELECT user_id FROM votes WHERE phone=?", (phone,))
    res = cursor.fetchone()
    
    if not res:
        return bot.answer_callback_query(call.id, "Bu raqam bazada topilmadi!", show_alert=True)
    
    target_user_id = res[0]

    if action == 'approve':
        cursor.execute("UPDATE votes SET status='completed' WHERE phone=?", (phone,))
        conn.commit()
        
        bot.answer_callback_query(call.id, "Ovoz tasdiqlandi va foydalanuvchiga pul qo'shildi!")
        bot.edit_message_caption(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            caption=f"✅ **TASDIQLANDI**\n📱 Raqam: `{phone}`", 
            parse_mode="Markdown"
        )
        # Foydalanuvchiga xabar berish
        bot.send_message(
            target_user_id, 
            f"🎉 **Tabriklaymiz!**\n📱 `{phone}` raqamdan bergan ovozingiz admin tomonidan tasdiqlandi va hamyoningizga **{TOLOV_MATNI}** qo'shildi! ✅", 
            parse_mode="Markdown"
        )

    elif action == 'reject':
        cursor.execute("UPDATE votes SET status='rejected' WHERE phone=?", (phone,))
        conn.commit()
        
        bot.answer_callback_query(call.id, "Ovoz rad etildi.")
        bot.edit_message_caption(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            caption=f"❌ **RAD ETILDI**\n📱 Raqam: `{phone}`", 
            parse_mode="Markdown"
        )
        # Foydalanuvchiga xabar berish
        bot.send_message(
            target_user_id, 
            f"❌ **Afsuski...**\n📱 `{phone}` raqamdan yuborgan skrinshotlaringiz rad etildi (talabga javob bermadi).", 
            parse_mode="Markdown"
        )

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
