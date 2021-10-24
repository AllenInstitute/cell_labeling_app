from flask_login import LoginManager

from src.server.database.schemas import User

login = LoginManager()


@login.user_loader
def load_user(id):
    return User.query.get(id)
