import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types
import config  # Файл с переменными
import help_message
import schedule
import time
import threading
import ast
import re
import importlib

from config import ADMIN_ID

# Создание бота
bot = telebot.TeleBot(config.TOKEN)
# переключить бота с тестового на основного

# ========= Функция экранирования MarkdownV2 =========
def escape_markdown_v2(text):
    """Экранирует специальные символы для MarkdownV2"""
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in special_chars else char for char in text)

# ========= Проверка прав администратора =========
def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    return user_id in config.ADMIN_ID

# ========= Стандартные команды =========


# ========= Команда /delete_admin =========
@bot.message_handler(commands=['delete_admin'])
def handle_delete_admin(message):
    """Запускает процесс удаления администратора."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для удаления администраторов.")
        return

    # Создаем inline-кнопки
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_delete_admin"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete_admin")
    )

    bot.send_message(message.chat.id, "Хотите удалить администратора?", reply_markup=keyboard)

# ========= Обработка выбора "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_delete_admin", "cancel_delete_admin"])
def process_delete_admin_choice(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять администраторов.")
        return

    if call.data == "confirm_delete_admin":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

        # Перезагружаем config.py перед выводом списка администраторов
        importlib.reload(config)

        # Получаем список текущих администраторов
        keyboard = InlineKeyboardMarkup()
        admin_list = []

        for admin_id in config.ADMIN_ID:
            if admin_id == call.from_user.id:
                continue  # Администратор не может удалить сам себя!

            try:
                user = bot.get_chat(admin_id)
                username = f"@{user.username}" if user.username else "Без username"
                first_name = user.first_name or "Без имени"
                display_text = f"👤 {first_name} ({username}) - {admin_id}"
            except telebot.apihelper.ApiTelegramException:
                display_text = f"❌ ID: {admin_id} (не найден)"

            admin_list.append(display_text)
            keyboard.add(InlineKeyboardButton(display_text, callback_data=f"delete_admin_{admin_id}"))

        if not admin_list:
            bot.send_message(call.message.chat.id, "⚠ Нет доступных администраторов для удаления.", parse_mode="HTML")
            return

        bot.send_message(
            call.message.chat.id,
            "Выберите администратора для удаления:\n" + "\n".join(admin_list),
            parse_mode="HTML",
            reply_markup=keyboard
        )

    elif call.data == "cancel_delete_admin":
        bot.edit_message_text("❌ Удаление администратора отменено.", call.message.chat.id, call.message.message_id)

# ========= Удаление администратора и обновление config.py =========
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_admin_"))
def process_admin_deletion(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять администраторов.")
        return

    try:
        admin_id_to_delete = int(call.data.split("_")[2])
    except ValueError:
        bot.send_message(call.message.chat.id, "⚠ Ошибка: некорректный формат ID администратора.", parse_mode="HTML")
        return

    if admin_id_to_delete == call.from_user.id:
        bot.send_message(call.message.chat.id, "⛔ Вы не можете удалить сами себя!", parse_mode="HTML")
        return

    # Удаляем inline-кнопки после выбора администратора
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Удаление администратора из ADMIN_ID
    for i, line in enumerate(config_content):
        if line.strip().startswith("ADMIN_ID"):
            match = re.search(r"\[(.*?)\]", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                existing_ids_list = []

            if admin_id_to_delete not in existing_ids_list:
                bot.send_message(call.message.chat.id, f"⚠ Администратор с ID {admin_id_to_delete} не найден.", parse_mode="HTML")
                return

            # Удаляем администратора из списка
            existing_ids_list.remove(admin_id_to_delete)
            updated_ids = ", ".join(map(str, existing_ids_list))

            # Обновляем строку в файле
            config_content[i] = f"ADMIN_ID = [{updated_ids}]\n"
            break
    else:
        bot.send_message(call.message.chat.id, "⚠ Ошибка: не найден список администраторов в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(config_content)

    # Перезагружаем config.py, чтобы бот сразу видел изменения
    importlib.reload(config)

    bot.send_message(
        call.message.chat.id,
        f"✅ Администратор с ID <code>{admin_id_to_delete}</code> удален.",
        parse_mode="HTML"
    )

# ========= Команда /add_admin =========
@bot.message_handler(commands=['add_admin'])
def handle_add_admin(message):
    """Запускает процесс добавления нового администратора."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для добавления администраторов.")
        return

    # Перезагружаем config.py перед выводом списка администраторов
    importlib.reload(config)

    # Получаем список текущих администраторов
    admin_list = []
    for admin_id in config.ADMIN_ID:
        try:
            user = bot.get_chat(admin_id)
            username = f"@{user.username}" if user.username else f"ID: {admin_id}"
        except telebot.apihelper.ApiTelegramException:
            username = f"ID: {admin_id} (❌ не найден)"

        admin_list.append(f"👤 {username}")

    admin_text = "\n".join(admin_list) if admin_list else "❌ Нет администраторов."

    # Создаем inline-кнопки
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_add_admin"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_add_admin")
    )

    # Отправляем сообщение с HTML-разметкой
    bot.send_message(
        message.chat.id,
        f"🔹 <b>Список администраторов:</b>\n{admin_text}\n\n"
        "Хотите добавить нового администратора?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ========= Обработка выбора "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_add_admin", "cancel_add_admin"])
def process_add_admin_choice(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять администраторов.")
        return

    if call.data == "confirm_add_admin":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(call.message.chat.id, "✏ Укажите ID нового администратора:")
        bot.register_next_step_handler(call.message, process_admin_id)

    elif call.data == "cancel_add_admin":
        bot.edit_message_text("❌ Добавление администратора отменено.", call.message.chat.id, call.message.message_id)


# ========= Обработка ID нового администратора =========
def process_admin_id(message):
    """Добавляет новый ID администратора в список `ADMIN_ID` в `config.py`."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять администраторов.")
        return

    try:
        new_admin_id = int(message.text.strip())  # Преобразуем введенное значение в int
    except ValueError:
        bot.send_message(message.chat.id, "⚠ Ошибка: ID должен быть числом. Попробуйте снова с командой /add_admin.")
        return

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Проверяем, есть ли уже этот админ в списке
    if new_admin_id in config.ADMIN_ID:
        bot.send_message(
            message.chat.id,
            f"⚠ Пользователь с ID <code>{new_admin_id}</code> уже является администратором.",
            parse_mode="HTML"
        )
        return

    # Обновляем `ADMIN_ID`
    for i, line in enumerate(config_content):
        if line.strip().startswith("ADMIN_ID"):
            match = re.search(r"\[(.*?)\]", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                existing_ids_list = []

            # Добавляем нового администратора
            existing_ids_list.append(new_admin_id)
            updated_ids = ", ".join(map(str, existing_ids_list))

            # Обновляем строку в файле
            config_content[i] = f"ADMIN_ID = [{updated_ids}]\n"
            break
    else:
        bot.send_message(message.chat.id, "⚠ Ошибка: не найден список администраторов в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(config_content)

    # Перезагружаем config.py, чтобы бот сразу видел изменения
    importlib.reload(config)

    bot.send_message(
        message.chat.id,
        f"✅ Пользователь с ID <code>{new_admin_id}</code> добавлен в список администраторов.",
        parse_mode="HTML"
    )


# ========= Команда /auto_send =========
@bot.message_handler(commands=['auto_send'])
def handle_auto_send(message):
    """Показывает текущий статус автоматической рассылки задач и позволяет изменить его."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять статус автоматической рассылки.")
        return

    # Перезагружаем config.py перед выводом информации
    importlib.reload(config)

    current_status = "✅ Включена" if config.status_work_time == "on" else "⛔ Выключена"
    schedule_list = "\n".join(config.work_time)

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="change_auto_send"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_auto_send")
    )

    bot.send_message(
        message.chat.id,
        f"📅 *Текущее расписание автоматической рассылки:*\n{schedule_list}\n\n"
        f"🔄 *Статус автоматической рассылки:* {current_status}\n\n"
        f"Желаете изменить статус автоматической рассылки?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ========= Обработка нажатий "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["change_auto_send", "cancel_auto_send"])
