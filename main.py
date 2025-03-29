from __future__ import annotations

import argparse
import os
import re
import shutil
import time
import urllib.parse
from typing import List, Optional
from dotenv import load_dotenv
import hashlib

IMG_TAG_PATTERN = r'<img[^>]*?src="([^"]+)"[^>]*?>'

# Загрузка переменных окружения из .env файла
load_dotenv()

import requests
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, NoSuchFrameException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

class DocPage:
    """Класс для хранения информации о странице документации"""
    
    def __init__(self, url: str, title: str, level: int = 0, number: str = "") -> None:
        self.url: str = url
        self.title: str = title
        self.level: int = level
        self.number: str = number
        
    def __str__(self) -> str:
        return f"{self.number} {'  ' * self.level}{self.title}"

def download_image(browser: WebDriver, img_element: WebElement, save_dir: str) -> Optional[str]:
    """Скачивает изображение и заменяет путь в HTML"""
    try:
        src = img_element.get_attribute('src')
        if not src:
            return None
            
        # Получаем абсолютный URL изображения
        if src.startswith('/db/'):
            base_url = "https://its.1c.ru"
            src = f"{base_url}{src}"
        elif src.startswith('/'):
            base_url = urllib.parse.urlparse(browser.current_url).netloc
            src = f"https://{base_url}{src}"
        elif not src.startswith('http'):
            current_path = urllib.parse.urlparse(browser.current_url).path
            base_path = os.path.dirname(current_path)
            src = f"https://its.1c.ru{base_path}/{src}"
            
        # Загружаем изображение
        if args.verbose:
            print(f"Скачиваем изображение: {src}")
            
        os.makedirs(save_dir, exist_ok=True)
        
        # Определяем расширение файла из URL
        url_path = urllib.parse.urlparse(src).path
        file_ext = os.path.splitext(url_path)[1]
        if not file_ext:
            file_ext = '.png'  # По умолчанию используем png
        
        # Создаем имя файла на основе счетчика изображений в папке
        existing_images = len([f for f in os.listdir(save_dir) if f.endswith(file_ext)])
        new_filename = f"image{existing_images+1:03d}{file_ext}"
        
        # Путь для сохранения файла
        save_path = os.path.join(save_dir, new_filename)
        
        cookies = {}
        for cookie in browser.get_cookies():
            cookies[cookie['name']] = cookie['value']
        
        headers = {
            'Referer': browser.current_url,
        }
        
        response = requests.get(
            src,
            cookies=cookies,
            headers=headers,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            if args.verbose:
                print(f"Сохранено изображение: {save_path}")
            return new_filename
        else:
            if args.verbose:
                print(f"Ошибка при скачивании {src}: статус {response.status_code}")
                print(f"Заголовки ответа: {response.headers}")
            
    except Exception as e:
        if args.verbose:
            print(f"Ошибка при скачивании изображения {src}: {str(e)}")
    return None

def extract_doc_structure(browser: WebDriver) -> List[DocPage]:
    """Извлекает структуру документации из оглавления"""
    print("Извлекаем структуру документации...")
    
    # Ждем загрузки дерева
    tree = WebDriverWait(browser, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, "tree"))
    )
    
    # Разворачиваем все узлы дерева
    browser.execute_script("""
        function expandAllManually(element) {
            // Находим все свернутые узлы
            const collapsedNodes = element.querySelectorAll('.collapsed');
            console.log('Найдено свернутых узлов:', collapsedNodes.length);
            
            let changed = 0;
            
            // Вместо клика просто изменяем классы напрямую
            for (let i = 0; i < collapsedNodes.length; i++) {
                try {
                    const node = collapsedNodes[i];
                    
                    // Прокручиваем к узлу для уверенности
                    node.scrollIntoView({behavior: 'auto', block: 'center'});
                    
                    // Непосредственное изменение классов
                    node.classList.remove('collapsed');
                    node.classList.add('expanded');
                    
                    // Делаем дочерние элементы видимыми
                    const childUls = node.querySelectorAll('ul');
                    childUls.forEach(ul => {
                        ul.style.display = 'block';
                        ul.style.visibility = 'visible';
                    });
                    
                    changed++;
                } catch (e) {
                    console.error('Ошибка при развертывании узла:', e);
                }
            }
            
            console.log('Изменено узлов:', changed);
            return changed;
        }
        
        function waitAndExpandManually() {
            const tree = document.querySelector('.tree');
            if (!tree) {
                console.error('Дерево не найдено!');
                return;
            }
            
            // Подготовка дерева - делаем все элементы видимыми
            // Сначала убираем ограничения высоты
            tree.style.maxHeight = 'none';
            tree.style.overflow = 'visible';
            
            let attempts = 0;
            
            // Запускаем функцию разворачивания каждые 500мс
            let interval = setInterval(() => {
                const count = expandAllManually(tree);
                console.log('Попытка', attempts, 'изменено:', count);
                attempts++;
                
                // Продолжаем до 15 попыток или пока не останется свернутых узлов
                if (count === 0 || attempts >= 15) {
                    clearInterval(interval);
                    
                    // Финальный проход по всем элементам дерева
                    // Показываем все ul элементы
                    const allULs = tree.querySelectorAll('ul');
                    allULs.forEach(ul => {
                        ul.style.display = 'block';
                        ul.style.visibility = 'visible';
                    });
                    
                    // Показываем все li элементы
                    const allLIs = tree.querySelectorAll('li');
                    allLIs.forEach(li => {
                        li.style.visibility = 'visible';
                        li.style.display = 'block';
                        
                        // Иногда в li есть скрытые div с контентом
                        const divs = li.querySelectorAll('div');
                        divs.forEach(div => {
                            div.style.display = 'block';
                            div.style.visibility = 'visible';
                        });
                    });
                    
                    // Удаляем все обработчики событий на кнопках expand
                    // (чтобы предотвратить случайное сворачивание)
                    const expandButtons = tree.querySelectorAll('.expand');
                    expandButtons.forEach(button => {
                        const clone = button.cloneNode(true);
                        if (button.parentNode) {
                            button.parentNode.replaceChild(clone, button);
                        }
                    });
                    
                    console.log('Финальная обработка дерева завершена');
                }
            }, 500);
        }
        
        waitAndExpandManually();
    """)
    
    # Увеличиваем время ожидания для разворачивания сложного дерева
    time.sleep(10)
    
    # Проверяем, что дерево правильно развернуто
    collapsed_nodes = browser.execute_script("""
        return document.querySelectorAll('.tree .collapsed').length;
    """)
    
    if collapsed_nodes > 0 and args.verbose:
        print(f"Внимание: после разворачивания остались свернутые узлы ({collapsed_nodes})")
        
        # Принудительно разворачиваем оставшиеся узлы через DOM-манипуляции
        browser.execute_script("""
            // Принудительно разворачиваем все оставшиеся узлы
            document.querySelectorAll('.tree .collapsed').forEach(node => {
                node.classList.remove('collapsed');
                node.classList.add('expanded');
                
                // Показываем все подэлементы
                const childElements = node.querySelectorAll('*');
                childElements.forEach(el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                });
            });
            
            // Также находим все скрытые ul и показываем их
            document.querySelectorAll('.tree ul[style*="display: none"]').forEach(ul => {
                ul.style.display = 'block';
                ul.style.visibility = 'visible';
            });
        """)
        time.sleep(3)
        
        # Проверяем снова
        collapsed_nodes = browser.execute_script("""
            return document.querySelectorAll('.tree .collapsed').length;
        """)
        if collapsed_nodes > 0 and args.verbose:
            print(f"Всё еще остались свернутые узлы: {collapsed_nodes}")
            
            # Если узлы все еще свернуты, используем глубокое преобразование HTML
            browser.execute_script("""
                // Создаем глубокую копию дерева
                const tree = document.querySelector('.tree');
                if (tree) {
                    // Рекурсивно разворачиваем все узлы через модификацию DOM
                    function unfoldRecursive(element) {
                        // Разворачиваем текущий элемент
                        if (element.classList && element.classList.contains('collapsed')) {
                            element.classList.remove('collapsed');
                            element.classList.add('expanded');
                        }
                        
                        // Делаем элемент видимым
                        element.style.display = 'block';
                        element.style.visibility = 'visible';
                        
                        // Рекурсивно обрабатываем дочерние элементы
                        for (let i = 0; i < element.children.length; i++) {
                            unfoldRecursive(element.children[i]);
                        }
                    }
                    
                    // Запускаем рекурсивную обработку дерева
                    unfoldRecursive(tree);
                }
            """)
            time.sleep(2)
    
    pages: List[DocPage] = []
    processed_urls = set()
    current_section = [0]
    
    def clean_title(title: str) -> str:
        """Очищает заголовок от лишних символов и пробелов"""
        title = re.sub(r'\s+', ' ', title)
        title = title.replace('__', ' — ')
        return title.strip()
    
    def get_section_number(level: int, index: int) -> str:
        """Формирует номер раздела с учетом уровня вложенности"""
        while len(current_section) <= level:
            current_section.append(0)
        current_section[level] = index
        return '.'.join(str(num) for num in current_section[:level + 1]) + '.'
    
    def process_list_items(ul_element: WebElement, level: int = 0) -> None:
        # Сначала пробуем получить все ссылки и заголовки непосредственно через JavaScript
        if level == 0:
            try:
                # Запускаем JavaScript для извлечения всех ссылок независимо от структуры DOM
                js_results = browser.execute_script("""
                    function getAllLinksAndTexts() {
                        // Получаем все ссылки из DOM
                        const allLinks = Array.from(document.querySelectorAll('.tree a'));
                        
                        // Фильтруем и преобразуем
                        return allLinks
                            .filter(link => link.href && link.textContent.trim())
                            .map(link => {
                                // Определяем уровень вложенности на основе позиции в DOM
                                let level = 0;
                                let parent = link.parentElement;
                                
                                // Точнее определяем уровень вложенности
                                while (parent && parent.tagName !== 'BODY' && parent.className !== 'tree') {
                                    if (parent.tagName === 'UL') level++;
                                    parent = parent.parentElement;
                                }
                                
                                // Дополнительно проверяем количество родительских ul до элемента tree
                                const countParentULs = (elem) => {
                                    let count = 0;
                                    let current = elem;
                                    
                                    while (current && !current.classList.contains('tree')) {
                                        if (current.tagName === 'UL') count++;
                                        current = current.parentElement;
                                    }
                                    
                                    return count;
                                };
                                
                                const ulCount = countParentULs(link);
                                
                                // Корректируем уровень на основе нескольких признаков
                                // 1. Глубина вложенности ul
                                // 2. Отступ элемента (если доступен)
                                const computedStyle = window.getComputedStyle(link);
                                const paddingLeft = parseInt(computedStyle.paddingLeft) || 
                                                  parseInt(computedStyle.marginLeft) || 0;
                                
                                // Если есть большой отступ, учитываем его при определении уровня
                                const paddingLevel = Math.floor(paddingLeft / 20);
                                
                                // Выбираем наиболее правдоподобное значение уровня
                                const estimatedLevel = Math.max(level, ulCount, paddingLevel);
                                
                                // Проверяем, есть ли у ссылки особые классы, указывающие на уровень
                                const hasLevelClass = (link) => {
                                    for (let i = 0; i <= 10; i++) {
                                        if (link.classList.contains(`level-${i}`)) return i;
                                    }
                                    return -1;
                                };
                                
                                const classLevel = hasLevelClass(link);
                                if (classLevel >= 0) level = classLevel;
                                
                                return {
                                    url: link.href,
                                    title: link.textContent.trim(),
                                    level: estimatedLevel, 
                                    originalLevel: level,
                                    ulCount: ulCount,
                                    paddingLevel: paddingLevel
                                };
                            });
                    }
                    
                    return getAllLinksAndTexts();
                """)
                
                # Преобразуем результаты из JavaScript в объекты DocPage
                if js_results and len(js_results) > 0 and args.verbose:
                    print(f"JavaScript метод нашел {len(js_results)} ссылок")
                    
                    # Обрабатываем каждую ссылку
                    item_index = [0] * 10  # Поддерживаем счетчики для каждого уровня (до 10 уровней глубины)
                    
                    for item in js_results:
                        try:
                            url = item.get('url')
                            title = item.get('title')
                            level = item.get('level', 0)
                            
                            if url and title and url not in processed_urls and any(keyword in url for keyword in ["content", "bookmark", "browse"]):
                                item_index[level] += 1
                                # Сбрасываем счетчики для всех более глубоких уровней
                                for i in range(level + 1, len(item_index)):
                                    item_index[i] = 0
                                
                                # Формируем номер раздела
                                section_number = '.'.join(str(num) for num in item_index[:level + 1] if num > 0) + '.'
                                
                                page = DocPage(url, title, level, section_number)
                                pages.append(page)
                                processed_urls.add(url)
                                if args.verbose:
                                    print(f"Добавлена страница через JS: {page}")
                        except Exception as e:
                            if args.verbose:
                                print(f"Ошибка при обработке JS результата: {str(e)}")
            
            except Exception as e:
                if args.verbose:
                    print(f"Ошибка при JavaScript обходе дерева: {str(e)}")
            
            # Если JavaScript метод не дал результатов, используем стандартный метод
            if not pages:
                if args.verbose:
                    print("JavaScript метод не дал результатов, используем стандартный обход")
        
        # Стандартный обход дерева через Selenium
        items = ul_element.find_elements(By.CSS_SELECTOR, "li")
        item_index = 0
        
        for item in items:
            try:
                # Проверяем, является ли элемент видимым или свернутым
                is_collapsed = False
                try:
                    is_collapsed = 'collapsed' in item.get_attribute('class')
                except Exception as e:
                    pass
                    
                # Если элемент свернут, попробуем его развернуть
                if is_collapsed:
                    try:
                        # Используем JavaScript для разворачивания вместо поиска кнопки
                        # Это позволит избежать ошибки "no such element: .expand"
                        browser.execute_script("""
                            arguments[0].classList.remove('collapsed');
                            arguments[0].classList.add('expanded');
                            // Делаем дочерние элементы видимыми
                            const childUls = arguments[0].querySelectorAll('ul');
                            childUls.forEach(ul => {
                                ul.style.display = 'block';
                                ul.style.visibility = 'visible';
                            });
                        """, item)
                        
                        time.sleep(0.3)  # Даем время на разворачивание
                        if args.verbose:
                            print("Развернут элемент через JavaScript")
                    except Exception as e:
                        if args.verbose:
                            print(f"Не удалось развернуть элемент через JavaScript: {str(e)}")
                        
                        # Запасной вариант - пробуем найти кнопку expand
                        try:
                            expand_buttons = item.find_elements(By.CSS_SELECTOR, ".expand")
                            if expand_buttons:
                                # Прокручиваем страницу к кнопке, чтобы она была видна
                                browser.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", expand_buttons[0])
                                expand_buttons[0].click()
                                time.sleep(0.3)  # Даем время на разворачивание
                                if args.verbose:
                                    print("Развернут элемент через клик")
                        except Exception as e2:
                            if args.verbose:
                                print(f"Не удалось развернуть элемент: {str(e2)}")
                
                # Проверяем, является ли элемент видимым
                if not item.is_displayed():
                    # Попробуем прокрутить к элементу, чтобы сделать его видимым
                    try:
                        browser.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", item)
                        time.sleep(0.2)
                    except Exception as e:
                        pass
                    
                    # Если после прокрутки элемент всё ещё не виден, пропускаем его
                    if not item.is_displayed():
                        continue
                
                # Получаем ссылку и заголовок
                try:
                    link = item.find_element(By.CSS_SELECTOR, "a")
                    url = link.get_attribute("href")
                    title = clean_title(link.text)
                except Exception as e:
                    if args.verbose:
                        print("Пропущен элемент без ссылки или заголовка")
                    continue
                
                if not url or not title or url in processed_urls:
                    continue
                
                if any(keyword in url for keyword in ["content", "bookmark", "browse"]):
                    item_index += 1
                    section_number = get_section_number(level, item_index)
                    page = DocPage(url, title, level, section_number)
                    pages.append(page)
                    processed_urls.add(url)
                    if args.verbose:
                        print(f"Добавлена страница: {page}")
                
                # Обрабатываем вложенные элементы
                nested_lists = item.find_elements(By.CSS_SELECTOR, "ul")
                if nested_lists:
                    # Сбрасываем счетчики для следующего уровня
                    if len(current_section) > level + 1:
                        current_section[level + 1:] = [0] * (len(current_section) - level - 1)
                    for nested_list in nested_lists:
                        if nested_list.is_displayed():
                            process_list_items(nested_list, level + 1)
                            
            except Exception as e:
                if args.verbose:
                    print(f"Ошибка при обработке элемента: {str(e)}")
                continue
    
    # Начинаем обработку с корневого элемента
    process_list_items(tree)
    
    # Если стандартный обход дал мало результатов, попробуем JavaScript метод
    if len(pages) < 10:
        try:
            if args.verbose:
                print("Стандартный обход дал мало результатов, пробуем JavaScript метод")
                
            # Запускаем JavaScript для извлечения всех ссылок независимо от структуры DOM
            js_results = browser.execute_script("""
                function getAllLinksAndTexts() {
                    // Получаем все ссылки из DOM
                    const allLinks = Array.from(document.querySelectorAll('.tree a'));
                    
                    // Фильтруем и преобразуем
                    return allLinks
                        .filter(link => link.href && link.textContent.trim())
                        .map(link => {
                            // Определяем уровень вложенности на основе позиции в DOM
                            let level = 0;
                            let parent = link.parentElement;
                            
                            // Точнее определяем уровень вложенности
                            while (parent && parent.tagName !== 'BODY' && parent.className !== 'tree') {
                                if (parent.tagName === 'UL') level++;
                                parent = parent.parentElement;
                            }
                            
                            // Дополнительно проверяем количество родительских ul до элемента tree
                            const countParentULs = (elem) => {
                                let count = 0;
                                let current = elem;
                                
                                while (current && !current.classList.contains('tree')) {
                                    if (current.tagName === 'UL') count++;
                                    current = current.parentElement;
                                }
                                
                                return count;
                            };
                            
                            const ulCount = countParentULs(link);
                            
                            // Корректируем уровень на основе нескольких признаков
                            // 1. Глубина вложенности ul
                            // 2. Отступ элемента (если доступен)
                            const computedStyle = window.getComputedStyle(link);
                            const paddingLeft = parseInt(computedStyle.paddingLeft) || 
                                              parseInt(computedStyle.marginLeft) || 0;
                            
                            // Если есть большой отступ, учитываем его при определении уровня
                            const paddingLevel = Math.floor(paddingLeft / 20);
                            
                            // Выбираем наиболее правдоподобное значение уровня
                            const estimatedLevel = Math.max(level, ulCount, paddingLevel);
                            
                            // Проверяем, есть ли у ссылки особые классы, указывающие на уровень
                            const hasLevelClass = (link) => {
                                for (let i = 0; i <= 10; i++) {
                                    if (link.classList.contains(`level-${i}`)) return i;
                                }
                                return -1;
                            };
                            
                            const classLevel = hasLevelClass(link);
                            if (classLevel >= 0) level = classLevel;
                            
                            return {
                                url: link.href,
                                title: link.textContent.trim(),
                                level: estimatedLevel, 
                                originalLevel: level,
                                ulCount: ulCount,
                                paddingLevel: paddingLevel
                            };
                        });
                }
                
                return getAllLinksAndTexts();
            """)
            
            if js_results and len(js_results) > 0 and args.verbose and len(pages) < len(js_results):
                print(f"JavaScript извлек {len(js_results)} ссылок")
            
            # Очищаем текущие страницы
            pages = []
            processed_urls = set()
            
            # Анализируем уровни, чтобы определить правильную структуру
            min_level = min([item.get('level', 0) for item in js_results if 'level' in item], default=0)
            
            # Нормализуем уровни, чтобы минимальный был 0
            for item in js_results:
                if 'level' in item:
                    item['level'] = max(0, item['level'] - min_level)
            
            # Сортируем ссылки, чтобы они шли в правильном порядке
            # Сначала по уровню, потом по заголовку
            js_results.sort(key=lambda x: (x.get('level', 0), x.get('title', '')))
            
            # Сначала определим максимальный уровень для корректной нумерации
            max_level = max([item.get('level', 0) for item in js_results if 'level' in item], default=0)
            
            # Создаем счетчики для каждого уровня
            level_counters = {i: 0 for i in range(max_level + 1)}
            
            # Текущий контекст уровней для определения правильной нумерации
            current_level_context = [-1] * (max_level + 1)
            
            if args.verbose:
                print(f"Обработка ссылок, найдено уровней от {min_level} до {max_level}")
            
            for item in js_results:
                try:
                    url = item.get('url')
                    title = item.get('title')
                    level = item.get('level', 0)
                    
                    if not url or not title or url in processed_urls:
                        continue
                        
                    if any(keyword in url for keyword in ["content", "bookmark", "browse"]):
                        # Если мы переходим на новый уровень или возвращаемся на предыдущий
                        # Сбрасываем счетчики для всех более глубоких уровней
                        if level <= max_level:
                            # Обновляем счетчик текущего уровня
                            level_counters[level] += 1
                            
                            # Обновляем контекст для текущего уровня
                            current_level_context[level] = level_counters[level]
                            
                            # Сбрасываем все более глубокие уровни
                            for l in range(level + 1, max_level + 1):
                                level_counters[l] = 0
                                current_level_context[l] = -1
                        
                        # Формируем номер раздела на основе контекста
                        section_parts = []
                        for l in range(level + 1):
                            if current_level_context[l] > 0:
                                section_parts.append(str(current_level_context[l]))
                        
                        section_number = '.'.join(section_parts) + '.'
                        
                        # Создаем объект страницы
                        page = DocPage(url, title, level, section_number)
                        pages.append(page)
                        processed_urls.add(url)
                        
                        if args.verbose:
                            debug_info = f"(исходные данные: level={item.get('originalLevel', 'N/A')}, " + \
                                        f"ulCount={item.get('ulCount', 'N/A')}, " + \
                                        f"paddingLevel={item.get('paddingLevel', 'N/A')})"
                            print(f"Добавлена страница через JavaScript: {page} {debug_info}")
                except Exception as e:
                    if args.verbose:
                        print(f"Ошибка при обработке JS результата: {str(e)}")
        except Exception as e:
            if args.verbose:
                print(f"Ошибка при JavaScript извлечении ссылок: {str(e)}")
    
    if args.verbose:
        print("\nСтруктура документации:")
        for page in pages:
            print(f"{'  ' * page.level}{page.number} {page.title}")
    
    if not pages:
        print("Внимание: не найдено ни одной страницы в дереве")
        if args.verbose:
            print("Содержимое дерева:")
            print(tree.get_attribute('innerHTML'))
            
        # Крайний случай - используем любые ссылки со страницы
        try:
            print("Пробуем получить хотя бы какие-то ссылки со страницы...")
            all_links = browser.find_elements(By.TAG_NAME, "a")
            
            # Фильтруем только уникальные ссылки, относящиеся к документации
            for link in all_links:
                try:
                    url = link.get_attribute("href")
                    title = link.text.strip()
                    
                    if not url or not title or url in processed_urls:
                        continue
                        
                    if any(keyword in url for keyword in ["content", "bookmark", "browse"]):
                        page = DocPage(url, title, 0, f"{len(pages)+1}.")
                        pages.append(page)
                        processed_urls.add(url)
                except Exception:
                    continue
                    
            if pages:
                print(f"Удалось получить {len(pages)} ссылок напрямую со страницы")
        except Exception as e:
            if args.verbose:
                print(f"Не удалось получить ссылки напрямую: {str(e)}")
    else:
        print(f"Найдено {len(pages)} страниц")
    
    return pages

