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
    ("private", r"\bprivate\b|do not have permission to view this post|status code 102(?:16|22)",
     "This post is private or restricted. Open it with an account that already has access."),
    ("region", r"not available in your country|geo.?restrict|in your (?:country|region)",
     "This video isn't available in your country."),
    ("login", r"log ?in|sign in|cookies|age[- ]restricted|confirm your age|not comfortable"
     r"|members[- ]only|join this channel",
     "The platform asked for sign-in. Open the original video to check whether your account can see it."),
    ("blocked", r"blocked from accessing|status code 10204|http error (?:403|429)|rate.limit",
     "The site blocked this request. The video may still be available. Try again or open the original."),
    ("gone", r"(?:has been|was) (?:removed|deleted)\b|\bdeleted by\b",
     "The platform reports that this video was removed."),
    ("no_media", r"unsupported url|no video formats|requested format is not available|no formats|"
     r"there's no video|no media",
     "Keptwise couldn't find a playable video. This may be a photo post or a link to a web page."),
    ("unavailable", r"not available|unavailable|does not exist|doesn't exist|no longer|not found|http error 404",
     "Keptwise couldn't open this video. Check the original link or try again."),
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
