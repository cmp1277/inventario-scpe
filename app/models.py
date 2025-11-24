from app import db
from datetime import datetime
from config import Config
from flask_login import UserMixin 
from werkzeug.security import generate_password_hash, check_password_hash 

class Usuario(UserMixin, db.Model):
    """Modelo para la autenticación de usuarios."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    rol = db.Column(db.Integer, default=2) 

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.rol == 1
        
    def __repr__(self):
        return f'<Usuario {self.username}>'

class Producto(db.Model):
    """Modelo de la tabla 'producto'."""
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    cantidad = db.Column(db.Float, default=0.0)
    precio = db.Column(db.Float, default=0.0)
    proveedor = db.Column(db.String(100))
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow)
    stock_minimo = db.Column(db.Float, default=Config.STOCK_MINIMO)
    subalmacen = db.Column(db.String(50), nullable=False)
    unidad = db.Column(db.String(50), nullable=False)
    diametro = db.Column(db.String(50))

    # Relaciones con cascada para evitar errores al eliminar
    salidas = db.relationship('Salida', backref='producto', lazy=True, cascade="all, delete-orphan")
    ingresos = db.relationship('Ingreso', backref='producto', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Producto {self.nombre}>'

    def necesita_alerta(self):
        return self.cantidad <= self.stock_minimo

    @property
    def total_value(self):
        return self.precio * self.cantidad


class Salida(db.Model):
    """Modelo para registrar salidas de productos."""
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad_salida = db.Column(db.Float, nullable=False)
    nombre_funcionario = db.Column(db.String(100), nullable=False)
    codigo_funcionario = db.Column(db.String(50), nullable=False)
    fecha_salida = db.Column(db.DateTime, default=datetime.utcnow)
    precio_en_bs = db.Column(db.Float, nullable=False)
    imagen_salida = db.Column(db.String(255), nullable=True)
    
    # NUEVO: Usuario del sistema que registró la salida
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario', backref='salidas_registradas')

    def __repr__(self):
        return f'<Salida {self.producto.nombre}>'


class Ingreso(db.Model):
    """Modelo para registrar ingresos/actualizaciones de productos."""
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad_agregada = db.Column(db.Float, nullable=False)
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow)
    imagen_ingreso = db.Column(db.String(255), nullable=True)
    
    # NUEVO: Usuario del sistema que registró el ingreso
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario', backref='ingresos_registrados')

    def __repr__(self):
        return f'<Ingreso {self.producto.nombre}>'