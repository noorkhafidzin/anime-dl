import streamlit as st
import yaml
import os
import logging
from logging.handlers import RotatingFileHandler

# ------------------ Paths ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder web.py
CONFIG_FILE = os.path.normpath(os.path.join(BASE_DIR, "..", "config", "config.yaml"))
LOG_FILE = os.path.normpath(os.path.join(BASE_DIR, "..", "logs", "web.log"))

os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ------------------ Create logger ------------------
def create_logger(name, level='INFO', file=None):
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(level)

    # StreamHandler
    if sum(isinstance(h, logging.StreamHandler) for h in logger.handlers) == 0:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(ch)

    # FileHandler
    if file is not None:
        if sum(isinstance(h, logging.FileHandler) for h in logger.handlers) == 0:
            fh = RotatingFileHandler(file, maxBytes=1_000_000, backupCount=3)
            fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))
            logger.addHandler(fh)

    return logger

if 'logger' not in st.session_state:
    st.session_state['logger'] = create_logger('AnimeConfigWebUI', level='INFO', file=LOG_FILE)
logger = st.session_state['logger']
logger.info("Starting anime-dl Config Web UI")

# ------------------ Helpers ------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config_to_file(cfg):
    with open(CONFIG_FILE, 'w') as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    logger.info(f"Config saved to {CONFIG_FILE}")

# ------------------ Session State ------------------
if 'config' not in st.session_state:
    st.session_state.config = load_config()
if 'titles' not in st.session_state:
    st.session_state.titles = st.session_state.config.get('titles', {})
if 'library_dirs' not in st.session_state:
    st.session_state.library_dirs = st.session_state.config.get('library_dirs', {})
if 'mappings' not in st.session_state:
    st.session_state.mappings = st.session_state.config.get('mappings', [])

if 'delete_title_key' not in st.session_state:
    st.session_state.delete_title_key = None
if 'delete_mapping_index' not in st.session_state:
    st.session_state.delete_mapping_index = None

config = st.session_state.config
titles = st.session_state.titles
library_dirs = st.session_state.library_dirs
mappings = st.session_state.mappings

# ------------------ UI ------------------
st.set_page_config(
    page_title="anime-dl Config WEB UI",
    page_icon="📺",
    layout="centered",
)
st.title("anime-dl Config Editor")
st.header("General Settings")

config["watch_dir"] = st.text_input("Watch Directory", config.get("watch_dir", ""), key="watch_dir")
config["log_file"] = st.text_input("Log File", config.get("log_file", ""), key="log_file")
config["discord_webhook"] = st.text_input("Discord Webhook", config.get("discord_webhook", ""), key="discord_webhook")

# ------------------ Titles ------------------
st.header("Titles & Library Dirs")

def delete_title_callback(key):
    removed_title = titles.pop(key)
    library_dirs.pop(key, None)
    removed_mappings = [m for m in mappings if m.get("anime_key") == key]
    mappings[:] = [m for m in mappings if m.get("anime_key") != key]

    logger.info(f"Deleted title: {key}")
    for m in removed_mappings:
        logger.info(f"Deleted mapping '{m.get('pattern')}' because it used deleted title '{key}'")
    st.success(f"Deleted title '{key}' and {len(removed_mappings)} mapping(s) related")
    st.session_state.delete_title_key = None  # reset

for key in list(titles.keys()):
    st.text_input(f"{key}", titles[key], key=f"title_{key}")
    col1, col2 = st.columns([0.2,0.8])
    with col1:
        st.button("Delete", key=f"del_title_{key}", on_click=lambda k=key: st.session_state.update({'delete_title_key': k}))
    if st.session_state.delete_title_key == key:
        st.warning(f"Are you sure you want to delete title '{key}'? This will also delete related mappings.")
        colc1, colc2 = st.columns([0.2,0.8])
        with colc1:
            st.button("Confirm Delete", key=f"confirm_delete_{key}", on_click=lambda k=key: delete_title_callback(k))

