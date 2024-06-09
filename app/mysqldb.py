import mysql.connector
from flask import g

class DBConnector:
    def __init__(self, app):
        self.app = app
        self.app.teardown_appcontext(self.disconnect)

    def get_config(self):
        return {
            'user': self.app.config["MYSQL_USER"],
            'password': self.app.config["MYSQL_PASSWORD"],
            'host': self.app.config["MYSQL_HOST"],
            'database': self.app.config["MYSQL_DATABASE"]
        }

    def connect(self):
        if 'db' not in g:
            g.db = mysql.connector.connect(**self.get_config())
        return g.db

    def disconnect(self, e=None):
        if 'db' in g:
            g.db.close()
        g.pop('db', None)
