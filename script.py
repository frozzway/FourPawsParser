from __future__ import annotations

import time
import asyncio
from typing import TypeAlias, Annotated, get_type_hints, Iterator, Literal
from itertools import chain
from dataclasses import dataclass, field, is_dataclass

import httpx
import requests
from httpx import AsyncClient
from openpyxl import Workbook

from params_resolver import resolve_secure_params


base_url = 'https://4lapy.ru'
products_endpoint = 'api/v2/catalog/product/list/'
price_endpoint = 'api/v2/catalog/product/info-list/'
auth_value = 'Basic NGxhcHltb2JpbGU6eEo5dzFRMyhy'
token_endpoint = 'api/start/'

client = requests.Session()
auth_header = {'Authorization': auth_value}
client.headers.update(auth_header)


@dataclass
class Product:
    id: Annotated[int, "Идентификатор"]
    title: Annotated[str, "Наименование"]
    link: Annotated[str, "Ссылка"]
    brand: Annotated[str, "Бренд"]
    available: bool
    variants: list[Product] = field(default_factory=list)
    price: Price | None = None

    def set_price(self, variant):
        price_info = variant['price']
        self.price = Price(
            regular_price=price_info['actual'],
            promo_price=price_info['singleItemPackDiscountPrice']
        )


@dataclass
class Price:
    regular_price: Annotated[int, "Регулярная цена"]
    promo_price: Annotated[int, "Промо цена"]


ProductDict: TypeAlias = dict[int, Product]


def chunk_array(array, chunk_size=10):
    """Разделить массив на подмассивы заданного размера."""
    return [array[i:i + chunk_size] for i in range(0, len(array), chunk_size)]


