# app/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# Inicialización de extensiones fuera de la función de fábrica
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_class=Config):
    """Función de fábrica para crear la aplicación Flask."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar las extensiones con la aplicación
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configuración de Flask-Login
    login_manager.login_view = 'main.login' 
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'


    # Importar y registrar rutas y modelos
    from app import routes, models
    app.register_blueprint(routes.bp) 

    # Función que Flask-Login usa para recargar el objeto de usuario desde la sesión
    @login_manager.user_loader
    def load_user(user_id):
        # Importación local para evitar errores circulares en la inicialización
        from app.models import Usuario
        return Usuario.query.get(int(user_id)) 

    # Inicializar la base de datos (crea las tablas si no existen)
    with app.app_context():
        db.create_all() 
    
    return app