Simple Python replacement for `anime-dl.sh`.

Usage

1. Create `config.yaml` (see `config.yaml.example`).
2. Create virtualenv and install requirements:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

3. Run:

```bash
bin/anime-dl.py --config config.yaml
```

Notes
- Script performs an initial recursive scan and then watches `watch_dir` for new files.
- If `watchdog` isn't available, the script will perform only initial scan then exit.
- Discord notifications use `requests.post(json=...)` to avoid manual escaping.

Ask regex:
- filename: 
- expected result:
- wrong result:
- code :
```python
def extract_episode(filename: str):
    import re
    # Search pattern: Season + Episode (S05E01, S5--01, S5.01)
    s_e_match = re.search(r"S(?P<s>\d{1,2})[ \-_.]+(?P<e>\d{1,4})", filename, re.IGNORECASE)
    if s_e_match:
        s = s_e_match.group("s")
        e = s_e_match.group("e")
        return int(e), int(s)

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
```