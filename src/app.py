# -*- coding: utf-8 -*-
"""
Основной модуль Flask-приложения.

Этот файл отвечает за создание и конфигурацию экземпляра Flask-приложения.
Здесь происходит:
- Импорт необходимых библиотек и модулей (Flask, Config, database).
- Создание объекта приложения Flask.
- Загрузка конфигурации из объекта Config.
- Инициализация базы данных с помощью функции init_db из модуля database.
- Определение базовых маршрутов (пока только корневой '/').
- Настройка точки входа для запуска сервера разработки.
"""

# -*- coding: utf-8 -*-
"""
Основной модуль Flask-приложения.

Этот файл отвечает за создание и конфигурацию экземпляра Flask-приложения.
Здесь происходит:
- Импорт необходимых библиотек и модулей (Flask, Config, database, Migrate, models, commands).
- Создание объекта приложения Flask.
- Загрузка конфигурации из объекта Config.
- Инициализация базы данных с помощью функции init_db из модуля database.
- Инициализация Flask-Migrate для управления миграциями БД.
- Инициализация пользовательских команд CLI.
- Определение базовых маршрутов (пока только корневой '/').
- Настройка точки входа для запуска сервера разработки.
"""

from flask import Flask
from flask_migrate import Migrate # Импортируем Migrate
from .config import Config  # Импортируем класс конфигурации
from .database import db, init_db # Импортируем объект db и функцию инициализации
from . import models # Импортируем модели, чтобы Flask-Migrate мог их обнаружить
# Импортируем группу команд CLI
from .commands import data_cli
# Импортируем Blueprints
from .routes import main_bp
from .auth_routes import auth_bp # Импортируем auth_bp

# Создаем экземпляр LoginManager
# (Перемещаем сюда для ясности, т.к. он связан с auth_bp)
from flask_login import LoginManager
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # Указываем маршрут входа
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    """Загрузчик пользователя для Flask-Login."""
    # Импортируем User здесь, чтобы избежать циклических зависимостей при импорте models в начале
    from .models import User
    return db.session.get(User, int(user_id))

def create_app(config_class=Config):
    """
    Фабрика для создания экземпляра Flask-приложения.

    Использование фабрики приложений (Application Factory pattern) позволяет создавать
    несколько экземпляров приложения с разными конфигурациями (например, для тестов).
    Это считается хорошей практикой в разработке Flask-приложений.

    Args:
        config_class (class): Класс конфигурации для приложения. По умолчанию используется Config.

    Returns:
        Flask: Сконфигурированный экземпляр Flask-приложения.
    """
    # Создаем экземпляр Flask.
    # __name__ передается, чтобы Flask знал, где искать шаблоны, статические файлы и т.д.
    app = Flask(__name__)

    # Загружаем конфигурацию из объекта config_class (по умолчанию Config из config.py).
    # app.config.from_object() загружает атрибуты класса конфигурации в app.config.
    app.config.from_object(config_class)

    # Инициализируем базу данных для нашего приложения.
    # Функция init_db связывает объект db (SQLAlchemy) с нашим app.
    init_db(app)

    # Инициализируем Flask-Migrate
    # Передаем экземпляр приложения (app) и объект SQLAlchemy (db)
    migrate = Migrate(app, db)

    # Инициализируем Flask-Login
    login_manager.init_app(app)

    # Регистрируем группу команд CLI напрямую
    app.cli.add_command(data_cli)

    # Регистрируем основной Blueprint
    app.register_blueprint(main_bp)
    # Регистрируем Blueprint аутентификации
    app.register_blueprint(auth_bp)

    # Удаляем старый обработчик для '/', так как он теперь определен в main_bp
    # @app.route('/')
    # def index():
    #     """
    #     Обработчик для корневого маршрута '/'.
    #     Возвращает простое приветственное сообщение.
    #     """
    #     return "Привет! Веб-сервис информации о ВУЗах России."

    # Регистрация других Blueprints (например, для админки 'admin') будет здесь
    # from .admin_routes import admin_bp
    # app.register_blueprint(admin_bp, url_prefix='/admin')

    # Возвращаем созданный и сконфигурированный экземпляр приложения.
    # --- Контекстный процессор ---
    # Добавляет переменные в контекст всех шаблонов
    @app.context_processor
    def inject_current_year():
        """Внедряет текущий год в контекст шаблона."""
        from datetime import datetime
        return dict(current_year=datetime.utcnow().year)

    return app

# Блок if __name__ == '__main__': больше не нужен,
# так как приложение запускается через wsgi.py или flask run (с FLASK_APP=wsgi:app)
