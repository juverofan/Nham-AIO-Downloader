import re
import time
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

API_BASE = "https://www.wattpad.com/api/v3"
API_LEGACY = "https://www.wattpad.com/apiv2"


class WattpadStory:
    def __init__(self, url: str):
        self.url = url.strip()
        self.story_id = self._extract_id()
        self.title = ""
        self.author = ""
        self.description = ""
        self.chapters = []
        self.cover_url = ""
        self._raw_story = None

    def _extract_id(self) -> str:
        m = re.search(r"wattpad\.com/story/(\d+)", self.url)
        if not m:
            m = re.search(r"wattpad\.com/(\d+)", self.url)
        if not m:
            # Accept plain numeric
            if self.url.strip().isdigit():
                return self.url.strip()
            raise ValueError(f"Invalid Wattpad URL: {self.url}")
        return m.group(1)

    def _api_get(self, url: str) -> dict:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _legacy_get(self, url: str) -> str:
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html,*/*"}, timeout=15)
        resp.raise_for_status()
        return resp.text

    def fetch_info(self):
        story = self._api_get(f"{API_BASE}/stories/{self.story_id}")
        self._raw_story = story
        self.title = story.get("title", "Unknown")
        user = story.get("user", {})
        self.author = user.get("username", user.get("name", "Unknown"))
        self.description = (story.get("description") or "").strip()
        self.cover_url = story.get("cover", "") or ""

        parts = story.get("parts", [])
        self.chapters = []
        for p in parts:
            if p.get("draft"):
                continue
            self.chapters.append({
                "id": p["id"],
                "title": p.get("title", f"Chapter {len(self.chapters)+1}"),
                "url": p.get("url", ""),
                "length": p.get("length", 0),
            })

        return {
            "title": self.title,
            "author": self.author,
            "chapters": len(self.chapters),
        }

    def fetch_chapter(self, chapter_url: str = None, chapter_id: str = None) -> str:
        if chapter_id is None:
            if chapter_url and "/" in str(chapter_url):
                m = re.search(r'/(\d+)$', chapter_url)
                if m:
                    chapter_id = m.group(1)
                else:
                    # search by URL in chapters list
                    for ch in self.chapters:
                        if ch["url"] == chapter_url:
                            chapter_id = ch["id"]
                            break
        if chapter_id is None and self.chapters:
            # fallback: extract from URL pattern
            m = re.search(r'/(\d+)$', str(chapter_url))
            if m:
                chapter_id = m.group(1)
        if chapter_id is None:
            raise ValueError(f"Cannot determine chapter ID from: {chapter_url}")

        try:
            html = self._legacy_get(f"{API_LEGACY}/storytext?id={chapter_id}")
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = soup.find_all("p")
            text_parts = []
            for p in paragraphs:
                # Remove data attributes noise
                text = p.get_text(strip=True)
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch chapter {chapter_id}: {e}")

    def fetch_all_chapters(self, delay: float = 0.5, progress_callback=None):
        texts = []
        total = len(self.chapters)
        for idx, ch in enumerate(self.chapters):
            if progress_callback:
                progress_callback(idx, total, ch["title"])
            text = self.fetch_chapter(chapter_id=ch["id"])
            texts.append(text)
            if idx < total - 1:
                time.sleep(delay)
        return texts


def format_as_markdown(story: WattpadStory, chapters_text: list) -> str:
    lines = []
    lines.append(f"# {story.title}")
    lines.append("")
    lines.append(f"**Author:** {story.author}")
    lines.append("")
    if story.description:
        lines.append(f"*{story.description}*")
        lines.append("")
    lines.append("---")
    lines.append("")
    for ch_text, ch_info in zip(chapters_text, story.chapters):
        lines.append(f"## {ch_info['title']}")
        lines.append("")
        lines.append(ch_text)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)
