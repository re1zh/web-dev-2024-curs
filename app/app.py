from flask import Flask, render_template

app = Flask(__name__)
application = app

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html', title='Об авторе')

@app.route('/auth')
def auth():
    return render_template('auth.html', title='Вход')

if __name__ == '__main__':
    app.run(debug=True)