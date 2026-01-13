from telethon import TelegramClient, events, Button
import logging
from datetime import datetime, timedelta
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
from telethon.tl.types import PeerUser
from telethon.tl.types import User
from telethon import types
from telethon.tl.types import Channel, ChatAdminRights, User
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.types import InputPeerChat
from telethon.errors import ChatAdminRequiredError, UserNotParticipantError
from telethon.tl.types import ChatBannedRights, ChannelParticipantsAdmins
from telethon.tl.types import UserStatusRecently
from telethon.tl.custom import Button
import json
import os
import asyncio
import sqlite3
import time
import requests
import random
import re
import hashlib
import uuid
from datetime import datetime, timedelta  # Правильный импорт
from collections import defaultdict

user_scammers_count = {}
user_states = {}
checks_count = 0


# Настройки логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
API_ID = '27231812'
API_HASH = '59d6d299a99f9bb97fcbf5645d9d91e9'
BOT_TOKEN = '8502910736:AAFQKj8DJMhbUUASonk6bOAbgFefvhFh878'
ADMINS = [262511724]  # ID администраторов
LOG_CHANNEL = 'https://t.me/+cnym32Oi-mJiMGNi'  # Ссылка на канал логов

# Владельцы бота
OWNER_ID = [262511724]

# Добавьте после других глобальных переменных
user_states = {}
APPEAL_CHAT_ID = -1003516817505  # Замените на реальный ID чата для апелляций

