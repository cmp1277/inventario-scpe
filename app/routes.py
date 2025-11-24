# app/routes.py
# ARCHIVO COMPLETO Y DEFINITIVO (Versión Final con Historial Full)
# Incluye: Exportación de Historial, Edición/Eliminación desde Historial y Zona Horaria Bolivia.

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, abort, current_app
from app import db
from app.models import Producto, Usuario, Salida, Ingreso
from app.forms import (
    ProductoForm, BusquedaForm, LoginForm, RegistrationForm, 
    SalidaForm, ImportForm, UserEditForm, RegistroUsuarioForm
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

# --- IMPORTS DE REPORTLAB ---
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
    if not utc_dt: return None
    # Restamos 4 horas a la hora UTC del servidor
    return utc_dt - timedelta(hours=4)

# =================================================================
# --- FUNCIÓN AUXILIAR PARA GUARDAR IMÁGENES ---
# =================================================================
def guardar_imagen(file_storage, subalmacen_actual):
    if not file_storage or subalmacen_actual != 'POZO 57':
        return None
    try:
        now = datetime.now()
        year = now.strftime('%Y'); month = now.strftime('%m'); day = now.strftime('%d')
        original_filename = secure_filename(file_storage.filename)
        filename_base, ext = os.path.splitext(original_filename)
        timestamp = now.strftime('%H%M%S_%f')
        unique_filename = f"{filename_base}_{timestamp}{ext}"
        relative_dir = os.path.join('uploads', year, month, day)
        relative_filepath = os.path.join(relative_dir, unique_filename).replace(os.path.sep, '/')
        absolute_dir = os.path.join(current_app.root_path, 'static', relative_dir)
        os.makedirs(absolute_dir, exist_ok=True)
        absolute_filepath = os.path.join(absolute_dir, unique_filename)
        file_storage.save(absolute_filepath)
        return relative_filepath
    except Exception as e:
        current_app.logger.error(f"Error al guardar imagen: {e}")
        return None

# --- ESTILOS PROFESIONALES PDF ---
def get_professional_table_style():
    return TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#00416A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ('TOPPADDING', (0,0), (-1,0), 10),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#00416A')),
        ('LINEBELOW', (0,1), (-1,-2), 0.5, colors.HexColor('#E0E0E0')),
        ('LINEABOVE', (0,-1), (-1,-1), 1, colors.black),
    ])

def apply_zebra_striping(table, data):
    for i in range(1, len(data)):
        if i % 2 == 0:
            bg_color = colors.HexColor('#F4F6F7')
            table.setStyle(TableStyle([('BACKGROUND', (0,i), (-1,i), bg_color)]))

# --- HEADERS Y FOOTERS PDF ---
def _draw_header(canvas, doc, title, subtitle):
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setFillColorRGB(0.96, 0.97, 0.98); canvas.rect(0, height - (3.0*cm), width, (3.0*cm), fill=1, stroke=0)
    logo_path = os.path.join(current_app.root_path, 'static', 'img', 'logo.jpg')
    if os.path.exists(logo_path):
        try: canvas.drawImage(logo_path, -4.0*cm, height - 2.3*cm, height=1.9*cm, preserveAspectRatio=True, mask='auto')
        except: pass
    canvas.setFillColor(colors.HexColor('#00416A')); canvas.setFont("Helvetica-Bold", 22)
    canvas.drawString(4.0*cm, height - 1.5*cm, title)
    canvas.setFillColor(colors.gray); canvas.setFont("Helvetica", 12)
    canvas.drawString(4.0*cm, height - 2.2*cm, subtitle)
    canvas.setFont("Helvetica", 9); canvas.drawRightString(width - 2*cm, height - 2.2*cm, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.setStrokeColor(colors.HexColor('#00416A')); canvas.setLineWidth(2)
    canvas.line(0, height - 3.0*cm, width, height - 3.0*cm)
    canvas.restoreState()

def _draw_footer(canvas, doc):
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setStrokeColor(colors.lightgrey); canvas.line(1.5*cm, 1.5*cm, width-1.5*cm, 1.5*cm)
    canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.grey)
    canvas.drawString(2*cm, 1*cm, "Sistema de Control de Pozos y Estaciones (SCPE)")
    canvas.drawRightString(width - 2*cm, 1*cm, f"Página {canvas.getPageNumber()}")
    canvas.restoreState()

