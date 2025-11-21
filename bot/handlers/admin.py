import logging
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database, User, Ad
from keyboards import Keyboards
from states import AdminStates, AdStates
from config import Config
from utils.validators import validate_price, validate_phone

# Создаем роутер для админ-обработчиков
router = Router()
db = Database()

# ========== АДМИН КОМАНДЫ ==========

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """
    Главная админ-панель
    """
    if message.from_user.id != Config.ADMIN_ID:
        await message.answer("❌ Доступ запрещен")
        return
    
    # Получаем статистику
    users_count = db.get_users_count()
    ads_count = db.get_ads_count()
    pending_ads = db.get_pending_ads_count()
    today_ads = db.get_today_ads_count()
    
    admin_text = f"""
🛠️ <b>Панель администратора</b>

📊 <b>Статистика системы:</b>
👥 Пользователи: <code>{users_count}</code>
📋 Всего объявлений: <code>{ads_count}</code>
⏳ На модерации: <code>{pending_ads}</code>
📅 Сегодня: <code>{today_ads}</code>

<b>Доступные команды:</b>
• /moderate - Модерация объявлений
• /stats - Детальная статистика
• /users - Управление пользователями
• /add_ad - Добавить объявление вручную
• /broadcast - Рассылка сообщений
• /settings - Настройки системы

<b>Быстрые действия:</b>
    """
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="📋 Модерация", callback_data="admin_moderate"))
    keyboard.add(types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    keyboard.add(types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"))
    keyboard.add(types.InlineKeyboardButton(text="🏠 Добавить объявление", callback_data="admin_add_ad"))
    keyboard.add(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    keyboard.add(types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"))
    keyboard.adjust(2)
    
    await message.answer(admin_text, reply_markup=keyboard.as_markup(), parse_mode='HTML')

@router.message(Command("moderate"))
async def cmd_moderate(message: Message):
    """
    Модерация объявлений
    """
    if message.from_user.id != Config.ADMIN_ID:
        return
    
    await show_next_pending_ad(message)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Детальная статистика
    """
    if message.from_user.id != Config.ADMIN_ID:
        return
    
    # Получаем расширенную статистику
    stats = db.get_detailed_stats()
    
    stats_text = f"""
📈 <b>Детальная статистика системы</b>

<b>Пользователи:</b>
• Всего: <code>{stats['total_users']}</code>
• Активных: <code>{stats['active_users']}</code>
• Новых сегодня: <code>{stats['new_users_today']}</code>

<b>Объявления:</b>
• Всего: <code>{stats['total_ads']}</code>
• Одобренных: <code>{stats['approved_ads']}</code>
• На модерации: <code>{stats['pending_ads']}</code>
• Отклоненных: <code>{stats['rejected_ads']}</code>

<b>По типам недвижимости:</b>
"""
    
    for prop_type, count in stats['ads_by_type'].items():
        stats_text += f"• {prop_type}: <code>{count}</code>\n"
    
    stats_text += f"\n<b>По ролям пользователей:</b>"
    for role, count in stats['users_by_role'].items():
        stats_text += f"\n• {role}: <code>{count}</code>"
    
    await message.answer(stats_text, parse_mode='HTML')

@router.message(Command("add_ad"))
async def cmd_add_ad(message: Message, state: FSMContext):
    """
    Ручное добавление объявления админом
    """
    if message.from_user.id != Config.ADMIN_ID:
        return
    
    await message.answer(
        "🏠 <b>Ручное добавление объявления</b>\n\n"
        "Вы можете добавить объявление вручную. Выберите тип недвижимости:",
        reply_markup=Keyboards.get_property_type_keyboard(),
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_for_ad_type)

# ========== РУЧНОЕ ДОБАВЛЕНИЕ ОБЪЯВЛЕНИЙ ==========

@router.callback_query(AdminStates.waiting_for_ad_type, F.data.startswith("type_"))
async def process_admin_ad_type(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора типа недвижимости для ручного добавления
    """
    prop_type = callback.data[5:]  # type_аренда -> аренда
    
    await state.update_data(
        property_type=prop_type,
        is_admin_ad=True
    )
    
    await callback.message.edit_text(
        f"🏷️ Выбран тип: <b>{prop_type}</b>\n\n"
        "Введите заголовок объявления:",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_for_ad_title)

@router.message(AdminStates.waiting_for_ad_title)
async def process_admin_ad_title(message: Message, state: FSMContext):
    """
    Обработка заголовка для ручного объявления
    """
    if len(message.text) > 100:
        await message.answer("❌ Заголовок слишком длинный. Максимум 100 символов.")
        return
    
    await state.update_data(title=message.text)
    
    await message.answer(
        "📝 Введите подробное описание объявления:"
    )
    await state.set_state(AdminStates.waiting_for_ad_description)

@router.message(AdminStates.waiting_for_ad_description)
async def process_admin_ad_description(message: Message, state: FSMContext):
    """
    Обработка описания для ручного объявления
    """
    if len(message.text) < 20:
        await message.answer("❌ Описание слишком короткое. Минимум 20 символов.")
        return
    
    await state.update_data(description=message.text)
    
    await message.answer(
        "💰 Введите цену (только числа):"
    )
    await state.set_state(AdminStates.waiting_for_ad_price)

@router.message(AdminStates.waiting_for_ad_price)
async def process_admin_ad_price(message: Message, state: FSMContext):
    """
    Обработка цены для ручного объявления
    """
    try:
        price = float(message.text.replace(' ', '').replace(',', '.'))
        
        if price <= 0:
            await message.answer("❌ Цена должна быть положительным числом.")
            return
            
        await state.update_data(price=price)
        
        # Предлагаем выбрать валюту
        keyboard = InlineKeyboardBuilder()
        keyboard.add(types.InlineKeyboardButton(text="🇺🇿 UZS", callback_data="currency_uzs"))
        keyboard.add(types.InlineKeyboardButton(text="🇺🇸 USD", callback_data="currency_usd"))
        
        await message.answer(
            "💱 Выберите валюту:",
            reply_markup=keyboard.as_markup()
        )
        await state.set_state(AdminStates.waiting_for_ad_currency)
        
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите только числа:")

@router.callback_query(AdminStates.waiting_for_ad_currency, F.data.startswith("currency_"))
async def process_admin_ad_currency(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора валюты для ручного объявления
    """
    currency = callback.data.split('_')[1]
    
    await state.update_data(currency=currency)
    
    await callback.message.edit_text(
        f"💱 Валюта: <b>{currency.upper()}</b>\n\n"
        "📍 Введите местоположение (адрес или район):",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_for_ad_location)

@router.message(AdminStates.waiting_for_ad_location)
async def process_admin_ad_location(message: Message, state: FSMContext):
    """
    Обработка местоположения для ручного объявления
    """
    await state.update_data(location=message.text)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="📸 Добавить фото", callback_data="admin_add_photos"))
    keyboard.add(types.InlineKeyboardButton(text="➡️ Пропустить", callback_data="admin_skip_photos"))
    
    await message.answer(
        "📸 Хотите добавить фотографии?",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "admin_add_photos")
async def process_admin_add_photos(callback: CallbackQuery, state: FSMContext):
    """
    Начало добавления фото для ручного объявления
    """
    await callback.message.edit_text(
        "📸 Отправьте фотографии объекта (максимум 10):\n\n"
        "Напишите 'Готово' когда закончите."
    )
    await state.set_state(AdminStates.waiting_for_ad_photos)

@router.callback_query(F.data == "admin_skip_photos")
async def process_admin_skip_photos(callback: CallbackQuery, state: FSMContext):
    """
    Пропуск добавления фото
    """
    await state.update_data(photos=[])
    await show_admin_ad_preview(callback.message, state)

@router.message(AdminStates.waiting_for_ad_photos, F.photo)
async def process_admin_ad_photo(message: Message, state: FSMContext):
    """
    Обработка фото для ручного объявления
    """
    data = await state.get_data()
    photos = data.get('photos', [])
    
    # Сохраняем file_id фото
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    
    if len(photos) >= 10:
        await message.answer("✅ Достигнут лимит в 10 фото. Создаем предпросмотр...")
        await show_admin_ad_preview(message, state)
    else:
        await message.answer(
            f"✅ Фото добавлено ({len(photos)}/10). "
            f"Отправьте еще фото или напишите 'Готово' для продолжения."
        )

@router.message(AdminStates.waiting_for_ad_photos, F.text == "Готово")
async def process_admin_finish_photos(message: Message, state: FSMContext):
    """
    Завершение добавления фото
    """
    data = await state.get_data()
    photos = data.get('photos', [])
    
    if not photos:
        await message.answer("⚠️ Фото не добавлены. Продолжаем без фото.")
    
    await show_admin_ad_preview(message, state)

async def show_admin_ad_preview(message: Message, state: FSMContext):
    """
    Показ предпросмотра ручного объявления
    """
    data = await state.get_data()
    
    preview_text = f"""
📋 <b>Предпросмотр объявления (ручное добавление)</b>

🏷️ <b>Тип:</b> {data['property_type']}
📝 <b>Заголовок:</b> {data['title']}
📄 <b>Описание:</b> {data['description']}
💰 <b>Цена:</b> {data['price']:,.0f} {data['currency'].upper()}
📍 <b>Местоположение:</b> {data['location']}
📸 <b>Фото:</b> {len(data.get('photos', []))} шт.

<b>Выберите действие:</b>
    """
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="✅ Опубликовать", callback_data="admin_publish_ad"))
    keyboard.add(types.InlineKeyboardButton(text="✏️ Редактировать", callback_data="admin_edit_ad"))
    keyboard.add(types.InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_ad"))
    keyboard.adjust(2)
    
    photos = data.get('photos', [])
    
    if photos:
        # Показываем первое фото с подписью
        media = InputMediaPhoto(
            media=photos[0],
            caption=preview_text,
            parse_mode='HTML'
        )
        await message.answer_photo(photos[0], caption=preview_text, reply_markup=keyboard.as_markup(), parse_mode='HTML')
    else:
        await message.answer(preview_text, reply_markup=keyboard.as_markup(), parse_mode='HTML')
    
    await state.set_state(AdminStates.ad_preview)

@router.callback_query(AdminStates.ad_preview, F.data == "admin_publish_ad")
async def process_admin_publish_ad(callback: CallbackQuery, state: FSMContext):
    """
    Публикация ручного объявления
    """
    data = await state.get_data()
    
    # Создаем объявление от имени админа
    ad_id = db.create_ad(
        user_id=Config.ADMIN_ID,  # ID админа как владельца
        ad_data={
            'type': data['property_type'],
            'title': data['title'],
            'description': data['description'],
            'price': data['price'],
            'currency': data['currency'],
            'location': data['location'],
            'photos': data.get('photos', [])
        }
    )
    
    # Автоматически одобряем (т.к. админ)
    db.update_ad_status(ad_id, 'approved')
    
    # Отправляем в канал
    ad = db.get_ad_by_id(ad_id)
    await send_ad_to_channel(ad, is_admin_ad=True)
    
    await callback.message.edit_text(
        "✅ <b>Объявление успешно опубликовано!</b>\n\n"
        f"🏠 <b>{ad.title}</b>\n"
        f"💰 {ad.price:,.0f} {ad.currency.upper()}\n"
        f"📍 {ad.location}\n\n"
        "Объявление автоматически одобрено и отправлено в канал.",
        parse_mode='HTML'
    )
    
    await state.clear()

@router.callback_query(AdminStates.ad_preview, F.data == "admin_edit_ad")
async def process_admin_edit_ad(callback: CallbackQuery, state: FSMContext):
    """
    Редактирование ручного объявления
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="🏷️ Тип", callback_data="edit_type"))
    keyboard.add(types.InlineKeyboardButton(text="📝 Заголовок", callback_data="edit_title"))
    keyboard.add(types.InlineKeyboardButton(text="📄 Описание", callback_data="edit_description"))
    keyboard.add(types.InlineKeyboardButton(text="💰 Цена", callback_data="edit_price"))
    keyboard.add(types.InlineKeyboardButton(text="📍 Местоположение", callback_data="edit_location"))
    keyboard.add(types.InlineKeyboardButton(text="📸 Фото", callback_data="edit_photos"))
    keyboard.add(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_back_to_preview"))
    keyboard.adjust(2)
    
    await callback.message.edit_text(
        "✏️ <b>Что вы хотите отредактировать?</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )

@router.callback_query(AdminStates.ad_preview, F.data == "admin_cancel_ad")
async def process_admin_cancel_ad(callback: CallbackQuery, state: FSMContext):
    """
    Отмена создания ручного объявления
    """
    await callback.message.edit_text(
        "❌ <b>Создание объявления отменено</b>",
        parse_mode='HTML'
    )
    await state.clear()

# ========== МОДЕРАЦИЯ ОБЪЯВЛЕНИЙ ==========

@router.callback_query(F.data == "admin_moderate")
async def admin_moderate_callback(callback: CallbackQuery):
    """
    Обработка кнопки модерации из админ-панели
    """
    if callback.from_user.id != Config.ADMIN_ID:
        return
    
    await show_next_pending_ad(callback.message)

async def show_next_pending_ad(message: Message):
    """
    Показ следующего объявления на модерации
    """
    pending_ads = db.get_pending_ads()
    
    if not pending_ads:
        await message.answer("✅ Нет объявлений для модерации")
        return
    
    ad = pending_ads[0]
    user = db.get_user_by_id(ad.user_id)
    
    ad_text = f"""
⏳ <b>Объявление на модерацию</b>

ID: <code>{ad.id}</code>
🏷️ <b>Тип:</b> {ad.type}
📝 <b>Заголовок:</b> {ad.title}
📄 <b>Описание:</b> {ad.description}
💰 <b>Цена:</b> {ad.price:,.0f} {ad.currency.upper()}
📍 <b>Местоположение:</b> {ad.location}

👤 <b>Автор:</b> {user.first_name} (@{user.username})
📅 <b>Создано:</b> {ad.created_at.strftime('%d.%m.%Y %H:%M')}
    """
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ad.id}"))
    keyboard.add(types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{ad.id}"))
    keyboard.add(types.InlineKeyboardButton(text="💬 Написать автору", url=f"tg://user?id={user.telegram_id}"))
    keyboard.add(types.InlineKeyboardButton(text="⏭️ Следующее", callback_data="admin_next_moderate"))
    keyboard.adjust(2)
    
    if ad.photos:
        await message.answer_photo(
            ad.photos[0],
            caption=ad_text,
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )
    else:
        await message.answer(ad_text, reply_markup=keyboard.as_markup(), parse_mode='HTML')

@router.callback_query(F.data.startswith("approve_"))
async def approve_ad(callback: CallbackQuery):
    """
    Одобрение объявления
    """
    if callback.from_user.id != Config.ADMIN_ID:
        return
    
    ad_id = int(callback.data.split('_')[1])
    
    # Одобряем объявление
    db.update_ad_status(ad_id, 'approved')
    
    # Отправляем в канал
    ad = db.get_ad_by_id(ad_id)
    user = db.get_user_by_id(ad.user_id)
    
    await send_ad_to_channel(ad)
    
    # Уведомляем пользователя
    await notify_user_about_approval(user.telegram_id, ad)
    
    await callback.message.edit_text(
        f"✅ <b>Объявление одобрено!</b>\n\n"
        f"🏠 {ad.title}\n"
        f"Автор уведомлен, объявление опубликовано в канале.",
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("reject_"))
async def reject_ad(callback: CallbackQuery, state: FSMContext):
    """
    Отклонение объявления с указанием причины
    """
    if callback.from_user.id != Config.ADMIN_ID:
        return
    
    ad_id = int(callback.data.split('_')[1])
    
    await state.update_data(reject_ad_id=ad_id)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Не соответствует правилам", callback_data="reject_reason_rules"))
    keyboard.add(types.InlineKeyboardButton(text="Неполная информация", callback_data="reject_reason_incomplete"))
    keyboard.add(types.InlineKeyboardButton(text="Некорректная цена", callback_data="reject_reason_price"))
    keyboard.add(types.InlineKeyboardButton(text="Другая причина", callback_data="reject_reason_other"))
    keyboard.adjust(1)
    
    await callback.message.edit_text(
        "❌ <b>Укажите причину отклонения:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("reject_reason_"))
async def process_reject_reason(callback: CallbackQuery, state: FSMContext):
    """
    Обработка причины отклонения
    """
    reason_type = callback.data.split('_')[2]
    
    reason_texts = {
        'rules': "Не соответствует правилам публикации",
        'incomplete': "Неполная информация в объявлении", 
        'price': "Некорректная цена",
        'other': "Другая причина"
    }
    
    reason = reason_texts.get(reason_type, "Другая причина")
    
    if reason_type == 'other':
        await callback.message.edit_text(
            "✍️ <b>Введите причину отклонения:</b>",
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.waiting_for_reject_reason)
    else:
        data = await state.get_data()
        ad_id = data['reject_ad_id']
        
        await complete_rejection(ad_id, reason, callback.message)
        await state.clear()

@router.message(AdminStates.waiting_for_reject_reason)
async def process_custom_reject_reason(message: Message, state: FSMContext):
    """
    Обработка пользовательской причины отклонения
    """
    data = await state.get_data()
    ad_id = data['reject_ad_id']
    
    await complete_rejection(ad_id, message.text, message)
    await state.clear()

async def complete_rejection(ad_id: int, reason: str, message: Message):
    """
    Завершение процесса отклонения объявления
    """
    # Отклоняем объявление
    db.update_ad_status(ad_id, 'rejected')
    
    # Уведомляем пользователя
    ad = db.get_ad_by_id(ad_id)
    user = db.get_user_by_id(ad.user_id)
    
    await notify_user_about_rejection(user.telegram_id, ad, reason)
    
    await message.answer(
        f"❌ <b>Объявление отклонено</b>\n\n"
        f"Причина: {reason}\n"
        f"Автор уведомлен.",
        parse_mode='HTML'
    )

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_ad_to_channel(ad: Ad, is_admin_ad: bool = False):
    """
    Отправка объявления в канал
    """
    try:
        from main import bot
        
        user = db.get_user_by_id(ad.user_id)
        
        ad_text = f"""
🏠 <b>{ad.title}</b>

{ad.description}

💰 <b>Цена:</b> {ad.price:,.0f} {ad.curre
