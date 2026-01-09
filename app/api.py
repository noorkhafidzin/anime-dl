import os
import logging
import threading
from flask import Flask, request, jsonify
from myjdapi import Myjdapi
from myjdapi.exception import MYJDTokenInvalidException

app = Flask(__name__)

# ---- Logging setup ----
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
)

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

    def add_links(self, links, package_name=None):
        try:
            # Jika package_name tidak dikirim, JDownloader akan otomatis menentukan nama package
            params = {
                "autostart": True,
                "links": "\n".join(links) if isinstance(links, list) else links,
            }
            
            if package_name:
                params["packageName"] = package_name

            return self.device.linkgrabber.add_links([params])

        except (MYJDTokenInvalidException, AttributeError):
            logging.error("Token invalid or device disconnected → reconnecting...")
            self.connect()
            # Ulangi proses setelah reconnect
            return self.device.linkgrabber.add_links([params])

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