def _header_footer_general(c, d): _draw_header(c, d, "INVENTARIO GENERAL", "Estado actual del almacén"); _draw_footer(c, d)
def _header_footer_ingresos(c, d): _draw_header(c, d, "REPORTE DE INGRESOS", "Historial de entradas al almacén"); _draw_footer(c, d)
def _header_footer_salidas(c, d): _draw_header(c, d, "REPORTE DE SALIDAS", "Historial de retiros por funcionario"); _draw_footer(c, d)
def _header_footer_por_item(c, d): _draw_header(c, d, "SALIDAS POR PRODUCTO", "Detalle de movimientos por ítem"); _draw_footer(c, d)
def _header_footer_por_subalmacen(c, d): _draw_header(c, d, "POR SUBALMACÉN", "Inventario valorado por ubicación"); _draw_footer(c, d)
# NUEVO HEADER PARA HISTORIAL
def _header_footer_historial(c, d): _draw_header(c, d, "HISTORIAL DE MOVIMIENTOS", "Kardex completo de operaciones"); _draw_footer(c, d)

# --- RUTAS DE AUTENTICACIÓN ---
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.inventario'))
    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect(url_for('main.inventario'))
        flash('Credenciales inválidas.', 'danger')
    return render_template('login.html', form=form)

@bp.route('/logout')
def logout():
    logout_user(); flash('Sesión cerrada.', 'success'); return redirect(url_for('main.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    admin_setup = (Usuario.query.count() == 0)
    if form.validate_on_submit():
        user = Usuario(username=form.username.data, email=form.email.data)
        user.rol = 1 if admin_setup else (form.rol.data if current_user.is_authenticated and current_user.is_admin() else 2)
        user.set_password(form.password.data)
        db.session.add(user); db.session.commit()
        flash('Registrado.', 'success'); return redirect(url_for('main.login'))
    return render_template('register.html', form=form, admin_setup=admin_setup)

# --- CRUD INVENTARIO ---
@bp.route('/', methods=['GET', 'POST'])
@login_required
def inventario():
    form = BusquedaForm()
    productos = Producto.query.all()
    if form.validate_on_submit():
        productos = Producto.query.filter(Producto.nombre.ilike(f'%{form.busqueda.data}%') | Producto.codigo.ilike(f'%{form.busqueda.data}%')).all()
    alertas = [p for p in productos if p.necesita_alerta()]
    return render_template('inventario.html', productos=productos, form=form, alertas=alertas)

@bp.route('/agregar', methods=['GET', 'POST'])
@bp.route('/editar/<int:producto_id>', methods=['GET', 'POST'])
@login_required
def agregar_editar(producto_id=None):
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    p = Producto.query.get_or_404(producto_id) if producto_id else None
    form = ProductoForm(obj=p)
    if form.validate_on_submit():
        try:
            if p:
                cant_ant = p.cantidad
                form.populate_obj(p)
                if p.cantidad > cant_ant:
                    img = guardar_imagen(form.imagen_ingreso.data, p.subalmacen)
                    db.session.add(Ingreso(producto_id=p.id, cantidad_agregada=p.cantidad-cant_ant, imagen_ingreso=img, usuario_id=current_user.id))
                flash('Actualizado.', 'success')
            else:
                np = Producto(); form.populate_obj(np)
                img = guardar_imagen(form.imagen_ingreso.data, np.subalmacen)
                db.session.add(np)
                db.session.add(Ingreso(producto=np, cantidad_agregada=np.cantidad, imagen_ingreso=img, usuario_id=current_user.id))
                flash('Agregado.', 'success')
            db.session.commit(); return redirect(url_for('main.inventario'))
        except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('agregar_editar.html', form=form, titulo='Editar' if producto_id else 'Nuevo')

@bp.route('/eliminar/<int:producto_id>', methods=['POST'])
@login_required
def eliminar(producto_id):
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    db.session.delete(Producto.query.get_or_404(producto_id)); db.session.commit()
    return redirect(url_for('main.inventario'))

# --- GESTIÓN DE SALIDAS ---
@bp.route('/salida', methods=['GET', 'POST'])
@login_required
def salida():
    form = SalidaForm()
    form.producto_id.choices = [(p.id, f'{p.nombre} ({p.subalmacen})') for p in Producto.query.all()]
    if form.validate_on_submit():
        prod = Producto.query.get_or_404(form.producto_id.data)
        if prod.cantidad < form.cantidad_salida.data:
            flash(f'Stock insuficiente ({prod.cantidad}).', 'danger')
        else:
            try:
                prod.cantidad -= form.cantidad_salida.data
                img = guardar_imagen(form.imagen_salida.data, prod.subalmacen)
                nueva = Salida(
                    producto_id=prod.id,
                    cantidad_salida=form.cantidad_salida.data,
                    nombre_funcionario=form.nombre_funcionario.data,
                    codigo_funcionario=form.codigo_funcionario.data,
                    precio_en_bs=prod.precio,
                    imagen_salida=img,
                    usuario_id=current_user.id
                )
                db.session.add(nueva); db.session.commit()
                flash('Salida registrada.', 'success'); return redirect(url_for('main.inventario'))
            except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('salida.html', form=form, titulo="Registrar Salida")

@bp.route('/eliminar_salida/<int:salida_id>', methods=['POST'])
@login_required
def eliminar_salida(salida_id):
    if not current_user.is_admin(): return redirect(url_for('main.reporte_salidas'))
    s = Salida.query.get_or_404(salida_id)
    p = Producto.query.get(s.producto_id)
    if p: p.cantidad += s.cantidad_salida
    db.session.delete(s); db.session.commit()
    flash('Eliminado y stock devuelto.', 'success')
    # Redirigimos al historial si la petición vino de allí, sino a reporte salidas
    if 'historial' in request.referrer:
         return redirect(url_for('main.historial'))
    return redirect(url_for('main.reporte_salidas'))

@bp.route('/editar_salida/<int:salida_id>', methods=['GET', 'POST'])
@login_required
def editar_salida(salida_id):
    if not current_user.is_admin(): return redirect(url_for('main.reporte_salidas'))
    s = Salida.query.get_or_404(salida_id)
    form = SalidaForm(obj=s)
    form.producto_id.choices = [(p.id, f'{p.nombre} ({p.subalmacen})') for p in Producto.query.all()]
    if request.method == 'GET': form.producto_id.data = s.producto_id
    if form.validate_on_submit():
        try:
            p_ant = Producto.query.get(s.producto_id)
            if p_ant: p_ant.cantidad += s.cantidad_salida
            p_new = Producto.query.get(form.producto_id.data)
            if p_new.cantidad < form.cantidad_salida.data:
                p_ant.cantidad -= s.cantidad_salida
                flash('Stock insuficiente.', 'danger'); return render_template('salida.html', form=form)
            p_new.cantidad -= form.cantidad_salida.data
            
            # Actualización manual segura
            s.producto_id = form.producto_id.data
            s.cantidad_salida = form.cantidad_salida.data
            s.nombre_funcionario = form.nombre_funcionario.data
            s.codigo_funcionario = form.codigo_funcionario.data
            s.precio_en_bs = p_new.precio
            if form.imagen_salida.data:
                img = guardar_imagen(form.imagen_salida.data, p_new.subalmacen)
                if img: s.imagen_salida = img
            
            db.session.commit(); flash('Actualizado.', 'success')
            if 'historial' in request.referrer: return redirect(url_for('main.historial'))
            return redirect(url_for('main.reporte_salidas'))
        except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('salida.html', form=form, titulo="Editar Salida")

# =================================================================
# --- HISTORIAL DE MOVIMIENTOS (KARDEX) ---
# =================================================================
def obtener_movimientos():
    """Función auxiliar para obtener y ordenar movimientos"""
    ingresos = Ingreso.query.all()
    salidas = Salida.query.all()
    movimientos = []
    
    def get_user_display(user_obj):
        if user_obj: return f"{user_obj.username} ({'Admin' if user_obj.rol==1 else 'Empleado'})"
        return "Sistema (Registro Histórico)"

    for i in ingresos:
        movimientos.append({
            'id': i.id, # Necesario para edición futura si se implementa para ingresos
            'tipo_raw': 'ingreso', # Para lógica interna
            'tipo': 'INGRESO', 
            'fecha': get_bolivia_time(i.fecha_ingreso), # APLICAMOS HORA BOLIVIA
            'producto': i.producto.nombre, 
            'codigo': i.producto.codigo, 
            'cantidad': i.cantidad_agregada, 
            'usuario_sistema': get_user_display(i.usuario), 
            'detalle': 'Compra / Actualización', 
            'color': 'success', 'icono': 'fa-arrow-down'
        })
        
    for s in salidas:
        movimientos.append({
            'id': s.id, # Necesario para los botones de editar/eliminar
            'tipo_raw': 'salida',
            'tipo': 'SALIDA', 
            'fecha': get_bolivia_time(s.fecha_salida), # APLICAMOS HORA BOLIVIA
            'producto': s.producto.nombre, 
            'codigo': s.producto.codigo, 
            'cantidad': s.cantidad_salida, 
            'usuario_sistema': get_user_display(s.usuario), 
            'detalle': f"Retirado por: {s.nombre_funcionario}", 
            'color': 'danger', 'icono': 'fa-arrow-up'
        })
    
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
    if not movs: flash('Sin datos', 'warning'); return redirect(url_for('main.historial'))
    
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

# ... (RESTO DE RUTAS DE REPORTES Y USUARIOS SE MANTIENEN IGUAL) ...

@bp.route('/exportar/excel')
@login_required
def exportar_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    try:
        df = pd.DataFrame([{'Código': p.codigo, 'Nombre': p.nombre, 'Cantidad': p.cantidad, 'Precio': p.precio, 'Total': p.total_value, 'Proveedor': p.proveedor, 'Fecha': p.fecha_ingreso.strftime('%Y-%m-%d'), 'Subalmacén': p.subalmacen, 'Unidad': p.unidad} for p in Producto.query.all()])
        output = BytesIO(); writer = pd.ExcelWriter(output, engine='xlsxwriter'); df.to_excel(writer, index=False, sheet_name='Inventario'); writer.close(); output.seek(0)
        return send_file(output, download_name='Reporte_Inventario.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True)
    except: return redirect(url_for('main.inventario'))

@bp.route('/exportar/reporte_ingresos/excel')
@login_required
def exportar_reporte_ingresos_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    df = pd.DataFrame([{'Producto': i.producto.nombre, 'Código': i.producto.codigo, 'Cantidad': i.cantidad_agregada, 'Fecha': i.fecha_ingreso.strftime('%Y-%m-%d %H:%M:%S')} for i in Ingreso.query.all()])
    output = BytesIO(); writer = pd.ExcelWriter(output, engine='xlsxwriter'); df.to_excel(writer, index=False, sheet_name='Ingresos'); writer.close(); output.seek(0)
    return send_file(output, download_name='Reporte_Ingresos.xlsx', as_attachment=True)

@bp.route('/exportar/reporte_salidas/excel')
@login_required
def exportar_reporte_salidas_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    df = pd.DataFrame([{'Funcionario': s.nombre_funcionario, 'Producto': s.producto.nombre, 'Cantidad': s.cantidad_salida, 'Fecha': s.fecha_salida.strftime('%Y-%m-%d'), 'Total': s.cantidad_salida * s.precio_en_bs} for s in Salida.query.all()])
    output = BytesIO(); writer = pd.ExcelWriter(output, engine='xlsxwriter'); df.to_excel(writer, index=False, sheet_name='Salidas'); writer.close(); output.seek(0)
    return send_file(output, download_name='Reporte_Salidas.xlsx', as_attachment=True)

@bp.route('/exportar/reporte_por_item/excel')
@login_required
def exportar_reporte_por_item_excel(): return exportar_reporte_salidas_excel()

@bp.route('/exportar/reporte_por_subalmacen/excel')
@login_required
def exportar_reporte_por_subalmacen_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    datos = []
    for sub in ['SCPE', 'POZO 57']:
        for p in Producto.query.filter_by(subalmacen=sub).all():
            datos.append({'Subalmacén': sub, 'Código': p.codigo, 'Nombre': p.nombre, 'Cantidad': p.cantidad, 'Total': p.total_value})
    df = pd.DataFrame(datos); output = BytesIO(); writer = pd.ExcelWriter(output, engine='xlsxwriter'); df.to_excel(writer, index=False, sheet_name='Por_Subalmacen'); writer.close(); output.seek(0)
    return send_file(output, download_name='Reporte_Por_Subalmacen.xlsx', as_attachment=True)

@bp.route('/exportar/pdf')
@login_required
def exportar_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    productos = Producto.query.all()
    buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm)
    Story = []
    data = [["Código", "Nombre", "Cant.", "Precio", "Total", "Subalm.", "Prov."]]
    for p in productos: data.append([p.codigo, Paragraph(p.nombre, getSampleStyleSheet()['Normal']), f"{p.cantidad:.1f}", f"{p.precio:.0f}", f"{p.total_value:.0f}", p.subalmacen, Paragraph(p.proveedor or '', getSampleStyleSheet()['Normal'])])
    t = Table(data, colWidths=[2.5*cm, 8*cm, 1.5*cm, 2*cm, 2*cm, 2.5*cm, 4*cm])
    t.setStyle(get_professional_table_style())
    apply_zebra_striping(t, data)
    Story.append(t)
    doc.build(Story, onFirstPage=_header_footer_general, onLaterPages=_header_footer_general)
    buffer.seek(0); return send_file(buffer, download_name='Reporte_General.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_ingresos/pdf')
@login_required
def exportar_reporte_ingresos_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    ingresos = Ingreso.query.all()
    if not ingresos: flash('Sin datos', 'warning'); return redirect(url_for('main.inventario'))
    reporte = defaultdict(list)
    for i in ingresos: reporte[i.producto.nombre].append(i)
    buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm); Story = []
    styles = getSampleStyleSheet()
    for producto, lista in reporte.items():
        Story.append(Paragraph(f"Producto: {producto}", styles['h3']))
        data = [["Cantidad", "Fecha Ingreso"]]; total = 0
        for i in lista: data.append([f"{i.cantidad_agregada:.2f}", i.fecha_ingreso.strftime('%d/%m/%Y %H:%M')]); total += i.cantidad_agregada
        data.append([f"TOTAL: {total:.2f}", ""])
        t = Table(data, colWidths=[4*cm, 6*cm]); t.setStyle(get_professional_table_style()); apply_zebra_striping(t, data)
        Story.append(t); Story.append(Spacer(1, 0.5*cm))
    doc.build(Story, onFirstPage=_header_footer_ingresos, onLaterPages=_header_footer_ingresos)
    buffer.seek(0); return send_file(buffer, download_name='Reporte_Ingresos.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_salidas/pdf')
@login_required
def exportar_reporte_salidas_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    salidas = Salida.query.all()
    if not salidas: flash('Sin datos', 'warning'); return redirect(url_for('main.inventario'))
    reporte = defaultdict(list)
    for s in salidas: reporte[s.nombre_funcionario].append(s)
    buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm); Story = []
    styles = getSampleStyleSheet()
    for func, lista in reporte.items():
        Story.append(Paragraph(f"Funcionario: {func}", styles['h3']))
        data = [["Producto", "Cant.", "Fecha", "Precio U.", "Total"]]
        total_bs = 0
        for s in lista: 
            tot = s.cantidad_salida*s.precio_en_bs; total_bs += tot
            data.append([Paragraph(s.producto.nombre, styles['Normal']), f"{s.cantidad_salida:.2f}", s.fecha_salida.strftime('%d/%m/%Y'), f"{s.precio_en_bs:.2f}", f"{tot:.2f}"])
        data.append(["", "", "", "TOTAL BS:", f"{total_bs:.2f}"])
        t = Table(data, colWidths=[10*cm, 2.5*cm, 3*cm, 2.5*cm, 3*cm]); t.setStyle(get_professional_table_style()); apply_zebra_striping(t, data)
        Story.append(t); Story.append(Spacer(1, 0.5*cm))
    doc.build(Story, onFirstPage=_header_footer_salidas, onLaterPages=_header_footer_salidas)
    buffer.seek(0); return send_file(buffer, download_name='Reporte_Salidas.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_por_item/pdf')
