import logging
from pathlib import Path

from flask import Flask

from src.server.database.database import db
from src.server.endpoints.endpoints import api
from src.server.endpoints.user_authentication import users
from src.server.user_authentication.user_authentication import login


def create_app(config_file: Path, port=5000):
    if not config_file.exists():
        raise ValueError('Config file does not exist')
    if not config_file.suffix == '.py':
        raise ValueError('Config file must be a python module ending in '
                           '".py"')

    template_dir = (Path(__file__).parent.parent / 'client').resolve()
    static_dir = template_dir
    app = Flask(__name__, static_folder=static_dir,
                          template_folder=str(template_dir))
    app.register_blueprint(api)
    app.config.from_pyfile(filename=str(config_file))
    app.config['PORT'] = port
    db.init_app(app)
    app.register_blueprint(api)
    app.register_blueprint(users)
    app.secret_key = app.config['SESSION_SECRET_KEY']
    login.init_app(app)
    return app


def setup_database(app: Flask):
    with app.app_context():
        db.create_all()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', help='Path to config file',
                        required=True)
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable automatic reloading when server-side code changes; '
             'enable debug level logging')
    parser.add_argument('--log_file', help='Path to log file')
    parser.add_argument('--port', default=5000, help='Port to run app')
    args = parser.parse_args()

    config_file = Path(args.config_file)
    port = int(args.port)

    app = create_app(config_file=config_file, port=port)
    if not Path(app.config['SQLALCHEMY_DATABASE_URI']
                .replace('sqlite:///', '')).is_file():
        setup_database(app=app)

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(filename=args.log_file, level=log_level)
    app.run(debug=args.debug, port=port)
