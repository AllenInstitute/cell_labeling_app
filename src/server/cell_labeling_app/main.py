import logging
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
        required=True,
        description='Path to where logs should be written'
    )
    LABELS_PER_REGION_LIMIT = argschema.fields.Integer(
        default=3,
        allow_none=True,
        description='Limits the number of labelers who need to label a region '
                    'to mark it "complete". Once it is "complete" it is not '
                    'shown to other labelers. If None, a region will be shown '
                    'to all labelers regardless of the number of times it has '
                    'been labeled. '
    )
    debug = argschema.fields.Boolean(
        default=False,
        description='Whether to enable debug mode (more logging, '
                    'autoreload of server on code change)'
    )
    num_threads = argschema.fields.Integer(
        default=16,
        description='Number of threads to use for the webserver'
    )
    backup_params = argschema.fields.Nested(
        _BackupSchema,
        default={}
    )


class App(argschema.ArgSchemaParser):
    default_schema = AppSchema

    def run(self):
        app = self._create_app()
        port = self.args['PORT']

        if self.args['debug']:
            app.run(debug=True, port=port)
        else:
            from waitress import serve
            serve(app, port=port, threads=self.args['num_threads'])

    def _create_app(self):
        template_dir = (
                    Path(__file__).parent.parent.parent / 'client').resolve()
        static_dir = template_dir
        app = Flask(__name__, static_folder=static_dir,
                    template_folder=str(template_dir))
        app.config['SQLALCHEMY_DATABASE_URI'] = \
            f'sqlite:///{self.args["database_path"]}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SESSION_SECRET_KEY'] = str(uuid.uuid4())
        app.register_blueprint(api)
        for k, v in self.args.items():
            app.config[k] = v
        db.init_app(app)
        app.register_blueprint(users)
        app.secret_key = app.config['SESSION_SECRET_KEY']

        log_level = logging.DEBUG if self.args['debug'] else logging.INFO
        logging.basicConfig(
            filename=app.config['LOG_FILE'],
            level=log_level,
            format='%(asctime)s %(levelname)-8s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')

        login.init_app(app)
        self._create_backup_manager(app)

        return app

    def _create_backup_manager(self, app):
        database_path = Path(self.args['database_path'])
        backup_manager = BackupManager(
            app=app,
            database_path=database_path,
            backup_dir=database_path.parent / 'backups',
            frequency=self.args['backup_params']['frequency']
        )
        t = threading.Thread(target=backup_manager.run)
        t.start()


if __name__ == '__main__':
    app = App()
    app.run()
