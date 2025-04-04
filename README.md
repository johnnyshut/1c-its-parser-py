# Парсер документации 1С ИТС

Инструмент для загрузки и локального сохранения документации с [сайта ИТС](https://its.1c.ru).

- [Парсер документации 1С ИТС](#парсер-документации-1с-итс)
  - [Возможности](#возможности)
  - [Установка](#установка)
    - [Предварительные требования](#предварительные-требования)
    - [Установка зависимостей](#установка-зависимостей)
  - [Настройка](#настройка)
    - [1. Аргументы командной строки](#1-аргументы-командной-строки)
    - [2. Файл .env (рекомендуется для безопасности)](#2-файл-env-рекомендуется-для-безопасности)
  - [Использование](#использование)
    - [Простой запуск](#простой-запуск)
    - [Полный пример с указанием всех параметров](#полный-пример-с-указанием-всех-параметров)
    - [Параметры командной строки](#параметры-командной-строки)
  - [Структура проекта](#структура-проекта)
  - [Особенности и рекомендации](#особенности-и-рекомендации)
  - [Устранение неполадок](#устранение-неполадок)

## Возможности

- Автоматическая авторизация на сайте 1С ИТС
- Извлечение структуры документации с учетом иерархии разделов
- Сохранение HTML-страниц с сохранением форматирования
- Загрузка и сохранение изображений
- Создание локального оглавления со ссылками на сохраненные страницы
- Поддержка ограничения количества загружаемых страниц
- Возможность возобновления загрузки с заданного раздела

## Установка

### Предварительные требования

- Python 3.6 или выше
- Google Chrome или Chromium
- ChromeDriver, соответствующий версии вашего браузера

### Установка зависимостей

```bash
pip install -r requirements.txt
```

## Настройка

Существует два способа указания учетных данных для авторизации:

### 1. Аргументы командной строки

Передайте логин и пароль напрямую через аргументы `--username` и `--password`.

### 2. Файл .env (рекомендуется для безопасности)

Скопируйте файл-шаблон `.env.example` в `.env` командой:

```cmd
copy .env.example .env
```

Затем откройте файл `.env` в любом текстовом редакторе и заполните свои учетные данные:

```txt
USERNAME=ваш_логин
PASSWORD=ваш_пароль
```

## Использование

### Простой запуск

```bash
python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru
```

### Полный пример с указанием всех параметров

```python
python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru/login --username 56572-45 --password 5c5ad902 --limit 50 --headless --verbose
```

### Параметры командной строки

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `--url` | Да | URL-адрес документации для загрузки |
| `--login` | Да | URL-адрес страницы входа |
| `--username` | Нет | Логин пользователя (если не указан, берется из .env) |
| `--password` | Нет | Пароль пользователя (если не указан, берется из .env) |
| `--limit` | Нет | Максимальное количество страниц для загрузки |
| `--headless` | Нет | Запуск браузера в фоновом режиме без отображения окна |
| `--verbose` | Нет | Включить подробный вывод отладочной информации в консоль |

## Структура проекта

После завершения работы программы в директории `out` будут созданы:

- `index.html` - оглавление документации со ссылками на загруженные страницы
- Папки `page_XXXX` для каждой загруженной страницы
  - `page.html` - содержимое страницы с корректными ссылками на изображения
  - `metadata.txt` - информация о странице (заголовок, уровень, URL)
  - `images/` - папка с изображениями для данной страницы

## Особенности и рекомендации

1. **Оптимизация скорости**: При указании параметра `--limit` скрипт оптимизирует процесс разворачивания узлов дерева, что значительно ускоряет работу программы.

2. **Headless режим**: По умолчанию браузер запускается в видимом режиме. Чтобы запустить в фоновом режиме без графического интерфейса, используйте параметр `--headless`.

3. **Возобновление загрузки**: Для продолжения загрузки после ошибки или прерывания, вы можете указать конкретный URL страницы, с которой нужно начать:

    ```bash
    python main.py --url https://its.1c.ru/db/edtdoc/content/123 --login https://login.1c.ru
    ```

4. **Использование локальной копии**: Для просмотра загруженной документации откройте файл `out/index.html` в любом современном браузере. В оглавлении доступны фильтры по уровням иерархии и инструменты навигации.

## Устранение неполадок

1. **Ошибки авторизации**: Убедитесь, что указаны правильные учетные данные. Проверьте URL страницы входа (`--login`).

2. **Таймауты при загрузке**: Для больших документаций может потребоваться больше времени. Используйте параметр `--limit` для ограничения количества страниц.

3. **Проблемы с отображением кириллицы**: Все файлы сохраняются в UTF-8, проверьте, что ваш браузер правильно определяет кодировку.

4. **Несоответствие уровней вложенности**: Если в консоли или результатах видны проблемы с определением уровней, используйте параметр `--verbose` для детальной диагностики.

5. **Изображения не отображаются в документации ERP**: Парсер включает специальную обработку для различных типов документации. Для документации ERP реализована дополнительная логика обработки путей изображений с учетом специфики этой документации. Если все же возникают проблемы с отображением:
   - Запустите скрипт без параметра `--headless` для отслеживания загрузки изображений
   - Проверьте папку `images` сохраненной страницы на наличие подпапок вида `.files`
   - В браузере откройте инструменты разработчика (F12) для анализа ошибок загрузки ресурсов
