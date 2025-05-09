import os
import sqlite3
from datetime import timedelta, datetime
import locale
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import aiohttp
import json

# Конфигурация
API_TOKEN = '6899828449:AAEGKYoJYx714U5KXm6I_4XTnRWS7m6O_E0'
WEATHER_API = 'bd5e378503939ddaee76f12ad7a97608'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Состояния FSM
class Form(StatesGroup):
    city = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('code/data_telebot_2.sql')
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id VARCHAR(50), city VARCHAR(50), username VARCHAR(50))")
    conn.commit()
    conn.close()

init_db()

# Клавиатура основного меню
def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text='погода на день'))
    builder.add(types.KeyboardButton(text='погода на 3 дня'))
    builder.add(types.KeyboardButton(text='погода на 7 дней'))
    builder.adjust(2)

    return builder.as_markup(resize_keyboard=True)

# Обработка команды /start
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer('Привет!', reply_markup=main_keyboard())
    # await set_city(message)

# Установка города
@dp.message(Command('set_city'))
async def set_city(message: types.Message, state: FSMContext):
    await state.set_state(Form.city)
    await message.answer('Введите город проживания:')

# Обработка ввода города
@dp.message(Form.city)
async def process_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    city = message.text.strip().lower()
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API}&units=metric') as resp:
            if resp.status == 200:
                data = await resp.json()
                add_user(user_id, city, message.from_user.username)

                await message.answer(
                    f"Город успешно установлен!\nСейчас в {city}: {data['main']['temp']}°C\n",
                    reply_markup=main_keyboard()
                )

                await state.clear()
            else:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(
                    text='Ввести повторно', 
                    callback_data='retry_city')
                )

                await message.answer('Город не найден', reply_markup=builder.as_markup())

# Колбэки
@dp.callback_query(F.data == 'retry_city')
async def retry_city(callback: types.CallbackQuery, state: FSMContext):
    await set_city(callback.message, state)

# Показать пользователей
@dp.message(Command('display_users'))
async def display_users(message: types.Message):
    conn = sqlite3.connect('code/data_telebot_2.sql')

    cur = conn.cursor()
    cur.execute('SELECT * FROM users')

    await message.answer(str(cur.fetchall()))
    conn.close()

# Обработка погодных запросов
@dp.message(F.text.in_(['погода на день', 'погода на 3 дня', 'погода на 7 дней']))
async def handle_weather_request(message: types.Message):
    user_id = message.from_user.id
    city = get_city(user_id)
    
    if not city:
        await message.answer('Сначала установите город')
        # await set_city(message)
        return

    days = 1 if 'день' in message.text else 3 if '3' in message.text else 7
    weather_text = await get_weather(city, days)
    
    builder = InlineKeyboardBuilder()
    buttons = [
        ('1 день', '1_day'),
        ('3 дня', '3_day'), 
        ('7 дней', '7_day')
    ]
    for text, data in buttons:
        if str(days) not in data:
            builder.add(types.InlineKeyboardButton(text=text, callback_data=data))
    
    await message.answer(weather_text, reply_markup=builder.as_markup())

# Обновление прогноза через инлайн кнопки
@dp.callback_query(F.data.endswith('_day'))
async def update_forecast(callback: types.CallbackQuery):
    days = int(callback.data.split('_')[0])
    city = get_city(callback.from_user.id)
    weather_text = await get_weather(city, days)
    
    builder = InlineKeyboardBuilder()
    buttons = [
        ('1 день', '1_day'),
        ('3 дня', '3_day'), 
        ('7 дней', '7_day')
    ]
    for text, data in buttons:
        if str(days) not in data:
            builder.add(types.InlineKeyboardButton(text=text, callback_data=data))
    
    await callback.message.edit_text(weather_text, reply_markup=builder.as_markup())

# Получение погоды
async def get_weather(city: str, days: int) -> str:
    global API
    
    if days == 1:
        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {'q': city, 'units': 'metric', 'lang': 'ru', 'appid': WEATHER_API}
    else:
        url = 'https://api.openweathermap.org/data/2.5/forecast/daily'
        params = {'q': city, 'cnt': days, 'units': 'metric', 'lang': 'ru', 'appid': WEATHER_API}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
    
    formatted_text = ''
    if days == 1:
        formatted_text += f'в {city} сейчас:\n'
        formatted_text += f'{data["main"]["temp"]} градусов\n'
        formatted_text  += f'влажность {data["main"]["humidity"]}%\n'
        formatted_text += f'ветер {data["wind"]["speed"]} м/с'

        return formatted_text
    else:
        flag = 0
        now = datetime.now()
        locale.setlocale(locale.LC_ALL, 'ru_RU.utf8')

        for i in data['list']:
            a = now + timedelta(flag)
            formatted_text += f'{a.strftime("%a")} - {i["weather"][0]["description"]}\n'
            formatted_text += f'днём: {i["temp"]["day"]}\n'
            formatted_text += f'ночью: {i["temp"]["night"]}\n\n'
            flag += 1

        return formatted_text[:-2]


# Работа с БД
def add_user(user_id: int, city: str, username: str):
    conn = sqlite3.connect('code/data_telebot_2.sql')
    cur = conn.cursor()
    cur.execute('DELETE FROM users WHERE id = ?', (user_id,))
    cur.execute('INSERT INTO users VALUES (?, ?, ?)', (user_id, city, username))
    conn.commit()
    conn.close()

def get_city(user_id: int) -> str | None:
    conn = sqlite3.connect('code/data_telebot_2.sql')
    cur = conn.cursor()
    cur.execute('SELECT city FROM users WHERE id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else None

if __name__ == '__main__':
    dp.run_polling(bot)