from flask import Blueprint, request, redirect, url_for
from flask_login import login_user, current_user

from src.server.database.database import db
from src.server.database.schemas import User

users = Blueprint(name='users', import_name=__name__, url_prefix='/users')


@users.route('/getCurrentUser')
def get_current_user():
    return {
        'user_id': current_user.get_id()
    }


@users.route('/loadUsers')
def load_users():
    users = db.session.query(User.id).all()
    users = [user.id for user in users]
    return {
        'users': users
    }


@users.route('/login', methods=['POST'])
def login():
    request_data = request.get_json(force=True)

    user = db.session.query(User).filter_by(id=request_data[
        'user_id']).first()
    login_user(user)

    return 'success'
