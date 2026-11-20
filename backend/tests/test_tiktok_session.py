"""The tests use made-up session values and make no platform requests."""
from __future__ import annotations

from copy import copy

from fastapi.testclient import TestClient
from yt_dlp import YoutubeDL

from app.enrich.fetch import YtDlpFetcher
from app.enrich.tiktok_session import MAX_SESSION_BYTES, TikTokSession

COOKIES = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t0\tsid_tt\tdummy-session\n"
    ".example.org\tTRUE\t/\tTRUE\t0\tsessionid\tother-site\n"
    ".tiktok.com.example.org\tTRUE\t/\tTRUE\t0\tsid_tt\tbogus-domain\n"
    ".tiktok.com\tTRUE\t/\tTRUE\t1\tsessionid\texpired\n"
)


def test_session_endpoint_rejects_untrusted_requests_and_only_returns_state(api: TestClient) -> None:
    url = "/api/enrich/tiktok-session"
    assert TestClient(api.app).put(url, content=COOKIES).status_code in (401, 403)
    headers = {"Content-Type": "application/octet-stream"}
    assert api.put(url, content=b"x" * (MAX_SESSION_BYTES + 1), headers=headers).status_code == 413
    error = api.put(url, content="dummy-session invalid", headers=headers)
    assert error.status_code == 400
    assert "dummy-session" not in error.text

    assert api.put(url, content=COOKIES, headers=headers).json() == {"connected": True}
    assert api.get("/api/enrich").json()["tiktok_session"]
    assert api.delete(url).json() == {"connected": False}
    assert not api.get("/api/enrich").json()["tiktok_session"]


def test_session_cookies_stay_scoped_even_if_the_extractor_copies_them(monkeypatch) -> None:
    session = TikTokSession()
    session.load(COOKIES)
    assert [cookie.name for cookie in session.cookies()] == ["sid_tt"]

    def extract(ydl, url, *, download):
        cookiejar = ydl.cookiejar
        if url.startswith("https://www.tiktok.com/"):
            cookie, = list(cookiejar)
            copied = copy(cookie)
            copied.domain = "cdn.example.org"  # simulates the extractor's media URL behavior
            cookiejar.set_cookie(copied)
            assert cookiejar.get_cookie_header(url) == "sid_tt=dummy-session"
            assert cookiejar.get_cookie_header("http://www.tiktok.com/video") is None
            assert cookiejar.get_cookie_header("https://cdn.example.org/video") is None
        else:
            assert not list(cookiejar)
        return {"id": "example"}

    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    fetcher = YtDlpFetcher(session=session)
    _, page = fetcher.details("https://www.tiktok.com/@creator/video/1000000000", "tiktok")
    assert page.signed_in
    _, page = fetcher.details("https://www.youtube.com/watch?v=abcdefghijk", "youtube")
    assert not page.signed_in
