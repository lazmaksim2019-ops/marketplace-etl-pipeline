<p align="center">
  <img src="assets/pipeline_schema.png" alt="Marketplace ETL Pipeline Architecture" width="100%" style="border-radius: 12px;">
</p>

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-teal?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/n8n-Self--hosted-red?style=for-the-badge&logo=n8n&logoColor=white" alt="n8n" />
  <img src="https://img.shields.io/badge/Gemini-Flash_Lite-gold?style=for-the-badge&logo=googlebard&logoColor=white" alt="Gemini" />
  <img src="https://img.shields.io/badge/Pydantic-v2-cyan?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic v2" />
</div>

<div align="center">
  <a href="https://github.com/lazmaksim2019-ops/marketplace-etl-pipeline/actions"><img src="https://img.shields.io/github/actions/workflow/status/lazmaksim2019-ops/marketplace-etl-pipeline/ci.yml?branch=master&style=for-the-badge&logo=githubactions&label=CI/CD" alt="CI/CD" /></a>
  <a href="https://codecov.io/gh/lazmaksim2019-ops/marketplace-etl-pipeline"><img src="https://img.shields.io/codecov/c/github/lazmaksim2019-ops/marketplace-etl-pipeline?style=for-the-badge&logo=codecov&label=Coverage" alt="Codecov" /></a>
  <a href="https://github.com/lazmaksim2019-ops/marketplace-etl-pipeline"><img src="https://img.shields.io/github/last-commit/lazmaksim2019-ops/marketplace-etl-pipeline?style=for-the-badge&logo=github&color=8b5cf6" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT" />
</div>

<h1 align="center">
  🤖 Асинхронный ИИ-Парсер каталогов и ETL-конвейер для маркетплейсов
</h1>

<p align="center">
  <b>Промышленный отказоустойчивый B2B-пайплайн автоматизации e-commerce.</b>
  Сквозная интеграция n8n + Python (FastAPI) + Google Gemini API
  для массового импорта и ИИ-уникализации контента.
</p>

> **⚡ Ключевая бизнес-ценность:** Автоматизирует рутину контент-менеджеров по переносу товаров от поставщиков или конкурентов. Система берет на себя парсинг, обход блокировок, глубокий рерайт (удаление чужих брендов, SEO-насыщение) и подготовку валидных данных для загрузки в маркетплейс в один клик.

---

## 🏗 Архитектура (System Design)

Пайплайн спроектирован по канонам событийно-ориентированной архитектуры (EDA) с разделением ответственности: n8n отвечает за оркестрацию и временные задержки, а FastAPI-бэкенд — за вычислительные процессы (парсинг) и бизнес-логику ИИ-валидации.

```mermaid
graph TD
    Trigger[n8n: Schedule/Manual Trigger] -->|1. Получение пула ссылок| HTTP_List[n8n: HTTP Request URLs]
    HTTP_List -->|2. Разделение на батчи| Batcher[n8n: Batch Splitter]
    Batcher -->|3. Пауза 2с Rate Limiting| Wait[n8n: Wait Node]
    Wait -->|4. Запрос на извлечение данных| API_Parser[FastAPI: POST /api/parser/extract]
    API_Parser -->|5. Асинхронный HTTPX + BS4| TargetSite[Сайт-донор / Поставщик]
    API_Parser -->|6. Сырые данные товара| Wait
    Wait -->|7. Запрос на трансформацию| API_LLM[FastAPI: POST /api/parser/transform]
    API_LLM -->|8. Вызов Gemini через SOCKS5-прокси| Gemini[Google Gemini 3.1 Flash Lite]
    Gemini -->|9. JSON-ответ| Validator[FastAPI: Pydantic v2 Validation Layer]
    Validator -->|10. Валидный структурированный контент| Wait
    Wait -->|11. Загрузка в кабинет| API_Upload[FastAPI: POST /api/marketplace/mock-upload]
```

---

## 💎 Промышленные B2B-стандарты

### Rate Limiting & Safety
Данные разбиваются на изолированные батчи по **1 товару**. Между батчами — задержка **2 секунды** (Wait Node n8n), что гарантирует отсутствие блокировки по HTTP 429.

### Error Isolation
Сбой при парсинге одной битой ссылки или таймаут Gemini не останавливают весь конвейер. `continueOnFail: true` в n8n + логирование ошибок на стороне FastAPI.

### SOCKS5/HTTP-прокси
Встроенная поддержка прокси для стабильного доступа к Gemini API из инфраструктуры РФ. Прокси автоматически прокидываются как в `httpx.AsyncClient`, так и в SDK Gemini.

### Pydantic v2 Validation
Жёсткая валидация схемы ответа перед отправкой в маркетплейс исключает «галлюцинации» языковых моделей:

```python
class CleanProductData(BaseModel):
    original_sku: str
    clean_title: str
    clean_description: str
    extracted_specs: dict
    media_urls: list[str]
```

