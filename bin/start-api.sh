#!/bin/bash
source /opt/anime-dl/src/venv/bin/activate
python3 /opt/anime-dl/src/jd2-server.py >> /opt/anime-dl/logs/jd2-server.log 2>&1
