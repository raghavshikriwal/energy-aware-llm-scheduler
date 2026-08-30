import os

from flask import Flask, render_template

from extensions import limiter
from models.exceptions import register_error_handlers
from routes.api import api
from routes.live_api import live_api

app = Flask(__name__)
app.register_blueprint(api)
app.register_blueprint(live_api)
register_error_handlers(app)
limiter.init_app(app)


@app.route('/')
def home():
    return render_template('dashboard.html')


@app.route('/live')
def live():
    return render_template('live.html')


if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode)