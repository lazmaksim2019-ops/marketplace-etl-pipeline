import os
import re
import json
import asyncio
import random
import logging
import string

from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException
from bs4 import BeautifulSoup

from models import (
    ExtractRequest,
    RawProductData,
    CleanProductData,
    UploadResponse,
)

# ── Environment ──────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")


def build_proxy_url() -> str | None:
    if not PROXY_HOST or not PROXY_PORT:
        return None
    if PROXY_USER and PROXY_PASS:
        return f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
    return f"http://{PROXY_HOST}:{PROXY_PORT}"


PROXY_URL = build_proxy_url()

# ── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("marketplace-pipeline")

# ── Gemini ───────────────────────────────────────────────────────

if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL

genai = None
GenerativeModel = None
_gemini_available = False

try:
    import google.generativeai as _genai

    _genai.configure(api_key=GEMINI_API_KEY)
    genai = _genai
    GenerativeModel = _genai.GenerativeModel
    _gemini_available = bool(GEMINI_API_KEY)
except Exception as exc:
    logger.warning("Gemini SDK init skipped: %s", exc)

# ── FastAPI app ──────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Marketplace ETL Pipeline starting up…")
    logger.info("Gemini model: %s | available: %s", GEMINI_MODEL, _gemini_available)
    if PROXY_URL:
        logger.info("Proxy: %s:%s", PROXY_HOST, PROXY_PORT)
    yield
    logger.info("Marketplace ETL Pipeline shut down.")


app = FastAPI(
    title="Marketplace ETL Pipeline",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Helpers ──────────────────────────────────────────────────────


def _get_httpx_client() -> httpx.AsyncClient:
    kwargs: Dict = {"timeout": httpx.Timeout(30.0, connect=10.0)}
    if PROXY_URL:
        kwargs["proxies"] = {"http://": PROXY_URL, "https://": PROXY_URL}
    return httpx.AsyncClient(**kwargs)


def _generate_sku() -> str:
    ts = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"SKU-{ts}-{rand}"


def _is_image_url(src: str) -> bool:
    ext = src.lower().split("?")[0]
    return any(ext.endswith(e) for e in [".jpg", ".jpeg", ".png", ".webp", ".avif"])


# ── Scraper ──────────────────────────────────────────────────────


async def _scrape_url(url: str) -> RawProductData | None:
    """Парсит страницу через BS4. Возвращает None при любой ошибке."""
    try:
        async with _get_httpx_client() as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("HTTP fetch failed for %s: %s", url, exc)
        return None

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # заголовок
        title_tag = soup.find("h1") or soup.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""

        # описание
        desc_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", attrs={"property": "og:description"})
            or soup.find("meta", attrs={"name": "twitter:description"})
        )
        raw_description = ""
        if desc_tag:
            raw_description = desc_tag.get("content", "") or desc_tag.get("value", "")

        if not raw_description:
            desc_div = soup.select_one(
                ".product-description, .description, [data-product-description]"
            )
            if desc_div:
                raw_description = desc_div.get_text(strip=True, separator=" ")

        # характеристики
        specs: Dict[str, str] = {}
        for row in soup.select(
            "table.attributes tr, .specs tr, "
            ".product-attribute, .characteristic, "
            "[class*=spec] tr, [class*=attribute] li"
        ):
            cells = row.find_all(["th", "td", "span", "div"])
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            if len(texts) >= 2:
                specs[texts[0]] = texts[1]

        if not specs:
            for li in soup.select("ul.specs li, ul.features li, [class*=spec] li"):
                txt = li.get_text(strip=True, separator=" ")
                if ":" in txt:
                    k, v = txt.split(":", 1)
                    specs[k.strip()] = v.strip()

        # изображения
        images: list[str] = []
        seen = set()
        for img in soup.select("img[src]"):
            src = img.get("src", "").strip()
            if not src or src.startswith("data:"):
                continue
            if not src.startswith("http"):
                src = _resolve_url(url, src)
            if src and src not in seen and _is_image_url(src):
                seen.add(src)
                images.append(src)

        images = images[:10]

        sku = _generate_sku()

        return RawProductData(
            original_sku=sku,
            raw_title=raw_title or f"Product from {url}",
            raw_description=raw_description or "No description extracted",
            raw_specs=specs or {"Note": "No structured specs found"},
            media_urls=images or ["https://via.placeholder.com/600"],
            source_url=url,
        )
    except Exception as exc:
        logger.error("BS4 parsing failed for %s: %s", url, exc)
        return None


