# -*- coding: utf-8 -*-
"""
Модуль для загрузки и предварительной обработки данных Рособрнадзора.

Отвечает за:
- Загрузку архива с данными с официального портала.
- Распаковку архива в локальную директорию для кэширования.
- Проверку наличия обновлений данных (базовая реализация).
- В будущем: парсинг XML-файлов и загрузку данных в БД.
"""

import os
import requests # Библиотека для выполнения HTTP-запросов (скачивание файла)
import zipfile # Библиотека для работы с ZIP-архивами
import logging # Библиотека для логирования событий
from urllib.parse import urlparse # Для извлечения имени файла из URL
import glob # Для поиска файлов по шаблону
from lxml import etree # Эффективная библиотека для парсинга XML
from sqlalchemy.orm import sessionmaker # Для создания сессий БД
from sqlalchemy import create_engine # Для создания движка БД (если запускать отдельно)
from contextlib import contextmanager # Для создания менеджера контекста сессии

# Импортируем конфигурацию приложения и модели
from ..config import Config
from ..database import db
# Импортируем все модели, чтобы SQLAlchemy знал о них
# Убираем StudyForm и program_stdy_forms, так как их нет в новой структуре
from ..models import Region, SpecialtyGroup, Specialty, EducationalOrganization, EducationalProgram
# Убрали блок except ImportError и импорт create_app, т.к. команда запускается через Flask CLI с контекстом

