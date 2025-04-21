# -*- coding: utf-8 -*-
"""
Точка входа WSGI для приложения.

Этот файл используется для запуска приложения с помощью командной строки
или WSGI-серверов (например, Gunicorn, uWSGI).
Он импортирует фабрику приложений `create_app` из пакета `src`
и создает экземпляр приложения.
"""

import os
from src.app import create_app # Импортируем фабрику приложений из src/app.py

# Создаем экземпляр приложения, используя конфигурацию по умолчанию.
# Можно передать другую конфигурацию при необходимости, например, для разных сред.
# config_name = os.getenv('FLASK_CONFIG') or 'default'
app = create_app()

# Этот блок позволяет запускать сервер разработки напрямую через `python wsgi.py`
if __name__ == "__main__":
    # Получаем хост и порт из переменных окружения или используем значения по умолчанию
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    try:
        port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    except ValueError:
        port = 5000
    # Используем встроенный сервер Flask для разработки.
    # debug=True берется из конфигурации приложения (app.config['DEBUG'])
    # или можно установить явно app.run(debug=True, host=host, port=port)
    # ВАЖНО: Не используйте debug=True в продакшене!
    app.run(host=host, port=port)
