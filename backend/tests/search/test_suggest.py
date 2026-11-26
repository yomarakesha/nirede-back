async def _suggest(client, q, **params):
    r = await client.get("/api/v1/search/suggest", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


async def test_suggest_palto_lists_categories(client, world):
    body = await _suggest(client, "пальто")
    cats = {c["id"]: c for c in body["categories"]}
    assert set(cats) >= {world.w_coat.id, world.m_coat.id}
    women = cats[world.w_coat.id]
    assert women["path_ru"] == ["Женщинам", "Верхняя одежда", "Пальто"]
    assert women["path_tk"] == ["Aýallara", "Daşky eşik", "Palto"]
    assert women["shop_count"] == 7
    assert cats[world.m_coat.id]["shop_count"] == 1


async def test_suggest_malls_for_top_category(client, world):
    body = await _suggest(client, "женское пальто")
    assert body["categories"][0]["id"] == world.w_coat.id
    counts = {m["name_ru"]: m["shop_count"] for m in body["malls_for_top_category"]}
    assert counts == {"Беркарар": 4, "Аркач": 1, "Толкучка": 1}


async def test_suggest_phrase_women(client, world):
    body = await _suggest(client, "женское пальто")
    assert [c["id"] for c in body["categories"]] == [world.w_coat.id]


async def test_suggest_by_path_words(client, world):
    body = await _suggest(client, "детям шубы")
    assert [c["id"] for c in body["categories"]] == [world.k_fur.id]


async def test_suggest_case_and_turkmen_letters(client, world):
    for q in ("ýüpek", "ÝÜPEK", "Ýüp"):
        body = await _suggest(client, q)
        assert [s["name"] for s in body["shops"]] == ["Ýüpek"], q
    upper = await _suggest(client, "ПАЛЬТО")
    lower = await _suggest(client, "пальто")
    assert [c["id"] for c in upper["categories"]] == [c["id"] for c in lower["categories"]]


async def test_suggest_turkmen_query(client, world):
    body = await _suggest(client, "palto")
    assert world.w_coat.id in [c["id"] for c in body["categories"]]


async def test_q_too_short_422(client, world):
    r = await client.get("/api/v1/search/suggest", params={"q": " a "})
    assert r.status_code == 422


async def test_suggest_shop_name_partial(client, world):
    body = await _suggest(client, "style")
    assert [s["name"] for s in body["shops"]] == ["Lady Style"]
    assert body["shops"][0]["is_premium"] is True


async def test_suggest_hides_inactive_shop(client, world):
    body = await _suggest(client, "hidden")
    assert body["shops"] == []