@login_required
def exportar_reporte_por_item_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    salidas = Salida.query.all(); reporte = defaultdict(list)
    for s in salidas: reporte[s.producto.nombre].append(s)
    buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm); Story = []
    styles = getSampleStyleSheet()
    for prod, lista in reporte.items():
        Story.append(Paragraph(f"Producto: {prod}", styles['h3']))
        data = [["Funcionario", "Cant.", "Fecha", "Total"]]
        total_cant = 0
        for s in lista: 
            data.append([s.nombre_funcionario, f"{s.cantidad_salida:.2f}", s.fecha_salida.strftime('%d/%m/%Y'), f"{(s.cantidad_salida*s.precio_en_bs):.2f}"]); total_cant += s.cantidad_salida
        data.append(["TOTAL CANTIDAD:", f"{total_cant:.2f}", "", ""])
        t = Table(data, colWidths=[8*cm, 3*cm, 4*cm, 4*cm]); t.setStyle(get_professional_table_style()); apply_zebra_striping(t, data)
        Story.append(t); Story.append(Spacer(1, 0.5*cm))
    doc.build(Story, onFirstPage=_header_footer_por_item, onLaterPages=_header_footer_por_item)
    buffer.seek(0); return send_file(buffer, download_name='Reporte_Por_Item.pdf', mimetype='application/pdf', as_attachment=True)

