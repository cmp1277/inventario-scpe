# config.py

class Config:
    """Clase base de configuración de la aplicación."""
    # Configuración de la base de datos SQLite
    SQLALCHEMY_DATABASE_URI = 'sqlite:///inventario.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Clave Secreta (Necesaria para Flask-WTF y Flask-Login)
    SECRET_KEY = 'clave_secreta_muy_segura_y_larga' 
    
    # Stock Mínimo para Alertas
    STOCK_MINIMO = 10