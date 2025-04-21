# -*- coding: utf-8 -*-
"""
Модуль определения основных маршрутов веб-приложения (Blueprint).

Здесь определяются обработчики URL-адресов для главной страницы и страницы реестра.
Используется Flask Blueprint для лучшей организации кода.
"""

from flask import Blueprint, render_template, request, url_for, redirect, flash, abort # Добавили flash, abort
from sqlalchemy import asc, desc, distinct # Для сортировки и distinct
from flask_login import login_required, current_user # Для защиты маршрутов и проверки прав (пока не используется)
# Импортируем модели (StudyForm и program_study_forms удалены)
from .models import EducationalOrganization, Region, Specialty, SpecialtyGroup, EducationalProgram
# Убрали импорт click и команды CLI
from .database import db # Импортируем объект БД для запросов
# Импортируем формы
from .forms import FilterRegistryForm, OrganizationForm # Добавили OrganizationForm

# Создаем Blueprint с именем 'main'.
# Первый аргумент - имя Blueprint.
# Второй аргумент - __name__, помогает Flask найти шаблоны и статические файлы относительно этого модуля.
# url_prefix можно использовать, если все маршруты этого Blueprint должны начинаться с определенного префикса (например, '/admin').
main_bp = Blueprint('main', __name__)

# --- Маршруты веб-приложения ---

# Определяем маршрут для главной страницы ('/')
@main_bp.route('/')
def index():
    """
    Обработчик для главной страницы.
    Пока просто перенаправляет на страницу реестра.
    В будущем здесь может быть приветственная информация или статистика.
    """
    # Используем url_for для генерации URL к маршруту 'show_registry' внутри этого же Blueprint ('main').
    # Точка перед именем маршрута ('.show_registry') указывает, что ищем маршрут внутри текущего Blueprint.
    return redirect(url_for('.show_registry'))

