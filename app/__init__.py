import os
from dotenv import load_dotenv
from flask import Flask
from .models import db
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app():
    load_dotenv()
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.secret_key = os.environ.get("SECRET_KEY")
    # db_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
    db_uri = os.environ.get("RENDER_SQLALCHEMY_DATABASE_URI")
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # Register blueprints, extensions, etc.
    # from .views import main as main_blueprint
    # app.register_blueprint(main_blueprint)
    

    return app