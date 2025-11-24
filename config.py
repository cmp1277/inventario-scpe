import os

# Obtiene la ruta absoluta de la carpeta donde está este archivo config.py
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Clase base de configuración de la aplicación."""
    
    # Clave Secreta: Intenta leerla del sistema (más seguro), si no existe usa la por defecto
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave_secreta_muy_segura_y_larga_produccion'

    # Configuración de la Base de Datos
    # Usamos os.path.join para construir la ruta completa y evitar errores en Linux
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'inventario.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuración personalizada
    STOCK_MINIMO = 10