# Определяем маршрут для страницы реестра ('/registry')
# Используем только GET, так как фильтры будут передаваться через URL параметры
@main_bp.route('/registry')
def show_registry():
    """
    Обработчик для отображения реестра образовательных организаций.
    Поддерживает пагинацию, сортировку и фильтрацию.
    """
    # --- Обработка параметров запроса ---
    # Получаем номер страницы из GET-параметра 'page', по умолчанию 1. Тип integer.
    page = request.args.get('page', 1, type=int)
    # Получаем параметр сортировки из GET-параметра 'sort_by', по умолчанию 'name'.
    sort_by = request.args.get('sort_by', 'name')
    # Получаем направление сортировки из GET-параметра 'sort_order', по умолчанию 'asc'.
    sort_order = request.args.get('sort_order', 'asc')

    # --- Создание и заполнение формы фильтрации ---
    # Создаем экземпляр формы, передавая данные из GET-параметров (request.args)
    filter_form = FilterRegistryForm(request.args)

    # Загружаем данные для выпадающих списков формы
    # Используем .scalars().all() для получения списка объектов
    regions = db.session.execute(db.select(Region).order_by(Region.name)).scalars().all()
    specialty_groups = db.session.execute(db.select(SpecialtyGroup).order_by(SpecialtyGroup.name)).scalars().all()
    specialties = db.session.execute(db.select(Specialty).order_by(Specialty.name)).scalars().all()
    # Загрузка study_forms удалена
    # study_forms = db.session.execute(db.select(StudyForm).order_by(StudyForm.name)).scalars().all()

    # Заполняем choices для полей формы (кроме опции "Все ...", которая добавляется в конструкторе формы)
    filter_form.region.choices = [(r.id, r.name) for r in regions]
    filter_form.specialty_group.choices = [(sg.id, f"{sg.code} {sg.name}") for sg in specialty_groups]
    filter_form.specialty.choices = [(s.id, f"{s.code} {s.name}") for s in specialties]
    # Заполнение choices для study_form удалено
    # filter_form.study_form.choices = [(sf.id, sf.name) for sf in study_forms]

    # --- Построение запроса к БД с учетом фильтров ---
    # Начинаем строить запрос к таблице EducationalOrganization
    # Используем select() вместо query() для современного SQLAlchemy
    query = db.select(EducationalOrganization).distinct() # distinct() чтобы избежать дубликатов организаций при join

    # Применяем фильтры, если они выбраны в форме (значение не равно 0)
    if filter_form.region.data:
        query = query.filter(EducationalOrganization.region_id == filter_form.region.data)

    # Фильтр по УГСН требует join через программы и специальности
    if filter_form.specialty_group.data:
        query = query.join(EducationalOrganization.programs).join(EducationalProgram.specialty)\
                     .filter(Specialty.group_id == filter_form.specialty_group.data)

    # Фильтр по специальности требует join через программы
    if filter_form.specialty.data:
        # Убедимся, что join добавлен, если он не был добавлен фильтром по УГСН
        if not filter_form.specialty_group.data:
             query = query.join(EducationalOrganization.programs)
        query = query.filter(EducationalProgram.specialty_id == filter_form.specialty.data)

    # Фильтр по форме обучения требует join через программы и таблицу связей
    if filter_form.study_form.data:
        # Убедимся, что join с программами добавлен
        if not filter_form.specialty_group.data and not filter_form.specialty.data:
             query = query.join(EducationalOrganization.programs)
        # Добавляем join с таблицей связей и формой обучения - Удалено
        # query = query.join(EducationalProgram.study_forms).filter(StudyForm.id == filter_form.study_form.data)

    # --- Применение сортировки ---
    # Определяем столбец для сортировки
    sort_column = EducationalOrganization.full_name # Сортировка по умолчанию
    if sort_by == 'ogrn':
        sort_column = EducationalOrganization.ogrn
    elif sort_by == 'inn':
        sort_column = EducationalOrganization.inn
    elif sort_by == 'region':
        # Сортировка по связанной таблице (имени региона)
        # Добавляем join только если сортируем по региону и он еще не был добавлен фильтрами
        if sort_by == 'region' and not filter_form.region.data: # Проверяем, что join еще не сделан
             # Используем outerjoin на случай, если у организации не указан регион
             query = query.outerjoin(EducationalOrganization.region)
        sort_column = Region.name
    # Добавьте другие поля для сортировки при необходимости

    # Применяем направление сортировки
    if sort_order == 'desc':
        query = query.order_by(desc(sort_column))
    else:
        # По умолчанию сортируем по возрастанию ('asc')
        query = query.order_by(asc(sort_column))
        sort_order = 'asc' # Убедимся, что значение корректно для передачи в шаблон

    # --- Выполнение запроса с пагинацией ---
    # Выполняем запрос с пагинацией.
    # Первый аргумент - номер страницы.
    # Второй аргумент (per_page) - количество элементов на странице (можно вынести в конфиг).
    # Третий аргумент (error_out) - генерировать ли ошибку 404, если страница не существует.
    # Четвертый аргумент (max_per_page) - максимальное количество элементов на странице.
    pagination = db.paginate(query, page=page, per_page=20, error_out=False, max_per_page=100)
    # Получаем список организаций для текущей страницы
    organizations = pagination.items

    # --- Подготовка данных для шаблона ---
    # Передаем данные в шаблон 'registry.html'
    return render_template('registry.html',
                           organizations=organizations, # Список организаций для текущей страницы
                           pagination=pagination,       # Объект пагинации для ссылок на страницы
                           sort_by=sort_by,             # Текущее поле сортировки
                           sort_order=sort_order,       # Текущее направление сортировки
                            filter_form=filter_form      # Передаем форму в шаблон
                            )

# --- Маршруты для CRUD операций над организациями ---

