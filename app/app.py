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

        id_role = 0
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

            if id_role == 3:
                try:
                    query = "SELECT id FROM users WHERE login = %s and password = SHA2(%s, 256)"
                    cursor.execute(query, (login, password))
                    js_id = cursor.fetchone()
                    print(cursor.statement)
                    print(js_id.id)

                    query = (
                        "INSERT INTO job_seekers (id_user) VALUES "
                        "(%s)"
                    )
                    cursor.execute(query, [js_id.id])
                    print(cursor.statement)
                    flash('Запись добавлена в "Соискатели"', 'success')
                except connector.errors.DatabaseError as error:
                    flash(f'Произошла ошибка при создании записи: {error}','danger')
            return redirect(url_for('auth'))
        except connector.errors.DatabaseError as error:
            flash(f'Произошла ошибка при создании записи: {error}', 'danger')

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

    employer_data_check = False
    if employer_data is None:
        employer_data_check = True

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

                try:
                    if employer_data_check is True:
                        query = (
                            "INSERT INTO employers (id_user, company_name, description, location) VALUES "
                            "(%(id_user)s, %(company_name)s, %(description)s, %(location)s)"
                        )
                    else:
                        query = (f"UPDATE employers SET {field_assignments_emp} "
                                 "WHERE id_user = %(id_user)s")
                    cursor.execute(query, employer_data)
                    flash('Запись добавлена в "Работодатели"', 'success')
                except connector.errors.DatabaseError as error:
                    flash(f'Произошла ошибка вставке записи: {error}', 'danger')

                print(cursor.statement)

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


@app.route('/<int:user_id>/create_resume', methods=['POST', 'GET'])
@db_operation
def create_resume(cursor, user_id):
    if request.method == 'POST':
        query = ("SELECT id FROM job_seekers WHERE id_user = %s")
        cursor.execute(query, [user_id])
        id_js = cursor.fetchone()

        query = (
            "SELECT now() as date "
        )
        cursor.execute(query)
        created_at = cursor.fetchone()

        experience = request.form['experience']
        description = request.form['description']
        skills = request.form['skills']
        education = request.form['education']
        user_data = {
            'experience': experience,
            'description': description,
            'skills': skills,
            'education': education,
            'id_job_seeker': id_js.id,
            'date': created_at.date
        }

        try:
            query = (
                "INSERT INTO resume (id_job_seeker, experience, description, skills, education, date) VALUES "
                "(%(id_job_seeker)s, %(experience)s, %(description)s, %(skills)s, %(education)s, %(date)s)"
            )
            cursor.execute(query, user_data)
            print(cursor.statement)
            flash('Резюме успешно создано', 'success')
            return redirect(url_for('profile', user_id=user_id))
        except connector.errors.DatabaseError as error:
            flash(f'Произошла ошибка при создании записи: {error}', 'danger')
    return render_template('create_resume.html')


@app.route('/<int:user_id>/resume')
@db_operation
def resume(cursor, user_id):
    query = ("SELECT last_name, first_name, second_name FROM users WHERE id = %s ")
    cursor.execute(query, [user_id])
    user_data = cursor.fetchone()

    query = (
        "SELECT resume.* "
        "FROM resume "
        "WHERE id_job_seeker = ( "
        "select job_seekers.id"
        "   FROM job_seekers "
        "   LEFT JOIN std_2411_findaworkk.users "
        "   ON users.id = job_seekers.id_user "
        "    WHERE users.id = %s"
        ") "
    )
    cursor.execute(query, [user_id])
    resume_data = cursor.fetchall()

    return render_template('resume.html',user_data=user_data, resume_data=resume_data)


@app.route('/<int:user_id>/<int:resume_id>/edit_resume', methods=['POST', 'GET'])
@login_required
@db_operation
def edit_resume(cursor, user_id, resume_id):
    query = (
        "SELECT resume.* "
        "FROM resume "
        "WHERE id_job_seeker = ( "
        "   select job_seekers.id "
        "       FROM job_seekers "
        "       LEFT JOIN users "
        "       ON users.id = job_seekers.id_user "
        "       WHERE users.id = %s"
        ") AND resume.id = %s "
    )
    cursor.execute(query, (user_id, resume_id))
    resume_data = cursor.fetchone()

    if resume_data is None:
        flash('Резюме с такими данными нет в базе данных', 'danger')
        return redirect(url_for('profile', user_id=user_id))

    if request.method == 'POST':
        fields_user = ['experience', 'description', 'skills', 'education']

        resume_data = {field: request.form[field] or None for field in fields_user}
        resume_data['id'] = resume_id

        try:
            field_assignments = ', '.join([f"{field} = %({field})s" for field in fields_user])

            query = (f"UPDATE resume SET {field_assignments} "
                     "WHERE id = %(id)s")
            cursor.execute(query, resume_data)
            print(cursor.statement)
            flash('Данные резюме успешно изменены', 'success')
            return redirect(url_for('resume', user_id=user_id))
        except connector.errors.DatabaseError as error:
            flash(f'Произошла ошибка при изменении записи: {error}', 'danger')
    return render_template('edit_resume.html', resume_data=resume_data)


@app.route('/<int:user_id>/<int:resume_id>/delete_resume', methods=['POST', 'GET', 'DELETE'])
@login_required
@db_operation
def delete_resume(cursor, user_id, resume_id):
    try:
        query = ("DELETE FROM resume WHERE id = %s")
        cursor.execute(query, (resume_id,))
        flash('Резюме успешно удалено', 'success')
        return redirect(url_for('resume', user_id=user_id))
    except connector.errors.DatabaseError as error:
        flash(f'Произошла ошибка при удалении записи: {error}', 'danger')