def _generate_html_styles() -> str:
    """Возвращает CSS стили для оглавления"""
    return """
        body { 
            font-family: Arial, sans-serif; 
            margin: 20px;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        /* Отображать метаданные всегда, если включен режим */
        body.show-metadata .metadata {
            display: block !important;
            position: static !important;
            margin-left: 20px !important;
            box-shadow: none !important;
            border: none !important;
            background: transparent !important;
            padding: 2px 0 !important;
            font-size: 0.8em !important;
            color: #777 !important;
        }
        body.show-metadata .toc-entry:hover .metadata {
            background: transparent !important;
        }
        .controls {
            margin: 15px 0;
            padding: 10px;
            background: #f8f8f8;
            border-radius: 5px;
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }
        .toc { 
            margin-left: 20px; 
            max-width: 100%;
            overflow-x: hidden;
        }
        .toc-entry { 
            margin: 8px 0;
            position: relative;  /* Для позиционирования метаданных */
            padding: 3px 5px;    /* Небольшие отступы для лучшего вида при наведении */
            overflow: hidden;    /* Обрезаем выходящий контент */
            border-radius: 4px;
        }
        /* Контейнер для строки с заголовком и кнопками */
        .entry-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        /* Контейнер для действий (кнопок) */
        .actions {
            display: flex;
            align-items: center;
            gap: 4px;
            opacity: 0.2;
            transition: opacity 0.2s;
        }
        .toc-entry:hover .actions {
            opacity: 1;
        }
        /* Кнопка открытия оригинальной страницы */
        .original-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            color: #666;
            border-radius: 4px;
            transition: all 0.2s;
        }
        .original-link:hover {
            background-color: rgba(0, 119, 204, 0.1);
            color: #0077cc;
        }
        .original-link svg {
            width: 14px;
            height: 14px;
        }
        /* Подсветка строки при наведении */
        .toc-entry:hover {
            background-color: rgba(0, 0, 0, 0.03);
        }
        .title {
            color: #2156a5;
            text-decoration: none;
            font-size: 1.1em;
            display: block;      /* Блочный элемент для стабильного отображения */
            word-wrap: break-word; /* Перенос длинных слов */
            overflow-wrap: break-word;
            max-width: 100%;    /* Ограничиваем ширину */
            width: fit-content;  /* По содержимому */
            overflow: hidden;    /* Прячем вышедший за границы текст */
        }
        /* Ссылка на оригинальный URL */
        .url-link {
            color: #0077cc;
            text-decoration: none;
            word-break: break-all;
        }
        .url-link:hover {
            text-decoration: underline;
            color: #0055aa;
        }
        /* Класс для очень длинных заголовков */
        .title.truncated {
            white-space: nowrap;
            text-overflow: ellipsis;
        }
        .title:hover { 
            text-decoration: underline;
        }
        .level-0 { 
            margin: 20px 0 10px 0; 
            font-size: 1.2em; 
            font-weight: bold;
            border-bottom: 1px solid #eee;
            padding-bottom: 5px;
        }
        .metadata {
            font-size: 0.85em;
            color: #666;
            position: absolute;
            background: #f5f5f5;
            border: 1px solid #ddd;
            padding: 5px 10px;
            border-radius: 4px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            z-index: 10;
            display: none;
            top: calc(100% + 5px); /* Отступ от элемента */
            left: 20px;
            min-width: 200px;
            max-width: 600px;
            white-space: nowrap; /* Предотвращаем перенос текста внутри метаданных */
        }
        /* Слегка затемняем метаданные при постоянном отображении */
        body.show-metadata .metadata {
            opacity: 0.8;
        }
        body.show-metadata .toc-entry:hover .metadata {
            opacity: 1;
        }
        .toc-entry:hover .metadata { display: block; }
        .section {
            margin: 20px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .section-title {
            font-size: 1.3em;
            color: #333;
            margin-bottom: 10px;
            padding: 8px;
            border-bottom: 1px solid #ddd;
            border-radius: 4px;
            background-color: #f4f4f4;
        }
        button {
            padding: 8px 15px;
            background-color: #4285f4;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        button:hover {
            background-color: #3367d6;
        }
        /* Активное состояние кнопки */
        button.active {
            background-color: #1c3aa9;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
            position: relative;
        }
        button.active::after {
            content: '✓';
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 12px;
        }
        /* Адаптивные стили для маленьких экранов */
        @media (max-width: 768px) {
            .controls {
                flex-direction: column;
            }
            .controls button {
                width: 100%;
                margin: 2px 0;
                text-align: left;
                padding-left: 15px;
            }
            .toc {
                margin-left: 10px;
            }
            .metadata {
                max-width: 90%;
            }
        }
    """