@bp.route('/exportar/reporte_por_subalmacen/pdf')
@login_required
def exportar_reporte_por_subalmacen_pdf():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = {}
    for sub in ['SCPE', 'POZO 57']: reporte[sub] = Producto.query.filter_by(subalmacen=sub).all()
    buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=2*cm, rightMargin=2*cm, topMargin=3.5*cm, bottomMargin=2.5*cm); Story = []
    styles = getSampleStyleSheet()
    for sub, lista in reporte.items():
        if not lista: continue
        Story.append(Paragraph(f"Subalmacén: {sub}", styles['h3']))
        data = [["Código", "Nombre", "Cant.", "Precio", "Total"]]
        total_val = 0
        for p in lista: 
            data.append([p.codigo, Paragraph(p.nombre, styles['Normal']), f"{p.cantidad:.2f}", f"{p.precio:.2f}", f"{p.total_value:.2f}"]); total_val += p.total_value
        data.append(["", "", "", "TOTAL VALOR:", f"{total_val:.2f}"])
        t = Table(data, colWidths=[3*cm, 10*cm, 3*cm, 3*cm, 4*cm]); t.setStyle(get_professional_table_style()); apply_zebra_striping(t, data)
        Story.append(t); Story.append(Spacer(1, 0.5*cm))
    doc.build(Story, onFirstPage=_header_footer_por_subalmacen, onLaterPages=_header_footer_por_subalmacen)
    buffer.seek(0); return send_file(buffer, download_name='Reporte_Por_Subalmacen.pdf', mimetype='application/pdf', as_attachment=True)

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
    top = db.session.query(Salida.producto_id, func.sum(Salida.cantidad_salida).label('total')).group_by(Salida.producto_id).order_by(func.sum(Salida.cantidad_salida).desc()).limit(10).all()
    prods = []
    for t in top:
        p = Producto.query.get(t.producto_id)
        if p: p.total_salida = t.total; prods.append(p)
    return render_template('reporte_top_productos.html', productos=prods, tipo='salidos')