def process_auto_send_change(call):
    """Переключает статус автоматической рассылки."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять статус автоматической рассылки.")
        return

    if call.data == "cancel_auto_send":
        bot.edit_message_text("❌ Изменение отменено.", call.message.chat.id, call.message.message_id)
        return

    # Перезагружаем config.py перед изменением
    importlib.reload(config)

    new_status = "off" if config.status_work_time == "on" else "on"

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Обновляем `status_work_time`
    for i, line in enumerate(config_content):
        if line.strip().startswith("status_work_time"):
            config_content[i] = f"status_work_time = '{new_status}'\n"
            break

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(config_content)

    # Перезагружаем config.py для применения изменений
    importlib.reload(config)

    # Перезапускаем автоматическую рассылку
    restart_scheduler()

    new_status_text = "✅ Включена" if new_status == "on" else "⛔ Выключена"
    bot.edit_message_text(f"🔄 Новый статус автоматической рассылки: {new_status_text}",
                          call.message.chat.id, call.message.message_id)


# ========= Команда /delete_user =========
@bot.message_handler(commands=['delete_user'])
def handle_delete_user(message):
    """Запускает процесс удаления пользователя из группы."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для удаления пользователей.")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_delete_user"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete_user")
    )

    bot.send_message(message.chat.id, "Хотите удалить пользователя?", reply_markup=keyboard)


