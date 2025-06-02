# bot.py

import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
import openpyxl
import os
from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, get_user_role, add_start_session, add_end_session, \
    get_last_open_session, get_sessions_by_month, get_all_sessions_by_month

logging.basicConfig(level=logging.INFO)

# --- Настройка клавиатуры ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Начать рабочий день")],
        [KeyboardButton("Закончить рабочий день")],
        [KeyboardButton("Получить отчет")]
    ], resize_keyboard=True)

main_keyboard = get_main_keyboard()

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите действие:", reply_markup=main_keyboard)

# --- Обработка текстовых команд ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "Начать рабочий день":
        last_session = get_last_open_session(user_id)
        if last_session:
            await update.message.reply_text("Вы уже начали рабочий день.")
            return

        confirm_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("Подтвердить начало")],
            [KeyboardButton("Отменить")]
        ], resize_keyboard=True)

        await update.message.reply_text("Вы хотите начать рабочий день?", reply_markup=confirm_keyboard)

    elif text == "Закончить рабочий день":
        last_session = get_last_open_session(user_id)
        if not last_session:
            await update.message.reply_text("Вы не начали рабочий день.")
            return

        confirm_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("Подтвердить завершение")],
            [KeyboardButton("Отменить")]
        ], resize_keyboard=True)

        await update.message.reply_text("Вы хотите закончить рабочий день?", reply_markup=confirm_keyboard)

    elif text == "Получить отчет":
        await update.message.reply_text(
            "Введите:\n"
            "/report_current - текущий месяц\n"
            "/report_last - прошлый месяц\n"
            "/report_all <год-месяц> - за указанный месяц"
        )

    elif text == "Подтвердить начало":
        location_button = KeyboardButton("Отправить местоположение", request_location=True)
        markup = ReplyKeyboardMarkup([[location_button]], one_time_keyboard=True)
        await update.message.reply_text("Поделитесь своим местоположением:", reply_markup=markup)
        context.user_data['action'] = 'start'

    elif text == "Подтвердить завершение":
        location_button = KeyboardButton("Отправить местоположение", request_location=True)
        markup = ReplyKeyboardMarkup([[location_button]], one_time_keyboard=True)
        await update.message.reply_text("Поделитесь своим местоположением:", reply_markup=markup)
        context.user_data['action'] = 'end'

    elif text == "Отменить":
        await update.message.reply_text("Действие отменено.", reply_markup=main_keyboard)

    else:
        # Неизвестная команда — возвращаем главное меню
        await update.message.reply_text("Неизвестное действие.", reply_markup=main_keyboard)

# --- Получение геолокации ---
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    location = f"{lat}, {lon}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    action = context.user_data.get('action')
    if action == 'start':
        add_start_session(user_id, location)
        await update.message.reply_text("Рабочий день начат.", reply_markup=main_keyboard)
        asyncio.create_task(start_reminders(user_id, context))

    elif action == 'end':
        add_end_session(user_id, location)
        await update.message.reply_text("Рабочий день окончен.", reply_markup=main_keyboard)

    context.user_data.pop('action', None)

# --- Напоминания ---
async def start_reminders(user_id, context):
    while True:
        last_session = get_last_open_session(user_id)
        if not last_session:
            break
        try:
            start_time = datetime.strptime(last_session[0], "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            start_time = datetime.strptime(last_session[0], "%Y-%m-%d %H:%M:%S")

        duration = (datetime.now() - start_time).total_seconds() / 3600
        if duration >= 9:
            await context.bot.send_message(chat_id=user_id, text="⚠️ Вы работаете больше 9 часов. Завершите день.")
            break
        await asyncio.sleep(3600)

# --- Отчеты ---
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user_id = update.effective_user.id

    if not args:
        await update.message.reply_text("Используйте: /report_current, /report_last или /report_all <год-месяц>")
        return

    period = args[0]

    if period == "current":
        month = datetime.now().strftime("%Y-%m")
    elif period == "last":
        prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        month = prev_month
    else:
        month = period

    sessions = get_sessions_by_month(user_id, month)

    if not sessions:
        await update.message.reply_text(f"Нет данных за {month}.")
        return

    day_summary = {}
    total_hours = 0

    for s in sessions:
        try:
            start = datetime.strptime(s[2], "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            start = datetime.strptime(s[2], "%Y-%m-%d %H:%M:%S")

        if s[3]:
            try:
                end = datetime.strptime(s[3], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                end = datetime.strptime(s[3], "%Y-%m-%d %H:%M:%S")

            hours = (end - start).total_seconds() / 3600
            total_hours += hours
            day_key = start.strftime("%Y-%m-%d")
            day_summary[day_key] = round(day_summary.get(day_key, 0) + hours, 2)

    if period in ["current", "last"]:
        msg = "\n".join([f"{day}: {hours} ч." for day, hours in day_summary.items()])
    else:
        msg = f"{month}: {round(total_hours, 2)} ч."

    await update.message.reply_text(msg)

# --- Админская часть: экспорт в Excel ---
async def export_excel_report(context, month):
    sessions = get_all_sessions_by_month(month)
    if not sessions:
        return None

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Дата", "Время начала", "Гео-начала", "Время окончания", "Гео-окончания", "Часов"])

    total = 0
    for s in sessions:
        try:
            start = datetime.strptime(s[2], "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            start = datetime.strptime(s[2], "%Y-%m-%d %H:%M:%S")

        if s[3]:
            try:
                end = datetime.strptime(s[3], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                end = datetime.strptime(s[3], "%Y-%m-%d %H:%M:%S")

            hours = round((end - start).total_seconds() / 3600, 2)
            total += hours
            ws.append([
                start.strftime("%Y-%m-%d"),
                start.strftime("%H:%M"),
                s[4],
                end.strftime("%H:%M"),
                s[5],
                hours
            ])

    ws.append(["", "", "", "", "Итого", round(total, 2)])
    filename = f"report_{month}.xlsx"
    wb.save(filename)
    return filename

async def admin_excel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой функции.")
        return

    if not context.args:
        await update.message.reply_text("Используйте: /export <год-месяц>")
        return

    month = context.args[0]
    file_path = await export_excel_report(context, month)
    if not file_path:
        await update.message.reply_text("Нет данных за указанный период.")
        return

    with open(file_path, "rb") as f:
        await update.message.reply_document(document=f)
    os.remove(file_path)

# --- Запуск бота ---
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CommandHandler("report_current", lambda u, c: report_command_wrapper(u, c, "current")))
    app.add_handler(CommandHandler("report_last", lambda u, c: report_command_wrapper(u, c, "last")))
    app.add_handler(CommandHandler("report_all", lambda u, c: report_command_wrapper(u, c, "all")))
    app.add_handler(CommandHandler("export", admin_excel_report))

    async def report_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
        context.args = [period]
        await report_command(update, context)

    print("Бот запущен...")
    app.run_polling()