import logging
from pathlib import Path

from flask import Flask

from cell_labeling_app.database.database import db
from cell_labeling_app.endpoints.endpoints import api
from cell_labeling_app.endpoints.user_authentication import users
from cell_labeling_app.user_authentication.user_authentication import login


def create_app(config_file: Path, debug=False):
    if not config_file.exists():
        raise ValueError('Config file does not exist')
    if not config_file.suffix == '.py':
        raise ValueError('Config file must be a python module ending in '
                           '".py"')

    template_dir = (Path(__file__).parent.parent.parent / 'client').resolve()
    static_dir = template_dir
    app = Flask(__name__, static_folder=static_dir,
                          template_folder=str(template_dir))
    app.register_blueprint(api)
    app.config.from_pyfile(filename=str(config_file))
    db.init_app(app)
    app.register_blueprint(users)
    app.secret_key = app.config['SESSION_SECRET_KEY']

    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(filename=app.config['LOG_FILE'], level=log_level)

    login.init_app(app)
    return app


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', help='Path to config file',
                        required=True)
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable automatic reloading when server-side code changes; '
             'enable debug level logging')
    parser.add_argument('--threads', default=16, help='Number of threads for '
                                                      'the web server',
                        type=int)
    args = parser.parse_args()

    config_file = Path(args.config_file)

    app = create_app(config_file=config_file, debug=args.debug)
    port = app.config['PORT']

    if args.debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        serve(app, port=port, threads=args.threads)
