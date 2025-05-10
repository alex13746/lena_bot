import os
import logging
import re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# ── Загрузка .env ──────────────────────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
if not TOKEN or not GOOGLE_SHEET_ID:
    raise RuntimeError("Убедитесь, что в .env заданы TOKEN и GOOGLE_SHEET_ID")

# ── Логирование ────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Состояния ──────────────────────────────────────────────────────────────────
(
    START_MENU,
    NAME,
    CLASS,
    SUBJECT,
    TOPIC,
    CONTACT,
    PHONE,
    EMAIL,
    DATES,
    TIME,
    LEAVE_REQUEST,
    REPEAT
) = range(12)

user_data = {}

# ── Google Sheets ──────────────────────────────────────────────────────────────
def get_workbook():
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds).open_by_key(GOOGLE_SHEET_ID)

def get_main_sheet():
    return get_workbook().sheet1

# ── Нормализация телефона ─────────────────────────────────────────────────────
def normalize_phone(txt: str) -> str | None:
    digits = re.findall(r"\d", txt)
    s = "".join(digits)
    if len(s) == 11 and s.startswith("8"):
        return "+7" + s[1:]
    if len(s) == 11 and s.startswith("7"):
        return "+" + s
    if len(s) == 10:
        return "+7" + s
    return None

# ── Текст подтверждения ───────────────────────────────────────────────────────
def get_confirmation_text(data: dict) -> str:
    contacts = "; ".join(f"{k}: {v}" for k, v in data.get("contact", {}).items())
    return (
        "📝 Ваша заявка:\n"
        f"▫️ Имя: {data.get('name','не указано')}\n"
        f"▫️ Класс: {data.get('class','не указан')}\n"
        f"▫️ Предмет: {data.get('subject','не указан')}\n"
        f"▫️ Тема: {data.get('topic','не указана')}\n"
        f"▫️ Дата: {data.get('time','не указана')}\n"
        f"▫️ Контакты: {contacts}\n\n"
        "⚠️ Сохраните это сообщение."
    )

