from pathlib import Path

from flask import Flask

from src.server.config.config import CELL_LABELING_APP_DB
from src.server.database.database import db
from src.server.endpoints.endpoints import api
from src.server.database.populate_db import populate_users, \
    populate_labeling_job


def create_app():
    template_dir = (Path(__file__).parent.parent / 'client').resolve()
    static_dir = template_dir
    app = Flask(__name__, static_folder=static_dir,
                          template_folder=str(template_dir))
    app.register_blueprint(api)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{CELL_LABELING_APP_DB}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(api)
    return app


def setup_database(app: Flask):
    with app.app_context():
        db.create_all()
        populate_users(db)
        populate_labeling_job(db)


if __name__ == '__main__':
    app = create_app()
    if not Path(CELL_LABELING_APP_DB).is_file():
        setup_database(app=app)
    app.run(debug=False)
