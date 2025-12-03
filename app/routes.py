# app/routes.py
# ARCHIVO COMPLETO Y EXTENDIDO - VERSIÓN FINAL
# Incluye:
# 1. Gestión de Imágenes (Función auxiliar)
# 2. Reportes PDF y Excel (Formato completo y extendido con ReportLab)
# 3. Nuevas rutas: editar_salida, eliminar_salida, historial
# 4. Correcciones críticas: 
#    - Error 'Choices cannot be None' en Salidas
#    - Error 'InterfaceError' en Edición de Salidas (FileStorage)
#    - Visualización de nombres de usuario en Historial
# 5. Soporte para ALMACEN CENTRAL

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, abort, current_app
from app import db
from app.models import Producto, Usuario, Salida, Ingreso
# Importamos todos los formularios necesarios
from app.forms import (
    ProductoForm, 
    BusquedaForm, 
    LoginForm, 
    RegistrationForm, 
    SalidaForm, 
    ImportForm, 
    UserEditForm, 
    RegistroUsuarioForm  # Nuevo formulario para gestión de usuarios
)
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlparse
import pandas as pd
from io import BytesIO
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from collections import defaultdict
from wtforms.validators import DataRequired

# --- IMPORTS DE REPORTLAB (Para generación de PDF profesional) ---
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4, landscape

bp = Blueprint('main', __name__)

# --- AJUSTE DE ZONA HORARIA BOLIVIA (GMT-4) ---
def get_bolivia_time(utc_dt):
    """Convierte una fecha UTC a la hora de Bolivia (GMT-4)"""
    if not utc_dt: return None
    return utc_dt - timedelta(hours=4)


# =================================================================
# --- FUNCIÓN AUXILIAR PARA GUARDAR IMÁGENES ---
# =================================================================
def guardar_imagen(file_storage, subalmacen_actual):
    """
    Guarda un archivo de imagen en una estructura de carpetas basada en fechas
    y devuelve la ruta relativa para la base de datos.
    Requerimiento: Solo guarda si el subalmacen es 'POZO 57'.
    """
    # 1. Validar que el archivo existe y el subalmacén es el correcto
    if not file_storage or subalmacen_actual != 'POZO 57':
        return None

    try:
        # 2. Generar nombres y rutas basadas en la fecha actual
        now = datetime.now()
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        original_filename = secure_filename(file_storage.filename)
        filename_base, ext = os.path.splitext(original_filename)
        
        # Timestamp para unicidad
        timestamp = now.strftime('%H%M%S_%f')
        unique_filename = f"{filename_base}_{timestamp}{ext}"

        # 3. Definir rutas
        # Ruta relativa para la BD (ej: 'uploads/2025/11/07/mi_imagen.jpg')
        relative_dir = os.path.join('uploads', year, month, day)
        # Reemplazamos separadores de OS por '/' para compatibilidad web
        relative_filepath = os.path.join(relative_dir, unique_filename).replace(os.path.sep, '/')
        
        # Ruta absoluta para guardar en el servidor
        absolute_dir = os.path.join(current_app.root_path, 'static', relative_dir)
        os.makedirs(absolute_dir, exist_ok=True) # Crea carpetas si no existen
        
        absolute_filepath = os.path.join(absolute_dir, unique_filename)
        
        # 4. Guardar el archivo físico
        file_storage.save(absolute_filepath)
        
        current_app.logger.info(f"Imagen guardada en: {absolute_filepath}")
        return relative_filepath

    except Exception as e:
        flash(f'Error crítico al guardar la imagen: {str(e)}', 'danger')
        current_app.logger.error(f"Error al guardar imagen: {e}")
        return None


# =================================================================
# --- FUNCIONES AUXILIARES Y ESTILOS PARA PDF (REPORTLAB) ---
# =================================================================

def get_professional_table_style():
    """Retorna un estilo de tabla corporativo y limpio para los reportes"""
    return TableStyle([
        # Cabecera
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#00416A')), # Azul corporativo
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ('TOPPADDING', (0,0), (-1,0), 10),
        
        # Cuerpo
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ALIGN', (0,1), (0,-1), 'LEFT'), # Primera columna a la izquierda
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'), # Resto (números) a la derecha
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        
        # Líneas sutiles
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#00416A')), # Debajo del header
        ('LINEBELOW', (0,1), (-1,-2), 0.5, colors.HexColor('#E0E0E0')), # Entre filas
        ('LINEABOVE', (0,-1), (-1,-1), 1, colors.black), # Encima del total
    ])

def apply_zebra_striping(table, data):
    """Aplica fondo alterno a las filas para mejorar lectura"""
    for i in range(1, len(data)):
        if i == len(data) - 1: # Fila de TOTALES
            bg_color = colors.HexColor('#E8E8E8')
            table.setStyle(TableStyle([
                ('FONTNAME', (0,i), (-1,i), 'Helvetica-Bold'),
                ('BACKGROUND', (0,i), (-1,i), bg_color),
            ]))
        elif i % 2 == 0:
            bg_color = colors.HexColor('#F4F6F7')
            table.setStyle(TableStyle([('BACKGROUND', (0,i), (-1,i), bg_color)]))


