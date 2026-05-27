import json
from typing import Dict, List, Union
from pydantic import BaseModel, Field, HttpUrl, field_validator


class ExtractRequest(BaseModel):
    url: HttpUrl


class RawProductData(BaseModel):
    original_sku: str = Field(description="Исходный артикул конкурента")
    raw_title: str = Field(description="Сырой заголовок товара")
    raw_description: str = Field(description="Сырое описание товара")
    raw_specs: Union[Dict[str, str], str] = Field(description="Характеристики товара")
    media_urls: Union[List[str], str] = Field(description="Ссылки на изображения")
    source_url: str = Field(description="URL исходной страницы")

    @field_validator("raw_specs")
    @classmethod
    def coerce_raw_specs(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return {}
        return v

    @field_validator("media_urls")
    @classmethod
    def coerce_media_urls(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v


class CleanProductData(BaseModel):
    original_sku: str = Field(description="Исходный артикул конкурента")
    clean_title: str = Field(description="Уникальный SEO-заголовок без чужих брендов")
    clean_description: str = Field(description="Переписанный B2C/B2B-текст")
    extracted_specs: Dict[str, str] = Field(description="Очищенные характеристики товара")
    media_urls: List[str] = Field(description="Ссылки на изображения")


class UploadResponse(BaseModel):
    status: str = Field(description="Статус загрузки")
    marketplace_id: str = Field(description="ID карточки на маркетплейсе")
