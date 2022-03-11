import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import argschema
from cell_labeling_app.backup_manager import BackupManager
from flask import Flask

from cell_labeling_app.database.database import db
from cell_labeling_app.endpoints.endpoints import api
from cell_labeling_app.endpoints.user_authentication import users
from cell_labeling_app.user_authentication.user_authentication import login


class _BackupSchema(argschema.ArgSchema):
    frequency = argschema.fields.Integer(
        default=60 * 5,
        description='Number of seconds to wait before creating a new backup'
    )


class AppSchema(argschema.ArgSchema):
    database_path = argschema.fields.InputFile(
        required=True,
        description='Database path',
    )
    ARTIFACT_DIR = argschema.fields.InputDir(
        required=True,
        description='Path to h5 files storing data required for the '
                    'app to run'
    )
    PREDICTIONS_DIR = argschema.fields.InputDir(
        required=True,
        description='Path to pre-classification predictions'
    )
    PORT = argschema.fields.Integer(
        default=5000,
        description='Port the app should run on'
    )
    FIELD_OF_VIEW_DIMENSIONS = argschema.fields.Tuple(
        (argschema.fields.Int, argschema.fields.Int),
        default=(512, 512),
        description='Field of view dimensions'
    )
    LOG_FILE = argschema.fields.OutputFile(
        default=None,
        allow_none=True,
        description='Path to where stdout/stderr logs should be written'
    )
    ACCESS_LOG_FILE = argschema.fields.OutputFile(
        default=None,
        allow_none=True,
        description='Path to where access logs should be written'
    )
    LABELERS_REQUIRED_PER_REGION = argschema.fields.Integer(
        default=3,
        description='Requires a certain number of labelers to label a region '
                    'until it is no longer shown to other labelers.'
    )
    debug = argschema.fields.Boolean(
        default=False,
        description='Whether to enable debug mode (more logging, '
                    'autoreload of server on code change)'
    )
    num_workers = argschema.fields.Integer(
        default=32,
        description='Number of workers to use for the webserver'
    )
    backup_params = argschema.fields.Nested(
        _BackupSchema,
        default={}
    )


class App(argschema.ArgSchemaParser):
    """The main driver for the app."""
    default_schema = AppSchema

    def create_flask_app(self, session_secret_key: str) -> Flask:
        """Creates a flask app
        :param session_secret_key: A session secret key for authentication
        :return: instantiated flask app

        """
        template_dir = (
                    Path(__file__).parent.parent.parent / 'client').resolve()
        static_dir = template_dir
        app = Flask(__name__, static_folder=static_dir,
                    template_folder=str(template_dir))
        app.config['SQLALCHEMY_DATABASE_URI'] = \
            f'sqlite:///{self.args["database_path"]}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SESSION_SECRET_KEY'] = session_secret_key
        app.register_blueprint(api)
        for k, v in self.args.items():
            app.config[k] = v
        db.init_app(app)
        app.register_blueprint(users)
        app.secret_key = app.config['SESSION_SECRET_KEY']

        login.init_app(app)
        self._create_backup_manager(app)

        return app

    def run_production_server(self):
        """Launches webserver running app"""
        gunicorn_cmd_args = [
            f'--bind=localhost:{self.args["PORT"]}',
            f'--workers={self.args["num_workers"]}',
            '--capture-output',
            '--name=cell_labeling_app',
            '--timeout=90'
        ]
        if self.args['ACCESS_LOG_FILE'] is not None:
            gunicorn_cmd_args.append(
                f'--access-logfile {self.args["ACCESS_LOG_FILE"]}')

        if self.args['LOG_FILE'] is not None:
            gunicorn_cmd_args.append(f'--log-file {self.args["LOG_FILE"]}')

        if self.args['debug']:
            gunicorn_cmd_args.append('--reload')

        os.environ['GUNICORN_CMD_ARGS'] = ' '.join(gunicorn_cmd_args)
        input_json_path = sys.argv[-1]
        session_secret_key = str(uuid.uuid4())
        cmd = ['gunicorn',
               f'src.server.cell_labeling_app.main:main('
               f'input_json_path="{input_json_path}", '
               f'session_secret_key="{session_secret_key}")']

        subprocess.run(cmd, stdout=sys.stdout,
                       stderr=sys.stderr,
                       env=os.environ)

    def _create_backup_manager(self, app):
        """Starts a backup manager running in the background in a new thread"""
        database_path = Path(self.args['database_path'])
        backup_manager = BackupManager(
            app=app,
            database_path=database_path,
            backup_dir=database_path.parent / 'backups',
            frequency=self.args['backup_params']['frequency']
        )
        t = threading.Thread(target=backup_manager.run)
        t.start()


def main(input_json_path: str, session_secret_key: str) -> Flask:
    with open(input_json_path) as f:
        input_data = json.load(f)
    app = App(input_data=input_data, args=[])
    app = app.create_flask_app(session_secret_key=session_secret_key)
    return app


if __name__ == '__main__':
    app = App()
    if app.args['debug']:
        app = app.create_flask_app(session_secret_key=str(uuid.uuid4()))
        app.run(debug=True, port=app.args['PORT'])
    else:
        app.run_production_server()