def _draw_header(canvas, doc, title, subtitle):
    """Dibuja el encabezado estándar en cada página del PDF"""
    canvas.saveState()
    width, height = doc.pagesize
    
    # 1. Banner superior sutil
    canvas.setFillColorRGB(0.96, 0.97, 0.98) # Gris/Azulado muy claro de fondo
    canvas.rect(0, height - (3.0*cm), width, (3.0*cm), fill=1, stroke=0)
    
    # 2. Intentar cargar el logo
    logo_path = os.path.join(current_app.root_path, 'static', 'img', 'logo.jpg')
    if os.path.exists(logo_path):
        logo_height_cm = 1.8 * cm
        logo_x_cm = -3.8 * cm
        logo_y_cm = height - 2.2*cm
        try:
            canvas.drawImage(
                logo_path, 
                logo_x_cm, 
                logo_y_cm, 
                height=logo_height_cm, 
                preserveAspectRatio=True, 
                mask='auto'
            )
        except Exception as e:
            current_app.logger.error(f"Error al dibujar imagen en PDF: {e}")
    
    # 3. Títulos
    canvas.setFillColor(colors.HexColor('#00416A')) # Azul corporativo
    canvas.setFont("Helvetica-Bold", 22)
    canvas.drawString(4.0*cm, height - 1.5*cm, title)
    
    canvas.setFillColor(colors.gray)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(4.0*cm, height - 2.2*cm, subtitle)
    
    # 4. Fecha de generación
    canvas.setFont("Helvetica", 9)
    fecha_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    canvas.drawRightString(width - 2*cm, height - 2.2*cm, f"Generado: {fecha_str}")
    
    # Línea decorativa azul
    canvas.setStrokeColor(colors.HexColor('#00416A'))
    canvas.setLineWidth(2)
    canvas.line(0, height - 3.0*cm, width, height - 3.0*cm)
    
    canvas.restoreState()

def _draw_footer(canvas, doc):
    """Dibuja el pie de página estándar"""
    canvas.saveState()
    width, height = doc.pagesize
    
    # Línea separadora
    canvas.setStrokeColor(colors.lightgrey)
    canvas.line(1.5*cm, 1.5*cm, width-1.5*cm, 1.5*cm)
    
    # Textos
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2*cm, 1*cm, "Sistema de Control de Pozos y Estaciones (SCPE)")
    
    # Número de página
    canvas.drawRightString(width - 2*cm, 1*cm, f"Página {canvas.getPageNumber()}")
    canvas.restoreState()

# Wrappers específicos para cada tipo de reporte (para facilitar la llamada en el build)
def _header_footer_general(canvas, doc):
    _draw_header(canvas, doc, "INVENTARIO GENERAL", "Estado actual del almacén")
    _draw_footer(canvas, doc)

def _header_footer_ingresos(canvas, doc):
    _draw_header(canvas, doc, "REPORTE DE INGRESOS", "Historial de entradas al almacén")
    _draw_footer(canvas, doc)

def _header_footer_salidas(canvas, doc):
    _draw_header(canvas, doc, "REPORTE DE SALIDAS", "Historial de retiros por funcionario")
    _draw_footer(canvas, doc)

def _header_footer_por_item(canvas, doc):
    _draw_header(canvas, doc, "SALIDAS POR PRODUCTO", "Detalle de movimientos por ítem")
    _draw_footer(canvas, doc)

def _header_footer_por_subalmacen(canvas, doc):
    _draw_header(canvas, doc, "POR SUBALMACÉN", "Inventario valorado por ubicación")
    _draw_footer(canvas, doc)

def _header_footer_historial(canvas, doc):
    _draw_header(canvas, doc, "HISTORIAL DE MOVIMIENTOS", "Kardex completo de operaciones")
    _draw_footer(canvas, doc)