# ── /start ───────────────────────────────────────────────────────────────────
async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([["Записаться на занятия"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Добро пожаловать! Нажмите кнопку:", reply_markup=kb)
    return START_MENU

# ── Шаг 1: имя ────────────────────────────────────────────────────────────────
async def start_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    u = update.effective_user
    user_data[cid] = {
        "first_name": u.first_name or "",
        "last_name": u.last_name or "",
        "username": u.username or "",
        "contact": {}
    }
    await update.message.reply_text("📝 Введите ваше имя:", reply_markup=ReplyKeyboardRemove())
    return NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_data[cid]["name"] = update.message.text.strip()
    kb = [["6","7","8"],["9","10","11"]]
    await update.message.reply_text("Выберите класс:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
    return CLASS

# ── Шаг 2: класс ──────────────────────────────────────────────────────────────
async def handle_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_data[cid]["class"] = update.message.text.strip()
    kb = [["Геометрия","Алгебра"],["Стереометрия"]]
    await update.message.reply_text("Выберите предмет:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
    return SUBJECT

# ── Шаг 3: предмет ────────────────────────────────────────────────────────────
async def handle_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_data[cid]["subject"] = update.message.text.strip()
    await update.message.reply_text("📖 Укажите тему занятия:", reply_markup=ReplyKeyboardRemove())
    return TOPIC

# ── Шаг 4: тема ───────────────────────────────────────────────────────────────
async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_data[cid]["topic"] = update.message.text.strip()
    # кнопки всегда видны: one_time_keyboard=False
    kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("📞 Выберите способ связи или «Готово»:", reply_markup=kb)
    return CONTACT

# ── Шаг 5: контакт ────────────────────────────────────────────────────────────
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    choice = update.message.text.strip()
    data = user_data[cid]

    if choice == "Telegram":
        full = f"{data['first_name']} {data['last_name']}".strip()
        data["contact"]["Telegram"] = full or f"@{data['username']}"
        await update.message.reply_text(f"Добавлено Telegram: {data['contact']['Telegram']}")
        return CONTACT

    if choice == "Телефон":
        kb = ReplyKeyboardMarkup([["Пропустить"],["Telegram","Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Введите номер или «Пропустить»:", reply_markup=kb)
        return PHONE

    if choice == "Email":
        kb = ReplyKeyboardMarkup([["Пропустить"],["Telegram","Телефон","Готово"]], resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Введите email или «Пропустить»:", reply_markup=kb)
        return EMAIL

    if choice == "Готово":
        return await handle_dates(update, context)

    # неверный ввод — повторяем клавиатуру
    kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Пожалуйста, выберите кнопку на клавиатуре.", reply_markup=kb)
    return CONTACT

# ── Шаг 6: телефон ────────────────────────────────────────────────────────────
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    txt = update.message.text.strip().lower()
    if txt == "пропустить":
        kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Продолжаем без телефона. Выберите способ:", reply_markup=kb)
        return CONTACT
    norm = normalize_phone(txt)
    if not norm:
        await update.message.reply_text("❌ Неверный номер! Попробуйте снова или «Пропустить»:")
        return PHONE
    user_data[cid]["contact"]["Телефон"] = norm
    kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(f"Добавлено Телефон: {norm}\nДругой способ или «Готово»?", reply_markup=kb)
    return CONTACT

# ── Шаг 7: email ─────────────────────────────────────────────────────────────
async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    txt = update.message.text.strip().lower()
    if txt == "пропустить":
        kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Продолжаем без email. Выберите способ:", reply_markup=kb)
        return CONTACT
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", txt):
        await update.message.reply_text("❌ Неверный email! Попробуйте снова или «Пропустить»:")
        return EMAIL
    user_data[cid]["contact"]["Email"] = txt
    kb = ReplyKeyboardMarkup([["Telegram","Телефон"],["Email","Готово"]], resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(f"Добавлено Email: {txt}\nДругой способ или «Готово»?", reply_markup=kb)
    return CONTACT

# ── Шаг 8: выбор листа по дате ─────────────────────────────────────────────────
async def handle_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    try:
        tabs = [ws.title for ws in get_workbook().worksheets()]
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Ошибка доступа к таблице.")
        return ConversationHandler.END

    kb = ReplyKeyboardMarkup([[t] for t in tabs], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите дату:", reply_markup=kb)
    return TIME

# ── Шаги 9+10: выбор времени и запись в лист ───────────────────────────────────
async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    text = update.message.text.strip()
    data = user_data[cid]

    if "selected_date" not in data:
        data["selected_date"] = text
        try:
            sheet = get_workbook().worksheet(text)
            recs = sheet.get_all_records()
        except Exception as e:
            logger.error(e)
            await update.message.reply_text("Не удалось открыть лист.")
            return ConversationHandler.END

        times = [r["time"] for r in recs if str(r.get("status","")).lower()=="available"]
        if not times:
            kb = ReplyKeyboardMarkup([["Да","Нет"]], resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("⏳ Нет свободного времени. Оставить заявку?", reply_markup=kb)
            return LEAVE_REQUEST

        kb = ReplyKeyboardMarkup([[t] for t in times], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите время:", reply_markup=kb)
        return TIME

    # запись брони
    chosen_time = text
    date_tab = data.pop("selected_date")
    data["time"] = f"{date_tab} {chosen_time}"
    contacts_str = "; ".join(f"{k}: {v}" for k, v in data["contact"].items())

    try:
        sheet = get_workbook().worksheet(date_tab)
        recs = sheet.get_all_records()
        for idx, r in enumerate(recs, start=2):
            if r.get("time") == chosen_time:
                sheet.update_cell(idx, 3, "booked")
                sheet.update_cell(idx, 4, data["name"])
                sheet.update_cell(idx, 5, data["subject"])
                sheet.update_cell(idx, 6, data["topic"])
                sheet.update_cell(idx, 7, contacts_str)
                break
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Ошибка записи в таблицу.")
        return ConversationHandler.END

    await update.message.reply_text(get_confirmation_text(data), reply_markup=ReplyKeyboardRemove())
    kb = ReplyKeyboardMarkup([["Начать заново"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Чтобы начать заново, нажмите кнопку:", reply_markup=kb)
    return START_MENU

# ── Шаг 11: ожидание заявки без времени ────────────────────────────────────────
async def handle_leave_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    ans = update.message.text.strip().lower()
    data = user_data.get(cid, {})

    if ans == "да":
        try:
            main = get_main_sheet()
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.now().strftime("%H:%M")
            contacts_str = "; ".join(f"{k}: {v}" for k, v in data["contact"].items())
            main.append_row([date_str, time_str, "pending", data["name"],
                             data["subject"], data["topic"], contacts_str])
        except Exception as e:
            logger.error(e)
        await update.message.reply_text("✅ Заявка сохранена.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(get_confirmation_text(data))

    kb = ReplyKeyboardMarkup([["Начать заново"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Чтобы начать заново, нажмите кнопку:", reply_markup=kb)
    user_data.pop(cid, None)
    return START_MENU

# ── Конфиг бота ────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_menu),
            MessageHandler(filters.Regex(r"^(Записаться на занятия|Начать заново)$"), start_record)
        ],
        states={
            START_MENU:    [MessageHandler(filters.Regex(r"^(Записаться на занятия|Начать заново)$"), start_record)],
            NAME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            CLASS:         [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_class)],
            SUBJECT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_subject)],
            TOPIC:         [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_topic)],
            CONTACT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact)],
            PHONE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            EMAIL:         [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            DATES:         [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dates)],
            TIME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time)],
            LEAVE_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_leave_request)],
            REPEAT:        [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_leave_request)],
        },
        fallbacks=[]
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
