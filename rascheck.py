import os
import re
import calendar
import logging
from datetime import datetime, timedelta, date
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest
from persiantools.jdatetime import JalaliDate

# تنظیمات logging (به شما کمک می‌کند تا لاگ‌ها را در کنسول یا فایل مشاهده کنید)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن بات خود را جایگزین کنید
TOKEN = "7987671225:AAEtMnYVnkrHTlwCVKO18cj3QuRqd88RRew"
# شناسه چت مدیر جهت ارسال گزارش (آیدی عددی چت مدیر یا کانال)
ADMIN_CHAT_ID = 7897179800  # مقدار مناسب را جایگزین کنید

# تعریف stateهای گفتگو
(ASK_BASE_DATE, ASK_CHECK_COUNT, ASK_AMOUNT, ASK_DUE_DATE, ASK_FEE_RATE, CONFIRM) = range(6)

# لیست نام ماه‌های شمسی
persian_months = [
    "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# ===================== ساخت تقویم شمسی تعاملی =====================
def build_calendar_persian(j_year: int, j_month: int, callback_prefix: str = "DAY") -> InlineKeyboardMarkup:
    keyboard = []
    header_text = f"{persian_months[j_month]} ({j_month}) {j_year}"
    keyboard.append([InlineKeyboardButton(header_text, callback_data="IGNORE")])
    
    week_days = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    keyboard.append([InlineKeyboardButton(day, callback_data="IGNORE") for day in week_days])
    
    if j_month <= 6:
        num_days = 31
    elif j_month <= 11:
        num_days = 30
    else:
        try:
            is_leap = JalaliDate(j_year, 12, 1).is_leap_year()
        except Exception:
            is_leap = False
        num_days = 30 if is_leap else 29

    first_day_g = JalaliDate(j_year, j_month, 1).to_gregorian()
    start_index = (first_day_g.weekday() + 2) % 7

    row = []
    for _ in range(start_index):
        row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
    for day in range(1, num_days + 1):
        row.append(InlineKeyboardButton(str(day), callback_data=f"{callback_prefix}-{j_year}-{j_month}-{day}"))
        if len(row) == 7:
            keyboard.append(row)
            row = []
    if row:
        while len(row) < 7:
            row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("< ماه قبل", callback_data=f"PREV-{j_year}-{j_month}"),
        InlineKeyboardButton("ماه بعد >", callback_data=f"NEXT-{j_year}-{j_month}")
    ])
    
    return InlineKeyboardMarkup(keyboard)

# ===================== Callback های تقویم =====================
async def base_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info("Base date callback data: %s", data)

    if data == "IGNORE":
        return

    if data.startswith("DAY-"):
        _, jy, jm, jd = data.split("-")
        try:
            j_year = int(jy)
            j_month = int(jm)
            j_day = int(jd)
        except Exception:
            await query.edit_message_text("تاریخ انتخاب شده نامعتبر است.")
            return
        selected_date = JalaliDate(j_year, j_month, j_day).to_gregorian()
        context.user_data["base_date"] = datetime(selected_date.year, selected_date.month, selected_date.day)
        selected_j_date = JalaliDate(j_year, j_month, j_day).isoformat()
        await query.edit_message_text(
            f"تاریخ انتخاب شده: {selected_j_date}\n\n"
            "لطفاً تعداد چک‌ها را وارد کنید (عدد صحیح بزرگتر از صفر):",
            parse_mode=ParseMode.MARKDOWN
        )
        return ASK_CHECK_COUNT

    if data.startswith("PREV-") or data.startswith("NEXT-"):
        _, jy, jm = data.split("-")
        j_year = int(jy)
        j_month = int(jm)
        if data.startswith("PREV-"):
            j_month = 12 if j_month == 1 else j_month - 1
            if j_month == 12: j_year -= 1
        else:
            j_month = 1 if j_month == 12 else j_month + 1
            if j_month == 1: j_year += 1
        new_markup = build_calendar_persian(j_year, j_month, callback_prefix="DAY")
        try:
            await query.edit_message_reply_markup(reply_markup=new_markup)
        except BadRequest as e:
            logger.error("Edit reply markup error in base_date_callback: %s", e)
        return

