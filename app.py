from flask import Flask, render_template, redirect, url_for
from flask_login import login_required, current_user

from config import Config
from models import db, User
from extensions import login_manager, csrf, limiter


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from auth import auth_bp
    from admin import admin_bp
    from consent import consent_bp
    from assessment import assessment_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(consent_bp)
    app.register_blueprint(assessment_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    return app


app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0" makes this reachable from other devices on the same
    # WiFi network (phones, tablets) - not just the machine it's running on.
    app.run(host="0.0.0.0", port=5000, debug=True)
