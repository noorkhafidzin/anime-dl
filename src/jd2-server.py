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

JD_EMAIL = os.getenv("JD_EMAIL")
JD_PASSWORD = os.getenv("JD_PASSWORD")
JD_DEVICE = os.getenv("JD_DEVICE")

if not JD_EMAIL or not JD_PASSWORD or not JD_DEVICE:
    raise RuntimeError("Environment variable JD_EMAIL, JD_PASSWORD, or JD_DEVICE is not set.")


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

    def add_links(self, links):
        try:
            return self.jd.linkgrabber.add_links(
                self.device,
                links,
                autostart=True
            )
        except MYJDTokenInvalidException:
            logging.error("MYJD TOKEN INVALID → reconnecting...")
            self.connect()
            return self.jd.linkgrabber.add_links(
                self.device,
                links,
                autostart=True
            )


# Global client instance
myjd_client = MyJDClient(JD_EMAIL, JD_PASSWORD, JD_DEVICE)


# =========================================================
# API Endpoint
# =========================================================

@app.route("/add", methods=["POST"])
def add_link():
    data = request.get_json(silent=True)
    if not data or "links" not in data:
        return jsonify({"success": False, "error": "Missing 'links' in JSON body"}), 400

    try:
        myjd_client.add_links(data["links"])
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