# =================================================================
# --- RUTAS DE AUTENTICACIÓN ---
# =================================================================

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.inventario'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Usuario o contraseña inválidos.', 'danger')
            return redirect(url_for('main.login'))
        
        login_user(user, remember=form.remember_me.data)
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '': 
            next_page = url_for('main.inventario')
        return redirect(next_page)
    
    return render_template('login.html', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('main.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Verificar si el registro está permitido (solo si no hay usuarios o si es admin)
    if Usuario.query.count() > 0 and not (current_user.is_authenticated and current_user.is_admin()):
        flash('El registro está deshabilitado. Contacte a un administrador.', 'warning')
        return redirect(url_for('main.inventario'))
    
    form = RegistrationForm()
    admin_setup = (Usuario.query.count() == 0)
    
    if form.validate_on_submit():
        user = Usuario(username=form.username.data, email=form.email.data)
        
        # Lógica de asignación de rol
        if admin_setup:
            user.rol = 1 # Primer usuario es Admin
        elif current_user.is_authenticated and current_user.is_admin():
            user.rol = form.rol.data # Admin puede elegir rol
        else:
            user.rol = 2 # Por defecto Empleado
        
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('Usuario registrado con éxito. Por favor, inicia sesión.', 'success')
        return redirect(url_for('main.login'))
    
    return render_template('register.html', form=form, admin_setup=admin_setup)


# =================================================================
# --- CRUD DE INVENTARIO (Create, Read, Update, Delete) ---
# =================================================================

@bp.route('/', methods=['GET', 'POST'])
@login_required
def inventario():
    form = BusquedaForm()
    productos = Producto.query.all()
    busqueda = None
    
    if form.validate_on_submit():
        busqueda = form.busqueda.data
        productos = Producto.query.filter(
            (Producto.nombre.ilike(f'%{busqueda}%')) | 
            (Producto.codigo.ilike(f'%{busqueda}%'))
        ).all()
        if not productos:
            flash(f'No se encontraron productos para "{busqueda}".', 'info')
    
    alertas_stock = [p for p in productos if p.necesita_alerta()]
    
    return render_template(
        'inventario.html', 
        productos=productos, 
        form=form,
        alertas=alertas_stock,
        busqueda=busqueda,
        current_user=current_user 
    )

@bp.route('/agregar', methods=['GET', 'POST'])
@bp.route('/editar/<int:producto_id>', methods=['GET', 'POST'])
@login_required
def agregar_editar(producto_id=None):
    if not current_user.is_admin():
        flash('Acceso denegado. Se requiere rol de Administrador para modificar el inventario.', 'danger')
        return redirect(url_for('main.inventario'))

    producto = Producto.query.get_or_404(producto_id) if producto_id else None
    form = ProductoForm(obj=producto)

    if form.validate_on_submit():
        try:
            if producto:
                # --- Lógica de EDICIÓN ---
                cantidad_anterior = producto.cantidad
                form.populate_obj(producto) 
                
                if producto.cantidad > cantidad_anterior:
                    # Registrar ingreso automático si aumenta el stock
                    cantidad_agregada = producto.cantidad - cantidad_anterior
                    imagen_ingreso_path = guardar_imagen(form.imagen_ingreso.data, producto.subalmacen)
                    
                    # Registrar el ingreso con el usuario actual
                    nuevo_ingreso = Ingreso(
                        producto_id=producto.id,
                        cantidad_agregada=cantidad_agregada,
                        imagen_ingreso=imagen_ingreso_path,
                        usuario_id=current_user.id
                    )
                    db.session.add(nuevo_ingreso)
                
                flash('Producto actualizado con éxito.', 'success')

            else:
                # --- Lógica de CREACIÓN ---
                nuevo_producto = Producto()
                form.populate_obj(nuevo_producto)
                
                imagen_ingreso_path = guardar_imagen(form.imagen_ingreso.data, nuevo_producto.subalmacen)
                
                db.session.add(nuevo_producto)
                
                # Registrar ingreso inicial
                nuevo_ingreso = Ingreso(
                    producto=nuevo_producto,
                    cantidad_agregada=nuevo_producto.cantidad,
                    imagen_ingreso=imagen_ingreso_path,
                    usuario_id=current_user.id
                )
                db.session.add(nuevo_ingreso)
                flash('Producto agregado al inventario.', 'success')

            db.session.commit()
            return redirect(url_for('main.inventario'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar el producto: {str(e)}', 'danger')
            current_app.logger.error(f"Error en agregar_editar: {e}")

    titulo = 'Editar Producto' if producto_id else 'Agregar Nuevo Producto'
    return render_template('agregar_editar.html', form=form, titulo=titulo, producto=producto, Producto=Producto)


@bp.route('/eliminar/<int:producto_id>', methods=['POST'])
@login_required
def eliminar(producto_id):
    if not current_user.is_admin():
        flash('Acceso denegado. Se requiere rol de Administrador para eliminar productos.', 'danger')
        return redirect(url_for('main.inventario'))
    
    producto = Producto.query.get_or_404(producto_id)
    try:
        db.session.delete(producto)
        db.session.commit()
        flash(f'Producto "{producto.nombre}" eliminado.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el producto: {str(e)}', 'danger')
        current_app.logger.error(f"Error en eliminar: {e}")
        
    return redirect(url_for('main.inventario'))


# =================================================================
# --- GESTIÓN DE SALIDAS (Registrar, Editar, Eliminar) ---
# =================================================================

@bp.route('/salida', methods=['GET', 'POST'])
@login_required
def salida():
    form = SalidaForm()
    
    # --- CORRECCIÓN: Cargar choices SIEMPRE para evitar error de validación ---
    form.producto_id.choices = [(p.id, f'{p.nombre} ({p.subalmacen})') for p in Producto.query.all()]

    if form.validate_on_submit():
        producto = Producto.query.get_or_404(form.producto_id.data)
        
        if producto.cantidad < form.cantidad_salida.data:
            flash(f'Cantidad insuficiente en stock. Disponible: {producto.cantidad}', 'danger')
            return redirect(url_for('main.salida'))

        try:
            # Restar del inventario
            producto.cantidad -= form.cantidad_salida.data
            
            imagen_salida_path = guardar_imagen(form.imagen_salida.data, producto.subalmacen)

            nueva_salida = Salida(
                producto_id=producto.id,
                cantidad_salida=form.cantidad_salida.data,
                nombre_funcionario=form.nombre_funcionario.data,
                codigo_funcionario=form.codigo_funcionario.data,
                precio_en_bs=producto.precio,
                imagen_salida=imagen_salida_path,
                usuario_id=current_user.id  # Guardamos quién registró
            )
            
            db.session.add(nueva_salida)
            db.session.commit() 
            
            flash('Salida registrada con éxito.', 'success')
            return redirect(url_for('main.inventario'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar la salida: {str(e)}', 'danger')
            current_app.logger.error(f"Error en salida: {e}")

    return render_template('salida.html', form=form, titulo="Registrar Salida")


# --- RUTA: ELIMINAR SALIDA (CON DEVOLUCIÓN DE STOCK) ---
@bp.route('/eliminar_salida/<int:salida_id>', methods=['POST'])
@login_required
def eliminar_salida(salida_id):
    if not current_user.is_admin():
        flash('Solo administradores pueden eliminar registros de salida.', 'danger')
        return redirect(url_for('main.reporte_salidas'))
    
    salida = Salida.query.get_or_404(salida_id)
    producto = Producto.query.get(salida.producto_id)
    
    try:
        # IMPORTANTE: Devolver el stock al inventario antes de borrar
        if producto:
            producto.cantidad += salida.cantidad_salida
            
        db.session.delete(salida)
        db.session.commit()
        flash('Registro de salida eliminado. El stock ha sido devuelto al inventario.', 'success')
        
        # Redirigir al lugar correcto
        if 'historial' in request.referrer:
             return redirect(url_for('main.historial'))
        return redirect(url_for('main.reporte_salidas'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el registro: {e}', 'danger')
        return redirect(url_for('main.reporte_salidas'))


# --- RUTA: EDITAR SALIDA (CON CORRECCIÓN DE IMAGEN Y STOCK) ---
@bp.route('/editar_salida/<int:salida_id>', methods=['GET', 'POST'])
@login_required
def editar_salida(salida_id):
    if not current_user.is_admin():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.reporte_salidas'))
    
    salida_obj = Salida.query.get_or_404(salida_id)
    form = SalidaForm(obj=salida_obj)
    
    # Cargar lista de productos
    form.producto_id.choices = [(p.id, f'{p.nombre} ({p.subalmacen})') for p in Producto.query.all()]
    
    # Pre-seleccionar producto en modo GET
    if request.method == 'GET':
        form.producto_id.data = salida_obj.producto_id

    if form.validate_on_submit():
        try:
            # 1. REVERTIR: Devolver el stock original como si la salida no hubiera ocurrido
            prod_ant = Producto.query.get(salida_obj.producto_id)
            if prod_ant:
                prod_ant.cantidad += salida_obj.cantidad_salida
            
            # 2. VERIFICAR: ¿Hay stock suficiente para la NUEVA cantidad solicitada?
            prod_nuevo = Producto.query.get(form.producto_id.data)
            
            if prod_nuevo.cantidad < form.cantidad_salida.data:
                # Si falla, deshacemos la reversión manualmente
                prod_ant.cantidad -= salida_obj.cantidad_salida 
                flash(f'Stock insuficiente para la nueva cantidad. Disponible: {prod_nuevo.cantidad}', 'danger')
                return render_template('salida.html', form=form, titulo="Editar Salida")

            # 3. APLICAR: Restar la nueva cantidad del inventario
            prod_nuevo.cantidad -= form.cantidad_salida.data
            
            # 4. ACTUALIZACIÓN MANUAL DE CAMPOS (Evita error de FileStorage)
            salida_obj.producto_id = form.producto_id.data
            salida_obj.cantidad_salida = form.cantidad_salida.data
            salida_obj.nombre_funcionario = form.nombre_funcionario.data
            salida_obj.codigo_funcionario = form.codigo_funcionario.data
            salida_obj.precio_en_bs = prod_nuevo.precio # Actualizar precio si cambió el producto
            
            # 5. MANEJO SEGURO DE LA IMAGEN
            if form.imagen_salida.data:
                nueva_imagen = guardar_imagen(form.imagen_salida.data, prod_nuevo.subalmacen)
                if nueva_imagen:
                    salida_obj.imagen_salida = nueva_imagen
            
            db.session.commit()
            flash('Registro de salida actualizado correctamente.', 'success')
            
            if 'historial' in request.referrer:
                return redirect(url_for('main.historial'))
            return redirect(url_for('main.reporte_salidas'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el registro: {e}', 'danger')

    return render_template('salida.html', form=form, titulo="Editar Salida")


# =================================================================
# --- HISTORIAL DE MOVIMIENTOS (KARDEX) ---
# =================================================================

def obtener_movimientos():
    """Función auxiliar para obtener y ordenar todos los movimientos (Kardex)"""
    ingresos = Ingreso.query.all()
    salidas = Salida.query.all()
    movimientos = []
    
    def get_user_display(user_obj):
        if user_obj:
            role = "Admin" if user_obj.rol == 1 else "Empleado"
            return f"{user_obj.username} ({role})"
        else:
            return "Sistema (Registro Histórico)"

    # Procesar Ingresos
    for i in ingresos:
        movimientos.append({
            'id': i.id,
            'tipo_raw': 'ingreso',
            'tipo': 'INGRESO',
            'fecha': get_bolivia_time(i.fecha_ingreso),
            'producto': i.producto.nombre,
            'codigo': i.producto.codigo,
            'cantidad': i.cantidad_agregada,
            'usuario_sistema': get_user_display(i.usuario),
            'detalle': 'Compra / Actualización de Stock',
            'color': 'success',
            'icono': 'fa-arrow-down'
        })
        
    # Procesar Salidas
    for s in salidas:
        movimientos.append({
            'id': s.id,
            'tipo_raw': 'salida',
            'tipo': 'SALIDA',
            'fecha': get_bolivia_time(s.fecha_salida),
            'producto': s.producto.nombre,
            'codigo': s.producto.codigo,
            'cantidad': s.cantidad_salida,
            'usuario_sistema': get_user_display(s.usuario),
            'detalle': f"Retirado por: {s.nombre_funcionario}",
            'color': 'danger',
            'icono': 'fa-arrow-up'
        })
    
    # Ordenar por fecha descendente (lo más reciente primero)
    movimientos.sort(key=lambda x: x['fecha'], reverse=True)
    return movimientos

@bp.route('/historial')
@login_required
def historial():
    movimientos = obtener_movimientos()
    return render_template('historial.html', movimientos=movimientos)


# --- EXPORTACIÓN DEL HISTORIAL ---

@bp.route('/exportar/historial/excel')
@login_required
def exportar_historial_excel():
    if not current_user.is_admin(): return redirect(url_for('main.historial'))
    
    movs = obtener_movimientos()
    if not movs:
        flash('Sin datos para exportar.', 'warning')
        return redirect(url_for('main.historial'))
    
    data = []
    for m in movs:
        data.append({
            'Fecha y Hora (Bolivia)': m['fecha'].strftime('%d/%m/%Y %H:%M'),
            'Tipo': m['tipo'],
            'Código': m['codigo'],
            'Producto': m['producto'],
            'Cantidad': m['cantidad'],
            'Registrado Por': m['usuario_sistema'],
            'Detalle': m['detalle']
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Historial_Kardex')
    
    # Ajustar ancho de columnas
    worksheet = writer.sheets['Historial_Kardex']
    worksheet.set_column('A:A', 20)
    worksheet.set_column('B:B', 10)
    worksheet.set_column('C:C', 15)
    worksheet.set_column('D:D', 30)
    worksheet.set_column('F:G', 25)
    
    writer.close()
    output.seek(0)
    return send_file(output, download_name='Historial_Completo.xlsx', as_attachment=True)


@bp.route('/exportar/historial/pdf')
@login_required
def exportar_historial_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.historial'))
    
    movs = obtener_movimientos()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    
    data = [["Fecha", "Tipo", "Producto", "Cant.", "Usuario", "Detalle"]]
    for m in movs:
        data.append([
            m['fecha'].strftime('%d/%m/%y %H:%M'),
            m['tipo'],
            Paragraph(m['producto'], getSampleStyleSheet()['Normal']),
            str(m['cantidad']),
            Paragraph(m['usuario_sistema'], getSampleStyleSheet()['Normal']),
            Paragraph(m['detalle'], getSampleStyleSheet()['Normal'])
        ])
    
    t = Table(data, colWidths=[3.5*cm, 2.5*cm, 8*cm, 2*cm, 5*cm, 6*cm])
    t.setStyle(get_professional_table_style())
    apply_zebra_striping(t, data)
    Story.append(t)
    
    doc.build(Story, onFirstPage=_header_footer_historial, onLaterPages=_header_footer_historial)
    buffer.seek(0)
    return send_file(buffer, download_name='Historial_Completo.pdf', mimetype='application/pdf', as_attachment=True)


# =================================================================
# --- REPORTES (EXPORTACIÓN EXCEL Y PDF) ---
# =================================================================

@bp.route('/exportar/excel')
@login_required
def exportar_excel():
    if not current_user.is_admin():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.inventario'))
    try:
        productos = Producto.query.all()
        datos_exportar = [{
            'Código': p.codigo,
            'Nombre': p.nombre,
            'Cantidad': p.cantidad,
            'Precio': p.precio,
            'Valor Total': p.total_value,
            'Proveedor': p.proveedor,
            'Fecha Ingreso': p.fecha_ingreso.strftime('%Y-%m-%d'),
            'Stock Mínimo': p.stock_minimo,
            'Subalmacén': p.subalmacen,
            'Unidad': p.unidad,
            'Diámetro': p.diametro or ''
        } for p in productos]
        
        df = pd.DataFrame(datos_exportar)
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, index=False, sheet_name='Inventario')
        writer.close()
        output.seek(0)
        
        return send_file(
            output,
            download_name='Reporte_Inventario.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True
        )
    except Exception as e:
        flash(f'Error al generar Excel: {str(e)}', 'danger')
        return redirect(url_for('main.inventario'))

@bp.route('/exportar/reporte_ingresos/excel')
@login_required
def exportar_reporte_ingresos_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    ingresos = Ingreso.query.all()
    if not ingresos:
        flash('No hay ingresos para exportar.', 'warning')
        return redirect(url_for('main.inventario'))
    
    datos_exportar = [{
        'Producto': i.producto.nombre,
        'Código Producto': i.producto.codigo,
        'Cantidad Agregada': i.cantidad_agregada,
        'Fecha Ingreso': i.fecha_ingreso.strftime('%Y-%m-%d %H:%M:%S')
    } for i in ingresos]
    
    df = pd.DataFrame(datos_exportar)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Ingresos')
    writer.close()
    output.seek(0)
    
    return send_file(output, download_name='Reporte_Ingresos.xlsx', as_attachment=True)

@bp.route('/exportar/reporte_salidas/excel')
@login_required
def exportar_reporte_salidas_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    salidas = Salida.query.all()
    if not salidas:
        flash('No hay salidas para exportar.', 'warning')
        return redirect(url_for('main.inventario'))
    
    datos_exportar = [{
        'Funcionario': s.nombre_funcionario,
        'Código Funcionario': s.codigo_funcionario,
        'Producto': s.producto.nombre,
        'Código Producto': s.producto.codigo,
        'Cantidad Salida': s.cantidad_salida,
        'Fecha Salida': s.fecha_salida.strftime('%Y-%m-%d'),
        'Precio Bs.': s.precio_en_bs,
        'Valor Total': s.cantidad_salida * s.precio_en_bs
    } for s in salidas]
    
    df = pd.DataFrame(datos_exportar)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Salidas')
    writer.close()
    output.seek(0)
    
    return send_file(output, download_name='Reporte_Salidas.xlsx', as_attachment=True)

@bp.route('/exportar/reporte_por_item/excel')
@login_required
def exportar_reporte_por_item_excel():
    return exportar_reporte_salidas_excel() # Reutilizamos lógica ya que los datos son similares

@bp.route('/exportar/reporte_por_subalmacen/excel')
@login_required
def exportar_reporte_por_subalmacen_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    datos_exportar = []
    # ACTUALIZACIÓN: Agregado 'ALMACEN CENTRAL'
    for sub in ['SCPE', 'POZO 57', 'ALMACEN CENTRAL']:
        productos = Producto.query.filter_by(subalmacen=sub).all()
        for p in productos:
            datos_exportar.append({
                'Subalmacén': sub,
                'Código': p.codigo,
                'Nombre': p.nombre,
                'Cantidad': p.cantidad,
                'Precio': p.precio,
                'Valor Total': p.total_value
            })
    if not datos_exportar:
        flash('No hay datos para exportar.', 'warning')
        return redirect(url_for('main.inventario'))
    
    df = pd.DataFrame(datos_exportar)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Por_Subalmacen')
    writer.close()
    output.seek(0)
    
    return send_file(output, download_name='Reporte_Por_Subalmacen.xlsx', as_attachment=True)

@bp.route('/exportar/pdf')
@login_required
def exportar_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    productos = Producto.query.all()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    
    data = [["Código", "Nombre", "Cant.", "Precio", "Total", "Subalm.", "Prov."]]
    for p in productos:
        data.append([
            p.codigo, 
            Paragraph(p.nombre, getSampleStyleSheet()['Normal']),
            f"{p.cantidad:.1f}", 
            f"{p.precio:.0f}", 
            f"{p.total_value:.0f}", 
            p.subalmacen, 
            Paragraph(p.proveedor or '', getSampleStyleSheet()['Normal'])
        ])
    
    t = Table(data, colWidths=[2.5*cm, 8*cm, 1.5*cm, 2*cm, 2*cm, 2.5*cm, 4*cm])
    t.setStyle(get_professional_table_style())
    apply_zebra_striping(t, data)
    Story.append(t)
    
    doc.build(Story, onFirstPage=_header_footer_general, onLaterPages=_header_footer_general)
    buffer.seek(0)
    return send_file(buffer, download_name='Reporte_General.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_ingresos/pdf')
@login_required
def exportar_reporte_ingresos_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    ingresos = Ingreso.query.all()
    if not ingresos:
        flash('No hay ingresos para exportar.', 'warning')
        return redirect(url_for('main.inventario'))
        
    reporte = defaultdict(list)
    for i in ingresos:
        reporte[i.producto.nombre].append(i)
        
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    styles = getSampleStyleSheet()
    style_grupo = ParagraphStyle(name='Grupo', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=12, spaceAfter=6, spaceBefore=12)
    
    for producto, lista_ingresos in reporte.items():
        Story.append(Paragraph(f"Producto: {producto}", style_grupo))
        data = [["Cantidad", "Fecha Ingreso"]]
        total_prod = 0
        for ing in lista_ingresos:
            data.append([f"{ing.cantidad_agregada:.2f}", ing.fecha_ingreso.strftime('%Y-%m-%d %H:%M')])
            total_prod += ing.cantidad_agregada
        data.append([f"TOTAL: {total_prod:.2f}", ""])
        
        t = Table(data, colWidths=[4*cm, 6*cm])
        t.setStyle(get_professional_table_style())
        apply_zebra_striping(t, data)
        Story.append(t)
        Story.append(Spacer(1, 0.5*cm))
        
    doc.build(Story, onFirstPage=_header_footer_ingresos, onLaterPages=_header_footer_ingresos)
    buffer.seek(0)
    return send_file(buffer, download_name='Reporte_Ingresos.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_salidas/pdf')
@login_required
def exportar_reporte_salidas_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    salidas = Salida.query.all()
    if not salidas:
        flash('No hay salidas para exportar.', 'warning')
        return redirect(url_for('main.inventario'))
        
    reporte = defaultdict(list)
    for s in salidas:
        reporte[s.nombre_funcionario].append(s)
        
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    styles = getSampleStyleSheet()
    style_grupo = ParagraphStyle(name='Grupo', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=12, spaceAfter=6, spaceBefore=12)
    
    for funcionario, lista_salidas in reporte.items():
        Story.append(Paragraph(f"Funcionario: {funcionario}", style_grupo))
        data = [["Producto", "Cantidad", "Fecha", "Precio U.", "Total"]]
        total_bs = 0
        for sal in lista_salidas:
            total_linea = sal.cantidad_salida * sal.precio_en_bs
            data.append([
                Paragraph(sal.producto.nombre, styles['Normal']), 
                f"{sal.cantidad_salida:.2f}",
                sal.fecha_salida.strftime('%Y-%m-%d'),
                f"{sal.precio_en_bs:.2f}",
                f"{total_linea:.2f}"
            ])
            total_bs += total_linea
        data.append(["", "", "", "TOTAL BS:", f"{total_bs:.2f}"])
        
        t = Table(data, colWidths=[10*cm, 2.5*cm, 3*cm, 2.5*cm, 3*cm])
        t.setStyle(get_professional_table_style())
        apply_zebra_striping(t, data)
        Story.append(t)
        Story.append(Spacer(1, 0.5*cm))
        
    doc.build(Story, onFirstPage=_header_footer_salidas, onLaterPages=_header_footer_salidas)
    buffer.seek(0)
    return send_file(buffer, download_name='Reporte_Salidas.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_por_item/pdf')
@login_required
def exportar_reporte_por_item_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    salidas = Salida.query.all()
    reporte = defaultdict(list)
    for s in salidas:
        reporte[s.producto.nombre].append(s)
        
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    styles = getSampleStyleSheet()
    style_grupo = ParagraphStyle(name='Grupo', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=12)
    
    for producto, lista in reporte.items():
        Story.append(Paragraph(f"Producto: {producto}", style_grupo))
        data = [["Funcionario", "Cantidad", "Fecha", "Total"]]
        total_cant = 0
        for s in lista: 
            data.append([
                s.nombre_funcionario, 
                f"{s.cantidad_salida:.2f}", 
                s.fecha_salida.strftime('%Y-%m-%d'), 
                f"{(s.cantidad_salida * s.precio_en_bs):.2f}"
            ])
            total_cant += s.cantidad_salida
        data.append(["TOTAL CANTIDAD:", f"{total_cant:.2f}", "", ""])
        
        t = Table(data, colWidths=[8*cm, 3*cm, 4*cm, 4*cm])
        t.setStyle(get_professional_table_style())
        apply_zebra_striping(t, data)
        Story.append(t)
        Story.append(Spacer(1, 0.5*cm))

    doc.build(Story, onFirstPage=_header_footer_por_item, onLaterPages=_header_footer_por_item)
    buffer.seek(0)
    return send_file(buffer, download_name='Reporte_Por_Item.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_por_subalmacen/pdf')
@login_required
def exportar_reporte_por_subalmacen_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    # ACTUALIZACIÓN: Agregado 'ALMACEN CENTRAL'
    reporte = {}
    subalmacenes = ['SCPE', 'POZO 57', 'ALMACEN CENTRAL']
    for sub in subalmacenes: 
        reporte[sub] = Producto.query.filter_by(subalmacen=sub).all()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    styles = getSampleStyleSheet()
    
    for sub, lista in reporte.items():
        if not lista: continue
        Story.append(Paragraph(f"Subalmacén: {sub}", styles['h3']))
        data = [["Código", "Nombre", "Cant.", "Precio", "Total"]]
        total_val = 0
        for p in lista: 
            data.append([
                p.codigo, 
                Paragraph(p.nombre, getSampleStyleSheet()['Normal']), 
                f"{p.cantidad:.2f}", 
                f"{p.precio:.2f}", 
                f"{p.total_value:.2f}"
            ])
            total_val += p.total_value
        data.append(["", "", "", "TOTAL VALOR:", f"{total_val:.2f}"])
        
        t = Table(data, colWidths=[3*cm, 10*cm, 3*cm, 3*cm, 4*cm])
        t.setStyle(get_professional_table_style())
        apply_zebra_striping(t, data)
        Story.append(t)
        Story.append(Spacer(1, 0.5*cm))
        
    doc.build(Story, onFirstPage=_header_footer_por_subalmacen, onLaterPages=_header_footer_por_subalmacen)
    buffer.seek(0)
    return send_file(buffer, download_name='Reporte_Por_Subalmacen.pdf', mimetype='application/pdf', as_attachment=True)


# =================================================================
# --- VISTAS HTML DE REPORTES ---
# =================================================================

@bp.route('/reporte_ingresos')
@login_required
def reporte_ingresos():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = defaultdict(list)
    for i in Ingreso.query.all(): reporte[i.producto.nombre].append(i)
    return render_template('reporte_ingresos.html', reporte=reporte)

@bp.route('/reporte_salidas')
@login_required
def reporte_salidas():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = defaultdict(list)
    for s in Salida.query.all(): reporte[s.nombre_funcionario].append(s)
    return render_template('reporte_salidas.html', reporte=reporte)

@bp.route('/reporte_por_item')
@login_required
def reporte_por_item():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = defaultdict(list)
    for s in Salida.query.all(): reporte[s.producto.nombre].append(s)
    return render_template('reporte_por_item.html', reporte=reporte)

@bp.route('/reporte_top_productos_in')
@login_required
def reporte_top_productos_in():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    return render_template('reporte_top_productos.html', productos=Producto.query.order_by(Producto.cantidad.desc()).limit(10).all(), tipo='agregados')

@bp.route('/reporte_top_productos_out')
@login_required
def reporte_top_productos_out():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    from sqlalchemy import func
    top_salidas = db.session.query(
        Salida.producto_id,
        func.sum(Salida.cantidad_salida).label('total_salida')
    ).group_by(Salida.producto_id).order_by(func.sum(Salida.cantidad_salida).desc()).limit(10).all()
    
    productos = []
    for salida in top_salidas:
        producto = Producto.query.get(salida.producto_id)
        if producto:
            producto.total_salida = salida.total_salida
            productos.append(producto)
            
    return render_template('reporte_top_productos.html', productos=productos, tipo='salidos')

@bp.route('/reporte_por_subalmacen')
@login_required
def reporte_por_subalmacen():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = {}
    # ACTUALIZACIÓN: Agregado 'ALMACEN CENTRAL'
    for sub in ['SCPE', 'POZO 57', 'ALMACEN CENTRAL']:
        ps = Producto.query.filter_by(subalmacen=sub).all()
        reporte[sub] = {'productos': ps, 'total_value': sum(p.total_value for p in ps)}
    return render_template('reporte_por_subalmacen.html', reporte=reporte)


# =================================================================
# --- IMPORTACIÓN MASIVA ---
# =================================================================

@bp.route('/importar/excel', methods=['GET', 'POST'])
@login_required
def importar_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    form = ImportForm()
    if form.validate_on_submit():
        file = form.file.data
        if not file.filename.endswith('.xlsx'):
            flash('El archivo debe ser un Excel (.xlsx).', 'danger')
            return redirect(request.url)
        try:
            df = pd.read_excel(file)
            productos_importados = 0
            errores = []
            for index, row in df.iterrows():
                try:
                    if pd.isna(row.get('Código')) or pd.isna(row.get('Nombre')): continue
                    
                    # Verificar duplicados
                    if Producto.query.filter_by(codigo=str(row['Código']).strip()).first():
                        errores.append(f"Fila {index+2}: Código '{row['Código']}' repetido.")
                        continue
                        
                    nuevo_producto = Producto(
                        codigo=str(row['Código']).strip(),
                        nombre=str(row['Nombre']).strip(),
                        cantidad=float(row['Cantidad']),
                        precio=float(row['Precio']),
                        proveedor=str(row.get('Proveedor', '')).strip(),
                        stock_minimo=float(row.get('Stock Mínimo', 0.0)),
                        subalmacen=str(row['Subalmacén']).strip(),
                        unidad=str(row['Unidad']).strip(),
                        diametro=str(row.get('Diámetro', '')).strip()
                    )
                    db.session.add(nuevo_producto)
                    productos_importados += 1
                    
                except Exception as ex:
                    errores.append(f"Fila {index+2}: {str(ex)}")
            
            db.session.commit()
            flash(f'Importación completada. {productos_importados} productos importados.', 'success')
            if errores:
                flash(f'Errores encontrados: {"; ".join(errores)}', 'warning')
                
        except Exception as e:
            flash(f'Error al procesar el archivo: {str(e)}', 'danger')
            
    return render_template('importar.html', form=form)


# =================================================================
# --- GESTIÓN DE USUARIOS (CORE REEMPLAZADO Y MEJORADO) ---
# =================================================================
@bp.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.rol != 1:
        flash('Acceso denegado. Se requieren permisos de administrador.', 'danger')
        return redirect(url_for('main.index'))

    form = RegistroUsuarioForm()
    users = Usuario.query.all()
    edit_user = None

    # 1. Lógica de Interacción (Botones de la Tabla)
    if request.method == 'POST' and 'action' in request.form:
        action = request.form.get('action')
        uid = request.form.get('user_id')
        
        if action == 'delete' and uid:
            u = Usuario.query.get(uid)
            if u:
                # Protección para no borrar el último admin
                if u.rol == 1 and Usuario.query.filter_by(rol=1).count() <= 1: 
                    flash('No puedes borrar al último administrador del sistema.', 'danger')
                else: 
                    db.session.delete(u)
                    db.session.commit()
                    flash('Usuario eliminado correctamente.', 'success')
            return redirect(url_for('main.manage_users'))
        
        elif action == 'edit' and uid:
            u = Usuario.query.get(uid)
            if u:
                edit_user = u
                form.username.data = u.username
                form.email.data = u.email
                form.rol.data = str(u.rol)

    # 2. Truco para validación de contraseña vacía en edición
    # Si se está editando y el campo password está vacío, quitamos la obligatoriedad
    if request.method == 'POST' and request.form.get('user_id_edit'):
        if not form.password.data:
            form.password.validators = [v for v in form.password.validators if not isinstance(v, DataRequired)]
            form.confirm_password.validators = [v for v in form.confirm_password.validators if not isinstance(v, DataRequired)]

    # 3. Procesamiento del Formulario (Crear o Actualizar)
    if form.validate_on_submit():
        uid_edit = request.form.get('user_id_edit')
        
        if uid_edit:
            # --- MODO ACTUALIZAR ---
            u = Usuario.query.get(uid_edit)
            if u:
                # Verificar duplicados (excluyendo al usuario actual)
                dup = Usuario.query.filter(
                    (Usuario.username==form.username.data) | (Usuario.email==form.email.data)
                ).filter(Usuario.id!=u.id).first()
                
                if dup: 
                    flash('El nombre de usuario o correo ya está en uso por otra persona.', 'warning')
                else:
                    u.username = form.username.data
                    u.email = form.email.data
                    u.rol = int(form.rol.data)
                    # Solo actualizamos pass si se escribió algo
                    if form.password.data: 
                        u.set_password(form.password.data)
                    
                    db.session.commit()
                    flash('Usuario actualizado correctamente.', 'success')
                    return redirect(url_for('main.manage_users'))
        else:
            # --- MODO CREAR NUEVO ---
            if Usuario.query.filter((Usuario.username==form.username.data) | (Usuario.email==form.email.data)).first():
                flash('El nombre de usuario o correo ya existe.', 'warning')
            else:
                nu = Usuario(
                    username=form.username.data, 
                    email=form.email.data, 
                    rol=int(form.rol.data)
                )
                nu.set_password(form.password.data)
                db.session.add(nu)
                db.session.commit()
                flash('Usuario creado exitosamente.', 'success')
                return redirect(url_for('main.manage_users'))

    return render_template('manage_users.html', form=form, users=users, edit_user=edit_user)
# --- AGREGAR EN app/routes.py ---

# 1. Definimos el encabezado específico para este reporte
def _header_footer_critico(canvas, doc):
    _draw_header(canvas, doc, "REPORTE DE STOCK CRÍTICO", "Productos con existencia bajo el mínimo")
    _draw_footer(canvas, doc)

# 2. Ruta para Excel
@bp.route('/exportar/stock_critico/excel')
@login_required
def exportar_stock_critico_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    
    # Filtramos usando la lógica de tu modelo (Pythonic way)
    todos = Producto.query.all()
    criticos = [p for p in todos if p.necesita_alerta()]
    
    if not criticos:
        flash('Excelente noticia: No hay productos en stock crítico.', 'success')
        return redirect(url_for('main.inventario'))
    
    datos_exportar = [{
        'Código': p.codigo,
        'Nombre': p.nombre,
        'Cantidad Actual': p.cantidad,
        'Stock Mínimo': p.stock_minimo,
        'Déficit': p.stock_minimo - p.cantidad, # Dato útil para compras
        'Proveedor': p.proveedor,
        'Subalmacén': p.subalmacen
    } for p in criticos]
    
    df = pd.DataFrame(datos_exportar)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Stock_Critico')
    
    # Ajuste cosmético de columnas
    worksheet = writer.sheets['Stock_Critico']
    worksheet.set_column('B:B', 30) # Columna Nombre más ancha
    
    writer.close()
    output.seek(0)
    
    return send_file(output, download_name='Alerta_Stock_Critico.xlsx', as_attachment=True)

# 3. Ruta para PDF
@bp.route('/exportar/stock_critico/pdf')
@login_required
def exportar_stock_critico_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    
    todos = Producto.query.all()
    criticos = [p for p in todos if p.necesita_alerta()]
    
    if not criticos:
        flash('No hay productos en riesgo para generar reporte.', 'info')
        return redirect(url_for('main.inventario'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    
    # Texto de advertencia
    styles = getSampleStyleSheet()
    Story.append(Paragraph(f"¡ATENCIÓN! Se han detectado {len(criticos)} ítems por debajo del nivel requerido.", styles['Normal']))
    Story.append(Spacer(1, 0.5*cm))

    data = [["Código", "Nombre", "Actual", "Mínimo", "Subalmacén"]]
    for p in criticos:
        data.append([
            p.codigo,
            Paragraph(p.nombre, styles['Normal']),
            f"{p.cantidad:.2f}",
            f"{p.stock_minimo:.2f}",
            p.subalmacen
        ])
    
    # Usamos tu estilo profesional, pero podríamos cambiar el color de fondo del header a rojo si quisiéramos ser dramáticos
    t = Table(data, colWidths=[3*cm, 8*cm, 2*cm, 2*cm, 3*cm])
    t.setStyle(get_professional_table_style())
    
    # Sobrescribimos el header a un color ROJO suave para indicar alerta
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#C0392B')), # Rojo Alerta
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ]))
    
    apply_zebra_striping(t, data)
    Story.append(t)
    
    doc.build(Story, onFirstPage=_header_footer_critico, onLaterPages=_header_footer_critico)
    buffer.seek(0)
    return send_file(buffer, download_name='Alerta_Stock_Critico.pdf', mimetype='application/pdf', as_attachment=True)