class Category:
    def __init__(self, category_id: int, token: str) -> None:
        self.category_id = category_id
        self.token = token
        self.products: ProductDict = {}
        self.products_ids: list[int] = []
        self.total_items: int = 0
        self.base_params = {
            'token': self.token,
            'category_id': self.category_id,
            'page': '1',
            'sort': 'popular'
        }

    async def parse(self):
        """Спарсить категорию"""
        self._get_items_amount()
        self._get_products_list()
        await self._get_products_prices()

    def export_to_excel(self):
        """Экспортировать данные в excel"""
        wb = Workbook()
        ws = wb.active

        products = list(self.products.values())
        headers = self._get_product_exported_headers(products[0])
        ws.append(headers)
        for prod in products:
            ws.append(self._get_product_row(prod))
            for variant_prod in prod.variants:
                ws.append(self._get_product_row(variant_prod))

        wb.save('output.xlsx')

    @staticmethod
    def _get_exported_attrs_names(obj) -> Iterator:
        """Извлечь наименования атрибутов, которые предназначены для выгрузки в excel"""
        hints = get_type_hints(obj.__class__, include_extras=True)
        return (attr_name for attr_name, type_annotation in hints.items() if hasattr(type_annotation, "__metadata__"))

    def _get_exported_attrs_values(self, obj) -> Iterator:
        """Извлечь значения атрибутов, которые предназначены для выгрузки в excel"""
        return (getattr(obj, attr_name) for attr_name in self._get_exported_attrs_names(obj))

    def _get_product_exported_headers(self, prod: Product) -> list[str]:
        """Извлечь заголовки таблицы excel объекта Product"""
        headers = []
        product_headers = self._get_exported_headers(prod)
        dataclasses_objects = [v for v in prod.__dict__.values() if is_dataclass(v)]
        extra = [self._get_exported_headers(o) for o in dataclasses_objects]
        headers.extend(chain(product_headers, *extra))
        return headers

    @staticmethod
    def _get_exported_headers(obj) -> list:
        """Извлечь заголовки таблицы excel объекта по атрибутам с аннотацией типа"""
        hints = get_type_hints(obj.__class__, include_extras=True)
        types = (type_annotation for type_annotation in hints.values() if hasattr(type_annotation, "__metadata__"))
        return [type_annotation.__metadata__[0] for type_annotation in types]

    def _get_product_row(self, prod: Product) -> list:
        """Извлечь строку значений таблицы excel из объекта Product"""
        row = []
        product_info = self._get_exported_attrs_values(prod)
        dataclasses_objects = [v for v in prod.__dict__.values() if is_dataclass(v)]
        extras = [self._get_exported_attrs_values(o) for o in dataclasses_objects]
        row.extend(chain(product_info, *extras))
        return row

    def _get_items_amount(self):
        """Получить и сохранить количество продуктов категории"""
        params = resolve_secure_params({
            'count': '1',
            **self.base_params
        })
        response = self.retry_request(f'{base_url}/{products_endpoint}', params=params, method='GET')
        self.total_items = response['data']['total_items']

    def _get_products_list(self):
        """Получить и сохранить информацию о продуктах категории, за исключением цены"""
        params = resolve_secure_params({
            'count': self.total_items,
            **self.base_params
        })
        response = self.retry_request(f'{base_url}/{products_endpoint}', params=params, method='GET')
        goods = response['data']['goods']
        self.products_ids = response['data']['goods_ids']
        for good in goods:
            if packing_variants := good.get('packingVariants'):
                for packing_variant in packing_variants:
                    product = self._construct_product(packing_variant)
                    self.products[product.id] = product
            else:
                product = self._construct_product(good)
                self.products[product.id] = product

    @staticmethod
    def retry_request(url: str, method: Literal['GET', 'POST'], params: dict = None, data: dict = None) -> dict:
        while True:
            response = client.request(method=method, url=url, params=params, data=data, timeout=60).json()
            if not response.get('error'):
                return response
            time.sleep(2)

    @staticmethod
    async def async_retry_request(async_client: AsyncClient, url: str, method: Literal['GET', 'POST'],
                                  params: dict = None, data: dict = None, attempts: int = 3) -> dict | None:
        for _ in range(attempts):
            response = await async_client.request(method=method, url=url, params=params, data=data, timeout=60)
            response = response.json()
            if not response.get('error'):
                print('Success async request')
                return response
            await asyncio.sleep(2)
            print(f'Failed {attempts} attempts to make request')

    async def _get_chunked_products_prices(self, async_client: AsyncClient, chunked_products_ids: list[int]):
        params = {}
        for i, product_id in enumerate(chunked_products_ids):
            params[f'offers[{i}]'] = product_id
        params['token'] = self.token
        params = resolve_secure_params(params)
        return await self.async_retry_request(async_client=async_client,
                                              url=f'{base_url}/{price_endpoint}', data=params, method='POST')

    async def _get_products_prices(self):
        """Получить информацию о ценах продуктов категории"""
        chunked_products_ids = chunk_array(self.products_ids)

        async with AsyncClient(limits=httpx.Limits(max_connections=10)) as async_client:
            async_client.headers.update(auth_header)
            tasks = [self._get_chunked_products_prices(async_client, chunk) for chunk in chunked_products_ids]
            responses = await asyncio.gather(*tasks)

        hierarchical_products: ProductDict = {}

        for response in responses:
            if not response:
                continue
            products = response['data']['products']
            for product_price_info in products:
                if product := self.products.get(product_price_info['active_offer_id']):
                    for variant in product_price_info['variants']:
                        product_id = variant['id']
                        if child_product := self.products.get(product_id):
                            child_product.set_price(variant)
                            if child_product != product:
                                product.variants.append(child_product)
                            else:
                                hierarchical_products[product_id] = child_product

        self.products = hierarchical_products

    @staticmethod
    def _construct_product(obj) -> Product:
        product = Product(
            id=obj['id'],
            title=obj['title'],
            link=obj['webpage'],
            brand=obj['brand_name'],
            available=obj['isAvailable']
        )
        return product


async def supervisor():
    token = client.get(f'{base_url}/{token_endpoint}').json()['data']['token']
    category = Category(2, token)
    await category.parse()
    category.export_to_excel()
    pass


if __name__ == '__main__':
    asyncio.run(supervisor())
    pass