def _generate_toc_entry(page: DocPage, index: int) -> str:
    """Генерирует HTML для одного элемента оглавления"""
    # Добавляем больше отступов для корректного отображения уровней
    indentation = page.level * 30  # 30px на каждый уровень вложенности
    
    return f"""
        <div class="toc-entry level-{page.level}" style="margin-left: {indentation}px;">
            <div class="entry-row">
                <a class="title" href="page_{index:04d}/page.html" title="{page.title}">{page.title}</a>
                <div class="actions">
                    <a href="{page.url}" target="_blank" class="original-link" title="Открыть оригинальную страницу">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                    </a>
                </div>
            </div>
            <div class="metadata">
                <div><strong>URL:</strong> <a href="{page.url}" target="_blank" class="url-link">{page.url}</a></div>
                <div><strong>Уровень:</strong> {page.level}</div>
                <div><strong>Номер:</strong> {page.number}</div>
            </div>
        </div>"""

def save_all_pages(browser: webdriver.WebDriver, pages: List[DocPage], limit: int = None) -> None:
    """Сохраняет все страницы документации"""
    if limit is not None:
        pages = pages[:limit]
        print(f"Ограничение: будет сохранено {len(pages)} страниц")
    
    # Создаем оглавление в HTML
    toc_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Оглавление документации</title>
    <style>{_generate_html_styles()}</style>
