import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "gemini_available" in data


@pytest.mark.asyncio
async def test_extract_endpoint_returns_mock_on_invalid_url(client: AsyncClient):
    resp = await client.post(
        "/api/parser/extract",
        json={"url": "https://invalid.example.com/nonexistent"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "original_sku" in data
    assert data["original_sku"].startswith("SKU-")
    assert "raw_title" in data
    assert "raw_description" in data
    assert "media_urls" in data


@pytest.mark.asyncio
async def test_extract_endpoint_validates_url(client: AsyncClient):
    resp = await client.post(
        "/api/parser/extract",
        json={"url": "not-a-url"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transform_endpoint_returns_mock_when_no_gemini(client: AsyncClient):
    raw_data = {
        "original_sku": "SKU-TEST-001",
        "raw_title": "Смартфон Xiaomi Redmi Note 12 Pro",
        "raw_description": "Оригинальный смартфон Xiaomi. 8GB RAM, 256GB ROM.",
        "raw_specs": {"Бренд": "Xiaomi", "Память": "256GB", "Цвет": "Черный"},
        "media_urls": ["https://example.com/photo1.jpg"],
        "source_url": "https://example.com/product/123",
    }
    resp = await client.post("/api/parser/transform", json=raw_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_sku"] == "SKU-TEST-001"
    assert "clean_title" in data
    assert "clean_description" in data
    assert "extracted_specs" in data
    assert "media_urls" in data


@pytest.mark.asyncio
async def test_transform_removes_brand_names(client: AsyncClient):
    raw_data = {
        "original_sku": "SKU-TEST-002",
        "raw_title": "Наушники Sony WH-1000XM5",
        "raw_description": "Беспроводные наушники Sony с шумоподавлением.",
        "raw_specs": {"Бренд": "Sony", "Тип": "Полноразмерные"},
        "media_urls": [],
        "source_url": "https://example.com/product/456",
    }
    resp = await client.post("/api/parser/transform", json=raw_data)
    assert resp.status_code == 200
    data = resp.json()
    assert "Sony" not in data["clean_title"]
    assert "Xiaomi" not in data["clean_title"]
    assert "Samsung" not in data["clean_title"]


@pytest.mark.asyncio
async def test_mock_upload_success(client: AsyncClient):
    product = {
        "original_sku": "SKU-TEST-003",
        "clean_title": "Смартфон Премиум Model 1234",
        "clean_description": "Купить смартфон премиум model 1234 по лучшей цене с доставкой по РФ. Оригинальная гарантия, быстрая доставка.",
        "extracted_specs": {"Память": "256GB", "Цвет": "Черный"},
        "media_urls": ["https://example.com/photo.jpg"],
    }
    resp = await client.post("/api/marketplace/mock-upload", json=product)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["marketplace_id"].startswith("wb_")


@pytest.mark.asyncio
async def test_mock_upload_fails_on_short_title(client: AsyncClient):
    product = {
        "original_sku": "SKU-TEST-004",
        "clean_title": "Abc",
        "clean_description": "Длинное описание товара для проверки валидации.",
        "extracted_specs": {"Цвет": "Красный"},
        "media_urls": [],
    }
    resp = await client.post("/api/marketplace/mock-upload", json=product)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_mock_upload_fails_on_empty_specs(client: AsyncClient):
    product = {
        "original_sku": "SKU-TEST-005",
        "clean_title": "Нормальный заголовок товара",
        "clean_description": "Достаточно длинное описание для прохождения валидации.",
        "extracted_specs": {},
        "media_urls": [],
    }
    resp = await client.post("/api/marketplace/mock-upload", json=product)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_test_urls_endpoint(client: AsyncClient):
    resp = await client.get("/api/urls/test-list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert all("url" in item for item in data)


@pytest.mark.asyncio
async def test_transform_preserves_sku_and_source(client: AsyncClient):
    raw_data = {
        "original_sku": "SKU-TEST-006",
        "raw_title": "Тестовый товар",
        "raw_description": "Описание тестового товара для проверки.",
        "raw_specs": {"Характеристика": "Значение"},
        "media_urls": [],
        "source_url": "https://example.com/test",
    }
    resp = await client.post("/api/parser/transform", json=raw_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_sku"] == "SKU-TEST-006"


@pytest.mark.asyncio
async def test_extract_generates_unique_sku(client: AsyncClient):
    resp1 = await client.post(
        "/api/parser/extract",
        json={"url": "https://invalid.example.com/product/1"},
    )
    resp2 = await client.post(
        "/api/parser/extract",
        json={"url": "https://invalid.example.com/product/2"},
    )
    assert resp1.json()["original_sku"] != resp2.json()["original_sku"]
