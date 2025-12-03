from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FloatField, SelectField, FileField, EmailField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange, Optional, Length
from app.models import Usuario, Producto

# --- FORMULARIO DE LOGIN ---
class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')

# --- FORMULARIO DE REGISTRO (PÚBLICO) ---
class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=64)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Repetir Contraseña', validators=[DataRequired(), EqualTo('password')])
    rol = SelectField('Rol', choices=[(2, 'Empleado'), (1, 'Administrador')], coerce=int, validators=[Optional()])
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = Usuario.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Por favor use un nombre de usuario diferente.')

    def validate_email(self, email):
        user = Usuario.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Por favor use un correo electrónico diferente.')

# --- FORMULARIO DE REGISTRO (ADMIN) ---
class RegistroUsuarioForm(FlaskForm):
    username = StringField('Nombre de Usuario', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[DataRequired(), EqualTo('password')])
    rol = SelectField('Rol del Usuario', choices=[('2', 'Empleado (Almacén)'), ('1', 'Administrador Total')], validators=[DataRequired()])
    submit = SubmitField('Guardar Usuario')

# --- FORMULARIO DE EDICIÓN DE PERFIL ---
class UserEditForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=64)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Nueva Contraseña', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('Repetir Nueva Contraseña', validators=[EqualTo('password')])
    rol = SelectField('Rol', choices=[('2', 'Empleado'), ('1', 'Administrador')], validators=[Optional()])
    submit = SubmitField('Actualizar Usuario')

    def __init__(self, *args, **kwargs):
        super(UserEditForm, self).__init__(*args, **kwargs)
        self.original_username = kwargs.get('obj').username if kwargs.get('obj') else None
        self.original_email = kwargs.get('obj').email if kwargs.get('obj') else None

    def validate_username(self, username):
        if username.data != self.original_username:
            user = Usuario.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Por favor use un nombre de usuario diferente.')

    def validate_email(self, email):
        if email.data != self.original_email:
            user = Usuario.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Por favor use un correo electrónico diferente.')

# --- FORMULARIO DE PRODUCTO (ACTUALIZADO CON ALMACEN CENTRAL) ---
class ProductoForm(FlaskForm):
    codigo = StringField('Código', validators=[DataRequired(), Length(max=50)])
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    cantidad = FloatField('Cantidad', validators=[DataRequired(), NumberRange(min=0)])
    precio = FloatField('Precio (Bs.)', validators=[DataRequired(), NumberRange(min=0)])
    proveedor = StringField('Proveedor', validators=[Optional(), Length(max=100)])
    stock_minimo = FloatField('Stock Mínimo', default=10.0, validators=[Optional(), NumberRange(min=0)])
    
    # AQUÍ AGREGAMOS 'ALMACEN CENTRAL' A LAS OPCIONES
    subalmacen = SelectField('Subalmacén', choices=[('SCPE', 'SCPE'), ('POZO 57', 'POZO 57'), ('ALMACEN CENTRAL', 'ALMACEN CENTRAL')], validators=[DataRequired()])
    
    unidad = StringField('Unidad', validators=[DataRequired(), Length(max=50)])
    diametro = StringField('Diámetro', validators=[Optional(), Length(max=50)])
    imagen_ingreso = FileField('Imagen de Ingreso (Solo POZO 57)', validators=[Optional()])
    submit = SubmitField('Guardar Producto')

    def __init__(self, *args, **kwargs):
        super(ProductoForm, self).__init__(*args, **kwargs)
        self.original_producto = kwargs.get('obj')

    def validate_codigo(self, codigo):
        producto = Producto.query.filter_by(codigo=codigo.data).first()
        if producto:
            if self.original_producto:
                if producto.id != self.original_producto.id:
                    raise ValidationError('El código ya existe en otro producto.')
            else:
                raise ValidationError('El código ya existe. Por favor use un código diferente.')

# --- FORMULARIOS RESTANTES (SIN CAMBIOS) ---
class BusquedaForm(FlaskForm):
    busqueda = StringField('Buscar por nombre o código', validators=[Optional()])
    submit = SubmitField('Buscar')

class SalidaForm(FlaskForm):
    producto_id = SelectField('Producto', coerce=int, validators=[DataRequired()])
    cantidad_salida = FloatField('Cantidad a Salir', validators=[DataRequired(), NumberRange(min=0.01)])
    nombre_funcionario = StringField('Nombre del Funcionario', validators=[DataRequired(), Length(max=100)])
    codigo_funcionario = StringField('Código del Funcionario', validators=[DataRequired(), Length(max=50)])
    imagen_salida = FileField('Imagen de Salida (Solo POZO 57)', validators=[Optional()])
    submit = SubmitField('Registrar Salida')

class ImportForm(FlaskForm):
    file = FileField('Archivo Excel', validators=[DataRequired()])
    submit = SubmitField('Importar')