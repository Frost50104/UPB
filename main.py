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
import hashlib
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


# ========= Команда /set_group_name =========
@bot.message_handler(commands=['set_group_name'])
def handle_set_group_name(message):
    """Запускает процесс изменения названия группы."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять названия групп.")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_set_group_name"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_set_group_name")
    )

    bot.send_message(
        message.chat.id,
        "Хотите изменить название группы?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# Словарь для хранения соответствия индексов и имен групп
group_index_map = {str(index): name for index, name in enumerate(config.performers.keys())}

@bot.callback_query_handler(func=lambda call: call.data == "cancel_set_group_name")
def cancel_set_group_name(call):
    """Обрабатывает отказ от изменения названия группы."""
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🚫 Смена названия группы отменена.")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_set_group_name")
def process_set_group_name_choice(call):
    """Обрабатывает выбор администратора (изменять название или нет)."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять названия групп.")
        return

    # Удаляем inline-кнопки после выбора
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    importlib.reload(config)  # Обновляем данные

    # Динамически создаем индексный словарь после каждой команды
    global group_index_map
    group_index_map = {str(index): name for index, name in enumerate(config.performers.keys())}

    keyboard = InlineKeyboardMarkup()
    for index, group_name in group_index_map.items():
        keyboard.add(InlineKeyboardButton(group_name, callback_data=f"select_group_to_rename|{index}"))

    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_group_rename"))

    bot.send_message(
        call.message.chat.id,
        "Выберите группу, у которой хотите изменить имя:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "cancel_group_rename")
def cancel_group_rename(call):
    """Обрабатывает отмену выбора группы."""
    bot.edit_message_text("❌ Операция переименования группы отменена.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_group_to_rename"))
def select_group_to_rename(call):
    """Сохраняет выбранную группу и запрашивает новое имя."""
    _, group_index = call.data.split("|")

    # Обновляем данные перед каждым изменением
    importlib.reload(config)
    group_index_map = {str(index): name for index, name in enumerate(config.performers.keys())}

    old_group_name = group_index_map.get(group_index)

    if not old_group_name or old_group_name not in config.performers:
        bot.send_message(call.message.chat.id, "⚠ Ошибка: группа не найдена.", parse_mode="HTML")
        return

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    bot.send_message(
        call.message.chat.id,
        f"Введите новое название для группы <b>{old_group_name}</b>:",
        parse_mode="HTML"
    )

    bot.register_next_step_handler(call.message, process_new_group_name, old_group_name)

