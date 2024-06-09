import datetime
import re
from functools import wraps

import mysql.connector as connector
from flask import Flask, render_template, session, request, redirect, url_for, flash, current_app
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

from mysqldb import DBConnector

from users_policy import UsersPolicy

app = Flask(__name__)
application = app
app.config.from_pyfile('config.py')

db_connector = DBConnector(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth'
login_manager.login_message_category = 'warning'

class User(UserMixin):
    def __init__(self, user_id, user_login, user_role):
        self.id = user_id
        self.user_login = user_login
        self.id_role = user_role

    def is_admin(self):
        return self.id_role == current_app.config['ADMIN_ID_ROLE']

    def is_employer(self):
        return self.id_role == current_app.config['EMPLOYER_ID_ROLE']

    def is_job_seeker(self):
        return self.id_role == current_app.config['JOB_SEEKER_ID_ROLE']

    def can(self, action, user=None):
        policy = UsersPolicy(user)
        return getattr(policy, action, lambda: False)()

def db_operation(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time, end_time = None, None
        connection = db_connector.connect()
        try:
            start_time = datetime.datetime.now()
            with connection.cursor(named_tuple=True, buffered=True) as cursor:
                result = func(cursor, *args, **kwargs)
                connection.commit()
        except Exception as e:
            connection.rollback()
            raise e
        finally:
            end_time = datetime.datetime.now()
            print(f"Duration {func}: {end_time - start_time}")
            # connection.close()
        return result

    return wrapper


def check_for_privelege(action):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            user = None
            if 'user_id' in kwargs.keys():
                with db_connector.connect().cursor(named_tuple=True) as cursor:
                    cursor.execute("SELECT * FROM users WHERE id = %s;", (kwargs.get('user_id'),))
                    user = cursor.fetchone()
            if not (current_user.is_authenticated and current_user.can(action, user)):
                flash('Недостаточно прав для доступа к этой странице', 'warning')
                return redirect(url_for('index'))
            return function(*args, **kwargs)
        return wrapper
    return decorator


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html', title='О проекте')


@login_manager.user_loader
def load_user(user_id):
    with db_connector.connect().cursor(named_tuple=True) as cursor:
        cursor.execute("SELECT id, login, id_role FROM users WHERE id = %s;", (user_id,))
        user = cursor.fetchone()
    if user is not None:
        return User(user.id, user.login, user.id_role)
    return None

@app.route('/auth', methods=['POST', 'GET'])
@db_operation
def auth(cursor):
    error = ''
    if request.method == 'POST':
        login = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me', None) == 'on'
        cursor.execute("SELECT id, login, id_role FROM users WHERE login = %s AND password = SHA2(%s, 256)",
                       (login, password))
        user = cursor.fetchone()

        if user is not None:
            flash('Авторизация прошла успешно', 'success')
            login_user(User(user.id, user.login, user.id_role), remember=remember_me)
            return redirect(url_for('index'))
        flash('Неправильный логин или пароль', 'danger')
    return render_template('auth.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/create_profile', methods=['POST', 'GET'])
@db_operation
def create_profile(cursor):
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        lastname = request.form['lastname']
        name = request.form['name']
        secondname = request.form['secondname']
        role = request.form['role']

        if role == 'Работодатель':
            id_role = 2
        elif role == 'Соискатель':
            id_role = 3
        else:
            flash('Неправильно введена роль пользователя', 'danger')

        user_data = {
            'login': login,
            'password': password,
            'lastname': lastname,
            'name': name,
            'secondname': secondname,
            'id_role': id_role
        }

        try:
            query = (
                "INSERT INTO users (login, first_name, second_name, last_name, password, id_role) VALUES "
                "(%(login)s, %(name)s, %(secondname)s, %(lastname)s, SHA2(%(password)s, 256), %(id_role)s)"
            )
            cursor.execute(query, user_data)
            print(cursor.statement)
            flash('Учетная запись успешно создана', 'success')
            return redirect(url_for('auth'))
        except connector.errors.DatabaseError:
            flash('Произошла ошибка при создании записи. Проверьте, что все необходимые поля заполнены', 'danger')

    return render_template('create_profile.html')


@app.route('/<int:user_id>/profile')
def profile(user_id):
    user_data = {}
    employer_data = {}
    job_seeker_data = {}
    with db_connector.connect().cursor(named_tuple=True, buffered=True) as cursor:
        query = ("SELECT * FROM users WHERE id = %s")
        cursor.execute(query, [user_id])
        user_data = cursor.fetchone()
        if user_data is None:
            flash('Пользователя нет в базе данных', 'danger')
            return redirect(url_for('profile', user_id=user_id))

        query = "SELECT name FROM roles WHERE id = %s"
        cursor.execute(query, [user_data.id_role])
        user_role = cursor.fetchone()

        query = "SELECT company_name, description, location FROM employers WHERE id_user = %s"
        cursor.execute(query, [user_id])
        employer_data = cursor.fetchone()

        return render_template(
            'profile.html',
            user_data=user_data, user_role=user_role.name,
            employer_data=employer_data
        )


@app.route('/<int:user_id>/edit_profile', methods=['POST', 'GET'])
@login_required
@db_operation
def edit_profile(cursor, user_id):
    query = ("SELECT first_name, second_name, last_name, id_role "
             "FROM users WHERE id = %s")
    cursor.execute(query, [user_id])
    user_data = cursor.fetchone()

    query = ("SELECT id_user, company_name, description, location "
             "FROM employers WHERE id_user = %s")
    cursor.execute(query, [user_id])
    employer_data = cursor.fetchone()

    print(employer_data)

    if user_data is None:
        flash('Пользователя нет в базе данных', 'danger')
        return redirect(url_for('profile', user_id=user_id))

    if request.method == 'POST':
        if user_data.id_role == 1 or user_data.id_role == 2:
            fields_user = ['first_name', 'second_name', 'last_name']
            fields_employer = ['company_name', 'description', 'location']

            user_data = {field: request.form[field] or None for field in fields_user}
            user_data['id'] = user_id

            employer_data = {field: request.form[field] or None for field in fields_employer}
            employer_data['id_user'] = user_id

            try:
                field_assignments = ', '.join([f"{field} = %({field})s" for field in fields_user])
                field_assignments_emp = ', '.join([f"{field} = %({field})s" for field in fields_employer])

                query = (f"UPDATE users SET {field_assignments} "
                         "WHERE id = %(id)s")
                cursor.execute(query, user_data)

                if employer_data is None:
                    query = (
                        "INSERT INTO employers (id_user, {fields assignments_emp}) VALUES "
                        "(%(id_user)s, %(company_name)s, %(description)s, %(location)s)"
                    )
                else:
                    query = (f"UPDATE employers SET {field_assignments_emp} "
                             "WHERE id_user = %(id_user)s")
                cursor.execute(query, employer_data)

                flash('Учетная запись успешно изменена', 'success')
                return redirect(url_for('profile', user_id=user_id))
            except connector.errors.DatabaseError as error:
                flash(f'Произошла ошибка при изменении записи: {error}', 'danger')
        elif user_data.id_role == 3:
            fields_user = ['first_name', 'second_name', 'last_name']

            user_data = {field: request.form[field] or None for field in fields_user}
            user_data['id'] = user_id
            try:
                field_assignments = ', '.join([f"{field} = %({field})s" for field in fields_user])

                query = (f"UPDATE users SET {field_assignments} "
                         "WHERE id = %(id)s")
                cursor.execute(query, user_data)

                flash('Учетная запись успешно изменена', 'success')
                return redirect(url_for('profile', user_id=user_id))
            except connector.errors.DatabaseError as error:
                flash(f'Произошла ошибка при изменении записи: {error}', 'danger')
    return render_template('edit_profile.html', user_data=user_data, employer_data=employer_data)


if __name__ == '__main__':
    app.run(debug=True)