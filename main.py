# Стандартні бібліотеки Python
import asyncio
import sqlite3
import os
from datetime import datetime

# Бібліотека python-telegram-bot
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ExtBot
)
# ВАШ ТОКЕН
# Беремо токен з системної змінної. Це безпечніше.
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Необхідно встановити змінну оточення TELEGRAM_TOKEN")

# Список ID користувачів, які мають доступ до бота
ALLOWED_USER_IDS = [285168148, 6300922224, 1365817032]

# ID власника бота, який має розширені права
OWNER_ID = 285168148

async def post_init(application: Application) -> None:
    """Налаштовує меню команд: базове для всіх і розширене для власника."""
    
    # Створюємо список команд для звичайних користувачів
    user_commands = [
        BotCommand("start", "Перезапустити бота"),
        BotCommand("stats", "Показати статистику"),
        BotCommand("getid", "Дізнатися свій ID")
    ]
    
    # Створюємо розширений список команд для власника
    owner_commands = [
        BotCommand("start", "Перезапустити бота"),
        BotCommand("stats", "Показати статистику"),
        BotCommand("getid", "Дізнатися свій ID"),
        BotCommand("backup", "Завантажити базу даних"),
        BotCommand("edit", "Редагувати запис (ID сума категорія)"),
        BotCommand("del", "Видалити запис (ID)"),
        BotCommand("reset", "❗️ Скинути всі дані"),
    ]

    # КРОК 1: Встановлюємо базове меню як глобальне для всіх користувачів.
    print("Встановлюємо базове меню для всіх...")
    await application.bot.set_my_commands(user_commands)
    
    # КРОК 2: Встановлюємо розширене меню персонально для власника.
    # Для цього використовуємо scope=BotCommandScopeChat(chat_id=OWNER_ID),
    # що вказує Telegram, що це меню лише для конкретного чату.
    print(f"Встановлюємо розширене меню для власника (ID: {OWNER_ID})...")
    await application.bot.set_my_commands(owner_commands, scope=BotCommandScopeChat(chat_id=OWNER_ID))
    
    print("Меню команд налаштовано.")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Повертає користувачу його унікальний Telegram ID."""
    #print(f"!!! Користувач {update.effective_user.id} викликав команду /myid !!!")
    user_id = update.effective_user.id
    await update.message.reply_text(f"Ваш Telegram ID: {user_id}")

def init_db():
    """Створює базу даних та таблицю, якщо їх ще не існує."""
    conn = sqlite3.connect('finance.db') # Створює або підключається до файлу finance.db
    cursor = conn.cursor()
    
    # Створюємо таблицю 'expenses' з потрібними нам колонками
    # IF NOT EXISTS - важлива частина, щоб не було помилки при повторному запуску
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    
    conn.commit() # Зберігаємо зміни
    conn.close()  # Закриваємо з'єднання

def reorder_ids_and_reset_sequence():
    """
    Перестворює таблицю expenses та примусово скидає лічильник ID.
    НЕ РЕКОМЕНДУЄТЬСЯ ДЛЯ ВИРОБНИЧОГО ВИКОРИСТАННЯ.
    """
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('BEGIN TRANSACTION;')
        
        # 1. Створюємо тимчасову таблицю
        cursor.execute('''
            CREATE TABLE expenses_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 2. Копіюємо дані
        cursor.execute('''
            INSERT INTO expenses_new (amount, category, created_at)
            SELECT amount, category, created_at FROM expenses ORDER BY id ASC
        ''')
        
        # 3. Видаляємо стару таблицю
        cursor.execute('DROP TABLE expenses')
        
        # 4. Перейменовуємо нову
        cursor.execute('ALTER TABLE expenses_new RENAME TO expenses')
        
        # 5. !!! КЛЮЧОВИЙ КРОК !!!
        # Оновлюємо системний лічильник. Ми встановлюємо його на значення
        # останнього ID в нашій новій таблиці.
        cursor.execute("UPDATE sqlite_sequence SET seq = (SELECT MAX(id) FROM expenses) WHERE name='expenses'")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"Помилка при перенумерації ID: {e}")
    finally:
        conn.close()

def add_expense(amount: float, category: str):
    """Додає новий запис про витрату в базу даних."""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Отримуємо поточну дату та час у вигляді тексту
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Виконуємо SQL-команду для вставки даних
    # Знаки ? - це безпечний спосіб передати дані в запит
    cursor.execute('INSERT INTO expenses (amount, category, created_at) VALUES (?, ?, ?)',
                   (amount, category, created_at))
    
    conn.commit()
    conn.close()

def delete_expense(record_id: int):
    """Видаляє запис з бази даних за його ID."""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM expenses WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    reorder_ids_and_reset_sequence()

def get_statistics():
    """Отримує всі записи та загальну суму з бази даних."""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Отримуємо всі записи, сортуючи їх за ID від найновіших до найстаріших    
    cursor.execute('SELECT id, amount, category, created_at FROM expenses ORDER BY id ASC')
    records = cursor.fetchall()
    
    # Рахуємо загальну суму всіх записів
    cursor.execute('SELECT SUM(amount) FROM expenses')
    # fetchone()[0] отримує результат з першої колонки першого рядка
    total_sum = cursor.fetchone()[0]
    
    conn.close()
    
    # Якщо в базі ще немає записів, сума буде None. Замінимо її на 0.
    if total_sum is None:
        total_sum = 0
        
    return records, total_sum

def edit_expense(record_id: int, new_amount: float, new_category: str):
    """Оновлює суму та категорію існуючого запису."""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE expenses SET amount = ?, category = ? WHERE id = ?',
                   (new_amount, new_category, record_id))
    conn.commit()
    conn.close()

# Функція, яка буде викликатись при команді /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Привіт, {user_name}! Я ваш особистий фінансовий бот.")

# Функція для очистки бази даних
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Видаляє запис за його ID. Формат: /del ID"""
    try:
        # context.args - це список слів, що йдуть після команди
        record_id = int(context.args[0])
        delete_expense(record_id)
        await update.message.reply_text(f"✅ Запис з ID {record_id} було успішно видалено.")
    except (IndexError, ValueError):
        # Помилка виникне, якщо після /del нічого не вказали, або вказали не число
        await update.message.reply_text("Будь ласка, вкажіть ID запису для видалення. Наприклад: `/del 123`")

