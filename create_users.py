from app import create_app, db
from app.models import Usuario

app = create_app()

with app.app_context():
    # Create admin user
    admin = Usuario(username='admin', email='admin@example.com', rol=1)
    admin.set_password('admin123')
    db.session.add(admin)

    # Create employee user
    employee = Usuario(username='empleado', email='empleado@example.com', rol=2)
    employee.set_password('empleado123')
    db.session.add(employee)

    db.session.commit()
    print("Users created successfully:")
    print("Admin: admin / admin123")
    print("Employee: empleado / empleado123")
