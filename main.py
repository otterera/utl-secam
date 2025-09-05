"""Application entrypoint: starts the service and Flask web app."""

from security_cam.config import Config  # App configuration
from security_cam.service import SecurityCamService  # Background capture service
from security_cam.web import create_app  # Flask app factory


def main() -> None:
    """Create the service and run the Flask development server."""
    service = SecurityCamService()  # Instantiate service
    service.start()  # Start background worker thread
    app = create_app(service)  # Build Flask app bound to the service
    # Use Flask’s built-in server; suitable for local/LAN use on the Pi
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)


if __name__ == "__main__":
    main()