class Database:
    def __init__(self, db_name='Ice.db'):
        logging.info("Инициализация базы данных...")
        self.users = {}
        self.conn = sqlite3.connect(db_name, isolation_level=None)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.conn.row_factory = sqlite3.Row  # Преобразует результаты в словарь
        self.lock = asyncio.Lock()
        self.create_tables()  # Вызов метода для создания таблиц
        self.check_table_structure()  # Проверка структуры таблицы

    def create_tables(self):
        logging.info("Проверка и создание таблиц если не существуют...")

        # Таблица пользователей
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role_id INTEGER DEFAULT 0,
            check_count INTEGER DEFAULT 0,
            last_check_date TEXT,
            country TEXT,
            channel TEXT,
            custom_photo TEXT,
            custom_photo_url TEXT,
            premium_points INTEGER DEFAULT 0,
            description TEXT,
            scammers_count INTEGER DEFAULT 0,
            scammers_slept INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            role TEXT,
            custom_status TEXT,
            granted_by_id INTEGER,
            curator_id INTEGER,
            allowance INTEGER DEFAULT 0,
            FOREIGN KEY(curator_id) REFERENCES users(user_id)
        )''')
        logging.info("Таблица users проверена/создана")

        # Таблица премиум пользователей
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY,
            expiry_date TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )''')
        logging.info("Таблица premium_users проверена/создана")

        # Таблица проверок
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS checks (
            check_id INTEGER PRIMARY KEY AUTOINCREMENT,
            checker_id INTEGER,
            target_id INTEGER,
            check_date TEXT,
            description TEXT,
            FOREIGN KEY(checker_id) REFERENCES users(user_id),
            FOREIGN KEY(target_id) REFERENCES users(user_id)
        )''')
        logging.info("Таблица checks проверена/создана")

        # Таблица мошенников
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS scammers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            reason TEXT,
            reported_by TEXT,
            description TEXT,
            reporter_id INTEGER,
            scammer_id INTEGER,
            extra_info TEXT,
            unique_id VARCHAR(255),
            FOREIGN KEY(scammer_id) REFERENCES users(user_id)
        )''')
        logging.info("Таблица scammers проверена/создана")

        # Таблица статистики
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS statistics (
            total_messages INTEGER DEFAULT 0
        )''')
        # Добавляем начальную запись только если таблица пустая
        self.cursor.execute('INSERT OR IGNORE INTO statistics (total_messages) VALUES (0)')
        logging.info("Таблица statistics проверена/создана")

        # Таблица причин
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS reasons (
            user_id INTEGER PRIMARY KEY,
            reason TEXT
        )''')
        logging.info("Таблица reasons проверена/создана")

        # Таблица стажеров
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS trainees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )''')
        logging.info("Таблица trainees проверена/создана")

        # Таблица сообщений
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            content TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )''')
        logging.info("Таблица messages проверена/создана")

        # Таблица доверия
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS trust (
            user_id INTEGER PRIMARY KEY,
            granted_by INTEGER,
            grant_date TEXT
        )''')
        logging.info("Таблица trust проверена/создана")

        self.conn.commit()
        logging.info("Все таблицы проверены/созданы")

    def check_table_structure(self):
        logging.info("Проверка структуры таблицы users...")
        self.cursor.execute("PRAGMA table_info(users);")
        columns = self.cursor.fetchall()
        for column in columns:
            print(column)  # Вывод структуры таблицы

    def user_exists(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()[0] > 0
        cursor.close()
        return exists

    def execute(self, query, params=()):
        """
        Выполняет SQL-запрос с передачей параметров.
        """
        try:
            self.cursor.execute(query, params)  # Выполнение запроса
            self.conn.commit()  # Сохранение изменений
        except sqlite3.Error as e:
            print(f"Ошибка при выполнении запроса: {e}")  # Обработка ошибок

    def update_total_messages(self, count):
        try:
            logging.info("Обновление количества сообщений...")
            self.cursor.execute('UPDATE statistics SET total_messages = total_messages + ?', (count,))
            self.conn.commit()
            current_count = self.get_total_messages()
            logging.info(f"Текущее количество сообщений в базе данных: {current_count}")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления количества сообщений: {e}")

    def get_total_messages(self):
        self.cursor.execute('SELECT total_messages FROM statistics')
        result = self.cursor.fetchone()
        return result[0] if result is not None else 0

    def get_granted_by(self, user_id):
        """Получает ID гаранта для указанного user_id."""
        self.cursor.execute("SELECT granted_by_id FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Гарант найден для user_id {user_id}: {result[0]}")
        else:
            logging.warning(f"Гарант не найден для user_id {user_id}.")
        return result[0] if result else None

    def increment_scammers_count(self, user_id):
        """Увеличивает счетчик слитых скаммеров для пользователя с указанным user_id."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET scammers_slept = scammers_slept + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_user(self, user_id, username, role_id=0):
        try:
            self.cursor.execute('''
                INSERT INTO users (user_id, username, role_id)
                VALUES (?, ?, ?)
            ''', (user_id, username, role_id))
            self.conn.commit()
            logging.info(f"Пользователь {username} с ID {user_id} добавлен с ролью {role_id}.")
        except Exception as e:
            logging.error(f"Ошибка при добавлении пользователя: {e}")

    def get_user_role(self, user_id):
        self.cursor.execute('SELECT role_id FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        role = result[0] if result else 0
        logging.info(f"Роль пользователя {user_id}: {role}")
        return role

    def update_user(self, user_id, country=None, channel=None):
        logging.info(f"Обновление пользователя {user_id}: страна - {country}, канал - {channel}")

        # Явная проверка на None для страны
        if country is not None:
            logging.info(f"Обновляем страну на: {country}")
            self.cursor.execute('UPDATE users SET country = ? WHERE user_id = ?', (country, user_id))

        # Явная проверка на None для канала
        if channel is not None:
            logging.info(f"Обновляем канал на: {channel}")
            self.cursor.execute('UPDATE users SET channel = ? WHERE user_id = ?', (channel, user_id))

        # Выполнение коммита для сохранения изменений
        self.conn.commit()

        # Проверка обновленных данных
        self.cursor.execute('SELECT country, channel FROM users WHERE user_id = ?', (user_id,))
        user_data = self.cursor.fetchone()

        # Логирование обновленных данных
        if user_data:
            logging.info(
                f"Данные пользователя после обновления: id={user_id}, страна={user_data[0]}, канал={user_data[1]}")
        else:
            logging.warning(f"Пользователь с id={user_id} не найден после обновления.")

    def get_user_allowance(self, user_id):
        """Получает сумму ручения для указанного пользователя."""
        try:
            self.cursor.execute("SELECT allowance FROM users WHERE user_id = ?", (user_id,))
            result = self.cursor.fetchone()
            if result:
                allowance = result[0]
                logging.info(f"Сумма ручения для пользователя {user_id}: {allowance}")
                return allowance
            else:
                logging.warning(f"Пользователь с ID {user_id} не найден.")
                return None
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении суммы ручения для пользователя {user_id}: {e}")
            return None

    def get_user_custom_photo(self, user_id):
        logging.info(f"Attempting to retrieve custom photo for user_id: {user_id}")

        try:
            # Изменяем запрос на правильный столбец
            cursor = self.cursor.execute('SELECT custom_photo_url FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            logging.info(f"SQL query executed for user_id {user_id}. Result: {result}")

            if result:
                custom_photo = result[0]
                logging.info(f"Retrieved custom photo for user {user_id}: {custom_photo}")
            else:
                logging.warning(f"No custom photo found for user_id: {user_id}. Result was None.")
                custom_photo = None

        except Exception as e:
            logging.error(f"Error retrieving custom photo for user_id {user_id}: {str(e)}")
            custom_photo = None

        if custom_photo is None:
            logging.info(f"Custom photo for user_id {user_id} is None or not found.")
        else:
            logging.info(f"Custom photo URL for user_id {user_id}: {custom_photo}")

        return custom_photo

    def get_user_custom_photo_url(self, user_id):
        """Получает URL кастомного фото пользователя"""
        try:
            self.cursor.execute('SELECT custom_photo_url FROM users WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            return result[0] if result and result[0] else None
        except Exception as e:
            logging.error(f"Error getting custom photo for {user_id}: {e}")
            return None

    def get_user_curator(self, user_id):
        query = "SELECT curator_id FROM users WHERE user_id = ?"
        cursor = self.conn.cursor()  # Изменено на self.conn
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_user_name(self, user_id):
        query = "SELECT username FROM users WHERE user_id = ?"
        cursor = self.conn.cursor()
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        return result[0] if result else "Не указано"

    def get_last_spin(self, user_id):
        """Получает время последнего использования команды рулетки для указанного пользователя."""
        self.cursor.execute('SELECT last_spin FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def update_last_spin(self, user_id):
        """Обновляет время последнего использования команды рулетки для указанного пользователя."""
        self.cursor.execute('UPDATE users SET last_spin = ? WHERE user_id = ?', (datetime.now(), user_id))
        self.conn.commit()

    def add_grant(self, user_id, granted_by_id):
        """Добавляет запись о гарантии для пользователя."""
        try:
            self.cursor.execute('''
                INSERT INTO trust (user_id, granted_by, grant_date)
                VALUES (?, ?, ?)
            ''', (user_id, granted_by_id, datetime.now().isoformat()))
            self.conn.commit()
            logging.info(f"Запись о гарантии для user_id {user_id} добавлена. Granted by ID: {granted_by_id}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении записи о гарантии для user_id {user_id}: {e}")

    def set_profile_checks_count(self, user_id, checks_count):
        # Устанавливаем количество проверок для пользователя
        logging.info(f"Устанавливаем количество проверок для пользователя {user_id}: {checks_count}")

        # Проверяем, существует ли пользователь
        if self.get_user(user_id) is None:
            logging.warning(f"Пользователь {user_id} не найден. Не удается установить количество проверок.")
            return

        self.cursor.execute("UPDATE users SET checks_count = ? WHERE user_id = ?", (checks_count, user_id))
        self.conn.commit()
        logging.info(f"Количество проверок для пользователя {user_id} успешно установлено на {checks_count}")

    def get_profile_checks_count(self, user_id):
        # Получаем количество проверок для пользователя
        logging.info(f"Запрос количества проверок для пользователя {user_id}")
        self.cursor.execute("SELECT checks_count FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()

        if result is not None:
            logging.info(f"Количество проверок для пользователя {user_id}: {result[0]}")
        else:
            logging.warning(f"Пользователь {user_id} не найден в базе данных.")

        return result[0] if result else None

    def update_profile_checks_count(self, user_id, checks_count):
        # Обновляем количество проверок профиля
        if checks_count < 0:
            logging.warning(
                f"Попытка установить отрицательное количество проверок для пользователя {user_id}. Устанавливаем 0.")
            checks_count = 0

        logging.info(f"Обновляем количество проверок для пользователя {user_id} на {checks_count}")
        self.cursor.execute("UPDATE users SET checks_count = ? WHERE user_id = ?", (checks_count, user_id))
        self.conn.commit()
        logging.info(f"Количество проверок для пользователя {user_id} успешно обновлено на {checks_count}")

    def add_premium(self, user_id, expiry_date):
        """Добавляет пользователя в премиум с указанной датой окончания."""
        try:
            self.cursor.execute('''
                INSERT INTO premium_users (user_id, expiry_date)
                VALUES (?, ?)
            ''', (user_id, expiry_date))
            self.conn.commit()
            logging.info(f"Пользователь {user_id} добавлен в премиум до {expiry_date}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении пользователя {user_id} в премиум: {e}")

    def is_premium_user(self, user_id):
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            expiry_date = result[0]
            logging.info(f"Пользователь {user_id} имеет премиум статус до {expiry_date}.")
            return expiry_date
        else:
            logging.warning(f"Пользователь {user_id} не найден в таблице premium_users.")
            return None

    def remove_premium(self, user_id):
        # Удаляем премиум статус пользователя из таблицы users
        self.cursor.execute('UPDATE users SET premium = NULL, premium_expiry = NULL WHERE user_id = ?', (user_id,))
        # Удаляем запись из таблицы premium_users
        self.cursor.execute('DELETE FROM premium_users WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def get_premium_expiry(self, user_id):
        """Возвращает дату истечения премиум статуса для пользователя."""
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        logging.info(f"Результат запроса для пользователя {user_id}: {result}")
        return result[0] if result else None

    def increment_check_count(self, user_id):
        """Увеличивает счетчик проверок для пользователя с указанным user_id, добавляя пользователя в базу, если он не найден."""
        try:
            # Проверяем, существует ли пользователь
            self.cursor.execute('SELECT COUNT(*) FROM users WHERE user_id = ?', (user_id,))
            user_exists = self.cursor.fetchone()[0] > 0

            if not user_exists:
                # Если пользователь не найден, добавляем его в базу данных
                self.cursor.execute('INSERT INTO users (user_id, check_count) VALUES (?, ?)', (user_id, 0))
                logging.info(f"Пользователь с ID {user_id} добавлен в базу данных.")

            # Увеличиваем счетчик
            self.cursor.execute('UPDATE users SET check_count = check_count + 1 WHERE user_id = ?', (user_id,))
            self.conn.commit()
            logging.info(f"Счетчик проверок для пользователя {user_id} увеличен.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления счетчика проверок для {user_id}: {e}")

    def update_warnings(self, user_id):
        try:
            self.cursor.execute('UPDATE users SET warnings = warnings + 1 WHERE user_id = ?', (user_id,))
            self.conn.commit()
            logging.info(f"Количество выговоров для пользователя {user_id} увеличено.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления выговоров для {user_id}: {e}")

    def get_warnings_count(self, user_id):
        result = self.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (user_id,)).fetchone()
        return result[0] if result is not None else 0

    def reset_warnings(self, user_id):
        """Сбрасывает количество выговоров до 0 для указанного пользователя."""
        self.cursor.execute('UPDATE users SET warnings = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
        logging.info(f"Количество выговоров для пользователя {user_id} сброшено до 0.")

    def delete_old_description(self, user_id):
        """Удаляет старое описание."""
        self.cursor.execute("DELETE FROM reasons WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_or_update_premium_user(self, user_id, expiry_date):
        try:
            existing_user = self.cursor.execute('SELECT * FROM premium_users WHERE user_id = ?', (user_id,)).fetchone()
            if existing_user:
                self.cursor.execute('UPDATE premium_users SET expiry_date = ? WHERE user_id = ?',
                                    (expiry_date, user_id))
                logging.info(f"Обновлена дата истечения для пользователя {user_id}: {expiry_date}")
            else:
                self.cursor.execute('INSERT INTO premium_users (user_id, expiry_date) VALUES (?, ?)',
                                    (user_id, expiry_date))
                logging.info(f"Добавлен пользователь {user_id} с премиум статусом до {expiry_date}")
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении/обновлении пользователя {user_id} в премиум: {e}")

    def update_description(self, user_id, new_description):
        try:
            # Обновление описания пользователя в базе данных
            self.cursor.execute("UPDATE users SET description = ? WHERE user_id = ?", (new_description, user_id))
            self.conn.commit()  # Зафиксировать изменения

            # Логирование успешного обновления
            logging.info(f"Описание для пользователя {user_id} обновлено на: {new_description}")

            # Вставка нового описания в статус
            self.update_status(user_id, new_description)
        except Exception as e:
            logging.error(f"Ошибка при обновлении описания: {str(e)}")

    def is_user_in_db(self, user_id):
        """Проверяет, есть ли пользователь в базе данных."""
        self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_user_info(self, user_id):
        self.cursor.execute('''
            SELECT user_id, username, role 
            FROM users 
            WHERE user_id = ?
        ''', (user_id,))
        return self.cursor.fetchone()  # Возвращает sqlite3.Row

    def update_status(self, user_id, new_description):
        try:
            # Обновление статуса с новым описанием
            status_message = f"Новое описание: {new_description}"
            self.cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (status_message, user_id))
            self.conn.commit()  # Зафиксировать изменения

            logging.info(f"Статус для пользователя {user_id} обновлен на: {status_message}")
        except Exception as e:
            logging.error(f"Ошибка при обновлении статуса: {str(e)}")

    def update_user_description(self, user_id, description):
        """Обновляет описание пользователя."""
        try:
            logging.info(f"Попытка обновления описания пользователя {user_id} на: {description}.")

            # Проверяем, существует ли пользователь перед обновлением
            existing_user = self.get_user(user_id)
            if not existing_user:
                logging.warning(f"Пользователь с ID {user_id} не найден. Описание не может быть обновлено.")
                return False

            # Обновляем описание
            self.cursor.execute('UPDATE users SET description = ? WHERE user_id = ?', (description, user_id))
            self.conn.commit()

            # Проверяем, обновилось ли описание
            updated_description = self.get_user_description(user_id)
            if updated_description == description:
                logging.info(f"Описание пользователя {user_id} успешно обновлено на: {description}.")
            else:
                logging.error(
                    f"Описание пользователя {user_id} не обновилось. Текущее значение: {updated_description}.")

            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления описания для {user_id}: {e}")
            return False

    def get_user_description(self, user_id):
        try:
            self.cursor.execute('SELECT description FROM scammers WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            if result and result[0]:
                logging.info(f"Описание для пользователя {user_id}: {result[0]}.")
                return result[0]
            else:
                logging.warning(f"Описание для пользователя {user_id} не найдено.")
                return "Описание отсутствует"
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении описания для пользователя {user_id}: {e}")
            return "Ошибка базы данных"

    def update_role(self, user_id, role_id, granted_by_id=None):
        try:
            self.cursor.execute('UPDATE users SET role_id = ? WHERE user_id = ?', (role_id, user_id))

            if granted_by_id is not None:
                self.cursor.execute('UPDATE users SET granted_by_id = ? WHERE user_id = ?', (granted_by_id, user_id))

            # ВСЕГДА делаем commit
            self.conn.commit()
            logging.info(f"Роль пользователя {user_id} обновлена на {role_id}. Granted by ID: {granted_by_id}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления роли для {user_id}: {e}")
            return False

    def add_scammer(self, scammer_id, reason, reported_by, description, unique_id):
        # Проверка, существует ли пользователь уже в таблице скаммеров
        if self.is_scammer(scammer_id):
            logging.warning(f"Пользователь с ID {scammer_id} уже находится в базе скаммеров.")
            return False  # Возвращаем False, если пользователь уже в базе

        # Проверка, существует ли пользователь в основной базе
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (scammer_id,))
        user = self.cursor.fetchone()

        if user is None:
            logging.error(f"Пользователь с ID {scammer_id} не найден. Не могу добавить скамера.")
            return False

        try:
            # Добавляем скаммера
            self.cursor.execute('''
                INSERT INTO scammers (user_id, reason, reported_by, description, scammer_id, unique_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (scammer_id, reason, reported_by, description, scammer_id, unique_id))
            self.conn.commit()
            logging.info(f"Скаммер {scammer_id} добавлен с причиной: {reason}. Уникальный ID: {unique_id}.")
            return True
        except Exception as e:
            logging.error(f"Ошибка при добавлении скамера: {e}")
            return False

    def update_reason(self, user_id, reason):
        """Обновляет причину заноса для указанного пользователя."""
        self.cursor.execute('''
            INSERT INTO reasons (user_id, reason) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason
        ''', (user_id, reason))
        self.conn.commit()

    def add_additional_reason(self, user_id, additional_reason):
        """Добавляет дополнительное описание для указанного пользователя."""
        # Предполагаем, что у вас есть отдельная таблица для дополнительных описаний
        self.cursor.execute('''
            INSERT INTO additional_reasons (user_id, additional_reason) VALUES (?, ?)
        ''', (user_id, additional_reason))
        self.conn.commit()

    def get_user_scammers_count(self, user_id):
        self.cursor.execute('SELECT scammers_slept FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def update_user_scammers_count(self, user_id, new_count):
        """Обновляет количество слитых скаммеров для указанного пользователя."""
        try:
            self.cursor.execute('UPDATE users SET scammers_slept = ? WHERE user_id = ?', (new_count, user_id))
            self.conn.commit()
            logging.info(f"Количество слитых скаммеров для пользователя {user_id} обновлено на {new_count}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при обновлении количества слитых скаммеров для {user_id}: {e}")

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Пользователь найден: {result}")
        else:
            logging.info(f"Пользователь с ID {user_id} не найден.")
        return result

    def is_scammer(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

    async def update_user_check_count(self, user_id):
        async with self.lock:
            try:
                self.cursor.execute('UPDATE users SET check_count = check_count + 1 WHERE user_id = ?', (user_id,))
                self.conn.commit()
                logging.info(f"Счетчик проверок для пользователя {user_id} обновлен.")
            except sqlite3.Error as e:
                logging.error(f"Ошибка при обновлении счетчика проверок для {user_id}: {e}")

    def get_check_count(self, user_id):
        try:
            self.cursor.execute('SELECT check_count FROM users WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            count = result[0] if result else 0
            logging.info(f"Количество проверок для пользователя {user_id}: {count}")
            return count
        except Exception as e:
            logging.error(f"Ошибка базы данных в get_check_count: {e}")
            return 0

    def get_user_scammers_slept(self, user_id):
        """Получает количество слитых скаммеров для указанного пользователя."""
        logging.info(f"Запрос на получение количества слитых скаммеров для пользователя {user_id}.")
        query = 'SELECT scammers_slept FROM users WHERE user_id = ?'
        self.cursor.execute(query, (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Пользователь {user_id} имеет {result[0]} слитых скаммеров.")
            return result[0]
        else:
            logging.warning(f"Пользователь {user_id} не найден, возвращаем 0.")
            return 0

    def update_user_scammers_slept(self, user_id, new_count):
        logging.info(f"Обновление количества слитых скаммеров для пользователя {user_id} на {new_count}.")
        try:
            self.cursor.execute('''
                UPDATE users SET scammers_slept = ? WHERE user_id = ?
            ''', (new_count, user_id))
            self.conn.commit()
            logging.info(f"Количество слитых скаммеров для пользователя {user_id} успешно обновлено на {new_count}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления количества слитых скаммеров для пользователя {user_id}: {e}")
            return False

    def remove_scammer_status(self, user_id):
        try:
            # Проверка, есть ли пользователь в базе скаммеров
            if not self.is_scammer(user_id):  # Если пользователя уже нет в базе
                return False  # Возвращаем False, чтобы бот сообщил об ошибке

            # Удаление пользователя из таблицы скаммеров
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM scammers WHERE user_id = ?", (user_id,))
            self.conn.commit()

            # Обновление роли пользователя на "Нет в базе" (0)
            query = "UPDATE users SET role_id = 0 WHERE user_id = ?"
            self.execute(query, (user_id,))
            logging.info(f"Статус скамера для пользователя {user_id} успешно снят.")

            return True  # Возвращаем True, если всё прошло успешно
        except sqlite3.Error as e:
            logging.error(f"Ошибка при удалении статуса скамера для пользователя {user_id}: {e}")
            return False  # Возвращаем False, если произошла ошибка

    def set_user_allowance(self, user_id, amount):
        try:
            # Используем текущее соединение, а не создаем новое
            cursor = self.cursor  # Используем курсор из существующего соединения
            cursor.execute("UPDATE users SET allowance = ? WHERE user_id = ?", (amount, user_id))
            self.conn.commit()

            if cursor.rowcount == 0:
                logging.warning(f"Пользователь с ID {user_id} не найден.")
            else:
                logging.info(f"Сумма ручения для пользователя с ID {user_id} успешно обновлена на {amount}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при обновлении суммы ручения: {e}")

    def add_premium_points(self, user_id, points):
        """Добавляет премиум очки пользователю."""
        try:
            self.cursor.execute('UPDATE users SET premium_points = premium_points + ? WHERE user_id = ?', (points, user_id))
            self.conn.commit()
            logging.info(f"Премиум очки пользователя {user_id} обновлены на {points}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при обновлении премиум очков для {user_id}: {e}")

    def get_premium_points(self, user_id):
        """Получает количество премиум очков пользователя."""
        try:
            self.cursor.execute('SELECT premium_points FROM users WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"Ошибка при получении премиум очков для {user_id}: {e}")
            return 0

    def add_check(self, checker_id, target_id):
        """Добавляет запись о проверке."""
        try:
            self.cursor.execute('''
                INSERT INTO checks (checker_id, target_id, check_date)
                VALUES (?, ?, ?)
            ''', (checker_id, target_id, datetime.now().isoformat()))
            self.conn.commit()
            logging.info(f"Запись о проверке добавлена: checker_id={checker_id}, target_id={target_id}")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении записи о проверке: {e}")

    async def __aenter__(self):
        await self.lock.acquire()
        logging.info("База данных открыта для асинхронного доступа.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()
        logging.info("База данных закрыта для асинхронного доступа.")

    def close(self):
        try:
            self.conn.close()
            logging.info("Соединение с базой данных закрыто.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка закрытия БД: {e}")
            return False

main_buttons = [
    [Button.text("🎭 Профиль", resize=True)],
    [Button.text("👥 Состав базы", resize=True), Button.text("🔰 Проверенные пользователи", resize=True)],
    [Button.text("📊 Статистика базы", resize=True), Button.text("🚫 Слить скаммера!", resize=True)],
    [Button.text("🔓 Премиум", resize=True), Button.text("❓ Частые вопросы", resize=True)],
    [Button.text("🔗 Проверить ссылку", resize=True)]
]

# Роли пользователей
ROLES = {
0: {"name": "Нет в базе 📝", "preview_url": "https://imgfy.ru/ib/NS5ly0KvlGnJ7TH_1768319364.jpg", "scam_chance": 31},
    1: {"name": "Гарант 🛡️", "preview_url": "https://imgfy.ru/ib/1GWpjFVMTDoAb8Q_1768319364.jpg", "scam_chance": 1},
    2: {"name": "Возможно скамер ⚠️", "preview_url": "https://imgfy.ru/ib/vgyGQVxXgTlD4su_1768319364.jpg",
        "scam_chance": 65},
    3: {"name": "Скамер ❌", "preview_url": "https://imgfy.ru/ib/YT6lXofT8fHsnA4_1768319364.jpg", "scam_chance": 99},
    4: {"name": "Петух 🐓", "preview_url": "https://imgfy.ru/ib/qF7jT8qDILL06Ni_1768319901.jpg", "scam_chance": 45},
    5: {"name": "Подозрение на скам ⚠️", "preview_url": "https://imgfy.ru/ib/fdnOeaUX2htvdkm_1768319365.jpg",
        "scam_chance": 51},
    6: {"name": "Стажёр 🎓", "preview_url": "https://imgfy.ru/ib/3ub4rh7JxOE3kno_1768319365.jpg", "scam_chance": 20},
    7: {"name": "Админ 👮", "preview_url": "https://imgfy.ru/ib/8vPp8tINWVPyYuE_1768319364.jpg", "scam_chance": 15},
    8: {"name": "Директор 👔", "preview_url": "https://imgfy.ru/ib/59y4upESFCONO2x_1768319364.jpg", "scam_chance": 10},
    9: {"name": "Президент 👑", "preview_url": "https://imgfy.ru/ib/6O81I764EZvEFFe_1768319364.jpg", "scam_chance": 5},
    10: {"name": "Создатель ⭐", "preview_url": "https://imgfy.ru/ib/HXkVyyIJl2xJ5l3_1768319364.jpg", "scam_chance": 1},
    11: {"name": "Кодер 💻", "preview_url": "https://i.ibb.co/pjYvHgP2/IMG-20250830-171539-780.jpg", "scam_chance": 3},
    12: {"name": "Проверен гарантом ✅", "preview_url": "https://imgfy.ru/ib/fDocPi2gjwsztYh_1768319365.jpg",
         "scam_chance": 5},
    13: {"name": "Айдош⭐", "preview_url": "https://i.ibb.co/xtQPhT16/image.jpg", "scam_chance": 20}
}




async def check_user(event):
    user_to_check = event.user  # Получаем пользователя из события
    user_data = db.get_user(user_to_check.id)  # Получаем данные пользователя
    target = user_to_check

    if user_data:  # Если пользователь найден
        role_id = user_data.role_id  # Доступ к атрибуту role_id
        username = user_data.username  # Пример доступа к другим атрибутам
        # Здесь продолжайте с остальной логикой, используя атрибуты user_data

        logging.info(f"Пользователь найден: {username}, Роль: {role_id}")
        # Добавьте вашу логику здесь
    else:
        logging.warning("Пользователь не найден.")



    # Пример реализации метода user_exists
    def user_exists(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()[0] > 0
        cursor.close()
        return exists

    def execute(self, query, params=()):
        """
        Выполняет SQL-запрос с передачей параметров.

        :param query: SQL-запрос для выполнения
        :param params: Параметры для SQL-запроса
        """
        try:
            self.cursor.execute(query, params)  # Выполнение запроса
            self.conn.commit()  # Сохранение изменений
        except sqlite3.Error as e:
            print(f"Ошибка при выполнении запроса: {e}")  # Обработка ошибок
        finally:
            # Закрытие курсора, если необходимо
            pass

    def update_total_messages(self, count):
        try:
            logging.info("Обновление количества сообщений...")
            self.cursor.execute('UPDATE statistics SET total_messages = total_messages + ?', (count,))
            self.conn.commit()
            current_count = self.get_total_messages()
            logging.info(f"Текущее количество сообщений в базе данных: {current_count}")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления количества сообщений: {e}")

    def get_granted_by(self, user_id):
        """Получает ID гаранта для указанного user_id."""
        self.cursor.execute("SELECT granted_by_id FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Гарант найден для user_id {user_id}: {result[0]}")
        else:
            logging.warning(f"Гарант не найден для user_id {user_id}.")
        return result[0] if result else None

    def get_total_messages(self):
        self.cursor.execute('SELECT total_messages FROM statistics')
        result = self.cursor.fetchone()
        return result[0] if result is not None else 0

    def increment_scammers_count(self, user_id):
        """Увеличивает счетчик слитых скаммеров для пользователя с указанным user_id."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET scammers_slept = scammers_slept + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_user(self, user_id, username, role_id=0):
        try:
            self.cursor.execute('''
                INSERT INTO users (user_id, username, role_id)
                VALUES (?, ?, ?)
            ''', (user_id, username, role_id))
            self.conn.commit()
            logging.info(f"Пользователь {username} с ID {user_id} добавлен с ролью {role_id}.")
        except Exception as e:
            logging.error(f"Ошибка при добавлении пользователя: {e}")

    def get_user_role(self, user_id):
        self.cursor.execute('SELECT role_id FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        role = result[0] if result else 0
        logging.info(f"Роль пользователя {user_id}: {role}")
        return role

    def update_user(self, user_id, country=None, channel=None):
        logging.info(f"Обновление пользователя {user_id}: страна - {country}, канал - {channel}")

        # Явная проверка на None для страны
        if country is not None:
            logging.info(f"Обновляем страну на: {country}")
            self.cursor.execute('UPDATE users SET country = ? WHERE user_id = ?', (country, user_id))

        # Явная проверка на None для канала
        if channel is not None:
            logging.info(f"Обновляем канал на: {channel}")
            self.cursor.execute('UPDATE users SET channel = ? WHERE user_id = ?', (channel, user_id))

        # Выполнение коммита для сохранения изменений
        self.conn.commit()

        # Проверка обновленных данных
        self.cursor.execute('SELECT country, channel FROM users WHERE user_id = ?', (user_id,))
        user_data = self.cursor.fetchone()

        # Логирование обновленных данных
        if user_data:
            logging.info(
                f"Данные пользователя после обновления: id={user_id}, страна={user_data[0]}, канал={user_data[1]}")
        else:
            logging.warning(f"Пользователь с id={user_id} не найден после обновления.")

    def get_user_allowance(self, user_id):
        """Получает сумму ручения для указанного пользователя."""
        try:
            self.cursor.execute("SELECT allowance FROM users WHERE user_id = ?", (user_id,))
            result = self.cursor.fetchone()
            if result:
                allowance = result[0]
                logging.info(f"Сумма ручения для пользователя {user_id}: {allowance}")
                return allowance
            else:
                logging.warning(f"Пользователь с ID {user_id} не найден.")
                return None
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении суммы ручения для пользователя {user_id}: {e}")
            return None

    def get_user_custom_photo(self, user_id):
        logging.info(f"Attempting to retrieve custom photo for user_id: {user_id}")

        try:
            # Изменяем запрос на правильный столбец
            cursor = self.cursor.execute('SELECT custom_photo_url FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            logging.info(f"SQL query executed for user_id {user_id}. Result: {result}")

            if result:
                custom_photo = result[0]
                logging.info(f"Retrieved custom photo for user {user_id}: {custom_photo}")
            else:
                logging.warning(f"No custom photo found for user_id: {user_id}. Result was None.")
                custom_photo = None

        except Exception as e:
            logging.error(f"Error retrieving custom photo for user_id {user_id}: {str(e)}")
            custom_photo = None

        if custom_photo is None:
            logging.info(f"Custom photo for user_id {user_id} is None or not found.")
        else:
            logging.info(f"Custom photo URL for user_id {user_id}: {custom_photo}")

        return custom_photo

    def get_user_curator(self, user_id):
        query = "SELECT curator_id FROM users WHERE user_id = ?"
        cursor = self.conn.cursor()  # Изменено на self.conn
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_user_name(self, user_id):
        query = "SELECT username FROM users WHERE user_id = ?"
        cursor = self.conn.cursor()
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        return result[0] if result else "Не указано"

    def get_last_spin(self, user_id):
        """Получает время последнего использования команды рулетки для указанного пользователя."""
        self.cursor.execute('SELECT last_spin FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def update_last_spin(self, user_id):
        """Обновляет время последнего использования команды рулетки для указанного пользователя."""
        self.cursor.execute('UPDATE users SET last_spin = ? WHERE user_id = ?', (datetime.now(), user_id))
        self.conn.commit()

    def add_grant(self, user_id, granted_by_id):
        """Добавляет запись о гарантии для пользователя."""
        try:
            self.cursor.execute('''
                INSERT INTO trust (user_id, granted_by, grant_date)
                VALUES (?, ?, ?)
            ''', (user_id, granted_by_id, datetime.now().isoformat()))
            self.conn.commit()
            logging.info(f"Запись о гарантии для user_id {user_id} добавлена. Granted by ID: {granted_by_id}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении записи о гарантии для user_id {user_id}: {e}")

    def set_profile_checks_count(self, user_id, checks_count):
        # Устанавливаем количество проверок для пользователя
        logging.info(f"Устанавливаем количество проверок для пользователя {user_id}: {checks_count}")

        # Проверяем, существует ли пользователь
        if self.get_user(user_id) is None:
            logging.warning(f"Пользователь {user_id} не найден. Не удается установить количество проверок.")
            return

        self.cursor.execute("UPDATE users SET checks_count = ? WHERE user_id = ?", (checks_count, user_id))
        self.connection.commit()
        logging.info(f"Количество проверок для пользователя {user_id} успешно установлено на {checks_count}")

    def get_profile_checks_count(self, user_id):
        # Получаем количество проверок для пользователя
        logging.info(f"Запрос количества проверок для пользователя {user_id}")
        self.cursor.execute("SELECT checks_count FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()

        if result is not None:
            logging.info(f"Количество проверок для пользователя {user_id}: {result[0]}")
        else:
            logging.warning(f"Пользователь {user_id} не найден в базе данных.")

        return result[0] if result else None

    def update_profile_checks_count(self, user_id, checks_count):
        # Обновляем количество проверок профиля
        if checks_count < 0:
            logging.warning(
                f"Попытка установить отрицательное количество проверок для пользователя {user_id}. Устанавливаем 0.")
            checks_count = 0

        logging.info(f"Обновляем количество проверок для пользователя {user_id} на {checks_count}")
        self.cursor.execute("UPDATE users SET checks_count = ? WHERE user_id = ?", (checks_count, user_id))
        self.connection.commit()
        logging.info(f"Количество проверок для пользователя {user_id} успешно обновлено на {checks_count}")

    def add_premium(self, user_id, expiry_date):
        """Добавляет пользователя в премиум с указанной датой окончания."""
        try:
            self.cursor.execute('''
                INSERT INTO premium_users (user_id, expiry_date)
                VALUES (?, ?)
            ''', (user_id, expiry_date))
            self.conn.commit()
            logging.info(f"Пользователь {user_id} добавлен в премиум до {expiry_date}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении пользователя {user_id} в премиум: {e}")

    def is_premium_user(self, user_id):
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            expiry_date = result[0]
            logging.info(f"Пользователь {user_id} имеет премиум статус до {expiry_date}.")
            return expiry_date
        else:
            logging.warning(f"Пользователь {user_id} не найден в таблице premium_users.")
            return None

    def remove_premium(self, user_id):
        # Удаляем премиум статус пользователя из таблицы users
        db.cursor.execute('UPDATE users SET premium = NULL, premium_expiry = NULL WHERE user_id = ?', (user_id,))
        # Удаляем запись из таблицы premium_users
        db.cursor.execute('DELETE FROM premium_users WHERE user_id = ?', (user_id,))
        db.conn.commit()

    def get_premium_expiry(self, user_id):
        """Возвращает дату истечения премиум статуса для пользователя."""
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        logging.info(f"Результат запроса для пользователя {user_id}: {result}")
        return result[0] if result else None

    def increment_check_count(self, user_id):
        """Увеличивает счетчик проверок для пользователя с указанным user_id, добавляя пользователя в базу, если он не найден."""
        try:
            # Проверяем, существует ли пользователь
            self.cursor.execute('SELECT COUNT(*) FROM users WHERE user_id = ?', (user_id,))
            user_exists = self.cursor.fetchone()[0] > 0

            if not user_exists:
                # Если пользователь не найден, добавляем его в базу данных
                self.cursor.execute('INSERT INTO users (user_id, check_count) VALUES (?, ?)', (user_id, 0))
                logging.info(f"Пользователь с ID {user_id} добавлен в базу данных.")

            # Увеличиваем счетчик
            self.cursor.execute('UPDATE users SET check_count = check_count + 1 WHERE user_id = ?', (user_id,))
            self.conn.commit()
            logging.info(f"Счетчик проверок для пользователя {user_id} увеличен.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления счетчика проверок для {user_id}: {e}")

    def update_warnings(self, user_id):
        try:
            self.cursor.execute('UPDATE users SET warnings = warnings + 1 WHERE user_id = ?', (user_id,))
            self.conn.commit()
            logging.info(f"Количество выговоров для пользователя {user_id} увеличено.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления выговоров для {user_id}: {e}")

    def get_warnings_count(self, user_id):
        result = self.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (user_id,)).fetchone()
        return result[0] if result is not None else 0

    def reset_warnings(self, user_id):
        """Сбрасывает количество выговоров до 0 для указанного пользователя."""
        self.cursor.execute('UPDATE users SET warnings = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
        logging.info(f"Количество выговоров для пользователя {user_id} сброшено до 0.")

    def delete_old_description(self, user_id):
        """Удаляет старое описание."""
        self.cursor.execute("DELETE FROM reasons WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_or_update_premium_user(self, user_id, expiry_date):
        try:
            existing_user = self.cursor.execute('SELECT * FROM premium_users WHERE user_id = ?', (user_id,)).fetchone()
            if existing_user:
                self.cursor.execute('UPDATE premium_users SET expiry_date = ? WHERE user_id = ?',
                                    (expiry_date, user_id))
                logging.info(f"Обновлена дата истечения для пользователя {user_id}: {expiry_date}")
            else:
                self.cursor.execute('INSERT INTO premium_users (user_id, expiry_date) VALUES (?, ?)',
                                    (user_id, expiry_date))
                logging.info(f"Добавлен пользователь {user_id} с премиум статусом до {expiry_date}")
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Ошибка при добавлении/обновлении пользователя {user_id} в премиум: {e}")

    def update_description(self, user_id, new_description):
        try:
            # Обновление описания пользователя в базе данных
            self.cursor.execute("UPDATE users SET description = ? WHERE user_id = ?", (new_description, user_id))
            self.conn.commit()  # Зафиксировать изменения

            # Логирование успешного обновления
            logging.info(f"Описание для пользователя {user_id} обновлено на: {new_description}")

            # Вставка нового описания в статус
            self.update_status(user_id, new_description)
        except Exception as e:
            logging.error(f"Ошибка при обновлении описания: {str(e)}")

    def is_user_in_db(self, user_id):
        """Проверяет, есть ли пользователь в базе данных."""
        self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    # В методе get_user_info:
    def get_user_info(self, user_id):
        self.cursor.execute('''
            SELECT user_id, username, role 
            FROM users 
            WHERE user_id = ?
        ''', (user_id,))
        return self.cursor.fetchone()  # Возвращает sqlite3.Row

    def update_status(self, user_id, new_description):
        try:
            # Обновление статуса с новым описанием
            status_message = f"Новое описание: {new_description}"
            self.cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (status_message, user_id))
            self.conn.commit()  # Зафиксировать изменения

            logging.info(f"Статус для пользователя {user_id} обновлен на: {status_message}")
        except Exception as e:
            logging.error(f"Ошибка при обновлении статуса: {str(e)}")

    def update_user_description(self, user_id, description):
        """Обновляет описание пользователя."""
        try:
            logging.info(f"Попытка обновления описания пользователя {user_id} на: {description}.")

            # Проверяем, существует ли пользователь перед обновлением
            existing_user = self.get_user(user_id)
            if not existing_user:
                logging.warning(f"Пользователь с ID {user_id} не найден. Описание не может быть обновлено.")
                return False

            # Обновляем описание
            self.cursor.execute('UPDATE users SET description = ? WHERE user_id = ?', (description, user_id))
            self.conn.commit()

            # Проверяем, обновилось ли описание
            updated_description = self.get_user_description(user_id)
            if updated_description == description:
                logging.info(f"Описание пользователя {user_id} успешно обновлено на: {description}.")
            else:
                logging.error(
                    f"Описание пользователя {user_id} не обновилось. Текущее значение: {updated_description}.")

            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления описания для {user_id}: {e}")
            return False

    def get_user_description(self, user_id):
        try:
            self.cursor.execute('SELECT description FROM scammers WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            if result and result[0]:
                logging.info(f"Описание для пользователя {user_id}: {result[0]}.")
                return result[0]
            else:
                logging.warning(f"Описание для пользователя {user_id} не найдено.")
                return "Описание отсутствует"
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении описания для пользователя {user_id}: {e}")
            return "Ошибка базы данных"

    def update_role(self, user_id, role_id, granted_by_id=None):
        try:
            self.cursor.execute('UPDATE users SET role_id = ? WHERE user_id = ?', (role_id, user_id))

            if granted_by_id is not None:
                self.cursor.execute('UPDATE users SET granted_by_id = ? WHERE user_id = ?', (granted_by_id, user_id))

            # ВСЕГДА делаем commit
            self.conn.commit()
            logging.info(f"Роль пользователя {user_id} обновлена на {role_id}. Granted by ID: {granted_by_id}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления роли для {user_id}: {e}")
            return False

    def add_scammer(self, scammer_id, reason, reported_by, description, unique_id):
        # Проверка, существует ли пользователь
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (scammer_id,))
        user = self.cursor.fetchone()

        if user is None:
            logging.error(f"Пользователь с ID {scammer_id} не найден. Не могу добавить скамера.")
            return

        try:
            # Попытка добавить скаммера или обновить, если он уже существует
            self.cursor.execute('''
                INSERT INTO scammers (user_id, reason, reported_by, description, scammer_id, unique_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    reason = excluded.reason,
                    reported_by = excluded.reported_by,
                    description = excluded.description,
                    unique_id = excluded.unique_id
            ''', (scammer_id, reason, reported_by, description, scammer_id, unique_id))
            self.conn.commit()
            logging.info(f"Скаммер {scammer_id} добавлен/обновлен с причиной: {reason}. Уникальный ID: {unique_id}.")
        except Exception as e:
            logging.error(f"Ошибка при добавлении/обновлении скамера: {e}")

    def update_reason(self, user_id, reason):
        """Обновляет причину заноса для указанного пользователя."""
        self.cursor.execute('''
            INSERT INTO reasons (user_id, reason) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason
        ''', (user_id, reason))
        self.conn.commit()

    def add_additional_reason(self, user_id, additional_reason):
        """Добавляет дополнительное описание для указанного пользователя."""
        # Предполагаем, что у вас есть отдельная таблица для дополнительных описаний
        self.cursor.execute('''
            INSERT INTO additional_reasons (user_id, additional_reason) VALUES (?, ?)
        ''', (user_id, additional_reason))
        self.conn.commit()

    async def scam_command(event):
        user_id = event.sender_id  # ID пользователя, который сообщает о скаммере
        scammer_username = event.message.text.split('@')[1]  # Извлечение имени скамера из команды
        reason = "Причина скамера"  # Причина сообщения о скаммере
        description = reason  # Устанавливаем описание как причину

        # Логирование перед вызовом метода
        logging.info(f"Вызов add_scammer с аргументами: {user_id}, {scammer_username}, {reason}, {description}")

        # Проверяем, существует ли скаммер в базе данных
        existing_scammer = db.get_user_by_username(scammer_username)  # Метод для получения пользователя по имени
        if existing_scammer:
            scammer_id = existing_scammer[0]  # Получаем ID скамера
        else:
            # Если скаммер не существует, добавляем его
            db.add_user(scammer_username, scammer_username)  # Добавляем скамера с именем
            scammer_id = db.get_user_by_username(scammer_username)[0]  # Получаем ID после добавления
            logging.info(f"Пользователь {scammer_username} добавлен в базу данных с ID {scammer_id}.")

        # Убедитесь, что scammer_id существует перед добавлением скамера
        if scammer_id:
            try:
                # Вызов метода добавления скамера
                db.add_scammer(user_id, reason, description, scammer_id)
            except Exception as e:
                logging.error(f"Ошибка при добавлении скамера: {e}")
        else:
            logging.error(f"Не удалось получить ID скамера для пользователя {scammer_username}.")

    def get_user_scammers_count(self, user_id):
        self.cursor.execute('SELECT scammers_slept FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def update_user_scammers_count(self, user_id, new_count):
        """Обновляет количество слитых скаммеров для указанного пользователя."""
        try:
            self.cursor.execute('UPDATE users SET scammers_slept = ? WHERE user_id = ?', (new_count, user_id))
            self.conn.commit()
            logging.info(f"Количество слитых скаммеров для пользователя {user_id} обновлено на {new_count}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при обновлении количества слитых скаммеров для {user_id}: {e}")

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Пользователь найден: {result}")
        else:
            logging.info(f"Пользователь с ID {user_id} не найден.")
        return result

    def is_scammer(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

    async def update_user_check_count(self, user_id):
        async with self.lock:
            try:
                self.cursor.execute('UPDATE users SET check_count = check_count + 1 WHERE user_id = ?', (user_id,))
                self.conn.commit()
                logging.info(f"Счетчик проверок для пользователя {user_id} обновлен.")
            except sqlite3.Error as e:
                logging.error(f"Ошибка при обновлении счетчика проверок для {user_id}: {e}")

    def get_check_count(self, user_id):
        try:
            self.cursor.execute('SELECT check_count FROM users WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            count = result[0] if result else 0
            logging.info(f"Количество проверок для пользователя {user_id}: {count}")
            return count
        except Exception as e:
            logging.error(f"Ошибка базы данных в get_check_count: {e}")
            return 0

    def get_user_scammers_slept(self, user_id):
        """Получает количество слитых скаммеров для указанного пользователя."""
        logging.info(f"Запрос на получение количества слитых скаммеров для пользователя {user_id}.")
        query = 'SELECT scammers_slept FROM users WHERE user_id = ?'
        self.cursor.execute(query, (user_id,))
        result = self.cursor.fetchone()
        if result:
            logging.info(f"Пользователь {user_id} имеет {result[0]} слитых скаммеров.")
            return result[0]
        else:
            logging.warning(f"Пользователь {user_id} не найден, возвращаем 0.")
            return 0

    def update_user_scammers_slept(self, user_id, new_count):
        logging.info(f"Обновление количества слитых скаммеров для пользователя {user_id} на {new_count}.")
        try:
            self.cursor.execute('''
                UPDATE users SET scammers_slept = ? WHERE user_id = ?
            ''', (new_count, user_id))
            self.conn.commit()
            logging.info(f"Количество слитых скаммеров для пользователя {user_id} успешно обновлено на {new_count}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка обновления количества слитых скаммеров для пользователя {user_id}: {e}")
            return False

    def remove_scammer_status(self, user_id):
        try:
            # Проверка, есть ли пользователь в базе скаммеров
            if not self.is_scammer(user_id):  # Если пользователя уже нет в базе
                return False  # Возвращаем False, чтобы бот сообщил об ошибке

            # Удаление пользователя из таблицы скаммеров
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM scammers WHERE user_id = ?", (user_id,))
            self.conn.commit()

            # Обновление роли пользователя на "Нет в базе" (0)
            query = "UPDATE users SET role_id = 0 WHERE user_id = ?"
            self.execute(query, (user_id,))
            logging.info(f"Статус скамера для пользователя {user_id} успешно снят.")

            return True  # Возвращаем True, если всё прошло успешно
        except sqlite3.Error as e:
            logging.error(f"Ошибка при удалении статуса скамера для пользователя {user_id}: {e}")
            return False  # Возвращаем False, если произошла ошибка

    def set_user_allowance(self, user_id, amount):
        try:
            # Используем текущее соединение, а не создаем новое
            cursor = self.cursor  # Используем курсор из существующего соединения
            cursor.execute("UPDATE users SET allowance = ? WHERE user_id = ?", (amount, user_id))
            self.conn.commit()

            if cursor.rowcount == 0:
                logging.warning(f"Пользователь с ID {user_id} не найден.")
            else:
                logging.info(f"Сумма ручения для пользователя с ID {user_id} успешно обновлена на {amount}.")
        except sqlite3.Error as e:
            logging.error(f"Ошибка при обновлении суммы ручения: {e}")

    async def __aenter__(self):
        await self.lock.acquire()
        logging.info("База данных открыта для асинхронного доступа.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()
        logging.info("База данных закрыта для асинхронного доступа.")

    def close(self):
        try:
            self.conn.close()
            logging.info("Соединение с базой данных закрыто.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка закрытия БД: {e}")
            return False



# Инициализация бота
bot = TelegramClient('sosot.session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
db = Database()

def get_guarantors():
    """Получает список гарантов из базы данных"""
    try:
        db.cursor.execute('SELECT user_id FROM users WHERE role_id = 1')  # role_id = 1 - гарант
        guarantors = db.cursor.fetchall()
        return [guarantor[0] for guarantor in guarantors]
    except Exception as e:
        logging.error(f"Ошибка при получении гарантов: {e}")
        return []

def get_trainees():
    """Получает список стажеров из базы данных"""
    try:
        db.cursor.execute("SELECT * FROM trainees")
        trainees = db.cursor.fetchall()
        return trainees
    except Exception as e:
        logging.error(f"Ошибка при получении стажеров: {e}")
        return []


@bot.on(events.NewMessage(pattern="👥 Состав базы"))
async def members_menu(event):
    if not event.is_private:
        return

    buttons = [
        [Button.text("✅ Гаранты базы", resize=True)],
        [Button.text("👨‍🎓 Волонтёры базы", resize=True)],
        [Button.text("↩ Назад", resize=True)]
    ]

    await event.respond(
        "👥 **Меню состава базы**\n\n"
        "Выберите категорию участников для просмотра:",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.NewMessage(pattern="↩ Назад"))
async def back_to_main(event):
    if not event.is_private:
        return

    await event.respond(
        "Главное меню:",
        buttons=main_buttons
    )

@bot.on(events.NewMessage(pattern="📊 Статистика базы"))
async def statistics(event):
    if not event.is_private:
        return

    # Получаем статистические данные
    user = await event.get_sender()
    # Используем существующий глобальный экземпляр db вместо создания нового

    # Основные статистические данные
    total_checks = db.cursor.execute('SELECT SUM(check_count) FROM users').fetchone()[0] or 0
    scammers_count = db.cursor.execute('SELECT COUNT(*) FROM scammers').fetchone()[0]
    total_users = db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    # Статистика по ролям
    roles_stats = {
        'admins': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 7').fetchone()[0],
        'guarantors': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 1').fetchone()[0],
        'verified': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 12').fetchone()[0],
        'trainees': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 6').fetchone()[0]
    }

    text = f"""🔍 {user.first_name}, вот текущая статистика бота:
    [⠀](https://i.ibb.co/dwfVKmMH/photo-2025-04-17-17-44-19-2.jpg)

    🚫 Скаммеров в базе: {scammers_count}
    👥 Пользователей бота: {total_users}

    ⚖️ Админов: {roles_stats['admins']}
    💎 Гарантов: {roles_stats['guarantors']}
    ✅ Проверенных: {roles_stats['verified']}
    👨‍🎓 Стажеров: {roles_stats['trainees']}

    🔎 Всего проверок: {total_checks}
    ⏳ Последняя проверка: {datetime.now().strftime('%d.%m.%Y %H:%M')}
    """

    # Создаем кнопки
    buttons = [
        [Button.inline("🏆 Топ Стажеров", b"top_trainees")],
        [Button.inline("😎 Топ Активных", b"top_day")],
        [Button.url("🎇 Наша База", 'https://t.me/infinityANTIscam')]
    ]

    stat_message = await event.respond(text, parse_mode='md', link_preview=True, buttons=buttons)

    # Сохраняем ID сообщения для последующего удаления
    bot.stat_message_id = stat_message.id


@bot.on(events.NewMessage(pattern='/check_my_photo'))
async def check_my_photo(event):
    user_id = event.sender_id

    # Проверяем структуру таблицы
    db.cursor.execute("PRAGMA table_info(users)")
    columns = db.cursor.fetchall()
    print("Структура таблицы users:")
    for i, col in enumerate(columns):
        print(f"{i}: {col}")

    # Проверяем конкретно нашу запись
    db.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = db.cursor.fetchone()
    print(f"Все данные пользователя: {user_data}")

    if user_data:
        print(f"custom_photo_url: {user_data[8] if len(user_data) > 8 else 'NO COLUMN'}")

    await event.respond("Проверка завершена, смотрите консоль")

@bot.on(events.CallbackQuery(pattern=r'sliv_scammers'))
async def sliv_scammers_handler(event):
    target_user_id = int(event.pattern_match.group(1))
    sender_id = event.sender_id

    # Сохраняем информацию о том, на кого подается апелляция

    try:
        await bot.send_message(
            sender_id,
            f"чтобы слить скаммера,вам надо зайди в чат-слива скаммеров👇.\n\n"
            "просто скиньте в чат следующие данные:"
            "все доказательства(фото,видео,сообщения).\n\n"
            "айди,можно и юзернейм но желательно лучше айди"
            "если вы сделали все это,и наши волонтеры занесли скаммера,то они выдадут вам +спасибо"
        )
        # Создаем кнопку
        keyboard = [
            [Button.url("предложка🔍", "https://t.me/infinityantiscam")]
        ]

        await event.answer("📨 Инструкции отправлены вам в личные сообщения", alert=True)
    except Exception as e:
        await event.answer("❌ Не удалось отправить сообщение.Пожалуйста,запустите бота", alert=True)
        logging.error(f"Ошибка отправки сообщения в ЛС: {e}")


@bot.on(events.CallbackQuery(pattern=r'appeal_(\d+)'))
async def appeal_handler(event):
    target_user_id = int(event.pattern_match.group(1))
    sender_id = event.sender_id

    # Сохраняем информацию о том, на кого подается апелляция
    user_states[sender_id] = {'appeal_target': target_user_id, 'waiting_for_appeal': True}

    try:
        await bot.send_message(
            sender_id,
            f"📝 Вы начали процесс апелляции на пользователя с ID {target_user_id}.\n\n"
            "Пожалуйста, напишите текст вашей апелляции. Опишите подробно причины, "
            "по которым считаете, что пользователь не должен быть в базе скамеров.\n\n"
            "❌ Отправьте 'отмена' для отмены процесса."
        )
        await event.answer("📨 Инструкции по апелляции отправлены вам в личные сообщения", alert=True)
    except Exception as e:
        await event.answer("❌ Не удалось отправить сообщение. Убедитесь, что у бота есть доступ к вашим ЛС", alert=True)
        logging.error(f"Ошибка отправки сообщения в ЛС: {e}")

@bot.on(events.NewMessage)
async def handle_appeal_text(event):
    user_id = event.sender_id

    # Проверяем, что это личное сообщение и пользователь ожидает ввода апелляции
    if event.is_private and user_id in user_states and user_states[user_id].get('waiting_for_appeal'):
        appeal_text = event.raw_text.strip()

        # Проверка на отмену
        if appeal_text.lower() in ['отмена', 'cancel', 'отменить']:
            if user_id in user_states:
                del user_states[user_id]
            await event.respond("❌ Процесс апелляции отменен.")
            return

        # Проверяем, что текст не пустой
        if not appeal_text:
            await event.respond("❌ Текст апелляции не может быть пустым. Пожалуйста, напишите вашу апелляцию.")
            return

        target_user_id = user_states[user_id]['appeal_target']

        try:
            # Получаем информацию о пользователях
            target_user = await bot.get_entity(target_user_id)
            sender_user = await event.get_sender()

            # Формируем сообщение для чата апелляций
            appeal_message = (
                f"🚨 **Новая апелляция**\n\n"
                f"👤 **На пользователя:** {target_user.first_name} (ID: {target_user_id})\n"
                f"📝 **От пользователя:** {sender_user.first_name} (ID: {user_id})\n"
                f"📄 **Текст апелляции:**\n{appeal_text}\n\n"
                f"⏰ **Время подачи:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

            # ID группы апелляций (ЗАМЕНИТЕ НА РЕАЛЬНЫЙ ID!)
            APPEAL_CHAT_ID = -1003516817505   # Замените на реальный ID группы

            # Пытаемся отправить в группу апелляций
            try:
                await bot.send_message(
                    APPEAL_CHAT_ID,
                    appeal_message,
                    parse_mode='md'
                )
                logging.info(f"Апелляция успешно отправлена в группу {APPEAL_CHAT_ID}")

                # Подтверждаем пользователю
                await event.respond(
                    "✅ Ваша апелляция успешно отправлена на рассмотрение!\n\n"
                    "Мы рассмотрим ваше обращение в ближайшее время. "
                    "О результате уведомим вас личным сообщением."
                )

            except Exception as e:
                logging.error(f"Ошибка отправки в группу апелляций: {e}")
                await event.respond(
                    f"❌ Ошибка при отправке апелляции в группу. "
                    f"Пожалуйста, сообщите администраторам об ошибке: {str(e)}"
                )

        except Exception as e:
            logging.error(f"Ошибка при обработке апелляции: {e}")
            await event.respond(
                "❌ Произошла ошибка при обработке апелляции. "
                "Пожалуйста, попробуйте позже или свяжитесь с администраторами."
            )

        # Очищаем состояние в любом случае
        if user_id in user_states:
            del user_states[user_id]

async def get_user_profile_response(event, user, user_data):
    user_id = user.id
    role_id = db.get_user_role(user_id)

    print(f"User ID: {user_id}, Role: {role_id}")

    custom_image_url = db.get_user_custom_photo_url(user_id)
    print(f"Custom image URL: {custom_image_url}")

    logging.info(f"Проверка профиля для user_id: {user_id}, role_id: {role_id}")

    country = user_data[5].strip() if user_data and len(user_data) > 5 and user_data[5] else "❓"
    channel = user_data[6].strip() if user_data and len(user_data) > 6 and user_data[6] else "❓"
    description = db.get_user_description(user_id) or "Нет описания"
    checks_count = db.get_check_count(user_id)
    logging.info(f"Количество проверок для user_id {user_id} после увеличения: {checks_count}")

    scammers_slept = db.get_user_scammers_slept(user_id)
    custom_image_url = db.get_user_custom_photo_url(user_id)
    logging.info(f"Custom image URL retrieved for user {user_id}: {custom_image_url}")

    current_time = datetime.now().strftime("%d.%m.%Y")

    buttons = [
        [
            Button.url("🎧 Профиль", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"),
            Button.inline("⚖️ Аппеляция", f"appeal_{user_id}")
        ],
        [
            Button.inline("🚫 Слить скаммера", f"report_instruction_{user_id}")
        ]
    ]

    # Добавляем кнопку "вынести из базы" для скамеров и подозреваемых
    if role_id in [2, 3, 4, 5]:  # Возможно скамер, Скамер, Петух, Подозрение на скам
        buttons.append([Button.inline("🚫 Вынести из базы", f"remove_from_db_{user_id}")])


    warnings_count = db.get_warnings_count(user_id)

    emojis = ["🧛‍♂️", "👩‍💻", "🎮", "🔥", "⛄", "☃", "🌟", "🐻", "🐳", "🐵", "🦢", "💸", "🌸", "💥", "🌈", "🐹", "🦉"]

    message_text = ""

    random_emoji = random.choice(emojis) if country == "Не указана" else ""

    country_display = f"[Не указана](https://telegra.ph/Kak-ustanovit-stranu-v-bote-05-29)" if country == "Не указана" else country

    granted_by_id = db.get_granted_by(user.id)  # Заменили target на user
    logging.info(f"Получен ID гаранта: {granted_by_id}")

    granted_by_username = "Неизвестный гарант"
    if granted_by_id is not None:
        try:
            logging.info(f"Попытка получить информацию о гаранте с ID {granted_by_id}")
            granted_by_user = await bot.get_entity(granted_by_id)
            granted_by_username = granted_by_user.username if granted_by_user.username else granted_by_user.first_name
            logging.info(f"Имя гаранта: {granted_by_username}")
        except Exception as e:
            logging.error(f"Ошибка при получении информации о гаранте с ID {granted_by_id}: {e}")
    else:
        logging.warning("granted_by_id равен None, гарант не найден.")

    if role_id == 0:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[❌] Статус: не найден в базе. Риск скама: **44%**\n"
            f"[ℹ️] [Узнайте о гарантах](https://telegra.ph/Kto-takoj-GARANT-05-29)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[🔒] Используйте Гарантов infinity для безопасных сделок.\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 12:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[❌] Статус: Проверен(а) гарантом | [ {granted_by_username} ](tg://user?id={granted_by_id}) ✅\n"
            f"[ℹ️] [Узнайте о гарантах](https://telegra.ph/Kto-takoj-GARANT-05-29)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[🔒] Используйте Гарантов infinity для безопасных сделок.\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 1:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[✅] Статус: Гарант\n"
            f"[ℹ️] [Узнайте о гарантах](https://telegra.ph/Kto-takoj-GARANT-05-29)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[🔒] Данный пользователь является проверенным гарантом infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 10:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[💢] Статус: Владелец\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[🔒] Данный пользователь является Cоздателем базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 9:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🧿] Статус: Президент\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[⚠] Выговоры: {warnings_count} "
            f"[🔒] Данный пользователь является надёжным президентом базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 4:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🐓] Статус: Петух\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"📚 Описание: {description}\n\n"
            f"[❌] Данный пользователь является подозрительной личностью! \n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 3:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🛑] Статус: Скаммер\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"📚 Описание: {description}\n\n"
            f"[❌] Данный пользователь Является скаммером! Не идите первыми!\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 7:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🔍] Статус: Админ\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[⚠] Выговоры: {warnings_count} "
            f"[🔒] Данный пользователь является Администратором Базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 5:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🛑] Статус: Подозрения На Скам\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"📚 Описание: {description}\n\n"
            f"[❌] Данный пользователь Является подозрительной личностью, будьте осторожны!\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 2:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[🛑] Статус: Возможно скаммер\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"📚 Описание: {description}\n\n"
            f"[❌] Данный пользователь Является Потонциальным скаммером, будьте осторожны!\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 6:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[👨‍🎓] Статус: Стажер\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[⚠] Выговоры: {warnings_count}\n"
            f"[📣] Канал: {channel}\n\n"
            f"[🔒] Данный пользователь является Стажёром Базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 8:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[‍🎩] Статус: Директор\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[⚠] Выговоры: {warnings_count}\n"
            f"[📣] Канал: {channel}\n\n"
            f"[🔒] Данный пользователь является Директором Базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )

    elif role_id == 11:
        preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
        message_text = (
            f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({ROLES[role_id]['preview_url']})\n\n"
            f"[👨‍💻] Статус: Кодер\n"
            f"[💖] [Персонал infinity](https://t.me/infinityantiscam)\n\n"
            f"[📍] Регион: {country_display}\n"
            f"[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
            f"[⚠] Выговоры: {warnings_count}\n"
            f"[📣] Канал: {channel}\n\n"
            f"[🔒] Данный пользователь является Техническим Специалистом Базы infinity\n\n"
            f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
        )
    else:
        logging.warning(f"Неизвестная роль: {role_id}")
        return "❌ Неизвестная роль"

    return message_text, buttons


async def send_user_profile(event, user, user_data):
    message_text, profile_button = await get_user_profile_response(user, user_data)
    await event.respond(message_text, buttons=[profile_button])


@bot.on(events.NewMessage(pattern='/profile'))
async def handler(event):
    user = event.sender  # Получаем пользователя, который отправил сообщение
    user_data = db.get_user_data(user.id)  # Получаем данные пользователя из базы
    await send_user_profile(event, user, user_data)


async def send_response(event, response_text, buttons=None):
    if buttons:
        await event.respond(response_text, buttons=buttons, parse_mode='md')
    else:
        await event.respond(response_text, parse_mode='md')


@bot.on(events.CallbackQuery(data=re.compile(r"^profile_(\d+)$")))
async def callback_handler(event):
    user_id = int(event.pattern_match.group(1))

    # Перекидываем пользователя на профиль выбранного человека
    await event.client.send_message(event.chat_id, f"tg://user?id={user_id}", link_preview=False)


last_check_time = {}

# Глобальная переменная для хранения кэша
joined_users_cache = set()


# Функция для сброса кэша
def reset_cache():
    global joined_users_cache
    joined_users_cache.clear()  # Очищаем кэш
    logging.info('Кэш успешно сброшен.')



@bot.on(events.NewMessage(pattern=r'(?i)^(чек|чек ми|чек я|чек себя|check|/check).*'))
async def check_user(event):
    global checks_count  # Убедитесь, что checks_count объявлена глобальной
    user_id = event.sender_id
    user = await event.get_sender()
    loading_msg = await event.respond("🔍")

    # Проверяем время последнего вызова команды
    current_time = time.time()
    if user_id in last_check_time:
        elapsed_time = current_time - last_check_time[user_id]
        if elapsed_time < 5:  # Если прошло меньше 5 секунд
            await loading_msg.delete()
            remaining_time = 5 - elapsed_time
            return await send_response(event, f"пожалуйста,подождите  {remaining_time:.1f} секунд(ы)!")

    # Обновляем время последнего вызова команды
    last_check_time[user_id] = current_time

    # Задержка на 0.5 секунды
    await asyncio.sleep(0.5)

    # Инициализация переменных
    user_to_check = None
    user_data = None  # Инициализация переменной для данных пользователя

    # Определяем пользователя для проверки
    if event.reply_to_msg_id:  # Если команда вызвана ответом на сообщение
        replied = await event.get_reply_message()
        user_to_check = await event.client.get_entity(replied.sender_id)
        user_data = db.get_user(user_to_check.id) if db else None  # Получаем данные из БД
    else:
        if "чек себя" in event.raw_text.lower() or "чек ми" in event.raw_text.lower():
            user_to_check = user
        else:
            try:
                args = event.raw_text.split()[1:]
                if args and args[0].isdigit():  # Проверка по ID
                    user_id_to_check = int(args[0])
                    user_data = db.get_user(user_id_to_check) if db else None  # Получаем данные из БД
                    if user_data:
                        user_to_check = user_data  # Присваиваем данные пользователя
                    else:
                        await loading_msg.delete()
                        return await send_response(event, "❌ | Пользователь не найден в базе данных.")
                elif args:  # Проверка по юзернейму
                    user_to_check = await event.client.get_entity(args[0])
            except Exception as e:
                logging.error(f"Ошибка при получении пользователя: {e}")
                await loading_msg.delete()
                return await send_response(event, "❌ | Не удалось найти пользователя.")

    if user_to_check is None:
        await loading_msg.delete()
        return await send_response(event, "❌ | Не удалось определить пользователя.")

    # Получаем данные, если они еще не загружены
    if not user_data and db:
        user_data = db.get_user(user_to_check.id)

    async with db:
        # Увеличиваем счетчики проверок
        if db:
            db.increment_check_count(user_to_check.id)
        checks_count += 1

        # Формируем ответ
        response = await get_user_profile_response(event, user_to_check, user_data)

        if isinstance(response, tuple):
            message_text, buttons = response
        else:
            message_text = response
            buttons = []

        # Отправка результата
        try:
            await send_response(event, message_text[:4096] if len(message_text) > 4096 else message_text, buttons)
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")

        # Уведомление для премиум-пользователей
        if db and db.is_premium_user(user_id) and event.raw_text.lower() in ('чек', '/check'):
            await bot.send_message(
                user_id,
                f'🔍 Пользователь [{user.first_name}](tg://user?id={user_id}) проверял вас в боте!',
                buttons=Button.inline("↩Скрыть", b"hide_message")
            )

    # Удаляем сообщение о загрузке
    try:
        await loading_msg.delete()
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения о загрузке: {e}")


@bot.on(events.NewMessage(pattern=r'(?i)^/on$'))
async def enable_chat(event):
    """Команда для разрешения участникам чата писать сообщения."""
    user_id = event.sender_id

    # Проверяем, является ли пользователь с ролью 10
    if db.get_user_role(user_id) != 10:
        await event.respond("❌ У вас нет прав для выполнения этой команды.")
        return

    # Разрешаем всем участникам писать сообщения
    await bot.edit_permissions(event.chat_id, send_messages=True)

    await event.respond(
        "🔓 Предложка открыта, вы снова можете писать сообщения в чат![⠀](https://i.ibb.co/JFq2r3Dg/image.jpg)")


@bot.on(events.NewMessage(pattern=r'(?i)^/off$'))
async def disable_chat(event):
    """Команда для запрета участникам чата писать сообщения."""
    user_id = event.sender_id

    # Проверяем, является ли пользователь с ролью 10
    if db.get_user_role(user_id) != 10:
        await event.respond("❌ У вас нет прав для выполнения этой команды.")
        return

    # Запрещаем всем участникам писать сообщения
    await bot.edit_permissions(event.chat_id, send_messages=False)

    await event.respond(
        "🔒 Предложка закрыта на время, скоро мы вернёмся в строй, следите за новостями![⠀](https://i.ibb.co/JFq2r3Dg/image.jpg)")


@bot.on(events.CallbackQuery(pattern=r'remove_from_db_(\d+)'))
async def remove_from_db_handler(event):
    user_id = int(event.pattern_match.group(1))

    # Проверяем права пользователя
    sender_role = db.get_user_role(event.sender_id)
    allowed_roles = [6, 7, 8, 9, 10, 11, 13]  # Стажер, Админ, Директор, Президент, Создатель, Кодер, Заместитель

    if sender_role not in allowed_roles:
        await event.answer("❌ У вас нет прав для выполнения этого действия!", alert=True)
        return

    try:
        # Получаем информацию о пользователе, которого нужно вынести из базы
        target_user = await bot.get_entity(user_id)
        target_role = db.get_user_role(user_id)

        # Проверяем, что пользователь действительно имеет одну из ролей скамера
        if target_role not in [2, 3, 4, 5]:
            await event.answer("❌ Этот пользователь не является скамером!", alert=True)
            return

        # Снимаем статус скамера - устанавливаем роль "Нет в базе" (0)
        db.update_role(user_id, 0)

        # Удаляем из таблицы scammers
        db.cursor.execute('DELETE FROM scammers WHERE user_id = ?', (user_id,))
        db.conn.commit()

        # Получаем информацию о пользователе, который выполнил действие
        admin_user = await bot.get_entity(event.sender_id)

        await event.answer("✅ Пользователь успешно вынесен из базы!", alert=True)

        # Редактируем сообщение, убирая кнопку
        await event.edit(
            f"👤 Пользователь [{target_user.first_name}](tg://user?id={user_id}) был вынесен из базы\n"
            f"👮 Вынес: [{admin_user.first_name}](tg://user?id={event.sender_id})\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            buttons=[
                [
                    Button.url("🎧 Профиль",
                               f"https://t.me/{target_user.username}" if target_user.username else f"tg://user?id={user_id}"),
                    Button.inline("⚖️ Аппеляция", f"appeal_{user_id}")
                ]
            ],
            parse_mode='md'
        )

        logging.info(f"Пользователь {user_id} вынесен из базы пользователем {event.sender_id}")

    except Exception as e:
        logging.error(f"Ошибка при выносе пользователя из базы: {e}")
        await event.answer("❌ Произошла ошибка при выносе из базы!", alert=True)


@bot.on(events.NewMessage(pattern=r'(?i)^/cur|/курировать|/кур'))
async def cur_command(event):
    try:
        sender = await event.get_sender()
        user_id = sender.id

        # Проверяем права пользователя
        user_role = db.get_user_role(user_id)
        allowed_roles = [8, 9, 13, 10]  # 8 - директор, 10 - владелец

        if user_role not in allowed_roles:
            await event.respond("❌ У вас нет прав для выполнения этой команды.")
            return

        # Определяем целевого пользователя
        target = None
        if event.is_reply:
            replied = await event.get_reply_message()
            target_id = replied.sender_id
            try:
                target = await event.client.get_entity(target_id)
            except ValueError:
                # Если не можем получить entity, создаем минимальную информацию
                target = type('obj', (object,), {
                    'id': target_id,
                    'first_name': 'Пользователь'
                })()
        else:
            args = event.raw_text.split()
            if len(args) < 2:
                await event.reply("❌ Используйте: /cur @username или ответьте на сообщение.")
                return

            username = args[1].lstrip('@')
            try:
                target = await event.client.get_entity(username)
            except Exception as e:
                await event.reply("❌ Не могу найти указанного пользователя.")
                return

        if not target:
            await event.reply("❌ Не удалось определить пользователя.")
            return

        # Проверяем роль целевого пользователя
        target_role = db.get_user_role(target.id)
        if target_role != 6:  # 6 - стажёр
            await event.reply("❌ Указанный пользователь не является стажёром.")
            return

        # Назначаем куратора
        db.cursor.execute('UPDATE users SET curator_id = ? WHERE user_id = ?', (user_id, target.id))
        db.conn.commit()

        # Формируем ответ
        target_name = getattr(target, 'first_name', 'Пользователь')
        sender_name = getattr(sender, 'first_name', 'Куратор')

        await event.reply(
            f"✅ Стажёру [{target_name}](tg://user?id={target.id}) назначен курирующий: [{sender_name}](tg://user?id={user_id}).",
            link_preview=False
        )

    except Exception as e:
        print(f"Ошибка в команде /cur: {e}")
        await event.reply("❌ Произошла ошибка при выполнении команды.")


@bot.on(events.NewMessage(pattern=r'(?i)^(выговор|/выговор)'))
async def warning_handler(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
    else:
        await event.reply("❌ Пожалуйста, используйте команду в ответ на сообщение пользователя.")
        return

    # Проверяем права
    user_role = db.get_user_role(event.sender_id)
    logging.info(f"Пользователь {event.sender_id} с ролью {user_role} пытается выдать выговор.")

    # Проверяем, чтобы создающий пользователь (роль 10) не получал выговоры
    target_user_role = db.get_user_role(target_user.id)
    if target_user_role == 10:
        await event.reply("Ты шо ахуел?, нельзя владельцу выговоры выдавать!.")
        return

    # Проверяем, что у пользователя есть права на выдачу выговоров
    if user_role not in [13, 8, 9, 10]:  # Только админ, директор, президент
        await event.reply("❌ У вас нет прав для выдачи выговора.")
        return

    # Получаем количество выговоров
    result = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()

    if result is None:
        # Если пользователь не найден, добавляем его в базу с 0 выговорами
        db.add_user(target_user.id, target_user.username, 0)  # Добавляем пользователя с нулевым количеством выговоров
        warnings_count = 0
    else:
        warnings_count = result[0]

    # Увеличиваем количество выговоров
    db.update_warnings(target_user.id)

    # Получаем обновленное количество выговоров
    new_warnings_count = \
        db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()[0]

    if new_warnings_count >= 3:
        # Снимаем статус пользователя
        db.update_role(target_user.id, 0)

        # Сбрасываем количество выговоров до 0
        db.reset_warnings(target_user.id)

        await event.reply(
            f"✅ Пользователь [{target_user.first_name}](tg://user/{target_user.id}) получил 3 выговора и теперь имеет статус 'Нет в базе'.")
    else:
        await event.reply(
            f"✅ Выговор выдан пользователю [{target_user.first_name}](tg://user/{target_user.id})")


@bot.on(events.NewMessage(pattern=r'(?i)^(/-выговор|снять выговор)'))
async def remove_warnings_handler(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
    else:
        await event.reply("❌ Пожалуйста, используйте команду в ответ на сообщение пользователя.")
        return

    # Проверяем права
    user_role = db.get_user_role(event.sender_id)
    logging.info(f"Пользователь {event.sender_id} с ролью {user_role} пытается снять выговоры.")

    # Проверяем, что у пользователя есть права на снятие выговоров
    if user_role not in [13, 8, 9, 10]:  # Только админ, директор, президент
        await event.reply("❌ У вас нет прав для снятия выговоров.")
        return

    # Получаем текущее количество выговоров
    result = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()
    if result is None:
        await event.reply("❌ Пользователь не найден в базе.")
        return

    warnings_count = result[0]

    if warnings_count <= 0:
        await event.reply(f"❌ У пользователя [{target_user.first_name}](tg://user/{target_user.id}) нет выговоров.")
        return

    # Уменьшаем количество выговоров на 1
    db.cursor.execute('UPDATE users SET warnings = warnings - 1 WHERE user_id = ?', (target_user.id,))
    db.conn.commit()

    # Получаем обновленное количество выговоров
    new_warnings_count = \
        db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()[0]

    await event.reply(
        f"✅ выговор снят у пользователя [{target_user.first_name}](tg://user/{target_user.id})."
    )


# Глобальная переменная для хранения времени последнего использования команды
last_sell_command_time = {}


@bot.on(events.NewMessage(pattern=r'продать (.+)'))
async def sell_command(event):
    user_id = event.sender_id
    item_to_sell = event.pattern_match.group(1)  # Получаем то, что пользователь хочет продать

    # Проверка колдауна
    current_time = time.time()
    if user_id in last_sell_command_time:
        if current_time - last_sell_command_time[user_id] < 10:  # 10 секунд колдаун
            await event.respond("Потерпи брадок, 10 секунд не так уж и много.")
            return

    # Устанавливаем время последнего использования команды
    last_sell_command_time[user_id] = current_time

    # Шанс на успех (15%)
    if random.randint(1, 100) <= 15:
        # Успех
        success_texts = [
            f"ЁЁЁЁЁЁУУУУУУУУУ😎😎😎 Да ты своего {item_to_sell} продал цыганам за 5 копеек, хочешь вернуть да?, того пиздуй искать в бд неуч!",
            f"Нихуя себе какой важный хуй бумажный🎴, ты продал своего {item_to_sell} на органы! Хочешь сохранить друга\n\n Тогда Ищи в бд! Неуч блять!",
            f"О!, а куда это твой {item_to_sell} делся? Кажись его цыгани спиздили! Смотреть надо за своим {item_to_sell}, а не хуи пинать!\n\n Вы на базаре всё-таки! Всего проёбано {random.randint(1, 10)}."
        ]
        await event.respond(random.choice(success_texts))
    else:
        # Проигрыш
        losses = random.randint(1, 10)  # Случайное количество проигрышей
        response_texts = [
            f"БЛЯЯЯЯЯЯЯЯЯЯЯ😭😭 Ты проебал своего {item_to_sell} в казик, кажись его логи схавали.\n\nВсего ты проебал {losses}. Поищи в логах!",
            f"АХХХПАХХАХАХАПХПАХАПХ ЕБАТЬ ТЫ ЛОХ🤣🤣, Ты где-то проебал {item_to_sell} ищи в бд!\n\nВсего проёбано {losses}.",
            f"Лелелелелеле😑, тебе чё занятся нехуй? своего {item_to_sell} на базаре продавать. пиздуй ищи в логах!\n\nВсего проёбано {losses}.",
            f"ААХХАХАХАХАХАХХА😂😂😂😂😂, Кажись твой {item_to_sell} обосрался и убежал😂 ищи в логах!\n\nВсего проёбано {losses}.",
            f"АХХАПХАХПХАПХАПХАПХ🤣🤣🤣🤣, Ты успешно продал своего {item_to_sell} цыганам! теперь нету смысла искать в логах!",
            f"Ох ебааать😨, а кто это там с зади тебя стоит?, хахаха! наебал!, ты как обычно проебал своего {item_to_sell}, пиздуй искать в бд!\n\nВсего проёбано {losses}.",
            f"Стапе!😱, а где твой {item_to_sell}😨, Кажись он потерялся на базаре!, скорее вызывай ментов пока его бабки костылями не отпиздили!\n\nВсего проёбано {losses}."
        ]

        # Выбираем случайное сообщение для проигрыша
        response_message = random.choice(response_texts)

        # Создаем кнопки
        buttons = [
            [Button.inline("🔍Искать ещё раз!", f"search_again_{user_id}"),
             Button.inline("🤑Гойда продадим что-то?", f"sell_something_{user_id}")]
        ]

        # Отправляем сообщение с кнопками
        message = await event.respond(response_message, buttons=buttons)


@bot.on(events.CallbackQuery(pattern=r'search_again_(\d+)'))
async def search_again_handler(event):
    user_id = int(event.pattern_match.group(1))
    await event.answer("Да мне лень работать чё-то🥱🥱", alert=False)  # Ответ пользователю в виде окошка


@bot.on(events.CallbackQuery(pattern=r'sell_something_(\d+)'))
async def sell_something_handler(event):
    user_id = int(event.pattern_match.group(1))
    await event.answer("Напиши продать (что-то твоё)", alert=False)  # Ответ пользователю в виде окошка


@bot.on(events.NewMessage(pattern='/профиль'))
async def profile_command(event):
    user = await event.get_sender()  # Получаем пользователя, который отправил команду
    user_id = user.id
    role = db.get_user_role(user_id)  # Получаем роль пользователя

    # Получаем данные пользователя из базы
    user_data = db.get_user(user_id)
    custom_photo = user_data[7] if user_data else None
    preview_url = custom_photo if custom_photo else ROLES[role]['preview_url']
    checks_count = db.get_check_count(user_id)

    # Инициализация scammers_count
    scammers_count = 0
    scammers_info = ""

    # Для персонала показываем количество слитых скамеров
    if role in [6, 7, 8, 9, 10]:  # Проверяем, если это персонал
        scammers_count = db.get_user_scammers_count(user_id)  # Получаем количество слитых скаммеров
        scammers_info = f"🔥 **Скаммеров слито:** `{scammers_count}`\n"
    else:
        scammers_info = "🔥 **Скаммеров слито:** `0`\n"  # Если не персонал, показываем 0

    # Формируем текст профиля
    profile_text = f"""
**👤 Профиль пользователя в базе: {user.first_name}](tg://user/{user_id})**

🔍 **Вас проверяли:** `{checks_count}` раз
{scammers_info}
**📝 Роль в базе:** {ROLES[role]['name']}
**infinity Премиум:** {'✅' if db.get_premium_expiry(user_id) else '❌'}
[⠀](https://i.ibb.co/ycyPRXrb/photo-2025-04-17-17-44-20-2.jpg)
"""

    await event.respond(profile_text, parse_mode='md')


@bot.on(events.NewMessage(pattern=r'(?i)^\+спасибо'))
async def thank_command(event):
    logging.info("Команда +спасибо была вызвана.")
    user_id = event.sender_id

    # Проверка роли пользователя, который вызывает команду
    user_role = db.get_user_role(user_id)
    logging.info(f"Роль пользователя {user_id}: {user_role}")
    allowed_roles = [6, 8, 10, 11, 9, 13]  # Стажёр=6, Директор=8, Создатель=10, Кодер=1, Президент=9

    # Если у пользователя нет прав, просто выходим из функции
    if user_role not in allowed_roles:
        return

    # Получаем ID пользователя, которому будет выдано +1 слитого скаммера
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
        target_user_id = reply_message.sender_id

        # Проверяем, что у пользователя роль не 0 (разрешаем выдачу +спасибо пользователям с ролью 0)
        target_user_role = db.get_user_role(target_user_id)
        logging.info(f"Роль целевого пользователя {target_user_id}: {target_user_role}")

        # Условие, чтобы разрешить выдачу +спасибо пользователям с ролью 0
        if target_user_role in [1, 6, 8, 9, 10, 11, 13]:
            return  # Если роль целевого пользователя запрещает выдачу, просто выходим

    # Увеличиваем счетчик слитых скаммеров
    try:
        db.increment_scammers_count(target_user_id)  # Метод для увеличения счетчика
        await event.respond(
            f"📛 пользователю с ID: {target_user_id} выдано +спасибо.\n\n"
            "📈 Спасибо, что боретесь со скамом вместе с infinity [ ] (https://i.ibb.co/HDc1Bwpr/photo-2025-04-17-17-44-20-4.jpg).\n\n"
            "☕ Если у вас есть ещё скаммеры, сообщите об этом нашим стажёрам или администраторам, и они занесут скаммера в базу!"
        )
    except Exception as e:
        logging.error(f"Ошибка при увеличении счетчика слитых скаммеров: {str(e)}")
        await event.respond("❌ Произошла ошибка при увеличении счетчика слитых скаммеров.")


# Обработчик команды для проверки баланса
@bot.on(events.NewMessage(pattern=r'^(балик|Балик)$'))
async def balance_check(event):
    user_id = event.sender_id
    balance = db.get_premium_points(user_id)

    # Выдача 1000 коинов новичкам
    if balance == 0:
        db.add_premium_points(user_id, 1000)
        balance = 1000  # Обновляем баланс для ответа

    await event.respond(f"Ваш баланс: {balance} коинов.")


# Обработчик для начала игры
@bot.on(events.NewMessage(pattern=r'^мб (\d+)$'))
async def start_game(event):
    user_id = event.sender_id
    bet_amount = int(event.pattern_match.group(1))
    balance = db.get_premium_points(user_id)

    if balance < bet_amount:
        await event.respond("❌ У вас недостаточно коинов для этой ставки!")
        return

    # Запрос на другого игрока
    await event.respond(f"{user_id} предложил сыграть в морской бой на сумму {bet_amount} коинов. Согласитесь?")

    # Хранение информации о игре
    db.cur.execute(
        'INSERT INTO games (player1_id, player2_id, bet_amount, turn, player1_aimed, player2_aimed) VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, None, bet_amount, 1, 0, 0))
    db.conn.commit()

    buttons = [[Button.inline("Принять!", f"accept_game_{user_id}_{bet_amount}")]]
    await event.respond("Нажмите кнопку, чтобы принять игру:", buttons=buttons)


# Обработчик принятия игры
@bot.on(events.CallbackQuery(pattern=r'accept_game_(\d+)_(\d+)'))
async def accept_game(event):
    opponent_id = int(event.pattern_match.group(1))
    bet_amount = int(event.pattern_match.group(2))

    # Проверка, что игра существует
    game = db.cur.execute('SELECT * FROM games WHERE player1_id = ?', (opponent_id,)).fetchone()
    if not game:
        await event.answer("❌ Игра не найдена!", alert=True)
        return

    # Начало игры
    await event.respond(f"🎮 Игра началась! Ставка: {bet_amount} коинов. Ваш ход!")
    db.cur.execute('UPDATE games SET player2_id = ?, turn = ? WHERE player1_id = ?', (event.sender_id, 2, opponent_id))
    db.conn.commit()

    # Кнопка для выстрела
    await send_action_buttons(event, opponent_id)


# Обработчик выстрела
@bot.on(events.CallbackQuery(pattern=r'shoot_(\d+)'))
async def shoot(event):
    opponent_id = int(event.pattern_match.group(1))

    # Получаем информацию об игре
    game = db.cur.execute('SELECT * FROM games WHERE player1_id = ? OR player2_id = ?',
                          (event.sender_id, opponent_id)).fetchone()
    if not game:
        await event.answer("❌ Игра не найдена!", alert=True)
        return

    # Проверка, чей сейчас ход
    if game[3] != (1 if event.sender_id == game[1] else 2):
        await event.answer("❌ Это не ваш ход!", alert=True)
        return

    chance = 20  # базовый шанс
    if random.randint(1, 100) <= chance:
        # Успех
        db.add_premium_points(event.sender_id, game[2])  # Ставка
        db.add_premium_points(opponent_id, -game[2])  # Снимаем ставку с проигравшего

        # Отправка сообщения о победе с изображением
        await event.respond("✅ Вы успешно уничтожили корабль противника!",
                            file="https://i.ibb.co/DfSQZk0Z/temp-5173733679.jpg")
    else:
        # Провал
        await event.respond("❌ Вы промахнулись мимо корабля.")

    # Завершение игры
    await update_turn(event, opponent_id)


# Обработчик кнопки "Прицелиться"
@bot.on(events.CallbackQuery(pattern=r'aim_(\d+)'))
async def aim(event):
    opponent_id = int(event.pattern_match.group(1))

    # Получаем информацию об игре
    game = db.cur.execute('SELECT * FROM games WHERE player1_id = ? OR player2_id = ?',
                          (event.sender_id, opponent_id)).fetchone()
    if not game:
        await event.answer("❌ Игра не найдена!", alert=True)
        return

    # Проверка, чей сейчас ход
    if game[3] != (1 if event.sender_id == game[1] else 2):
        await event.answer("❌ Это не ваш ход!", alert=True)
        return

    # Проверка, если игрок уже прицеливался в этом раунде
    if (event.sender_id == game[1] and game[5] == 1) or (event.sender_id == game[2] and game[6] == 1):
        await event.answer("❌ Вы уже прицелились в этом ходе!", alert=True)
        return

    # Обновляем статус прицеливания
    if event.sender_id == game[1]:
        db.cur.execute('UPDATE games SET player1_aimed = ? WHERE player1_id = ?', (1, game[1]))
    else:
        db.cur.execute('UPDATE games SET player2_aimed = ? WHERE player2_id = ?', (1, game[2]))

    db.conn.commit()

    # Отправка сообщения о прицеливании
    await event.respond("✅ Успешно! +5% шанса к попаданию по противнику!")

    await update_turn(event, opponent_id)


async def update_turn(event, opponent_id):
    # Обновляем информацию о ходе
    db.cur.execute('UPDATE games SET turn = ? WHERE player1_id = ? OR player2_id = ?',
                   (1 if event.sender_id == opponent_id else 2, event.sender_id, opponent_id))
    db.conn.commit()

    # Удаляем старые кнопки и создаем новые для следующего игрока
    await event.respond("Ваш ход завершён. Теперь ход противника.")
    await send_action_buttons(event, opponent_id)


async def send_action_buttons(event, opponent_id):
    # Проверяем, существует ли игра
    game = db.cur.execute('SELECT * FROM games WHERE player1_id = ? OR player2_id = ?',
                          (event.sender_id, opponent_id)).fetchone()
    if not game:
        await event.respond("❌ Игра не найдена!", alert=True)
        return

    buttons = [[Button.inline("Выстрелить!", f"shoot_{opponent_id}")],
               [Button.inline("Прицелиться!", f"aim_{opponent_id}")]]
    await event.respond("Выберите действие:", buttons=buttons)


# Обработчик команды /магазин
@bot.on(events.NewMessage(pattern='/магазин'))
async def shop_handler(event):
    user_id = event.sender_id
    balance = db.get_premium_points(user_id)  # Получаем баланс

    # Создание кнопок
    buttons = [
        [Button.inline("Прем 1д (10 коинов)", data="buy_premium_1d")],
        [Button.inline("Прем 1н (50 коинов)", data="buy_premium_7d")],
        [Button.inline("Прем 1м (125 коинов)", data="buy_premium_30d")],
        [Button.inline("Отдых 1д (100 коинов)", data="buy_rest_1d")],
        [Button.inline(f"Сумма: {balance} очков")]
    ]

    # Отправка сообщения с кнопками
    await event.respond("Добро пожаловать в магазин!", buttons=buttons)


# Обработчик покупки
@bot.on(events.CallbackQuery(pattern='buy_.*'))
async def purchase_handler(event):
    user_id = event.sender_id
    action = event.data.decode('utf-8')

    if action == "buy_premium_1d":
        cost = 10
        duration = 1
        message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_premium_7d":
        cost = 50
        duration = 7
        message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_premium_30d":
        cost = 125
        duration = 30
        message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_rest_1d":
        cost = 100
        duration = 0  # Отдых не имеет срока
        message = "Вы успешно купили отдых, вы освобождены от обязательств стажёра на 1 день!"
    else:
        await event.answer("Неизвестная команда.", alert=True)
        return

    if db.get_premium_points(user_id) >= cost:
        db.add_premium_points(user_id, -cost)
        if duration > 0:
            expiry_date = (datetime.now() + timedelta(days=duration)).strftime("%Y-%m-%d %H:%M:%S")
            db.add_premium(user_id, expiry_date)
        await event.answer(message, alert=True)
    else:
        await event.answer("У вас недостаточно коинов!", alert=True)


# Словарь для отслеживания сообщений
user_message_count = defaultdict(list)


@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id

    # Игнорируем сообщения от ботов
    if event.sender.bot:
        return

    # Получаем текущее время
    current_time = datetime.now()

    # Добавляем временную метку сообщения
    user_message_count[user_id].append(current_time)

    # Удаляем временные метки старше 30 секунд
    user_message_count[user_id] = [timestamp for timestamp in user_message_count[user_id]
                                   if current_time - timestamp < timedelta(seconds=30)]

    # Проверяем количество сообщений
    if len(user_message_count[user_id]) > 8:
        # Выдаём мут на 10 минут
        await bot.edit_permissions(
            event.chat_id,
            user_id,
            until_date=current_time + timedelta(minutes=10),
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False
        )

        await event.respond(f"🔇 Пользователь {event.sender.first_name} был замучен за спам на 10 минут!")
        logging.info(f"Пользователь {user_id} замучен за спам.")

        # Очищаем записи сообщений после мута
        del user_message_count[user_id]


# Глобальные переменные
games = {}
joined_users_cache = set()
guesses = {}
muted_users = {}  # {user_id: expiry_time}
last_scam_times = {}
START_USERS = set()  # Пользователи, использовавшие /start
BOT_CHATS = set()  # Чаты, где есть бот
LAST_CHECKED = {}  # Последний проверенный пользователь
TEMP_STORAGE = {}  # Временное хранилище данных
COUNTRIES = [
    "США 🇺🇸", "Канада 🇨🇦", "Мексика 🇲🇽", "Бразилия 🇧🇷",
    "Аргентина 🇦🇷", "Великобритания 🇬🇧", "Франция 🇫🇷",
    "Германия 🇩🇪", "Италия 🇮🇹", "Испания 🇪🇸", "Китай 🇨🇳",
    "Япония 🇯🇵", "Австралия 🇦🇺", "Индия 🇮🇳", "Россия 🇷🇺",
    "Южноафриканская Республика 🇿🇦", "Египет 🇪🇬", "ОАЭ 🇦🇪",
    "Турция 🇹🇷", "Греция 🇬🇷", "Швеция 🇸🇪", "Норвегия 🇳🇴",
    "Финляндия 🇫🇮", "Дания 🇩🇰", "Польша 🇵🇱", "Чехия 🇨🇿",
    "Австрия 🇦🇹", "Швейцария 🇨🇭", "Нидерланды 🇳🇱", "Бельгия 🇧🇪",
    "Ирландия 🇮🇪", "Португалия 🇵🇹", "Румыния 🇷🇴", "Словакия 🇸🇰",
    "Словения 🇸🇮", "Хорватия 🇭🇷", "Латвия 🇱🇻", "Литва 🇱🇹",
    "Эстония 🇪🇪", "Мальта 🇲🇹", "Кипр 🇨🇾", "Исландия 🇮🇸",
    "Албания 🇦🇱", "Сербия 🇷🇸", "Босния и Герцеговина 🇧🇦",
    "Черногория 🇲🇪", "Македония 🇲🇰", "Косово 🇽🇰", "Беларусь 🇧🇾",
    "Украина 🇺🇦", "Грузия 🇬🇪", "Армения 🇦🇲", "Азербайджан 🇦🇿",
    "Казахстан 🇰🇿", "Узбекистан 🇺🇿", "Таджикистан 🇹🇯",
    "Туркменистан 🇹🇲", "Кыргызстан 🇰🇬", "Монголия 🇲🇳",
    "Иран 🇮🇷", "Ирак 🇮🇶", "Сирия 🇸🇾", "Ливан 🇱🇧",
    "Иордания 🇯🇴", "Катар 🇶🇦", "Бахрейн 🇧🇭", "Кувейт 🇰🇼",
    "Саудовская Аравия 🇸🇦", "Йемен 🇾🇪", "Вьетнам 🇻🇳",
    "Таиланд 🇹🇭", "Малайзия 🇲🇾", "Индонезия 🇮🇩", "Филиппины 🇵🇭",
    "Сингапур 🇸🇬", "Непал 🇳🇵", "Шри-Ланка 🇱🇰", "Бангладеш 🇧🇩",
    "Пакистан 🇵🇰", "Мьянма 🇲🇲", "Лаос 🇱🇦", "Камбоджа 🇰🇭",
    "Тайвань 🇹🇼", "Гонконг 🇭🇰", "Южная Корея 🇰🇷", "Северная Корея 🇰🇵",
    "Австралия 🇦🇺", "Новая Зеландия 🇳🇿", "Папуа — Новая Гвинея 🇵🇬",
    "Фиджи 🇫🇯", "Самоа 🇼🇸", "Тонга 🇹🇴", "Вануату 🇻🇺",
    "Микронезия 🇫🇲", "Науру 🇳🇷", "Тувалу 🇹🇻", "Соломоновы Острова 🇸🇧",
    "Кирибати 🇰🇷", "Сент-Люсия 🇱🇨", "Сент-Винсент и Гренадины 🇻🇨",
    "Барбадос 🇧🇧", "Ямайка 🇯🇲", "Тринидад и Тобаго 🇹🇹",
    "Багамы 🇧🇸", "Гренада 🇬🇩", "Антигуа и Барбуда 🇦🇬",
    "Сент-Китс и Невис 🇰🇳"
]

# API для загрузки изображений
IMG_API_KEY = "cb21b904cc405cdfc05731896bc29c64"


# Функция для проверки премиум статуса
def is_premium(user_id):
    expiry_date = db.get_premium_expiry(user_id)
    if not expiry_date:
        return False
    return datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S") > datetime.now()


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    sender = await event.get_sender()
    START_USERS.add(event.sender_id)

    # Основное сообщение с reply-кнопками
    await event.respond(
        "👋 Добро пожаловать в infinity!\n\n"
        "Мы — официальный бот антискам базы infinity | Scam Base, созданный для обеспечения вашей безопасности в мире обменов и сделок.\n\n"
        "🔒 Ваше доверие — наша приоритетная задача!\n\n[⠀](https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg)!\n"
        "Спасибо, что выбрали infinity! Вместе мы сделаем все безопаснее!",
        buttons=main_buttons
    )

    # Дополнительные inline-кнопки
    inline_buttons = [
        [Button.url("🌍 Предложка", "https://t.me/infinityantiscam")],
        [Button.url("🔐 Кодер Бота", "https://t.me/rewylerss")],
        [Button.url("🔍 Трейдинг Чат", "https://t.me/steal_a_brainrotchat1")]
    ]

    await event.respond(
        "📌 **Дополнительные функции:**",
        buttons=inline_buttons,
        parse_mode='md'
    )

    # Сообщение с кнопкой добавления в чат
    await event.respond(
        "Спасибо за выбор infinity нас, добавив нашего бота в чат",
        buttons=[
            [Button.url("💌 добавить в чат",
                        "http://t.me/InfinityASB_bot?startgroup=newgroup&admin=manage_chat+delete_messages+restrict_members+invite_users+restrict_members+change_info+pin_messages+manage_video_chats")]
        ]
    )


@bot.on(events.CallbackQuery(pattern='about_project'))
async def about_project(event):
    about_text = (
        "спасибо за выбор infinity🤗\n"
       f"вы можете поддержать нас,добавив нашего бота в чат\n"
   )


    buttons = [
        [Button.inline("🤔 Как стать гарантом?", "how_to_become_guarantor")],
        [Button.inline("🤑 У кого и как купить траст?", "how_to_buy_trust")],
        [Button.inline("😈 Как слить вам скаммера?", "how_to_report_scammer")]
    ]

    await event.respond(
        about_text,
        buttons=buttons,
        parse_mode='md'
    )


# Обработчики для других кнопок
@bot.on(events.CallbackQuery(pattern='how_to_become_guarantor'))
async def how_to_become_guarantor(event):
    response_text = (
        "Чтобы стать гарантом, нужно пройти набор в нашу базу. "
        "Владельцы регулярно проводят наборы на многие роли, в том числе гарантов. "
        "Если ты хочешь стать гарантом, просто пройди набор в нашу базу🤗[⠀](https://i.ibb.co/ZR8qJ80N/1.jpg)"
    )
    await event.respond(response_text)


@bot.on(events.CallbackQuery(pattern='how_to_buy_trust'))
async def how_to_buy_trust(event):
    response_text = (
        "Хочешь купить траст? Да ты богач🤗. Чтобы купить траст, тебе нужно написать нашим гарантам "
        "Гарантов ты можешь найти в чате или же нажав на кнопку 'Гаранты' в главном меню🤑[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)"
    )
    await event.respond(response_text)


@bot.on(events.CallbackQuery(pattern='how_to_report_scammer'))
async def how_to_report_scammer(event):
    response_text = (
        "Ох, тебя тоже задрали скаммеры? Меня тоже😡 Если ты действительно хочешь слить скаммера, "
        "то тебе нужно зайти в нашу базу и написать в чат доказательства скама и юзернейм-айди. "
        "Наши волонтёры занесут этого скаммера😈[⠀](https://i.ibb.co/bj4g7h3y/photo-2025-04-17-17-44-19-3.jpg)"
    )
    await event.respond(response_text)


# Обработчик кнопки "Поддержать"
@bot.on(events.CallbackQuery(pattern='support_handler'))
async def support_handler(event):
    support_text = (
        "Если вы хотите помочь кодеру для продвижения ботов, "
        "то вы можете поддержать кодера этими вариантами:\n\n"
        "Если вы хотите поддержать кодера в ттд ник: **pisun11000**[⠀](https://i.ibb.co/0x7KTr0/image.jpg)"
    )

    buttons = [
        [Button.url("💌 Крипто ботом", "https://t.me/send?start=IVdGVHgwlEsa")],
        [Button.url("💞 Наш кодер", "https://t.me/Steach_Garant")]
    ]

    await event.respond(
        support_text,
        buttons=buttons,
        parse_mode='md'
    )


@bot.on(events.NewMessage(pattern="🔗 Проверить ссылку"))
async def check_link(event):
    buttons = [
        [Button.inline("1: Роблокс", b"check_roblox")],
        [Button.inline("2: Сайт", b"check_site")],
        [Button.inline("3: Проверить на стиллер/логер", b"check_logger")]
    ]
    await event.respond("Выберите тип ссылки:", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=b"check_roblox"))
async def handle_roblox_link(event):
    buttons = [
        [Button.inline("1: Роблокс профиль", b"roblox_profile")],
        [Button.inline("2: Пригласительная ссылка", b"invite_link")],
        [Button.inline("3: Ссылка на Роблокс", b"roblox_link")]
    ]
    try:
        await event.respond("Выберите пункт:", buttons=buttons)
        await event.delete()  # Удаляем сообщение с кнопками
    except Exception as e:
        logging.error(f"Ошибка при обработке выбора Роблокс: {e}")


@bot.on(events.CallbackQuery(pattern=b"roblox_profile"))
async def handle_roblox_profile(event):
    await event.respond("Отправьте ссылку на профиль игрока!")

    @bot.on(events.NewMessage(from_users=event.sender_id))
    async def roblox_profile_handler(message):
        try:
            link = message.text.strip()
            if re.match(r"https?://www\.roblox\.com/users/\d+/profile", link):
                await message.reply("Ссылка безопасна! Но помните, лучше не переходить по посторонним ссылкам.")
            else:
                await message.reply("Ссылка не безопасна! Не рекомендуем переходить по ней.")
        except Exception as e:
            logging.error(f"Ошибка при проверке профиля Роблокс: {e}")
        finally:
            bot.remove_event_handler(roblox_profile_handler)


@bot.on(events.CallbackQuery(pattern=b"invite_link"))
async def handle_invite_link(event):
    await event.respond("Отправьте пригласительную ссылку, и я её проверю!")

    @bot.on(events.NewMessage(from_users=event.sender_id))
    async def invite_link_handler(message):
        try:
            link = message.text.strip()
            if re.match(r"https?://www\.roblox\.com/", link):
                await message.reply("Ссылка безопасна! Но лучше не переходить по посторонним ссылкам.")
            else:
                await message.reply("Ссылка не безопасна! Не рекомендуем переходить по ней.")
        except Exception as e:
            logging.error(f"Ошибка при проверке пригласительной ссылки: {e}")
        finally:
            bot.remove_event_handler(invite_link_handler)


@bot.on(events.CallbackQuery(pattern=b"roblox_link"))
async def handle_roblox_link(event):
    await event.respond("Отправьте ссылку на Роблокс!")

    @bot.on(events.NewMessage(from_users=event.sender_id))
    async def roblox_link_handler(message):
        try:
            link = message.text.strip()
            if re.match(r"https?://www\.roblox\.com/", link):
                await message.reply("Ссылка безопасна!")
            else:
                await message.reply("Ссылка не безопасна! Не рекомендуем переходить по ней.")
        except Exception as e:
            logging.error(f"Ошибка при проверке ссылки на Роблокс: {e}")
        finally:
            bot.remove_event_handler(roblox_link_handler)


@bot.on(events.CallbackQuery(pattern=b"check_site"))
async def handle_site_link(event):
    await event.respond("Отправьте ссылку на сайт, который хотите проверить!")

    @bot.on(events.NewMessage(from_users=event.sender_id))
    async def site_link_handler(message):
        try:
            link = message.text.strip()
            if re.match(r"https?://[^\s]+", link) and len(link) < 100:
                await message.reply(
                    "Ссылка безопасна! Но учтите, в ссылке может быть логгер. Рекомендуем проверить ссылку, нажав на 3 кнопку.")
            else:
                await message.reply("Ссылка не является безопасной, рекомендуем не переходить по ней!")
        except Exception as e:
            logging.error(f"Ошибка при проверке ссылки на сайт: {e}")
        finally:
            bot.remove_event_handler(site_link_handler)


@bot.on(events.CallbackQuery(pattern=b"check_logger"))
async def handle_logger_check(event):
    await event.respond("Отправьте ссылку, которую хотите проверить на наличие логгера или стиллера!")

    @bot.on(events.NewMessage(from_users=event.sender_id))
    async def logger_check_handler(message):
        try:
            link = message.text.strip()
            # Пример проверки (можно добавить более сложную логику)
            if re.search(r"(virus|malware|stealer)", link, re.IGNORECASE):
                await message.reply(
                    "⚠️ Внимание! Ссылка может содержать вредоносный код (стиллер/логер). Не переходите по ней!")
            else:
                await message.reply(
                    "✅ Ссылка выглядит безопасной, но всегда будьте осторожны при переходе по неизвестным ссылкам.")
        except Exception as e:
            logging.error(f"Ошибка при проверке на логгер/стиллер: {e}")
        finally:
            bot.remove_event_handler(logger_check_handler)


@bot.on(events.NewMessage(pattern="❓ Частые вопросы"))
async def faq_handler(event):
    query = event.raw_text
    faq_buttons = [
        [Button.inline("Кто такой гарант?", "who_is_guarantee")],
        [Button.inline("Как найти гаранта?", "find_guarantee")],
        [Button.inline("Как стать волонтёром?", "become_volunteer")],
        [Button.inline("Как стать гарантом?", "become_guarantee")],
        [Button.inline("Как слить скаммера?", "report_scammer")],
        [Button.inline("Когда набор на админов?", "admin_recruitment")],
        [Button.inline("Можно ли купить роль в базе?", "buy_role")],
        [Button.inline("Можно ли купить снятие из базы?", "buy_removal")],
        [Button.inline("Вернуться ↩", "back_to_main")]
    ]

    await event.respond("Выберите нужный вам пункт:[⠀](https://i.ibb.co/q3bGLp9J/image.png)", buttons=faq_buttons)


@bot.on(events.CallbackQuery(data="who_is_guarantee"))
async def who_is_guarantee_handler(event):
    response_text = (
        "💁‍♂️ Кто такой гарант?\n\n"
        "[У нас есть мини-статья об этом (ТЫК)](https://telegra.ph/Kto-takoj-GARANT-05-29)"
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="find_guarantee"))
async def find_guarantee_handler(event):
    response_text = (
        "💁‍♂️ Как найти гаранта?\n\n"
        "В лс с ботом жмём кнопку 'Гаранты' или вводим /mms.\n\n"
        "Бот отобразит вам проверенных людей, которые безопасно проведут сделку 😉"
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="become_volunteer"))
async def become_volunteer_handler(event):
    response_text = (
        "💁‍♂️ Как стать волонтёром?\n\n"
        "Следите за информацией в новостнике базы и участвуйте в наборах."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="become_guarantee"))
async def become_guarantee_handler(event):
    response_text = (
        "💁‍♂️ Как стать гарантом?\n\n"
        "Следите за информацией в новостнике базы и участвуйте в наборах."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="report_scammer"))
async def report_scammer_handler(event):
    response_text = (
        "💁‍♂️ Как слить скаммера?\n\n"
        "Слить скаммера можно в нашей группе жалоб - новостнике базы.\n"
        "- Заходите в группу и кидаете пруфы скама, админы их рассматривают и принимают решение."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="admin_recruitment"))
async def admin_recruitment_handler(event):
    response_text = (
        "💁‍♂️ Когда набор на админов?\n\n"
        "В среднем наборы проходят 2 раза в месяц."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="buy_role"))
async def buy_role_handler(event):
    response_text = (
        "НЕТ. Мы НЕ продаём админки/ роли гарантов в нашей базе. "
        "Если вы хотите поддержать нашу базу - /premium."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="buy_removal"))
async def buy_removal_handler(event):
    response_text = (
        "НЕТ. Мы НЕ удаляем пользователей. Наша цель - быть надёжным и честным источником информации."
    )
    back_button = [Button.inline("Вернуться ↩", "back_to_main")]
    await event.respond(response_text, buttons=back_button)


@bot.on(events.CallbackQuery(data="back_to_main"))
async def back_to_main_handler(event):
    # Возвращаем пользователя к сообщению с кнопками выбора
    faq_buttons = [
        [Button.inline("Кто такой гарант?", "who_is_guarantee")],
        [Button.inline("Как найти гаранта?", "find_guarantee")],
        [Button.inline("Как стать волонтёром?", "become_volunteer")],
        [Button.inline("Как стать гарантом?", "become_guarantee")],
        [Button.inline("Как слить скаммера?", "report_scammer")],
        [Button.inline("Когда набор на админов?", "admin_recruitment")],
        [Button.inline("Можно ли купить роль в базе?", "buy_role")],
        [Button.inline("Можно ли купить снятие из базы?", "buy_removal")],
        [Button.inline("Вернуться ↩", "back_to_main")]
    ]

    await event.respond("Выберите нужный вам пункт:[⠀](https://i.ibb.co/q3bGLp9J/image.png)", buttons=faq_buttons)


# Обработчик команды /help
@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    help_text = """
🤖 **Команды бота:**

📋 **Проверка пользователей:**
• `Чек [юзернейм/ID]` - проверить пользователя
• `Чек` (ответом на сообщение) - проверить пользователя
• `Чек ми/я/себя` - проверить себя

👮‍♂️ **Выдача ролей:**
• `+стажер` (ответом) - выдать роль стажера  
• `+админ` (ответом) - выдать роль админа
• `+директор` (ответом) - выдать роль директора
• `+президент` (ответом) - выдать роль президента 
• `+создатель` (ответом) - выдать роль создателя
• `+кодер` (ответом) - выдать роль кодера
• `+гарант` (ответом) - выдать роль гаранта

🔄 **Снятие ролей:**
• `-стажер` (ответом) - снять роль стажера
• `-админ` (ответом) - снять роль админа  
• `-директор` (ответом) - снять роль директора
• `-президент` (ответом) - снять роль президента
• `-создатель` (ответом) - снять роль создателя  
• `-кодер` (ответом) - снять роль кодера
• `-гарант` (ответом) - снять роль гаранта

⚠️ **Примечание:**
Команды выдачи и снятия ролей доступны только создателю и кодеру!
"""
    await event.respond(help_text, parse_mode='md')


# Переменные для хранения статистики
guarantors_count = len(get_guarantors())  # Получаем количество гарантов
trainees_count = len(get_trainees())  # Получаем количество стажеров
total_messages = 0
verified_guarantors_count = 0
checks_count = 0
scammers_count = 0

# Словари для хранения времени последнего вызова команд
admin_cooldowns = {}
guarantor_cooldowns = {}


# Обработчик команды "админы!"
@bot.on(events.NewMessage(pattern=r'(?i)^админы!$'))
async def call_admins(event):
    user_id = event.sender_id
    current_time = datetime.now()

    # Проверка времени последнего вызова команды
    if user_id in admin_cooldowns:
        time_diff = current_time - admin_cooldowns[user_id]
        if time_diff < timedelta(hours=4):
            remaining = timedelta(hours=4) - time_diff
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await event.respond(
                f"**⏳ Подождите {hours} ч. {minutes} мин. прежде чем снова вызывать админов!**"
            )
            return

    admin_cooldowns[user_id] = current_time

    # Получение администраторов из базы данных
    conn =get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id FROM users 
        WHERE role IN ("Стажер", "Админ", "Директор", "Президент", "Создатель", "Заместитель")
    ''')
    admins = cursor.fetchall()
    conn.close()

    # Создаем текст с невидимыми упоминаниями
    mentions_text = "**✅ Админы вызваны!**"
    for admin in admins:
        mentions_text += f"[\u200b](tg://user?id={admin[0]})"  # Невидимое упоминание

        # Отправка личного сообщения админам
        caller_username = event.sender.username
        caller_mention = f"@{caller_username}" if caller_username else event.sender.mention

        admin_message = f"**🚨 В чате пользователь {caller_mention} вызывает админов!**"

        await bot.send_message(admin[0], admin_message)
        logging.info(f"Сообщение отправлено администратору: {admin[0]}")

    # Отправляем одно сообщение с текстом и скрытыми упоминаниями
    await event.respond(mentions_text)


# Обработчик команды "гаранты!"
@bot.on(events.NewMessage(pattern=r'(?i)^гаранты!$'))
async def call_guarantors(event):
    user_id = event.sender_id
    current_time = datetime.now()

    # Проверка времени последнего вызова команды
    if user_id in guarantor_cooldowns:
        time_diff = current_time - guarantor_cooldowns[user_id]
        if time_diff < timedelta(hours=1):
            remaining = timedelta(hours=1) - time_diff
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await event.respond(
                f"**⏳ Подождите {hours} ч. {minutes} мин. прежде чем снова вызывать гарантов!**"
            )
            return

    guarantor_cooldowns[user_id] = current_time

    # Получение гарантов из базы данных
    guarantors = get_guarantors()

    # Создаем текст с невидимыми упоминаниями
    mentions_text = "**🔰 Гаранты вызваны!**"
    for guarantor_id in guarantors:
        mentions_text += f"[\u200b](tg://user?id={guarantor_id})"  # Невидимое упоминание

        # Отправка личного сообщения гарантам
        caller_username = event.sender.username
        caller_mention = f"@{caller_username}" if caller_username else event.sender.mention

        guarantor_message = f"**🚨 В чате пользователь {caller_mention} вызывает гарантов!**"

        await bot.send_message(guarantor_id, guarantor_message)
        logging.info(f"Сообщение отправлено гаранту: {guarantor_id}")

    # Отправляем одно сообщение с текстом и скрытыми упоминаниями
    await event.respond(mentions_text)


# Обработчик команды "/stata"
@bot.on(events.NewMessage(pattern=r'(?i)^/stata$'))
async def show_statistics(event):
    global total_messages, verified_guarantors_count, checks_count, scammers_count, trainees_count

    # Получаем общее количество сообщений через экземпляр db
    total_messages = db.get_total_messages()  # Используйте экземпляр db

    # Получаем количество гарантов
    guarantors_count = len(get_guarantors())  # Получаем актуальное количество гарантов

    statistics = (
        f"📊 **Статистика чата:[⠀](https://i.ibb.co/dwfVKmMH/photo-2025-04-17-17-44-19-2.jpg)**\n"
        f"👥 Гаранты: {guarantors_count}\n"
        f"👨‍🎓 Стажеры: {trainees_count}\n"
        f"📩 Общее количество сообщений: {total_messages}\n"
        f"✅ Проверены гарантом: {verified_guarantors_count}\n"
        f"🔍 Число проверок: {checks_count}\n"
        f"🚫 Скаммеры в базе: {scammers_count}"
    )

    await event.respond(statistics)


@bot.on(events.NewMessage())
async def count_messages(event):
    global total_messages
    total_messages += 1
    db.update_total_messages(1)
    logging.info(f"Общее количество сообщений: {total_messages}")


@bot.on(events.NewMessage(pattern=r'(?i)^/del'))
async def delete_message(event):
    if event.is_reply:
        replied_message = await event.get_reply_message()
        await replied_message.delete()  # Удаляем сообщение, на которое ответили
    else:
        await event.reply("❌ Пожалуйста, ответьте на сообщение, которое хотите удалить.")


@bot.on(events.NewMessage(pattern=r'[+-](?:[А-Яа-я]+)(?:\s+(?:@?\w+|\d+))?'))
async def handle_role_command(event):
    user_role = db.get_user_role(event.sender_id)
    is_admin = event.sender_id in [262511724] or user_role == 10

    if not is_admin:
        msg = await event.reply("❌ У вас нет прав для выполнения этой команды",
                                buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
        return

    command_parts = event.raw_text.split()
    action = command_parts[0][0]  # + или -
    role = command_parts[0][1:].lower()

    # Получаем целевого пользователя
    try:
        if len(command_parts) > 1:
            target = command_parts[1]
            if target.isdigit():
                user = await event.client.get_entity(int(target))
            else:
                if target.startswith('@'):
                    target = target[1:]
                user = await event.client.get_entity(target)
        else:
            if not event.is_reply:
                msg = await event.reply("❌ Укажите пользователя или ответьте на его сообщение",
                                        buttons=Button.inline("↩Скрыть", b"hide_message"))
                bot.last_message_id = msg.id
                return
            replied = await event.get_reply_message()
            user = await event.client.get_entity(replied.sender_id)
    except:
        msg = await event.reply("❌ Не удалось найти пользователя!",
                                buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
        return

    role_mapping = {
        'стажер': 6,
        'админ': 7,
        'директор': 8,
        'президент': 9,
        'гарант': 1,
        'кодер': 11,
        'создатель': 10,
        'айдош': 13
    }

    current_role = db.get_user_role(user.id)

    if action == '+':
        # Проверка для президента
        if user_role == 9 and role in ['президент']:
            msg = await event.reply("❌ Президент не может выдавать роль президента.",
                                    buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        # Специальные права для ID 5399940308 и 808428464
        # Специальные права для выдачи ролей создателя и кодера
        if event.sender_id in [262511724] and role in ['кодер', 'создатель']:
            db.add_user(user.id, user.username)
            db.update_role(user.id, role_mapping[role])
            msg = await event.reply(
                f"✅ Роль {role} выдана пользователю [{user.first_name}](tg://user?id={user.id})",
                buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        # Обычная выдача ролей
        if current_role in [1]:
            db.add_user(user.id, user.username)
            db.update_role(user.id, role_mapping[role])
            msg = await event.reply(
                f"✅ Роль {role} выдана пользователю [{user.first_name}](tg://user?id={user.id})",
                buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
        else:
            msg = await event.reply("❌ Нельзя выдавать роль пользователю, который уже имеет роль.",
                                    buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
    else:
        # Снятие ролей
        # Снятие роли создателя
        if current_role == 10 and event.sender_id in [262511724]:
            db.update_role(user.id, 0)
            msg = await event.reply(
                f"✅ Роль снята с пользователя [{user.first_name}](tg://user?id={user.id})",
                buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        if current_role == 10 and user_role == 10:
            msg = await event.reply("❌ Создатель не может снять роль создателя у другого создателя.",
                                    buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        if current_role > 0:
            db.update_role(user.id, 0)
            msg = await event.reply(
                f"✅ Роль снята с пользователя [{user.first_name}](tg://user?id={user.id})",
                buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
        else:
            msg = await event.reply("❌ У пользователя нет роли",
                                    buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id


@bot.on(events.CallbackQuery(data=b"hide_message"))
async def hide_message_handler(event):
    try:
        await event.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")


# Права для мута (ограничения)
MUTE_RIGHTS = ChatBannedRights(
    until_date=None,
    send_messages=True,
    send_media=True,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
)

# Права для размута (снятие ограничений)
UNMUTE_RIGHTS = ChatBannedRights(
    until_date=None,
    send_messages=False,
    send_media=False,
    send_stickers=False,
    send_gifs=False,
    send_games=False,
    send_inline=False,
)


async def check_admin(chat, user_id):
    """Проверяет, является ли пользователь администратором"""
    if user_id in ADMINS:
        return True

    try:
        participant = await bot.get_permissions(chat, user_id)
        return participant.is_admin
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        return False


async def send_log(action, admin, user, duration, chat, reason=None, message_link=None):
    """Отправляет логи в канал"""
    text = (
        f"**{action.upper()}**\n\n"
        f"👤 **Пользователь:** {user.first_name} (`{user.id}`)\n"
        f"👮 **Администратор:** {admin.first_name} (`{admin.id}`)\n"
        f"💬 **Чат:** {chat.title} (`{chat.id}`)\n"
    )

    if duration:
        text += f"⏳ **Длительность:** {duration}\n"
    if reason:
        text += f"📝 **Причина:** {reason}\n"
    if message_link:
        text += f"🔗 **Сообщение:** [ссылка]({message_link})"

    try:
        await bot.send_message(LOG_CHANNEL, text, link_preview=False)
    except Exception as e:
        logger.error(f"Ошибка отправки лога: {e}")


@bot.on(events.NewMessage(pattern=r'(?i)^(/|\.)?(mute|мут)(@\w+)?\s*(\d+[дмчh])\s*(.*)'))
async def mute_handler(event):
    """Обработчик команды мута"""
    # Получаем имя пользователя, если указано
    username = event.pattern_match.group(3)
    replied = await event.get_reply_message() if not username else None

    if username:
        try:
            user = await bot.get_entity(username)
        except Exception:
            await event.reply("⚠️ **Не удалось найти пользователя**")
            return
    elif replied:
        user = await replied.get_sender()
    else:
        await event.reply("⚠️ **Команда должна быть ответом на сообщение пользователя или содержать @username**")
        return

    if not await check_admin(event.chat_id, event.sender_id):
        await event.reply("⛔️ **У вас недостаточно прав для выполнения данного действия**")
        return

    # Парсим аргументы
    args = event.pattern_match
    time_str = args.group(4).lower()
    reason = args.group(5) or "Не указана"

    # Парсим время
    duration_match = re.match(r"(\d+)([дмчh])", time_str)
    if not duration_match:
        await event.reply(
            "⚠️ **Неверный формат времени**\n\n"
            "**Примеры:**\n"
            "30м - 30 минут\n"
            "2ч - 2 часа\n"
            "1д - 1 день"
        )
        return

    amount = int(duration_match.group(1))
    unit = duration_match.group(2)

    # Определяем длительность
    if unit in ["м", "m"]:
        duration = timedelta(minutes=amount)
        duration_text = f"{amount} минут"
    elif unit in ["ч", "h"]:
        duration = timedelta(hours=amount)
        duration_text = f"{amount} часов"
    elif unit in ["д", "d"]:
        duration = timedelta(days=amount)
        duration_text = f"{amount} дней"
    else:
        await event.reply("⚠️ **Неверная единица времени**")
        return

    try:
        # Применяем мут
        until_date = datetime.now() + duration
        await bot.edit_permissions(
            event.chat_id,
            user.id,
            until_date=until_date,
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False
        )

        # Формируем сообщение
        mute_text = (
            f"📛 **Пользователю {user.first_name} (`{user.id}`) был выдан мут на {duration_text}!**"
        )

        # Создание кнопок для ответа
        keyboard = [
            [Button.inline("🕐 Снять мут", f"unmute_{user.id}")],
            [Button.url("👓 Чат для оффтопа", "https://t.me/+qVD_2vYoWKNmOWJl+qVD_2vYoWKNmOWJl")],
            [Button.url("📋 Логи", LOG_CHANNEL)]
        ]

        mute_msg = await event.reply(mute_text, buttons=keyboard)

        # Логируем действие
        await send_log(
            "Мут",
            event.sender,
            user,
            duration_text,
            await event.get_chat(),
            reason,
            f"https://t.me/c/{event.chat_id}/{mute_msg.id}"
        )

        # Удаляем сообщение, если команда delmute
        if event.pattern_match.group(2).lower() in ["delmute", "делмут"]:
            await replied.delete()

    except Exception as e:
        await event.reply(f"❌ **Ошибка:** {str(e)}")


@bot.on(events.NewMessage(pattern=r'(?i)^(/|\.)?(unmute|анмут)(@\w+)?'))
async def unmute_handler(event):
    """Обработчик команды размута"""
    # Получаем имя пользователя, если указано
    username = event.pattern_match.group(3)
    replied = await event.get_reply_message() if not username else None

    if username:
        try:
            user = await bot.get_entity(username)
        except Exception:
            await event.reply("⚠️ **Не удалось найти пользователя**")
            return
    elif replied:
        user = await replied.get_sender()
    else:
        await event.reply("⚠️ **Команда должна быть ответом на сообщение пользователя или содержать @username**")
        return

    if not await check_admin(event.chat_id, event.sender_id):
        await event.reply("⛔️ **У вас недостаточно прав для выполнения данного действия**")
        return

    try:
        # Снимаем мут
        await bot.edit_permissions(
            event.chat_id,
            user.id,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
        )

        # Формируем сообщение
        unmute_text = (
            f"🔊 **Пользователь размучен!**\n\n"
            f"👤 **Снял мут:** {event.sender.first_name}"
        )

        keyboard = [
            [Button.url("👑 Чат для оффтопа", "https://t.me/+qVD_2vYoWKNmOWJl")],
            [Button.url("📋 Логи", LOG_CHANNEL)]
        ]

        unmute_msg = await event.reply(unmute_text, buttons=keyboard)

        # Логируем действие
        await send_log(
            "Размут",
            event.sender,
            user,
            "Досрочно",
            await event.get_chat(),
            message_link=f"https://t.me/c/{event.chat_id}/{unmute_msg.id}"
        )

    except Exception as e:
        await event.reply(f"❌ **Ошибка:** {str(e)}")


@bot.on(events.NewMessage(pattern=r'(?i)^(/|\.)?(ban|бан)(@\w+)?\s*(\d+[дмчh])\s*(.*)'))
async def ban_handler(event):
    """Обработчик команды бана"""
    # Получаем имя пользователя, если указано
    username = event.pattern_match.group(3)
    replied = await event.get_reply_message() if not username else None

    if username:
        try:
            user = await bot.get_entity(username)
        except Exception:
            await event.reply("⚠️ **Не удалось найти пользователя**")
            return
    elif replied:
        user = await replied.get_sender()
    else:
        await event.reply("⚠️ **Команда должна быть ответом на сообщение пользователя или содержать @username**")
        return

    if not await check_admin(event.chat_id, event.sender_id):
        await event.reply("⛔️ **У вас недостаточно прав для выполнения данного действия**")
        return

    # Парсим аргументы
    args = event.pattern_match
    time_str = args.group(4).lower()
    reason = args.group(5) or "Не указана"

    # Парсим время
    duration_match = re.match(r"(\d+)([дмчh])", time_str)
    if not duration_match:
        await event.reply(
            "⚠️ **Неверный формат времени**\n\n"
            "**Примеры:**\n"
            "30м - 30 минут\n"
            "2ч - 2 часа\n"
            "1д - 1 день"
        )
        return

    amount = int(duration_match.group(1))
    unit = duration_match.group(2)

    # Определяем длительность
    if unit in ["м", "m"]:
        duration = timedelta(minutes=amount)
        duration_text = f"{amount} минут"
    elif unit in ["ч", "h"]:
        duration = timedelta(hours=amount)
        duration_text = f"{amount} часов"
    elif unit in ["д", "d"]:
        duration = timedelta(days=amount)
        duration_text = f"{amount} дней"

    try:
        # Баним пользователя
        until_date = datetime.now() + duration
        await bot.edit_permissions(
            event.chat_id,
            user.id,
            until_date=until_date,
            view_messages=False
        )

        # Формируем сообщение
        ban_text = (
            f"📛 **Пользователю был выдан бан!**\n\n"
            f"🧸 **Бан выдан:** {user.first_name} (`{user.id}`)\n"
            f"🔮 **Выдал бан:** {event.sender.first_name}\n"
            f"🕐 **Длительность бана:** {duration_text}\n"
            f"📝 **Причина бана:** {reason}"
        )

        keyboard = [
            [Button.inline("🔓 Снять бан пользователю", f"unban_{user.id}")],
            [Button.url("💭 Чат для оффтопа", "https://t.me/+qVD_2vYoWKNmOWJl")],
            [Button.url("📋 Логи", LOG_CHANNEL)]
        ]

        ban_msg = await event.reply(ban_text, buttons=keyboard)

        # Логируем действие
        await send_log(
            "Бан",
            event.sender,
            user,
            duration_text,
            await event.get_chat(),
            reason,
            f"https://t.me/c/{event.chat_id}/{ban_msg.id}"
        )

    except Exception as e:
        await event.reply(f"❌ **Ошибка:** {str(e)}")


@bot.on(events.NewMessage(pattern=r'(?i)^(/|\.)?(unban|разбан)(@\w+)?'))
async def unban_handler(event):
    """Обработчик команды разбана"""
    # Получаем имя пользователя, если указано
    username = event.pattern_match.group(3)
    replied = await event.get_reply_message() if not username else None

    if username:
        try:
            user = await bot.get_entity(username)
        except Exception:
            await event.reply("⚠️ **Не удалось найти пользователя**")
            return
    elif replied:
        user = await replied.get_sender()
    else:
        await event.reply("⚠️ **Команда должна быть ответом на сообщение пользователя или содержать @username**")
        return

    if not await check_admin(event.chat_id, event.sender_id):
        await event.reply("⛔️ **У вас недостаточно прав для выполнения данного действия**")
        return

    try:
        # Разбаниваем пользователя
        await bot.edit_permissions(
            event.chat_id,
            user.id,
            view_messages=True
        )

        # Формируем сообщение
        unban_text = (
            f"💫 **Пользователю снят бан!**\n\n"
            f"👨‍💻 **Пользователь:** {user.first_name} (`{user.id}`)\n"
            f"⛱ **Снял бан:** {event.sender.first_name}"
        )

        keyboard = [
            [Button.url("💭 Чат для оффтопа", "https://t.me/+qVD_2vYoWKNmOWJl")],
            [Button.url("📋 Логи", LOG_CHANNEL)]
        ]

        unban_msg = await event.reply(unban_text, buttons=keyboard)

        # Логируем действие
        await send_log(
            "Разбан",
            event.sender,
            user,
            "Досрочно",
            await event.get_chat(),
            message_link=f"https://t.me/c/{event.chat_id}/{unban_msg.id}"
        )

    except Exception as e:
        await event.reply(f"❌ **Ошибка:** {str(e)}")


@bot.on(events.NewMessage(pattern=r'(?i)^(?:/скам|/sc|/scam)'))
async def scam_command(event):
    logging.info("Команда /sc была вызвана.")
    user_id = event.sender_id

    user_role = db.get_user_role(user_id)
    allowed_roles = [6, 8, 10, 11, 9]  # Роли, которые могут использовать команду

    # Проверка на наличие прав
    if user_role not in allowed_roles and user_id not in OWNER_ID:
        await event.respond("❌ У вас нет прав для использования этой команды")
        return

    args = event.raw_text.split(maxsplit=2)
    if len(args) < 3:
        await event.respond("❌ Используйте: /скам @username/ID *причина*")
        return

    target = args[1]
    reason = args[2].strip('*')

    logging.info(f"Пользователь {user_id} пытается добавить скамера: {target}, причина: {reason}")

    try:
        if target.isdigit():  # Проверка, является ли аргумент числом (ID)
            user = await event.client.get_entity(int(target))
            logging.info(f"Пользователь найден по ID: {user.id}, имя: {user.first_name}")
        else:
            if target.startswith('@'):
                target = target[1:]
            user = await event.client.get_entity(target)
            logging.info(f"Пользователь найден по юзернейму: {user.id}, имя: {user.first_name}")
    except Exception as e:
        await event.respond("❌ Не могу найти пользователя")
        logging.error(f"Ошибка при получении пользователя: {e}")
        return

    # ПРОВЕРКА: Уже ли пользователь в базе скаммеров
    if db.is_scammer(user.id):
        await event.respond(f"❌ Пользователь [{user.first_name}](tg://user/{user.id}) уже находится в базе скаммеров!")
        return

    # Проверка роли пользователя, которого пытаются занести в базу
    target_user_role = db.get_user_role(user.id)
    if target_user_role == 10:
        logging.warning(f"Попытка занести владельца базы (ID: {user.id})")
        await event.respond("❌ Действие не допустимо, вы не можете занести владельца базы!")
        return

    # Генерация уникального идентификатора
    unique_id = str(uuid.uuid4())

    # Добавляем пользователя в базу с описанием
    db.add_user(user.id, user.username)

    # Пытаемся добавить скаммера (с проверкой на дубликат)
    success = db.add_scammer(user.id, reason, user_id, reason, unique_id)

    if not success:
        await event.respond(f"❌ Пользователь [{user.first_name}](tg://user/{user.id}) уже находится в базе скаммеров!")
        return

    # Создаем кнопки с уникальным идентификатором
    buttons = [
        [Button.inline("Скамер ❌", f"mark_scammer_{user.id}_{unique_id}")],
        [Button.inline("Подозрение на скам ⚠️", f"mark_suspect_{user.id}_{unique_id}")],
        [Button.inline("Возможно скаммер ⚠️", f"mark_possible_{user.id}_{unique_id}")],
        [Button.inline("Петух 🐓", f"mark_rooster_{user.id}_{unique_id}")]
    ]

    await event.respond(
        f"⚠️ Выберите роль для пользователя {user.first_name} | 🆔 {user.id}\n\n",
        buttons=buttons,
        parse_mode='md'
    )


# Удаление сообщения с кнопками после нажатия
@bot.on(events.CallbackQuery)
async def callback_handler(callback_event):
    # Удаляем сообщение с кнопками
    await callback_event.delete()


@bot.on(events.CallbackQuery(pattern=r'mark_(scammer|possible|suspect|rooster)_(\d+)_(.+)'))
async def mark_user_handler(event):
    logging.info(f"Обработчик вызван с данными: {event.pattern_match.groups()}")

    role_mapping = {
        'scammer': 3,
        'possible': 2,
        'suspect': 5,
        'rooster': 4
    }

    role_type = event.pattern_match.group(1).decode('utf-8')
    user_id = int(event.pattern_match.group(2))
    reason = event.pattern_match.group(3).strip().decode('utf-8')

    logging.info(f"Попытка изменить роль пользователя {user_id} на {role_type} с причиной: {reason}")

    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Уже ли пользователь имеет роль скаммера
    current_role = db.get_user_role(user_id)
    if current_role in [2, 3, 4, 5]:  # Если уже имеет роль скаммера/подозреваемого
        await event.answer("❌ Этот пользователь уже находится в базе!", alert=True)
        return

    # Получаем роль отправителя
    user_role = db.get_user_role(event.sender_id)
    logging.info(f"Роль пользователя {event.sender_id}: {user_role}")

    # Проверка прав для изменения роли
    if user_role not in [1, 6, 8, 10, 11, 9] and event.sender_id != OWNER_ID:
        await event.answer("⛔ У вас нет прав лол.", alert=True)
        return

    if not reason:
        await event.answer("❌ Причина не может быть пустой!", alert=True)
        return

    # Обновление роли в базе данных
    db.update_role(user_id, role_mapping[role_type])

    # Увеличиваем количество слитых скаммеров для пользователя, который инициировал команду
    current_count = db.get_user_scammers_count(event.sender_id)
    logging.info(f"Текущее количество слитых скаммеров для пользователя {event.sender_id}: {current_count}")

    scammers_slept = current_count + 1
    logging.info(f"Пользователь {event.sender_id} теперь должен иметь {scammers_slept} слитых скаммеров.")

    if not db.update_user_scammers_slept(event.sender_id, scammers_slept):
        logging.error(f"Не удалось обновить количество слитых скаммеров для пользователя {event.sender_id}.")
        await event.answer("Ошибка при обновлении количества слитых скаммеров.", alert=True)
        return

    logging.info(f"Количество слитых скаммеров для пользователя {event.sender_id} успешно обновлено на {scammers_slept}.")

    chat_id = event.chat_id
    await event.client.send_message(
        chat_id,
        message=f"🔥 Вы успешно занесли скаммера! | Скаммеров слито: {scammers_slept}"
    )


@bot.on(events.CallbackQuery(pattern=r'remove_from_db_(\d+)_(.+)'))
async def remove_from_db_handler(event):
    user_id = int(event.pattern_match.group(1))
    role_type = event.pattern_match.group(2).strip()

    logging.info(f"Попытка удалить пользователя ID: {user_id} с ролью: {role_type}")

    user_role = db.get_user_role(event.sender_id)

    # Проверка прав для удаления
    if user_role in [0, 1, 2, 3, 4, 5, 6, 7, 12]:
        await event.answer("❌ Действие не допустимо, у вас нет прав!", alert=True)
        return

    # Проверка, был ли пользователь уже удален
    if not db.is_scammer(user_id):  # Предположим, что функция `is_scammer` возвращает False, если пользователь удален
        await event.answer("ℹ️ Вы уже вынесли пользователя из базы, действие отменено!", alert=True)
        return

    # Снимаем статус скаммера
    if db.remove_scammer_status(user_id):
        await event.answer("✅ Статус был успешно снят!", alert=True)
        await event.client.send_message(event.sender_id, "✅ Статус был успешно снят!")
    else:
        await event.answer("❌ Не удалось снять статус, попробуйте позже.", alert=True)


@bot.on(events.CallbackQuery(pattern=r'report_instruction_(\d+)'))
async def report_instruction_handler(event):
    """Отправляет инструкцию по заносу скаммера в ЛС"""
    target_user_id = int(event.pattern_match.group(1))
    sender_id = event.sender_id

    try:
        # Сначала пытаемся отправить сообщение в ЛС
        instruction_text = """
📋 **ИНСТРУКЦИЯ ПО ЗАНОСУ СКАММЕРА**

Чтобы занести скаммера в базу:

1. **Перейдите в группу жалоб**: @infinityantiscam
2. **Предоставьте доказательства**:
   • Скриншоты переписки
   • Подтверждения платежей
   • Любые другие материалы
3. **Укажите данные скаммера**
4. **Ожидайте рассмотрения** модераторами

🤝 **Спасибо за помощь в борьбе со скамом!**
        """

        await event.answer("📨 Инструкции по апелляции отправлены вам в личные сообщения", alert=True)


        await bot.send_message(
            sender_id,
            instruction_text,
            parse_mode='md'
        )

        await event.answer("✅ Инструкция отправлена в ваши ЛС!", show_alert=False)

    except Exception as e:
        logging.error(f"Ошибка при отправке инструкции в ЛС: {e}")

        # Если не удалось отправить в ЛС, показываем инструкцию прямо в чате
        error_text = """
❌ **Не удалось отправить инструкцию в ЛС**

📋 **Краткая инструкция:**
1. Перейдите в @Huntesreport
2. Предоставьте доказательства скама
3. Укажите данные пользователя
4. Ожидайте рассмотрения

💡 *Чтобы получать полные инструкции, разрешите боту писать вам в ЛС*
        """

        await event.answer("❌ Включите ЛС с ботом!", alert=True)

        # Отправляем краткую инструкцию в текущий чат
        await event.reply(error_text, parse_mode='md')


@bot.on(events.NewMessage(pattern=r'(?i)^(/|\.)?(add) (@\w+) (.+)'))
async def add_reason_handler(event):
    """Обработчик для обновления описания заноса"""
    # Получаем роль отправителя
    user_role = db.get_user_role(event.sender_id)

    # Проверяем права (только админы/владельцы)
    if event.sender_id not in OWNER_ID and user_role not in [6, 8, 10, 11]:
        await event.reply("❌ Только администраторы могут использовать эту команду")
        return

    # Получаем целевого пользователя и текст нового описания
    target_username = event.pattern_match.group(3)  # Юзернейм
    new_description = event.pattern_match.group(4).strip()  # Новое описание

    # Проверка формата юзернейма
    if not target_username.startswith('@'):
        await event.reply("❌ Юзернейм должен начинаться с '@'.")
        return

    # Проверка, что новое описание не пустое
    if not new_description:
        await event.reply("❌ Описание не может быть пустым.")
        return

    # Логируем информацию о попытке получения пользователя
    logging.info(f"Попытка получить пользователя по юзернейму: {target_username}")

    try:
        target = await event.client.get_entity(target_username)
        logging.info(f"Пользователь найден: {target.first_name} (ID: {target.id})")
    except Exception as e:
        logging.error(f"Ошибка при получении пользователя {target_username}: {str(e)}")
        await event.reply("❌ Не могу найти указанного пользователя. Проверьте правильность юзернейма.")
        return

    # Логируем информацию о целевом пользователе и новом описании
    logging.info(
        f"Попытка обновления описания для пользователя {target.first_name} ({target.id}) с новым описанием: {new_description}")

    # Обновляем описание в базе данных
    try:
        # Обновляем описание (предполагается, что эта функция обновляет поле description)
        db.update_description(target.id, new_description)  # Убедитесь, что эта функция обновляет поле description
        logging.info(
            f"Описание для пользователя {target.first_name} ({target.id}) успешно обновлено на: {new_description}")
        await event.reply(
            f"✅ Описание для пользователя [{target.first_name}](tg://user/{target.id}) обновлено: {new_description}",
            parse_mode='md')
    except Exception as e:
        logging.error(f"Ошибка при обновлении описания для пользователя {target.id}: {str(e)}")
        await event.reply(f"❌ Произошла ошибка при обновлении описания: {str(e)}")


@bot.on(events.NewMessage(pattern=r'(?i)^(/add1) (@\w+) (.+)'))
async def add_additional_reason_handler(event):
    """Обработчик для добавления дополнительного описания"""
    # Получаем роль отправителя
    user_role = db.get_user_role(event.sender_id)

    # Проверяем права (только админы/владельцы)
    if event.sender_id not in OWNER_ID and user_role not in [6, 8, 10, 11]:
        await event.reply("❌ Только администраторы могут использовать эту команду")
        return

    # Получаем целевого пользователя и текст дополнительного описания
    target_username = event.pattern_match.group(2)
    additional_reason_text = event.pattern_match.group(3).strip()

    try:
        target = await event.client.get_entity(target_username)
    except Exception as e:
        await event.reply("❌ Не могу найти указанного пользователя")
        return

    # Добавляем дополнительное описание в базе данных
    db.add_additional_reason(target.id, additional_reason_text)

    await event.reply(
        f"✅ Дополнительное описание для пользователя [{target.first_name}](tg://user/{target.id}) добавлено: {additional_reason_text}",
        parse_mode='md')


@bot.on(events.NewMessage(pattern=r'/траст|!trust'))
async def trust_command(event):
    sender = await event.get_sender()

    # Проверка роли: разрешено гарантам и создателям
    if db.get_user_role(sender.id) not in [1, 10]:
        await event.reply(
            "**⚠️ Отказано в доступе!**\n\n"
            f"**👤 Пользователь:** [{sender.first_name}](tg://user/{sender.id})\n"
            "**📛 Причина:** Недостаточно прав\n"
            "**ℹ️ Информация:** Выдавать траст могут только гаранты и создатель\n"
            "[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)",
            parse_mode='md',
            link_preview=True
        )
        return

    # Получаем целевого пользователя
    target = await get_target_user(event)
    if not target:
        return

    # Получаем ID гаранта (того, кто выдает роль)
    granted_by_username = sender.username if sender.username else f"ID: {sender.id}"

    # Проверяем, является ли целевой пользователь владельцем, кодером, стажером, гарантом, президентом, админом или директором
    target_role = db.get_user_role(target.id)
    if target_role in [6, 7, 8, 9, 10, 11, 12]:
        await event.reply(
            "**❌ Ошибка!**\n\n"
            "**📛 Причина:** Нельзя выдавать траст владельцу, кодеру, стажеру, гаранту, президенту, админу или директору.\n"
            f"**📝 Текущая роль:** {ROLES[target_role]['name']}",
            parse_mode='md'
        )
        return

    # Блокируем операцию выдачи траста
    async with db.lock:  # Используем блокировку правильно
        # Проверяем, есть ли пользователь в базе
        user_role = db.get_user_role(target.id)
        if user_role is not None and user_role > 0:
            await event.reply(
                "**❌ Ошибка!**\n\n"
                "**📛 Причина:** У пользователя уже есть роль в базе.\n"
                f"**📝 Текущая роль:** {ROLES[user_role]['name']}",
                parse_mode='md'
            )
            return

        # Устанавливаем роль "Проверен гарантом" с указанием ID гаранта
        db.update_role(target.id, 12, granted_by_id=sender.id)  # Передаем ID гаранта

        # Сохраняем информацию о трасте в таблицу trust
        db.add_grant(target.id, sender.id)  # Добавляем запись о гарантии

    # Отправляем сообщение об успешной выдаче траста
    await event.reply(
        f"**✅ Траст успешно выдан!**\n\n"
        f"**👤 Получатель:** [{target.first_name}](tg://user/{target.id})\n"
        f"**👮 Выдал:** [{sender.first_name}](tg://user/{sender.id})\n"
        f"💙 Репутация: Проверен(а) гарантом {granted_by_username} ✅",
        parse_mode='md'
    )


async def get_target_user(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        return await event.client.get_entity(replied.sender_id)
    else:
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply(
                "**❌ Ошибка использования команды!**\n\n"
                "**✏️ Правильное использование:**\n"
                "• `/trust` (ответом на сообщение)\n"
                "• `/trust @username`\n"
                "• `/trust ID`",
                parse_mode='md'
            )
            return None
        try:
            return await event.client.get_entity(args[1])
        except:
            await event.reply(
                "**❌ Ошибка!**\n\n"
                "**📛 Причина:** Не удалось найти пользователя\n"
                "**💡 Совет:** Проверьте правильность указанного юзернейма/ID",
                parse_mode='md'
            )
            return None


@bot.on(events.NewMessage(pattern=r'/untrust|/антраст|-антраст'))
async def untrust_command(event):
    sender = await event.get_sender()

    # Проверяем права (гарант, создатель, владельцы или кодер)
    sender_role = db.get_user_role(sender.id)
    if db.get_user_role(sender.id) not in [1, 10]:
        await event.reply(
            "**⚠️ Отказано в доступе!**\n\n"
            f"**👤 Пользователь:** [{sender.first_name}](tg://user/{sender.id})\n"
            "**📛 Причина:** Недостаточно прав\n"
            "**ℹ️ Информация:** Снимать траст могут только гаранты, создатель и владельцы\n"
            "[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)",
            parse_mode='md',
            link_preview=True
        )
        return

    # Получаем целевого пользователя
    if event.is_reply:
        replied = await event.get_reply_message()
        target = await event.client.get_entity(replied.sender_id)
    else:
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply(
                "**❌ Ошибка использования команды!**\n\n"
                "**✏️ Правильное использование:**\n"
                "• `/untrust` (ответом на сообщение)\n"
                "• `/untrust @username`\n"
                "• `/untrust ID`",
                parse_mode='md'
            )
            return

        try:
            target = await event.client.get_entity(args[1])
        except:
            await event.reply(
                "**❌ Ошибка!**\n\n"
                "**📛 Причина:** Не удалось найти пользователя\n"
                "**💡 Совет:** Проверьте правильность указанного юзернейма/ID",
                parse_mode='md'
            )
            return

    # Проверяем, есть ли у пользователя траст
    if db.get_user_role(target.id) != 12:
        await event.reply(
            "**❌ Ошибка!**\n\n"
            "**📛 Причина:** У пользователя нет траста",
            parse_mode='md'
        )
        return

    # Снимаем траст (устанавливаем стандартную роль)
    db.update_role(target.id, 0)

    await event.reply(
        "**✅ Траст успешно снят!**\n\n"
        f"**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})\n"
        f"**👮 Снял:** [{sender.first_name}](tg://user/{sender.id})",
        parse_mode='md'
    )


@bot.on(events.NewMessage(pattern=r'\+премиум'))
async def add_premium(event):
    # Проверяем права (только создатель, кодер или владельцы)
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.reply("❌ У вас нет прав для выполнения этого действия!")
        return

    try:
        # Получаем целевого пользователя
        if event.is_reply:
            replied = await event.get_reply_message()
            target = await event.client.get_entity(replied.sender_id)
            duration = event.raw_text.split()[-1].lower()
        else:
            args = event.raw_text.split()
            if len(args) != 2:
                await event.reply("**❌ Использование:**\n`+премиум @username 1д`")
                return

            try:
                if args[1].isdigit():
                    target = await event.client.get_entity(int(args[1]))
                else:
                    target = await event.client.get_entity(args[1])
            except:
                await event.reply("**❌ Не удалось найти пользователя!**")
                return

        # Парсим длительность
        amount = int(duration[:-1])
        unit = duration[-1]

        if unit == 'м':
            delta = timedelta(minutes=amount)
            time_str = f"{amount} минут"
        elif unit == 'ч':
            delta = timedelta(hours=amount)
            time_str = f"{amount} часов"
        elif unit == 'д':
            delta = timedelta(days=amount)
            time_str = f"{amount} дней"
        elif unit == 'г':
            delta = timedelta(days=amount * 365)
            time_str = f"{amount} лет"
        else:
            await event.reply("**❌ Неверный формат времени!**")
            return

        expiry_date = (datetime.now() + delta).strftime("%Y-%m-%d %H:%M:%S")

        # Используем новый метод для добавления или обновления премиум статуса
        db.add_or_update_premium_user(target.id, expiry_date)

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                target.id,
                "**🎉 Вам выдан премиум доступ!**",
                buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam")
            )
        except:
            pass

        await event.reply(
            f"**✅ Премиум успешно выдан!**\n\n"
            f"**👤 Получатель:** [{target.first_name}](tg://user/{target.id})\n"
            f"**⏱ Длительность:** {time_str}",
            buttons=[Button.inline("❌ Снять премиум", f"remove_premium_{target.id}")],
            parse_mode='md'
        )

    except Exception as e:
        await event.reply(f"**❌ Ошибка:** `{str(e)}`")


# Обработчик команды -премиум
@bot.on(events.NewMessage(pattern=r'-премиум'))
async def remove_premium_command(event):
    # Проверяем права (только создатель, кодер или владельцы)
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.reply("❌ У вас нет прав для выполнения этого действия!")
        return

    try:
        # Получаем целевого пользователя
        if event.is_reply:
            replied = await event.get_reply_message()
            target = await event.client.get_entity(replied.sender_id)
        else:
            args = event.raw_text.split()
            if len(args) != 2:
                await event.reply("**❌ Использование:**\n`-премиум @username` или `-премиум ID`")
                return

            try:
                if args[1].isdigit():
                    target = await event.client.get_entity(int(args[1]))
                else:
                    target = await event.client.get_entity(args[1])
            except Exception as e:
                await event.reply("**❌ Не удалось найти пользователя!**")
                return

        # Проверяем наличие премиум статуса
        if db.get_premium_expiry(target.id):
            db.remove_premium(target.id)

            # Уведомляем пользователя о снятии премиума
            try:
                await bot.send_message(
                    target.id,
                    "**🕵️‍♂️ Ваш премиум статус был снят.**",
                    buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam")
                )
            except Exception as e:
                pass

            await event.reply(
                f"**✅ Премиум успешно снят!**\n\n"
                f"**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})",
                parse_mode='md'
            )
        else:
            await event.reply("❌ У пользователя нет премиум статуса!")

    except Exception as e:
        await event.reply(f"**❌ Ошибка:** `{str(e)}`")


# Обработчик кнопки снятия премиума
@bot.on(events.CallbackQuery(pattern=r'remove_premium_(\d+)'))
async def remove_premium_button(event):
    # Проверяем права
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.answer("❌ У вас нет прав для выполнения этого действия!", alert=True)
        return

    user_id = int(event.data.decode().split('_')[2])

    if db.get_premium_expiry(user_id):
        db.remove_premium(user_id)

        try:
            target = await event.client.get_entity(user_id)

            # Отправляем уведомление пользователю
            try:
                await bot.send_message(
                    user_id,
                    "**🕵️‍♂️ Шо те лох премиум сняли?.**",
                    buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam")
                )
            except:
                pass

            await event.edit(
                f"**✅ Премиум успешно снят!**\n\n"
                f"**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})",
                buttons=None,
                parse_mode='md'
            )

        except Exception as e:
            await event.edit(f"**❌ Ошибка:** `{str(e)}`")
    else:
        await event.answer("❌ У пользователя нет премиума!", alert=True)


# Обработчик команды /untrust
@bot.on(events.NewMessage(pattern=r'/untrust|/антраст|-антраст'))
async def untrust_command(event):
    sender = await event.get_sender()

    # Проверяем права (гарант, создатель, владельцы или кодер)
    sender_role = db.get_user_role(sender.id)
    if sender_role != 1 and sender.id not in OWNER_ID and sender_role not in [10, 11]:
        await event.reply(
            "**⚠️ Отказано!**\n\n"
            f"**👤 Пользователь:** [{sender.first_name}](tg://user/{sender.id})\n"
            "**📛 Причина:** У тя прав нету пон?\n"
            "**ℹ️ Информация:** Снимать траст могут только гаранты, создатель и владельцы\n"
            "[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)",
            parse_mode='md',
            link_preview=True
        )
        return

    # Получаем целевого пользователя
    if event.is_reply:
        replied = await event.get_reply_message()
        target = await event.client.get_entity(replied.sender_id)
    else:
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply(
                "**❌ Ошибка использования команды!**\n\n"
                "**✏️ Правильное использование:**\n"
                "• `/untrust` (ответом на сообщение)\n"
                "• `/untrust @username`\n"
                "• `/untrust ID`",
                parse_mode='md'
            )
            return

        try:
            target = await event.client.get_entity(args[1])
        except:
            await event.reply(
                "**❌ ну, ошибочка вышла):**\n\n"
                "**📛 Причина:** Не удалось найти пользователя\n"
                "**💡 Совет:** Дебик, правильно ник введи или айди, заебали уже честно.",
                parse_mode='md'
            )
            return

    # Проверяем, есть ли у пользователя траст
    if db.get_user_role(target.id) != 12:
        await event.reply(
            "**❌ Ну не плач только ошибочка получилась**\n\n"
            "**📛 Причина:** Его нет в базе даун..",
            parse_mode='md'
        )
        return

    # Снимаем траст (устанавливаем стандартную роль)
    await db.update_role(target.id, 0)

    await event.reply(
        "**✅ Траст успешно снят!, плаки плаки ):**\n\n"
        f"**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})\n"
        f"**👮 Снял:** [{sender.first_name}](tg://user/{sender.id})",
        parse_mode='md'
    )


# Команда /гаранты
@bot.on(events.NewMessage(pattern='/гаранты'))
async def list_online_garants(event):
    await event.respond("Ищу онлайн гарантов...")

    # Получаем всех гарантов из базы (роль 1)
    try:
        garants = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 1')]
        logging.info(f"Найдено {len(garants)} гарантов с ролью 1.")
    except Exception as e:
        logging.error(f"Ошибка при получении гарантов из базы: {e}")
        await event.respond("Не удалось получить список гарантов из базы данных.")
        return

    online_garants = []

    for uid in garants:
        try:
            user = await bot.get_entity(uid)
            logging.info(f"Проверяем пользователя: {user.id}, Имя: {user.first_name}, Статус: {user.status}")

            # Проверяем статус пользователя
            if user.status is None:
                online_garants.append(user)
                logging.info(f"Пользователь {user.first_name} ({user.id}) онлайн (нет статуса).")
            elif user.status == "online":
                online_garants.append(user)
                logging.info(f"Пользователь {user.first_name} ({user.id}) онлайн.")
            elif isinstance(user.status, UserStatusRecently):
                # Учитываем пользователей с состоянием Recently как онлайн
                online_garants.append(user)
                logging.info(f"Пользователь {user.first_name} ({user.id}) был в сети недавно.")
            else:
                logging.info(f"Пользователь {user.first_name} ({user.id}) не онлайн. Статус: {user.status}")
        except Exception as e:
            logging.error(f"Ошибка при получении пользователя {uid}: {e}")
            continue

    if not online_garants:
        await event.respond("На данный момент онлайн гарантов нет ⛔")
        logging.info("Нет онлайн гарантов.")
        return

    # Формируем текст ответа
    text = "📊 Вот наш список онлайн гарантов:\n"
    buttons = []

    for user in online_garants:
        buttons.append([Button.inline(f"🛡️ {user.first_name}", f"check_{user.id}")])

    await event.respond(text, buttons=buttons, parse_mode='markdown', link_preview=True)
    logging.info("Список онлайн гарантов успешно отправлен.")

@bot.on(events.CallbackQuery(data=b"top_trainees"))
async def top_trainees_handler(event):
    try:
        await bot.delete_messages(event.chat_id, bot.stat_message_id)
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    try:
        top_trainees = db.cursor.execute('''
            SELECT user_id, username, scammers_slept 
            FROM users 
            WHERE role_id = 6 
            ORDER BY scammers_slept DESC 
            LIMIT 10
        ''').fetchall()

        if not top_trainees:
            msg = await event.respond("📭 Список стажеров пока пуст!",
                                      buttons=Button.inline("↩Вернуться", b"return_to_stats"))
            bot.last_message_id = msg.id
            return

        response = "🏆 Топ 10 стажеров по слитым скаммерам:\n\n"
        for i, (user_id, username, count) in enumerate(top_trainees, 1):
            # Используем username или user_id, если username отсутствует
            user_link = f"[{username or f'ID:{user_id}'}](tg://user?id={user_id})"
            response += f"{i}. {user_link} — 🚫 {count} скаммеров\n"

        msg = await event.respond(response,
                                  parse_mode='Markdown',
                                  buttons=Button.inline("↩Вернуться", b"return_to_stats"))
        bot.last_message_id = msg.id

    except Exception as e:
        await event.respond(f"⚠️ Ошибка: {str(e)}", buttons=Button.inline("↩Вернуться", b"return_to_stats"))
    finally:
        db.close()


@bot.on(events.CallbackQuery(data=b"return_to_stats"))
async def return_to_stats_handler(event):
    try:
        # Удаляем сообщение с топом стажёров
        await bot.delete_messages(event.chat_id, event.message_id)

        # Возвращаем пользователя к сообщению со статистикой
        user = await event.get_sender()

        # Основные статистические данные
        total_checks = db.cursor.execute('SELECT SUM(check_count) FROM users').fetchone()[0] or 0
        scammers_count = db.cursor.execute('SELECT COUNT(*) FROM scammers').fetchone()[0]
        total_users = db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]

        # Статистика по ролям
        roles_stats = {
            'admins': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 7').fetchone()[0],
            'guarantors': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 1').fetchone()[0],
            'verified': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 12').fetchone()[0],
            'trainees': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 6').fetchone()[0]
        }

        # Формируем сообщение со статистикой
        text = f"""🔍 {user.first_name}, вот текущая статистика бота:
[⠀](https://i.ibb.co/Fzpqd0K/IMG-3735.jpg)
🚫 Скаммеров в базе: {scammers_count}
👥 Пользователей бота: {total_users}

⚖️ Админов: {roles_stats['admins']}
💎 Гарантов: {roles_stats['guarantors']}
✅ Проверенных: {roles_stats['verified']}
👨‍🎓 Стажеров: {roles_stats['trainees']}

🔎 Всего проверок: {total_checks}
⏳ Последняя проверка: {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""

        # Создаем кнопки
        buttons = [
            [Button.inline("🏆 Топ Стажеров", b"top_trainees")],
            [Button.inline("😎 Топ Активных", b"top_day")]
        ]

        stat_message = await event.respond(text, parse_mode='md', link_preview=True, buttons=buttons)
        bot.stat_message_id = stat_message.id

    except Exception as e:
        await event.respond(f"⚠️ Ошибка: {str(e)}")
    finally:
        db.close()


@bot.on(events.CallbackQuery(data=b"top_day"))
async def top_day_handler(event):
    try:
        await bot.delete_messages(event.chat_id, bot.stat_message_id)
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    try:
        # Проверяем существование таблицы messages
        db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if not db.cursor.fetchone():
            msg = await event.respond("⚠️ Таблица сообщений ещё не создана. Активность не отслеживается.",
                                      buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        # ИСПРАВЛЕННЫЙ ЗАПРОС - используем message_id вместо id
        top_users = db.cursor.execute('''
            SELECT u.user_id, u.username, COUNT(m.message_id) as count
            FROM users u
            JOIN messages m ON u.user_id = m.user_id
            WHERE m.timestamp >= datetime('now', '-1 day')
            GROUP BY u.user_id
            ORDER BY count DESC
            LIMIT 10
        ''').fetchall()

        if not top_users:
            msg = await event.respond("📭 Пока нет активности за последние 24 часа!",
                                      buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return

        response = "😎 Топ 10 активных пользователей за 24 часа:\n\n"
        for i, (user_id, username, count) in enumerate(top_users, 1):
            user_link = f"[{username or f'ID:{user_id}'}](tg://user?id={user_id})"
            response += f"{i}. {user_link} — ✉️ {count} сообщений\n"

        msg = await event.respond(response, buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id

    except sqlite3.Error as e:
        await event.respond(f"⚠️ Ошибка базы данных: {str(e)}", buttons=Button.inline("↩Скрыть", b"hide_message"))
    except Exception as e:
        await event.respond(f"⚠️ Произошла ошибка: {str(e)}", buttons=Button.inline("↩Скрыть", b"hide_message"))



@bot.on(events.CallbackQuery(data=b"hide_message"))
async def hide_message_handler(event):
    try:
        await event.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")


@bot.on(events.NewMessage(pattern="🚫 Слить скаммера!"))
async def report_scammer(event):
    if not event.is_private:
        return  # Игнорируем, если не в ЛС

    keyboard = types.KeyboardButtonUrl(text="🚨 Отправить жалобу", url="https://t.me/infinityantiscam")
    await event.respond(
        """🔥 Вы хотите слить скаммера? 🔥

⚡️ Лучшее решение:
• Нажмите кнопку "🚨 Отправить жалобу"
• Наш персонал примет меры в течение некоторого времени, просто скиньте пруфы!

🔒 Как избежать скама?:
1. ✅ Всегда проверяйте пользователя через /check
2. ✅ Используйте только официальных гарантов
3. ✅ Требуйте подтверждающие скриншоты
4. ✅ При малейших сомнениях - отменяйте сделку

📛 Помните: 95% скама можно избежать, следуя этим правилам!
[⠀](https://i.ibb.co/bj4g7h3y/photo-2025-04-17-17-44-19-3.jpg)""",
        parse_mode='md',
        link_preview=True,
        buttons=keyboard
    )


@bot.on(events.NewMessage(pattern="✅ Гаранты базы"))
async def list_garants(event):
    if not event.is_private:
        return

    # Получаем всех гарантов из базы
    try:
        garants = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 1')]
    except Exception as e:
        return

    if not garants:
        # ИЗМЕНЕНО: было await loading_message.edit(), теперь await event.respond()
        await event.respond("На данный момент Гарантов нету ⛔")
        return

    # Формируем текст с актуальным списком
    text = f"""💢 Актуальный список гарантов infinity
━━━━━━━━━━━━━━
• Всего: {len(garants)}
━━━━━━━━━━━━━━
💡 Если хотите стать гарантом, пройдите набор!
[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)"""

    buttons = []

    for uid in garants:
        try:
            user = await bot.get_entity(uid)
            buttons.append([Button.inline(f"🛡️ {user.first_name}", f"check_{uid}")])
        except Exception as e:
            print(f"Ошибка при получении данных пользователя {uid}: {e}")
            continue

    # УДАЛЕНО: await loading_message.delete()
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)


@bot.on(events.NewMessage(pattern="👨‍🎓 Волонтёры базы"))
async def list_volunteers(event):
    if not event.is_private:
        return

    # УДАЛЕНО: Весь блок прогресс-загрузки
    # loading_message = await event.respond("🔄 Загрузка\n▰▱▱▱▱▱▱▱▱▱ 10%")
    # progress_steps = [
    #     (20, "▰▰▱▱▱▱▱▱▱▱"),
    #     (99, "▰▰▰▰▰▰▰▰▰▱")
    # ]
    # for percent, bar in progress_steps:
    #     await asyncio.sleep(0.3)
    #     await loading_message.edit(f"🔄 Загрузка\n{bar} {percent}%")

    # Получаем всех волонтеров (роли 6-10)
    volunteers = []
    for role_id in [6, 7, 8, 9, 10]:
        volunteers.extend(
            [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = ?', (role_id,))])

    if not volunteers:
        # ИЗМЕНЕНО: было await loading_message.edit(), теперь await event.respond()
        await event.respond("На данный момент Волонтёров нету ⛔")
        return

    # Формируем текст с актуальным списком
    text = f"""🤝 Актуальный список волонтёров infinity
━━━━━━━━━━━━━━
• Всего: {len(volunteers)}
━━━━━━━━━━━━━━
💡 Если вы хотите стать волонтёром базы, просто пройдите набор!
[⠀](https://i.ibb.co/rGKnW46r/photo-2025-04-17-17-44-19.jpg)"""

    buttons = []

    for uid in volunteers:
        try:
            user = await bot.get_entity(uid)
            role_id = db.get_user_role(uid)
            role_name = ROLES[role_id]["name"]
            buttons.append([Button.inline(f"{role_name} {user.first_name}", f"check_{uid}")])
        except:
            continue

    # УДАЛЕНО: await loading_message.delete()
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)


@bot.on(events.NewMessage(pattern="🔰 Проверенные пользователи"))
async def list_verified_users(event):
    if not event.is_private:
        return

    # УДАЛЕНО: Весь блок прогресс-загрузки
    # loading_message = await event.respond("🔄 Загрузка\n▰▱▱▱▱▱▱▱▱▱ 10%")
    # progress_steps = [
    #     (20, "▰▰▱▱▱▱▱▱▱▱"),
    #     (99, "▰▰▰▰▰▰▰▰▰▱")
    # ]
    # for percent, bar in progress_steps:
    #     await asyncio.sleep(0.3)
    #     await loading_message.edit(f"🔄 Загрузка\n{bar} {percent}%")

    # Получаем всех проверенных пользователей (роль 12)
    verified_users = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 12')]

    if not verified_users:
        # ИЗМЕНЕНО: было await loading_message.edit(), теперь await event.respond()
        await event.respond("На данный момент проверенных пользователей нет ⛔")
        return

    text = "📊 Вот наш список проверенных пользователей:\n"
    buttons = []

    for uid in verified_users:
        try:
            user = await bot.get_entity(uid)
            buttons.append([Button.inline(f"✅ {user.first_name}", f"check_{uid}")])
        except:
            continue

    # УДАЛЕНО: await loading_message.delete()
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)


@bot.on(events.NewMessage(pattern="🔓 Премиум"))
async def premium_info(event):
    # УДАЛЕНО: Весь блок прогресс-загрузки
    # loading_message = await event.respond("🔄 Загрузка\n▰▱▱▱▱▱▱▱▱▱ 10%")
    # progress_steps = [
    #     (20, "▰▰▱▱▱▱▱▱▱▱"),
    #     (99, "▰▰▰▰▰▰▰▰▰▱")
    # ]
    # for percent, bar in progress_steps:
    #     await asyncio.sleep(0.2)
    #     await loading_message.edit(f"🔄 Загрузка\n{bar} {percent}%")

    # Финальное сообщение
    final_image = "https://i.ibb.co/bMbQc9c0/photo-2025-06-01-12-01-48.jpg"
    text = (
        f"Откройте уникальные возможности: [ ](https://i.ibb.co/bMbQc9c0/photo-2025-06-01-12-01-48.jpg)\n\n"
        "• Установить себе кастомное фото\n"
        "• Поставить ссылку на свой канал\n"
        "• Получать уведомления о проверках\n"
        "Все эти фишки входят в infinity Premium"
    )

    buttons = [
        [Button.url("💰 Оплата", "https://t.me/rewylerss")],
        [Button.inline("↩ Скрыть", b"hide_message")]
    ]

    # УДАЛЕНО: await loading_message.delete()
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)


@bot.on(events.NewMessage(pattern="🎭 Профиль"))
async def my_profile(event):
    if not event.is_private:
        await event.delete()
        return

    # УДАЛЕНО: Весь блок прогресс-загрузки
    # loading_message = await event.respond("🔄 Загрузка 10%\n▰")
    # progress_steps = [20, 99]
    # progress_bars = ["▰", "▰▰▰▰▰▰▰▰▰▰"]
    # for i, (step, bar) in enumerate(zip(progress_steps, progress_bars)):
    #     await asyncio.sleep(1)
    #     await loading_message.edit(f"🔄 Загрузка {step}%\n{bar}")

    # Получаем user_id из события
    user_id = event.sender_id

    # Получаем данные пользователя из базы
    user_data = db.get_user(user_id)
    if user_data is None:
        # ИЗМЕНЕНО: было await loading_message.edit(), теперь await event.respond()
        await event.respond("❌ Не удалось найти ваши данные в базе.")
        return

    role_id = user_data[2]
    role_info = ROLES[role_id]

    custom_photo = user_data[8] if user_data else None
    preview_url = custom_photo if custom_photo else role_info['preview_url']

    # Получаем объект пользователя
    user = await event.get_sender()

    checks_count = db.get_check_count(user_id)

    # Определяем количество слитых скамеров
    scammers_slept = 0
    if role_id in [6, 7, 8, 9, 10, 13]:
        scammers_slept = \
            db.cursor.execute('SELECT COUNT(*) FROM scammers WHERE reporter_id = ?', (user_id,)).fetchone()[0]

    # Получаем статус премиума
    premium_expiry = db.get_premium_expiry(user_id)
    is_premium = premium_expiry is not None and datetime.strptime(premium_expiry, "%Y-%m-%d %H:%M:%S") > datetime.now()
    premium_status = "✅" if is_premium else "❌"

    # Определяем текст кнопки для кастомного изображения
    custom_button_text = "🎆 Снять кастомное изображение" if custom_photo else "🎆 Установить кастомку"
    custom_callback_data = "remove_custom" if custom_photo else "custom_soon"

    profile_text = f"""
👤 **Профиль пользователя** [{user.first_name}](tg://user/{user_id})

📛 **Роль:** {role_info['name']}
🆔 **ID:** {user_id}[ ](https://i.ibb.co/ycyPRXrb/photo-2025-04-17-17-44-20-2.jpg)
👑 **infinity Premium:** {premium_status}
🔍 **Проверок:** {checks_count}
"""

    # УДАЛЕНО: await loading_message.delete()
    await event.respond(
        profile_text,
        buttons=[
            [Button.inline("🔎 Проверить себя", "check_soon"),
             Button.inline("🎨 Тема проверки", "themes_soon")],
            [Button.inline("📢 Канал", "channel_soon"),
             Button.inline("🌍 Страна", "country_soon")],
            [Button.inline(custom_button_text, custom_callback_data)]
        ],
        parse_mode='md',
        link_preview=True
    )


# Обработчик команды /bt (показать кнопки)
@bot.on(events.NewMessage(pattern='/bt'))
async def show_buttons(event):
    # Проверяем права (только создатель, кодер или владельцы)
    user_id = event.sender_id
    user_role = db.get_user_role(user_id)

    if user_id not in OWNER_ID and user_role not in [10, 11]:
        await event.respond("❌ У вас нет прав для использования этой команды")
        return

    await event.respond(
        "Кнопки активированы ✅",
        buttons=main_buttons
    )


# Обработчик команды /unbt (убрать кнопки)
@bot.on(events.NewMessage(pattern='/unbt'))
async def remove_buttons(event):
    # Проверяем права (только создатель, кодер или владельцы)
    user_id = event.sender_id
    user_role = db.get_user_role(user_id)

    if user_id not in OWNER_ID and user_role not in [10, 11]:
        await event.respond("❌ У вас нет прав для использования этой команды")
        return

    await event.respond(
        "Кнопки деактивированы ✅",
        buttons=[]  # Пустой список кнопок
    )


@bot.on(events.NewMessage(pattern='/оффтоп'))
async def handle_offtopic_command(event):
    # Проверяем права пользователя
    allowed_roles = [1, 6, 7, 8, 9, 10]  # 1 - владелец, 6 - стажер, 7 - админ, 8 - директор, 9 - президент
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in allowed_roles:
        await event.respond("❌ У вас нет прав для использования этой команды.")
        return

    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
        try:
            # Выдаем мут на 30 минут
            await bot.edit_permissions(
                event.chat_id,
                target_user.id,
                until_date=time.time() + 1800,
                send_messages=False
            )
            # Формируем текст ответа
            mute_message = (
                f"{target_user.first_name} выдан мут на 30 минут\n\n"
                f"Причина: Оффтоп\n\n"
                f"общайтесь в нашем чате для оффтопа☕"
            )

            # Создаем кнопку
            keyboard = [
                [Button.url("Перейти", "https://t.me/+qVD_2vYoWKNmOWJl")]
            ]

            # Отправляем сообщение с кнопкой
            await event.respond(mute_message, buttons=keyboard)

            # Удаляем сообщение, на которое был дан ответ
            await replied.delete()
        except Exception as e:
            await event.respond(f"❌ Не могу выдать мут: {e}")
    else:
        await event.respond("❌ Ответьте на сообщение пользователя, которому нужно выдать мут.")


# Обработчик сообщений для проверки мута
@bot.on(events.NewMessage())
async def check_message(event):
    user_id = event.sender_id

    # Проверка, замучен ли пользователь
    if user_id in muted_users:
        expiry_time = muted_users[user_id]
        if time.time() < expiry_time:
            await event.delete()  # Удаляем сообщение
            await event.respond("❌ Вы замучены и не можете отправлять сообщения.")
            return


joined_users_cache = set()


@bot.on(events.ChatAction)
async def handle_chat_join(event):
    if not (event.user_joined or event.user_added):
        return  # Не обрабатываем другие действия

    user = await event.get_user()
    user_id = user.id

    # Исключаем ботов
    if user.bot:
        return

    # Кэш от повторов
    if user_id in joined_users_cache:
        return
    joined_users_cache.add(user_id)
    asyncio.create_task(remove_from_cache_later(user_id))

    # Получение роли
    user_role = db.get_user_role(user_id)
    image_url = "https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg"

    # Для кодера
    if user_role == 11:
        buttons = [[Button.inline("🤗", "welcome_coder")]]
        text = f"""
☕ Добро пожаловать! [{user.first_name}](tg://user?id={user.id})

Добро пожаловать!!😊

[🤗]({image_url})
"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

    # Для персонала
    elif user_role in [6, 7, 8, 9, 10]:
        text = f"""
☕ Добро пожаловать! [{user.first_name}](tg://user?id={user.id})

[🤗]({image_url})
"""
        await event.respond(text, parse_mode='md', link_preview=True)

    # Проверенный гарантом
    elif user_role == 12:
        text = f"""
🔥 К чату присоединился человек, проверенный гарантом Grand

[🤗]({image_url})
"""
        await event.respond(text, parse_mode='md', link_preview=True)

    # Скамер
    elif user_role == 3:
        buttons = [[Button.inline("ЗАБАНИТЬ ⛔", f"ban_{user.id}")]]
        text = f"""
⚠️ К чату присоединился [{user.first_name}](tg://user?id={user.id}) **Скаммер**!

Не доверяйте этому человеку.

[🤗]({image_url})
"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

    # Подозреваемый в скаме
    elif user_role in [2, 4, 5]:
        buttons = [[Button.inline("ЗАБАНИТЬ ⛔", f"ban_{user.id}")]]
        text = f"""
⚠️ К чату присоединился [{user.first_name}](tg://user?id={user.id}) с высоким шансом скама!

Вероятность скама: {ROLES[user_role]['scam_chance']}%

[🤗]({image_url})
"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

    # Неизвестный пользователь
    else:
        buttons = [[Button.inline("🤗", "welcome")]]
        text = f"""
👋 Добро пожаловать! [{user.first_name}](tg://user?id={user.id})

[🤗](https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg)
"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

    # Проверка мута
    if user_id in muted_users:
        expiry_time = muted_users[user_id]
        if time.time() < expiry_time:
            await bot.edit_permissions(event.chat_id, user_id, view_messages=False)
        else:
            del muted_users[user_id]


# Очистка кэша
async def remove_from_cache_later(user_id, delay=600):
    await asyncio.sleep(delay)
    joined_users_cache.discard(user_id)


# Обработчик кнопки "Добавить в группу"
@bot.on(events.CallbackQuery(pattern='add_group'))
async def add_group_handler(event):
    url = "https://t.me/ROBLOXpvsb_bot?startgroup=newgroup&admin=manage_chat+delete_messages+restrict_members+invite_users+restrict_members+change_info+pin_messages+manage_video_chats"
    keyboard = types.KeyboardButtonUrl(text="добавить в группу", url=url)
    await event.edit(
        "Нажмите кнопку ниже, чтобы добавить бота в группу:",
        buttons=keyboard
    )


# Обработчик кнопки "Пожаловаться на скамера"
@bot.on(events.CallbackQuery(pattern='report_scammer'))
async def report_handler(event):
    await event.respond(
        "Для того что бы пожаловатся на скамера вы должны перейти в наш [специальный чат](https://t.me/infinityantiscam)\nВам нужны пруфы и скрины переписок!")


# Обработчик кнопки "Создатель"
@bot.on(events.CallbackQuery(pattern='creator'))
async def creator_handler(event):
    user_id = event.original_update.user_id
    try:
        user = await bot.get_entity(user_id)
        username = user.username
        if username:
            user_info = f"@{username}"
        else:
            user_info = f"ID: {user_id}"
    except Exception as e:
        user_info = f"ID: {user_id} (не удалось получить имя)"

    await event.edit(f"{user_info}, вот информация:\nСоздатель - @half50k\nКодер - @MyNameIsLiner")


# Обработчик кнопки "Тема проверки"
@bot.on(events.CallbackQuery(pattern='themes_soon'))
async def themes_handler(event):
    # Списки фотографий для различных статусов
    status_photos = {
        6: [  # Стажер
            "https://cdn.streamable.com/video/mp4/z1j4w6.mp4",
            "https://i.ibb.co/jPQpWgg3/temp-5173733679-1248.jpg",
            "https://i.ibb.co/JRFhpf2d/temp-5173733679-1294.jpg",
            "https://i.ibb.co/dwXYzYvV/temp-5173733679-1312.jpg"
        ],
        8: [  # Директор
            "https://i.ibb.co/Z6qKqwvY/temp-5173733679.jpg",
            "https://i.ibb.co/XfYFmf8n/temp-5173733679-1178.jpg",
            "https://i.ibb.co/ynNp17dG/1.jpg"
        ],
        7: [  # Админ
            "https://i.ibb.co/VWYdQrwK/temp-5173733679-1310.jpg",
            "https://i.ibb.co/hRNMk3Pg/temp-5173733679-1295.jpg",
            "https://i.ibb.co/Y7fZWqkY/temp-5173733679-1183.jpg",
            "https://i.ibb.co/PbN53Mj/image.jpg",
            "https://i.ibb.co/7NXdHPd5/image.jpg"
        ],
        9: [  # Президент
            "https://i.ibb.co/d4jHKRZC/temp-5173733679-1311.jpg",
            "https://i.ibb.co/pjYcnsHk/temp-5173733679-1182.jpg",
            "https://i.ibb.co/Z1XrK4sB/image.jpg",
            "https://i.ibb.co/fYjWwYwH/1.jpg"
        ],
        0: [  # Нет в базе
            "https://i.ibb.co/qYfWnnvY/temp-5173733679-1176.jpg",
            "https://i.ibb.co/23G4pXk6/temp-5173733679.jpg",
            "https://i.ibb.co/RpfWS3Q0/image.jpg",
            "https://i.ibb.co/YB8849FG/temp-5173733679-1309.jpg"
        ]
    }

    user_id = event.sender_id
    role_id = db.get_user_role(user_id)

    # Получаем фотографии для текущего статуса пользователя
    photos = status_photos.get(role_id, [])
    current_index = 0

    if not photos:
        await event.respond("📸 У вас нет доступных фотографий для выбора.")
        return

    # Функция для отправки фото
    async def send_photo(index):
        if index < 0 or index >= len(photos):
            return  # Проверка выхода за пределы списка
        await event.respond(
            f"📸 Выберите фото для статуса:\n\n"
            f"[❤]({photos[index]})",
            buttons=[
                [
                    Button.inline("◀", f"photo_prev_{index}"),
                    Button.inline("Выбрать!", f"select_photo_{index}"),
                    Button.inline("▶", f"photo_next_{index}")
                ]
            ],
            link_preview=True
        )

    # Отправляем первое фото
    await send_photo(current_index)

    # Обработчик для кнопки "Выбрать!"
    @bot.on(events.CallbackQuery(pattern=r'select_photo_(\d+)'))
    async def select_photo_handler(event):
        index = int(event.pattern_match.group(1))
        user_id = event.sender_id

        # Сохраняем фото как кастомное для пользователя
        db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (photos[index], user_id))
        db.conn.commit()

        await event.respond(f"✅ Новое фото успешно установлено в статус!")

    # Обработчик для кнопки "◀"
    @bot.on(events.CallbackQuery(pattern=r'photo_prev_(\d+)'))
    async def photo_prev_handler(event):
        index = int(event.pattern_match.group(1)) - 1
        await send_photo(index)

    # Обработчик для кнопки "▶"
    @bot.on(events.CallbackQuery(pattern=r'photo_next_(\d+)'))
    async def photo_next_handler(event):
        index = int(event.pattern_match.group(1)) + 1
        await send_photo(index)


@bot.on(events.CallbackQuery(pattern='check_soon'))
async def check_soon_handler(event):
    try:
        user = await event.client.get_entity(event.sender_id)
        user_id = user.id

        # Получаем текущую роль пользователя
        current_role_id = db.get_user_role(user_id)

        # Добавляем запись о проверке
        db.add_check(user_id, user_id)

        current_time = datetime.now()
        role_info = ROLES[current_role_id]

        # Получаем данные пользователя из базы
        user_data = db.get_user(user_id)
        country = user_data[5] if user_data and user_data[5] else "Не указана"
        channel = user_data[6] if user_data and user_data[6] else None
        custom_photo = user_data[7] if user_data and user_data[7] else None

        # Проверяем, изменилась ли роль пользователя
        new_role_id = db.get_user_role(user_id)  # Получаем новую роль
        if new_role_id != current_role_id:  # Если роль изменилась
            custom_photo = None  # Сбрасываем фото
            db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (custom_photo, user_id))
            db.conn.commit()

        response = (
            f"👤 | Пользователь: [{user.first_name}](tg://user/{user.id})\n\n"
            f"🔍 | ID: `{user.id}`\n\n"
            f"🤗 | Роль в базе: {role_info['name']}\n\n"
            f"🌍 | Страна: {country}\n\n"
            f"📢 | Канал: {channel}\n\n"
            f"⚖ | Шанс скама: {role_info['scam_chance']}%\n\n"
            f"📅 {current_time.strftime('%d.%m.%Y')} | 🔍 {db.get_check_count(user_id)}\n\n"
            f"[Просмотреть медиа]({custom_photo if custom_photo else role_info['preview_url']})"
        )

        buttons = [
            [
                Button.url("👤 Профиль",
                           f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"),
                Button.url("🔗 Ссылка", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}")
            ],
            [
                Button.url("⚠️ Слить скаммера", "https://t.me/infinityantiscam"),
                Button.url("⚖️ Аппеляция", "https://t.me/infinityAPPEALS")
            ]
        ]

        # ВМЕСТО event.edit ИСПОЛЬЗУЕМ event.respond для нового сообщения
        await event.respond(response, buttons=buttons, parse_mode='md')

        # Подтверждаем callback чтобы убрать "часики" на кнопке
        await event.answer()

    except Exception as e:
        print(f"Ошибка в check_soon_handler: {e}")
        await event.answer("❌ Произошла ошибка при обработке запроса", alert=True)


# Обработчик кнопки "Назад" в профиле
@bot.on(events.CallbackQuery(pattern='back_to_profile'))
async def back_to_profile_handler(event):
    user = await event.get_sender()
    user_id = user.id
    role = db.get_user_role(user_id)
    role_info = ROLES[role]

    # Получаем кастомное фото из базы
    user_data = db.get_user(user_id)
    custom_photo = user_data[7] if user_data else None
    preview_url = custom_photo if custom_photo else role_info['preview_url']

    checks_count = db.get_check_count(user_id)

    # Определяем текст кнопки для кастомного изображения
    custom_button_text = "🎆 Снять кастомное изображение" if custom_photo else "🎆 Установить кастомку"
    custom_callback_data = "remove_custom" if custom_photo else "custom_soon"

    keyboard = [
        [Button.inline("🔎 Проверить себя", "check_soon"),
         Button.inline("🎨 Тема проверки", "themes_soon")],
        [Button.inline("📢 Канал", "channel_soon"),
         Button.inline("🌍 Страна", "country_soon")],
        [Button.inline("❓ Помощь", "help_soon")],
        [Button.inline(custom_button_text, custom_callback_data)]
    ]

    profile_text = f"""
**👤 Профиль пользователя [{user.first_name}](tg://user/{user_id})**

🔍 **Вас проверяли:** `{checks_count}` раз
**📝 Роль в базе:** {role_info['name']}
[⠀]({preview_url})
"""

    await event.edit(profile_text, buttons=keyboard, parse_mode='md')


@bot.on(events.CallbackQuery(pattern='custom_soon'))
async def custom_soon_handler(event):
    user_id = event.sender_id

    # Проверка премиум-статуса
    if not db.is_premium_user(user_id):
        await event.answer(
            "❌ У вас нет премиум статуса! Для установки Кастом картинки приобретите премиум.",
            alert=True
        )
        return

    await event.respond("Отправьте изображение или видео")
    logger.info(f"User {user_id} initiated custom image/video upload.")

    @bot.on(events.NewMessage(from_users=user_id))
    async def media_handler(media_event):
        logger.info(f"User {user_id} sent a media message.")

        if media_event.photo or media_event.video:
            try:
                # Скачиваем медиа (изображение или видео)
                media_path = await bot.download_media(media_event.photo or media_event.video)
                logger.info(f"Downloaded media to {media_path}.")

                if media_event.photo:
                    # Обработка изображений
                    with open(media_path, "rb") as image_file:
                        files = {"image": image_file}
                        params = {"key": IMG_API_KEY}
                        response = requests.post(
                            "https://api.imgbb.com/1/upload",
                            params=params,
                            files=files
                        )
                        response.raise_for_status()  # Проверка на успешный статус
                        data = response.json()
                        logger.info(f"Image upload response: {data}")

                    os.remove(media_path)  # Удаляем временный файл

                    if data.get("success") and "data" in data and "url" in data["data"]:
                        image_url = data["data"]["url"]

                        # Сохраняем URL изображения в базу данных как кастомное фото
                        db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?',
                                          (image_url, user_id))
                        db.conn.commit()

                        await media_event.reply(
                            f"✅ Кастомное изображение успешно установлено в статус!\nСсылка: {image_url}",
                            parse_mode='md'
                        )
                        logger.info(f"Custom image set for user {user_id}: {image_url}")
                    else:
                        await media_event.reply("❌ Не удалось получить URL изображения.")
                        logger.error(f"Failed to get image URL for user {user_id}: {data}")

                elif media_event.video:
                    # Обработка видео
                    video_url = f"https://t.me/your_bot_name?start=video_{media_event.video.id}"  # Пример ссылки на видео
                    # Сохраняем URL видео в базу данных как кастомное фото
                    db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (video_url, user_id))
                    db.conn.commit()
                    await media_event.reply(
                        f"✅ Кастомное видео успешно установлено в статус!\nСсылка: {video_url}",
                        parse_mode='md'
                    )
                    logger.info(f"Custom video set for user {user_id}: {video_url}")

            except Exception as e:
                await media_event.reply(f"❌ Произошла ошибка: {str(e)}")
                logger.error(f"Error while processing media for user {user_id}: {str(e)}")
        else:
            await media_event.reply("❌ Пожалуйста, отправьте изображение или видео.")
            logger.warning(f"User {user_id} did not send valid media.")

        # Удаляем обработчик после завершения
        bot.remove_event_handler(media_handler)


@bot.on(events.CallbackQuery(pattern='remove_custom'))
async def remove_custom_handler(event):
    user_id = event.sender_id

    # Удаляем кастомное изображение из базы
    db.cursor.execute('UPDATE users SET custom_photo_url = NULL WHERE user_id = ?', (user_id,))
    db.conn.commit()

    await event.answer("✅ Кастомное изображение успешно удалено.")
    logger.info(f"Custom image removed for user {user_id}.")

    # Обновляем профиль пользователя
    await back_to_profile_handler(event)


@bot.on(events.CallbackQuery(pattern='channel_soon'))
async def channel_soon_handler(event):
    user_id = event.sender_id

    # Проверка премиум-статуса
    if not db.is_premium_user(user_id):
        # Всплывающее уведомление вместо сообщения в чат
        await event.answer(
            "❌ У вас нет премиум статуса! Для установки канала приобретите премиум.",
            alert=True  # Ключевой параметр для всплывающего окна
        )
        return

    # Остальной код без изменений
    await event.respond("Отправьте username канала (например, @channelname)")

    @bot.on(events.NewMessage(from_users=user_id))
    async def channel_handler(channel_event):
        channel_name = channel_event.text.strip()
        if not channel_name.startswith('@'):
            await channel_event.reply("❌ Имя канала должно начинаться с @")
        elif len(channel_name) > 32:
            await channel_event.reply("❌ Имя канала слишком длинное (макс. 32 символа)")
        else:
            db.update_user(channel_event.sender_id, channel=channel_name)
            await channel_event.reply(f"✅ Канал {channel_name} успешно сохранен!")
        bot.remove_event_handler(channel_handler)


# Обработчик кнопки "Страна"
@bot.on(events.CallbackQuery(pattern='country_soon'))
async def country_soon_handler(event):
    countries = [
        "США 🇺🇸", "Канада 🇨🇦", "Мексика 🇲🇽", "Бразилия 🇧🇷",
        "Аргентина 🇦🇷", "Великобритания 🇬🇧", "Франция 🇫🇷",
        "Германия 🇩🇪", "Италия 🇮🇹", "Испания 🇪🇸", "Китай 🇨🇳",
        "Япония 🇯🇵", "Австралия 🇦🇺", "Индия 🇮🇳", "Россия 🇷🇺",
        "Южноафриканская Республика 🇿🇦", "Египет 🇪🇬", "ОАЭ 🇦🇪",
        "Турция 🇹🇷", "Греция 🇬🇷", "Швеция 🇸🇪", "Норвегия 🇳🇴",
        "Финляндия 🇫🇮", "Дания 🇩🇰", "Польша 🇵🇱", "Чехия 🇨🇿",
        "Австрия 🇦🇹", "Швейцария 🇨🇭", "Нидерланды 🇳🇱", "Бельгия 🇧🇪",
        "Ирландия 🇮🇪", "Португалия 🇵🇹", "Румыния 🇷🇴", "Словакия 🇸🇰",
        "Словения 🇸🇮", "Хорватия 🇭🇷", "Латвия 🇱🇻", "Литва 🇱🇹",
        "Эстония 🇪🇪", "Мальта 🇲🇹", "Кипр 🇨🇾", "Исландия 🇮🇸",
        "Албания 🇦🇱", "Сербия 🇷🇸", "Босния и Герцеговина 🇧🇦",
        "Черногория 🇲🇪", "Македония 🇲🇰", "Косово 🇽🇰", "Беларусь 🇧🇾",
        "Украина 🇺🇦", "Грузия 🇬🇪", "Армения 🇦🇲", "Азербайджан 🇦🇿",
        "Казахстан 🇰🇿", "Узбекистан 🇺🇿", "Таджикистан 🇹🇯",
        "Туркменистан 🇹🇲", "Кыргызстан 🇰🇬", "Монголия 🇲🇳",
        "Иран 🇮🇷", "Ирак 🇮🇶", "Сирия 🇸🇾", "Ливан 🇱🇧",
        "Иордания 🇯🇴", "Катар 🇶🇦", "Бахрейн 🇧🇭", "Кувейт 🇰🇼",
        "Саудовская Аравия 🇸🇦", "Йемен 🇾🇪", "Вьетнам 🇻🇳"
    ]

    buttons = [Button.inline(country, f"set_country_{i}")
               for i, country in enumerate(countries)]

    # Создаём новое сообщение с кнопками выбора страны
    await event.respond(
        "🌍 Выберите страну, выбраная вами страна будет стоять у вас в профиле!",
        buttons=[buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    )


# Обработчик выбора страны
@bot.on(events.CallbackQuery(pattern=r'set_country_(\d+)'))
async def set_country_handler(event):
    country_idx = int(event.data.decode().split('_')[2])
    country = [
        "США 🇺🇸", "Канада 🇨🇦", "Мексика 🇲🇽", "Бразилия 🇧🇷",
        "Аргентина 🇦🇷", "Великобритания 🇬🇧", "Франция 🇫🇷",
        "Германия 🇩🇪", "Италия 🇮🇹", "Испания 🇪🇸", "Китай 🇨🇳",
        "Япония 🇯🇵", "Австралия 🇦🇺", "Индия 🇮🇳", "Россия 🇷🇺",
        "Южноафриканская Республика 🇿🇦", "Египет 🇪🇬", "ОАЭ 🇦🇪",
        "Турция 🇹🇷", "Греция 🇬🇷", "Швеция 🇸🇪", "Норвегия 🇳🇴",
        "Финляндия 🇫🇮", "Дания 🇩🇰", "Польша 🇵🇱", "Чехия 🇨🇿",
        "Австрия 🇦🇹", "Швейцария 🇨🇭", "Нидерланды 🇳🇱", "Бельгия 🇧🇪",
        "Ирландия 🇮🇪", "Португалия 🇵🇹", "Румыния 🇷🇴", "Словакия 🇸🇰",
        "Словения 🇸🇮", "Хорватия 🇭🇷", "Латвия 🇱🇻", "Литва 🇱🇹",
        "Эстония 🇪🇪", "Мальта 🇲🇹", "Кипр 🇨🇾", "Исландия 🇮🇸",
        "Албания 🇦🇱", "Сербия 🇷🇸", "Босния и Герцеговина 🇧🇦",
        "Черногория 🇲🇪", "Македония 🇲🇰", "Косово 🇽🇰", "Беларусь 🇧🇾",
        "Украина 🇺🇦", "Грузия 🇬🇪", "Армения 🇦🇲", "Азербайджан 🇦🇿",
        "Казахстан 🇰🇿", "Узбекистан 🇺🇿", "Таджикистан 🇹🇯",
        "Туркменистан 🇹🇲", "Кыргызстан 🇰🇬", "Монголия 🇲🇳",
        "Иран 🇮🇷", "Ирак 🇮🇶", "Сирия 🇸🇾", "Ливан 🇱🇧",
        "Иордания 🇯🇴", "Катар 🇶🇦", "Бахрейн 🇧🇭", "Кувейт 🇰🇼",
        "Саудовская Аравия 🇸🇦", "Йемен 🇾🇪", "Вьетнам 🇻🇳"
    ][country_idx]

    db.update_user(event.sender_id, country=country)

    # Создаём новое сообщение с подтверждением
    await event.respond(f"✅ Страна установлена: {country}")


# Обработчик кнопки "Помощь"
@bot.on(events.CallbackQuery(pattern='help_soon'))
async def help_soon_handler(event):
    help_text = """
🤖 **Команды бота:**

📋 **Проверка пользователей:**
• `Чек [юзернейм/ID]` - проверить пользователя
• `Чек` (ответом на сообщение) - проверить пользователя
• `Чек ми/я/себя` - проверить себя

👮‍♂️ **Выдача ролей (только для админов):**
• `+роль` (ответом на сообщение)
• `-роль` (снять роль)

📊 **Другие команды:**
• `/profile` - ваш профиль
• `/stats` - статистика бота
• `/report` - пожаловаться на скамера
"""
    await event.edit(help_text, buttons=[Button.inline("« Назад", "back_to_profile")])


def main():
    print("Bot started...")
    bot.run_until_disconnected()


if __name__ == "asgard":
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Бот запущен и готов к работе.")
    bot.run_until_disconnected()