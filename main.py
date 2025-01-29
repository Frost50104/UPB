import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config  # Файл с переменными
import help_message

from telebot import types
from io import StringIO
from datetime import datetime
import requests


# Создание бота
bot = telebot.TeleBot(config.TOKEN)

@bot.message_handler(commands=['start'])
def handle_command_start(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text='Привет! Я бот для постановки задач',
    )

# Хранение задач (чтобы знать, чье фото чей)
task_data = {}

# --- 1. Команда /new_task (только для админа) ---
@bot.message_handler(commands=['new_task'])
def new_task(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "Введите текст задачи:")
    bot.register_next_step_handler(message, send_task_to_performers)

def send_task_to_performers(message):
    task_text = message.text
    for performer in config.performers_list:
        bot.send_message(performer, f"📌 *Новое задание:*\n{task_text}", parse_mode="Markdown")
        bot.send_message(performer, "Отправьте фото выполнения.")
        task_data[performer] = {"task_text": task_text}  # Сохраняем задачу для исполнителя

# --- 2. Получение фото от исполнителя ---
@bot.message_handler(content_types=['photo'])
def receive_photo(message):
    user_id = message.from_user.id

    if user_id not in config.performers_list:
        bot.send_message(message.chat.id, "Вы не исполнитель.")
        return

    photo = message.photo[-1].file_id  # Берем фото лучшего качества
    task_text = task_data.get(user_id, {}).get("task_text", "Задача без описания")

    # Создаем кнопки для админа
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✔ Принять", callback_data=f"accept_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
    )

    # Отправляем фото в контрольный чат
    bot.send_photo(config.control_chat_id, photo, caption=f"📝 *Задача:* {task_text}", parse_mode="Markdown", reply_markup=keyboard)

    # Сохраняем фото в task_data
    task_data[user_id]["last_photo"] = photo

# --- 3. Обработка нажатий в контрольном чате ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_", "reject_")))
def process_verification(call):
    admin_id = call.from_user.id
    if admin_id != config.ADMIN_ID:
        bot.answer_callback_query(call.id, "Вы не можете одобрять или отклонять фото.")
        return

    action, user_id = call.data.split("_")
    user_id = int(user_id)

    if action == "accept":
        bot.send_message(user_id, "✅ *Работа выполнена! Спасибо!*", parse_mode="Markdown")
        bot.answer_callback_query(call.id, "Фото принято!")
    elif action == "reject":
        bot.send_message(user_id, "⚠ Фото не принято. Переделайте и отправьте заново!")
        bot.answer_callback_query(call.id, "Фото отклонено!")
        request_new_photo(user_id)

# --- 4. Запрос нового фото у исполнителя ---
def request_new_photo(user_id):
    bot.send_message(user_id, "📷 Отправьте новое фото выполнения.")

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен!")
    bot.polling(none_stop=True)
