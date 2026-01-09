#!/usr/bin/env python3
"""Robust replacement for anime-dl.sh: scan + watch + move + Discord notify."""
import argparse
import logging
import os
import re
import shutil
import stat
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None

try:
    import requests
except Exception:
    requests = None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except Exception:
    Observer = None
    FileSystemEventHandler = object

ALLOWED_EXT = {"mkv", "mp4", "avi", "mov"}


def load_config(path: Path):
    if not path.exists():
        raise SystemExit(f"Config not found: {path}")
    if path.suffix in (".yml", ".yaml"):
        if yaml is None:
            raise SystemExit("PyYAML required to load YAML config. Install requirements.txt")
        with path.open() as f:
            return yaml.safe_load(f)
    else:
        # treat as simple key=value like fallback? prefer YAML
        raise SystemExit("Please use a YAML config (path ending with .yaml)")


def setup_logging(log_file: str):
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(str(log_path), maxBytes=10 * 1024 * 1024, backupCount=3)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def human_size(num: int):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"


def stable_file(path: Path, checks: int = 2, delay: float = 1.0) -> bool:
    try:
        last = path.stat().st_size
    except Exception:
        return False
    for _ in range(checks):
        time.sleep(delay)
        try:
            cur = path.stat().st_size
        except Exception:
            return False
        if cur != last:
            last = cur
        else:
            return True
    return False


def extract_episode(filename: str):
    # Prioritized patterns
    pat_list = [
        r"S(?P<s>\d{1,2})[ \-_.]*E(?P<e>\d{1,4})",
        r"(?i)E(?P<e>\d{1,4})",
        r"(?i)Ep(?:isode)?[ _.-]?(?P<e>\d{1,4})",
    ]
    for p in pat_list:
        m = re.search(p, filename)
        if m:
            s = m.groupdict().get("s")
            e = m.groupdict().get("e")
            return (int(e), int(s) if s else None) if e else (None, None)

    # Fallback: first standalone number that is not a resolution (e.g., 1080p)
    m = re.search(r"(?<!\d)(?P<n>\d{1,4})(?!p|\d)", filename)
    if m:
        return (int(m.group('n')), None)
    return (None, None)

def apply_episode_offset(ep_num: int, mapping: dict):
    offset = mapping.get("episode_offset")
    if not offset:
        return ep_num

    try:
        start = int(offset.get("start", 0))
        subtract = int(offset.get("subtract", 0))
    except (TypeError, ValueError):
        logging.warning("Invalid episode_offset config: %s", offset)
        return ep_num

    if ep_num >= start:
        new_ep = ep_num - subtract
        if new_ep <= 0:
            logging.warning("Episode offset result invalid: %s -> %s", ep_num, new_ep)
            return ep_num

        logging.info("EPISODE OFFSET APPLIED: %s -> %s", ep_num, new_ep)
        return new_ep

    return ep_num

def normalize_filename(filename: str) -> str:
    # replace non-alnum with spaces and lowercase for token matching
    return re.sub(r'[^A-Za-z0-9]+', ' ', filename).lower()


def parse_mapping(filename: str, mappings: list):
    normalized = normalize_filename(filename)
    tokens = normalized.split()
    for m in mappings:
        # first try pattern if present
        pat = m.get("pattern")
        if pat:
            try:
                if re.search(pat, filename, re.IGNORECASE):
                    return m
            except re.error:
                logging.warning("Invalid regex in mapping: %s", pat)
        # then try aliases list (token based)
        aliases = m.get("aliases") or []
        for a in aliases:
            if a.lower() in tokens:
                return m
    return None
    return None


def notify_discord(webhook: str, anime_title: str, new_name: str, filesize: str, season: int):
    if requests is None:
        logging.warning("requests not installed; cannot send Discord notification")
        return
    msg = (
        f"🎬 **ANIME SUDAH DIDOWNLOAD!**\n"
        f"📺 Judul: **{anime_title} (Season {season})**\n"
        f"📝 Nama: `{new_name}`\n"
        f"💾 Size: `{filesize}`\n"
        f"⏰ Ditambahkan: <t:{int(time.time())}:R>"
    )
    try:
        r = requests.post(webhook, json={"content": msg}, timeout=10)
        if r.status_code not in (200, 204):
            logging.error("Discord webhook failed: %s %s", r.status_code, r.text)
    except Exception as e:
        logging.exception("Failed to notify Discord: %s", e)


def process_file(path: Path, cfg: dict):
    filename = path.name
    ext = path.suffix.lstrip('.').lower()
    if ext not in ALLOWED_EXT:
        logging.info("SKIPPED: unsupported extension - %s", filename)
        return
    if not stable_file(path):
        logging.info("SKIPPED: file not stable yet - %s", filename)
        return

    m = parse_mapping(filename, cfg.get('mappings', []))
    if not m:
        logging.info("SKIPPED: pattern not matched - %s", filename)
        return

    anime_key = m.get('anime_key')
    season_cfg = m.get('season')
    anime_title = cfg.get('titles', {}).get(anime_key, anime_key)

    ep_num, season_from_name = extract_episode(filename)
    season = season_from_name if season_from_name else season_cfg
    if ep_num is None:
        logging.info("SKIPPED: episode not found - %s", filename)
        return

    ep_num = apply_episode_offset(ep_num, m)
    
    new_name = f"{anime_title} S{int(season):02d}E{int(ep_num):02d}.{ext}"
    library_dir = cfg.get('library_dirs', {}).get(anime_key)
    if not library_dir:
        logging.error("No library dir for anime key: %s", anime_key)
        return
    target_dir = Path(library_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    new_path = target_dir / new_name

    try:
        shutil.move(str(path), str(new_path))
        os.chmod(str(new_path), 0o664)
        size = human_size(new_path.stat().st_size)
        logging.info("SUCCESS: %s -> %s (Season %s)", filename, new_name, season)
        if cfg.get('discord_webhook'):
            notify_discord(cfg['discord_webhook'], anime_title, new_name, size, season)
    except Exception:
        logging.exception("FAILED to move %s", filename)


class WatchHandler(FileSystemEventHandler):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    def on_created(self, event):
        if event.is_directory:
            return
        process_file(Path(event.src_path), self.cfg)

    def on_moved(self, event):
        if event.is_directory:
            return
        process_file(Path(event.dest_path), self.cfg)


def initial_scan(watch_dir: Path, cfg: dict):
    for p in watch_dir.rglob('*'):
        if p.is_file() and p.suffix.lstrip('.').lower() in ALLOWED_EXT:
            process_file(p, cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', '-c', default='config.yaml')
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)

    setup_logging(cfg.get('log_file', 'logs/anime-dl.log'))

    # minimal validations
    if 'watch_dir' not in cfg:
        logging.error('watch_dir missing in config')
        raise SystemExit(1)
    watch_dir = Path(cfg['watch_dir'])
    if not watch_dir.exists():
        logging.error('watch_dir does not exist: %s', watch_dir)
        raise SystemExit(1)

    # initial scan
    logging.info('Starting initial scan...')
    initial_scan(watch_dir, cfg)

    if Observer is None:
        logging.warning('watchdog not installed; exiting after initial scan')
        return

    logging.info('Starting watcher...')
    observer = Observer()
    handler = WatchHandler(cfg)
    observer.schedule(handler, str(watch_dir), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == '__main__':
    main()
