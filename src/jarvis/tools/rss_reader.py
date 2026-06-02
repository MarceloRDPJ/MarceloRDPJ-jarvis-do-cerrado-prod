import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List

from jarvis.config import Config
from jarvis.tools.web_fetch import fetch_url

logger = logging.getLogger(__name__)


@dataclass
class RSSItem:
    title: str
    link: str
    published: str
    summary: str


def read_feeds(limit: int = 5) -> List[RSSItem]:
    if not Config.RSS_FEEDS_ENABLED or not Config.RSS_FEEDS:
        return []

    items = []
    for feed_url in Config.RSS_FEEDS:
        result = fetch_url(feed_url)
        if not result.ok:
            logger.warning(f"RSS indisponível: {feed_url} ({result.error})")
            continue
        items.extend(_parse_rss(result.text, limit=limit - len(items)))
        if len(items) >= limit:
            break
    return items[:limit]


def _parse_rss(xml_text: str, limit: int = 5) -> List[RSSItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"Falha ao parsear RSS: {e}")
        return []

    parsed = []
    channel_items = root.findall(".//item")
    if channel_items:
        for item in channel_items[:limit]:
            parsed.append(RSSItem(
                title=_node_text(item, "title"),
                link=_node_text(item, "link"),
                published=_node_text(item, "pubDate"),
                summary=_node_text(item, "description"),
            ))
        return parsed

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns)[:limit]:
        link = ""
        link_node = entry.find("atom:link", ns)
        if link_node is not None:
            link = link_node.attrib.get("href", "")
        parsed.append(RSSItem(
            title=_node_text(entry, "atom:title", ns),
            link=link,
            published=_node_text(entry, "atom:updated", ns) or _node_text(entry, "atom:published", ns),
            summary=_node_text(entry, "atom:summary", ns),
        ))
    return parsed


def _node_text(parent, path: str, ns: dict = None) -> str:
    node = parent.find(path, ns or {})
    return "" if node is None or node.text is None else node.text.strip()
