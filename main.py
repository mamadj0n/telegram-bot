'''
this is a telegram bot for cryptocurrency analysis and price tracking. 
It uses the aiogram library for handling Telegram interactions, aiohttp for asynchronous HTTP requests, 
and the ta library for technical analysis indicators. The bot can provide real-time price information, 
technical analysis based on various indicators, and manage capital risk for trading.
and also it can provide the price of gold and dollar in iran.

programmed by: MODSO & Chatgpt & deepseek

'''
import datetime
import asyncio
import aiohttp
import requests
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import json
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
headers = {'Authorization': 'u5STfPOsgEjtgZGj6q3O'}

# ==========================
#         ALARM SYSTEM
# ==========================

ALARMS_FILE = "user_alarms.json"

class AlarmType:
    CRYPTO = "crypto"
    GOLD = "gold"
    DOLLAR = "dollar"

class AlarmCondition:
    ABOVE = "above"
    BELOW = "below"

class AlarmState(StatesGroup):
    waiting_for_alarm_type = State()
    waiting_for_crypto_symbol = State()
    waiting_for_price = State()
    waiting_for_condition = State()
    waiting_for_interval = State()
    waiting_for_alarm_delete = State()

# ساختار ذخیره‌سازی آلارم‌ها
def load_alarms():
    """بارگذاری آلارم‌ها از فایل"""
    if os.path.exists(ALARMS_FILE):
        with open(ALARMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_alarms(alarms):
    """ذخیره آلارم‌ها در فایل"""
    with open(ALARMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(alarms, f, ensure_ascii=False, indent=2)

async def check_alarms():
    """بررسی مداوم آلارم‌ها"""
    while True:
        try:
            alarms = load_alarms()
            current_time = datetime.datetime.now()
            
            for user_id, user_alarms in alarms.items():
                for alarm_id, alarm in list(user_alarms.items()):
                    # بررسی زمان آخرین چک
                    last_check = datetime.datetime.fromisoformat(alarm.get('last_check', '2000-01-01'))
                    interval_minutes = alarm.get('interval', 5)
                    
                    if (current_time - last_check).total_seconds() < interval_minutes * 60:
                        continue
                    
                    # به‌روزرسانی زمان آخرین چک
                    alarm['last_check'] = current_time.isoformat()
                    
                    # دریافت قیمت جدید بر اساس نوع آلارم
                    current_price = None
                    alarm_type = alarm['type']
                    
                    if alarm_type == AlarmType.CRYPTO:
                        price_data = await get_price(alarm['symbol'])
                        if price_data:
                            current_price = price_data['price']
                    elif alarm_type == AlarmType.GOLD:
                        current_price = await get_gold_price()
                    elif alarm_type == AlarmType.DOLLAR:
                        buy_price, _ = await get_dollar_price()
                        current_price = buy_price
                    
                    if current_price is not None:
                        target_price = alarm['price']
                        condition = alarm['condition']
                        
                        # بررسی شرط آلارم
                        should_trigger = False
                        if condition == AlarmCondition.ABOVE and current_price >= target_price:
                            should_trigger = True
                        elif condition == AlarmCondition.BELOW and current_price <= target_price:
                            should_trigger = True
                        
                        if should_trigger:
                            # ارسال نوتیفیکیشن
                            await send_alarm_notification(int(user_id), alarm, current_price)
                            # حذف آلارم یکبار مصرف
                            if not alarm.get('recurring', False):
                                del user_alarms[alarm_id]
            
            save_alarms(alarms)
            
        except Exception as e:
            print(f"Error in check_alarms: {e}")
        
        await asyncio.sleep(30)  # چک هر 30 ثانیه

async def send_alarm_notification(user_id: int, alarm: dict, current_price: float):
    """ارسال نوتیفیکیشن آلارم"""
    alarm_type = alarm['type']
    condition = alarm['condition']
    target_price = alarm['price']
    
    type_names = {
        AlarmType.CRYPTO: f"ارز دیجیتال {alarm.get('symbol', '')}",
        AlarmType.GOLD: "طلای 18 عیار",
        AlarmType.DOLLAR: "دلار/تتر"
    }
    
    condition_text = "رسید به" if condition == AlarmCondition.ABOVE else "رسید به"
    emoji = "🟢" if condition == AlarmCondition.ABOVE else "🔴"
    
    message = f"""
🔔 **آلارم قیمتی فعال شد!** 🔔

{emoji} **نوع:** {type_names.get(alarm_type, 'نامشخص')}
💰 **قیمت هدف:** {target_price:,.0f} تومان
📊 **قیمت فعلی:** {current_price:,.0f} تومان
⚡ **شرط:** قیمت {condition_text} سطح مورد نظر

⏰ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    try:
        await bot.send_message(user_id, message)
    except Exception as e:
        print(f"Error sending alarm notification: {e}")

# ==========================
#         API FUNCTIONS
# ==========================

async def get_price(symbol):
    """دریافت قیمت لحظه‌ای از بایننس"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol.upper()}USDT"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return {
                    "price": float(data["lastPrice"]),
                    "change_percent": float(data["priceChangePercent"]),
                    "volume": float(data["volume"]),
                    "high": float(data["highPrice"]),
                    "low": float(data["lowPrice"])
                }
    except Exception as e:
        print(f"Error in get_price: {e}")
        return None


async def get_gold_price():
    """دریافت قیمت طلا"""
    try:
        res = requests.get('https://api.alanchand.com/?type=golds&token=u5STfPOsgEjtgZGj6q3O', headers=headers)
        if res.status_code != 200:
            return None
        data = res.json()
        return data["18ayar"]["price"]
    except Exception as e:
        print(f"Error in get_gold_price: {e}")
        return None


async def get_dollar_price():
    """دریافت قیمت دلار"""
    try:
        res = requests.get('https://api.alanchand.com/?type=currencies&token=u5STfPOsgEjtgZGj6q3O', headers=headers)
        if res.status_code != 200:
            return None, None
        data = res.json()
        return data["usd"]["buy"], data["usd"]["sell"]
    except Exception as e:
        print(f"Error in get_dollar_price: {e}")
        return None, None


async def get_klines(symbol="BTC", interval="1h", limit=200):
    """دریافت داده‌های کندل از بایننس"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": f"{symbol.upper()}USDT", "interval": interval, "limit": limit}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                data = await response.json()

        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume", "_", "_", "_", "_", "_", "_"
        ])
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df
    except Exception as e:
        print(f"Error in get_klines: {e}")
        return None


async def add_indicators(df):
    """افزودن اندیکاتورها به دیتافریم"""
    try:
        # EMA 20/50
        df["ema20"] = EMAIndicator(df["close"], window=20).ema_indicator()
        df["ema50"] = EMAIndicator(df["close"], window=50).ema_indicator()
        # RSI
        df["rsi"] = RSIIndicator(df["close"], window=14).rsi()
        # DMI / ADX
        adx = ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"] = adx.adx()
        df["di_plus"] = adx.adx_pos()
        df["di_minus"] = adx.adx_neg()
        # ATR
        df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
        return df
    except Exception as e:
        print(f"Error in add_indicators: {e}")
        return None


async def generate_analysis(df, symbol="BTC"):
    """تولید تحلیل بر اساس اندیکاتورها"""
    try:
        latest = df.iloc[-1]
        rsi = latest["rsi"]
        ema20 = latest["ema20"]
        ema50 = latest["ema50"]
        adx = latest["adx"]
        di_plus = latest["di_plus"]
        di_minus = latest["di_minus"]
        atr = latest["atr"]
        atr_mean = df["atr"].rolling(14).mean().iloc[-1]

        # مومنتوم
        if rsi > 70:
            momentum_score = -1
            momentum_text = "🔴 اشباع خرید"
        elif rsi < 30:
            momentum_score = 1
            momentum_text = "🟢 اشباع فروش"
        else:
            momentum_score = 0
            momentum_text = "⚪ متعادل"

        # روند
        if ema20 > ema50:
            trend_score = 1
            trend_text = "🟢 صعودی"
        else:
            trend_score = -1
            trend_text = "🔴 نزولی"

        # قدرت حرکت
        direction_score = 1 if di_plus > di_minus else -1
        strength_score = 1 if adx > 25 else 0
        strength_text = "💪 قوی" if adx > 25 else "💫 ضعیف"

        # نوسان
        volatility_text = "📈 بالا" if atr > atr_mean else "📉 پایین"

        # امتیازدهی نهایی
        total_score = (trend_score * 2) + momentum_score + direction_score
        if strength_score:
            total_score *= 1.2

        if total_score >= 3:
            final_signal = "🟢 صعودی قوی"
            signal_emoji = "🚀"
        elif total_score >= 1:
            final_signal = "🟢 صعودی متوسط"
            signal_emoji = "📈"
        elif total_score <= -3:
            final_signal = "🔴 نزولی قوی"
            signal_emoji = "💥"
        elif total_score <= -1:
            final_signal = "🔴 نزولی متوسط"
            signal_emoji = "📉"
        else:
            final_signal = "⚪ رنج"
            signal_emoji = "⏸️"

        analysis = f"""
{signal_emoji} تحلیل تکنیکال {symbol}USDT {signal_emoji}

📊 اندیکاتورها:
• RSI: {rsi:.1f} - {momentum_text}
• EMA: {trend_text} (20: {ema20:.1f} | 50: {ema50:.1f})
• ADX: {adx:.1f} - {strength_text}
• ATR: {atr:.2f} - نوسان {volatility_text}

📌 سیگنال کلی :{final_signal}
⚡ اعتماد :    {"عالی" if abs(total_score) > 3 else "متوسط" if abs(total_score) > 1 else "کم"}

⚠️ مدیریت ریسک:
• حد سود: {latest['close'] + (atr * 2):.1f} USDT
• حد ضرر: {latest['close'] - atr:.1f} USDT
"""
        return analysis
    except Exception as e:
        return f"❌ خطا در تحلیل: {str(e)}"


# ==========================
#         STATES
# ==========================

class CapitalState(StatesGroup):
    capital = State()
    risk = State()


class CryptoState(StatesGroup):
    waiting_for_price = State()
    waiting_for_analysis = State()


# ==========================
#         KEYBOARD
# ==========================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 قیمت ارزدیجیتال"), KeyboardButton(text="💹 تحلیل ارز دیجیتال")],
        [KeyboardButton(text="💰 مدیریت سرمایه"), KeyboardButton(text="🔔 آلارم قیمتی")],
        [KeyboardButton(text="🥇 قیمت طلا 18 عیار"), KeyboardButton(text="💲 قیمت دلار و تتر")],
        [KeyboardButton(text="📋 لیست آلارم‌ها"), KeyboardButton(text="❌ حذف آلارم")],
    ],
    resize_keyboard=True
)


# ==========================
#         HANDLERS
# ==========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"سلام {message.from_user.first_name} 👋\nبه ربات تحلیل ارز دیجیتال خوش اومدی!\nیکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=main_keyboard
    )


# هندلر دریافت قیمت ارز دیجیتال
@dp.message(lambda m: m.text == "📊 قیمت ارزدیجیتال")
async def ask_symbol_price(message: Message, state: FSMContext):
    await message.answer("💰 اسم کوین رو بفرست (مثلاً BTC یا ETH):")
    await state.set_state(CryptoState.waiting_for_price)


# هندلر دریافت تحلیل ارز دیجیتال
@dp.message(lambda m: m.text == "💹 تحلیل ارز دیجیتال")
async def ask_symbol_analysis(message: Message, state: FSMContext):
    await message.answer("📊 اسم کوین رو بفرست برای تحلیل (مثلاً BTC یا ETH):")
    await state.set_state(CryptoState.waiting_for_analysis)


# هندلر آلارم قیمتی
@dp.message(lambda m: m.text == "🔔 آلارم قیمتی")
async def alarm_menu(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 ارز دیجیتال", callback_data="alarm_crypto")],
            [InlineKeyboardButton(text="🥇 طلا", callback_data="alarm_gold")],
            [InlineKeyboardButton(text="💲 دلار/تتر", callback_data="alarm_dollar")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="alarm_cancel")]
        ]
    )
    await message.answer("🔔 **تنظیم آلارم قیمتی**\n\nلطفاً نوع آلارم را انتخاب کنید:", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith('alarm_'))
async def alarm_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace('alarm_', '')
    
    if action == 'cancel':
        await callback.message.edit_text("❌ عملیات لغو شد.")
        await state.clear()
        return
    
    elif action == 'crypto':
        await state.update_data(alarm_type=AlarmType.CRYPTO)
        await callback.message.edit_text("💰 لطفاً نماد ارز دیجیتال را وارد کنید (مثلاً BTC یا ETH):")
        await state.set_state(AlarmState.waiting_for_crypto_symbol)
    
    elif action == 'gold':
        await state.update_data(alarm_type=AlarmType.GOLD)
        await show_price_input(callback.message, state, "🥇 لطفاً قیمت هدف برای طلای 18 عیار را وارد کنید (به تومان):")
    
    elif action == 'dollar':
        await state.update_data(alarm_type=AlarmType.DOLLAR)
        await show_price_input(callback.message, state, "💲 لطفاً قیمت هدف برای دلار/تتر را وارد کنید (به تومان):")
    
    await callback.answer()


async def show_price_input(message: Message, state: FSMContext, text: str):
    await message.answer(text)
    await state.set_state(AlarmState.waiting_for_price)


@dp.message(AlarmState.waiting_for_crypto_symbol)
async def get_crypto_symbol_alarm(message: Message, state: FSMContext):
    symbol = message.text.upper().strip()
    
    # بررسی وجود کوین
    price_data = await get_price(symbol)
    if not price_data:
        await message.answer(f"❌ کوین {symbol} یافت نشد! لطفاً دوباره امتحان کنید.")
        return
    
    await state.update_data(crypto_symbol=symbol, current_price=price_data['price'])
    await message.answer(f"💰 قیمت فعلی {symbol}: {price_data['price']:,.2f} USDT\n\nلطفاً قیمت هدف را وارد کنید (به USDT):")
    await state.set_state(AlarmState.waiting_for_price)


@dp.message(AlarmState.waiting_for_price)
async def get_target_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', ''))
        data = await state.get_data()
        
        await state.update_data(target_price=price)
        
        # انتخاب شرط
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📈 بالاتر از قیمت", callback_data="condition_above")],
                [InlineKeyboardButton(text="📉 پایین‌تر از قیمت", callback_data="condition_below")],
            ]
        )
        
        current_price_text = ""
        if 'current_price' in data:
            current_price_text = f"\n💰 قیمت فعلی: {data['current_price']:,.2f} USDT"
        
        await message.answer(
            f"🎯 قیمت هدف: {price:,.0f} تومان{current_price_text}\n\n"
            f"لطفاً شرط آلارم را انتخاب کنید:",
            reply_markup=keyboard
        )
        await state.set_state(AlarmState.waiting_for_condition)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")


@dp.callback_query(lambda c: c.data.startswith('condition_'))
async def condition_callback(callback: CallbackQuery, state: FSMContext):
    condition = callback.data.replace('condition_', '')
    await state.update_data(condition=condition)
    
    # انتخاب بازه زمانی چک
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏱️ هر 5 دقیقه", callback_data="interval_5")],
            [InlineKeyboardButton(text="⏱️ هر 15 دقیقه", callback_data="interval_15")],
            [InlineKeyboardButton(text="⏱️ هر 30 دقیقه", callback_data="interval_30")],
            [InlineKeyboardButton(text="⏱️ هر 60 دقیقه", callback_data="interval_60")],
        ]
    )
    
    await callback.message.edit_text("⏰ لطفاً بازه زمانی چک کردن آلارم را انتخاب کنید:", reply_markup=keyboard)
    await state.set_state(AlarmState.waiting_for_interval)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith('interval_'))
async def interval_callback(callback: CallbackQuery, state: FSMContext):
    interval = int(callback.data.replace('interval_', ''))
    data = await state.get_data()
    
    # ایجاد آلارم جدید
    user_id = str(callback.from_user.id)
    alarms = load_alarms()
    
    if user_id not in alarms:
        alarms[user_id] = {}
    
    import uuid
    alarm_id = str(uuid.uuid4())[:8]
    
    alarm_data = {
        'type': data['alarm_type'],
        'price': data['target_price'],
        'condition': data['condition'],
        'interval': interval,
        'recurring': True,
        'created_at': datetime.datetime.now().isoformat(),
        'last_check': datetime.datetime.now().isoformat()
    }
    
    if data['alarm_type'] == AlarmType.CRYPTO:
        alarm_data['symbol'] = data['crypto_symbol']
        type_name = f"ارز دیجیتال {data['crypto_symbol']}"
    elif data['alarm_type'] == AlarmType.GOLD:
        type_name = "طلای 18 عیار"
    else:
        type_name = "دلار/تتر"
    
    alarms[user_id][alarm_id] = alarm_data
    save_alarms(alarms)
    
    condition_text = "بالاتر از" if data['condition'] == 'above' else "پایین‌تر از"
    
    await callback.message.edit_text(
        f"✅ **آلارم با موفقیت ثبت شد!**\n\n"
        f"📌 **نوع:** {type_name}\n"
        f"🎯 **قیمت هدف:** {data['target_price']:,.0f} تومان\n"
        f"⚡ **شرط:** {condition_text} قیمت هدف\n"
        f"⏰ **بازه چک:** هر {interval} دقیقه\n"
        f"🆔 **کد آلارم:** `{alarm_id}`\n\n"
        f"به محض رسیدن قیمت به سطح مورد نظر، به شما اطلاع داده می‌شود."
    )
    
    await state.clear()
    await callback.answer()


# هندلر لیست آلارم‌ها
@dp.message(lambda m: m.text == "📋 لیست آلارم‌ها")
async def list_alarms(message: Message):
    user_id = str(message.from_user.id)
    alarms = load_alarms()
    
    if user_id not in alarms or not alarms[user_id]:
        await message.answer("📭 شما هیچ آلارم فعالی ندارید.")
        return
    
    text = "📋 **لیست آلارم‌های فعال شما:**\n\n"
    
    type_names = {
        AlarmType.CRYPTO: "🪙 ارز دیجیتال",
        AlarmType.GOLD: "🥇 طلا",
        AlarmType.DOLLAR: "💲 دلار/تتر"
    }
    
    condition_names = {
        AlarmCondition.ABOVE: "📈 بالاتر از",
        AlarmCondition.BELOW: "📉 پایین‌تر از"
    }
    
    for alarm_id, alarm in alarms[user_id].items():
        type_name = type_names.get(alarm['type'], 'نامشخص')
        if alarm['type'] == AlarmType.CRYPTO:
            type_name += f" {alarm.get('symbol', '')}"
        
        condition = condition_names.get(alarm['condition'], '')
        
        text += f"🆔 `{alarm_id}`\n"
        text += f"📌 {type_name}\n"
        text += f"💰 {condition} {alarm['price']:,.0f} تومان\n"
        text += f"⏰ هر {alarm['interval']} دقیقه\n"
        text += "─" * 20 + "\n"
    
    await message.answer(text)


# هندلر حذف آلارم
@dp.message(lambda m: m.text == "❌ حذف آلارم")
async def delete_alarm_prompt(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    alarms = load_alarms()
    
    if user_id not in alarms or not alarms[user_id]:
        await message.answer("📭 شما هیچ آلارم فعالی برای حذف ندارید.")
        return
    
    # نمایش آلارم‌ها برای انتخاب
    text = "❌ **حذف آلارم**\n\nلطفاً کد آلارم مورد نظر را وارد کنید:\n\n"
    
    for alarm_id in alarms[user_id].keys():
        text += f"🆔 `{alarm_id}`\n"
    
    text += "\n⏹️ برای لغو، /cancel را بفرستید."
    
    await message.answer(text)
    await state.set_state(AlarmState.waiting_for_alarm_delete)


@dp.message(AlarmState.waiting_for_alarm_delete)
async def delete_alarm(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await message.answer("❌ عملیات لغو شد.")
        await state.clear()
        return
    
    alarm_id = message.text.strip()
    user_id = str(message.from_user.id)
    alarms = load_alarms()
    
    if user_id in alarms and alarm_id in alarms[user_id]:
        del alarms[user_id][alarm_id]
        save_alarms(alarms)
        await message.answer(f"✅ آلارم با کد `{alarm_id}` با موفقیت حذف شد.")
    else:
        await message.answer(f"❌ آلارم با کد `{alarm_id}` یافت نشد!")
    
    await state.clear()


# هندلر مدیریت سرمایه
@dp.message(lambda m: m.text == "💰 مدیریت سرمایه")
async def capital_management(message: Message, state: FSMContext):
    await message.answer("💰 سرمایه کل رو وارد کن (به تومان):")
    await state.set_state(CapitalState.capital)


# هندلر دریافت قیمت طلا
@dp.message(lambda m: m.text == "🥇 قیمت طلا 18 عیار")
async def gold_price(message: Message):
    await message.answer("⏳ در حال دریافت قیمت طلا...")
    price = await get_gold_price()
    if price:
        await message.answer(f"💛 قیمت هر گرم طلای 18 عیار:\n{price:,.0f} تومان")
    else:
        await message.answer("❌ خطا در دریافت قیمت طلا")


# هندلر دریافت قیمت دلار و تتر
@dp.message(lambda m: m.text == "💲 قیمت دلار و تتر")
async def dollar_price(message: Message):
    await message.answer("⏳ در حال دریافت قیمت دلار...")
    buy, sell = await get_dollar_price()
    if buy and sell:
        await message.answer(
            f"💲 **قیمت دلار و تتر:**\n\n"
            f"خرید 🟢: {buy:,.0f} تومان\n"
            f"فروش 🔴: {sell:,.0f} تومان\n\n"
            f"💱 اسپرد: {sell - buy:,.0f} تومان"
        )
    else:
        await message.answer("❌ خطا در دریافت قیمت دلار")


# هندلر دریافت قیمت ارز دیجیتال
@dp.message(CryptoState.waiting_for_price)
async def get_crypto_price(message: Message, state: FSMContext):
    symbol = message.text.upper().strip()
    
    await message.answer(f"⏳ در حال دریافت قیمت {symbol}...")
    
    price_data = await get_price(symbol)
    
    if price_data:
        # تعیین رنگ برای تغییرات
        change = price_data['change_percent']
        change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
        
        await message.answer(
            f"📊 **آمار {symbol}USDT**\n\n"
            f"💰 قیمت: {price_data['price']:,.2f} USDT\n"
            f"📊 بیشترین 24h: {price_data['high']:,.2f} USDT\n"
            f"📊 کمترین 24h: {price_data['low']:,.2f} USDT\n"
            f"{change_emoji} تغییرات: {change:+.2f}%\n"
            f"📦 حجم معاملات: {price_data['volume']:,.0f} USDT"
        )
    else:
        await message.answer(f"❌ کوین {symbol} یافت نشد! لطفاً اسم صحیح رو وارد کن.")
    
    await state.clear()


# هندلر دریافت تحلیل ارز دیجیتال
@dp.message(CryptoState.waiting_for_analysis)
async def get_crypto_analysis(message: Message, state: FSMContext):
    symbol = message.text.upper().strip()
    
    await message.answer(f"⏳ در حال دریافت تحلیل {symbol}... (حدود 10 ثانیه)")
    
    # دریافت داده‌ها
    df = await get_klines(symbol=symbol, interval="1h", limit=200)
    
    if df is None:
        await message.answer(f"❌ خطا در دریافت داده‌های {symbol}")
        await state.clear()
        return
    
    # افزودن اندیکاتورها
    df_with_indicators = await add_indicators(df)
    
    if df_with_indicators is None:
        await message.answer(f"❌ خطا در محاسبه اندیکاتورها")
        await state.clear()
        return
    
    # تولید تحلیل
    analysis = await generate_analysis(df_with_indicators, symbol=symbol)
    
    # دریافت قیمت فعلی برای نمایش
    price_data = await get_price(symbol)
    current_price = f"\n💰 قیمت لحظه‌ای: {price_data['price']:,.2f} USDT" if price_data else ""
    
    await message.answer(analysis + current_price)
    await state.clear()


# هندلر مدیریت سرمایه
@dp.message(CapitalState.capital)
async def get_capital(message: Message, state: FSMContext):
    try:
        capital = float(message.text.replace(',', ''))
        await state.update_data(capital=capital)
        await message.answer("📊 چند درصد ریسک می‌کنی؟ (مثلاً 2 برای 2%)")
        await state.set_state(CapitalState.risk)
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کن.")


# هندلر محاسبه ریسک و پیشنهادات مدیریت سرمایه
@dp.message(CapitalState.risk)
async def calculate_risk(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        capital = data["capital"]
        risk_percent = float(message.text)

        risk_amount = capital * (risk_percent / 100)
        position_size = capital * 0.1  # 10% سرمایه برای هر موقعیت
        leverage_suggestions = {
            "کم": 2,
            "متوسط": 5,
            "زیاد": 10
        }

        await message.answer(
            f"🧠 **مدیریت سرمایه**\n\n"
            f"💰 سرمایه کل: {capital:,.0f} تومان\n"
            f"⚠️ ریسک هر معامله: {risk_percent}%\n"
            f"💸 مقدار مجاز ضرر: {risk_amount:,.0f} تومان\n"
            f"📊 حجم هر معامله: {position_size:,.0f} تومان\n\n"
            f"**پیشنهاد اهرم:**\n"
            f"• {leverage_suggestions['کم']}x برای ریسک کم\n"
            f"• {leverage_suggestions['متوسط']}x برای ریسک متوسط\n"
            f"• {leverage_suggestions['زیاد']}x برای ریسک زیاد"
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کن.")
    except Exception as e:
        await message.answer(f"❌ خطا: {str(e)}")
        await state.clear()


@dp.message()
async def unknown_message(message: Message):
    """هندلر پیام‌های ناشناخته"""
    await message.answer(
        "❌ دستور نامعتبر!\n"
        "لطفاً از دکمه‌های منو استفاده کنید.",
        reply_markup=main_keyboard
    )


async def main():
    print("✅ Robot started successfully!")
    print("🤖 Waiting for messages...")
    
    # اجرای تسک بررسی آلارم‌ها در پس‌زمینه
    asyncio.create_task(check_alarms())
    
    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())

