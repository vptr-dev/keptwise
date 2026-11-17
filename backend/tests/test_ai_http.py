"""Tests for the small HTTP helper the AI providers use."""

from __future__ import annotations

from app.ai.http import direct_local_url


def test_localhost_goes_straight_to_ipv4() -> None:
    assert direct_local_url("http://localhost:11434/api/tags") == "http://127.0.0.1:11434/api/tags"
    assert direct_local_url("http://localhost/v1") == "http://127.0.0.1/v1"


def test_other_addresses_are_left_alone() -> None:
    for url in (
        "https://api.anthropic.com/v1/messages",
        "http://127.0.0.1:1234/v1",
        "http://my-localhost-box:11434",
    ):
        assert direct_local_url(url) == url
