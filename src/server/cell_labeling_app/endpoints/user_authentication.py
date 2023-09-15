from flask import Blueprint, request, render_template, \
    current_app
from flask_login import login_user, current_user

from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import User

users = Blueprint(name='users', import_name=__name__, url_prefix='/users')


@users.route('/register', methods=['POST'])
def register():
    request_data = request.get_json(force=True)
    user = db.session.query(User).filter_by(id=request_data[
        'email']).first()
    if user is not None:
        return {
            'msg': 'That email address is already registered.'
        }, 400
    else:
        # register
        user = User(id=request_data['email'])
        db.session.add(user)
        db.session.commit()

        return 'success'


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
        'email']).first()
    if user is None:
        return 'failure', 400
    login_user(user)

    return 'success'
