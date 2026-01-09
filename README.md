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

cd /opt/anime-dl && . .venv/bin/activate && timeout 6s python3 bin/anime-dl.py --config src/config.yaml; echo '--- ls Naruto library ---'; ls -la src/library/Naruto || true; echo '--- log tail ---'; tail -n 50 logs/test-anime-dl.log || true

sudo systemd-run --unit=anime-dl-test \
  --working-directory=/opt/anime-dl \
  --property=Environment="VIRTUAL_ENV=/opt/anime-dl/.venv" \
  --property=Environment="PATH=/opt/anime-dl/.venv/bin:/usr/bin:/bin" \
  /bin/bash -c '
    timeout 6s /opt/anime-dl/.venv/bin/python3 /opt/anime-dl/bin/anime-dl.py --config /opt/anime-dl/src/config.yaml
    echo "--- ls Naruto library ---"
    ls -la /opt/anime-dl/src/library/Naruto || true
    echo "--- log tail ---"
    tail -n 50 /opt/anime-dl/logs/test-anime-dl.log || true
  '
