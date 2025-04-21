# -*- coding: utf-8 -*-
"""
Модуль определения форм WTForms для веб-приложения.

Используется Flask-WTF для создания, валидации и обработки веб-форм.
Здесь будет определена форма для фильтрации реестра.
"""

from flask_wtf import FlaskForm # Базовый класс для форм Flask-WTF
# Импортируем типы полей формы
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField # Добавили TextAreaField
# Импортируем валидаторы
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional, Length
# Импортируем модели
from .models import User, Region, EducationalOrganization # Добавили Region, EducationalOrganization
from .database import db # Импортируем db для запросов к БД в валидаторах

class FilterRegistryForm(FlaskForm):
    """
    Форма для фильтрации реестра образовательных организаций.
    """
    # Выпадающий список для выбора региона.
    # coerce=int гарантирует, что значение будет преобразовано в целое число (ID региона).
    # choices будет заполняться динамически в маршруте.
    # '0' - значение для опции "Все регионы".
    # validators=[Optional()] - делает поле необязательным для заполнения.
    region = SelectField('Регион', coerce=int, validators=[Optional()], default=0)

    # Выпадающий список для выбора УГСН.
    specialty_group = SelectField('Укрупненная группа', coerce=int, validators=[Optional()], default=0)

    # Выпадающий список для выбора специальности.
    # Будет зависеть от выбранной УГСН (можно реализовать с помощью JavaScript на клиенте
    # или обновлять страницу при выборе УГСН). Пока сделаем простой список всех специальностей.
    specialty = SelectField('Специальность', coerce=int, validators=[Optional()], default=0)

    # Поле для формы обучения удалено
    # study_form = SelectField('Форма обучения', coerce=int, validators=[Optional()], default=0)

    # Кнопка для отправки формы
    submit = SubmitField('Применить фильтры')

    def __init__(self, *args, **kwargs):
        """
        Конструктор формы. Добавляет опцию "Все ..." в начало каждого списка.
        """
        super(FilterRegistryForm, self).__init__(*args, **kwargs)
        # Динамически добавляем опцию "Все ..." в начало списков,
        # если она еще не была добавлена при инициализации choices.
        # Это гарантирует, что пользователь всегда может сбросить фильтр.
        if self.region.choices and self.region.choices[0][0] != 0:
            self.region.choices.insert(0, (0, 'Все регионы'))
        if self.specialty_group.choices and self.specialty_group.choices[0][0] != 0:
            self.specialty_group.choices.insert(0, (0, 'Все группы'))
        if self.specialty.choices and self.specialty.choices[0][0] != 0:
            self.specialty.choices.insert(0, (0, 'Все специальности'))
        # Логика для study_form удалена
        # if self.study_form.choices and self.study_form.choices[0][0] != 0:
        #     self.study_form.choices.insert(0, (0, 'Все формы'))


# --- Формы для аутентификации ---

class LoginForm(FlaskForm):
    """Форма для входа пользователя в систему."""
    # Поле для ввода имени пользователя или email
    # DataRequired проверяет, что поле не пустое.
    username_or_email = StringField('Имя пользователя или Email',
                                    validators=[DataRequired(message="Это поле обязательно.")])
    # Поле для ввода пароля
    password = PasswordField('Пароль',
                             validators=[DataRequired(message="Это поле обязательно.")])
    # Чекбокс "Запомнить меня"
    remember_me = BooleanField('Запомнить меня')
    # Кнопка отправки
    submit = SubmitField('Войти')


