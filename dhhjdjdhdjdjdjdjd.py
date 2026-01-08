import os
import json
import asyncio
import logging
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

import aiofiles
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    FloodWaitError,
    AuthKeyDuplicatedError
)
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
API_ID = 23258474
API_HASH = "f5dd3f52675030a650ca2259f9fb79ce"
BOT_TOKEN = "8379847495:AAHQIC5D9fipWz76h3-y0UOsY3amN5RUD_U"
CREATOR_ID = 7370566881
BOT_USERNAME = "RETSINGBOT"
BOT_DISPLAY_NAME = "RETSING BOT"

# Создание директорий
SESSION_DIR = Path("user_sessions")
DATA_DIR = Path("user_data")
BACKUP_DIR = Path("backups")

for directory in [SESSION_DIR, DATA_DIR, BACKUP_DIR]:
    directory.mkdir(exist_ok=True)

class UserState(Enum):
    WAITING_PHONE = 1
    WAITING_CODE = 2
    WAITING_PASSWORD = 3
    WAITING_MESSAGE = 4
    WAITING_CHAT_SELECTION = 5
    MAILING_ACTIVE = 6
    IDLE = 7

class ChatType(Enum):
    CHANNEL = "channel"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    USER = "user"

@dataclass
class ChatInfo:
    id: int
    title: str
    type: ChatType
    username: Optional[str] = None
    participants_count: int = 0
    is_selected: bool = False

@dataclass
class MailingStats:
    total_sent: int = 0
    total_failed: int = 0
    start_time: Optional[datetime] = None
    last_sent_time: Optional[datetime] = None
    successful_chats: Set[int] = field(default_factory=set)
    failed_chats: Dict[int, str] = field(default_factory=dict)

@dataclass
class UserAccount:
    user_id: int
    phone: str = ""
    session_string: str = ""
    message_text: str = ""
    state: UserState = UserState.IDLE
    selected_chats: Dict[int, ChatInfo] = field(default_factory=dict)
    available_chats: Dict[int, ChatInfo] = field(default_factory=dict)
    client: Optional[TelegramClient] = None
    is_connected: bool = False
    is_mailing: bool = False
    mailing_task: Optional[asyncio.Task] = None
    code_request_time: Optional[datetime] = None
    stats: MailingStats = field(default_factory=MailingStats)
    last_activity: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)

