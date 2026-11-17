"""Turn download errors into short reasons a person can understand.

yt-dlp's messages are written for developers ("ERROR: [TikTok] 123: Video
not available, status code 10204"). The app shows the reason next to the
item instead, so it must be plain English.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Why an item couldn't be read. "network" is special: the item isn't marked
# failed, because it will probably work next time.
KINDS = ("private", "login", "region", "gone", "no_media", "network", "other")


@dataclass(frozen=True)
class Reason:
    kind: str
    text: str

    @property
    def is_network(self) -> bool:
        return self.kind == "network"


# Checked in order; the first pattern that matches wins.
_RULES: list[tuple[str, str, str]] = [
    ("network", r"getaddrinfo|timed? ?out|connection (?:reset|refused|aborted)|network is unreachable"
     r"|temporary failure in name resolution|unable to download webpage: <urlopen error|no route to host"
     r"|remote end closed connection|ssl: |\[errno 1100[14]\]",
     "Couldn't reach the website. Check your internet connection and try again."),
    ("private", r"\bprivate\b",
     "This video is private, so only the person who posted it can see it."),
    ("login", r"log ?in|sign in|login required|cookies|age[- ]restricted|confirm your age|not comfortable"
     r"|members[- ]only|join this channel",
     "The site only shows this to signed-in users, and the app never signs in for you."),
    # yt-dlp says "IP address is blocked" for TikTok's status 10204, but TikTok's
    # own page for those says "Video currently unavailable": it was taken down.
    ("gone", r"blocked from accessing",
     "This video was deleted or isn't available any more."),
    ("region", r"not available in your country|geo.?restrict|in your (?:country|region)",
     "This video isn't available in your country."),
    ("gone", r"status code 10204|not available|unavailable|has been removed|was removed|deleted"
     r"|does not exist|doesn't exist|no longer|not found|http error 404|terminated",
     "This video was deleted or isn't available any more."),
    ("no_media", r"unsupported url|no video formats|requested format is not available|no formats|"
     r"there's no video|no media",
     "There's no video or sound here the app can read (it may be a photo post or a link to a web page)."),
]
_COMPILED = [(kind, re.compile(pattern, re.IGNORECASE), text) for kind, pattern, text in _RULES]

# yt-dlp puts "ERROR: [Extractor] id: " in front of every message.
_PREFIX = re.compile(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*)?(?:[\w-]+:\s*)?")


def plain_reason(error: BaseException | str) -> Reason:
    message = str(error)
    for kind, pattern, text in _COMPILED:
        if pattern.search(message):
            return Reason(kind, text)
    short = _PREFIX.sub("", message.strip().splitlines()[0] if message.strip() else "").strip()
    if len(short) > 160:
        short = short[:157] + "…"
    return Reason("other", f"Couldn't read this video: {short or type(error).__name__}")
