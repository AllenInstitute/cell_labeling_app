from pathlib import Path

from flask import Flask

from src.server.database.database import db
from src.server.endpoints.endpoints import api
from src.server.database.populate_db import populate_users, \
    populate_labeling_job
from src.server.endpoints.user_authentication import users
from src.server.user_authentication.user_authentication import login


def create_app(config_file: Path):
    template_dir = (Path(__file__).parent.parent / 'client').resolve()
    static_dir = template_dir
    app = Flask(__name__, static_folder=static_dir,
                          template_folder=str(template_dir))
    app.register_blueprint(api)
    app.config.from_pyfile(filename=str(config_file))
    db.init_app(app)
    app.register_blueprint(api)
    app.register_blueprint(users)
    app.secret_key = app.config['SESSION_SECRET_KEY']
    login.init_app(app)
    return app


def setup_database(app: Flask):
    with app.app_context():
        db.create_all()
        populate_labeling_job(db)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', help='Path to config file',
                        required=True)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    config_file = Path(args.config_file)
    if not config_file.exists():
        raise RuntimeError('Config file does not exist')
    if not config_file.suffix == '.py':
        raise RuntimeError('Config file must be a python module ending in '
                           '".py"')
    app = create_app(config_file=config_file)
    if not Path(app.config['SQLALCHEMY_DATABASE_URI']
                .replace('sqlite:///', '')).is_file():
        setup_database(app=app)
    app.run(debug=args.debug)