class AccountManager:
    def __init__(self):
        self.accounts: Dict[int, UserAccount] = {}
        self._load_all_accounts()
    
    def _load_all_accounts(self):
        for file_path in DATA_DIR.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                user_id = int(file_path.stem)
                account = UserAccount(user_id=user_id)
                
                account.phone = data.get("phone", "")
                account.session_string = data.get("session_string", "")
                account.message_text = data.get("message_text", "")
                account.state = UserState(data.get("state", UserState.IDLE.value))
                
                selected_chats = data.get("selected_chats", {})
                for chat_id_str, chat_data in selected_chats.items():
                    chat_id = int(chat_id_str)
                    account.selected_chats[chat_id] = ChatInfo(
                        id=chat_id,
                        title=chat_data["title"],
                        type=ChatType(chat_data["type"]),
                        username=chat_data.get("username"),
                        participants_count=chat_data.get("participants_count", 0),
                        is_selected=True
                    )
                
                available_chats = data.get("available_chats", {})
                for chat_id_str, chat_data in available_chats.items():
                    chat_id = int(chat_id_str)
                    is_selected = chat_id in account.selected_chats
                    account.available_chats[chat_id] = ChatInfo(
                        id=chat_id,
                        title=chat_data["title"],
                        type=ChatType(chat_data["type"]),
                        username=chat_data.get("username"),
                        participants_count=chat_data.get("participants_count", 0),
                        is_selected=is_selected
                    )
                
                if data.get("created_at"):
                    account.created_at = datetime.fromisoformat(data["created_at"])
                if data.get("last_activity"):
                    account.last_activity = datetime.fromisoformat(data["last_activity"])
                
                self.accounts[user_id] = account
                
            except Exception as e:
                logger.error(f"Ошибка загрузки аккаунта {file_path}: {e}")
    
    async def save_account(self, user_id: int):
        if user_id not in self.accounts:
            return
        
        account = self.accounts[user_id]
        account.last_activity = datetime.now()
        
        data = {
            "phone": account.phone,
            "session_string": account.session_string,
            "message_text": account.message_text,
            "state": account.state.value,
            "selected_chats": {
                str(chat_id): {
                    "title": chat_info.title,
                    "type": chat_info.type.value,
                    "username": chat_info.username,
                    "participants_count": chat_info.participants_count
                }
                for chat_id, chat_info in account.selected_chats.items()
            },
            "available_chats": {
                str(chat_id): {
                    "title": chat_info.title,
                    "type": chat_info.type.value,
                    "username": chat_info.username,
                    "participants_count": chat_info.participants_count
                }
                for chat_id, chat_info in account.available_chats.items()
            },
            "created_at": account.created_at.isoformat(),
            "last_activity": account.last_activity.isoformat()
        }
        
        try:
            file_path = DATA_DIR / f"{user_id}.json"
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            backup_path = BACKUP_DIR / f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            async with aiofiles.open(backup_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        except Exception as e:
            logger.error(f"Ошибка сохранения аккаунта {user_id}: {e}")
    
    def get_account(self, user_id: int) -> Optional[UserAccount]:
        return self.accounts.get(user_id)
    
    def create_account(self, user_id: int) -> UserAccount:
        account = UserAccount(user_id=user_id)
        self.accounts[user_id] = account
        return account
    
    async def delete_account(self, user_id: int):
        if user_id in self.accounts:
            account = self.accounts[user_id]
            if account.mailing_task and not account.mailing_task.done():
                account.mailing_task.cancel()
            if account.client and account.client.is_connected():
                await account.client.disconnect()
            del self.accounts[user_id]
            
            file_path = DATA_DIR / f"{user_id}.json"
            if file_path.exists():
                file_path.unlink()

class MailingSystem:
    def __init__(self, account_manager: AccountManager):
        self.account_manager = account_manager
        self.bot_app: Optional[Application] = None
    
    async def initialize_client(self, account: UserAccount) -> bool:
        try:
            if account.client and account.client.is_connected():
                await account.client.disconnect()
            
            if not account.session_string:
                return False
            
            account.client = TelegramClient(
                StringSession(account.session_string),
                API_ID,
                API_HASH
            )
            
            await account.client.connect()
            
            if not await account.client.is_user_authorized():
                return False
            
            account.is_connected = True
            return True
        
        except AuthKeyDuplicatedError:
            logger.error(f"Сессия дублируется для пользователя {account.user_id}")
            return False
        except Exception as e:
            logger.error(f"Ошибка инициализации клиента: {e}")
            return False
    
    async def send_welcome_message(self, update: Update, account: UserAccount):
        if account.is_connected:
            keyboard = [
                [
                    InlineKeyboardButton("📝 Указать текст", callback_data="set_message"),
                    InlineKeyboardButton("👥 Выбрать чаты", callback_data="select_chats")
                ],
                [
                    InlineKeyboardButton("🚀 Запустить рассылку", callback_data="start_mailing"),
                    InlineKeyboardButton("📊 Статистика", callback_data="show_stats")
                ],
                [
                    InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                    InlineKeyboardButton("🔄 Обновить чаты", callback_data="refresh_chats")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                f"✅ <b>Бот подключен к вашему аккаунту!</b>\n\n"
                f"📱 Номер: <code>{account.phone}</code>\n"
                f"📅 Подключен: {account.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏰ Последняя активность: {account.last_activity.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"📝 <b>Текст рассылки:</b>\n"
                f"{account.message_text[:150] + '...' if account.message_text and len(account.message_text) > 150 else account.message_text or 'Не указан'}\n\n"
                f"👥 <b>Выбрано чатов:</b> {len(account.selected_chats)}\n"
                f"📊 <b>Всего доступно:</b> {len(account.available_chats)}\n\n"
                f"<i>Выберите действие:</i>"
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        
        else:
            keyboard = [[InlineKeyboardButton("🔗 Подключить аккаунт", callback_data="connect_account")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                f"👋 <b>Добро пожаловать в {BOT_DISPLAY_NAME}!</b>\n\n"
                f"Я бесплатный бот для автоматической рассылки сообщений в Telegram.\n\n"
                f"<b>Возможности:</b>\n"
                f"• 📨 Рассылка в чаты, группы и каналы\n"
                f"• ⏰ Автоматическая отправка каждые 2 минуты\n"
                f"• 📊 Подробная статистика отправки\n"
                f"• 🔒 Безопасное хранение сессий\n"
                f"• 🎯 Выбор конкретных чатов\n\n"
                f"<b>Для начала работы подключите ваш Telegram аккаунт.</b>"
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            account = self.account_manager.create_account(user_id)
        
        if account.session_string and not account.is_connected:
            if await self.initialize_client(account):
                await self.send_welcome_message(update, account)
                return
        
        account.state = UserState.WAITING_PHONE
        
        text = (
            "📱 <b>Подключение Telegram аккаунта</b>\n\n"
            "Для работы бота необходимо подключить ваш Telegram аккаунт.\n\n"
            "Отправьте мне ваш номер телефона в международном формате:\n\n"
            "<b>Примеры:</b>\n"
            "<code>+79991234567</code>\n"
            "<code>+380991234567</code>\n"
            "<code>+77011234567</code>\n\n"
            "<i>Номер телефона используется только для авторизации и не передается третьим лицам.</i>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def handle_phone_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Ошибка. Начните с команды /start")
            return
        
        phone = update.message.text.strip()
        
        if not phone.startswith('+'):
            await update.message.reply_text(
                "❌ <b>Неверный формат номера!</b>\n\n"
                "Используйте международный формат с кодом страны.\n"
                "Например: <code>+79991234567</code>",
                parse_mode="HTML"
            )
            return
        
        try:
            account.phone = phone
            
            if account.client:
                await account.client.disconnect()
            
            session_path = SESSION_DIR / f"session_{user_id}.session"
            
            account.client = TelegramClient(
                str(session_path),
                API_ID,
                API_HASH
            )
            
            await account.client.connect()
            
            sent_code = await account.client.send_code_request(phone)
            account.code_request_time = datetime.now()
            account.state = UserState.WAITING_CODE
            
            await update.message.reply_text(
                f"✅ <b>Код подтверждения отправлен!</b>\n\n"
                f"📱 На номер <code>{phone}</code> был отправлен код подтверждения.\n\n"
                f"<b>Введите код:</b>\n"
                f"<i>Код приходит в виде 5 цифр, например: 12345</i>\n\n"
                f"⚠️ <b>Код действителен 5 минут</b>",
                parse_mode="HTML"
            )
            
            await self.account_manager.save_account(user_id)
        
        except FloodWaitError as e:
            wait_time = e.seconds
            await update.message.reply_text(
                f"⏳ <b>Слишком много запросов!</b>\n\n"
                f"Пожалуйста, подождите {wait_time} секунд перед следующей попыткой.",
                parse_mode="HTML"
            )
        
        except Exception as e:
            logger.error(f"Ошибка отправки кода: {e}")
            await update.message.reply_text(
                f"❌ <b>Ошибка отправки кода:</b>\n\n"
                f"{str(e)[:200]}\n\n"
                f"Попробуйте еще раз или используйте другой номер.",
                parse_mode="HTML"
            )
    
    async def handle_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account or account.state != UserState.WAITING_CODE:
            await update.message.reply_text("❌ Сначала отправьте номер телефона командой /start")
            return
        
        code = update.message.text.strip()
        
        if not code.isdigit() or len(code) != 5:
            await update.message.reply_text(
                "❌ <b>Неверный формат кода!</b>\n\n"
                "Код должен состоять из 5 цифр.\n"
                "Пример: <code>12345</code>",
                parse_mode="HTML"
            )
            return
        
        if account.code_request_time and (datetime.now() - account.code_request_time).seconds > 300:
            await update.message.reply_text(
                "❌ <b>Код устарел!</b>\n\n"
                "Код подтверждения действителен только 5 минут.\n"
                "Пожалуйста, начните заново с команды /start",
                parse_mode="HTML"
            )
            account.state = UserState.IDLE
            return
        
        try:
            await account.client.sign_in(account.phone, code)
            
            account.session_string = account.client.session.save()
            account.is_connected = True
            account.state = UserState.WAITING_MESSAGE
            
            await self.account_manager.save_account(user_id)
            
            keyboard = [[InlineKeyboardButton("📝 Указать текст рассылки", callback_data="set_message")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "✅ <b>Аккаунт успешно подключен!</b>\n\n"
                "Теперь укажите текст, который вы хотите рассылать.",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        
        except SessionPasswordNeededError:
            account.state = UserState.WAITING_PASSWORD
            await update.message.reply_text(
                "🔐 <b>Требуется пароль двухфакторной аутентификации</b>\n\n"
                "Пожалуйста, введите пароль от вашего аккаунта:",
                parse_mode="HTML"
            )
        
        except PhoneCodeExpiredError:
            await update.message.reply_text(
                "❌ <b>Код устарел!</b>\n\n"
                "Пожалуйста, начните заново с команды /start",
                parse_mode="HTML"
            )
            account.state = UserState.IDLE
        
        except PhoneCodeInvalidError:
            await update.message.reply_text(
                "❌ <b>Неверный код подтверждения!</b>\n\n"
                "Пожалуйста, проверьте код и попробуйте еще раз.",
                parse_mode="HTML"
            )
        
        except Exception as e:
            logger.error(f"Ошибка входа: {e}")
            await update.message.reply_text(
                f"❌ <b>Ошибка входа:</b>\n\n"
                f"{str(e)[:200]}\n\n"
                f"Попробуйте еще раз или начните заново с /start",
                parse_mode="HTML"
            )
    
    async def handle_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account or account.state != UserState.WAITING_PASSWORD:
            await update.message.reply_text("❌ Неожиданный запрос пароля. Начните с /start")
            return
        
        password = update.message.text
        
        try:
            await account.client.sign_in(password=password)
            
            account.session_string = account.client.session.save()
            account.is_connected = True
            account.state = UserState.WAITING_MESSAGE
            
            await self.account_manager.save_account(user_id)
            keyboard = [[InlineKeyboardButton("📝 Указать текст рассылки", callback_data="set_message")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "✅ <b>Аккаунт успешно подключен!</b>\n\n"
                "Двухфакторная аутентификация пройдена.\n"
                "Теперь укажите текст, который вы хотите рассылать.",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        
        except Exception as e:
            logger.error(f"Ошибка пароля: {e}")
            await update.message.reply_text(
                f"❌ <b>Ошибка входа:</b>\n\n"
                f"Неверный пароль. Пожалуйста, проверьте пароль и попробуйте еще раз.",
                parse_mode="HTML"
            )
    
    async def handle_message_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Сначала подключите аккаунт через /start")
            return
        
        account.message_text = update.message.text
        account.state = UserState.WAITING_CHAT_SELECTION
        
        await self.account_manager.save_account(user_id)
        
        keyboard = [[InlineKeyboardButton("👥 Выбрать чаты для рассылки", callback_data="select_chats")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text_preview = account.message_text[:100] + "..." if len(account.message_text) > 100 else account.message_text
        
        await update.message.reply_text(
            f"✅ <b>Текст сохранен!</b>\n\n"
            f"<b>Предпросмотр:</b>\n"
            f"{text_preview}\n\n"
            f"Теперь выберите чаты, в которые будут отправляться сообщения.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    async def get_user_chats(self, account: UserAccount) -> Dict[int, ChatInfo]:
        if not account.client or not account.is_connected:
            return {}
        
        try:
            result = await account.client(GetDialogsRequest(
                offset_date=None,
                offset_id=0,
                offset_peer=InputPeerEmpty(),
                limit=200,
                hash=0
            ))
            
            chats = {}
            
            for dialog in result.dialogs:
                peer = dialog.peer
                
                if isinstance(peer, types.PeerChannel) or isinstance(peer, types.PeerChat):
                    entity = None
                    chat_id = None
                    
                    if isinstance(peer, types.PeerChannel):
                        chat_id = peer.channel_id
                        for entity_obj in result.chats:
                            if isinstance(entity_obj, types.Channel) and entity_obj.id == chat_id:
                                entity = entity_obj
                                break
                    
                    elif isinstance(peer, types.PeerChat):
                        chat_id = peer.chat_id
                        for entity_obj in result.chats:
                            if isinstance(entity_obj, types.Chat) and entity_obj.id == chat_id:
                                entity = entity_obj
                                break
                    
                    if entity and hasattr(entity, 'title'):
                        chat_type = ChatType.CHANNEL if isinstance(entity, types.Channel) else ChatType.GROUP
                        
                        if isinstance(entity, types.Channel):
                            if entity.megagroup:
                                chat_type = ChatType.SUPERGROUP
                        
                        username = getattr(entity, 'username', None)
                        participants_count = getattr(entity, 'participants_count', 0)
                        
                        chat_info = ChatInfo(
                            id=chat_id,
                            title=entity.title,
                            type=chat_type,
                            username=username,
                            participants_count=participants_count,
                            is_selected=chat_id in account.selected_chats
                        )
                        
                        chats[chat_id] = chat_info
                        account.available_chats[chat_id] = chat_info
            
            await self.account_manager.save_account(account.user_id)
            return chats
        
        except Exception as e:
            logger.error(f"Ошибка получения чатов: {e}")
            return {}
    
    async def show_chat_selection(self, update: Update, account: UserAccount, page: int = 0):
        chats = await self.get_user_chats(account)
        
        if not chats:
            keyboard = [[InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_chats")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                "❌ <b>Не удалось получить список чатов</b>\n\n"
                "Возможные причины:\n"
                "• Вы не состоите в группах или каналах\n"
                "• Проблемы с подключением\n"
                "• Сессия устарела\n\n"
                "Попробуйте обновить список или переподключить аккаунт."
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
            return
        
        chat_list = list(chats.items())
        items_per_page = 10
        total_pages = (len(chat_list) + items_per_page - 1) // items_per_page
        
        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0
        
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(chat_list))
        
        keyboard = []
        
        for chat_id, chat_info in chat_list[start_idx:end_idx]:
            emoji = "✅" if chat_id in account.selected_chats else "❌"
            type_emoji = {
                ChatType.CHANNEL: "📢",
                ChatType.GROUP: "👥",
                ChatType.SUPERGROUP: "👥",
                ChatType.USER: "👤"
            }.get(chat_info.type, "💬")
            
            title = chat_info.title[:30] + "..." if len(chat_info.title) > 30 else chat_info.title
            button_text = f"{emoji} {type_emoji} {title}"
            callback_data = f"toggle_chat_{chat_id}_{page}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        navigation_buttons = []
        
        if page > 0:
            navigation_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_page_{page-1}"))
        
        if page < total_pages - 1:
            navigation_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"chat_page_{page+1}"))
        
        if navigation_buttons:
            keyboard.append(navigation_buttons)
        
        action_buttons = [
            InlineKeyboardButton("✅ Выбрать все", callback_data="select_all_chats"),
            InlineKeyboardButton("❌ Очистить все", callback_data="clear_all_chats")
        ]
        keyboard.append(action_buttons)
        
        control_buttons = [
            InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"),
            InlineKeyboardButton("🚀 Запустить рассылку", callback_data="start_mailing")
        ]
        keyboard.append(control_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        selected_count = len(account.selected_chats)
        total_count = len(chats)
        
        text = (
            f"📋 <b>Выбор чатов для рассылки</b>\n\n"
            f"Страница {page + 1} из {total_pages}\n"
            f"Всего чатов: {total_count}\n"
            f"Выбрано: {selected_count}\n\n"
            f"<b>Обозначения:</b>\n"
            f"✅ - выбран для рассылки\n"
            f"❌ - не выбран\n"
            f"📢 - канал\n"
            f"👥 - группа/супергруппа\n\n"
            f"<i>Нажмите на чат, чтобы выбрать/отменить его</i>"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    async def toggle_chat(self, update: Update, chat_id: int, page: int):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            return
        
        if chat_id in account.selected_chats:
            del account.selected_chats[chat_id]
        else:
            if chat_id in account.available_chats:
                account.selected_chats[chat_id] = account.available_chats[chat_id]
        
        await self.account_manager.save_account(user_id)
        await self.show_chat_selection(update, account, page)
    
    async def select_all_chats(self, update: Update, account: UserAccount):
        for chat_id, chat_info in account.available_chats.items():
            account.selected_chats[chat_id] = chat_info
        
        await self.account_manager.save_account(account.user_id)
        await update.callback_query.answer(f"✅ Выбрано {len(account.selected_chats)} чатов", show_alert=False)
        await self.show_chat_selection(update, account, 0)
    
    async def clear_all_chats(self, update: Update, account: UserAccount):
        account.selected_chats.clear()
        await self.account_manager.save_account(account.user_id)
        await update.callback_query.answer("❌ Все чаты отменены", show_alert=False)
        await self.show_chat_selection(update, account, 0)
    
    async def start_mailing(self, update: Update, account: UserAccount):
        if not account.message_text:
            await update.callback_query.answer("❌ Сначала укажите текст рассылки!", show_alert=True)
            return
        
        if not account.selected_chats:
            await update.callback_query.answer("❌ Выберите хотя бы один чат для рассылки!", show_alert=True)
            return
        
        if account.is_mailing:
            await update.callback_query.answer("❌ Рассылка уже запущена!", show_alert=True)
            return
        
        if not await self.initialize_client(account):
            await update.callback_query.answer("❌ Ошибка подключения к аккаунту!", show_alert=True)
            return
        
        account.is_mailing = True
        account.state = UserState.MAILING_ACTIVE
        account.stats = MailingStats(start_time=datetime.now())
        
        account.mailing_task = asyncio.create_task(self.mailing_loop(account))
        
        await update.callback_query.answer("✅ Рассылка запущена!", show_alert=True)
        
        text = (
            f"🚀 <b>РАССЫЛКА ЗАПУЩЕНА!</b>\n\n"
            f"📝 <b>Текст:</b>\n{account.message_text[:300] + '...' if len(account.message_text) > 300 else account.message_text}\n\n"
            f"👥 <b>Чатов:</b> {len(account.selected_chats)}\n"
            f"⏱ <b>Интервал:</b> 2 минуты\n"
            f"⏰ <b>Запущена:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<i>Рассылка будет продолжаться до команды /stop</i>"
        )
        
        keyboard = [[InlineKeyboardButton("🛑 Остановить рассылку", callback_data="stop_mailing")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    async def mailing_loop(self, account: UserAccount):
        while account.is_mailing:
            iteration_start = time.time()
            
            for chat_id, chat_info in list(account.selected_chats.items()):
                if not account.is_mailing:
                    break
                
                try:
                    footer = f"\n\n{'─' * 40}\n📢 Сообщения пересылает бесплатный бот для рассылки [RETSING BOT](https://t.me/{BOT_USERNAME})"
                    full_message = account.message_text + footer
                    
                    await account.client.send_message(
                        chat_id,
                        full_message,
                        parse_mode='markdown',
                        link_preview=False
                    )
                    
                    account.stats.total_sent += 1
                    account.stats.successful_chats.add(chat_id)
                    account.stats.last_sent_time = datetime.now()
                    
                    logger.info(f"Успешно отправлено в {chat_info.title} ({chat_id})")
                    
                    await asyncio.sleep(1.5)
                    
                except FloodWaitError as e:
                    wait_time = e.seconds
                    logger.warning(f"Flood wait в {chat_info.title}: {wait_time} сек")
                    await asyncio.sleep(wait_time)
                    
                except Exception as e:
                    error_msg = str(e)[:100]
                    account.stats.total_failed += 1
                    account.stats.failed_chats[chat_id] = error_msg
                    logger.error(f"Ошибка отправки в {chat_info.title}: {error_msg}")
                    await asyncio.sleep(2)
            
            if account.is_mailing:
                elapsed_time = datetime.now() - account.stats.start_time
                hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                stats_text = (
                    f"📊 <b>СТАТИСТИКА РАССЫЛКИ</b>\n\n"
                    f"✅ Успешно отправлено: {account.stats.total_sent}\n"
                    f"❌ Ошибок: {account.stats.total_failed}\n"
                    f"⏱ Время работы: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
                    f"👥 Чатов: {len(account.selected_chats)}\n"
                    f"📈 Успешных чатов: {len(account.stats.successful_chats)}\n"
                    f"🔄 Следующий цикл через 2 минуты"
                )
                
                try:
                    await account.client.send_message(
                        account.user_id,
                        stats_text,
                        parse_mode='HTML'
                    )
                except:
                    pass
                
                iteration_time = time.time() - iteration_start
                sleep_time = max(120 - iteration_time, 10)
                
                for i in range(int(sleep_time)):
                    if not account.is_mailing:
                        break
                    await asyncio.sleep(1)
    
    async def stop_mailing(self, update: Update, account: UserAccount):
        if not account.is_mailing:
            await update.callback_query.answer("❌ Рассылка не запущена!", show_alert=True)
            return
        
        account.is_mailing = False
        account.state = UserState.IDLE
        
        if account.mailing_task and not account.mailing_task.done():
            account.mailing_task.cancel()
            try:
                await account.mailing_task
            except asyncio.CancelledError:
                pass
        
        elapsed_time = datetime.now() - account.stats.start_time
        hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        text = (
            f"🛑 <b>РАССЫЛКА ОСТАНОВЛЕНА</b>\n\n"
            f"📊 <b>Итоговая статистика:</b>\n"
            f"✅ Успешно отправлено: {account.stats.total_sent}\n"
            f"❌ Ошибок: {account.stats.total_failed}\n"
            f"⏱ Общее время: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            f"👥 Чатов в рассылке: {len(account.selected_chats)}\n"
            f"📈 Успешных чатов: {len(account.stats.successful_chats)}\n\n"
            f"<i>Для запуска новой рассылки используйте /launch</i>"
        )
        
        keyboard = [[InlineKeyboardButton("🚀 Запустить новую рассылку", callback_data="start_mailing")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.answer("✅ Рассылка остановлена", show_alert=True)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    async def launch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Сначала подключите аккаунт через /start")
            return
        
        if not account.is_connected:
            await update.message.reply_text("❌ Аккаунт не подключен. Используйте /start")
            return
        
        if not account.message_text:
            await update.message.reply_text("❌ Сначала укажите текст рассылки")
            return
        
        if not account.selected_chats:
            await update.message.reply_text("❌ Выберите чаты для рассылки")
            return
        
        await self.start_mailing(update, account)
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Нет активной сессии")
            return
        
        await self.stop_mailing(update, account)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await query.edit_message_text("❌ Сессия не найдена. Используйте /start")
            return
        
        try:
            if query.data == "connect_account":
                account.state = UserState.WAITING_PHONE
                await self.start_command(update, context)
            
            elif query.data == "set_message":
                account.state = UserState.WAITING_MESSAGE
                await query.edit_message_text(
                    "✏️ <b>Укажите текст рассылки</b>\n\n"
                    "Отправьте мне текст, который вы хотите рассылать.\n\n"
                    "<i>Можно использовать форматирование Markdown</i>",
                    parse_mode="HTML"
                )
            
            elif query.data == "select_chats":
                await self.show_chat_selection(update, account, 0)
            
            elif query.data == "start_mailing":
                await self.start_mailing(update, account)
            
            elif query.data == "stop_mailing":
                await self.stop_mailing(update, account)
            
            elif query.data == "main_menu":
                await self.send_welcome_message(update, account)
            
            elif query.data == "refresh_chats":
                await self.get_user_chats(account)
                await query.answer("✅ Список чатов обновлен", show_alert=False)
                await self.show_chat_selection(update, account, 0)
            
            elif query.data == "show_stats":
                if account.stats.start_time:
                    elapsed_time = datetime.now() - account.stats.start_time
                    hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    text = (
                        f"📊 <b>СТАТИСТИКА РАССЫЛКИ</b>\n\n"
                        f"✅ Успешно: {account.stats.total_sent}\n"
                        f"❌ Ошибок: {account.stats.total_failed}\n"
                        f"⏱ Время работы: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
                        f"👥 Чатов: {len(account.selected_chats)}\n"
                        f"📈 Успешных чатов: {len(account.stats.successful_chats)}\n"
                        f"⏰ Начало: {account.stats.start_time.strftime('%d.%m.%Y %H:%M:%S')}"
                    )
                else:
                    text = "📊 <b>Статистика отсутствует</b>\n\nРассылка еще не запускалась."
                
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            
            elif query.data == "settings":
                keyboard = [
                    [InlineKeyboardButton("📱 Изменить номер", callback_data="change_phone")],
                    [InlineKeyboardButton("🗑 Удалить аккаунт", callback_data="delete_account")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                text = (
                    f"⚙️ <b>Настройки аккаунта</b>\n\n"
                    f"📱 Номер: <code>{account.phone}</code>\n"
                    f"📅 Создан: {account.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"⏰ Последняя активность: {account.last_activity.strftime('%d.%m.%Y %H:%M')}\n"
                    f"🔗 Статус: {'✅ Подключен' if account.is_connected else '❌ Не подключен'}\n"
                    f"📊 Сохранено чатов: {len(account.available_chats)}\n\n"
                    f"<i>Выберите действие:</i>"
                )
                
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            
            elif query.data == "change_phone":
                account.state = UserState.WAITING_PHONE
                account.session_string = ""
                account.is_connected = False
                
                if account.client:
                    await account.client.disconnect()
                    account.client = None
                
                await self.account_manager.save_account(user_id)
                
                await query.edit_message_text(
                    "📱 <b>Смена номера телефона</b>\n\n"
                    "Отправьте новый номер телефона в международном формате:\n\n"
                    "<code>+79991234567</code>",
                    parse_mode="HTML"
                )
            
            elif query.data == "delete_account":
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete"),
                        InlineKeyboardButton("❌ Нет, отмена", callback_data="main_menu")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
                    "Вы уверены, что хотите удалить аккаунт?\n\n"
                    "Это действие:\n"
                    "• Удалит все данные аккаунта\n"
                    "• Остановит все активные рассылки\n"
                    "• Удалит сессию Telegram\n\n"
                    "<b>Действие необратимо!</b>",
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            
            elif query.data == "confirm_delete":
                await self.account_manager.delete_account(user_id)
                await query.edit_message_text(
                    "✅ <b>Аккаунт удален</b>\n\n"
                    "Все данные были удалены.\n"
                    "Для создания нового аккаунта используйте /start",
                    parse_mode="HTML"
                )
            
            elif query.data.startswith("toggle_chat_"):
                parts = query.data.split("_")
                if len(parts) >= 3:
                    chat_id = int(parts[2])
                    page = int(parts[3]) if len(parts) > 3 else 0
                    await self.toggle_chat(update, chat_id, page)
            
            elif query.data.startswith("chat_page_"):
                page = int(query.data.split("_")[2])
                await self.show_chat_selection(update, account, page)
            
            elif query.data == "select_all_chats":
                await self.select_all_chats(update, account)
            
            elif query.data == "clear_all_chats":
                await self.clear_all_chats(update, account)
        
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", parse_mode="HTML")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not update.message or not update.message.text:
            return
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Сначала используйте команду /start")
            return
        
        try:
            if account.state == UserState.WAITING_PHONE:
                await self.handle_phone_number(update, context)
            
            elif account.state == UserState.WAITING_CODE:
                await self.handle_code(update, context)
            
            elif account.state == UserState.WAITING_PASSWORD:
                await self.handle_password(update, context)
            
            elif account.state == UserState.WAITING_MESSAGE:
                await self.handle_message_text(update, context)
            
            else:
                await update.message.reply_text(
                    "Используйте кнопки меню или команды:\n"
                    "/start - начало работы\n"
                    "/launch - запуск рассылки\n"
                    "/stop - остановка рассылки"
                )
        
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
    
    async def setup_handlers(self):
        self.bot_app.add_handler(CommandHandler("start", self.start_command))
        self.bot_app.add_handler(CommandHandler("launch", self.launch_command))
        self.bot_app.add_handler(CommandHandler("stop", self.stop_command))
        self.bot_app.add_handler(CommandHandler("help", self.help_command))
        self.bot_app.add_handler(CommandHandler("stats", self.stats_command))
        
        self.bot_app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            f"🆘 <b>Помощь по боту {BOT_DISPLAY_NAME}</b>\n\n"
            f"<b>Основные команды:</b>\n"
            f"/start - Начать работу\n"
            f"/launch - Запустить рассылку\n"
            f"/stop - Остановить рассылку\n"
            f"/stats - Показать статистику\n"
            f"/help - Эта справка\n\n"
            f"<b>Как работает бот:</b>\n"
            f"1. Подключаете Telegram аккаунт\n"
            f"2. Указываете текст рассылки\n"
            f"3. Выбираете чаты для рассылки\n"
            f"4. Запускаете рассылку\n\n"
            f"<b>Особенности:</b>\n"
            f"• Рассылка происходит каждые 2 минуты\n"
            f"• В каждом сообщении добавляется подпись\n"
            f"• Статистика отправляется регулярно\n"
            f"• Сессии сохраняются безопасно\n\n"
            f"<b>Поддержка:</b>\n"
            f"Создатель: {CREATOR_ID}\n"
            f"Бот: @{BOT_USERNAME}"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        account = self.account_manager.get_account(user_id)
        if not account:
            await update.message.reply_text("❌ Сначала подключите аккаунт через /start")
            return
        
        if not account.stats.start_time:
            await update.message.reply_text("📊 <b>Статистика отсутствует</b>\n\nРассылка еще не запускалась.", parse_mode="HTML")
            return
        
        elapsed_time = datetime.now() - account.stats.start_time
        hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        text = (
            f"📊 <b>СТАТИСТИКА РАССЫЛКИ</b>\n\n"
            f"✅ Успешно отправлено: {account.stats.total_sent}\n"
            f"❌ Ошибок: {account.stats.total_failed}\n"
            f"⏱ Время работы: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            f"👥 Чатов в рассылке: {len(account.selected_chats)}\n"
            f"📈 Успешных чатов: {len(account.stats.successful_chats)}\n"
            f"⏰ Начало: {account.stats.start_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"🔄 Статус: {'✅ Активна' if account.is_mailing else '❌ Остановлена'}"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    async def run(self):
        try:
            self.bot_app = Application.builder().token(BOT_TOKEN).build()
            await self.setup_handlers()
            
            logger.info(f"Бот {BOT_DISPLAY_NAME} запущен успешно!")
            logger.info(f"ID создателя: {CREATOR_ID}")
            logger.info(f"Папка сессий: {SESSION_DIR}")
            logger.info(f"Папка данных: {DATA_DIR}")
            
            # Простой запуск без updater
            await self.bot_app.initialize()
            await self.bot_app.start()
            
            # Просто ждем
            while True:
                await asyncio.sleep(3600)
                
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise
        finally:
            if self.bot_app:
                await self.bot_app.stop()

async def cleanup(account_manager: AccountManager):
    logger.info("Очистка ресурсов...")
    
    for user_id, account in list(account_manager.accounts.items()):
        try:
            if account.is_mailing:
                account.is_mailing = False
                if account.mailing_task and not account.mailing_task.done():
                    account.mailing_task.cancel()
            
            if account.client and account.client.is_connected():
                await account.client.disconnect()
            
            await account_manager.save_account(user_id)
        except Exception as e:
            logger.error(f"Ошибка при очистке аккаунта {user_id}: {e}")

def main():
    account_manager = AccountManager()
    mailing_system = MailingSystem(account_manager)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(mailing_system.run())
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
    finally:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup(account_manager))

if __name__ == "__main__":
    main()