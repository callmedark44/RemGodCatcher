import asyncio
import json
import os

import pytest
from PIL import Image

import shared
from shared import BaseDownloader


@pytest.fixture
def downloader(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "MASTER_FOLDER", str(tmp_path))
    monkeypatch.setattr(shared, "GALLERY_FILE", str(tmp_path / "database" / "gallery.json"))
    return BaseDownloader("test", "site", 1, {"download_retries": 1})


def test_enqueue_deduplicates_pending_filename(downloader, tmp_path):
    downloader.download_queue = asyncio.Queue()
    target = tmp_path / "image.png"

    async def run():
        first = await downloader.enqueue_download("https://example/a.png", str(target), "same.png", [], [])
        second = await downloader.enqueue_download("https://example/a.png", str(target), "same.png", [], [])
        return first, second

    assert asyncio.run(run()) == (True, False)
    assert downloader.download_queue.qsize() == 1


def test_download_validation_rejects_html_and_corrupt_images(downloader, tmp_path):
    html = tmp_path / "error.jpg"
    html.write_bytes(b"<html>upstream error</html>")
    with pytest.raises(Exception):
        downloader._validate_download(str(html), "text/html")

    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not an image")
    with pytest.raises(Exception):
        downloader._validate_download(str(corrupt), "image/png")


def test_download_validation_accepts_real_image(downloader, tmp_path):
    path = tmp_path / "valid.png"
    Image.new("RGB", (2, 2), "red").save(path)
    downloader._validate_download(str(path), "image/png")


def test_gallery_creates_database_directory_and_separates_sites(tmp_path, monkeypatch):
    gallery_file = tmp_path / "database" / "gallery.json"
    monkeypatch.setattr(shared, "GALLERY_FILE", str(gallery_file))
    shared.add_to_gallery("one", "same.jpg", "one/same.jpg", ["a"], [])
    shared.add_to_gallery("two", "same.jpg", "two/same.jpg", ["b"], [])
    data = json.loads(gallery_file.read_text())
    assert {(item["site"], item["filename"]) for item in data["images"]} == {
        ("one", "same.jpg"),
        ("two", "same.jpg"),
    }