@app.route('/<int:user_id>/create_vacancie', methods=['POST', 'GET'])
@db_operation
def create_vacancie(cursor, user_id):
    if request.method == 'POST':
        query = ("SELECT id FROM employers WHERE id_user = %s ")
        cursor.execute(query, [user_id])
        id_emp = cursor.fetchone()

        query = (
            "SELECT now() as date "
        )
        cursor.execute(query)
        created_at = cursor.fetchone()

        title = request.form['title']
        description = request.form['description']
        salary = request.form['salary']

        vacancie_data = {
            'title': title,
            'description': description,
            'salary': salary,
            'id_employer': id_emp.id,
            'date': created_at.date
        }

        try:
            query = (
                "INSERT INTO vacancy (id_employer, title, description, salary, date) VALUES "
                "(%(id_employer)s, %(title)s, %(description)s, %(salary)s, %(date)s)"
            )
            cursor.execute(query, vacancie_data)
            print(cursor.statement)

            flash('Вакансия успешно создана', 'success')
            return redirect(url_for('profile', user_id=user_id))
        except connector.errors.DatabaseError as error:
            flash(f'Произошла ошибка при создании записи: {error}', 'danger')
    return render_template('create_vacancie.html')


@app.route('/<int:user_id>/employer_vacancie_list')
@db_operation
def employer_vacancie_list(cursor, user_id):
    query = (
        "SELECT location FROM employers WHERE id_user = %s "
    )
    cursor.execute(query, [user_id])
    location_data = cursor.fetchone()

    query = (
        "SELECT vacancy.* "
        "FROM vacancy "
        "WHERE id_employer = ("
        "   select employers.id"
        "   FROM employers "
        "   LEFT JOIN users "
        "   ON users.id = employers.id_user"
        "   WHERE users.id = %s"
        ")"
    )
    cursor.execute(query, [user_id])
    vacancie_data = cursor.fetchall()

    return render_template('employer_vacancie_list.html', vacancie_data=vacancie_data, location_data=location_data)


@app.route('/<int:user_id>/<int:vacancie_id>/vacancie_view')
@db_operation
def vacancie_view(cursor, user_id, vacancie_id):
    query = (
        "SELECT location FROM employers WHERE id_user = %s "
    )
    cursor.execute(query, [user_id])
    location_data = cursor.fetchone()

    query = (
        "SELECT * "
        "FROM vacancy "
        "WHERE id = %s"
    )
    cursor.execute(query, [vacancie_id])
    vacancie_data = cursor.fetchone()

    return render_template('vacancie_view.html', vacancie_data=vacancie_data, location_data=location_data)


@app.route('/<int:user_id>/<int:vacancie_id>/edit_vacancie', methods=['POST', 'GET'])
@login_required
@db_operation
def edit_vacancie(cursor, user_id, vacancie_id):
    query = (
        "SELECT vacancy.* "
        "FROM vacancy "
        "WHERE id_employer = ( "
        "select employers.id"
        "   FROM employers "
        "   LEFT JOIN users "
        "   ON users.id = employers.id_user "
        "   WHERE users.id = %s"
        ") "
    )
    cursor.execute(query, [user_id])
    vacancie_data = cursor.fetchone()

    if vacancie_data is None:
        flash('Вакансии с такими данными нет в базе данных', 'danger')
        return redirect(url_for('profile', user_id=user_id))

    if request.method == 'POST':
        fields_user = ['title', 'description', 'salary']

        vacancie_data = {field: request.form[field] or None for field in fields_user}
        vacancie_data['id'] = vacancie_id

        try:
            field_assignments = ', '.join([f"{field} = %({field})s" for field in fields_user])

            query = (f"UPDATE vacancy SET {field_assignments} "
                     "WHERE id = %(id)s")
            cursor.execute(query, vacancie_data)
            print(cursor.statement)
            flash('Данные вакансии успешно изменены', 'success')
            return redirect(url_for('vacancie_view', user_id=user_id, vacancie_id=vacancie_id))
        except connector.errors.DatabaseError as error:
            flash(f'Произошла ошибка при изменении записи: {error}', 'danger')
    return render_template('edit_vacancie.html', vacancie_data=vacancie_data)


@app.route('/<int:user_id>/<int:vacancie_id>/delete_vacancie', methods=['POST', 'GET', 'DELETE'])
@login_required
@db_operation
def delete_vacancie(cursor, user_id, vacancie_id):
    try:
        query = ("DELETE FROM vacancy WHERE id = %s")
        cursor.execute(query, (vacancie_id,))
        flash('Вакансия успешно удалена', 'success')
        return redirect(url_for('employer_vacancie_list', user_id=user_id))
    except connector.errors.DatabaseError as error:
        flash(f'Произошла ошибка при удалении записи: {error}', 'danger')


@app.route('/vacancie_list')
@db_operation
def vacancie_list(cursor):
    query = (
        "SELECT vacancy.*, employers.location "
        "FROM vacancy "
        "LEFT JOIN employers "
        "ON vacancy.id_employer = employers.id"
    )
    cursor.execute(query)
    vacancie_data = cursor.fetchall()

    return render_template('vacancie_list.html', vacancie_data=vacancie_data)


if __name__ == '__main__':
    app.run(debug=True)