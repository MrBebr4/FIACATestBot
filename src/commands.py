# -*- coding: utf-8 -*-
"""
Модуль для определения пользовательских команд Flask CLI.
"""

import click
from flask.cli import with_appcontext
from .data_loader.loader import DataLoader

# Создаем группу команд 'data'
@click.group('data')
def data_cli():
    """Команды для управления данными реестра."""
    pass

# Определяем команду 'load' внутри группы 'data'
@data_cli.command('load')
@with_appcontext
def load_data_command():
    """
    Загружает, распаковывает, парсит данные Рособрнадзора и обновляет БД.
    """
    click.echo("Запуск процесса обновления данных из команды Flask CLI...")
    loader = DataLoader()
    success = False # Инициализируем флаг успеха
    try:
        # Передаем объект приложения из контекста Flask CLI
        loader.run_update(app=click.get_current_context().obj)
        # Если run_update завершился без исключений, считаем операцию успешной
        # (предполагая, что run_update сам логирует внутренние ошибки)
        success = True
    except Exception as e:
        # Ловим критические ошибки, которые могли прервать выполнение run_update
        click.echo(f"Критическая ошибка во время выполнения команды: {e}", err=True)
        # Можно добавить более детальное логирование ошибки при необходимости
        # import traceback
        # click.echo(traceback.format_exc(), err=True)
        # success остается False

    # Сообщаем результат на основе флага success
    if success:
        # Выводим сообщение об успехе только если не было исключений
        # (и если run_update не сообщил об ошибках внутри себя)
        click.echo("Процесс обновления данных завершен (проверьте логи на наличие ошибок).")
    else:
        click.echo("Процесс обновления данных завершился с ошибками.", err=True)
