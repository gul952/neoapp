"""
Run this ONCE to create the database tables and a first admin account.

    python init_db.py

Change the default admin password immediately after first login.
"""
from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username="admin").first():
        admin = User(full_name="Study Administrator", username="admin", role="admin")
        admin.set_password("changeme123")
        db.session.add(admin)
        db.session.commit()
        print("Database created and default admin account added:")
        print("  username: admin")
        print("  password: changeme123   <-- change this after first login")
    else:
        print("Database already set up - admin account already exists.")