@bp.route('/reporte_por_subalmacen')
@login_required
def reporte_por_subalmacen():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    reporte = {}
    for sub in ['SCPE', 'POZO 57']:
        ps = Producto.query.filter_by(subalmacen=sub).all()
        reporte[sub] = {'productos': ps, 'total_value': sum(p.total_value for p in ps)}
    return render_template('reporte_por_subalmacen.html', reporte=reporte)

@bp.route('/importar/excel', methods=['GET', 'POST'])
@login_required
def importar_excel():
    if not current_user.is_admin(): return redirect(url_for('main.inventario'))
    form = ImportForm()
    if form.validate_on_submit():
        file = form.file.data
        if not file.filename.endswith('.xlsx'): flash('Debe ser Excel (.xlsx)', 'danger'); return redirect(request.url)
        try:
            df = pd.read_excel(file); count = 0; errors = []
            for idx, row in df.iterrows():
                if pd.isna(row.get('Código')): continue
                if not Producto.query.filter_by(codigo=str(row['Código'])).first():
                    db.session.add(Producto(codigo=str(row['Código']), nombre=str(row['Nombre']), cantidad=float(row['Cantidad']), precio=float(row['Precio']), subalmacen=str(row['Subalmacén']), unidad=str(row['Unidad'])))
                    count += 1
            db.session.commit(); flash(f'Importados: {count}', 'success')
        except Exception as e: flash(f'Error: {e}', 'danger')
    return render_template('importar.html', form=form)