---

## 📡 API Endpoints

| Метод | Эндпоинт | Описание | Вход | Выход |
|-------|----------|----------|------|-------|
| `GET` | `/health` | Статус бэкенда и Gemini | — | `{"status": "ok"}` |
| `POST` | `/api/parser/extract` | Парсинг страницы товара-донора | `{"url": "string"}` | `RawProductData` |
| `POST` | `/api/parser/transform` | SEO-рерайт через Gemini | `RawProductData` | `CleanProductData` |
| `POST` | `/api/marketplace/mock-upload` | Симуляция выгрузки в маркетплейс | `CleanProductData` | `UploadResponse` |

### Бортовые логи сервера

```text
2026-05-27 09:47:14 [INFO]  Marketplace ETL Pipeline starting up…
2026-05-27 09:47:14 [INFO]  Gemini: gemini-3.1-flash-lite | available: True
2026-05-27 09:48:01 [INFO]  === EXTRACT === https://books.toscrape.com/...
2026-05-27 09:48:01 [INFO]  Extract done: sku=SKU-260527-DF2Y85 title=Ноутбук Sony Model 5312
2026-05-27 09:48:02 [INFO]  === TRANSFORM === sku=SKU-260527-DF2Y85
2026-05-27 09:48:03 [INFO]  Upload success: marketplace_id=wb_3492239
```

---

## 🛠 Технологический стек

| Компонент | Технология | Назначение |
|-----------|------------|-----------|
| **Оркестратор** | n8n (Self-hosted) | Визуальное проектирование сценариев, батчинг, очередь |
| **Бэкенд** | Python 3.12 / FastAPI / Uvicorn | Асинхронная обработка запросов |
| **ИИ-ядро** | Google Gemini 3.1 Flash Lite | Структурированная JSON-генерация контента |
| **Парсинг** | BeautifulSoup4 / httpx / lxml | Асинхронный парсинг с пулом соединений |
| **Валидация** | Pydantic v2 | Строгие B2B-схемы на входе и выходе |
| **Тесты** | pytest / pytest-asyncio / httpx | Интеграционные тесты API |
| **CI/CD** | GitHub Actions | Lint → Test → Coverage → Build |
| **Контейнеризация** | Docker / multi-stage | Лёгкий деплой (финальный образ ~130 MB) |

---

## 💻 Быстрый старт

```bash
# 1. Клонирование
git clone https://github.com/lazmaksim2019-ops/marketplace-etl-pipeline.git
cd marketplace-etl-pipeline

# 2. Окружение
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

# 3. Зависимости
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx  # для тестов

# 4. Настройка
cp .env.example .env
# Заполните GEMINI_API_KEY и PROXY_* в .env

# 5. Запуск
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. Тесты
pytest -v --cov=. --cov-report=term
```

### Через Docker

```bash
docker build -t marketplace-etl-pipeline .
docker run -p 8000:8000 --env-file .env marketplace-etl-pipeline
```

### Импорт n8n-сценария
1. Запустите n8n (локально или в облаке).
2. Создайте новый Workflow.
3. Откройте `marketplace_pipeline.json`, скопируйте содержимое.
4. Вставьте на холст n8n — **Ctrl+V** (**Cmd+V**). Пайплайн импортируется автоматически!

---

## 📁 Структура репозитория

```
marketplace-etl-pipeline/
├── .github/workflows/ci.yml   # CI/CD конвейер
├── .dockerignore               # Исключения для Docker
├── .env.example                # Шаблон переменных окружения
├── .gitignore                  # Игнорируемые файлы
├── pyproject.toml              # Конфиг ruff, pytest, coverage
├── Dockerfile                  # Multi-stage сборка
├── README.md                   # Документация
├── rules.md                    # Протокол разработки ETL
├── requirements.txt            # Python-зависимости
├── main.py                     # FastAPI сервер (точка входа)
├── models.py                   # Pydantic v2 схемы данных
├── marketplace_pipeline.json   # n8n workflow
├── tests/                      # Тесты
│   ├── __init__.py
│   └── test_main.py
└── assets/
    └── pipeline_schema.png     # Архитектура пайплайна
```

---

## 🔄 Workflow CI/CD

| Этап | Команда | Описание |
|------|---------|----------|
| Lint | `ruff check . && ruff format --check .` | Статический анализ кода |
| Test | `pytest -v --cov=. --cov-report=xml --cov-report=term` | 15+ тестов с покрытием |
| Build | `docker build -t marketplace-etl-pipeline .` | Проверка сборки Docker |

---

## 📄 Лицензия

Распространяется под лицензией **MIT**.

---

---

## 👨‍💻 Автор

**Александр Лазаренко** — Fullstack / AI Developer (React + FastAPI + TypeScript + Python)

[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/lazalex81)
[![Email](https://img.shields.io/badge/Email-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:lazalex81@gmail.com)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/lazmaksim2019-ops)