</head>
<body>
    <h1>Оглавление документации</h1>
    
    <div class="controls">
        <button data-level="1" class="level-filter">Показать только уровень 1</button>
        <button data-level="2" class="level-filter">Показать до уровня 2</button>
        <button data-level="3" class="level-filter">Показать до уровня 3</button>
        <button data-level="10" class="level-filter active">Показать все уровни</button>
        <button id="toggle-metadata">Показать/скрыть метаданные</button>
    </div>
    
    <div class="toc">
"""
    
    # Группируем страницы по основным разделам (уровень 0)
    current_level0 = None
    for i, page in enumerate(pages, 1):
        if page.level == 0:
            if current_level0 is not None:
                toc_html += "    </div>\n</div>\n"
            
            section_id = f"section_{i}"
            toc_html += f'<div class="section" id="{section_id}">\n'
            toc_html += f'    <div class="section-title">{page.title}</div>\n'
            toc_html += '    <div class="section-content">\n'
            current_level0 = page.title
            
        toc_html += _generate_toc_entry(page, i)
    
    if current_level0 is not None:
        toc_html += "    </div>\n</div>\n"
    
    toc_html += """
    </div>
    
    <script>
    // Переключение уровней с сохранением активного состояния
    document.querySelectorAll('.level-filter').forEach(button => {
        button.addEventListener('click', function() {
            const maxLevel = parseInt(this.getAttribute('data-level'));
            
            // Снимаем активное состояние со всех кнопок
            document.querySelectorAll('.level-filter').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Добавляем активное состояние текущей кнопке
            this.classList.add('active');
            
            // Показываем/скрываем элементы в зависимости от их уровня
            for (let i = 0; i <= 10; i++) {
                const elements = document.querySelectorAll('.level-' + i);
                
                for (let elem of elements) {
                    if (i <= maxLevel) {
                        elem.style.display = 'block';
                    } else {
                        elem.style.display = 'none';
                    }
                }
            }
            
            // Сохраняем выбор в localStorage
            localStorage.setItem('selectedLevel', maxLevel);
        });
    });
    
    // Переключение метаданных
    document.getElementById('toggle-metadata').addEventListener('click', function() {
        const body = document.body;
        const isActive = body.classList.contains('show-metadata');
        
        if (isActive) {
            body.classList.remove('show-metadata');
            this.classList.remove('active');
            localStorage.setItem('showMetadata', 'false');
        } else {
            body.classList.add('show-metadata');
            this.classList.add('active');
            localStorage.setItem('showMetadata', 'true');
        }
    });
    
    // При загрузке страницы
    document.addEventListener('DOMContentLoaded', function() {
        // Восстанавливаем выбранный уровень из localStorage
        const savedLevel = localStorage.getItem('selectedLevel');
        if (savedLevel) {
            const levelButton = document.querySelector(`.level-filter[data-level="${savedLevel}"]`);
            if (levelButton) {
                levelButton.click();
            }
        }
        
        // Восстанавливаем состояние отображения метаданных
        const showMetadata = localStorage.getItem('showMetadata');
        if (showMetadata === 'true') {
            document.getElementById('toggle-metadata').click();
        }
        
        // Инициализация тултипов для длинных названий
        const titles = document.querySelectorAll('.title');
        titles.forEach(title => {
            // Если текст слишком длинный, добавляем эллипсис
            if (title.offsetWidth < title.scrollWidth) {
                title.classList.add('truncated');
            }
        });
    });
    </script>