@bp.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.rol != 1: return redirect(url_for('main.index'))
    form = RegistroUsuarioForm()
    users = Usuario.query.all(); edit_user = None
    if request.method == 'POST' and 'action' in request.form:
        uid = request.form.get('user_id')
        if request.form.get('action') == 'delete':
            u = Usuario.query.get(uid)
            if u and (u.rol != 1 or Usuario.query.filter_by(rol=1).count() > 1):
                db.session.delete(u); db.session.commit(); flash('Eliminado', 'success')
            return redirect(url_for('main.manage_users'))
        elif request.form.get('action') == 'edit':
            u = Usuario.query.get(uid)
            if u: edit_user = u; form.username.data = u.username; form.email.data = u.email; form.rol.data = str(u.rol)
    if request.method == 'POST' and request.form.get('user_id_edit'):
        if not form.password.data:
            form.password.validators = [v for v in form.password.validators if not isinstance(v, DataRequired)]
            form.confirm_password.validators = [v for v in form.confirm_password.validators if not isinstance(v, DataRequired)]
    if form.validate_on_submit():
        uid_edit = request.form.get('user_id_edit')
        if uid_edit:
            u = Usuario.query.get(uid_edit)
            if u:
                u.username = form.username.data; u.email = form.email.data; u.rol = int(form.rol.data)
                if form.password.data: u.set_password(form.password.data)
                db.session.commit(); flash('Actualizado', 'success'); return redirect(url_for('main.manage_users'))
        else:
            nu = Usuario(username=form.username.data, email=form.email.data, rol=int(form.rol.data))
            nu.set_password(form.password.data); db.session.add(nu); db.session.commit()
            flash('Creado', 'success'); return redirect(url_for('main.manage_users'))
    return render_template('manage_users.html', form=form, users=users, edit_user=edit_user)