async def due_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info("Due date callback data: %s", data)
    if data == "IGNORE":
        return

    if data.startswith("DUE-"):
        _, jy, jm, jd = data.split("-")
        try:
            j_year = int(jy)
            j_month = int(jm)
            j_day = int(jd)
        except Exception:
            await query.edit_message_text("تاریخ انتخاب شده نامعتبر است.")
            return
        selected_due_date = JalaliDate(j_year, j_month, j_day).to_gregorian()
        due_dt = datetime(selected_due_date.year, selected_due_date.month, selected_due_date.day)
        base_dt = context.user_data["base_date"]
        diff_days = (due_dt - base_dt).days

        current_index = context.user_data["current_check"] - 1
        context.user_data["checks"][current_index]["due_date"] = due_dt
        context.user_data["checks"][current_index]["diff"] = diff_days

        # ایجاد پیام تأیید با فرمت: "مبلغ: <amount> ریال    تاریخ: yyyy/mm/dd"
        current_amount = context.user_data["checks"][current_index]["amount"]
        j_due = JalaliDate.to_jalali(due_dt.year, due_dt.month, due_dt.day)
        due_date_str = f"{j_due.year}/{j_due.month:02d}/{j_due.day:02d}"
        confirmation_text = f"مبلغ: {current_amount:,.0f} ریال    تاریخ: {due_date_str}"

        if context.user_data["current_check"] < context.user_data["count"]:
            context.user_data["current_check"] += 1
            try:
                await query.edit_message_text(
                    f"{confirmation_text}\n\nتاریخ سررسید چک ثبت شد.\n\nلطفاً مبلغ چک شماره {context.user_data['current_check']} را وارد کنید:",
                    parse_mode=ParseMode.MARKDOWN
                )
            except BadRequest as e:
                logger.error("Edit message error in due_date_callback: %s", e)
            return ASK_AMOUNT
        else:
            try:
                await query.edit_message_text(
                    f"{confirmation_text}\n\nتمام تاریخ‌های سررسید ثبت شدند.\n\nلطفاً درصد کارمزد ماهانه را وارد کنید (مثلاً `5` به معنی 5 درصد):",
                    parse_mode=ParseMode.MARKDOWN
                )
            except BadRequest as e:
                logger.error("Edit message error in due_date_callback: %s", e)
            return ASK_FEE_RATE

    if data.startswith("PREV-") or data.startswith("NEXT-"):
        _, jy, jm = data.split("-")
        j_year = int(jy)
        j_month = int(jm)
        if data.startswith("PREV-"):
            j_month = 12 if j_month == 1 else j_month - 1
            if j_month == 12: j_year -= 1
        else:
            j_month = 1 if j_month == 12 else j_month + 1
            if j_month == 1: j_year += 1
        new_markup = build_calendar_persian(j_year, j_month, callback_prefix="DUE")
        try:
            await query.edit_message_reply_markup(reply_markup=new_markup)
        except BadRequest as e:
            logger.error("Edit reply markup error in due_date_callback: %s", e)
        return

