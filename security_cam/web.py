"""Flask web application for the security camera dashboard and API."""

import os  # For file path operations
import time  # For timestamps and simple cache control

import cv2  # For JPEG encoding
import flask  # Web server and templating

from .config import Config  # App configuration
from .service import SecurityCamService  # Service providing frames and state


def create_app(service: SecurityCamService) -> flask.Flask:
    """Create and configure the Flask application.

    Args:
      service: Running `SecurityCamService` to fetch frames and state from.

    Returns:
      A Flask app instance with routes for dashboard, images, and API.
    """
    app = flask.Flask(__name__)

    @app.route("/")
    def index():
        """Render the main dashboard page."""
        st = service.get_status()
        alert_active = (time.time() - st.last_detection_ts) <= Config.ALERT_COOLDOWN_SEC
        latest_files = service.list_latest_images(Config.GALLERY_LATEST_COUNT)

        # Minimal inline HTML/CSS for a simple dashboard
        html = flask.render_template_string(
            _INDEX_TEMPLATE,
            alert_active=alert_active,
            saved_count=st.saved_images_count,
            total_frames=st.total_frames,
            armed=st.armed,
            person_count=getattr(st, "person_count", 0),
            face_count=getattr(st, "face_count", 0),
            exposure_state=st.exposure_state,
            ev_bias=getattr(st, "ev_bias", 0.0),
            gain=getattr(st, "gain", 0.0),
            shutter_ms=int(getattr(st, "shutter_us", 0) / 1000),
            latest_files=[os.path.basename(p) for p in latest_files],
            ts=int(time.time()),
        )
        return html

    @app.route("/latest.jpg")
    def latest_jpg():
        """Serve the most recent frame as a JPEG image."""
        frame = service.get_latest_frame()
        if frame is None:
            return ("No frame yet", 503)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return ("Encode error", 500)
        return flask.Response(buf.tobytes(), mimetype="image/jpeg")

    @app.route("/captures/<path:filename>")
    def captures(filename: str):
        """Serve a saved capture by filename."""
        path = os.path.join(Config.SAVE_DIR, filename)
        if not os.path.isfile(path):
            return ("Not found", 404)
        return flask.send_file(path, mimetype="image/jpeg")

    @app.route("/api/state")
    def api_state():
        """Return the current service state as JSON."""
        st = service.get_status()
        return {
            "detecting": st.detecting,
            "last_detection_ts": st.last_detection_ts,
            "saved_images_count": st.saved_images_count,
            "total_frames": st.total_frames,
            "armed": st.armed,
            "exposure_state": st.exposure_state,
            "exposure_mean": st.exposure_mean,
            "exposure_low_clip": st.exposure_low_clip,
            "exposure_high_clip": st.exposure_high_clip,
            "detect_stride": st.detect_stride,
            "hit_threshold": st.hit_threshold,
            "person_count": getattr(st, "person_count", 0),
            "face_count": getattr(st, "face_count", 0),
            "kinds": getattr(st, "last_kinds", []),
            "ev_bias": getattr(st, "ev_bias", 0.0),
            "gain": getattr(st, "gain", 0.0),
            "shutter_us": getattr(st, "shutter_us", 0),
        }

    @app.route("/stream.mjpg")
    def stream_mjpg():
        """Provide a multipart/x-mixed-replace MJPEG live stream."""
        def gen():
            boundary = b"--frame"
            while True:
                frame = service.get_latest_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if not ok:
                    continue
                yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"

        return flask.Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


_INDEX_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Raspberry Pi Security Cam</title>
  <style>
    body { font-family: system-ui, Arial, sans-serif; margin: 0; background: #111; color: #eee; }
    header { padding: 12px 16px; background: #222; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .alert { padding: 8px 12px; border-radius: 6px; font-weight: bold; }
    .alert.on { background: #b00020; color: #fff; }
    .alert.off { background: #2a2a2a; color: #aaa; }
    .arm { padding: 6px 10px; border-radius: 6px; font-weight: 600; font-size: 12px; }
    .arm.on { background: #144d14; color: #bff5bf; }
    .arm.off { background: #3a3a3a; color: #bbb; }
    .pill { padding: 4px 8px; border-radius: 999px; font-weight: 600; font-size: 11px; }
    .pill.person { background: #441111; color: #ff9a9a; border: 1px solid #b00020; }
    .pill.face { background: #0f2b3a; color: #9eeaff; border: 1px solid #1aa3d9; }
    .pill.cam { background: #2a2a2a; color: #bbb; border: 1px solid #444; }
    .exp { padding: 6px 10px; border-radius: 6px; font-weight: 600; font-size: 12px; }
    .exp.normal { background: #2a2a2a; color: #bbb; }
    .exp.over { background: #b00020; color: #fff; }
    .exp.under { background: #0b3d91; color: #dbe9ff; }
    main { padding: 16px; }
    .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
    .card { background: #1b1b1b; padding: 8px; border-radius: 8px; }
    img { width: 100%; height: auto; border-radius: 6px; display: block; }
    .live { max-width: 640px; margin-bottom: 16px; }
    .meta { color: #9aa; font-size: 12px; }
  </style>
  <meta http-equiv="refresh" content="5">
  <!-- lightweight auto-refresh every 5s for status and gallery -->
  </head>
  <body>
    <header>
      <div style="display:flex; align-items:center; gap:8px">
        <strong>Security Cam</strong>
        {% if armed %}
          <span class="arm on">Armed</span>
        {% else %}
          <span class="arm off">Disarmed</span>
        {% endif %}
        {% if exposure_state == 'over' %}
          <span class="exp over">Exposure: Over</span>
        {% elif exposure_state == 'under' %}
          <span class="exp under">Exposure: Under</span>
        {% elif exposure_state == 'normal' %}
          <span class="exp normal">Exposure: Normal</span>
        {% endif %}
        {% if person_count %}
          <span class="pill person">person × {{person_count}}</span>
        {% endif %}
        {% if face_count %}
          <span class="pill face">face × {{face_count}}</span>
        {% endif %}
        <span class="pill cam">EV {{ '%.2f' % ev_bias }}</span>
        <span class="pill cam">Gain {{ '%.2f' % gain }}</span>
        <span class="pill cam">Shutter {{ shutter_ms }} ms</span>
      </div>
      {% if alert_active %}
        <div class="alert on">HUMAN DETECTED</div>
      {% else %}
        <div class="alert off">Idle</div>
      {% endif %}
    </header>
    <main>
      <div class="live card">
        <img src="/latest.jpg?ts={{ts}}" alt="Latest frame" />
        <div class="meta">Saved: {{saved_count}} &nbsp; | &nbsp; Frames: {{total_frames}}</div>
      </div>
      <h3>Recent Captures</h3>
      <div class="grid">
        {% for f in latest_files %}
          <div class="card"><img src="/captures/{{f}}" alt="{{f}}" /></div>
        {% else %}
          <div class="meta">No captures yet.</div>
        {% endfor %}
      </div>
    </main>
  </body>
</html>
"""
