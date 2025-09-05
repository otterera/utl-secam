from security_cam.config import Config
from security_cam.service import SecurityCamService
from security_cam.web import create_app


def main():
    service = SecurityCamService()
    service.start()
    app = create_app(service)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)


if __name__ == "__main__":
    main()

