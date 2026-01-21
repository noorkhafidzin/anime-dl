#!/usr/bin/env python3
"""Simple grabber for anime episode pages.

Features:
- Loads `config/config.yaml`.
- For each mapping that includes a `source` URL, fetches the page
  and extracts the latest episode link/title.
- Fetches the episode page and extracts a download link by quality
  and host priority.
- Sends final download links to the local `api.py` `/add` endpoint.
- Records discovered episode links into a sqlite DB to avoid
  duplicate processing.
- Can run once or be scheduled daily/weekly via simple scheduler
  configured in `config/config.yaml` under `scheduler`.

This implementation uses only stdlib plus `requests` and `pyyaml`
which are already present in `requirements.txt`.
"""
import os
import re
import sys
import json
import time
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from urllib.parse import urljoin

import requests
import yaml

DEFAULT_HOST_PRIORITY = ["Pdrain", "Mega", "Acefile", "GoFile", "KFiles", "ODFiles"]
DEFAULT_QUALITY = "1080p"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.getenv("ANIME_DL_CONFIG", os.path.join(BASE_DIR, "config", "config.yaml"))
DB_PATH = os.path.join(BASE_DIR, "data", "episodes.db")


def load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def setup_logging(log_file):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)


def ensure_db(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            anime_key TEXT,
            season INTEGER,
            episode_number INTEGER,
            episode_link TEXT,
            host TEXT,
            quality TEXT,
            retrieved_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def get_last_episode(conn, anime_key, season):
    cur = conn.cursor()
    cur.execute(
        "SELECT episode_link, episode_number FROM episodes WHERE anime_key=? AND season=? ORDER BY id DESC LIMIT 1",
        (anime_key, season),
    )
    row = cur.fetchone()
    return row if row else (None, None)


def save_episode(conn, anime_key, season, episode_number, episode_link, host, quality):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO episodes (anime_key, season, episode_number, episode_link, host, quality, retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (anime_key, season, episode_number, episode_link, host, quality, datetime.utcnow().isoformat()),
    )
    conn.commit()


def fetch_url(url, timeout=20):
    headers = {"User-Agent": "anime-dl-grabber/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_latest_episode(html, base_url=None):
    # Try smokelister -> first <ul> -> first <a>
    header_regex = re.compile(r'<div[^>]*class="smokelister"[^>]*>\s*<span[^>]*class="monktit"[^>]*>[^<]*episode list[^<]*', re.I)
    m = header_regex.search(html)
    if m:
        slice_html = html[m.start():]
        ul_match = re.search(r"<ul>([\s\S]*?)</ul>", slice_html, re.I)
        if ul_match:
            ul_content = ul_match.group(1)
            item = re.search(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', ul_content, re.I)
            if item:
                link = item.group(1)
                title = item.group(2).strip()
                if base_url:
                    link = urljoin(base_url, link)
                return {"link": link, "title": title}

    # Fallback: find first anchor that contains the word "Episode" or a number
    fallback = re.search(r'<a\s+href="([^"]+)"[^>]*>([^<]*episode[^<]*|[^<]*\d{1,3}[^<]*)</a>', html, re.I)
    if fallback:
        link = fallback.group(1)
        title = fallback.group(2).strip()
        if base_url:
            link = urljoin(base_url, link)
        return {"link": link, "title": title}

    raise RuntimeError("Latest episode block not found")


def extract_latest_with_mapping(mapping, html, base_url=None):
    cfg = mapping.get("extract_latest")
    if not cfg:
        return extract_latest_episode(html, base_url=base_url)

    t = cfg.get("type", "regex")
    if t == "smokelister":
        return extract_latest_episode(html, base_url=base_url)

    if t == "regex":
        pattern = cfg.get("pattern")
        if not pattern:
            raise RuntimeError("extract_latest regex pattern not provided")
        m = re.search(pattern, html, re.I)
        if not m:
            raise RuntimeError("extract_latest regex did not match")
        # allow numeric or named groups
        link = None
        title = None
        if cfg.get("link_group"):
            link = m.group(int(cfg.get("link_group")))
        elif "link" in m.groupdict():
            link = m.group("link")
        else:
            link = m.group(1)

        if cfg.get("title_group"):
            title = m.group(int(cfg.get("title_group")))
        elif "title" in m.groupdict():
            title = m.group("title")
        else:
            # try group 2 if present
            try:
                title = m.group(2)
            except Exception:
                title = ""

        if base_url:
            link = urljoin(base_url, link)
        return {"link": link, "title": title.strip()}

    if t == "function":
        module_name = cfg.get("module")
        function_name = cfg.get("function")
        if not module_name or not function_name:
            raise RuntimeError("extract_latest function requires 'module' and 'function'")
        try:
            import importlib
            mod = importlib.import_module(module_name)
            func = getattr(mod, function_name)
            return func(html, base_url=base_url)
        except Exception as e:
            raise RuntimeError(f"Failed to load custom function {module_name}.{function_name}: {e}")

    raise RuntimeError(f"Unknown extract_latest type: {t}")


def extract_download_link(html, quality=DEFAULT_QUALITY, host_priority=None):
    host_priority = host_priority or DEFAULT_HOST_PRIORITY
    # Find marker for quality (e.g. <strong>Mp4 1080p</strong>)
    marker_regex = re.compile(r"<strong>\s*(?:mp4|mkv)\s*" + re.escape(quality) + r"\s*</strong>", re.I)
    m = marker_regex.search(html)
    if not m:
        raise RuntimeError(f"Section for quality {quality} not found")

    marker_start = m.start()
    # find nearest closing </li> after marker_start, else </ul>
    li_end = html.find("</li>", marker_start)
    ul_end = html.find("</ul>", marker_start)
    end_index = li_end if (li_end != -1 and (li_end < ul_end or ul_end == -1)) else ul_end
    if end_index == -1:
        # as last resort, take 1000 chars after marker
        block = html[marker_start: marker_start + 1000]
    else:
        block = html[marker_start:end_index]

    for host in host_priority:
        host_anchor = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>\s*' + re.escape(host) + r"\s*</a>", re.I)
        am = host_anchor.search(block)
        if am:
            return {"link": am.group(1), "host": host, "quality": quality}

    raise RuntimeError(f"No hosts from priority list found for quality {quality}")


def extract_download_with_mapping(mapping, html):
    cfg = mapping.get("extract_download")
    # if no mapping-specific config, use defaults
    if not cfg:
        # pass through to default extractor
        quality = mapping.get("target_quality") or DEFAULT_QUALITY
        host_priority = mapping.get("host_priority")
        return extract_download_link(html, quality=quality, host_priority=host_priority)

    t = cfg.get("type", "quality_block")
    if t == "quality_block":
        quality = cfg.get("quality") or mapping.get("target_quality") or DEFAULT_QUALITY
        host_priority = cfg.get("host_priority") or mapping.get("host_priority") or DEFAULT_HOST_PRIORITY
        return extract_download_link(html, quality=quality, host_priority=host_priority)

    if t == "regex":
        pattern = cfg.get("pattern")
        if not pattern:
            raise RuntimeError("extract_download regex pattern not provided")
        m = re.search(pattern, html, re.I)
        if not m:
            raise RuntimeError("extract_download regex did not match")
        # similar logic for link group
        if cfg.get("link_group"):
            link = m.group(int(cfg.get("link_group")))
        elif "link" in m.groupdict():
            link = m.group("link")
        else:
            link = m.group(1)
        host = cfg.get("host")
        quality = cfg.get("quality") or DEFAULT_QUALITY
        return {"link": link, "host": host, "quality": quality}

    if t == "function":
        module_name = cfg.get("module")
        function_name = cfg.get("function")
        if not module_name or not function_name:
            raise RuntimeError("extract_download function requires 'module' and 'function'")
        try:
            import importlib
            mod = importlib.import_module(module_name)
            func = getattr(mod, function_name)
            return func(html)
        except Exception as e:
            raise RuntimeError(f"Failed to load custom function {module_name}.{function_name}: {e}")

    raise RuntimeError(f"Unknown extract_download type: {t}")


def send_to_api(api_url, links, package_name=None, timeout=15):
    payload = {"links": links}
    if package_name:
        payload["packageName"] = package_name
    r = requests.post(api_url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def send_discord(webhook_url, message):
    if not webhook_url:
        logging.warning("No discord webhook configured")
        return
    payload = {"content": message}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception:
        logging.exception("Failed sending discord message")


def parse_episode_number(title):
    m = re.search(r"(\d{1,3})", title)
    if m:
        return int(m.group(1))
    return None


def process_mapping(mapping, cfg, conn):
    anime_key = mapping.get("anime_key")
    season = mapping.get("season")
    source = mapping.get("source")
    if not source:
        logging.info("Skipping mapping %s because no 'source' URL is configured", anime_key)
        return

    logging.info("Processing %s from %s", anime_key, source)
    try:
        src_html = fetch_url(source)
        latest = extract_latest_with_mapping(mapping, src_html, base_url=source)
        latest_link = latest["link"]
        latest_title = latest["title"]
    except Exception as e:
        logging.exception("Failed to extract latest episode for %s: %s", anime_key, e)
        send_discord(cfg.get("discord_webhook"), f"Failed to extract latest episode for {anime_key}: {e}")
        return

    last_link, last_episode = get_last_episode(conn, anime_key, season)
    if last_link and last_link == latest_link:
        logging.info("No update for %s (latest link unchanged)", anime_key)
        send_discord(cfg.get("discord_webhook"), f"No update for {anime_key} (latest link unchanged)")
        return

    # parse episode number
    ep_num = parse_episode_number(latest_title) or parse_episode_number(latest_link) or None
    # allow mapping episode_offset adjustments
    if mapping.get("episode_offset"):
        off = mapping["episode_offset"]
        start = off.get("start")
        subtract = off.get("subtract")
        if ep_num is not None and subtract is not None:
            ep_num = ep_num - subtract

    # fetch episode page and search for download
    try:
        ep_html = fetch_url(latest_link)
        dl = extract_download_with_mapping(mapping, ep_html)
        final_link = urljoin(latest_link, dl["link"]) if latest_link else dl["link"]
        logging.info("Found download for %s ep %s -> %s (%s)", anime_key, ep_num, dl["host"], final_link)

        api_url = cfg.get("api_add_url") or "http://127.0.0.1:5000/add"
        # package name should be the anime title if available
        package_name = "anime"
        send_to_api(api_url, [final_link], package_name=package_name)
        save_episode(conn, anime_key, season, ep_num or -1, latest_link, dl.get("host"), dl.get("quality"))

    except Exception as e:
        logging.exception("No download found for %s: %s", anime_key, e)
        # if no update (i.e. last_link is None) or download not found, notify
        send_discord(cfg.get("discord_webhook"), f"No download found for {anime_key} latest: {e}")


def run_once(cfg, conn):
    mappings = cfg.get("mappings", [])
    for mapping in mappings:
        # Skip mappings that have their own scheduler (they run in their own thread)
        if mapping.get("scheduler"):
            continue
        try:
            process_mapping(mapping, cfg, conn)
        except Exception:
            logging.exception("Unhandled error processing mapping %s", mapping.get("anime_key"))


def mapping_scheduler_loop(mapping, cfg, conn, stop_event: threading.Event):
    sched = mapping.get("scheduler")
    if not sched:
        return
    logging.info("Starting mapping scheduler for %s: %s", mapping.get("anime_key"), sched)
    # initial wait until next run
    while not stop_event.is_set():
        wait = seconds_until_next_run(sched)
        logging.info("Mapping %s next run in %s seconds", mapping.get("anime_key"), int(wait))
        end = time.time() + wait
        while time.time() < end:
            if stop_event.is_set():
                return
            time.sleep(1)

        try:
            process_mapping(mapping, cfg, conn)
        except Exception:
            logging.exception("Unhandled error in mapping_scheduler for %s", mapping.get("anime_key"))


def seconds_until_next_run(schedule_cfg):
    # schedule_cfg: {type: 'daily'|'weekly'|'interval', time: 'HH:MM', days: [0-6], hours: int, minutes: int} 
    now = datetime.now()
    t = schedule_cfg.get("type")
    if t == "daily":
        hh, mm = map(int, schedule_cfg.get("time", "00:00").split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    if t == "weekly":
        hh, mm = map(int, schedule_cfg.get("time", "00:00").split(":"))
        days = schedule_cfg.get("days", [])  # list of ints 0=Monday
        if not days:
            days = [0]
        # find next day from days
        for add in range(0, 8):
            cand = now + timedelta(days=add)
            if cand.weekday() in days:
                cand_target = cand.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand_target > now:
                    return (cand_target - now).total_seconds()
        return 24 * 3600

    if t == "interval":
        hours = schedule_cfg.get("hours", 0)
        minutes = schedule_cfg.get("minutes", 0)
        total_seconds = hours * 3600 + minutes * 60
        if total_seconds <= 0:
            total_seconds = 3600  # default 1 hour
        return total_seconds

    # default: run immediately
    return 0


def scheduler_loop(cfg, conn, stop_event: threading.Event):
    sched = cfg.get("scheduler")
    if not sched:
        logging.info("No scheduler configured; running once")
        run_once(cfg, conn)
        return

    logging.info("Starting scheduler: %s", sched)
    while not stop_event.is_set():
        wait = seconds_until_next_run(sched)
        logging.info("Next run in %s seconds", int(wait))
        # wait with support for early exit
        end = time.time() + wait
        while time.time() < end:
            if stop_event.is_set():
                return
            time.sleep(1)

        run_once(cfg, conn)


def main():
    cfg = load_config()
    log_file = cfg.get("log_file") or os.path.join(BASE_DIR, "logs", "grabber.log")
    setup_logging(log_file)
    conn = ensure_db()

    stop_event = threading.Event()
    try:
        # start mapping-specific schedulers
        mapping_threads = []
        for mapping in cfg.get("mappings", []):
            if mapping.get("scheduler"):
                t = threading.Thread(target=mapping_scheduler_loop, args=(mapping, cfg, conn, stop_event), daemon=True)
                t.start()
                mapping_threads.append(t)

        # start top-level scheduler (handles mappings without per-mapping scheduler)
        scheduler_loop(cfg, conn, stop_event)
    except KeyboardInterrupt:
        logging.info("Interrupted, stopping")
    finally:
        stop_event.set()
        conn.close()


if __name__ == "__main__":
    main()
