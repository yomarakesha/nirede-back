"""Generate the Postman collection and environment from the app's OpenAPI schema.

Usage: uv run python scripts/gen_postman.py
Writes postman/collections/nirede.postman_collection.json and
postman/environments/local.postman_environment.json.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = ROOT / "postman/collections/nirede.postman_collection.json"
ENVIRONMENT = ROOT / "postman/environments/local.postman_environment.json"
# Fixed ids: Postman matches re-imports by id, and regenerating must not churn the diff.
COLLECTION_ID = "f11343dc-cd26-4ea5-8a08-1719ae86e749"
ENVIRONMENT_ID = "48461070-3a11-4519-8ed2-0242522d74fd"

# Folder order and the bearer token each folder uses.
FOLDERS = [
    ("auth", "1. Auth (вход по SMS-коду)", "noauth"),
    ("me", "2. Me (профиль, избранное, уведомления)", "user"),
    ("cities", "3. Public: города", "user"),
    ("malls", "3. Public: торговые центры", "user"),
    ("categories", "3. Public: категории", "user"),
    ("shops", "3. Public: магазины", "user"),
    ("search", "3. Public: поиск", "user"),
    ("promotions", "3. Public: акции", "user"),
    ("seller", "4. Seller (кабинет продавца)", "user"),
    ("admin", "5. Admin", "admin"),
]

PATH_VARS = {
    "city_id": "city_id",
    "mall_id": "mall_id",
    "category_id": "category_id",
    "shop_id": "shop_id",
    "promo_id": "promotion_id",
    "app_id": "application_id",
    "cr_id": "change_request_id",
    "user_id": "user_id",
    "notification_id": "notification_id",
    "token": "device_token",
}

# Hand-written bodies where a generated example would be unhelpful.
EXAMPLES: dict[tuple[str, str], Any] = {
    ("POST", "/api/v1/auth/otp/request"): {"phone": "{{phone}}"},
    ("POST", "/api/v1/auth/otp/verify"): {"phone": "{{phone}}", "code": "{{otp_code}}"},
    ("POST", "/api/v1/auth/refresh"): {"refresh_token": "{{refresh_token}}"},
    ("POST", "/api/v1/auth/logout"): {"refresh_token": "{{refresh_token}}"},
    ("PATCH", "/api/v1/me"): {
        "name": "Аман",
        "language": "ru",
        "notify_favorite_shops": True,
        "notify_my_malls": True,
    },
    ("POST", "/api/v1/me/devices"): {"token": "{{device_token}}", "platform": "android"},
    ("POST", "/api/v1/me/seller-applications"): {
        "shop_id": None,
        "shop_name": "Moda Line",
        "mall_id": "{{mall_id}}",
        "floor": 2,
        "number": "214",
        "contact_phone": "{{phone}}",
    },
    ("POST", "/api/v1/admin/cities"): {"name_ru": "Ашхабад", "name_tk": "Aşgabat"},
    ("PATCH", "/api/v1/admin/cities/{city_id}"): {"is_active": True},
    ("POST", "/api/v1/admin/malls"): {
        "city_id": "{{city_id}}",
        "name_ru": "Беркарар",
        "name_tk": "Berkarar",
        "address_ru": "ул. Ататюрка, 80",
        "address_tk": "Atatürk köçesi, 80",
        "phone": "+99312000000",
        "opens_at": "09:00",
        "closes_at": "23:00",
        "layout": "floors",
        "floors_count": 4,
    },
    ("PATCH", "/api/v1/admin/malls/{mall_id}"): {"closes_at": "22:00"},
    ("PUT", "/api/v1/admin/malls/{mall_id}/photos"): {"paths": ["2026/11/example.webp"]},
    ("PUT", "/api/v1/admin/malls/{mall_id}/floors"): [
        {
            "number": 1,
            "summary_ru": "Супермаркет, обувь, телефоны",
            "summary_tk": "Supermarket, aýakgap, telefonlar",
        },
        {"number": 2, "summary_ru": "Одежда, сумки, аксессуары", "summary_tk": "Eşikler, sumkalar"},
    ],
    ("POST", "/api/v1/admin/categories"): {
        "parent_id": None,
        "name_ru": "Женщинам",
        "name_tk": "Aýallara",
        "slug": "women",
        "search_aliases_ru": None,
        "search_aliases_tk": None,
    },
    ("PATCH", "/api/v1/admin/categories/{category_id}"): {
        "search_aliases_ru": "женское пальто женские пальто"
    },
    ("POST", "/api/v1/admin/shops"): {
        "name": "Moda Line",
        "locations": [
            {"mall_id": "{{mall_id}}", "floor": 2, "number": "214"},
            {
                "city_id": "{{city_id}}",
                "address_ru": "ул. Гёроглы, 1",
                "address_tk": "Görogly köçesi, 1",
            },
        ],
        "phone": "+99365123456",
        "opens_at": "10:00",
        "closes_at": "22:00",
        "how_to_find_ru": "От главного входа на эскалаторе на 2 этаж, налево до № 214.",
        "how_to_find_tk": "Esasy girelgeden eskalator bilen 2-nji gata, çepe № 214.",
        "category_ids": ["{{category_id}}"],
        "photos": [],
    },
    ("PATCH", "/api/v1/admin/shops/{shop_id}"): {"phone": "+99365000000"},
    ("POST", "/api/v1/admin/shops/{shop_id}/subscriptions"): {
        "amount": "30",
        "days": 30,
        "note": "оплата наличными",
    },
    ("POST", "/api/v1/admin/promotions"): {
        "shop_id": "{{shop_id}}",
        "title_ru": "−30% на пальто и пуховики",
        "title_tk": "Paltolara we puhowiklere −30%",
        "badge": "−30%",
        "starts_at": "2026-11-23T00:00:00+05:00",
        "ends_at": "2026-12-03T23:59:00+05:00",
    },
    ("PATCH", "/api/v1/admin/promotions/{promo_id}"): {"badge": "2+1"},
    ("POST", "/api/v1/admin/promotions/{promo_id}/reject"): {"comment": "Добавьте фото"},
    ("POST", "/api/v1/admin/seller-applications/{app_id}/approve"): {
        "shop": None,
        "subscription": {"amount": "30", "days": 30},
    },
    ("POST", "/api/v1/admin/seller-applications/{app_id}/reject"): {"comment": "Не дозвонились"},
    ("POST", "/api/v1/admin/change-requests/{cr_id}/reject"): {"comment": "Опечатка в адресе"},
    ("PATCH", "/api/v1/admin/users/{user_id}"): {"role": "seller"},
    ("POST", "/api/v1/seller/shops/{shop_id}/change-requests"): {
        "how_to_find_ru": "Новый текст «как найти»",
        "category_ids": ["{{category_id}}"],
    },
    ("POST", "/api/v1/seller/shops/{shop_id}/promotions"): {
        "title_ru": "2+1 на платья",
        "title_tk": "Köýneklere 2+1",
        "badge": "2+1",
        "starts_at": "2026-11-23T00:00:00+05:00",
        "ends_at": "2026-12-05T23:59:00+05:00",
    },
    ("POST", "/api/v1/seller/promotions/{promo_id}/change-requests"): {
        "title_ru": "2+1 на все платья"
    },
}

# Saves tokens returned by verify/refresh into collection variables.
SAVE_TOKENS = """const body = pm.response.json();
pm.test("tokens issued", () => pm.expect(body.access_token).to.be.a("string"));
const prefix = pm.variables.get("login_as") === "admin" ? "admin_" : "";
pm.collectionVariables.set(prefix + "access_token", body.access_token);
pm.collectionVariables.set("refresh_token", body.refresh_token);
if (body.user) { pm.collectionVariables.set("user_id", body.user.id); }"""

# Remembers ids of created objects so follow-up requests work without copy-paste.
SAVE_ID = """if (pm.response.code === 201) {{
  pm.collectionVariables.set("{var}", pm.response.json().id);
}}"""

STATUS_OK = 'pm.test("status 2xx", () => pm.expect(pm.response.code).to.be.within(200, 299));'


def _resolve(schema: dict, components: dict) -> dict:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _example(schema: dict, components: dict, depth: int = 0) -> Any:
    schema = _resolve(schema, components)
    if depth > 4:
        return None
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return _example(options[0], components, depth) if options else None
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {
            name: _example(prop, components, depth + 1)
            for name, prop in schema.get("properties", {}).items()
        }
    if kind == "array":
        return [_example(schema.get("items", {}), components, depth + 1)]
    fmt = schema.get("format")
    return {
        "integer": 1,
        "number": 1,
        "boolean": True,
        "string": {"date-time": "2026-11-23T10:00:00+05:00", "time": "10:00"}.get(fmt, "string"),
    }.get(kind)


def _folder_key(path: str, tags: list[str]) -> str:
    if path.startswith("/api/v1/admin"):
        return "admin"
    if path.startswith("/api/v1/seller"):
        return "seller"
    if path.startswith("/api/v1/me"):
        return "me"
    if path.startswith("/api/v1/auth"):
        return "auth"
    if "/shops" in path and path.startswith("/api/v1/malls"):
        return "shops"
    return path.split("/")[3]


def _url(path: str, params: list[dict]) -> dict:
    pm_path = re.sub(r"\{(\w+)\}", r":\1", path.removeprefix("/"))
    query = [
        {
            "key": p["name"],
            "value": "{{" + PATH_VARS[p["name"]] + "}}" if p["name"] in PATH_VARS else "",
            "disabled": not p.get("required", False),
            "description": p.get("description", ""),
        }
        for p in params
        if p["in"] == "query"
    ]
    variables = [
        {"key": p["name"], "value": "{{" + PATH_VARS.get(p["name"], p["name"]) + "}}"}
        for p in params
        if p["in"] == "path"
    ]
    raw = "{{baseUrl}}/" + pm_path
    url: dict[str, Any] = {"raw": raw, "host": ["{{baseUrl}}"], "path": pm_path.split("/")}
    if query:
        url["query"] = query
    if variables:
        url["variable"] = variables
    return url


def _body(method: str, path: str, op: dict, components: dict) -> dict | None:
    content = op.get("requestBody", {}).get("content", {})
    if "multipart/form-data" in content:
        return {"mode": "formdata", "formdata": [{"key": "file", "type": "file", "src": []}]}
    if "application/json" not in content:
        return None
    example = EXAMPLES.get((method, path))
    if example is None:
        example = _example(content["application/json"]["schema"], components)
    raw = json.dumps(example, ensure_ascii=False, indent=2)
    raw = re.sub(
        r'"(\{\{\w+\}\})"', lambda m: m.group(1) if "_id" in m.group(1) else m.group(0), raw
    )
    return {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}


def _events(method: str, path: str) -> list[dict]:
    lines = [STATUS_OK]
    if path in ("/api/v1/auth/otp/verify", "/api/v1/auth/refresh"):
        lines = [SAVE_TOKENS]
    elif method == "POST" and re.fullmatch(
        r"/api/v1/(admin|seller)/[\w-]+(/\{\w+\}/promotions)?", path
    ):
        resource = path.rstrip("/").split("/")[-1]
        var = {
            "cities": "city_id",
            "malls": "mall_id",
            "categories": "category_id",
            "shops": "shop_id",
            "promotions": "promotion_id",
        }.get(resource)
        if var:
            lines.append(SAVE_ID.format(var=var))
    elif path == "/api/v1/me/seller-applications" and method == "POST":
        lines.append(SAVE_ID.format(var="application_id"))
    elif path.endswith("/change-requests") and method == "POST":
        lines.append(SAVE_ID.format(var="change_request_id"))
    return [
        {
            "listen": "test",
            "script": {"type": "text/javascript", "exec": "\n".join(lines).split("\n")},
        }
    ]


def _auth(kind: str) -> dict:
    if kind == "noauth":
        return {"type": "noauth"}
    token = "{{admin_access_token}}" if kind == "admin" else "{{access_token}}"
    return {"type": "bearer", "bearer": [{"key": "token", "value": token, "type": "string"}]}


def build() -> tuple[dict, dict]:
    spec = create_app().openapi()
    components = spec.get("components", {}).get("schemas", {})
    folders = {key: {"name": name, "item": [], "auth": _auth(auth)} for key, name, auth in FOLDERS}
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, op in methods.items():
            method = method.upper()
            item: dict[str, Any] = {
                "name": f"{method} {path.removeprefix('/api/v1')}",
                "event": _events(method, path),
                "request": {
                    "method": method,
                    "header": [{"key": "Accept", "value": "application/json"}],
                    "url": _url(path, op.get("parameters", [])),
                    "description": op.get("summary", ""),
                },
            }
            body = _body(method, path, op, components)
            if body:
                item["request"]["body"] = body
                if body["mode"] == "raw":
                    item["request"]["header"].append(
                        {"key": "Content-Type", "value": "application/json"}
                    )
            folders[_folder_key(path, op.get("tags", []))]["item"].append(item)

    variables = {
        "baseUrl": "http://localhost:8000",
        "phone": "+99365123456",
        "otp_code": "",
        "login_as": "user",
        "access_token": "",
        "admin_access_token": "",
        "refresh_token": "",
        **{v: "" for v in PATH_VARS.values()},
    }
    collection = {
        "info": {
            "_postman_id": COLLECTION_ID,
            "name": "Nirede API",
            "description": DESCRIPTION,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": _auth("user"),
        "variable": [{"key": k, "value": v} for k, v in variables.items()],
        "item": [
            {
                "name": "Health",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/health",
                        "host": ["{{baseUrl}}"],
                        "path": ["health"],
                    },
                },
                "event": _events("GET", "/health"),
            },
            *[f for f in folders.values() if f["item"]],
        ],
    }
    environment = {
        "id": ENVIRONMENT_ID,
        "name": "Nirede local",
        "values": [
            {"key": "baseUrl", "value": "http://localhost:8000", "enabled": True},
            {"key": "phone", "value": "+99365123456", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
    }
    return collection, environment


DESCRIPTION = """REST API Nirede: где в Ашхабаде продаётся нужная категория товаров.