# Add new title
new_title_key = st.text_input("New Title Key", key="new_title_key")
new_title_val = st.text_input("New Title Value", key="new_title_val")
if st.button("Add Title"):
    if new_title_key and new_title_val:
        titles[new_title_key] = new_title_val
        library_dirs[new_title_key] = ""
        logger.info(f"Added title: {new_title_key} -> {new_title_val}")
        st.success(f"Added title '{new_title_key}'")

# Library dirs
st.subheader("Library Directories")
for key in list(library_dirs.keys()):
    library_dirs[key] = st.text_input(f"{key} Dir", library_dirs[key], key=f"lib_{key}")

config["titles"] = titles
config["library_dirs"] = library_dirs

# ------------------ Mappings ------------------
st.header("Mappings")

def delete_mapping_callback(index):
    removed_map = mappings.pop(index)
    logger.info(f"Deleted mapping {index+1}: {removed_map.get('pattern','')}")
    st.success(f"Deleted mapping {index+1}")
    st.session_state.delete_mapping_index = None  # reset

for i, mapping in enumerate(list(mappings)):
    with st.expander(f"Mapping {i+1}: {mapping.get('pattern','')}", expanded=(st.session_state.delete_mapping_index==i)):
        mapping["pattern"] = st.text_input("Pattern", mapping.get("pattern",""), key=f"map_pattern_{i}")
        anime_keys = list(titles.keys())
        if mapping.get("anime_key") not in anime_keys:
            mapping["anime_key"] = anime_keys[0] if anime_keys else ""
        index = anime_keys.index(mapping["anime_key"]) if anime_keys else 0
        mapping["anime_key"] = st.selectbox("Anime Key", anime_keys, index=index, key=f"map_key_{i}")

        mapping["season"] = st.number_input("Season", min_value=1, value=mapping.get("season",1), key=f"map_season_{i}")
        aliases_str = ", ".join(mapping.get("aliases", []))
        aliases_input = st.text_input("Aliases (comma separated)", aliases_str, key=f"map_alias_{i}")
        mapping["aliases"] = [a.strip() for a in aliases_input.split(",") if a.strip()]

        episode_offset = mapping.get("episode_offset", {})
        start_val = episode_offset.get("start",1)
        subtract_val = episode_offset.get("subtract",0)
        if st.checkbox("Use Episode Offset", key=f"use_offset_{i}", value="episode_offset" in mapping):
            start_val = st.number_input("Offset Start", value=start_val, min_value=1, key=f"offset_start_{i}")
            subtract_val = st.number_input("Offset Subtract", value=subtract_val, min_value=0, key=f"offset_sub_{i}")
            mapping["episode_offset"] = {"start": start_val, "subtract": subtract_val}
        else:
            mapping.pop("episode_offset", None)

    colm1, colm2 = st.columns([0.2,0.8])
    with colm1:
        st.button("Delete Mapping", key=f"del_map_{i}", on_click=lambda idx=i: st.session_state.update({'delete_mapping_index': idx}))
    if st.session_state.delete_mapping_index == i:
        st.warning(f"Are you sure you want to delete mapping '{mapping.get('pattern','')}'?")
        colc1, colc2 = st.columns([0.2,0.8])
        with colc1:
            st.button("Confirm Delete", key=f"confirm_del_map_{i}", on_click=lambda idx=i: delete_mapping_callback(idx))

# Add new mapping
st.subheader("Add New Mapping")
new_map_pattern = st.text_input("Pattern", key="new_map_pattern")
new_map_anime_key = st.selectbox("Anime Key", list(titles.keys()), key="new_map_key")
new_map_season = st.number_input("Season", min_value=1, value=1, key="new_map_season")
if st.button("Add Mapping"):
    if new_map_pattern and new_map_anime_key:
        mappings.append({
            "pattern": new_map_pattern,
            "anime_key": new_map_anime_key,
            "season": new_map_season,
            "aliases": []
        })
        logger.info(f"Added mapping: {new_map_pattern} -> {new_map_anime_key}")
        st.success(f"Added mapping '{new_map_pattern}'")

config["mappings"] = mappings

# ------------------ Save Config ------------------
st.header("Save Config")
def save_config_callback():
    save_config_to_file(config)
    st.session_state['config'] = load_config()  # force UI refresh
    st.success("Config saved successfully!")

st.button("Save Config", on_click=save_config_callback)