def _populate_organization_form_choices(form):
    """Вспомогательная функция для заполнения choices в форме организации."""
    # Загружаем регионы и головные организации (не филиалы)
    regions = db.session.execute(db.select(Region).order_by(Region.name)).scalars().all()
    parents = db.session.execute(
        db.select(EducationalOrganization).filter(EducationalOrganization.parent_id.is_(None)).order_by(EducationalOrganization.short_name)
    ).scalars().all()
    # Заполняем choices, добавляя опцию "не выбрано"
    form.region.choices = [(0, '--- Не выбрано ---')] + [(r.id, r.name) for r in regions]
    form.parent.choices = [(0, '--- Нет (Головная организация) ---')] + [(p.id, p.short_name or p.full_name) for p in parents]


@main_bp.route('/organization/add', methods=['GET', 'POST'])
@login_required # Только аутентифицированные пользователи могут добавлять
def add_organization():
    """Обработчик для добавления новой образовательной организации."""
    # TODO: Добавить проверку прав доступа (например, только администратор)
    # if not current_user.is_admin():
    #     abort(403) # Forbidden

    form = OrganizationForm()
    _populate_organization_form_choices(form) # Заполняем выпадающие списки

    if form.validate_on_submit():
        # Создаем новый объект организации
        new_org = EducationalOrganization(
            full_name=form.full_name.data,
            short_name=form.short_name.data,
            ogrn=form.ogrn.data,
            inn=form.inn.data,
            address=form.address.data,
            # Устанавливаем region_id и parent_id, если выбрано значение (не 0)
            region_id=form.region.data if form.region.data else None,
            parent_id=form.parent.data if form.parent.data else None
        )
        db.session.add(new_org)
        try:
            db.session.commit()
            flash('Организация успешно добавлена!', 'success')
            # Перенаправляем на страницу реестра после добавления
            return redirect(url_for('.show_registry'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении организации: {e}', 'error')

    # Отображаем шаблон формы добавления
    return render_template('organization_form.html', title='Добавить организацию', form=form)


@main_bp.route('/organization/<int:org_id>/edit', methods=['GET', 'POST'])
@login_required # Только аутентифицированные пользователи могут редактировать
def edit_organization(org_id):
    """Обработчик для редактирования существующей образовательной организации."""
    # TODO: Добавить проверку прав доступа
    # if not current_user.is_admin():
    #     abort(403)

    # Находим организацию по ID или возвращаем 404
    organization = db.get_or_404(EducationalOrganization, org_id)
    # Создаем форму, передавая оригинальный ОГРН для валидации уникальности
    # и объект organization для предзаполнения полей формы при GET-запросе
    form = OrganizationForm(original_ogrn=organization.ogrn, obj=organization)
    _populate_organization_form_choices(form) # Заполняем выпадающие списки

    if form.validate_on_submit():
        # Обновляем поля существующего объекта organization данными из формы
        organization.full_name = form.full_name.data
        organization.short_name = form.short_name.data
        organization.ogrn = form.ogrn.data
        organization.inn = form.inn.data
        organization.address = form.address.data
        organization.region_id = form.region.data if form.region.data else None
        organization.parent_id = form.parent.data if form.parent.data else None
        try:
            db.session.commit()
            flash('Данные организации успешно обновлены!', 'success')
            # Перенаправляем на страницу реестра
            return redirect(url_for('.show_registry'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении организации: {e}', 'error')

    # Отображаем шаблон формы редактирования (тот же шаблон, что и для добавления)
    return render_template('organization_form.html', title='Редактировать организацию', form=form, organization=organization)


@main_bp.route('/organization/<int:org_id>/delete', methods=['POST']) # Используем POST для удаления
@login_required
def delete_organization(org_id):
    """Обработчик для удаления организации."""
    # TODO: Добавить проверку прав доступа
    # if not current_user.is_admin():
    #     abort(403)

    organization = db.get_or_404(EducationalOrganization, org_id)
    try:
        # TODO: Проверить зависимости (например, связанные программы) перед удалением
        # или настроить каскадное удаление в модели (ondelete='CASCADE')
        db.session.delete(organization)
        db.session.commit()
        flash('Организация успешно удалена.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении организации: {e}', 'error')
        # Можно добавить логирование ошибки

    return redirect(url_for('.show_registry'))

# TODO: Добавить CRUD для других моделей (программы, специальности и т.д.)