class RegistrationForm(FlaskForm):
    """Форма для регистрации нового пользователя."""
    username = StringField('Имя пользователя',
                           validators=[DataRequired(message="Это поле обязательно."),
                                       Length(min=3, max=64, message="Имя пользователя должно быть от 3 до 64 символов.")])
    email = StringField('Email',
                        validators=[DataRequired(message="Это поле обязательно."),
                                    Email(message="Некорректный формат Email.")])
    password = PasswordField('Пароль',
                             validators=[DataRequired(message="Это поле обязательно."),
                                         Length(min=6, message="Пароль должен быть не менее 6 символов.")])
    # Поле для подтверждения пароля
    # EqualTo проверяет, что значение этого поля совпадает со значением поля 'password'.
    password2 = PasswordField(
        'Повторите пароль', validators=[DataRequired(message="Это поле обязательно."),
                                     EqualTo('password', message='Пароли должны совпадать.')])
    submit = SubmitField('Зарегистрироваться')

    # Пользовательские валидаторы для проверки уникальности username и email.
    # WTForms автоматически вызывает методы, начинающиеся с validate_<имя_поля>.

    def validate_username(self, username):
        """Проверяет, не занято ли имя пользователя."""
        # Ищем пользователя с таким же именем в БД.
        # Используем db.session.scalar() для получения одного значения или None.
        user = db.session.scalar(db.select(User).filter_by(username=username.data))
        if user is not None:
            # Если пользователь найден, генерируем ошибку валидации.
            raise ValidationError('Это имя пользователя уже занято. Пожалуйста, выберите другое.')

    def validate_email(self, email):
        """Проверяет, не занят ли email."""
        user = db.session.scalar(db.select(User).filter_by(email=email.data))
        if user is not None:
            raise ValidationError('Этот email уже зарегистрирован. Пожалуйста, используйте другой.')


# --- Формы для CRUD операций ---

class OrganizationForm(FlaskForm):
    """Форма для добавления/редактирования образовательной организации."""
    full_name = StringField('Полное наименование', validators=[DataRequired()])
    short_name = StringField('Краткое наименование')
    ogrn = StringField('ОГРН', validators=[DataRequired(), Length(min=13, max=15)]) # ОГРН обычно 13 или 15 цифр
    inn = StringField('ИНН', validators=[Optional(), Length(min=10, max=12)]) # ИНН 10 или 12 цифр, может отсутствовать
    address = TextAreaField('Адрес')
    # Выпадающий список для выбора региона
    region = SelectField('Регион', coerce=int, validators=[Optional()])
    # Выпадающий список для выбора головной организации (для филиалов)
    parent = SelectField('Головная организация (для филиала)', coerce=int, validators=[Optional()])
    submit = SubmitField('Сохранить')

    def __init__(self, original_ogrn=None, *args, **kwargs):
        """
        Конструктор формы. Сохраняет оригинальный ОГРН для валидации уникальности при редактировании.
        """
        super(OrganizationForm, self).__init__(*args, **kwargs)
        self.original_ogrn = original_ogrn
        # Заполняем choices для региона и головной организации (лучше делать в маршруте)
        # self.region.choices = [(r.id, r.name) for r in db.session.scalars(db.select(Region).order_by(Region.name)).all()]
        # self.region.choices.insert(0, (0, '--- Не выбрано ---')) # Добавляем опцию "не выбрано"
        # self.parent.choices = [(o.id, o.short_name or o.full_name) for o in db.session.scalars(db.select(EducationalOrganization).filter_by(parent_id=None).order_by(EducationalOrganization.short_name)).all()]
        # self.parent.choices.insert(0, (0, '--- Нет (Головная организация) ---'))

    def validate_ogrn(self, ogrn):
        """Проверяет уникальность ОГРН."""
        # Игнорируем проверку, если ОГРН не изменился при редактировании
        if self.original_ogrn and self.original_ogrn == ogrn.data:
            return
        # Ищем организацию с таким же ОГРН
        organization = db.session.scalar(db.select(EducationalOrganization).filter_by(ogrn=ogrn.data))
        if organization:
            raise ValidationError('Организация с таким ОГРН уже существует.')

    def validate_inn(self, inn):
        """Проверяет уникальность ИНН (если он указан)."""
        if not inn.data: # ИНН не обязателен
            return
        # Игнорируем проверку, если ИНН не изменился (нужно передавать original_inn)
        # if self.original_inn and self.original_inn == inn.data:
        #     return
        organization = db.session.scalar(db.select(EducationalOrganization).filter_by(inn=inn.data))
        if organization:
            raise ValidationError('Организация с таким ИНН уже существует.')

# TODO: Добавить формы для редактирования программ, специальностей и т.д.
# TODO: Добавить форму смены пароля
