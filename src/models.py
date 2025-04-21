# -*- coding: utf-8 -*-
"""
Модуль определения моделей данных SQLAlchemy.

Этот файл содержит классы, которые представляют таблицы в базе данных.
SQLAlchemy использует эти классы (модели) для взаимодействия с БД:
создания таблиц, добавления, чтения, обновления и удаления записей (CRUD).
Каждый класс соответствует таблице, а атрибуты класса - столбцам таблицы.

Здесь определены модели для:
- Region: Регионы России.
- StudyForm: Формы обучения (очная, заочная и т.д.).
- SpecialtyGroup: Укрупненные группы специальностей (УГСН).
- Specialty: Специальности по классификатору ОКСО.
- EducationalOrganization: Образовательные организации (ВУЗы и их филиалы).
- EducationalProgram: Аккредитованные образовательные программы.
"""

from .database import db # Импортируем объект db из модуля database
from werkzeug.security import generate_password_hash, check_password_hash # Для хэширования паролей
from flask_login import UserMixin # Миксин для модели пользователя Flask-Login

# Вспомогательная таблица program_study_forms удалена (т.к. формы обучения отсутствуют в структуре данных)
# program_study_forms = db.Table('program_study_forms',
#     db.Column('program_id', db.Integer, db.ForeignKey('educational_program.id'), primary_key=True),
#     db.Column('study_form_id', db.Integer, db.ForeignKey('study_form.id'), primary_key=True)
# )

class Region(db.Model):
    """
    Модель для хранения регионов России.
    Используется для связи с образовательными организациями и для фильтрации.
    """
    __tablename__ = 'region' # Явное указание имени таблицы

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор региона
    name = db.Column(db.String(200), unique=True, nullable=False) # Название региона, должно быть уникальным и не пустым

    # Связь "один-ко-многим": один регион может иметь много организаций
    # backref='region' создает виртуальный атрибут 'region' у модели EducationalOrganization
    # lazy='dynamic' означает, что организации будут загружаться по запросу (как query), а не все сразу
    organizations = db.relationship('EducationalOrganization', backref='region', lazy='dynamic')

    def __repr__(self):
        # Метод для представления объекта Region в виде строки (удобно для отладки)
        return f'<Region {self.name}>'

# Модель StudyForm удалена (т.к. формы обучения отсутствуют в структуре данных)
# class StudyForm(db.Model):
#     """
#     Модель для хранения форм обучения (очная, заочная, очно-заочная и т.д.).
#     """
#     __tablename__ = 'study_form'
#
#     id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор формы обучения
#     name = db.Column(db.String(100), unique=True, nullable=False) # Название формы обучения
#
#     # Связь "многие-ко-многим" с EducationalProgram через таблицу program_study_forms
#     # programs = db.relationship('EducationalProgram', secondary=program_study_forms, back_populates='study_forms', lazy='dynamic')
#
#     def __repr__(self):
#         return f'<StudyForm {self.name}>'