</body>
</html>"""
    
    # Сохраняем оглавление
    os.makedirs('out', exist_ok=True)
    with open(os.path.join('out', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(toc_html)
    
    # Сохраняем страницы
    total = len(pages)
    for i, page in enumerate(pages, 1):
        try:
            if args.verbose:
                print(f"\nОбработка страницы {i}/{total}")
                print(f"Заголовок: {page.title}")
                print(f"Уровень: {page.level}")
                print(f"URL: {page.url}")
            else:
                print(f"Обработка: {i}/{total} - {page.title}")
            
            page_dir = os.path.join('out', f"page_{i:04d}")
            os.makedirs(page_dir, exist_ok=True)
            
            with open(os.path.join(page_dir, 'metadata.txt'), 'w', encoding='utf-8') as f:
                f.write(f"Title: {page.title}\n")
                f.write(f"Level: {page.level}\n")
                f.write(f"URL: {page.url}\n")
            
            browser.get(page.url)
            time.sleep(3)
            save_iframe_content(browser, "w_metadata_doc_frame", output_dir=page_dir)
            
            # Упрощаем пути к изображениям
            if simplify_image_paths(page_dir):
                if args.verbose:
                    print(f"Упрощены пути к изображениям для страницы {page.title}")
            
        except Exception as e:
            print(f"Ошибка при сохранении страницы {page.title}")
            if args.verbose:
                print(f"Детали: {str(e)}")
            continue

def save_iframe_content(browser, iframe_id, output_dir='out'):
    """Сохраняем содержимое iframe"""
    try:
        WebDriverWait(browser, 15).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, iframe_id))
        )
        if args.verbose:
            print("Переключились в iframe")
        
        try:
            WebDriverWait(browser, 15).until(
                lambda x: x.execute_script("return document.readyState") == "complete"
            )
            if args.verbose:
                print("readyState iframe complete")
            
            images_dir = os.path.join(output_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)
            
            images = browser.find_elements(By.TAG_NAME, "img")
            if args.verbose:
                print(f"Найдено изображений: {len(images)}")
            
            # Словарь для отслеживания уже скачанных изображений
            processed_images = {}
            
            for img in images:
                src = img.get_attribute('src')
                if args.verbose:
                    print(f"Обрабатываем изображение: {src}")
                
                # Если такой URL уже обрабатывался, используем существующий путь
                if src in processed_images:
                    new_src = processed_images[src]
                    img_path = f"images/{new_src}"
                    if args.verbose:
                        print(f"Используем существующий путь: {img_path}")
                else:
                    # Загружаем новое изображение
                    new_src = download_image(browser, img, images_dir)
                    if new_src:
                        img_path = f"images/{new_src}"
                        processed_images[src] = new_src
                        if args.verbose:
                            print(f"Обновляем путь на: {img_path}")
                    elif args.verbose:
                        print(f"Не удалось скачать изображение: {src}")
                        continue
                
                # Обновляем путь в HTML
                browser.execute_script("""
                    arguments[0].setAttribute('src', arguments[1]);
                    if (arguments[0].hasAttribute('data-src')) {
                        arguments[0].setAttribute('data-src', arguments[1]);
                    }
                    // Удаляем классы, которые могут мешать отображению
                    arguments[0].classList.remove('incomplete');
                    // Удаляем лишние стили, оставляя только размеры
                    var style = arguments[0].getAttribute('style');
                    if (style) {
                        var sizeStyles = [];
                        if (style.includes('width')) {
                            sizeStyles.push('width: ' + arguments[0].width + 'px');
                        }
                        if (style.includes('height')) {
                            sizeStyles.push('height: ' + arguments[0].height + 'px');
                        }
                        if (sizeStyles.length > 0) {
                            arguments[0].setAttribute('style', sizeStyles.join('; '));
                        } else {
                            arguments[0].removeAttribute('style');
                        }
                    }
                """, img, img_path)
            
            # Получаем обновленный HTML-код
            iframe_content = browser.page_source
            
            # Регулярное выражение для поиска тегов img с атрибутами width и height
            img_pattern = re.compile(r'<img[^>]*src="images/([^"]+)"[^>]*width="([^"]+)"[^>]*height="([^"]+)"[^>]*>')
            
            # Находим все совпадения и заменяем на упрощенный тег
            for match in img_pattern.finditer(iframe_content):
                src, width, height = match.groups()
                old_tag = match.group(0)
                new_tag = f'<img src="images/{src}" width="{width}" height="{height}" alt="">'
                iframe_content = iframe_content.replace(old_tag, new_tag)
            
            # Заменяем все оставшиеся сложные пути для изображений
            iframe_content = re.sub(
                r'src="[^"]*?/([^/"]+\.(png|jpg|gif|jpeg))"', 
                r'src="images/\1"',
                iframe_content
            )
            
            # Обновляем или добавляем мета-тег с UTF-8
            if '<meta charset=' not in iframe_content and '<meta http-equiv="Content-Type"' not in iframe_content:
                iframe_content = re.sub(
                    r'<head[^>]*>',
                    r'<head>\n    <meta charset="utf-8">',
                    iframe_content
                )
            else:
                # Обновляем существующий мета-тег
                iframe_content = re.sub(
                    r'<meta[^>]*charset=[^>]*>',
                    r'<meta charset="utf-8">',
                    iframe_content
                )
                iframe_content = re.sub(
                    r'<meta[^>]*Content-Type[^>]*>',
                    r'<meta charset="utf-8">',
                    iframe_content
                )
            
            # Сохраняем содержимое в файл в UTF-8
            output_file = os.path.join(output_dir, 'page.html')
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(iframe_content)
            if args.verbose:
                print(f"Содержимое iframe сохранено в {output_file}")
                
            # Выполняем постобработку HTML для исправления путей к изображениям
            if post_process_html(output_file):
                if args.verbose:
                    print(f"Выполнена постобработка HTML для {output_file}")
            
        finally:
            browser.switch_to.default_content()
            if args.verbose:
                print("Вернулись к основному документу")
            
    except TimeoutException as e:
        print("Ошибка: таймаут при ожидании iframe")
        if args.verbose:
            print(f"Детали: {str(e)}")
        raise
    except NoSuchFrameException as e:
        print("Ошибка: не удалось переключиться на iframe")
        if args.verbose:
            print(f"Детали: {str(e)}")
        raise
    except Exception as e:
        print("Ошибка при обработке iframe")
        if args.verbose:
            print(f"Детали: {str(e)}")
        raise

def clean_output_directory(directory='out'):
    """Очищает каталог вывода, если он существует"""
    if os.path.exists(directory):
        print(f"Очистка каталога {directory}")
        shutil.rmtree(directory)
    os.makedirs(directory, exist_ok=True)

def post_process_html(html_file_path):
    """Постобработка HTML файла для исправления путей к изображениям"""
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Регулярное выражение для поиска всех тегов img
        img_tag_pattern = re.compile(IMG_TAG_PATTERN)
        
        # Ищем все теги img
        for match in img_tag_pattern.finditer(content):
            full_img_tag = match.group(0)
            src = match.group(1)
            
            # Проверяем, требуется ли коррекция пути
            if 'images/' not in src and ('/' in src or '%' in src or 'http' in src):
                # Извлекаем имя файла из сложного пути
                filename = src.split('/')[-1]
                # Заменяем сложный путь на простой
                new_src = f"images/{filename}"
                new_img_tag = full_img_tag.replace(src, new_src)
                content = content.replace(full_img_tag, new_img_tag)
        
        # Упрощаем все теги img
        content = re.sub(
            r'<img[^>]*?src="images/([^"]+)"[^>]*?width="([^"]*)"[^>]*?height="([^"]*)"[^>]*?>', 
            r'<img src="images/\1" width="\2" height="\3" alt="">',
            content
        )
        
        # Убираем атрибуты, которые могут мешать отображению
        content = re.sub(
            r'<img([^>]*?)class="[^"]*?incomplete[^"]*?"([^>]*?)>', 
            r'<img\1\2>', 
            content
        )
        
        # Заменяем все URL-закодированные пути
        encoded_path_pattern = re.compile(r'images/[^"]*?%[^"]*?\.(?:png|jpg|gif|jpeg)')
        
        # Находим все закодированные пути
        for match in encoded_path_pattern.finditer(content):
            encoded_path = match.group(0)
            # Формируем новый путь с порядковым номером
            new_path = f"images/image{len(set(encoded_path_pattern.findall(content)))}.png"
            content = content.replace(encoded_path, new_path)
        
        # Заменяем ссылки на файлы в подкаталогах на прямые ссылки
        content = re.sub(
            r'images/[^"]+?/([^/"]+\.(?:png|jpg|gif|jpeg))', 
            r'images/\1',
            content
        )
        
        # Сохраняем обработанный файл
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return True
    except Exception as e:
        if not args.headless:
            print(f"Ошибка при постобработке HTML: {str(e)}")
        return False

def clean_img_tags(html_content):
    """Очищает теги img от ненужных атрибутов, оставляя только src, width, height и alt"""
    # Регулярное выражение для поиска тегов img
    img_pattern = re.compile(IMG_TAG_PATTERN)
    
    # Словарь для хранения замен
    replacements = {}
    
    # Обрабатываем каждый найденный тег img
    for match in img_pattern.finditer(html_content):
        full_tag = match.group(0)
        src = match.group(1)
        
        # Если тег уже обработан, пропускаем
        if full_tag in replacements:
            continue
        
        # Получаем значения width и height, если они есть
        width_match = re.search(r'width="([^"]+)"', full_tag)
        width = width_match.group(1) if width_match else ""
        
        height_match = re.search(r'height="([^"]+)"', full_tag)
        height = height_match.group(1) if height_match else ""
        
        # Создаем новый чистый тег
        if width and height:
            new_tag = f'<img src="{src}" width="{width}" height="{height}" alt="">'
        elif width:
            new_tag = f'<img src="{src}" width="{width}" alt="">'
        elif height:
            new_tag = f'<img src="{src}" height="{height}" alt="">'
        else:
            new_tag = f'<img src="{src}" alt="">'
        
        replacements[full_tag] = new_tag
    
    # Применяем все замены
    for old_tag, new_tag in replacements.items():
        html_content = html_content.replace(old_tag, new_tag)
    
    return html_content

def simplify_image_paths(page_dir):
    """Копирует все изображения из сложных путей в простую директорию изображений"""
    try:
        # Находим все подкаталоги с изображениями
        images_dir = os.path.join(page_dir, 'images')
        if not os.path.exists(images_dir):
            return False
            
        # Создаем простой каталог для изображений, если его нет
        simple_images_dir = os.path.join(page_dir, 'img')
        os.makedirs(simple_images_dir, exist_ok=True)
        
        # Счетчик изображений
        image_counter = 1
        
        # Словарь для отслеживания соответствий между старыми и новыми путями к файлам
        path_mapping = {}
        
        # Проходим по всем файлам в images и подкаталогах
        for root, dirs, files in os.walk(images_dir):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    # Полный путь к исходному файлу
                    src_path = os.path.join(root, file)
                    
                    # Получаем относительный путь от корня images
                    rel_path = os.path.relpath(src_path, images_dir)
                    
                    # Определяем расширение файла
                    _, ext = os.path.splitext(file)
                    
                    # Новое имя файла в формате imageNNN.ext
                    new_filename = f"image{image_counter:03d}{ext}"
                    dst_path = os.path.join(simple_images_dir, new_filename)
                    
                    # Копируем файл
                    shutil.copy2(src_path, dst_path)
                    
                    # Сохраняем соответствие путей
                    path_mapping[rel_path] = new_filename
                    
                    if args.verbose:
                        print(f"Скопирован файл {rel_path} -> {new_filename}")
                    
                    image_counter += 1
        
        # Обновляем HTML-файл, чтобы использовать новые пути
        html_file = os.path.join(page_dir, 'page.html')
        if os.path.exists(html_file):
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Получаем все ссылки на изображения в HTML
            img_tags = re.findall(r'<img[^>]*?src="([^"]+)"[^>]*?>', content)
            
            # Словарь для новых соответствий путей
            new_paths = {}
            
            # Обрабатываем каждую ссылку
            for src in img_tags:
                if src.startswith('images/'):
                    # Удаляем префикс images/
                    rel_path = src[7:]
                    
                    # Если есть соответствие в path_mapping, используем его
                    if rel_path in path_mapping:
                        new_paths[src] = f"img/{path_mapping[rel_path]}"
                    else:
                        # Попробуем найти подходящий файл по имени
                        filename = os.path.basename(rel_path)
                        for old_path, new_name in path_mapping.items():
                            if os.path.basename(old_path) == filename:
                                new_paths[src] = f"img/{new_name}"
                                break
                        else:
                            # Если не нашли, просто копируем с порядковым номером
                            new_name = f"image{len(new_paths)+1:03d}{os.path.splitext(filename)[1]}"
                            new_paths[src] = f"img/{new_name}"
            
            # Заменяем пути в HTML
            for old_path, new_path in new_paths.items():
                content = content.replace(f'src="{old_path}"', f'src="{new_path}"')
            
            # Очищаем теги img от ненужных атрибутов
            content = clean_img_tags(content)
            
            # Сохраняем обновленный HTML
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            if args.verbose:
                print(f"Обновлен HTML-файл {html_file}")
                
        return True
    except Exception as e:
        if args.verbose:
            print(f"Ошибка при упрощении путей к изображениям: {str(e)}")
        return False

def main():
    global args  # Перемещаем объявление в начало функции
    
    parser = argparse.ArgumentParser(
        description="""