# ========= Обработка выбора "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_delete_user", "cancel_delete_user"])
def process_delete_user_choice(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для удаления пользователей.")
        return

    if call.data == "confirm_delete_user":
        # Перезагружаем config.py перед выводом списка
        importlib.reload(config)

        keyboard = InlineKeyboardMarkup()
        for group_name, user_ids in config.performers.items():
            keyboard.add(InlineKeyboardButton(group_name, callback_data=f"select_group_for_delete_{group_name}"))

        bot.edit_message_text("Выберите группу, из которой хотите удалить сотрудника:",
                              call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    elif call.data == "cancel_delete_user":
        bot.edit_message_text("❌ Удаление пользователя отменено.", call.message.chat.id, call.message.message_id)


# ========= Обработка выбора группы для удаления =========
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_group_for_delete_"))
def process_group_selection_for_delete(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для удаления пользователей.")
        return

    selected_group = call.data.replace("select_group_for_delete_", "")

    # Перезагружаем config.py
    importlib.reload(config)

    user_ids = config.performers.get(selected_group, [])

    if not user_ids:
        bot.send_message(call.message.chat.id, f"🔹 В группе {selected_group} нет сотрудников.")
        return

    keyboard = InlineKeyboardMarkup()
    user_list = []

    for user_id in user_ids:
        try:
            user = bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else f"Без username"
            first_name = user.first_name or "Без имени"
            display_text = f"{first_name} ({username}) - {user_id}"
        except telebot.apihelper.ApiTelegramException:
            display_text = f"❌ Не найден - {user_id}"

        user_list.append(display_text)
        keyboard.add(InlineKeyboardButton(display_text, callback_data=f"delete_user_{selected_group}_{user_id}"))

    # ✅ Добавляем кнопку ❌ "Отмена"
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_user_deletion"))

    bot.send_message(call.message.chat.id, f"Выберите пользователя для удаления из {selected_group}:\n" +
                     "\n".join(user_list), reply_markup=keyboard)

# ========= Обработка нажатия "Отмена" =========
@bot.callback_query_handler(func=lambda call: call.data == "cancel_user_deletion")
def cancel_user_deletion(call):
    bot.edit_message_text("❌ Удаление пользователя отменено.", call.message.chat.id, call.message.message_id)

# ========= Удаление пользователя и обновление config.py =========
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_user_"))
def process_user_deletion(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для удаления пользователей.")
        return

    # ✅ Отладочный print
    print(f"DEBUG: call.data = {call.data}")

    try:
        # Разделяем строку **по последнему подчеркиванию**, чтобы корректно извлечь группу
        data_parts = call.data[len("delete_user_"):].rsplit("_", 1)
        if len(data_parts) != 2:
            raise ValueError("Ошибка разбора данных")

        selected_group, user_id = data_parts
        user_id = int(user_id)  # Преобразуем ID в число
    except ValueError as e:
        print(f"DEBUG: Ошибка парсинга call.data -> {e}")
        bot.send_message(call.message.chat.id, "⚠ Ошибка: некорректный формат ID пользователя.")
        return

    # ✅ Отладочный print
    print(f"DEBUG: selected_group = {selected_group}, user_id = {user_id}")

    config_file = "config.py"

    # Читаем config.py
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Карта групп
    group_mapping = {
        "Группа 1": "performers_list_1",
        "Группа 2": "performers_list_2",
        "Группа 3": "performers_list_3",
        "Группа 4": "performers_list_4",
        "Группа 5": "performers_list_5",
    }

    # ✅ Теперь selected_group содержит правильное название группы
    if selected_group not in group_mapping:
        bot.send_message(call.message.chat.id, f"⚠ Ошибка: группа <b>{selected_group}</b> не найдена в config.py",
                         parse_mode="HTML")
        return

    target_list = group_mapping[selected_group]

    # Удаление пользователя из config.py
    for i, line in enumerate(config_content):
        if line.strip().startswith(f"{target_list} = (") or line.strip().startswith(f"{target_list} = "):
            match = re.search(r"\((.*?)\)", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                existing_ids_list = []

            if user_id not in existing_ids_list:
                bot.send_message(call.message.chat.id, f"⚠ Пользователь с ID {user_id} не найден в группе {selected_group}.")
                return

            # Удаляем пользователя из списка
            existing_ids_list.remove(user_id)
            updated_ids = ", ".join(map(str, existing_ids_list))

            # Если список пуст, оставляем пустые скобки
            config_content[i] = f"{target_list} = ({updated_ids},)\n" if updated_ids else f"{target_list} = ()\n"
            break
    else:
        bot.send_message(call.message.chat.id, f"⚠ Ошибка: список {target_list} не найден в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(config_content)

    # 🔄 Перезагружаем config.py, чтобы бот сразу видел изменения
    importlib.reload(config)

    bot.send_message(
        call.message.chat.id,
        f"✅ Пользователь с ID <code>{user_id}</code> удален из <b>{selected_group}</b>.",
        parse_mode="HTML"
    )


# ========= Команда /add_user =========
@bot.message_handler(commands=['add_user'])
def handle_add_user(message):
    """Запускает процесс добавления нового пользователя в группу."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для добавления пользователей.")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_add_user"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_add_user")
    )

    bot.send_message(message.chat.id, "Хотите добавить нового пользователя?", reply_markup=keyboard)


# ========= Обработка выбора "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_add_user", "cancel_add_user"])
def process_add_user_choice(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для изменения пользователей.")
        return

    if call.data == "confirm_add_user":
        keyboard = InlineKeyboardMarkup()
        for group_name in config.performers.keys():
            keyboard.add(InlineKeyboardButton(group_name, callback_data=f"select_group_{group_name}"))

        bot.edit_message_text("Выберите группу, в которую хотите добавить сотрудника:",
                              call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    elif call.data == "cancel_add_user":
        bot.edit_message_text("❌ Добавление пользователя отменено.", call.message.chat.id, call.message.message_id)


# ========= Обработка выбора группы =========
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_group_"))
def process_group_selection(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для изменения пользователей.")
        return

    selected_group = call.data.replace("select_group_", "")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"Вы выбрали: *{selected_group}*.\n\nУкажите ID нового сотрудника:",
                     parse_mode="Markdown")

    # Запоминаем выбранную группу
    bot.register_next_step_handler(call.message, lambda msg: process_user_id(msg, selected_group))


# ========= Обработка ID нового пользователя =========
def process_user_id(message, selected_group):
    """Добавляет новый ID пользователя в выбранную группу и обновляет config.py."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для изменения пользователей.")
        return

    try:
        new_user_id = int(message.text.strip())  # Преобразуем в int
    except ValueError:
        bot.send_message(message.chat.id, "⚠ Ошибка: ID должен быть числом. Попробуйте снова с командой /add_user.")
        return

    config_file = "config.py"

    # Читаем config.py
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Определяем, какой performers_list_X обновлять
    group_mapping = {
        "Группа 1": "performers_list_1",
        "Группа 2": "performers_list_2",
        "Группа 3": "performers_list_3",
        "Группа 4": "performers_list_4",
        "Группа 5": "performers_list_5",
    }

    if selected_group not in group_mapping:
        bot.send_message(message.chat.id, f"⚠ Ошибка: группа <b>{selected_group}</b> не найдена в config.py",
                         parse_mode="HTML")
        return

    target_list = group_mapping[selected_group]

    # Найдем строку с соответствующим списком
    for i, line in enumerate(config_content):
        if line.strip().startswith(f"{target_list} = (") or line.strip().startswith(f"{target_list} = "):
            # Извлекаем текущий список ID
            match = re.search(r"\((.*?)\)", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                # Если список пуст или записан как число (int), исправляем
                existing_ids_list = []
                if "=" in line:
                    current_value = line.split("=")[1].strip()
                    if current_value.isdigit():  # Если это просто число, превращаем в tuple
                        existing_ids_list.append(int(current_value))

            # Проверим, есть ли уже такой ID
            if new_user_id in existing_ids_list:
                bot.send_message(message.chat.id,
                                 f"⚠ Пользователь с ID <code>{new_user_id}</code> уже в группе <b>{selected_group}</b>.",
                                 parse_mode="HTML")
                return

            # Добавляем новый ID и формируем обновленную строку как `tuple`
            existing_ids_list.append(new_user_id)
            updated_ids = ", ".join(map(str, existing_ids_list))
            config_content[i] = f"{target_list} = ({updated_ids},)\n"  # ✅ Гарантируем `tuple`
            break
    else:
        bot.send_message(message.chat.id, f"⚠ Ошибка: список {target_list} не найден в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(config_content)

    # 🔄 Перезагружаем config.py, чтобы бот сразу увидел изменения
    importlib.reload(config)

    bot.send_message(
        message.chat.id,
        f"✅ Сотрудник с ID <code>{new_user_id}</code> добавлен в <b>{selected_group}</b>.",
        parse_mode="HTML"
    )

# ========= Команда /set_time =========
@bot.message_handler(commands=['set_time'])
def handle_set_time(message):
    """Запрашивает у администратора изменение времени отправки заданий."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять время отправки заданий.")
        return

    # Вывод текущего расписания
    current_schedule = "\n".join(config.work_time)
    current_status = "✅ Включена" if config.status_work_time == "on" else "⛔ Выключена"
    # bot.send_message(message.chat.id, f"🕒 Текущее расписание:\n{current_schedule}\n ")

    bot.send_message(
        message.chat.id,
        f"🕒 Текущее расписание:\n{current_schedule}\n \n🔄 *Статус автоматической рассылки:* {current_status}\n\n",
        parse_mode="Markdown",
    )

    # Создание inline-кнопок
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="change_time"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_time")
    )

    bot.send_message(message.chat.id, "Желаете изменить время автоматической отправки заданий?", reply_markup=keyboard)



# ========= Обработка нажатий "Да" / "Нет" =========
@bot.callback_query_handler(func=lambda call: call.data in ["change_time", "cancel_time"])
def process_time_change(call):
    """Обрабатывает выбор администратора (изменить время или оставить текущее)."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять расписание.")
        return

    if call.data == "change_time":
        # Удаляем inline-кнопки, но оставляем текст сообщения
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

        # Запрашиваем у администратора новое время
        bot.send_message(call.message.chat.id, "⏳ Введите новое время в формате 'HH:MM HH:MM HH:MM' (через пробел):")
        bot.register_next_step_handler(call.message, update_schedule)

    elif call.data == "cancel_time":
        bot.edit_message_text("❌ Изменение отменено.", call.message.chat.id, call.message.message_id)


# ========= Обновление `work_time` =========
def update_schedule(message):
    """Обновляет список времени отправки задач в `config.py` и перезапускает планировщик."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять расписание.")
        return

    new_times = message.text.strip().split()

    # Проверяем корректность формата
    for time_value in new_times:
        if not time_value.count(":") == 1 or not all(x.isdigit() for x in time_value.split(":")):
            bot.send_message(message.chat.id, "⚠ Ошибка: введите время в формате 'HH:MM HH:MM HH:MM'\n Начните сначала, используя команду /set_time.")
            return

    # **Перезаписываем `work_time` в config.py**
    config.work_time = new_times
    with open("config.py", "r") as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if line.startswith("work_time"):
            lines[i] = f"work_time = {new_times}\n"

    with open("config.py", "w") as file:
        file.writelines(lines)

    # Перезагружаем config.py перед выводом информации
    importlib.reload(config)

    current_status = "✅ Включена" if config.status_work_time == "on" else "⛔ Выключена"

    bot.send_message(message.chat.id, f"✅ Время изменено! Новое расписание:\n" + "\n".join(config.work_time))
    bot.send_message(
        message.chat.id,
        f"🔄 *Статус автоматической рассылки:* {current_status}\n\n",
        parse_mode="Markdown",
    )


    # Перезапускаем планировщик
    restart_scheduler()


# ========= Автоматическая отправка задач по расписанию =========
def send_control_panel_tasks():
    for performers, tasks_text in config.control_panel.items():
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Ваши задачи:*\n{tasks_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")
            except telebot.apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in str(e):
                    print(f"⚠ Бот заблокирован пользователем {performer}.")
                else:
                    print(f"⚠ Ошибка при отправке сообщения пользователю {performer}: {e}")



# ========= Перезапуск планировщика =========
def restart_scheduler():
    """Перезапускает планировщик с учетом статуса автоматической рассылки."""
    importlib.reload(config)  # Перезагружаем config.py

    schedule.clear()

    if config.status_work_time == "off":
        print("⛔ Автоматическая рассылка отключена. Планировщик не запущен.")
        return  # Если авторассылка отключена, выходим из функции

    for work_time in config.work_time:
        schedule.every().day.at(work_time).do(send_control_panel_tasks)

    print(f"✅ Планировщик обновлен! Новое расписание: {config.work_time}")

# # ========= Перезапуск планировщика =========
# def restart_scheduler():
#     """Перезапускает планировщик с новыми временами"""
#     schedule.clear()
#     for work_time in config.work_time:
#         schedule.every().day.at(work_time).do(send_control_panel_tasks)
#     print(f"✅ Планировщик обновлен! Новое расписание: {config.work_time}")


# ========= Фоновый процесс планировщика =========
def schedule_jobs():
    while True:
        schedule.run_pending()
        time.sleep(30)

schedule_thread = threading.Thread(target=schedule_jobs)
schedule_thread.daemon = True
schedule_thread.start()

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
    """Выводит список администраторов бота."""
    admin_list = []

    for admin_id in config.ADMIN_ID:
        try:
            user = bot.get_chat(admin_id)
            username = f"👤 @{user.username}" if user.username else f"ID: {admin_id}"
        except telebot.apihelper.ApiTelegramException:
            username = f"👤 ID: {admin_id} (❌ недоступен)"

        # Экранируем username и ID перед отправкой
        admin_list.append(escape_markdown_v2(username))

    bot.send_message(
        chat_id=message.chat.id,
        text=f"🔹 *Список администраторов:*\n" + "\n".join(admin_list),
        parse_mode="MarkdownV2"
    )


@bot.message_handler(commands=['bot_users'])
def handle_bot_users(message):
    """Выводит актуальный список сотрудников по группам."""

    # Динамическая перезагрузка config.py
    importlib.reload(config)

    groups = {
        "Группа 1": config.performers_list_1,
        "Группа 2": config.performers_list_2,
        "Группа 3": config.performers_list_3,
        "Группа 4": config.performers_list_4,
        "Группа 5": config.performers_list_5,
    }

    response = []

    for group_name, users in groups.items():
        user_list = []
        for user_id in users:
            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else f"ID: {user_id}"
                user_list.append(f"👤 {username}")
            except telebot.apihelper.ApiTelegramException:
                user_list.append(f"⚠ ID: {user_id} (не найден)")

        if user_list:
            response.append(f"<b>{group_name}</b>:\n" + "\n".join(user_list))
        else:
            response.append(f"<b>{group_name}</b>:\n 🔹 Нет сотрудников.")

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

# ========= Хранение данных о задачах и фото =========
task_data = {}

# ========= Ручная постановка задачи (админом) =========
@bot.message_handler(commands=['new_task'])
def new_task(message):
    """Запрашивает у администратора текст задачи."""
    if not message.from_user.id in config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "✏ Введите текст задачи (или напишите 'отмена' для выхода):")
    bot.register_next_step_handler(message, send_task_to_performers)


def send_task_to_performers(message):
    """Обрабатывает введенный текст задачи, отменяет команду, если введено 'отмена'."""
    if message.text.lower() == "отмена":
        bot.send_message(message.chat.id, "🚫 Создание задачи отменено.")
        return  # Завершаем обработчик

    task_text = message.text  # Получаем текст задания

    for performers, tasks_text in config.control_panel.items():
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Новое задание:*\n{task_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")
                task_data[performer] = {"task_text": task_text}
            except telebot.apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in str(e):
                    print(f"⚠ Бот заблокирован пользователем {performer}.")
                else:
                    print(f"⚠ Ошибка при отправке задания пользователю {performer}: {e}")


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
    task_text = task_data.get(user_id, {}).get("task_text", "")
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
        InlineKeyboardButton("✅ Принять", callback_data=f"accept_{sent_message.message_id}_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{sent_message.message_id}_{user_id}")
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