**Как начать**
1. Запустите backend (`docker compose up --build`), Swagger: {{baseUrl}}/docs.
2. `1. Auth → POST /auth/otp/request` с `{{phone}}`. Код SMS пока пишется в лог сервера
   (`docker compose logs api | grep Nirede:`). Впишите его в переменную `otp_code`.
3. `POST /auth/otp/verify` — токены сохранятся в переменные коллекции автоматически.
4. Для админских запросов: создайте админа `uv run python -m app.cli create-admin +993...`,
   поставьте `login_as = admin` и войдите этим телефоном — токен ляжет в `admin_access_token`.
   Верните `login_as = user` для обычного пользователя.

**Соглашения**
- Все тексты парой полей `*_ru` / `*_tk`; клиент выбирает язык сам.
- Списки: `?limit=&offset=` → `{"items": [...], "total": N}`.
- Ошибки: `{"detail": "код_ошибки"}`, например `otp_invalid`, `subscription_required`,
  `already_reviewed`.
- Картинки: сначала `POST /admin/uploads` или `/seller/uploads` (multipart `file`),
  затем путь `path` передаётся в поля `photos`, `logo`, `image`, `icon`.
  Полный адрес — поле `*_url` в ответах.
- Время работы в часовом поясе Asia/Ashgabat; даты акций — ISO 8601 с часовым поясом.
- Созданные объекты (POST в Admin/Seller) сохраняют id в переменные (`mall_id`, `shop_id`, ...).
"""


def main() -> None:
    collection, environment = build()
    COLLECTION.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n")
    ENVIRONMENT.write_text(json.dumps(environment, ensure_ascii=False, indent=2) + "\n")
    count = sum(len(f.get("item", [])) for f in collection["item"] if "item" in f) + 1
    print(f"{COLLECTION.relative_to(ROOT)}: {count} requests")


if __name__ == "__main__":
    main()