def process_new_group_name(message, old_group_name):
    """Обновляет название группы в config.py."""
    chat_id = message.chat.id
    new_group_name = message.text.strip()

    if not new_group_name:
        bot.send_message(chat_id, "⚠ Ошибка: название группы не может быть пустым. Повторите команду /set_group_name.")
        return

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Обновляем словарь performers
    new_config_content = []
    group_updated = False

    for line in config_content:
        if line.strip().startswith("performers = {"):
            new_config_content.append(line)
            continue

        match = re.match(r"\s*'(.*?)':\s*(performers_list_\d+),", line)
        if match:
            current_group_name, group_var = match.groups()
            if current_group_name == old_group_name:
                new_config_content.append(f"    '{new_group_name}': {group_var},\n")
                group_updated = True
                continue

        new_config_content.append(line)

    if not group_updated:
        bot.send_message(chat_id, f"⚠ Ошибка: группа <b>{old_group_name}</b> не найдена в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(new_config_content)

    # Перезагружаем config.py
    importlib.reload(config)

    # Отправляем подтверждение
    bot.send_message(
        chat_id,
        f"✅ Название группы <b>{old_group_name}</b> изменено на <b>{new_group_name}</b>!",
        parse_mode="HTML"
    )

    # Выводим обновленный список групп
    updated_groups = "\n".join([f"🔹 <b>{group}</b>" for group in config.performers.keys()])
    bot.send_message(
        chat_id,
        f"🔄 <b>Обновленный список групп:</b>\n{updated_groups}",
        parse_mode="HTML"
    )



# ========= Команда /add_user =========
@bot.message_handler(commands=['add_user'])
def handle_add_user(message):
    """Запускает процесс добавления нового сотрудника."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав для добавления сотрудников.")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_add_user"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_add_user")
    )

    bot.send_message(
        message.chat.id,
        "Хотите добавить нового пользователя?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data in ["confirm_add_user", "cancel_add_user"])
def process_add_user_choice(call):
    """Обрабатывает выбор администратора (добавлять или нет)."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав изменять список сотрудников.")
        return

    if call.data == "cancel_add_user":
        bot.edit_message_text("❌ Добавление пользователя отменено.", call.message.chat.id, call.message.message_id)
        return

    # Перезагружаем config перед созданием кнопок
    importlib.reload(config)

    keyboard = InlineKeyboardMarkup()
    group_index_map = {str(index): group for index, group in enumerate(config.performers.keys())}

    for index, group_name in group_index_map.items():
        keyboard.add(InlineKeyboardButton(group_name[:30], callback_data=f"select_group_{index}"))

    bot.edit_message_text(
        "Выберите группу, в которую нужно добавить нового сотрудника:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

    # Сохраняем соответствие индексов и названий групп
    task_data[call.message.chat.id] = {"group_index_map": group_index_map}


@bot.callback_query_handler(func=lambda call: call.data.startswith("select_group_"))
def select_group(call):
    """Запрашивает ID нового сотрудника после выбора группы."""
    chat_id = call.message.chat.id
    group_index = call.data.split("_")[2]

    if chat_id not in task_data or "group_index_map" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: данные не найдены. Повторите команду /add_user.")
        return

    # Получаем название группы по индексу
    group_name = task_data[chat_id]["group_index_map"].get(group_index)

    if not group_name:
        bot.send_message(chat_id, "⚠ Ошибка: группа не найдена.")
        return

    # Сохраняем выбранную группу
    task_data[chat_id]["selected_group"] = group_name

    bot.edit_message_text(
        f"Вы выбрали группу <b>{group_name}</b>\n\nУкажите ID сотрудника:",
        chat_id,
        call.message.message_id,
        parse_mode="HTML"
    )

    bot.register_next_step_handler_by_chat_id(chat_id, process_new_user_id)


def process_new_user_id(message):
    """Добавляет нового сотрудника в config.py."""
    chat_id = message.chat.id

    if chat_id not in task_data or "selected_group" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: группа не найдена. Повторите команду /add_user.")
        return

    try:
        new_user_id = int(message.text.strip())
    except ValueError:
        bot.send_message(chat_id, "⚠ Ошибка: ID должен быть числом. Попробуйте снова.", parse_mode="HTML")
        return

    group_name = task_data[chat_id]["selected_group"]

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Определяем имя переменной с кортежем сотрудников
    group_var_name = None
    for var_name in config.performers.keys():
        if var_name == group_name:
            group_var_name = f"performers_list_{list(config.performers.keys()).index(var_name) + 1}"
            break

    if not group_var_name:
        bot.send_message(chat_id, f"⚠ Ошибка: группа <b>{group_name}</b> не найдена в config.py", parse_mode="HTML")
        return

    # Обновляем список сотрудников
    new_config_content = []
    group_updated = False

    for line in config_content:
        if line.strip().startswith(f"{group_var_name} ="):
            match = re.search(r"\((.*?)\)", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                existing_ids_list = []

            if new_user_id in existing_ids_list:
                bot.send_message(chat_id, f"⚠ Пользователь с ID <b>{new_user_id}</b> уже в группе {group_name}.", parse_mode="HTML")
                return

            existing_ids_list.append(new_user_id)
            updated_ids = ", ".join(map(str, existing_ids_list))

            # Обновляем строку в файле
            new_config_content.append(f"{group_var_name} = ({updated_ids},)\n")
            group_updated = True
        else:
            new_config_content.append(line)

    if not group_updated:
        bot.send_message(chat_id, f"⚠ Ошибка: список сотрудников группы <b>{group_name}</b> не найден в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(new_config_content)

    # Перезагружаем config.py
    importlib.reload(config)

    bot.send_message(
        chat_id,
        f"✅ Пользователь с ID <b>{new_user_id}</b> добавлен в группу <b>{group_name}</b>!",
        parse_mode="HTML"
    )

    del task_data[chat_id]



# ========= Команда /delete_user =========
@bot.message_handler(commands=['delete_user'])
def handle_delete_user(message):
    """Запускает процесс удаления сотрудника."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав удалять сотрудников.")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_delete_user"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete_user")
    )

    bot.send_message(
        message.chat.id,
        "Хотите удалить пользователя?",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data in ["confirm_delete_user", "cancel_delete_user"])
def process_delete_user_choice(call):
    """Обрабатывает выбор администратора."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав удалять сотрудников.")
        return

    if call.data == "cancel_delete_user":
        bot.edit_message_text("❌ Удаление сотрудника отменено.", call.message.chat.id, call.message.message_id)
        return

    # Перезагружаем config перед выводом списка групп
    importlib.reload(config)

    # Используем индекс вместо длинного названия группы
    group_index_map = {str(index): name for index, name in enumerate(config.performers.keys())}

    # Сохраняем соответствие индексов и имен групп (глобально)
    task_data[call.message.chat.id] = {"group_index_map": group_index_map}

    keyboard = InlineKeyboardMarkup()
    for index, group_name in group_index_map.items():
        keyboard.add(InlineKeyboardButton(group_name[:30], callback_data=f"delete_group_{index}"))

    bot.edit_message_text(
        "Выберите группу, из которой нужно удалить сотрудника:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_group_"))
def select_group_to_delete(call):
    """Обрабатывает выбор группы для удаления сотрудника."""
    chat_id = call.message.chat.id
    group_index = call.data.split("_")[2]

    if chat_id not in task_data or "group_index_map" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: данные не найдены. Повторите команду /delete_user.")
        return

    # Получаем название группы по индексу
    group_name = task_data[chat_id]["group_index_map"].get(group_index)

    if not group_name:
        bot.send_message(chat_id, "⚠ Ошибка: группа не найдена.")
        return

    # Сохраняем выбранную группу
    task_data[chat_id]["selected_group"] = group_name

    # Получаем список сотрудников
    employee_list = config.performers[group_name]
    if not employee_list:
        bot.send_message(chat_id, f"⚠ В группе <b>{group_name}</b> нет сотрудников.", parse_mode="HTML")
        return

    keyboard = InlineKeyboardMarkup()
    for user_id in employee_list:
        try:
            user = bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else "Без username"
            first_name = user.first_name or "Без имени"
            display_text = f"👤 {first_name} ({username})"
        except telebot.apihelper.ApiTelegramException:
            display_text = f"❌ ID: {user_id} (не найден)"

        keyboard.add(InlineKeyboardButton(display_text, callback_data=f"delete_user_{user_id}"))

    # Добавляем кнопку "❌ Отмена"
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete_employee"))

    bot.edit_message_text(
        f"Выберите сотрудника для удаления из <b>{group_name}</b>:",
        chat_id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete_employee")
def cancel_delete_employee(call):
    """Возвращает пользователя к выбору группы."""
    chat_id = call.message.chat.id

    if chat_id not in task_data or "group_index_map" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: данные не найдены. Повторите команду /delete_user.")
        return

    group_index_map = task_data[chat_id]["group_index_map"]

    keyboard = InlineKeyboardMarkup()
    for index, group_name in group_index_map.items():
        keyboard.add(InlineKeyboardButton(group_name[:30], callback_data=f"delete_group_{index}"))

    bot.edit_message_text(
        "Выберите группу, из которой нужно удалить сотрудника:",
        chat_id,
        call.message.message_id,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_user_"))
def delete_employee(call):
    """Удаляет сотрудника из группы."""
    chat_id = call.message.chat.id
    user_id = int(call.data.split("_")[2])

    if chat_id not in task_data or "selected_group" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: данные не найдены. Повторите команду /delete_user.")
        return

    group_name = task_data[chat_id]["selected_group"]

    if group_name not in config.performers:
        bot.send_message(chat_id, "⚠ Ошибка: группа не найдена.")
        return

    # Убираем inline-кнопки
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)

    # Читаем config.py
    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Определяем имя переменной с сотрудниками
    group_var_name = None
    for var_name, users in config.performers.items():
        if var_name == group_name:
            group_var_name = f"performers_list_{list(config.performers.keys()).index(var_name) + 1}"
            break

    if not group_var_name:
        bot.send_message(chat_id, f"⚠ Ошибка: группа <b>{group_name}</b> не найдена в config.py", parse_mode="HTML")
        return

    # Обновляем список сотрудников
    new_config_content = []
    group_updated = False

    for line in config_content:
        if line.strip().startswith(f"{group_var_name} ="):
            match = re.search(r"\((.*?)\)", line)
            if match:
                existing_ids = match.group(1).strip()
                existing_ids_list = [int(x.strip()) for x in existing_ids.split(",") if x.strip().isdigit()]
            else:
                existing_ids_list = []

            if user_id not in existing_ids_list:
                bot.send_message(chat_id, f"⚠ Пользователь с ID <b>{user_id}</b> не найден в группе {group_name}.", parse_mode="HTML")
                return

            # Удаляем пользователя
            existing_ids_list.remove(user_id)
            updated_ids = ", ".join(map(str, existing_ids_list))

            new_config_content.append(f"{group_var_name} = ({updated_ids},)\n" if updated_ids else f"{group_var_name} = ()\n")

            group_updated = True
        else:
            new_config_content.append(line)

    if not group_updated:
        bot.send_message(chat_id, f"⚠ Ошибка: список сотрудников группы <b>{group_name}</b> не найден в config.py", parse_mode="HTML")
        return

    # Записываем обновленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(new_config_content)

    importlib.reload(config)

    bot.send_message(
        chat_id,
        f"✅ Пользователь с ID <b>{user_id}</b> удален из группы <b>{group_name}</b>!",
        parse_mode="HTML"
    )

    del task_data[chat_id]




# ========= Команда /set_tasks_group =========
@bot.message_handler(commands=['set_tasks_group'])
def handle_set_tasks_group(message):
    """Позволяет администратору изменить задания для групп."""
    if message.from_user.id not in config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав изменять задания групп.")
        return

    importlib.reload(config)  # Обновляем данные

    global task_data
    task_data = {}  # Создаем глобальный словарь для хранения выбранной группы

    keyboard = InlineKeyboardMarkup()
    global group_name_map
    group_name_map = {}

    response = "<b>Текущие задания групп:</b>\n\n"

    for group_name, performers_list in config.performers.items():
        # Преобразуем название списка исполнителей в строку, чтобы соответствовать ключам в control_panel_for_set_tasks_group
        performers_key = f"performers_list_{list(config.performers.keys()).index(group_name) + 1}"
        correct_task = config.control_panel_for_set_tasks_group.get(performers_key, "❌ Нет задания")

        response += f"🔹 <b>{group_name}:</b>\n<pre>{correct_task.strip()}</pre>\n\n"

        group_hash = hashlib.md5(group_name.encode()).hexdigest()[:8]
        group_name_map[group_hash] = group_name  # Сохраняем соответствие

        callback_data = f"edit_task|{message.chat.id}|{group_hash}"
        keyboard.add(InlineKeyboardButton(group_name[:30], callback_data=callback_data))

    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_set_tasks_group|{message.chat.id}"))

    bot.send_message(
        message.chat.id,
        response + "Выберите группу, для которой хотите изменить задание:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_task"))
def edit_task(call):
    """Запрашивает у администратора новое задание для выбранной группы."""
    _, chat_id, group_hash = call.data.split("|")
    chat_id = int(chat_id)

    if group_hash not in group_name_map:
        bot.answer_callback_query(call.id, "⚠ Ошибка: группа не найдена.")
        return

    group_name = group_name_map[group_hash]

    task_data[chat_id] = {"selected_group": group_name}

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    bot.send_message(chat_id, f"Введите новое задание для группы <b>{group_name}</b>:", parse_mode="HTML")
    bot.register_next_step_handler_by_chat_id(chat_id, update_task_text)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_set_tasks_group"))
def cancel_set_tasks_group(call):
    """Отмена изменения заданий для групп."""
    chat_id = int(call.data.split("|")[1])

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(chat_id, "🚫 Изменение задач для автоматической отправки отменено.")

def update_task_text(message):
    """Обновляет задание для выбранной группы в config.py и сохраняет его в control_panel_for_set_tasks_group."""
    chat_id = message.chat.id

    if chat_id not in task_data or "selected_group" not in task_data[chat_id]:
        bot.send_message(chat_id, "⚠ Ошибка: группа не найдена. Повторите команду /set_tasks_group.")
        return

    new_task_text = message.text.strip()
    group_name = task_data[chat_id]["selected_group"]

    config_file = "config.py"
    with open(config_file, "r", encoding="utf-8") as file:
        config_content = file.readlines()

    # Определяем переменную задания
    group_index = list(config.performers.keys()).index(group_name) + 1
    task_var_name = f"task_group_{group_index}"
    performers_key = f"performers_list_{group_index}"

    # Обновленный список строк конфигурации
    new_config_content = []
    inside_task_block = False
    task_updated = False

    for line in config_content:
        if line.strip().startswith(f"{task_var_name} = '''") or line.strip().startswith(f'{task_var_name} = """'):
            # Найден старый блок задачи — заменяем его
            new_config_content.append(f"{task_var_name} = '''\n{new_task_text}\n'''\n")
            inside_task_block = True
            task_updated = True
            continue

        if inside_task_block:
            if line.strip().endswith("'''") or line.strip().endswith('"""'):
                inside_task_block = False  # Конец старого блока задачи
            continue  # Не записываем старые строки задачи

        new_config_content.append(line)  # Оставляем все остальные строки без изменений

    if not task_updated:
        bot.send_message(chat_id, f"⚠ Ошибка: переменная {task_var_name} не найдена в config.py")
        return

    # Записываем исправленный config.py
    with open(config_file, "w", encoding="utf-8") as file:
        file.writelines(new_config_content)

    # Перезагружаем config.py, чтобы бот сразу видел изменения
    importlib.reload(config)

    # Обновляем `control_panel_for_set_tasks_group`
    config.control_panel_for_set_tasks_group[performers_key] = new_task_text

    bot.send_message(
        chat_id,
        f"✅ Задание для группы <b>{group_name}</b> успешно обновлено!",
        parse_mode="HTML"
    )

    del task_data[chat_id]

# ========= Команда /group_task =========
@bot.message_handler(commands=['group_task'])
def handle_group_task(message):
    """Запрашивает у администратора текст задачи."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "✏ Введите текст задачи (или напишите 'отмена' для выхода):")
    bot.register_next_step_handler(message, process_group_task_text)


def process_group_task_text(message):
    """Обрабатывает введенный текст задачи и предлагает выбрать группы сотрудников."""
    if message.text.lower() == "отмена":
        bot.send_message(message.chat.id, "🚫 Создание задачи отменено.")
        return

    task_text = message.text.strip()
    chat_id = message.chat.id

    # Сохраняем данные о задаче
    task_data[chat_id] = {"task_text": task_text, "selected_groups": []}

    send_group_selection(chat_id)


def hash_group_name(group_name):
    """Создаёт короткий хеш названия группы для использования в callback_data."""
    return hashlib.md5(group_name.encode()).hexdigest()[:8]  # 8 символов достаточно для уникальности

group_name_map = {}  # Словарь для хранения соответствия хеша и оригинального названия

def send_group_selection(chat_id):
    """Отправляет список групп для выбора."""
    importlib.reload(config)  # Обновляем данные

    selected_groups = task_data[chat_id]["selected_groups"]
    available_groups = [group for group in config.performers.keys() if group not in selected_groups]

    keyboard = InlineKeyboardMarkup()

    if not available_groups:
        bot.send_message(
            chat_id,
            "Больше нет доступных групп",
            parse_mode="HTML"
        )
        send_selected_groups(chat_id)
        return

    for group_name in available_groups:
        group_hash = hash_group_name(group_name)
        group_name_map[group_hash] = group_name  # Сохраняем соответствие
        callback_data = f"group_task_select|{chat_id}|{group_hash}"
        keyboard.add(InlineKeyboardButton(group_name, callback_data=callback_data))

    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data=f"group_task_cancel|{chat_id}"))

    bot.send_message(
        chat_id,
        "Кому нужно поставить задачу?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("group_task_select"))
def select_group(call):
    """Добавляет группу в список получателей задачи и предлагает выбрать еще или отправить."""
    _, chat_id, group_hash = call.data.split("|")
    chat_id = int(chat_id)

    if chat_id not in task_data:
        bot.answer_callback_query(call.id, "⚠ Ошибка: задача не найдена.")
        return

    group_name = group_name_map.get(group_hash)
    if not group_name:
        bot.answer_callback_query(call.id, "⚠ Ошибка: группа не найдена.")
        return

    if group_name not in task_data[chat_id]["selected_groups"]:
        task_data[chat_id]["selected_groups"].append(group_name)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    send_selected_groups(chat_id)


def send_selected_groups(chat_id):
    """Отправляет сообщение с выбранными группами и возможностью добавить ещё или отправить."""
    selected_groups = task_data[chat_id]["selected_groups"]
    selected_text = "\n".join([f"✅ <b>{group}</b>" for group in selected_groups])

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("➕ Добавить ещё", callback_data=f"group_task_add_more|{chat_id}"),
        InlineKeyboardButton("📨 ОТПРАВИТЬ", callback_data=f"group_task_send|{chat_id}"),
        InlineKeyboardButton("❌ Отмена", callback_data=f"group_task_cancel|{chat_id}")
    )

    bot.send_message(
        chat_id,
        f"Добавить ещё одну группу или отправить задачу?\n\n<b>Выбранные группы:</b>\n{selected_text}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("group_task_add_more"))
def add_more_groups(call):
    """Позволяет выбрать ещё группы."""
    chat_id = int(call.data.split("|")[1])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    send_group_selection(chat_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("group_task_send"))
def send_group_task(call):
    """Отправляет задачу выбранным группам."""
    chat_id = int(call.data.split("|")[1])

    if chat_id not in task_data or not task_data[chat_id]["selected_groups"]:
        bot.answer_callback_query(call.id, "⚠ Ошибка: нет выбранных групп.")
        return

    task_text = task_data[chat_id]["task_text"]
    group_names = task_data[chat_id]["selected_groups"]
    user_ids = []

    for group_name in group_names:
        user_ids.extend(config.performers.get(group_name, []))

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    for user_id in user_ids:
        try:
            bot.send_message(user_id, f"📌 <b>Новое задание:</b>\n{task_text}", parse_mode="HTML")
            bot.send_message(user_id, "📷 Отправьте фото выполнения.")
            task_data[user_id] = {"task_text": task_text}
        except telebot.apihelper.ApiTelegramException as e:
            print(f"⚠ Ошибка отправки пользователю {user_id}: {e}")

    bot.send_message(chat_id, "✅ Задача успешно отправлена сотрудникам из выбранных групп!")
    del task_data[chat_id]


@bot.callback_query_handler(func=lambda call: call.data.startswith("group_task_cancel"))
def cancel_task(call):
    """Отмена создания задачи."""
    chat_id = int(call.data.split("|")[1])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(chat_id, "🚫 Создание задачи отменено.")
    if chat_id in task_data:
        del task_data[chat_id]


# ========= Команда /user_task =========
@bot.message_handler(commands=['user_task'])
def handle_user_task(message):
    """Запрашивает у администратора текст задачи."""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "✏ Введите текст задачи (или напишите 'отмена' для выхода):")
    bot.register_next_step_handler(message, process_user_task_text)


def process_user_task_text(message):
    """Обрабатывает введенный текст задачи и предлагает выбрать сотрудников."""
    if message.text.lower() == "отмена":
        bot.send_message(message.chat.id, "🚫 Создание задачи отменено.")
        return

    task_text = message.text.strip()
    chat_id = message.chat.id

    task_data[chat_id] = {"task_text": task_text, "selected_users": []}

    send_employee_selection(message.chat.id)


def send_employee_selection(chat_id):
    """Отправляет список сотрудников для выбора."""
    importlib.reload(config)  # Обновляем данные

    selected_users = task_data[chat_id]["selected_users"]
    available_users = []

    keyboard = InlineKeyboardMarkup()
    for group_name, users in config.performers.items():
        for user_id in users:
            if user_id in selected_users:
                continue  # Пропускаем уже выбранных

            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else "Без username"
                first_name = user.first_name or "Без имени"
                callback_data = f"select_employee|{chat_id}|{user_id}"
                keyboard.add(InlineKeyboardButton(f"{first_name} ({username})", callback_data=callback_data))
                available_users.append(f"👤 {first_name} ({username}) - {user_id}")
            except telebot.apihelper.ApiTelegramException:
                continue

    # Если нет доступных пользователей, сразу предлагаем отправить задачу
    if not available_users:
        bot.send_message(
            chat_id,
            "Больше нет доступных сотрудников",
            parse_mode="HTML"
        )
        send_selected_users(chat_id)
        return

    keyboard.add(
        InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_task|{chat_id}")
    )

    bot.send_message(
        chat_id,
        "Кому нужно поставить задачу?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("select_employee"))
def select_employee(call):
    """Добавляет сотрудника в список получателей задачи."""
    _, chat_id, user_id = call.data.split("|")
    chat_id, user_id = int(chat_id), int(user_id)

    if chat_id not in task_data:
        bot.answer_callback_query(call.id, "⚠ Ошибка: задача не найдена.")
        return

    if user_id not in task_data[chat_id]["selected_users"]:
        task_data[chat_id]["selected_users"].append(user_id)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    send_selected_users(chat_id)


def send_selected_users(chat_id):
    """Отправляет сообщение с выбранными пользователями и возможностью добавить ещё или отправить."""
    selected_users = task_data[chat_id]["selected_users"]
    selected_text = ""

    for user_id in selected_users:
        try:
            user = bot.get_chat(user_id)
            username = f"(@{user.username})" if user.username else ""
            first_name = user.first_name or "Без имени"
            selected_text += f"✅ {first_name} {username} - <code>{user_id}</code>\n"
        except telebot.apihelper.ApiTelegramException:
            selected_text += f"✅ <code>{user_id}</code> (ошибка получения данных)\n"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("➕ Добавить ещё", callback_data=f"add_more_users|{chat_id}"),
        InlineKeyboardButton("📨 ОТПРАВИТЬ", callback_data=f"send_task|{chat_id}"),
        InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_task|{chat_id}")
    )

    bot.send_message(
        chat_id,
        f"Добавить ещё одного сотрудника или отправить задачу?\n\n<b>Выбранные сотрудники:</b>\n{selected_text}",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("add_more_users"))
def add_more_users(call):
    """Позволяет выбрать ещё сотрудников."""
    chat_id = int(call.data.split("|")[1])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    send_employee_selection(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("send_task"))
def send_task(call):
    """Отправляет задачу выбранным сотрудникам."""
    chat_id = int(call.data.split("|")[1])

    if chat_id not in task_data or not task_data[chat_id]["selected_users"]:
        bot.answer_callback_query(call.id, "⚠ Ошибка: нет выбранных сотрудников.")
        return

    task_text = task_data[chat_id]["task_text"]
    user_ids = task_data[chat_id]["selected_users"]

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    for user_id in user_ids:
        try:
            bot.send_message(user_id, f"📌 <b>Новое задание:</b>\n{task_text}", parse_mode="HTML")
            bot.send_message(user_id, "📷 Отправьте фото выполнения.")
            task_data[user_id] = {"task_text": task_text}
        except telebot.apihelper.ApiTelegramException as e:
            print(f"⚠ Ошибка отправки пользователю {user_id}: {e}")

    bot.send_message(chat_id, "✅ Задача успешно отправлена выбранным сотрудникам!")
    del task_data[chat_id]


@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_task"))
def cancel_task(call):
    """Отмена создания задачи."""
    chat_id = int(call.data.split("|")[1])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(chat_id, "🚫 Создание задачи отменено.")
    if chat_id in task_data:
        del task_data[chat_id]


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

    # Проверяем корректность формата и исправляем, если нужно
    corrected_times = []
    for time_value in new_times:
        match = re.match(r"^(\d{1,2}):(\d{2})$", time_value)
        if not match:
            bot.send_message(
                message.chat.id,
                "⚠ Ошибка: введите время в формате 'H:MM' или 'HH:MM'.\n"
                "Пример: 9:30 или 09:30\n"
                "Начните сначала, используя команду /set_time."
            )
            return

        hours, minutes = match.groups()
        hours = hours.zfill(2)  # Добавляем ноль перед однозначными числами
        corrected_times.append(f"{hours}:{minutes}")

    # **Перезаписываем `work_time` в config.py**
    config.work_time = corrected_times
    with open("config.py", "r", encoding="utf-8") as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if line.startswith("work_time"):
            lines[i] = f"work_time = {corrected_times}\n"

    with open("config.py", "w", encoding="utf-8") as file:
        file.writelines(lines)

    # Перезагружаем config.py
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
    """Отправляет задачи сотрудникам и сохраняет их текст в task_data."""
    for performers, tasks_text in config.control_panel.items():
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Ваши задачи:*\n{tasks_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")

                # ✅ Сохраняем текст задачи в task_data
                task_data[performer] = {"task_text": tasks_text}

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


# ========= Фоновый процесс планировщика =========
def schedule_jobs():
    """Запускает бесконечный цикл выполнения задач, но только если авторассылка включена."""
    while True:
        importlib.reload(config)  # Загружаем актуальные настройки

        if config.status_work_time == "on":
            schedule.run_pending()

        time.sleep(20)  # Проверка каждые 20 секунд

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

    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав просматривать список администраторов.")
        return

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

    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав просматривать список пользователей.")
        return


    """Выводит актуальный список сотрудников по группам."""

    importlib.reload(config)  # Перезагружаем config.py

    response = []

    for group_name, users in config.performers.items():
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
@bot.message_handler(commands=['all_task'])
def new_task(message):
    """Запрашивает у администратора текст задачи."""
    if not message.from_user.id in config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав ставить задачи.")
        return

    bot.send_message(message.chat.id, "✏ Введите текст задачи (или напишите 'отмена' для выхода):")
    bot.register_next_step_handler(message, send_task_to_performers, message.chat.id)


def send_task_to_performers(message, admin_chat_id):
    """Обрабатывает введенный текст задачи, отменяет команду, если введено 'отмена'."""
    if message.text.lower() == "отмена":
        bot.send_message(admin_chat_id, "🚫 Создание задачи отменено.")
        return  # Завершаем обработчик

    task_text = message.text  # Получаем текст задания
    total_sent = 0  # Счетчик успешно отправленных сообщений

    for performers, tasks_text in config.control_panel.items():
        for performer in performers:
            try:
                bot.send_message(performer, f"📌 *Новое задание:*\n{task_text}", parse_mode="Markdown")
                bot.send_message(performer, "📷 Отправьте фото выполнения.")
                task_data[performer] = {"task_text": task_text}
                total_sent += 1  # Увеличиваем счетчик
            except telebot.apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in str(e):
                    print(f"⚠ Бот заблокирован пользователем {performer}.")
                else:
                    print(f"⚠ Ошибка при отправке задания пользователю {performer}: {e}")

    # ✅ Отправляем подтверждение администратору
    if total_sent > 0:
        bot.send_message(admin_chat_id, f"✅ Задача успешно отправлена {total_sent} сотрудникам!")
    else:
        bot.send_message(admin_chat_id, "⚠ Никому не удалось отправить задачу.")


# ========= Получение фото от исполнителя =========
@bot.message_handler(content_types=['photo'])
def receive_photo(message):
    user_id = message.from_user.id
    if user_id not in sum(config.control_panel.keys(), ()):  # Проверка, что исполнитель из одной из групп
        bot.send_message(message.chat.id, "⛔ Вы не числитесь в контрольной панели.", parse_mode="HTML")
        return

    photo = message.photo[-1].file_id

    # Попытаемся получить текст задачи для исполнителя; если нет — используем заглушку.
    task_text = task_data.get(user_id, {}).get("task_text", "_")
    username = message.from_user.username or f"ID: {user_id}"

    # Отправляем фото в контрольный чат без inline-кнопок для получения ID сообщения
    sent_message = bot.send_photo(
        config.control_chat_id,
        photo,
        caption=f"📝 <b>Задача:</b> {task_text}\n👤 <b>{username}</b>",
        parse_mode="HTML"
    )

    # Формируем inline-клавиатуру с кнопками "✅ Принять" и "❌ Отклонить"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Принять", callback_data=f"accept_{sent_message.message_id}_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{sent_message.message_id}_{user_id}")
    )

    # Редактируем сообщение в контрольном чате, добавляя клавиатуру
    bot.edit_message_reply_markup(chat_id=config.control_chat_id, message_id=sent_message.message_id, reply_markup=keyboard)

    # Сохраняем данные о сообщении в task_data (ключ – ID сообщения в контрольном чате)
    task_data[sent_message.message_id] = {
        "user_id": user_id,
        "user_message_id": message.message_id,
        "control_chat_id": config.control_chat_id,
        "task_text": task_text
    }

    # Подтверждаем пользователю, что фото отправлено
    bot.send_message(message.chat.id, "✅ <b>Фото отправлено на проверку!</b>", parse_mode="HTML")

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