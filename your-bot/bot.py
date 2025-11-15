import os
import asyncio
import logging
from datetime import datetime
import random

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')

# Проверка обязательных переменных
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка базы данных SQLite
engine = create_engine('sqlite:///bookings.db', echo=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)


# Модель данных для бронирований
class Booking(Base):
    __tablename__ = 'bookings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100), nullable=True)
    room = Column(String(50), nullable=False)
    booking_date = Column(String(20), nullable=False)
    booking_time = Column(String(10), nullable=False)
    phone_number = Column(String(20))
    amount = Column(Float, nullable=False)
    status = Column(String(20), default='new')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# Создаем таблицы
Base.metadata.create_all(engine)


# Состояния FSM
class BookingStates(StatesGroup):
    building = State()
    floor = State()
    room = State()
    date = State()
    time = State()
    notes = State()
    confirmation = State()


# Клавиатуры для выбора корпуса, этажа и комнаты
def get_building_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Корпус 1"), KeyboardButton(text="🏢 Корпус 2")],
            [KeyboardButton(text="❌ Отменить бронирование")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_floor_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1 этаж"), KeyboardButton(text="2 этаж")],
            [KeyboardButton(text="3 этаж"), KeyboardButton(text="4 этаж")],
            [KeyboardButton(text="◀️ Назад к корпусам"), KeyboardButton(text="❌ Отменить бронирование")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_room_keyboard(floor: int, building: int):
    # Создаем кнопки для комнат на этаже (20 комнат)
    rooms = []
    row = []

    for room_num in range(1, 21):
        room_name = f"{building}-{floor:02d}-{room_num:02d}"
        row.append(KeyboardButton(text=room_name))

        # Создаем ряды по 4 комнаты
        if len(row) == 4:
            rooms.append(row)
            row = []

    # Добавляем последний ряд если остались комнаты
    if row:
        rooms.append(row)

    # Добавляем кнопки навигации
    rooms.append([
        KeyboardButton(text="◀️ Назад к этажам"),
        KeyboardButton(text="❌ Отменить бронирование")
    ])

    return ReplyKeyboardMarkup(
        keyboard=rooms,
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_custom_room_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Ввести другую комнату")],
            [KeyboardButton(text="◀️ Назад к этажам"), KeyboardButton(text="❌ Отменить бронирование")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_confirmation_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить"), KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отменить бронирование")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗑️ Новое бронирование"), KeyboardButton(text="📋 Мои брони")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )


def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/stats")]
        ],
        resize_keyboard=True
    )


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = f"""
    Привет, {message.from_user.first_name}! 
    🗑️ Я бот для бронирования вывоза мусора.

    Чтобы начать бронирование, нажмите /book или кнопку "🗑️ Новое бронирование"

    📋 Доступные команды:
    /book - Создать новое бронирование
    /my_bookings - Мои бронирования
    /cancel - Отменить текущее бронирование
    /help - Помощь
    """

    if str(message.from_user.id) == ADMIN_CHAT_ID:
        await message.answer("👑 Добро пожаловать, Моя Госпожа!", reply_markup=get_admin_keyboard())

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


# Команда /help
@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
    🤖 Как пользоваться ботом:

    1. Нажмите /book или "🗑️ Новое бронирование" чтобы начать бронирование
    2. Выберите корпус (1 или 2)
    3. Выберите этаж (1-4)
    4. Выберите комнату из списка
    5. Укажите дату вывоза мусора (в формате ДД.ММ.ГГГГ)
    6. Укажите время (в формате ЧЧ:ММ)
    7. Можете добавить комментарий (необязательно)
    8. Подтвердите бронирование

    💰 После подтверждения вы получите номер для оплаты и сумму.

    📋 Другие команды:
    /my_bookings - Посмотреть ваши брони
    /cancel - Отменить текущее бронирование
    """
    await message.answer(help_text, reply_markup=get_main_keyboard())


# Команда для просмотра своих бронирований
@dp.message(Command("my_bookings"))
@dp.message(F.text == "📋 Мои брони")
async def cmd_my_bookings(message: types.Message):
    session = Session()
    try:
        bookings = session.query(Booking).filter(
            Booking.user_id == message.from_user.id
        ).order_by(Booking.created_at.desc()).limit(5).all()

        if not bookings:
            await message.answer(
                "📭 У вас пока нет бронирований. Создайте первую бронь с помощью /book",
                reply_markup=get_main_keyboard()
            )
            return

        bookings_text = "📋 <b>Ваши последние бронирования:</b>\n\n"
        for booking in bookings:
            if booking.status == 'new':
                status_emoji = "🆕"
                status_text = "Новое"
            elif booking.status == 'cancelled':
                status_emoji = "❌"
                status_text = "Отменено"
            else:
                status_emoji = "✅"
                status_text = "Подтверждено"

            bookings_text += f"""
{status_emoji} <b>Бронь #{booking.id}</b> ({status_text})
🏢 {booking.room} | 📅 {booking.booking_date} | ⏰ {booking.booking_time}
💰 {booking.amount} руб. | 📞 {booking.phone_number}
⏳ {booking.created_at.strftime("%d.%m.%Y %H:%M")}
------------------------
            """

        bookings_text += "\nℹ️ Чтобы отменить бронирование, используйте: /cancel_booking ID"
        bookings_text += "\n\n🔹 Чтобы создать новое бронирование, нажмите /start"

        await message.answer(bookings_text, parse_mode="HTML", reply_markup=get_main_keyboard())

    except Exception as e:
        logger.error(f"Ошибка при получении бронирований: {e}")
        await message.answer("❌ Ошибка при получении списка бронирований")
    finally:
        session.close()


# Команда отмены бронирования (во время процесса)
@dp.message(Command("cancel"))
@dp.message(F.text == "❌ Отменить бронирование")
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "❌ У вас нет активного процесса бронирования.\n\nЧтобы начать новое бронирование, нажмите /start",
            reply_markup=get_main_keyboard()
        )
        return

    await message.answer(
        "❌ Бронирование отменено. Чтобы начать заново, нажмите /start",
        reply_markup=get_main_keyboard()
    )
    await state.clear()


# Начало бронирования
@dp.message(Command("book"))
@dp.message(F.text == "🗑️ Новое бронирование")
async def cmd_book(message: types.Message, state: FSMContext):
    # Проверяем, нет ли уже активного бронирования
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer(
            "⚠️ У вас уже есть активное бронирование. Закончите его или отмените командой /cancel",
            reply_markup=get_cancel_keyboard()
        )
        return

    await message.answer(
        "🏢 Выберите корпус:",
        reply_markup=get_building_keyboard()
    )
    await state.set_state(BookingStates.building)


# Выбор корпуса
@dp.message(BookingStates.building)
async def process_building(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    if message.text == "◀️ Назад к корпусам":
        await message.answer("🏢 Выберите корпус:", reply_markup=get_building_keyboard())
        return

    building_text = message.text
    if building_text not in ["🏢 Корпус 1", "🏢 Корпус 2"]:
        await message.answer("❌ Пожалуйста, выберите корпус из предложенных вариантов:")
        return

    # Извлекаем номер корпуса
    building_num = 1 if "1" in building_text else 2
    await state.update_data(building=building_num)

    await message.answer(
        f"🏢 Выбран {building_text}\n\n📋 Теперь выберите этаж:",
        reply_markup=get_floor_keyboard()
    )
    await state.set_state(BookingStates.floor)


# Выбор этажа
@dp.message(BookingStates.floor)
async def process_floor(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    if message.text == "◀️ Назад к корпусам":
        await message.answer("🏢 Выберите корпус:", reply_markup=get_building_keyboard())
        await state.set_state(BookingStates.building)
        return

    floor_text = message.text
    if floor_text not in ["1 этаж", "2 этаж", "3 этаж", "4 этаж"]:
        await message.answer("❌ Пожалуйста, выберите этаж из предложенных вариантов:")
        return

    # Извлекаем номер этажа
    floor_num = int(floor_text[0])
    user_data = await state.get_data()
    building_num = user_data['building']

    await message.answer(
        f"🏢 Корпус {building_num} | {floor_text}\n\n🚪 Выберите комнату:",
        reply_markup=get_room_keyboard(floor_num, building_num)
    )
    await state.set_state(BookingStates.room)


# Выбор комнаты
@dp.message(BookingStates.room)
async def process_room(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    if message.text == "◀️ Назад к этажам":
        await message.answer("📋 Выберите этаж:", reply_markup=get_floor_keyboard())
        await state.set_state(BookingStates.floor)
        return

    if message.text == "🏢 Ввести другую комнату":
        await message.answer(
            "🏢 Введите номер комнаты вручную (например: '1-01-05' или '2-03-15'):",
            reply_markup=get_cancel_keyboard()
        )
        return

    room_text = message.text

    # Проверяем формат комнаты (X-XX-XX)
    if '-' in room_text and len(room_text.split('-')) == 3:
        await state.update_data(room=room_text)
        await message.answer(
            "📅 Введите дату вывоза мусора (в формате ДД.ММ.ГГГГ, например 25.12.2024):",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(BookingStates.date)
    else:
        await message.answer(
            "❌ Неверный формат комнаты. Пожалуйста, выберите комнату из списка или введите в формате X-XX-XX:",
            reply_markup=get_custom_room_keyboard()
        )


# Обработка ручного ввода комнаты
@dp.message(BookingStates.room)
async def process_custom_room(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    # Принимаем любой текст как номер комнаты
    await state.update_data(room=message.text)
    await message.answer(
        "📅 Введите дату вывоза мусора (в формате ДД.ММ.ГГГГ, например 25.12.2024):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BookingStates.date)


# Получение даты
@dp.message(BookingStates.date)
async def process_date(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    date_text = message.text
    try:
        booking_date = datetime.strptime(date_text, "%d.%m.%Y")
        current_date = datetime.now()

        if booking_date.date() < current_date.date():
            await message.answer("❌ Нельзя выбрать прошедшую дату. Введите будущую дату:",
                                 reply_markup=get_cancel_keyboard())
            return

        await state.update_data(date=date_text)
        await message.answer("⏰ Введите время вывоза (в формате ЧЧ:ММ, например 14:30):",
                             reply_markup=get_cancel_keyboard())
        await state.set_state(BookingStates.time)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
                             reply_markup=get_cancel_keyboard())


# Получение времени
@dp.message(BookingStates.time)
async def process_time(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    time_text = message.text
    try:
        datetime.strptime(time_text, "%H:%M")
        await state.update_data(time=time_text)
        await message.answer(
            "📝 Хотите добавить комментарий к заказу? (например, 'большой объем' или 'строительный мусор'). Если нет, напишите 'нет'",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(BookingStates.notes)
    except ValueError:
        await message.answer("❌ Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ:",
                             reply_markup=get_cancel_keyboard())


# Получение комментария
@dp.message(BookingStates.notes)
async def process_notes(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить бронирование":
        await cmd_cancel(message, state)
        return

    notes = message.text if message.text.lower() != 'нет' else ""
    await state.update_data(notes=notes)

    # Генерируем номер для оплаты и сумму
    booking_number = "89504995471(сбер) Хусаинов ЗД"
    amount = 50

    await state.update_data(booking_number=booking_number, amount=amount)

    # Получаем данные из состояния
    user_data = await state.get_data()

    # Формируем сводку
    summary = f"""
📋 <b>Подтвердите детали брони:</b>

🏢 <b>Комната:</b> {user_data['room']}
📅 <b>Дата:</b> {user_data['date']}
⏰ <b>Время:</b> {user_data['time']}
{f"📝 <b>Комментарий:</b> {user_data['notes']}" if user_data.get('notes') else ''}

💰 <b>К оплате:</b> {amount} руб.
📞 <b>Номер для перевода:</b> <code>{booking_number}</code>

Всё верно?
    """
    await message.answer(summary, parse_mode="HTML", reply_markup=get_confirmation_keyboard())
    await state.set_state(BookingStates.confirmation)


# Подтверждение бронирования
@dp.message(BookingStates.confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    user_response = message.text.lower()

    if user_response == "✅ подтвердить" or user_response == "да" or user_response == "подтвердить":
        user_data = await state.get_data()
        user = message.from_user

        # Сохраняем в базу данных
        session = Session()
        try:
            booking = Booking(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                room=user_data['room'],
                booking_date=user_data['date'],
                booking_time=user_data['time'],
                phone_number=str(user_data['booking_number']),
                amount=user_data['amount'],
                notes=user_data.get('notes', ''),
                status='new'
            )
            session.add(booking)
            session.commit()

            # Сообщение пользователю
            success_text = f"""
✅ <b>Бронирование подтверждено!</b>

🏢 <b>Комната:</b> {user_data['room']}
📅 <b>Дата:</b> {user_data['date']}
⏰ <b>Время:</b> {user_data['time']}
{f"📝 <b>Комментарий:</b> {user_data['notes']}" if user_data.get('notes') else ''}

💰 <b>Сумма к оплате:</b> {user_data['amount']} руб.
📞 <b>Номер для перевода:</b> <code>{user_data['booking_number']}</code>

<b>ID брони:</b> #{booking.id}

Спасибо за бронирование! 🗑️
            """
            await message.answer(success_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

            # Добавляем ссылку на /start для нового бронирования
            start_text = "🔹 Если нужно еще одно бронирование, нажмите /start"
            await message.answer(start_text, reply_markup=get_main_keyboard())

            # Уведомление в групповой чат
            group_text = f"""
🚀 <b>НОВАЯ БРОНЯ!</b>

📋 <b>ID:</b> #{booking.id}
👤 <b>Клиент:</b> {user.first_name or ''} {f'(@{user.username})' if user.username else ''}
🏢 <b>Комната:</b> {user_data['room']}
📅 <b>Дата:</b> {user_data['date']}
⏰ <b>Время:</b> {user_data['time']}
💰 <b>Сумма:</b> {user_data['amount']} руб.
📞 <b>Номер оплаты:</b> <code>{user_data['booking_number']}</code>
{f"📝 <b>Комментарий:</b> {user_data['notes']}" if user_data.get('notes') else ''}

⏰ <b>Создано:</b> {booking.created_at.strftime('%d.%m.%Y %H:%M')}
            """
            try:
                await bot.send_message(chat_id=GROUP_CHAT_ID, text=group_text, parse_mode="HTML")
                logger.info(f"Уведомление отправлено в группу {GROUP_CHAT_ID}")
            except Exception as e:
                logger.error(f"Ошибка отправки в группу: {e}")

            # Личное уведомление администратору
            try:
                await bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📨 Новое бронирование #{booking.id} от {user.first_name or 'пользователя'}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки администратору: {e}")

        except Exception as e:
            logger.error(f"Ошибка при сохранении в БД: {e}")
            await message.answer("❌ Произошла ошибка при сохранении брони. Попробуйте позже.")
        finally:
            session.close()

        await state.clear()

    elif user_response == "❌ отменить" or user_response == "отменить" or user_response == "нет":
        await message.answer("❌ Бронирование отменено. Чтобы начать заново, нажмите /start",
                             reply_markup=get_main_keyboard())
        await state.clear()
    else:
        await message.answer("❌ Непонятный ответ. Пожалуйста, нажмите '✅ Подтвердить' или '❌ Отменить'")


# Команда для отмены существующего бронирования (по ID)
@dp.message(Command("cancel_booking"))
async def cmd_cancel_booking(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /cancel_booking <ID_брони>\n\nНапример: /cancel_booking 5")
        return

    try:
        booking_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный ID брони. ID должен быть числом.")
        return

    session = Session()
    try:
        booking = session.query(Booking).filter(
            Booking.id == booking_id,
            Booking.user_id == message.from_user.id
        ).first()

        if not booking:
            await message.answer("❌ Бронирование не найдено. Проверьте ID или убедитесь, что это ваше бронирование.")
            return

        if booking.status == 'cancelled':
            await message.answer("ℹ️ Это бронирование уже отменено.")
            return

        booking.status = 'cancelled'
        booking.updated_at = datetime.now()
        session.commit()

        await message.answer(f"✅ Бронирование #{booking_id} успешно отменено.")

        # Добавляем ссылку на /start для нового бронирования
        start_text = "🔹 Чтобы создать новое бронирование, нажмите /start"
        await message.answer(start_text, reply_markup=get_main_keyboard())

        # Уведомление в группу об отмене
        cancel_text = f"""
🚫 <b>БРОНИРОВАНИЕ ОТМЕНЕНО</b>

📋 <b>ID:</b> #{booking.id}
👤 <b>Клиент:</b> {booking.first_name} {f'(@{booking.username})' if booking.username else ''}
🏢 <b>Комната:</b> {booking.room}
📅 <b>Дата:</b> {booking.booking_date}
⏰ <b>Время:</b> {booking.booking_time}
⏳ <b>Отменено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        try:
            await bot.send_message(chat_id=GROUP_CHAT_ID, text=cancel_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об отмене: {e}")

    except Exception as e:
        logger.error(f"Ошибка при отмене бронирования: {e}")
        await message.answer("❌ Ошибка при отмене бронирования.")
    finally:
        session.close()


# Обработка любых других сообщений
@dp.message()
async def handle_other_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("❌ Сначала завершите текущее бронирование или отмените его командой /cancel")
    else:
        await message.answer(
            "🤖 Используйте команды:\n/start - начать работу\n/book - новое бронирование\n/my_bookings - мои брони\n/help - помощь",
            reply_markup=get_main_keyboard()
        )


# Запуск бота
async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())