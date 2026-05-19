import os
import logging
import threading
import sys
import time
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify
from myjdapi import Myjdapi
from myjdapi.exception import MYJDTokenInvalidException

app = Flask(__name__)

# ---- Logging setup ----
# Konfigurasi Path Log
LOG_FILE = os.getenv("LOG_FILE", "logs/api.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Format Log
log_format = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")

# Handler 1: Terminal (STDOUT) - Agar muncul di systemctl status
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_format)

# Handler 2: File (Rotating)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2)
file_handler.setFormatter(log_format)

# Terapkan ke Root Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

# =========================================================
# lazy loader for MyJDownloader client
# =========================================================

_myjd_client = None
_client_lock = threading.Lock()

def get_client():
    global _myjd_client

    with _client_lock:
        if _myjd_client:
            return _myjd_client

        email = os.getenv("JD_EMAIL")
        password = os.getenv("JD_PASSWORD")
        device = os.getenv("JD_DEVICE")

        if not email or not password or not device:
            raise RuntimeError("JD_EMAIL, JD_PASSWORD, JD_DEVICE env not set")

        _myjd_client = MyJDClient(email, password, device)
        return _myjd_client

# =========================================================
# MyJDownloader Auto-Reconnect Client
# =========================================================

class MyJDClient:
    def __init__(self, email, password, device_name):
        self.email = email
        self.password = password
        self.device_name = device_name
        self.lock = threading.Lock()
        self.jd = None
        self.device = None
        self.connect()

    def connect(self):
        with self.lock:
            logging.warning("Connecting to MyJDownloader...")
            self.jd = Myjdapi()
            self.jd.connect(self.email, self.password)
            self.jd.update_devices()

            device = self.jd.get_device(self.device_name)
            if not device:
                raise RuntimeError(f"Device '{self.device_name}' not found in MyJDownloader.")

            self.device = device
            logging.warning("MyJDownloader connected successfully.")

    def _move_package_to_downloadlist(self, pkg_uuid):
        """
        Pindahkan package dari Linkgrabber ke Downloadlist.
        Mencoba dua strategi:
          1. Query link_ids di dalam package, lalu move_to_downloadlist(link_ids, [pkg_uuid])
          2. Fallback: move_to_downloadlist([], [pkg_uuid])
        """
        # --- Strategi 1: ambil link_ids dari dalam package ---
        try:
            links_in_pkg = self.device.linkgrabber.query_links([{
                "packageUUIDs": [pkg_uuid],
                "uuid": True
            }])
            link_ids = [lnk.get("uuid") for lnk in links_in_pkg if lnk.get("uuid")]
            logging.info(f"Link IDs in package {pkg_uuid}: {link_ids}")

            self.device.linkgrabber.move_to_downloadlist(link_ids, [pkg_uuid])
            logging.info("Package moved to Downloadlist (strategy 1: with link_ids)")
            return True

        except Exception as e1:
            logging.warning(f"Strategy 1 failed: {e1} — trying fallback (empty link_ids)...")

        # --- Strategi 2: fallback link_ids kosong ---
        try:
            self.device.linkgrabber.move_to_downloadlist([], [pkg_uuid])
            logging.info("Package moved to Downloadlist (strategy 2: empty link_ids)")
            return True

        except Exception as e2:
            logging.error(f"Strategy 2 also failed: {e2}")
            return False

    def _wait_for_packages(self, max_retries=10, delay=2):
        """
        Tunggu sampai package muncul di Linkgrabber.
        Retry loop karena JDownloader butuh waktu untuk memproses link menjadi package.
        """
        for attempt in range(1, max_retries + 1):
            time.sleep(delay)

            # Strategi 1: coba query_packages()
            try:
                packages = self.device.linkgrabber.query_packages()
                if packages:
                    logging.info(f"Found {len(packages)} package(s) via query_packages() (attempt {attempt})")
                    return packages
                logging.debug(f"query_packages() returned empty (attempt {attempt})")
            except (AttributeError, Exception) as e:
                logging.debug(f"query_packages() failed (attempt {attempt}): {e}")

            # Strategi 2: coba query_links() dan extract unique package UUIDs
            try:
                links = self.device.linkgrabber.query_links()
                if links:
                    # Extract unique package UUIDs dari links
                    pkg_uuids = []
                    seen = set()
                    for lnk in links:
                        pkg_uuid = lnk.get("packageUUID") or lnk.get("packageUuid") or lnk.get("uuid")
                        if pkg_uuid and pkg_uuid not in seen:
                            seen.add(pkg_uuid)
                            pkg_uuids.append({"uuid": pkg_uuid, "name": lnk.get("name", "")})
                    if pkg_uuids:
                        logging.info(f"Found {len(pkg_uuids)} package(s) via query_links() (attempt {attempt})")
                        return pkg_uuids
                    logging.debug(f"query_links() returned {len(links)} links but no package UUIDs (attempt {attempt})")
            except (AttributeError, Exception) as e:
                logging.debug(f"query_links() failed (attempt {attempt}): {e}")

            logging.info(f"No packages found yet, retrying... ({attempt}/{max_retries})")

        logging.warning(f"No packages found after {max_retries} attempts")
        return []

    def add_links(self, links, package_name=None):
        try:
            with self.lock:
                # --- Tambahkan links ke Linkgrabber ---
                params = {
                    "links": "\n".join(links) if isinstance(links, list) else links,
                }
                if package_name:
                    params["packageName"] = package_name

                result = self.device.linkgrabber.add_links([params])
                logging.info(f"Links added to Linkgrabber: {result}")

                # --- Tunggu package muncul di Linkgrabber (retry loop) ---
                packages = self._wait_for_packages(max_retries=10, delay=2)

                if not packages:
                    logging.warning("No packages found in Linkgrabber after all retries — link may be stuck")
                    return result

                # Ambil package terbaru (yang pertama = yang baru ditambahkan)
                latest_pkg = packages[0]
                pkg_uuid = latest_pkg.get("uuid") or latest_pkg.get("id")

                if not pkg_uuid:
                    logging.warning("Package UUID not found, skipping move")
                    return result

                logging.info(f"Moving package UUID {pkg_uuid} to Downloadlist...")
                moved = self._move_package_to_downloadlist(pkg_uuid)

                if moved:
                    time.sleep(1)
                    # Coba start download dengan berbagai method
                    started = False
                    for method_name in ["force_download", "start_download", "resume_download"]:
                        try:
                            method = getattr(self.device.downloads, method_name, None)
                            if method:
                                method()
                                logging.info(f"Download started via downloads.{method_name}()")
                                started = True
                                break
                        except Exception:
                            pass

                    if not started:
                        # Fallback: coba downloadlist
                        try:
                            self.device.downloadlist.resume()
                            logging.info("Download resumed via downloadlist.resume()")
                        except Exception as e:
                            logging.warning(f"Could not start download automatically: {e}")
                            logging.info("Package already moved to Downloadlist — JDownloader will auto-process")
                else:
                    logging.warning("Failed to move package — link stuck in Linkgrabber")

                return result

        except (MYJDTokenInvalidException, AttributeError) as e:
            logging.error(f"Token invalid or device disconnected ({e}) → reconnecting...")
            self.connect()
            try:
                params = {
                    "links": "\n".join(links) if isinstance(links, list) else links,
                }
                if package_name:
                    params["packageName"] = package_name
                return self.device.linkgrabber.add_links([params])
            except Exception as retry_err:
                logging.error(f"Failed to add links after reconnect: {retry_err}", exc_info=True)
                raise

        except Exception as e:
            logging.error(f"Unexpected error in add_links: {e}", exc_info=True)
            raise

# =========================================================
# API Endpoint
# =========================================================

@app.route("/add", methods=["POST"])
def add_link():
    data = request.get_json(silent=True)
    if not data or "links" not in data:
        return jsonify({"success": False, "error": "Missing 'links' in JSON body"}), 400

    links = data["links"]
    package_name = data.get("packageName")
    try:
        client = get_client()
        client.add_links(links, package_name=package_name)
        return jsonify({"success": True})
    except Exception as e:
        logging.exception("Failed to add links to MyJDownloader")
        return jsonify({"success": False, "error": str(e)}), 500


# =========================================================
# Health Check
# =========================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})
