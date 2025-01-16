import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from datetime import datetime, timedelta
from persiantools.jdatetime import JalaliDate

# اگر از متغیرمحیطی استفاده می‌کنید، سطر زیر را فعال و خط بعد را کامنت کنید
# TOKEN = os.environ["BOT_TOKEN"]
TOKEN = "7987671225:AAEtMnYVnkrHTlwCVKO18cj3QuRqd88RRew"

ASK_BASE_DATE, ASK_CHECK_COUNT, ASK_AMOUNT, ASK_DUE_DATE, ASK_FEE_RATE = range(5)

# نگه‌داری اطلاعات هر کاربر به شکل موقت
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! تاریخ مبدأ (شمسی) را به فرمت yyyy-mm-dd وارد کنید (مثلاً 1402-10-01):"
    )
    return ASK_BASE_DATE

async def ask_base_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    try:
        y, m, d = text.split("-")
        y, m, d = int(y), int(m), int(d)
        base_j = JalaliDate(y, m, d)
        base_g = base_j.to_gregorian()
        base_dt = datetime(base_g.year, base_g.month, base_g.day)
    except:
        await update.message.reply_text("تاریخ نامعتبر! دوباره تلاش کنید.")
        return ASK_BASE_DATE

    user_data[uid] = {
        "base_date": base_dt,
        "checks": [],
        "current_check": 1,
        "count": 0
    }
    await update.message.reply_text("تعداد چک‌ها؟ (یک عدد وارد کنید)")
    return ASK_CHECK_COUNT

async def ask_check_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_data:
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.isdigit():
        await update.message.reply_text("یک عدد صحیح وارد کنید.")
        return ASK_CHECK_COUNT

    c = int(t)
    if c <= 0:
        await update.message.reply_text("باید بزرگتر از صفر باشد.")
        return ASK_CHECK_COUNT

    user_data[uid]["count"] = c
    await update.message.reply_text("مبلغ چک شماره 1؟ (تومان)")
    return ASK_AMOUNT

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_data:
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.isdigit():
        await update.message.reply_text("عدد صحیح وارد کنید.")
        return ASK_AMOUNT

    amount = int(t)
    data = user_data[uid]
    data["checks"].append({
        "amount": amount,
        "due_date": None,
        "diff": None
    })
    await update.message.reply_text(
        f"تاریخ سررسید چک شماره {data['current_check']}؟ (شمسی: 1402-10-15)"
    )
    return ASK_DUE_DATE

async def ask_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_data:
        return ConversationHandler.END
    data = user_data[uid]
    idx = data["current_check"] - 1

    t = update.message.text.strip()
    try:
        y, m, d = t.split("-")
        y, m, d = int(y), int(m), int(d)
        j = JalaliDate(y, m, d)
        g = j.to_gregorian()
        dt = datetime(g.year, g.month, g.day)
    except:
        await update.message.reply_text("تاریخ نامعتبر!")
        return ASK_DUE_DATE

    data["checks"][idx]["due_date"] = dt
    data["checks"][idx]["diff"] = (dt - data["base_date"]).days

    if data["current_check"] < data["count"]:
        data["current_check"] += 1
        await update.message.reply_text(f"مبلغ چک شماره {data['current_check']}؟")
        return ASK_AMOUNT
    else:
        await update.message.reply_text("درصد کارمزد ماهانه؟ (مثلاً 5 یعنی 5 درصد)")
        return ASK_FEE_RATE

async def ask_fee_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_data:
        return ConversationHandler.END

    t = update.message.text.strip()
    try:
        # اگر کاربر مثلاً 5 وارد کند یعنی 5درصد => تبدیل به 0.05
        fee_input = float(t)
        fee_rate = fee_input / 100.0
    except:
        await update.message.reply_text("عدد معتبر وارد کنید (مثلاً 5 برای 5 درصد).")
        return ASK_FEE_RATE

    data = user_data[uid]
    checks = data["checks"]
    sum_ai = 0
    sum_ai_di = 0
    for ch in checks:
        sum_ai += ch["amount"]
        sum_ai_di += ch["amount"] * ch["diff"]

    if sum_ai == 0:
        user_data.pop(uid, None)
        await update.message.reply_text("مجموع مبالغ صفر است!")
        return ConversationHandler.END

    ras_day = sum_ai_di / sum_ai
    ras_month = ras_day / 30.4
    multiplier = fee_rate * ras_month
    fee_amount = sum_ai * multiplier
    total_payable = sum_ai - fee_amount

    base_dt = data["base_date"]
    ras_dt = base_dt + timedelta(days=ras_day)
    ras_jalali = JalaliDate(ras_dt.year, ras_dt.month, ras_dt.day).isoformat()

    msg = (
        f"راس روز: {ras_day:.2f}\n"
        f"تاریخ راس (شمسی): {ras_jalali}\n"
        f"راس ماه: {ras_month:.2f}\n\n"
        f"مبلغ کارمزد: {fee_amount:,.0f}\n"
        f"جمع پرداختی: {total_payable:,.0f}\n"
    )
    await update.message.reply_text(msg)

    user_data.pop(uid, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_BASE_DATE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_base_date)],
            ASK_CHECK_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_check_count)],
            ASK_AMOUNT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_DUE_DATE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_due_date)],
            ASK_FEE_RATE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fee_rate)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv)

    print("Bot is running on Railway...")
    app.run_polling()

if __name__ == "__main__":
    main()