Парсер документации 1С ИТС - инструмент для локального сохранения документации.

Примеры запуска:
  Простой запуск:
    python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru/login
  
  С авторизацией через командную строку:
    python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru/login --username user --password pass
  
  С ограничением количества страниц и запуском в фоновом режиме:
    python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru/login --limit 20 --headless
  
  С расширенным выводом для отладки:
    python main.py --url https://its.1c.ru/db/edtdoc --login https://login.1c.ru/login --verbose
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--url', required=True, help='URL документации для загрузки (например, https://its.1c.ru/db/edtdoc)')
    parser.add_argument('--login', required=True, help='URL страницы авторизации (например, https://login.1c.ru/login)')
    parser.add_argument('--username', required=False, help='Имя пользователя (если не указано, берется из .env файла)')
    parser.add_argument('--password', required=False, help='Пароль пользователя (если не указано, берется из .env файла)')
    parser.add_argument('--limit', type=int, help='Ограничение количества страниц для загрузки (по умолчанию - все страницы)')
    parser.add_argument('--headless', action='store_true', help='Запуск браузера в фоновом режиме без отображения окна')
    parser.add_argument('--verbose', action='store_true', help='Включить расширенный вывод для отладки')
    args = parser.parse_args()

    # Использование переменных окружения, если не указаны аргументы
    if not args.username:
        args.username = os.environ.get('USERNAME')
    if not args.password:
        args.password = os.environ.get('PASSWORD')
    
    # Проверка наличия учетных данных
    if not args.username or not args.password:
        raise ValueError("Необходимо указать username и password в аргументах или в файле .env")

    clean_output_directory()

    options = webdriver.ChromeOptions()
    if args.headless:
        options.add_argument('--headless=new')  # Использование современной реализации headless режима
        options.add_argument('--disable-gpu')  # Отключение GPU для headless режима
        options.add_argument('--disable-dev-shm-usage')  # Предотвращение ошибок в контейнерах
        options.add_argument('--no-sandbox')  # Для более стабильной работы
    
    # Оптимизация загрузки браузера
    options.add_argument('--disable-extensions')  # Отключение расширений
    options.add_argument('--disable-infobars')  # Отключение информационных сообщений
    options.add_argument('--disable-notifications')  # Отключение уведомлений
    options.add_argument('--disable-popup-blocking')  # Отключение блокировки всплывающих окон
    options.add_argument('--blink-settings=imagesEnabled=true')  # Включение загрузки изображений
    options.page_load_strategy = 'eager'  # Загрузка страницы не дожидаясь полной загрузки ресурсов
    
    # Дополнительные настройки для ускорения
    prefs = {
        'profile.default_content_setting_values.notifications': 2,  # Отключение уведомлений
        'profile.managed_default_content_settings.images': 1,  # Загрузка изображений (1-загружать, 2-блокировать)
        'disk-cache-size': 4096,  # Увеличение размера кэша
    }
    options.add_experimental_option('prefs', prefs)
    
    browser = webdriver.Chrome(options=options)
    browser.maximize_window()
    
    try:
        print("Авторизация...")
        browser.get(args.login)
        
        username_input = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        password_input = browser.find_element(By.NAME, "password")
        
        username_input.send_keys(args.username)
        password_input.send_keys(args.password)
        
        login_button = browser.find_element(By.CSS_SELECTOR, "input[type='submit']")
        login_button.click()
        
        time.sleep(2)
        
        print("Загрузка документации...")
        browser.get(args.url)
        time.sleep(2)
        
        pages = extract_doc_structure(browser)
        
        if args.limit:
            print(f"Сохранение {args.limit} страниц...")
        else:
            print("Сохранение всех страниц...")
        
        save_all_pages(browser, pages, args.limit)
        print("Готово!")
            
    except Exception as e:
        print("Ошибка при выполнении")
        if args.verbose:
            print(f"Детали: {str(e)}")
            print("URL в момент ошибки:", browser.current_url)
    finally:
        browser.quit()

if __name__ == "__main__":
    main()
