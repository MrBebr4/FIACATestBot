# -*- coding: utf-8 -*-
"""
Модуль определения маршрутов для аутентификации пользователей (Blueprint 'auth').
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse # Используем стандартную библиотеку для разбора URL
from .forms import LoginForm, RegistrationForm # Импортируем формы
from .models import User # Импортируем модель User
from .database import db # Импортируем объект БД

# Создаем Blueprint 'auth' с префиксом URL '/auth'
# Все URL в этом Blueprint будут начинаться с /auth (например, /auth/login)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Обработчик для страницы входа."""
    # Если пользователь уже аутентифицирован, перенаправляем на главную страницу реестра
    if current_user.is_authenticated:
        return redirect(url_for('main.show_registry')) # Используем 'main.show_registry' для ссылки на другой Blueprint

    form = LoginForm()
    # Если форма отправлена (POST) и валидна
    if form.validate_on_submit():
        login_identifier = form.username_or_email.data
        # Ищем пользователя по имени пользователя или email
        user = db.session.scalar(
            db.select(User).filter(
                (User.username == login_identifier) | (User.email == login_identifier)
            )
        )

        # Проверяем, найден ли пользователь и верен ли пароль
        if user is None or not user.check_password(form.password.data):
            flash('Неверное имя пользователя/email или пароль.', 'error') # Показываем сообщение об ошибке
            # Возвращаем страницу входа снова (с сообщением об ошибке)
            return redirect(url_for('.login')) # '.login' - ссылка внутри текущего Blueprint 'auth'

        # Если все верно, логиним пользователя
        # Функция login_user из Flask-Login регистрирует пользователя в сессии.
        # remember=form.remember_me.data - учитывает галочку "Запомнить меня".
        login_user(user, remember=form.remember_me.data)
        flash(f'Добро пожаловать, {user.username}!', 'success')

        # Перенаправляем пользователя на страницу, которую он пытался посетить до входа,
        # или на главную страницу реестра, если такой страницы не было.
        next_page = request.args.get('next')
        # Проверка безопасности: убеждаемся, что URL для перенаправления относится к нашему сайту.
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('main.show_registry') # Перенаправление по умолчанию
        return redirect(next_page)

    # Если GET-запрос или форма невалидна, показываем шаблон страницы входа
    return render_template('auth/login.html', title='Вход', form=form)


@auth_bp.route('/logout')
@login_required # Этот декоратор требует, чтобы пользователь был аутентифицирован для доступа к этому маршруту
def logout():
    """Обработчик для выхода пользователя из системы."""
    logout_user() # Функция Flask-Login для удаления пользователя из сессии
    flash('Вы успешно вышли из системы.', 'info')
    return redirect(url_for('main.show_registry')) # Перенаправляем на главную страницу реестра


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Обработчик для страницы регистрации."""
    # Если пользователь уже аутентифицирован, перенаправляем
    if current_user.is_authenticated:
        return redirect(url_for('main.show_registry'))

    form = RegistrationForm()
    if form.validate_on_submit():
        # Создаем нового пользователя
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data) # Устанавливаем хэшированный пароль
        # Добавляем пользователя в сессию БД и сохраняем
        db.session.add(user)
        db.session.commit()
        flash('Поздравляем, вы успешно зарегистрированы! Теперь вы можете войти.', 'success')
        # Перенаправляем на страницу входа после успешной регистрации
        return redirect(url_for('.login'))

    # Отображаем шаблон страницы регистрации
    return render_template('auth/register.html', title='Регистрация', form=form)

# TODO: Добавить маршруты для смены/сброса пароля
