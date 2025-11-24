from app import create_app, db
from app.models import Usuario

app = create_app()

with app.app_context():
    admin = Usuario.query.filter_by(username='admin').first()
    if admin:
        admin.set_password('Mateo230115*')
        db.session.commit()
        print("Admin password updated successfully to 'Mateo230115*'.")
    else:
        print("Admin user not found.")
