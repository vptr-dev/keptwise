"""Tests for reading TikTok, Instagram, Facebook and YouTube exports.

The fake exports in tests/samples/ copy the layout of the real ones.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.importers import parse_export
from app.importers.common import ParseResult, fix_meta_text, iso_from_text, iso_from_timestamp, plural
from app.importers.source import ExportSource
from app.importers.urls import (
    canonical_facebook,
    canonical_instagram,
    canonical_tiktok,
    canonical_youtube,
)

SAMPLES = Path(__file__).parent / "samples"


def zip_folder(folder: Path, zip_path: Path) -> Path:
    """Pack a sample folder into a zip, like the platforms deliver it."""
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(folder).as_posix())
    return zip_path


def parse_one(path: Path) -> ParseResult:
    with ExportSource.open(path) as source:
        results = parse_export(source)
    assert len(results) == 1, [result.platform for result in results]
    return results[0]


def by_id(result: ParseResult) -> dict[str | None, object]:
    return {item.external_id: item for item in result.items}


# ---------- links ----------


@pytest.mark.parametrize(
    "link",
    [
        "https://www.tiktokv.com/share/video/7300000000000000001/",
        "https://www.tiktok.com/@chef/video/7300000000000000001?is_from_webapp=1&sender_device=pc",
        "https://m.tiktok.com/v/7300000000000000001.html",
    ],
)
def test_tiktok_links_become_one_standard_link(link: str) -> None:
    assert canonical_tiktok(link) == (
        "https://www.tiktokv.com/share/video/7300000000000000001/",
        "7300000000000000001",
    )


def test_non_video_links_are_refused() -> None:
    assert canonical_tiktok("https://www.tiktok.com/music/sound-7000000000000000001") is None
    assert canonical_tiktok("https://example.com/video/7300000000000000001") is None
    assert canonical_instagram("https://www.instagram.com/chef_marco/") is None
    assert canonical_youtube("not a video") is None


@pytest.mark.parametrize(
    "link",
    [
        "https://www.instagram.com/p/CfakePost01/",
        "https://instagram.com/reel/CfakePost01/?igsh=abc",
        "https://www.instagram.com/chef_marco/p/CfakePost01/",
    ],
)
def test_instagram_links(link: str) -> None:
    assert canonical_instagram(link) == ("https://www.instagram.com/p/CfakePost01/", "CfakePost01")


@pytest.mark.parametrize(
    "link",
    [
        "AbCdEfGhI01",
        "https://www.youtube.com/watch?v=AbCdEfGhI01&t=30s",
        "https://youtu.be/AbCdEfGhI01?si=xyz",
        "https://www.youtube.com/shorts/AbCdEfGhI01",
    ],
)
def test_youtube_links(link: str) -> None:
    assert canonical_youtube(link) == ("https://www.youtube.com/watch?v=AbCdEfGhI01", "AbCdEfGhI01")


def test_facebook_links() -> None:
    watch = ("https://www.facebook.com/watch/?v=123456", "123456")
    assert canonical_facebook("https://www.facebook.com/watch/?v=123456&ref=sharing") == watch
    assert canonical_facebook("https://m.facebook.com/Tasty/videos/123456/") == watch
    assert canonical_facebook("https://www.facebook.com/reel/987/?mibextid=x") == (
        "https://www.facebook.com/reel/987",
        "987",
    )
    # Outside links are unwrapped from Facebook's redirect and lose tracking bits.
    assert canonical_facebook(
        "https://l.facebook.com/l.php?u=https%3A%2F%2Fshop.example%2Fpan%3Fid%3D7%26utm_source%3Dfb&h=x"
    ) == ("https://shop.example/pan?id=7", None)


# ---------- small helpers ----------


def test_meta_garbled_letters_are_repaired() -> None:
    assert fix_meta_text("cafÃ©") == "café"
    assert fix_meta_text("Recipes ð\u009f\u008d\u009d") == "Recipes 🍝"
    assert fix_meta_text("already fine 🍝") == "already fine 🍝"
    assert fix_meta_text("plain") == "plain"
    assert fix_meta_text(None) is None


def test_plural_counts_read_well() -> None:
    assert plural(1, "liked video") == "1 liked video"
    assert plural(2267, "liked video") == "2,267 liked videos"
    assert plural(3, "entry", "entries") == "3 entries"


def test_dates() -> None:
    assert iso_from_timestamp(1709300000) == "2024-03-01T13:33:20Z"
    assert iso_from_timestamp("bad") is None
    assert iso_from_text("2024-03-01 18:20:05") == "2024-03-01T18:20:05Z"
    assert iso_from_text("2024-01-15T08:30:00+02:00") == "2024-01-15T06:30:00Z"
    assert iso_from_text("2019-05-02 10:00:00 UTC") == "2019-05-02T10:00:00Z"
    assert iso_from_text("someday") is None


# ---------- each platform ----------


def test_tiktok_json() -> None:
    result = parse_one(SAMPLES / "tiktok_json")
    assert result.platform == "tiktok"
    items = by_id(result)
    # 4 favourites, one listed twice; likes and sounds are not imported.
    assert sorted(items) == ["7300000000000000001", "7300000000000000002", "7300000000000000003"]
    second = items["7300000000000000002"]
    assert second.url == "https://www.tiktokv.com/share/video/7300000000000000002/"
    assert second.author == "pasta.chef"
    assert second.saved_at == "2024-02-11T09:00:00Z"
    assert "Skipped 2 liked videos: likes aren't saves." in result.notes
    # TikTok lists collection names, but not which videos are in them.
    assert result.collections == ["Cooking", "Gym"]
    assert all(item.platform_collection is None for item in result.items)
    assert any("TikTok lists your 2 collections" in note for note in result.notes)


def test_tiktok_json_older_layout(tmp_path: Path) -> None:
    # Older exports put the favourites under "Activity".
    (tmp_path / "user_data.json").write_text(
        '{"Activity": {"Favorite Videos": {"FavoriteVideoList": ['
        '{"Date": "2023-05-01 12:00:00", "Link": "https://www.tiktokv.com/share/video/7200000000000000001/"}'
        "]}}}",
        encoding="utf-8",
    )
    result = parse_one(tmp_path)
    assert [item.external_id for item in result.items] == ["7200000000000000001"]
    assert result.collections == []


def test_tiktok_txt() -> None:
    result = parse_one(SAMPLES / "tiktok_txt")
    items = by_id(result)
    assert sorted(items) == ["7300000000000000001", "7300000000000000002", "7300000000000000004"]
    assert items["7300000000000000004"].saved_at == "2023-12-24T12:00:00Z"
    assert "Skipped 1 liked video: likes aren't saves." in result.notes


def test_instagram_posts_and_collections() -> None:
    result = parse_one(SAMPLES / "instagram")
    items = by_id(result)
    assert sorted(items) == ["CfakePost01", "CfakePost03", "CfakePost04", "CfakeReel02"]
    reel = items["CfakeReel02"]
    assert reel.url == "https://www.instagram.com/p/CfakeReel02/"
    assert reel.author == "café_lisboa"  # garbled letters repaired
    assert reel.platform_collection == "Recipes 🍝"
    assert items["CfakePost03"].platform_collection is None
    # Only in a collection, not in saved_posts.json: still imported.
    assert items["CfakePost04"].platform_collection == "Japan trip"
    assert items["CfakePost04"].author == "tokyo.eats"
    assert result.collections == ["Recipes 🍝", "Japan trip"]


def test_instagram_html_export_gives_links_only(tmp_path: Path) -> None:
    folder = tmp_path / "ig_html" / "your_instagram_activity" / "saved"
    folder.mkdir(parents=True)
    (folder / "saved_posts.html").write_text(
        '<a href="https://www.instagram.com/p/HtmlPost1/">x</a>'
        '<a href="https://www.instagram.com/chef/">profile</a>',
        encoding="utf-8",
    )
    result = parse_one(tmp_path / "ig_html")
    assert [item.external_id for item in result.items] == ["HtmlPost1"]
    assert "HTML format" in result.notes[0]


def test_facebook() -> None:
    result = parse_one(SAMPLES / "facebook")
    items = {item.url: item for item in result.items}
    assert sorted(items) == [
        "https://travelblog.example/japan",
        "https://www.facebook.com/reel/1000000000000002",
        "https://www.facebook.com/watch/?v=1000000000000001",
    ]
    pasta = items["https://www.facebook.com/watch/?v=1000000000000001"]
    assert pasta.caption == "One-pot pasta — 15 minutes"
    assert pasta.author == "Tasty"
    assert pasta.platform_collection == "Recipes"  # from "... added ... to Recipes."
    assert "Skipped 1 saved item with no link (for example photos)." in result.notes


def test_youtube_playlists() -> None:
    result = parse_one(SAMPLES / "youtube")
    items = by_id(result)
    assert sorted(items) == ["AbCdEfGhI01", "AbCdEfGhI02", "AbCdEfGhI03", "AbCdEfGhI04"]
    assert items["AbCdEfGhI01"].platform_collection == "Pasta ideas, Watch later"
    assert items["AbCdEfGhI01"].saved_at == "2024-01-10T08:30:00Z"  # the earliest
    assert items["AbCdEfGhI04"].platform_collection == "Old workouts"  # older layout
    assert "Skipped 1 liked video: likes aren't saves." in result.notes


# ---------- zips and folders ----------


def test_zip_gives_the_same_result_as_the_folder(tmp_path: Path) -> None:
    for name in ("tiktok_json", "instagram", "facebook", "youtube"):
        from_folder = parse_one(SAMPLES / name)
        from_zip = parse_one(zip_folder(SAMPLES / name, tmp_path / f"{name}.zip"))
        assert from_zip.items == from_folder.items


def test_folder_with_several_export_zips(tmp_path: Path) -> None:
    drop = tmp_path / "exports"
    drop.mkdir()
    zip_folder(SAMPLES / "tiktok_json", drop / "tiktok.zip")
    zip_folder(SAMPLES / "instagram", drop / "instagram-part-1.zip")
    with ExportSource.open(drop) as source:
        platforms = [result.platform for result in parse_export(source)]
    assert platforms == ["tiktok", "instagram"]


def test_unrelated_files_find_nothing(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    with ExportSource.open(tmp_path) as source:
        assert parse_export(source) == []