class SpecialtyGroup(db.Model):
    """
    Модель для хранения укрупненных групп специальностей (УГСН).
    Например, "09.00.00 Информатика и вычислительная техника".
    """
    __tablename__ = 'specialty_group'

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор УГСН
    code = db.Column(db.String(20), unique=True, nullable=False) # Код УГСН (например, "09.00.00")
    name = db.Column(db.String(255), nullable=False) # Наименование УГСН

    # Связь "один-ко-многим": одна УГСН содержит много специальностей
    specialties = db.relationship('Specialty', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<SpecialtyGroup {self.code} {self.name}>'

class Specialty(db.Model):
    """
    Модель для хранения специальностей по классификатору ОКСО.
    Связана с укрупненной группой специальностей (УГСН).
    Например, "09.03.01 Информатика и вычислительная техника" принадлежит УГСН "09.00.00".
    """
    __tablename__ = 'specialty'

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор специальности
    code = db.Column(db.String(20), unique=True, nullable=False) # Код специальности (например, "09.03.01")
    name = db.Column(db.String(255), nullable=False) # Наименование специальности
    group_id = db.Column(db.Integer, db.ForeignKey('specialty_group.id'), nullable=False) # Внешний ключ к УГСН

    # Связь "один-ко-многим": одна специальность может быть у многих образовательных программ
    programs = db.relationship('EducationalProgram', backref='specialty', lazy='dynamic')

    def __repr__(self):
        return f'<Specialty {self.code} {self.name}>'

class EducationalOrganization(db.Model):
    """
    Модель для хранения образовательных организаций (ВУЗы, ССУЗы) и их филиалов.
    Содержит основную информацию об организации и ее принадлежности к региону.
    Реализована поддержка иерархии (головная организация - филиал) через self-referential relationship.
    """
    __tablename__ = 'educational_organization'

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор организации
    full_name = db.Column(db.String(1000), nullable=False) # Полное наименование
    short_name = db.Column(db.String(500)) # Сокращенное наименование (может отсутствовать)
    ogrn = db.Column(db.String(15), unique=True, index=True) # ОГРН (Основной государственный регистрационный номер), уникален и индексирован для быстрого поиска
    inn = db.Column(db.String(12), unique=True, index=True) # ИНН (Идентификационный номер налогоплательщика), уникален и индексирован
    address = db.Column(db.String(1000)) # Адрес организации
    region_id = db.Column(db.Integer, db.ForeignKey('region.id')) # Внешний ключ к региону
    # Идентификатор головной организации (для филиалов)
    # Это внешний ключ, ссылающийся на id в этой же таблице (self-referential)
    parent_id = db.Column(db.Integer, db.ForeignKey('educational_organization.id'), nullable=True)

    # Связь "один-ко-многим" для филиалов: одна головная организация может иметь много филиалов
    # remote_side=[id] указывает, что 'id' является "удаленной" стороной в этой связи
    # backref='parent' создает атрибут 'parent' у филиала для доступа к головной организации
    branches = db.relationship('EducationalOrganization',
                               backref=db.backref('parent', remote_side=[id]),
                               lazy='dynamic')

    # Связь "один-ко-многим": одна организация может реализовывать много образовательных программ
    programs = db.relationship('EducationalProgram', backref='organization', lazy='dynamic')

    def is_branch(self):
        """Проверяет, является ли данная организация филиалом."""
        return self.parent_id is not None

    def __repr__(self):
        return f'<EducationalOrganization {self.short_name or self.full_name}>'

class EducationalProgram(db.Model):
    """
    Модель для хранения аккредитованных образовательных программ.
    Связана с образовательной организацией, специальностью и формами обучения.
    """
    __tablename__ = 'educational_program'

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор программы
    # Можно добавить поля для деталей аккредитации, если они есть в XML
    # accreditation_details = db.Column(db.Text)
    organization_id = db.Column(db.Integer, db.ForeignKey('educational_organization.id'), nullable=False) # Внешний ключ к организации
    specialty_id = db.Column(db.Integer, db.ForeignKey('specialty.id'), nullable=False) # Внешний ключ к специальности

    # Связь study_forms удалена (т.к. формы обучения отсутствуют в структуре данных)
    # study_forms = db.relationship('StudyForm', secondary=program_study_forms,
    #                               backref=db.backref('programs', lazy='dynamic'), # Добавляем backref здесь
    #                               lazy='dynamic')

    def __repr__(self):
        # Представление программы (можно улучшить, добавив название специальности/организации)
        return f'<EducationalProgram id={self.id} org_id={self.organization_id} spec_id={self.specialty_id}>'

# --- Модели для аутентификации и авторизации (Оценка 5) ---

# Класс UserMixin добавляет необходимые атрибуты и методы для Flask-Login:
# is_authenticated, is_active, is_anonymous, get_id()
class User(UserMixin, db.Model):
    """
    Модель для хранения информации о пользователях системы.
    """
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True) # Уникальный идентификатор пользователя
    username = db.Column(db.String(64), index=True, unique=True, nullable=False) # Имя пользователя (логин), уникальное
    email = db.Column(db.String(120), index=True, unique=True, nullable=False) # Email, уникальный
    password_hash = db.Column(db.String(256)) # Хэш пароля (строка достаточной длины)
    # TODO: Добавить поле для роли пользователя (связь с моделью Role)
    # role_id = db.Column(db.Integer, db.ForeignKey('role.id'))

    def set_password(self, password):
        """
        Устанавливает хэш пароля для пользователя.
        Использует generate_password_hash из Werkzeug для безопасного хэширования.

        Args:
            password (str): Пароль в открытом виде.
        """
        # generate_password_hash создает хэш с использованием соли,
        # что защищает от радужных таблиц.
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        Проверяет, соответствует ли предоставленный пароль хэшу, хранящемуся в БД.
        Использует check_password_hash из Werkzeug.

        Args:
            password (str): Пароль для проверки.

        Returns:
            bool: True, если пароль верный, False в противном случае.
        """
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        # Представление объекта User в виде строки
        return f'<User {self.username}>'

# TODO: Определить модель Role, если требуется ролевая система доступа
# class Role(db.Model):
#     __tablename__ = 'role'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(64), unique=True)
#     # Связь с пользователями
#     users = db.relationship('User', backref='role', lazy='dynamic')
#     # TODO: Добавить разрешения для роли
#     permissions = db.Column(db.Integer) # Пример: битовая маска разрешений