# ===================== مراحل گفتگو =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Entered start_command")
    context.user_data.clear()
    j_today = JalaliDate.to_jalali(date.today().year, date.today().month, date.today().day)
    calendar_markup = build_calendar_persian(j_today.year, j_today.month, callback_prefix="DAY")
    await update.message.reply_text(
        "سلام! این ربات برای محاسبه راس چک طراحی شده است.\n\n"
        "لطفاً تاریخ شروع راس را از روی تقویم انتخاب کنید:",
        reply_markup=calendar_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_BASE_DATE

async def ask_check_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Entered ask_check_count")
    text = update.message.text.strip()
    logger.info("Received check count: %s", text)
    if not text.isdigit():
        await update.message.reply_text("لطفاً یک عدد صحیح وارد کنید.")
        return ASK_CHECK_COUNT
    count = int(text)
    if count <= 0:
        await update.message.reply_text("تعداد چک‌ها باید بزرگتر از صفر باشد.")
        return ASK_CHECK_COUNT
    context.user_data["count"] = count
    context.user_data["checks"] = []
    context.user_data["current_check"] = 1
    await update.message.reply_text(
        "مبلغ چک شماره 1 را وارد کنید:",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Moving to state ASK_AMOUNT")
    return ASK_AMOUNT

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Entered ask_amount")
    text = update.message.text.strip()
    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر برای مبلغ وارد کنید.")
        return ASK_AMOUNT

    context.user_data.setdefault("checks", []).append({
        "amount": amount,
        "due_date": None,
        "diff": None
    })
    # نمایش تقویم جهت انتخاب تاریخ سررسید چک با callback_prefix "DUE"
    base_dt = context.user_data["base_date"]
    default_due = base_dt + timedelta(days=1)
    j_default_due = JalaliDate.to_jalali(default_due.year, default_due.month, default_due.day)
    calendar_markup = build_calendar_persian(j_default_due.year, j_default_due.month, callback_prefix="DUE")
    await update.message.reply_text(
        f"لطفاً تاریخ سررسید چک شماره {context.user_data['current_check']} را انتخاب کنید:",
        reply_markup=calendar_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_DUE_DATE

async def ask_fee_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Entered ask_fee_rate")
    text = update.message.text.strip()
    try:
        fee_input = float(text)
        fee_rate = fee_input / 100.0
    except Exception:
        await update.message.reply_text("لطفاً یک عدد معتبر برای درصد کارمزد وارد کنید.")
        return ASK_FEE_RATE
    context.user_data["fee_rate"] = fee_rate

    total_amount = sum(ch["amount"] for ch in context.user_data["checks"])
    summary_lines = []
    summary_lines.append("**خلاصه اطلاعات وارد شده:**\n")
    summary_lines.append(f"- تعداد چک‌ها: {context.user_data['count']}")
    summary_lines.append(f"- مجموع مبالغ: {total_amount:,.0f} ریال\n")
    for idx, ch in enumerate(context.user_data["checks"], start=1):
        due_dt = ch["due_date"]
        j_due = JalaliDate.to_jalali(due_dt.year, due_dt.month, due_dt.day)
        due_j_date = f"{j_due.year}/{j_due.month:02d}/{j_due.day:02d}"
        diff = ch["diff"]
        summary_lines.append(f"چک {idx}:")
        summary_lines.append(f"   مبلغ: {ch['amount']:,.0f} ریال")
        summary_lines.append(f"   تاریخ سررسید: {due_j_date}")
        summary_lines.append(f"   اختلاف روز از تاریخ شروع: {diff} روز\n")
    summary_lines.append(f"- درصد کارمزد ماهانه: {text}٪\n")
    summary_lines.append("آیا اطلاعات وارد شده صحیح است؟ (لطفاً بلی یا خیر ارسال کنید)")
    summary = "\n".join(summary_lines)
    await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
    return CONFIRM

async def confirm_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Entered confirm_data")
    text = update.message.text.strip().lower()
    if text not in ["بلی", "yes", "ok"]:
        await update.message.reply_text("عملیات لغو شد. برای شروع دوباره، دستور /start را ارسال کنید.")
        context.user_data.clear()
        return ConversationHandler.END

    fee_rate = context.user_data["fee_rate"]
    checks = context.user_data["checks"]
    sum_ai = sum(ch["amount"] for ch in checks)
    sum_ai_di = sum(ch["amount"] * ch["diff"] for ch in checks)
    if sum_ai == 0:
        await update.message.reply_text("مجموع مبالغ صفر است، محاسبه امکان‌پذیر نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    ras_day = sum_ai_di / sum_ai
    ras_month = ras_day / 30.4
    multiplier = fee_rate * ras_month
    fee_amount = sum_ai * multiplier
    total_payable = sum_ai - fee_amount

    base_dt = context.user_data["base_date"]
    ras_dt = base_dt + timedelta(days=ras_day)
    j_ras = JalaliDate.to_jalali(ras_dt.year, ras_dt.month, ras_dt.day)
    ras_j_date = f"{j_ras.year}/{j_ras.month:02d}/{j_ras.day:02d}"

    result_msg = (
        "**نتیجه محاسبات:**\n\n"
        f"- راس روز: {ras_day:.2f} روز\n"
        f"- راس ماه: {ras_month:.2f} ماه\n"
        f"- تاریخ راس (تقریباً): {ras_j_date}\n\n"
        f"- مبلغ کارمزد: {fee_amount:,.0f} ریال\n"
        f"- جمع پرداختی: {total_payable:,.0f} ریال\n"
    )
    await update.message.reply_text(result_msg, parse_mode=ParseMode.MARKDOWN)
    
    # ارسال گزارش به مدیر (ADMIN_CHAT_ID)
    try:
        report_text = (
            "گزارش استفاده از MyRasChekBot:\n"
            f"تعداد دفعات استفاده: ۱ (برای این تراکنش)\n"
            f"خلاصه اطلاعات:\n{result_msg}"
        )
        await update.effective_bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Error sending report to admin: %s", e)
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد. برای شروع دوباره، دستور /start را ارسال کنید.")
    context.user_data.clear()
    return ConversationHandler.END

# ===================== Main =====================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            ASK_BASE_DATE: [CallbackQueryHandler(base_date_callback)],
            ASK_CHECK_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_check_count)],
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_DUE_DATE: [CallbackQueryHandler(due_date_callback)],
            ASK_FEE_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fee_rate)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_data)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv_handler)
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
