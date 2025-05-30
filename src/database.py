# -*- coding: utf-8 -*-
"""
Модуль инициализации базы данных.

Этот модуль отвечает за создание и настройку объекта SQLAlchemy,
который будет использоваться для взаимодействия с базой данных во всем приложении.
Использование Flask-SQLAlchemy упрощает интеграцию SQLAlchemy с Flask,
предоставляя удобные инструменты для управления сессиями, моделями и миграциями.
"""

from flask_sqlalchemy import SQLAlchemy

# Создаем экземпляр SQLAlchemy.
# На данном этапе мы не привязываем его к конкретному Flask-приложению.
# Это позволяет использовать объект `db` в разных частях приложения (например, в моделях)
# до того, как само приложение будет полностью сконфигурировано.
# Привязка к приложению произойдет позже, при инициализации Flask-приложения
# с помощью метода `db.init_app(app)`.
db = SQLAlchemy()

def init_db(app):
    """
    Инициализирует базу данных для Flask-приложения.

    Эта функция связывает созданный экземпляр SQLAlchemy (`db`)
    с конкретным экземпляром Flask-приложения (`app`).
    Она также загружает конфигурацию базы данных из настроек приложения (`app.config`).

    Args:
        app: Экземпляр Flask-приложения.
    """
    db.init_app(app)
    # В будущем здесь можно добавить команды для создания таблиц при первом запуске,
    # если не используется Flask-Migrate, например:
    # with app.app_context():
    #     db.create_all()