# Фунція для виводу усієї статистики
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Надсилає статистику витрат."""
    records, total_sum = get_statistics()
    
    if not records:
        await update.message.reply_text("База даних порожня. Ще немає жодного запису.")
        return
        
    # Починаємо формувати текст повідомлення з заголовка
    message = "📖 <b>Історія операцій:</b>\n"
    
    # Спочатку додаємо у повідомлення всі записи
    for record in records:
        record_id, amount, category, created_at = record
        date_obj = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        formatted_date = date_obj.strftime('%d.%m.%Y')
        
        message += f"<code>{record_id}) </code><code>{amount:.2f}</code>  {category} ({formatted_date})\n"
        
    # А тепер, в самому кінці, додаємо загальний баланс
    message += f"\n📊 <b>Загальний баланс:</b> {total_sum:.2f} грн"

    # Надсилаємо повідомлення
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

# Функція, яка "слухає" всі текстові повідомлення
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробляє текстові повідомлення для додавання витрат."""
    # ПЕРЕВІРКА: тільки власник може додавати записи
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Вибачте, додавати витрати може лише власник бота.")
        return # Виходимо з функції, якщо це не власник
        
    text = update.message.text
    
    try:
        # Розділяємо повідомлення на частини: перше слово - сума, решта - категорія
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await update.message.reply_text("Будь ласка, вкажіть суму та категорію. Наприклад: `-150 Продукти`")
            return

        amount_str = parts[0].replace(',', '.') # Дозволяємо вводити суму через кому
        category = parts[1]
        amount = float(amount_str)
        
        # Викликаємо нашу функцію, щоб додати запис у базу даних
        add_expense(amount, category)
        
        await update.message.reply_text(f"✅ Запис додано: {amount} грн на '{category}'")

    except ValueError:
        # Ця помилка виникне, якщо перше слово - не число
        await update.message.reply_text("Помилка! Сума має бути числом. Наприклад: `50` або `-25.5`.")
    except Exception as e:
        # Обробка інших можливих помилок
        print(f"Сталася непередбачувана помилка: {e}")
        await update.message.reply_text("Ой, щось пішло не так. Спробуйте ще раз.")

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Редагує запис. Формат: /edit ID нова_сума нова_категорія"""
    try:
        # context.args - це список слів, що йдуть після команди.
        # Наприклад, для "/edit 15 -250.5 Продукти" це буде ['15', '-250.5', 'Продукти']
        
        if len(context.args) < 3:
            raise ValueError("Недостатньо аргументів.")

        record_id = int(context.args[0])
        new_amount_str = context.args[1].replace(',', '.')
        new_amount = float(new_amount_str)
        
        # Всі слова після ID та суми об'єднуємо в одну категорію
        new_category = ' '.join(context.args[2:])
        
        edit_expense(record_id, new_amount, new_category)
        
        await update.message.reply_text(f"✅ Запис з ID {record_id} було успішно оновлено.")

    except (ValueError, IndexError):
        # Помилка виникне, якщо формат команди неправильний
        await update.message.reply_text(
            "Неправильний формат команди.\n"
            "Будь ласка, використовуйте: `/edit ID нова_сума Нова категорія`\n"
            "Наприклад: `/edit 15 -250.5 Продукти на тиждень`"
        )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищує базу даних після підтвердження."""
    # Перевіряємо, чи є аргументи і чи перший з них - 'confirm'
    if context.args and context.args[0].lower() == 'confirm':
        reset_database()
        await update.message.reply_text("✅ Всі дані були успішно видалені. База даних порожня.")
    else:
        # Якщо підтвердження немає, надсилаємо попередження
        await update.message.reply_text(
            "❗️<b>УВАГА!</b>❗️\n"
            "Ця команда повністю видалить всю історію операцій.\n"
            "Цю дію неможливо буде скасувати.\n\n"
            "Якщо ви впевнені, надішліть команду ще раз у такому форматі:\n"
            "`/reset confirm`",
            parse_mode=ParseMode.HTML
        )