# Настройка базового логирования
# Уровень INFO означает, что будут записываться информационные сообщения,
# предупреждения и ошибки.
# Формат сообщения включает время, уровень логирования и само сообщение.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataLoader:
    """
    Класс для управления процессом загрузки и обработки данных Рособрнадзора.
    Инкапсулирует логику скачивания, распаковки, кэширования и (в будущем) парсинга.
    """
    def __init__(self, config=Config):
        """
        Инициализатор класса DataLoader.

        Args:
            config (object): Объект конфигурации приложения (по умолчанию Config).
                             Содержит пути, URL и другие настройки.
        """
        self.config = config
        # Путь для сохранения скачанных архивов и распакованных данных
        self.cache_path = self.config.DATA_CACHE_PATH
        # URL для скачивания данных
        self.data_url = self.config.ROSOBRNADZOR_DATA_URL
        # Путь к файлу, где будет храниться информация о последней загрузке (для проверки обновлений)
        self.metadata_file = os.path.join(self.cache_path, 'metadata.json') # Используем JSON для метаданных
        self.db_session = None # Сессия БД будет инициализирована позже

        # Убедимся, что директория для кэша существует
        os.makedirs(self.cache_path, exist_ok=True)
        logging.info(f"Директория для кэша: {self.cache_path}")

    # --- Вспомогательные функции ---
    def _get_text(self, element, xpath, default=''):
        """Безопасно извлекает текст из элемента по XPath."""
        found = element.findtext(xpath)
        return found.strip() if found else default

    def _extract_region_from_address(self, address):
        """
        Очень примитивная попытка извлечь регион из адреса.
        В реальных данных этот метод потребует значительной доработки
        с использованием библиотек для разбора адресов или регулярных выражений,
        а лучше всего - если регион будет указан в XML отдельным тегом.
        """
        # Пример: ищем известные города федерального значения или области/края/республики
        # Это ОЧЕНЬ ненадёжно!
        address_lower = address.lower()
        # Простые проверки (нужно расширять список)
        possible_regions = ['г. москва', 'московская область', 'г. санкт-петербург', 'ленинградская область']
        for region_name in possible_regions:
            if region_name in address_lower:
                # Возвращаем стандартизированное название (первая буква заглавная)
                return region_name.capitalize()
        # Если не нашли, пытаемся взять первую часть до первой запятой (тоже ненадёжно)
        parts = address.split(',', 1)
        if len(parts) > 1:
             # Убираем индекс, если он есть в начале
            region_part = parts[0].strip()
            if region_part.isdigit() and len(region_part) == 6: # Похоже на индекс
                 if len(parts) > 1:
                     region_part = parts[1].split(',', 1)[0].strip() # Берем следующую часть
                 else:
                     return None # Не удалось извлечь
            return region_part.capitalize()

        logging.warning(f"Не удалось извлечь регион из адреса: {address}")
        return None # Возвращаем None, если не удалось определить

    @contextmanager
    def session_scope(self, app=None):
        """
        Предоставляет транзакционную область видимости вокруг серии операций с БД.
        Создает сессию, обрабатывает commit/rollback и закрывает сессию.
        Может работать как с существующим Flask app context, так и создавать свой.
        """
        # Теперь app всегда должен передаваться при вызове из команды CLI
        if not app:
             # Эта ветка больше не должна выполняться при запуске через команду CLI
             # Можно либо вызвать ошибку, либо оставить старую логику создания сессии,
             # но она не будет работать без движка. Лучше вызвать ошибку.
             raise RuntimeError("Контекст приложения Flask не был предоставлен для session_scope.")

        with app.app_context():
            session = db.session
            try:
                yield session
                session.commit()
            except Exception as e:
                logging.error(f"Ошибка базы данных: {e}. Откат транзакции.")
                session.rollback()
                raise
            finally:
                # db.session управляется Flask-SQLAlchemy, обычно не нужно явно удалять
                # session.remove() # Или db.session.remove()
                pass # Flask-SQLAlchemy управляет сессией в контексте запроса/приложения
        # Блок else удален, так как мы теперь всегда требуем контекст приложения

    def _get_or_create(self, session, model, defaults=None, **kwargs):
        """
        Получает объект из БД по заданным параметрам (kwargs).
        Если объект не найден, создает новый с параметрами kwargs и defaults.

        Args:
            session: Активная сессия SQLAlchemy.
            model: Класс модели SQLAlchemy.
            defaults (dict, optional): Словарь значений по умолчанию для создания нового объекта.
            **kwargs: Параметры для поиска существующего объекта (обычно уникальные поля).

        Returns:
            tuple: (instance, created) - экземпляр модели и флаг (True, если создан новый).
        """
        # Ищем существующий экземпляр по параметрам kwargs
        instance = session.query(model).filter_by(**kwargs).first()
        if instance:
            # Если найден, возвращаем его и флаг False (не создан)
            return instance, False
        else:
            # Если не найден, создаем новый экземпляр
            # Объединяем параметры поиска kwargs и значения по умолчанию defaults
            params = {**kwargs, **(defaults or {})}
            instance = model(**params)
            # Добавляем новый экземпляр в сессию
            session.add(instance)
            # Возвращаем новый экземпляр и флаг True (создан)
            logging.debug(f"Создан новый объект {model.__name__}: {params}")
            return instance, True

    def _get_filename_from_url(self):
        """Извлекает имя файла из URL."""
        parsed_url = urlparse(self.data_url)
        # os.path.basename извлекает последнюю часть пути (имя файла)
        filename = os.path.basename(parsed_url.path)
        # Если URL не содержит имени файла (например, заканчивается на '/'),
        # возвращаем имя по умолчанию или генерируем ошибку.
        if not filename:
            logging.warning("Не удалось извлечь имя файла из URL. Используется 'data.zip'.")
            return 'data.zip' # Имя по умолчанию, если не удалось извлечь
        return filename

    def _download_data(self, archive_path):
        """
        Скачивает архив с данными по указанному URL.

        Args:
            archive_path (str): Полный путь для сохранения скачанного архива.

        Returns:
            bool: True, если скачивание успешно, False в противном случае.
        """
        logging.info(f"Начало скачивания данных с {self.data_url}")
        try:
            # Отправляем GET-запрос к URL. stream=True позволяет скачивать большие файлы
            # без загрузки всего содержимого в память сразу.
            response = requests.get(self.data_url, stream=True, timeout=60) # Таймаут 60 секунд
            # Проверяем статус ответа. Если код не 200 (OK), значит произошла ошибка.
            response.raise_for_status() # Генерирует исключение для кодов ошибок (4xx, 5xx)

            # Открываем файл для записи в бинарном режиме ('wb')
            with open(archive_path, 'wb') as f:
                # Итерируемся по содержимому ответа кусками по 8 КБ
                for chunk in response.iter_content(chunk_size=8192):
                    # Записываем каждый кусок в файл
                    f.write(chunk)
            logging.info(f"Данные успешно скачаны и сохранены в {archive_path}")
            return True
        except requests.exceptions.RequestException as e:
            # Обрабатываем ошибки, связанные с запросом (сеть, таймаут, неверный URL и т.д.)
            logging.error(f"Ошибка при скачивании данных: {e}")
            return False
        except Exception as e:
            # Обрабатываем другие возможные ошибки (например, проблемы с записью файла)
            logging.error(f"Непредвиденная ошибка при скачивании: {e}")
            return False

    def _unpack_archive(self, archive_path):
        """
        Распаковывает ZIP-архив в директорию кэша.

        Args:
            archive_path (str): Путь к скачанному ZIP-архиву.

        Returns:
            bool: True, если распаковка успешна, False в противном случае.
        """
        logging.info(f"Начало распаковки архива: {archive_path}")
        try:
            # Проверяем, является ли файл действительным ZIP-архивом
            if not zipfile.is_zipfile(archive_path):
                logging.error(f"Файл {archive_path} не является ZIP-архивом.")
                return False

            # Открываем ZIP-архив для чтения ('r')
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # Извлекаем все содержимое архива в директорию self.cache_path
                zip_ref.extractall(self.cache_path)
            logging.info(f"Архив успешно распакован в {self.cache_path}")
            # Можно добавить удаление архива после распаковки, если он больше не нужен
            # os.remove(archive_path)
            # logging.info(f"Удален исходный архив: {archive_path}")
            return True
        except zipfile.BadZipFile:
            # Ошибка, если архив поврежден
            logging.error(f"Ошибка: Архив {archive_path} поврежден.")
            return False
        except Exception as e:
            # Другие возможные ошибки при работе с файлами
            logging.error(f"Ошибка при распаковке архива {archive_path}: {e}")
            return False

    def _check_for_updates(self):
        """
        Проверяет, нужно ли скачивать новые данные.
        (Базовая реализация - всегда скачивает, если URL не пустой)

        В будущем можно реализовать проверку по HTTP-заголовкам (ETag, Last-Modified)
        или сравнивать хэш файла, если он предоставляется порталом.
        """
        logging.info("Проверка необходимости обновления данных...")
        if not self.data_url or self.data_url == 'URL_К_ДАННЫМ_РОСОБРНАДЗОРА': # Проверяем, что URL задан
            logging.warning("URL данных Рособрнадзора не настроен в конфигурации. Загрузка невозможна.")
            return False

        # TODO: Реализовать реальную проверку обновлений
        # Пример:
        # 1. Получить метаданные последней загрузки (дата, ETag) из self.metadata_file
        # 2. Сделать HEAD-запрос к self.data_url, чтобы получить заголовки сервера.
        # 3. Сравнить ETag или Last-Modified.
        # 4. Если данные изменились, вернуть True.

        logging.info("Требуется загрузка данных (базовая проверка).")
        return True # Пока что всегда возвращаем True, если URL задан

    def _parse_xml_files(self):
        """
        Парсит XML-файлы из директории кэша.
        Парсит XML-файлы из директории кэша, извлекая информацию об организациях и программах.
        Использует iterparse для эффективной обработки больших файлов.
        Основано на структуре data-20160713.xml.

        Returns:
            list: Список словарей, где каждый словарь представляет одну организацию
                  со вложенным списком программ.
                  Пример: [{'ogrn': '...', 'full_name': '...', 'programs': [...]}, ...]
                  Возвращает пустой список, если XML-файлы не найдены или произошла ошибка.
        """
        logging.info(f"Начало парсинга XML-файлов из {self.cache_path}...")
        # Ищем все XML файлы в директории кэша
        xml_files = glob.glob(os.path.join(self.cache_path, '*.xml'))
        if not xml_files:
            logging.warning("XML файлы для парсинга не найдены.")
            return []

        all_organizations_data = []
        # Обрабатываем каждый найденный XML-файл
        for xml_file_path in xml_files:
            logging.info(f"Парсинг файла: {xml_file_path}")
            organizations_in_file = []
            try:
                # Используем iterparse для потокового парсинга.
                # Итерируемся по основному тегу <Certificate>
                certificate_tag = 'Certificate'
                logging.info(f"Используется основной тег: '{certificate_tag}'")
                context = etree.iterparse(xml_file_path, events=('end',), tag=certificate_tag, recover=True)

                for event, cert_elem in context:
                    # Извлекаем данные об организации из <ActualEducationOrganization>
                    org_elem = cert_elem.find('ActualEducationOrganization')
                    if org_elem is None:
                        logging.warning(f"Пропущен сертификат без данных об организации (<ActualEducationOrganization>) в {xml_file_path}")
                        cert_elem.clear()
                        while cert_elem.getprevious() is not None: del cert_elem.getparent()[0]
                        continue

                    org_data = {
                        'full_name': self._get_text(org_elem, 'FullName'),
                        'short_name': self._get_text(org_elem, 'ShortName'),
                        'ogrn': self._get_text(org_elem, 'OGRN'),
                        'inn': self._get_text(org_elem, 'INN'),
                        'address': self._get_text(org_elem, 'PostAddress'),
                        'is_branch': self._get_text(org_elem, 'IsBranch', '0') == '1',
                        # Предполагаем, что OGRN родителя берется из <Certificate>, если это филиал
                        'parent_ogrn': self._get_text(cert_elem, 'EduOrgOGRN') if self._get_text(org_elem, 'IsBranch', '0') == '1' else None,
                        'region_name': self._get_text(org_elem, 'RegionName'), # Используем регион из ActualEducationOrganization
                        'programs': []
                    }

                    # Проверяем наличие ОГРН организации
                    if not org_data['ogrn']:
                        # Исправляем имя переменной в f-строке логирования
                        logging.warning(f"Пропущена организация без ОГРН в {xml_file_path}. Сертификат ID: {self._get_text(cert_elem, 'Id')}. Содержимое элемента: {etree.tostring(cert_elem, encoding='unicode')}")
                        # Убедимся, что используем cert_elem для очистки памяти
                        cert_elem.clear()
                        # И здесь тоже cert_elem
                        while cert_elem.getprevious() is not None:
                            del cert_elem.getparent()[0]
                        continue

                    # Извлекаем данные об аккредитованных программах из приложений (<Supplements>)
                    supplements_elem = cert_elem.find('Supplements')
                    if supplements_elem is not None:
                        for supp_elem in supplements_elem.findall('Supplement'):
                            programs_elem = supp_elem.find('EducationalPrograms')
                            if programs_elem is not None:
                                for program_elem in programs_elem.findall('EducationalProgram'):
                                    # Проверяем, аккредитована ли программа
                                    is_accredited = self._get_text(program_elem, 'IsAccredited', '1') == '0'
                                    if not is_accredited:
                                        continue # Пропускаем неаккредитованные

                                    prog_data = {
                                        'specialty_code': self._get_text(program_elem, 'ProgrammCode'), # Используем ProgrammCode
                                        'specialty_name': self._get_text(program_elem, 'ProgrammName'), # Используем ProgrammName
                                        'ugs_code': self._get_text(program_elem, 'UGSCode'),
                                        'ugs_name': self._get_text(program_elem, 'UGSName'),
                                        # 'study_forms': [] # Убрали формы обучения
                                    }
                                    # Добавляем программу, если есть код специальности/программы
                                    if prog_data['specialty_code']:
                                        org_data['programs'].append(prog_data)
                                    else:
                                        logging.debug(f"Пропущена программа без кода для ОГРН {org_data['ogrn']}")

                    organizations_in_file.append(org_data)

                    # Очищаем элемент <Certificate> и его предков
                    cert_elem.clear()
                    while cert_elem.getprevious() is not None:
                        del cert_elem.getparent()[0]

                # Очищаем контекст итератора
                del context

            except etree.XMLSyntaxError as e:
                logging.error(f"Ошибка синтаксиса XML в файле {xml_file_path}: {e}")
                continue # Переходим к следующему файлу
            except Exception as e:
                logging.error(f"Непредвиденная ошибка при парсинге файла {xml_file_path}: {e}")
                continue # Переходим к следующему файлу

            logging.info(f"В файле {xml_file_path} найдено {len(organizations_in_file)} организаций.")
            all_organizations_data.extend(organizations_in_file)

        logging.info(f"Парсинг XML-файлов завершен. Всего найдено {len(all_organizations_data)} организаций.")
        return all_organizations_data

    def _populate_db(self, organizations_data, app=None):
        """
        Заполняет базу данных данными, полученными из парсера XML.
        Использует SQLAlchemy для создания и обновления записей.
        Обрабатывает связи между моделями (регионы, специальности, формы обучения, филиалы).

        Args:
            organizations_data (list): Список словарей с данными организаций и программ.
            app (Flask, optional): Экземпляр Flask-приложения для получения контекста БД.
                                   Если None, будет создана автономная сессия.
        """
        logging.info("Начало заполнения базы данных...")
        if not organizations_data:
            logging.info("Нет данных для добавления в базу данных.")
            return

        # Используем менеджер контекста для управления сессией БД
        with self.session_scope(app) as session:
            # Словари для кэширования
            regions_cache = {}
            # study_forms_cache = {} # Убрали
            specialty_groups_cache = {}
            specialties_cache = {}
            organizations_cache = {}

            # --- Первый проход: Создаем/находим все организации ---
            logging.info("Первый проход: создание/поиск организаций...")
            for org_data in organizations_data:
                ogrn = org_data.get('ogrn')
                if not ogrn:
                    logging.warning(f"Пропуск организации без ОГРН: {org_data.get('full_name')}")
                    continue

                # Проверяем, не обрабатывали ли мы уже эту организацию (по OGRN)
                if ogrn in organizations_cache:
                    organization = organizations_cache[ogrn]
                else:
                    # Пытаемся найти организацию по ОГРН
                    organization = session.query(EducationalOrganization).filter_by(ogrn=ogrn).first()
                    if not organization:
                        # Если не найдена, создаем новую
                        # 1. Получаем или создаем регион (используем RegionName из XML)
                        region_name = org_data.get('region_name')
                        region = None
                        if region_name:
                            region_name = region_name.strip().capitalize() # Нормализуем
                            if region_name in regions_cache:
                                region = regions_cache[region_name]
                            else:
                                region, _ = self._get_or_create(session, Region, name=region_name)
                                regions_cache[region_name] = region
                        else:
                             # Пытаемся извлечь из адреса как запасной вариант
                             region_name_from_addr = self._extract_region_from_address(org_data.get('address', ''))
                             if region_name_from_addr:
                                 if region_name_from_addr in regions_cache:
                                     region = regions_cache[region_name_from_addr]
                                 else:
                                     region, _ = self._get_or_create(session, Region, name=region_name_from_addr)
                                     regions_cache[region_name_from_addr] = region

                        # 2. Создаем организацию
                        organization = EducationalOrganization(
                            full_name=org_data.get('full_name', 'Нет данных'),
                            short_name=org_data.get('short_name'),
                            ogrn=ogrn,
                            inn=org_data.get('inn'),
                            address=org_data.get('address'),
                            region=region # Присваиваем объект Region
                            # parent_id будет установлен во втором проходе
                        )
                        session.add(organization)
                        logging.debug(f"Добавлена новая организация: OGRN {ogrn}")
                        # Добавляем в кэш, чтобы избежать повторного создания
                        organizations_cache[ogrn] = organization
                        # Нужно выполнить flush, чтобы получить ID для связей, но коммитить будем в конце
                        session.flush()
                    else:
                        # Если организация найдена, обновляем данные (если нужно)
                        # TODO: Добавить логику обновления полей, если данные изменились
                        logging.debug(f"Найдена существующая организация: OGRN {ogrn}")
                        organizations_cache[ogrn] = organization # Добавляем в кэш

            # Коммитим первый проход (создание организаций), чтобы получить их ID
            try:
                 session.flush() # Применяем изменения для получения ID, но не коммитим транзакцию
                 logging.info("Первый проход завершен. Организации созданы/найдены.")
            except Exception as e:
                 logging.error(f"Ошибка во время flush после первого прохода: {e}")
                 session.rollback() # Откатываем все изменения первого прохода
                 return # Прерываем выполнение

            # --- Второй проход: Устанавливаем связи филиалов и создаем программы ---
            logging.info("Второй проход: установка связей филиалов и создание программ...")
            for org_data in organizations_data:
                ogrn = org_data.get('ogrn')
                if not ogrn or ogrn not in organizations_cache:
                    continue # Пропускаем, если организация не была создана/найдена

                organization = organizations_cache[ogrn]

                # Устанавливаем связь с головной организацией для филиалов
                if org_data.get('is_branch') and org_data.get('parent_ogrn'):
                    parent_ogrn = org_data['parent_ogrn']
                    # Ищем родительскую организацию по OGRN в кэше или в БД
                    parent_organization = organizations_cache.get(parent_ogrn) or \
                                          session.query(EducationalOrganization).filter_by(ogrn=parent_ogrn).first()
                    if parent_organization:
                        organization.parent_id = parent_organization.id
                        logging.debug(f"Установлена связь: Филиал {ogrn} -> Головная {parent_ogrn}")
                    else:
                        logging.warning(f"Не найдена головная организация с ОГРН {parent_ogrn} для филиала {ogrn}")

                # Обрабатываем образовательные программы
                for prog_data in org_data.get('programs', []):
                    specialty_code = prog_data.get('specialty_code')
                    ugs_code = prog_data.get('ugs_code')
                    if not specialty_code or not ugs_code:
                        logging.debug(f"Пропуск программы без кода специальности или УГСН для ОГРН {ogrn}")
                        continue

                    # Получаем или создаем УГСН
                    if ugs_code in specialty_groups_cache:
                        group = specialty_groups_cache[ugs_code]
                    else:
                        group, _ = self._get_or_create(session, SpecialtyGroup,
                                                       code=ugs_code,
                                                       defaults={'name': prog_data.get('ugs_name', 'Нет данных')})
                        specialty_groups_cache[ugs_code] = group

                    # Получаем или создаем Специальность
                    if specialty_code in specialties_cache:
                        specialty = specialties_cache[specialty_code]
                    else:
                        # Используем ProgrammCode как код специальности
                        specialty, _ = self._get_or_create(session, Specialty,
                                                           code=specialty_code,
                                                           defaults={'name': prog_data.get('specialty_name', 'Нет данных'),
                                                                     'group_id': group.id})
                        specialties_cache[specialty_code] = specialty

                    # Создаем образовательную программу
                    # Проверяем, существует ли уже такая программа (по org_id и spec_id)
                    existing_program = session.query(EducationalProgram).filter_by(
                        organization_id=organization.id,
                        specialty_id=specialty.id
                    ).first()

                    if not existing_program:
                        program = EducationalProgram(
                            organization_id=organization.id,
                            specialty_id=specialty.id
                        )
                        # Логика для форм обучения удалена
                        session.add(program)
                        logging.debug(f"Добавлена программа: ОГРН {ogrn}, Специальность {specialty_code}")
                    else:
                        logging.debug(f"Программа уже существует: ОГРН {ogrn}, Специальность {specialty_code}")

            logging.info("Второй проход завершен.")
            # Коммит в конце второго прохода (и всей транзакции) выполняется менеджером контекста session_scope

        logging.info("Заполнение базы данных завершено.")


    def run_update(self, app=None):
        """
        Запускает полный цикл обновления данных: проверка, скачивание, распаковка, парсинг, загрузка в БД.

        Args:
            app (Flask, optional): Экземпляр Flask-приложения для использования его контекста БД.
                                   Если None, будет создана автономная сессия SQLAlchemy.
        """
        logging.info("Запуск процесса обновления данных Рособрнадзора...")

        # Блок if __name__ == '__main__': ниже теперь не будет работать без create_app,
        # но он и не нужен, так как обновление запускается через команду CLI.
        # Мы оставим его закомментированным на случай, если понадобится автономный запуск в будущем.

        if not self._check_for_updates():
            logging.info("Обновление данных не требуется.")
            return

        # Определяем имя файла и путь для сохранения архива
        archive_filename = self._get_filename_from_url()
        # Проверяем, что имя файла не пустое
        if not archive_filename:
             logging.error("Не удалось определить имя файла для сохранения архива. Процесс обновления прерван.")
             return
        archive_path = os.path.join(self.cache_path, archive_filename)

        # Скачиваем данные
        if not self._download_data(archive_path):
            logging.error("Не удалось скачать данные. Процесс обновления прерван.")
            return

        # Распаковываем архив (если это ZIP)
        if archive_filename.lower().endswith('.zip'):
            # Перед распаковкой удалим старые XML файлы в кэше, чтобы избежать обработки устаревших данных
            logging.info("Удаление старых XML файлов из кэша...")
            existing_xml_files = glob.glob(os.path.join(self.cache_path, '*.xml'))
            for f_path in existing_xml_files:
                try:
                    os.remove(f_path)
                    logging.debug(f"Удален старый файл: {f_path}")
                except OSError as e:
                    logging.warning(f"Не удалось удалить старый файл {f_path}: {e}")

            # Распаковываем новый архив
            if not self._unpack_archive(archive_path):
                logging.error("Не удалось распаковать архив. Процесс обновления прерван.")
                return
            # Удаляем архив после успешной распаковки (опционально)
            try:
                os.remove(archive_path)
                logging.info(f"Удален исходный архив: {archive_path}")
            except OSError as e:
                logging.warning(f"Не удалось удалить архив {archive_path}: {e}")
        else:
            logging.warning(f"Файл {archive_filename} не является ZIP-архивом. Распаковка не выполнена.")
            # Здесь можно добавить обработку других форматов архивов (tar.gz и т.д.)
            # или просто оставить скачанный файл как есть, если он не архив.

        # Парсим XML
        parsed_data = self._parse_xml_files()

        # Заполняем БД
        if parsed_data:
             # Передаем app для использования контекста БД, если он есть
            self._populate_db(parsed_data, app=app)
        else:
             logging.warning("Парсинг не вернул данных для загрузки в БД.")

        # TODO: Улучшить проверку обновлений и обновить метаданные о последней загрузке

        logging.info("Процесс обновления данных Рособрнадзора завершен.")

# Блок if __name__ == '__main__': больше не будет работать без импорта create_app
# if __name__ == '__main__':
#     logging.info("Запуск DataLoader как отдельного скрипта (требует доработки).")
#     loader = DataLoader()
#     # Для автономного запуска нужно передать созданный app или настроить движок SQLAlchemy вручную
#     # loader.run_update()
