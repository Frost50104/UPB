import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types
import config  # Файл с переменными: TOKEN, ADMIN_ID, performers_list, control_chat_id, work_time, task_group_1
import help_message
import schedule
import time
import threading

# Создание бота
bot = telebot.TeleBot(config.TOKEN)


# ========= Стандартные команды =========
@bot.message_handler(commands=['start'])
def handle_command_start(message: types.Message):
    bot.send_message(message.chat.id, "Привет! Я бот для постановки задач")


@bot.message_handler(commands=['help'])
def handle_command_help(message: types.Message):
    bot.send_message(message.chat.id, help_message.help_msg, parse_mode="HTML")


@bot.message_handler(commands=['my_id'])
def handle_command_my_id(message: types.Message):
    bot.send_message(
        message.chat.id,
        f'ID пользователя <b>{message.from_user.first_name}</b> ({message.from_user.username}):\n<pre>{message.from_user.id}</pre>',
        parse_mode="HTML"
    )


@bot.message_handler(commands=['chat_id'])
def handle_command_chat_id(message: types.Message):
    bot.send_message(
        message.chat.id,
        f'ID чата:\n<pre>{message.chat.id}</pre>',
        parse_mode="HTML"
    )


# ========= Функция экранирования MarkdownV2 =========
def escape_markdown_v2(text):
    """Экранирует специальные символы для MarkdownV2"""
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in special_chars else char for char in text)


# ========= Хранение данных о фото =========
# Ключом будет ID сообщения в контрольном чате (control_message_id)
# Значение — словарь с данными:
#    "user_id": ID исполнителя,
#    "user_message_id": ID сообщения с фото, отправленного исполнителем,
#    "control_chat_id": ID контрольного чата,
#    "task_text": текст задачи (на тот момент)
task_data = {}


# ========= Ручная постановка задачи (админом) =========
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
        # Для ручного задания можно сохранить текст задачи для данного исполнителя,
        # если понадобится (здесь мы не формируем запись в task_data до получения фото)


# ========= Автоматическая отправка задач по расписанию =========
def scheduled_send_tasks():
    tasks_message = "\n".join(config.task_group_1)
    for performer in config.performers_list:
        bot.send_message(performer, f"📌 *Новые задачи:*\n{tasks_message}", parse_mode="Markdown")
        bot.send_message(performer, "📷 Отправьте фото выполнения.")
        # При автоматической рассылке мы можем сохранить текст задачи, если понадобится.
        # Здесь можно, например, сохранить в отдельном хранилище для исполнителя.


def schedule_jobs():
    for work_time in config.work_time:
        schedule.every().day.at(work_time).do(scheduled_send_tasks)
    while True:
        schedule.run_pending()
        time.sleep(1)


schedule_thread = threading.Thread(target=schedule_jobs)
schedule_thread.daemon = True
schedule_thread.start()


# ========= Получение фото от исполнителя =========
@bot.message_handler(content_types=['photo'])
def receive_photo(message):
    user_id = message.from_user.id
    if user_id not in config.performers_list:
        bot.send_message(message.chat.id, "⛔ Вы не исполнитель.")
        return
    photo = message.photo[-1].file_id  # Берем фото лучшего качества

    # Попытка получить текст задачи для данного исполнителя (если он был сохранён ранее)
    # Если нет — подставляем значение по умолчанию.
    task_text = ""
    # Если в task_data по ключу user_id (при ручной постановке) сохранён task_text, можно использовать его.
    # Здесь для упрощения автоматической рассылки мы не храним task_text в task_data, а используем "Задача без описания".

    safe_task_text = escape_markdown_v2(task_text)
    username = message.from_user.username or f"ID: {user_id}"
    safe_username = escape_markdown_v2(username)

    # Отправляем каждое фото в контрольный чат.
    # Сначала отправляем фото без inline-кнопок, чтобы получить ID отправленного сообщения.
    sent_message = bot.send_photo(
        config.control_chat_id,
        photo,
        caption=f"👤 {safe_username}",
        parse_mode="MarkdownV2"
    )
    # Формируем inline-клавиатуру с кнопками "+" и "–", используя ID сообщения в контрольном чате.
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("+", callback_data=f"accept_{sent_message.message_id}_{user_id}"),
        InlineKeyboardButton("–", callback_data=f"reject_{sent_message.message_id}_{user_id}")
    )
    # Редактируем отправленное сообщение, добавляя inline-кнопки.
    bot.edit_message_reply_markup(chat_id=config.control_chat_id, message_id=sent_message.message_id,
                                  reply_markup=keyboard)

    # Сохраняем данные по этому фото в task_data (ключ — ID сообщения в контрольном чате).
    task_data[sent_message.message_id] = {
        "user_id": user_id,
        "user_message_id": message.message_id,  # ID фото в чате исполнителя
        "control_chat_id": config.control_chat_id,
        "task_text": task_text
    }


# ========= Обработка нажатий в контрольном чате =========
@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_", "reject_")))
def process_verification(call):
    admin_id = call.from_user.id
    if admin_id != config.ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Вы не можете одобрять или отклонять фото.")
        return
    action, control_msg_id, user_id = call.data.split("_")
    control_msg_id = int(control_msg_id)
    user_id = int(user_id)

    # Получаем сохранённые данные по фото из task_data.
    if control_msg_id not in task_data:
        bot.answer_callback_query(call.id, "⚠ Данные не найдены.")
        return
    stored = task_data[control_msg_id]

    # Убираем inline-кнопки под фото в контрольном чате.
    try:
        bot.edit_message_reply_markup(chat_id=stored["control_chat_id"], message_id=control_msg_id, reply_markup=None)
    except telebot.apihelper.ApiTelegramException:
        bot.answer_callback_query(call.id, "⚠ Ошибка: сообщение уже изменено или удалено.")
        return

    if action == "accept":
        # Если админ нажал "+", отправляем ответное сообщение пользователю,
        # отвечая на конкретное фото (используем user_message_id) с текстом "Фото принято! Спасибо"
        bot.send_message(
            user_id,
            "Фото принято! Спасибо",
            reply_to_message_id=stored["user_message_id"],
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Фото принято!")
        # Удаляем запись о данном фото из task_data
        del task_data[control_msg_id]
    elif action == "reject":
        # Если админ нажал "–", отправляем сообщение с текстом "Фото не принято. Переделайте!"
        bot.send_message(
            user_id,
            "Фото не принято. Переделайте!",
            reply_to_message_id=stored["user_message_id"],
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Фото отклонено!")
        # Удаляем запись о данном фото из task_data
        del task_data[control_msg_id]
        # Запрашиваем у исполнителя новое фото.
        request_new_photo(user_id)


# ========= Запрос нового фото у исполнителя =========
def request_new_photo(user_id):
    bot.send_message(user_id, "📷 Отправьте новое фото выполнения.")


# ========= Запуск бота =========
if __name__ == "__main__":
    print("✅ Бот запущен!")
    bot.polling(none_stop=True)