def reset_database():
    """Видаляє всі записи з таблиці expenses та скидає лічильник ID."""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Крок 1: Видаляємо всі записи з таблиці
    cursor.execute('DELETE FROM expenses')
    
    # Крок 2: Скидаємо лічильник автоінкременту для цієї таблиці
    # Ця команда видаляє запис про 'expenses' із системної таблиці лічильників
    cursor.execute('DELETE FROM sqlite_sequence WHERE name="expenses"')
    
    conn.commit()
    conn.close()

# Функція, що повертає телеграм ID користувача
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Повертає користувачу його унікальний Telegram ID."""
    #print(f"!!! Користувач {update.effective_user.id} викликав команду /getid !!!")
    user_id = update.effective_user.id
    await update.message.reply_text(f"Ваш Telegram ID: {user_id}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Надсилає файл бази даних власнику."""
    try:
        with open('finance.db', 'rb') as doc:
            await update.message.reply_document(document=doc, filename='finance.db')
    except FileNotFoundError:
        await update.message.reply_text("Файл бази даних не знайдено.")


if __name__ == '__main__':
    # Викликаємо функцію для створення БД при старті
    init_db()

    # Створюємо Application
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Рядок для відлагодження
    #print(f"--- DEBUG: Реєструємо обробники. Дозволені ID: {ALLOWED_USER_IDS}")
    application.add_handler(CommandHandler("getid", get_id))

    # ----- Реєстрація всіх ваших обробників команд -----
    application.add_handler(CommandHandler("start", start, filters=filters.User(user_id=ALLOWED_USER_IDS)))
    application.add_handler(CommandHandler("stats", stats, filters=filters.User(user_id=ALLOWED_USER_IDS)))    
    
    # Обробники тільки для власника
    application.add_handler(CommandHandler("backup", backup_command, filters=filters.User(user_id=OWNER_ID)))
    application.add_handler(CommandHandler("del", del_command, filters=filters.User(user_id=OWNER_ID)))
    application.add_handler(CommandHandler("edit", edit_command, filters=filters.User(user_id=OWNER_ID)))
    application.add_handler(CommandHandler("reset", reset_command, filters=filters.User(user_id=OWNER_ID)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(user_id=OWNER_ID), handle_message))

    # Запускаємо бота. Цей метод сам керує асинхронним циклом.
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get('PORT', 8443)),        
        webhook_url=os.environ.get("WEBHOOK_URL")
    )