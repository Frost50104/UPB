import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config  # Файл с переменными
import help_message

from telebot import types


# Создание бота
bot = telebot.TeleBot(config.TOKEN)

@bot.message_handler(commands=['start'])
def handle_command_start(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text='Привет! Я бот для постановки задач',
    )

@bot.message_handler(commands=['help'])
def handle_command_help(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text=help_message.help_msg,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['my_id'])
def handle_command_my_id(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text=f'ID пользователя <b>{message.from_user.first_name}</b> ({message.from_user.username}):\n <pre>{message.from_user.id}</pre>',
        parse_mode='HTML',
    )

@bot.message_handler(commands=['chat_id'])
def handle_command_chat_id(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text=f'ID чата:\n <pre>{message.chat.id}</pre>',
        parse_mode='HTML',
    )


# --- Функция для экранирования MarkdownV2 ---
def escape_markdown_v2(text):
    """Экранирует специальные символы для MarkdownV2"""
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in special_chars else char for char in text)

# Хранение данных о задачах и фото
task_data = {}

# --- 1. Команда /new_task (только для админа) ---
@bot.message_handler(commands=['new_task'])
def new_task(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "✏ Введите текст задачи:")
    bot.register_next_step_handler(message, send_task_to_performers)

def send_task_to_performers(message):
    task_text = message.text
    for performer in config.performers_list:
        bot.send_message(performer, f"📌 *Новое задание:*\n{task_text}", parse_mode="Markdown")
        bot.send_message(performer, "📷 Отправьте фото выполнения.")
        task_data[performer] = {"task_text": task_text}  # Сохраняем задачу для исполнителя

# --- 2. Получение фото от исполнителя ---
@bot.message_handler(content_types=['photo'])
def receive_photo(message):
    user_id = message.from_user.id

    if user_id not in config.performers_list:
        bot.send_message(message.chat.id, "⛔ Вы не исполнитель.")
        return

    photo = message.photo[-1].file_id  # Берем фото лучшего качества
    task_text = task_data.get(user_id, {}).get("task_text", "Задача без описания")

    # Экранируем Markdown вручную
    safe_task_text = escape_markdown_v2(task_text)

    # Проверяем, есть ли у пользователя username и экранируем его
    username = message.from_user.username or f"ID: {user_id}"
    safe_username = escape_markdown_v2(username)

    # Создаем Inline-кнопки для админа
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✔ Принять", callback_data=f"accept_{message.message_id}_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{message.message_id}_{user_id}")
    )

    # Отправляем фото в контрольный чат
    sent_message = bot.send_photo(config.control_chat_id, photo,
                                  caption=f"📝 *Задача:* {safe_task_text}\n👤 {safe_username}",
                                  parse_mode="MarkdownV2", reply_markup=keyboard)

    # Сохраняем ID сообщения
    task_data[user_id]["last_photo"] = {"message_id": sent_message.message_id, "chat_id": config.control_chat_id}

# --- 3. Обработка нажатий в контрольном чате ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_", "reject_")))
def process_verification(call):
    admin_id = call.from_user.id
    if admin_id != config.ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Вы не можете одобрять или отклонять фото.")
        return

    action, msg_id, user_id = call.data.split("_")
    msg_id = int(msg_id)
    user_id = int(user_id)

    # Получаем данные о сообщении с фото
    if user_id in task_data and "last_photo" in task_data[user_id]:
        msg_id = task_data[user_id]["last_photo"]["message_id"]
        chat_id = task_data[user_id]["last_photo"]["chat_id"]

        try:
            # Убираем кнопки под фото
            bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
        except telebot.apihelper.ApiTelegramException:
            bot.answer_callback_query(call.id, "⚠ Ошибка: сообщение уже изменено или удалено.")
            return

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
    print("✅ Бот запущен!")
    bot.polling(none_stop=True)