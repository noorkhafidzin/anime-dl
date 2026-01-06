#!/bin/bash
source "$(dirname "$0")/../src/anime-config.sh"

touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

notify_discord() {
  local anime_title="$1"
  local filename="$2"
  local new_path="$3"
  local filesize="$4"
  local season_num="$5"

  local message="🎬 **ANIME SUDAH DIDOWNLOAD!**\n"
  message+="📺 Judul: **$anime_title** (Season $season_num)\n"
  message+="📝 Nama: \`$filename\`\n"
  message+="💾 Size: \`$filesize\`\n"
  message+="⏰ Ditambahkan: <t:$(date +%s):R>"

  curl -sS -H "Content-Type: application/json" \
    -X POST \
    -d "{\"content\":\"$message\"}" \
    "$DISCORD_WEBHOOK" >>"$LOG_FILE" 2>&1
}

extract_anime_info() {
  local filename="$1"
  for pattern in "${!ANIME_MAPPING[@]}"; do
    if echo "$filename" | grep -qP "$pattern"; then
      IFS=':' read -r anime_key season_num <<<"${ANIME_MAPPING[$pattern]}"
      local anime_title anime_title=$(get_anime_title "$anime_key")

    # Cari nomor episode
    local ep_num ep_num=$(echo "$filename" \
      | grep -oP '(?:S\d{1,2}[-_. ]*)\K\d{1,4}' \
      | head -n1)

    # Kalau masih kosong, pakai regex lama
    if [ -z "$ep_num" ]; then
      ep_num=$(echo "$filename" \
        | grep -oP '[_\s-]\K\d{1,4}(?=\s*(?:_|\.|\[|\(|$))' \
        | head -n1)
    fi

    # Fallback: ambil angka pertama
    if [ -z "$ep_num" ]; then
    ep_num=$(echo "$filename" | grep -oP '\d{1,4}' | head -n1)
    fi

    # Apply special rules
    ep_num=$(apply_special_rules "$anime_key" "$ep_num")
    echo "$anime_key:$anime_title:$season_num:$ep_num"
    return 0
   fi
  done
  return 1
}
process_file() {
  local filepath="$1"
  local filename
  filename=$(basename "$filepath")
  local filesize
  filesize=$(du -h "$filepath" | cut -f1)

  local anime_info
  anime_info=$(extract_anime_info "$filename")
  if [ -z "$anime_info" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SKIPPED: Format tidak dikenali - $filename" >>"$LOG_FILE"
    return
  fi

  IFS=':' read -r anime_key anime_title season_num ep_num <<<"$anime_info"

  if [ -n "$ep_num" ]; then
    local new_name="${anime_title} S$(printf '%02d' "$((10#$season_num))")E$(printf '%02d' "$((10#$ep_num))").${filename##*.}"
  # old  local new_name="${anime_title} S$(printf '%02d' "$season_num")E$(printf '%02d' "$ep_num").${filename##*.}"
    local library_dir="${LIBRARY_DIRS[$anime_key]}"
    local new_path="${library_dir}/${new_name}"

    mkdir -p "$library_dir"

    if mv -v "$filepath" "$new_path" >>"$LOG_FILE" 2>&1; then
      chmod 664 "$new_path"
      echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $filename → $new_name (Season $season_num)" >>"$LOG_FILE"
      notify_discord "$anime_title" "$new_name" "$new_path" "$filesize" "$season_num"
    else
      echo "$(date '+%Y-%m-%d %H:%M:%S') - FAILED: Gagal memindahkan $filename" >>"$LOG_FILE"
    fi
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SKIPPED: Nomor episode tidak ditemukan - $filename" >>"$LOG_FILE"
  fi
}

check_watch_dir() {
  # Bisa diisi pengecekan ekstra kalau perlu
  :
}

# Scan awal
echo "Scan awal folder..."
find "$WATCH_DIR" -type f -iregex '.*\.\(mkv\|mp4\|avi\|mov\)$' | while IFS= read -r filepath; do
  check_watch_dir
  process_file "$filepath"
done

# Pantau file baru
echo "Memantau folder..."
inotifywait -m -r -e close_write,moved_to --format '%w%f' "$WATCH_DIR" | \
while IFS= read -r filepath; do
  check_watch_dir
  if [[ -f "$filepath" && "$filepath" =~ \.(mkv|mp4|avi|mov)$ ]]; then
    process_file "$filepath"
  fi
done