def _resolve_url(base: str, path: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, path)


def _generate_mock_product(url: str) -> RawProductData:
    """Генерирует правдоподобные мок-данные при недоступности парсера."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc or url
    sku = _generate_sku()

    categories = ["Смартфон", "Наушники", "Ноутбук", "Планшет", "Часы"]
    brands = ["Xiaomi", "Samsung", "Apple", "Huawei", "Sony"]
    cat = random.choice(categories)
    brand = random.choice(brands)

    return RawProductData(
        original_sku=sku,
        raw_title=f"{cat} {brand} Model {random.randint(1000,9999)} ({domain})",
        raw_description=(
            f"Оригинальный {cat.lower()} {brand}. "
            f"Гарантия 12 месяцев. Доставка по всей РФ. "
            f"Характеристики: новейший процессор, большой объем памяти, "
            f"высококачественный дисплей. Цвет: черный/белый."
        ),
        raw_specs={
            "Бренд": brand,
            "Категория": cat,
            "Цвет": random.choice(["Черный", "Белый", "Синий"]),
            "Гарантия": "12 месяцев",
        },
        media_urls=[
            "https://via.placeholder.com/600/0000FF/FFFFFF?text=Photo1",
            "https://via.placeholder.com/600/FF0000/FFFFFF?text=Photo2",
        ],
        source_url=url,
    )


# ── Gemini transform ────────────────────────────────────────────


def _mock_transform(raw_data: RawProductData) -> CleanProductData:
    """Ручная mock-трансформация, когда Gemini недоступен."""
    clean_title = re.sub(
        r"\b(Xiaomi|Samsung|Apple|Honor|Huawei|Sony|Redmi)\b",
        "Премиум",
        raw_data.raw_title,
        flags=re.IGNORECASE,
    )
    clean_title = re.sub(r"\(.*?\)", "", clean_title).strip()

    return CleanProductData(
        original_sku=raw_data.original_sku,
        clean_title=clean_title,
        clean_description=(
            f"Купить {clean_title.lower()} по лучшей цене с доставкой по РФ. "
            f"Оригинальная гарантия, быстрая доставка. "
            f"Подходит для дома и офиса. Высокое качество."
        ),
        extracted_specs=(
            raw_data.raw_specs
            if isinstance(raw_data.raw_specs, dict)
            else {}
        ),
        media_urls=(
            raw_data.media_urls
            if isinstance(raw_data.media_urls, list)
            else []
        ),
    )


async def _call_gemini(raw_data: RawProductData) -> CleanProductData | None:
    """
    Отправляет сырые данные в Gemini, возвращает чистый продукт.
    При ошибке возвращает None — вызывающий решает, что делать.
    """
    if not _gemini_available:
        logger.info("Gemini unavailable — mock transform used")
        return None

    prompt = (
        "Преобразуй следующие сырые данные товара в clean-версию для маркетплейса.\n"
        "Правила:\n"
        "1. Полностью удали упоминания чужих брендов, магазинов, имен и артикулов.\n"
        "2. Обогати заголовок и описание целевыми SEO-ключами.\n"
        "3. characteristic — переведи названия характеристик на русский, "
        "удали значения, указывающие на бренд.\n"
        "4. Верни строго валидный JSON без markdown-обертки, со следующими ключами:\n"
        "   - original_sku (строка)\n"
        "   - clean_title (строка)\n"
        "   - clean_description (строка)\n"
        "   - extracted_specs (объект)\n"
        "   - media_urls (массив строк)\n\n"
        f"Исходные данные:\n{raw_data.model_dump_json(indent=2)}"
    )

    for attempt in range(2):
        try:
            model = GenerativeModel(
                model_name=f"models/{GEMINI_MODEL}",
                system_instruction=(
                    "Ты — e-commerce контент-инженер. Твоя задача — провести глубокий "
                    "рерайт текста, полностью удалить любые упоминания чужих брендов, "
                    "магазинов, имен или артикулов. Насытить текст целевыми SEO-ключами "
                    "и вернуть строго валидный JSON."
                ),
            )
            response = await model.generate_content_async(prompt)
            text = response.text.strip()

            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                text = json_match.group()

            parsed = json.loads(text)
            return CleanProductData(**parsed)
        except json.JSONDecodeError as exc:
            logger.error("Gemini returned invalid JSON (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.error("Gemini API error (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                await asyncio.sleep(1)

    return None


# ── Endpoints ────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "gemini_available": _gemini_available}


@app.post("/api/parser/extract", response_model=RawProductData)
async def extract_product(request: ExtractRequest):
    """
    Парсит страницу товара конкурента.
    Пытается через BeautifulSoup, при ошибке генерирует mock-данные.
    """
    url = str(request.url)
    logger.info("=== EXTRACT === %s", url)

    data = await _scrape_url(url)
    if data is None:
        logger.warning("Real scrape failed — using mock for %s", url)
        data = _generate_mock_product(url)

    logger.info(
        "Extract done: sku=%s title=%s",
        data.original_sku, data.raw_title[:80],
    )
    return data


@app.post("/api/parser/transform", response_model=CleanProductData)
async def transform_product(raw_data: RawProductData):
    """
    Принимает сырой JSON товара, отправляет в Gemini 3.1 Flash Lite
    для глубокого рерайта и уникализации. При ошибке Gemini —
    fallback на детерминированную mock-трансформацию.
    """
    logger.info("=== TRANSFORM === sku=%s", raw_data.original_sku)

    try:
        result = await _call_gemini(raw_data)
        if result is None:
            logger.warning("Gemini transform failed — using mock transform")
            result = _mock_transform(raw_data)

        logger.info(
            "Transform done: sku=%s clean_title=%s",
            result.original_sku, result.clean_title[:80],
        )
        return result
    except Exception:
        logger.exception("Unhandled error in transform endpoint")
        raise


@app.post("/api/marketplace/mock-upload", response_model=UploadResponse)
async def mock_upload(product: CleanProductData):
    """
    Имитирует загрузку карточки товара на Wildberries / Ozon.
    Валидирует данные, ждёт 1 сек (симуляция сети), логирует и возвращает ID.
    """
    logger.info("=== MOCK UPLOAD === sku=%s", product.original_sku)
    logger.info(
        "Payload: title=%s | specs=%s | images=%d",
        product.clean_title[:60],
        list(product.extracted_specs.keys()),
        len(product.media_urls),
    )

    errors = []
    if not product.clean_title or len(product.clean_title) < 5:
        errors.append("clean_title слишком короткий или пустой")
    if not product.clean_description or len(product.clean_description) < 20:
        errors.append("clean_description слишком короткое или пустое")
    if not product.extracted_specs:
        errors.append("extracted_specs пустой")

    if errors:
        logger.error("Validation failed for %s: %s", product.original_sku, errors)
        raise HTTPException(status_code=422, detail=errors)

    await asyncio.sleep(1.0)

    marketplace_id = f"wb_{random.randint(1000000, 9999999)}"

    logger.info(
        "Upload success: sku=%s marketplace_id=%s",
        product.original_sku, marketplace_id,
    )
    return UploadResponse(status="success", marketplace_id=marketplace_id)


@app.get("/api/urls/test-list")
async def get_test_urls():
    """Возвращает список тестовых URL для n8n workflow."""
    return [
        {"url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"},
        {"url": "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"},
        {"url": "https://books.toscrape.com/catalogue/soumission_998/index.html"},
    ]
