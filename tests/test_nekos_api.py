import asyncio

import pytest

import shared
from workers.nekosapi import NekosApiWorker


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "MASTER_FOLDER", str(tmp_path))
    return NekosApiWorker("Girl, blue_hair", "artist one", 2, "safe", {"anti_ban_pause": 0})


def test_filters_are_unique_and_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "MASTER_FOLDER", str(tmp_path))
    item = NekosApiWorker("Girl, girl, Catgirl", "", 1, "safe", {})
    assert item.tags == ["Girl", "Catgirl"]
    with pytest.raises(ValueError, match="at most 5 tags"):
        NekosApiWorker("a,b,c,d,e,f", "", 1, "safe", {})
    with pytest.raises(ValueError, match="Unsupported"):
        NekosApiWorker("Girl", "", 1, "invalid", {})


def test_scraper_uses_repeated_v5_filters(worker, monkeypatch):
    captured = {}

    async def request_page(params):
        captured["params"] = params
        return {
            "items": [
                {
                    "id": 42,
                    "url": "https://cdn.example/42.webp",
                    "rating": "safe",
                    "artist_name": "artist one",
                    "tags": [{"name": "Girl"}],
                }
            ],
            "total": 1,
        }

    queued = []

    async def enqueue(*args):
        queued.append(args)
        return True

    monkeypatch.setattr(worker, "_request_page", request_page)
    monkeypatch.setattr(worker, "enqueue_download", enqueue)
    asyncio.run(worker.scraper())

    assert captured["params"].count(("tag", "Girl")) == 1
    assert ("tag", "blue_hair") in captured["params"]
    assert ("artist", "artist one") in captured["params"]
    assert ("rating", "safe") in captured["params"]
    assert queued[0][2] == "nekosapi_42.webp"
    assert queued[0][3] == ["Girl", "rating:safe"]
    assert queued[0][4] == ["artist one"]


def test_non_json_api_response_is_retried_and_bounded(worker, monkeypatch):
    class Response:
        status_code = 200
        headers = {"Content-Type": "text/html"}

        def raise_for_status(self):
            return None

    calls = 0

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr(worker.session, "get", get)
    worker.net_config.update({"api_retries": 2, "retry_wait": 0})
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        asyncio.run(worker._request_page([]))
    assert calls == 2
