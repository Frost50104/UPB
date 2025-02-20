import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types
import config  # Файл с переменными
import help_message
import schedule
import time
import threading

from config import ADMIN_ID

# Создание бота
bot = telebot.TeleBot(config.TOKEN)

# ========= Стандартные команды =========
@bot.message_handler(commands=['start'])
def handle_command_start(message: types.Message):
    bot.send_message(message.chat.id, "Привет! Я бот для постановки задач")
    bot.send_message(
        message.chat.id,
        f'ID пользователя <b>{message.from_user.first_name}</b> ({message.from_user.username}):\n<pre>{message.from_user.id}</pre>',
        parse_mode="HTML"
    )

@bot.message_handler(commands=['help'])
def handle_command_help(message: types.Message):
    bot.send_message(message.chat.id, help_message.help_msg, parse_mode="HTML")

@bot.message_handler(commands=['admins'])
def handle_command_admins(message: types.Message):
    admin_list = []
    for admin_id in config.ADMIN_ID:
        user = bot.get_chat(admin_id)
        username = user.username or f"ID: {admin_id}"
        admin_list.append(f"@{username}")
    bot.send_message(
        chat_id=message.chat.id,
        text=f"Админы:\n" + "\n".join(admin_list),
    )


@bot.message_handler(commands=['bot_users'])
def handle_bot_users(message):
    groups = {
        "Группа 1": config.performers_list_1,
        "Группа 2": config.performers_list_2,
        "Группа 3": config.performers_list_3,
    }

    response = []

    for group_name, users in groups.items():
        user_list = []
        for user_id in users:
            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else f"ID: {user_id}"
                user_list.append(f"👤 {username}")
            except Exception as e:
                print(f"Ошибка получения информации о пользователе {user_id}: {e}")

        if user_list:
            response.append(f"{group_name}:\n" + "\n".join(user_list))
        else:
            response.append(f"{group_name}:\n Нет пользователей")

    bot.send_message(message.chat.id, "\n\n".join(response), parse_mode="HTML")



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

# ========= Хранение данных о задачах и фото =========
task_data = {}

# ========= Ручная постановка задачи (админом) =========
@bot.message_handler(commands=['new_task'])
def new_task(message):
    if not message.from_user.id in config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return
    bot.send_message(message.chat.id, "✏ Введите текст задачи:")
    bot.register_next_step_handler(message, send_task_to_performers)

def send_task_to_performers(message):
    task_text = message.text
    # Рассылаем задание всем исполнителям, указанным в контрольной панели
    for performers, tasks_text in config.control_panel.items():
        # Если админ вручную задаёт задание, можно игнорировать текст из control_panel
        # или дополнительно отправлять задание всем из всех групп.
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Новое задание:*\n{task_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")
                task_data[performer] = {"task_text": task_text}
            except telebot.apihelper.ApiTelegramException as e:
                # Если бот заблокирован пользователем, пропускаем его
                if "bot was blocked by the user" in str(e):
                    print(f"Бот заблокирован пользователем {performer}.")
                else:
                    print(f"Ошибка при отправке задания пользователю {performer}: {e}")

# ========= Автоматическая отправка задач по расписанию =========
def send_control_panel_tasks():
    # Для каждого набора исполнителей в контрольной панели отправляем им соответствующие задачи
    for performers, tasks_text in config.control_panel.items():
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Ваши задачи:*\n{tasks_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")
                task_data[performer] = {"task_text": tasks_text}
            except telebot.apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in str(e):
                    print(f"Бот заблокирован пользователем {performer}.")
                else:
                    print(f"Ошибка при отправке сообщения пользователю {performer}: {e}")

def schedule_jobs():
    # Для каждого времени из work_time планируем автоматическую рассылку
    for work_time in config.work_time:
        schedule.every().day.at(work_time).do(send_control_panel_tasks)
    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск планировщика в отдельном потоке
schedule_thread = threading.Thread(target=schedule_jobs)
schedule_thread.daemon = True
schedule_thread.start()

# ========= Получение фото от исполнителя =========
@bot.message_handler(content_types=['photo'])
def receive_photo(message):
    user_id = message.from_user.id
    if user_id not in sum(config.control_panel.keys(), ()):  # Проверка, что исполнитель из одной из групп
        bot.send_message(message.chat.id, "⛔ Вы не числитесь в контрольной панели.")
        return
    photo = message.photo[-1].file_id
    # Попытаемся получить текст задачи для исполнителя; если нет — используем заглушку.
    task_text = task_data.get(user_id, {}).get("task_text", "Задача без описания")
    safe_task_text = escape_markdown_v2(task_text)
    username = message.from_user.username or f"ID: {user_id}"
    safe_username = escape_markdown_v2(username)
    # Отправляем фото в контрольный чат без inline-кнопок для получения ID сообщения
    sent_message = bot.send_photo(
        config.control_chat_id,
        photo,
        caption=f"📝 *Задача:* {safe_task_text}\n👤 {safe_username}",
        parse_mode="MarkdownV2"
    )
    # Формируем inline-клавиатуру с кнопками "+" и "–"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("+", callback_data=f"accept_{sent_message.message_id}_{user_id}"),
        InlineKeyboardButton("–", callback_data=f"reject_{sent_message.message_id}_{user_id}")
    )
    # Редактируем сообщение, добавляя клавиатуру
    bot.edit_message_reply_markup(chat_id=config.control_chat_id, message_id=sent_message.message_id, reply_markup=keyboard)
    # Сохраняем данные о сообщении в task_data (ключ – ID сообщения в контрольном чате)
    task_data[sent_message.message_id] = {
        "user_id": user_id,
        "user_message_id": message.message_id,
        "control_chat_id": config.control_chat_id,
        "task_text": task_text
    }

# ========= Обработка нажатий в контрольном чате =========
@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_", "reject_")))
def process_verification(call):
    admin_id = call.from_user.id
    if not admin_id in config.ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Вы не можете одобрять или отклонять фото.")
        return
    action, control_msg_id, user_id = call.data.split("_")
    control_msg_id = int(control_msg_id)
    user_id = int(user_id)
    if control_msg_id not in task_data:
        bot.answer_callback_query(call.id, "⚠ Данные не найдены.")
        return
    stored = task_data[control_msg_id]
    try:
        bot.edit_message_reply_markup(chat_id=stored["control_chat_id"], message_id=control_msg_id, reply_markup=None)
    except telebot.apihelper.ApiTelegramException:
        bot.answer_callback_query(call.id, "⚠ Ошибка: сообщение уже изменено или удалено.")
        return
    if action == "accept":
        bot.send_message(
            user_id,
            "Фото принято! Спасибо",
            reply_to_message_id=stored["user_message_id"],
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Фото принято!")
        del task_data[control_msg_id]
    elif action == "reject":
        bot.send_message(
            user_id,
            "Фото не принято. Переделайте!",
            reply_to_message_id=stored["user_message_id"],
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Фото отклонено!")
        del task_data[control_msg_id]
        request_new_photo(user_id)

# ========= Запрос нового фото =========
def request_new_photo(user_id):
    bot.send_message(user_id, "📷 Отправьте новое фото выполнения.")

# ========= Запуск бота =========
if __name__ == "__main__":
    print("✅ Бот запущен!")
    bot.polling(none_stop=True)