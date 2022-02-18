from flask_login import LoginManager

from cell_labeling_app.database.schemas import User

login = LoginManager()


@login.user_loader
def load_user(id):
    return User.query.get(id)
