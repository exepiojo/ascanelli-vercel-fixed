# - Sección 1: Configuraciones e Importaciones---------------------------------------------------------

import os
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy import func # Agrega esto arriba
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Usar SECRET_KEY desde variables de entorno o generar una por defecto
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ascanelli_secret_key_123')

# Configuración para Vercel/serverless
if os.environ.get('VERCEL'):
    app.config['DEBUG'] = False
    app.config['TESTING'] = False

# Deshabilitar caché para desarrollo
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Base de datos: SQLite local para desarrollo, Neon/Supabase para producción
database_url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL')

if database_url:
    # Producción: Neon.tech o Supabase
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print(f"✅ Conectando a base de datos en la nube (Producción)")
    print(f"🔗 URL: {database_url[:50]}...")
else:
    # Desarrollo local: SQLite
    instance_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    os.makedirs(instance_folder, exist_ok=True)
    db_path = os.path.join(instance_folder, 'ascanelli.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    print("📁 Conectando a SQLite (Desarrollo Local)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para acceder a esta página.'
login_manager.login_message_category = 'info'

# ---- Sección 2: Modelos de Base de Datos ---------------------------------------------------------

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    legajo = db.Column(db.String(10), unique=True, nullable=False)  # Antes 'pin', ahora es legajo público
    pin_secreto = db.Column(db.String(10), nullable=False)  # Nuevo campo: PIN secreto personal
    nombre = db.Column(db.String(100), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    rol = db.Column(db.String(50), default='OPERARIO')  # ADMIN, VENTAS, PCP, CALIDAD, HYS, OPERARIO, MANDO_MEDIO

class PlanProduccion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(50))
    implemento = db.Column(db.String(100))
    sector = db.Column(db.String(50))
    puesto_conjunto = db.Column(db.String(50))
    nro_chasis = db.Column(db.String(50), nullable=False) # IMPORTANTE: Sin unique=True
    estado = db.Column(db.String(20), default='PENDIENTE')
    usuario_avance = db.Column(db.String(100)) # Guarda el nombre del legajo
    
    # Todas estas deben ser nullable=True porque no vienen en el Excel
    hora_fin = db.Column(db.DateTime, nullable=True)
    ubicacion_celda = db.Column(db.String(50), nullable=True)
    fecha_despacho = db.Column(db.String(50), nullable=True)
    observaciones_despacho = db.Column(db.Text, nullable=True)
    fotos_despacho = db.Column(db.String(200), nullable=True)
    # Nuevo: fecha en que se ubicó en playón y flags
    fecha_playon = db.Column(db.DateTime, nullable=True)
    cubiertas = db.Column(db.Boolean, default=False)
    con_cliente = db.Column(db.Boolean, default=False)
    
    # Relación con Calidad
    novedades = db.relationship('NovedadCalidad', backref='chasis', lazy=True)

class AlertaCalidad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))
    descripcion = db.Column(db.Text, nullable=False)
    imagen = db.Column(db.String(200)) # Nombre del archivo
    fecha = db.Column(db.DateTime, default=datetime.now)
    usuario = db.Column(db.String(100))
    sector = db.Column(db.String(50))
    
    # Relación con PlanProduccion
    plan = db.relationship('PlanProduccion', backref='alertas_calidad')


class NovedadCalidad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    puesto = db.Column(db.String(50))
    descripcion = db.Column(db.Text, nullable=False)
    foto_novedad = db.Column(db.String(100), nullable=True)
    fecha_deteccion = db.Column(db.DateTime, default=datetime.now)

# --- Sección 2.1: Checklists y Auditorías Digitales -----------------------------------------
class ChecklistTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50))  # 'AUDITORIA', 'CALIDAD', 'SEGURIDAD', 'PROCESO'
    sector = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    frecuencia = db.Column(db.String(20))  # 'DIARIO', 'SEMANAL', 'MENSUAL', 'ANUAL'
    estado = db.Column(db.String(20), default='ACTIVO')  # ACTIVO, INACTIVO
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    items = db.relationship('ChecklistItem', backref='template', lazy=True, cascade="all, delete-orphan")
    auditorias = db.relationship('AuditoriaRealizada', backref='template', lazy=True)

class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    tipo_respuesta = db.Column(db.String(20))  # 'SI/NO', 'TEXTO', 'FOTO', 'NUMERICO', 'MULTIPLE'
    obligatorio = db.Column(db.Boolean, default=True)
    orden = db.Column(db.Integer, default=0)
    puntos = db.Column(db.Integer, default=0)  # Para scoring
    referencia = db.Column(db.String(200))  # Link a documento o procedimiento

class AuditoriaRealizada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=True)
    auditor = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    estado = db.Column(db.String(20), default='EN_PROGRESO')  # EN_PROGRESO, APROBADO, RECHAZADO, CERRADO
    puntaje_total = db.Column(db.Integer, default=0)
    puntaje_obtenido = db.Column(db.Integer, default=0)
    porcentaje_cumplimiento = db.Column(db.Float, default=0.0)
    observaciones_generales = db.Column(db.Text)
    tiempo_inicio = db.Column(db.DateTime)
    tiempo_fin = db.Column(db.DateTime)
    respuestas = db.relationship('RespuestaAuditoria', backref='auditoria', lazy=True, cascade="all, delete-orphan")
    no_conformidades = db.relationship('NoConformidad', backref='auditoria_rel', lazy=True)

class RespuestaAuditoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    auditoria_id = db.Column(db.Integer, db.ForeignKey('auditoria_realizada.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('checklist_item.id'), nullable=False)
    respuesta = db.Column(db.Text)
    respuesta_si_no = db.Column(db.Boolean)  # Para tipo SI/NO
    respuesta_numerica = db.Column(db.Float)  # Para tipo NUMERICO
    evidencia_foto = db.Column(db.String(200))  # Nombre archivo
    observaciones = db.Column(db.Text)
    cumple = db.Column(db.Boolean, default=True)  # Si cumple o no con el requisito
    fecha_respuesta = db.Column(db.DateTime, default=datetime.now)

# --- Sección 2.2: No Conformidades y Acciones Correctivas (CAPA) -----------------------------
class NoConformidad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # NC-2026-001
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=True)
    auditoria_id = db.Column(db.Integer, db.ForeignKey('auditoria_realizada.id'), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    gravedad = db.Column(db.String(20), nullable=False)  # 'LEVE', 'MODERADO', 'GRAVE', 'CRITICO'
    tipo = db.Column(db.String(30))  # 'PRODUCTO', 'PROCESO', 'DOCUMENTO', 'SEGURIDAD'
    estado = db.Column(db.String(20), default='ABIERTA')  # ABIERTA, EN_ANALISIS, EN_PROCESO, VERIFICACION, CERRADA
    fuente_deteccion = db.Column(db.String(50))  # 'AUDITORIA', 'INSPECCION', 'QUEJA', 'RECLAMO'
    fecha_deteccion = db.Column(db.DateTime, default=datetime.now)
    fecha_limite_analisis = db.Column(db.DateTime)
    fecha_cierre = db.Column(db.DateTime)
    detectado_por = db.Column(db.String(100), nullable=False)
    responsable_analisis = db.Column(db.String(100))
    sector = db.Column(db.String(50))
    impacto = db.Column(db.Text)  # Descripción del impacto
    evidencia_inicial = db.Column(db.String(200))  # Nombre archivo
    acciones = db.relationship('AccionCorrectiva', backref='no_conformidad', lazy=True, cascade="all, delete-orphan")
    verificaciones = db.relationship('VerificacionNC', backref='no_conformidad', lazy=True)

class AccionCorrectiva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nc_id = db.Column(db.Integer, db.ForeignKey('no_conformidad.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'CORRECTIVA', 'PREVENTIVA', 'MEJORA'
    descripcion = db.Column(db.Text, nullable=False)
    responsable = db.Column(db.String(100), nullable=False)
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    fecha_limite = db.Column(db.DateTime, nullable=False)
    fecha_cierre = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default='PENDIENTE')  # PENDIENTE, EN_PROGRESO, COMPLETADA, VERIFICADA
    prioridad = db.Column(db.String(20), default='MEDIA')  # 'BAJA', 'MEDIA', 'ALTA', 'URGENTE'
    recursos_necesarios = db.Column(db.Text)
    evidencia_antes = db.Column(db.String(200))  # Nombre archivo
    evidencia_despues = db.Column(db.String(200))  # Nombre archivo
    costo_estimado = db.Column(db.Float)
    costo_real = db.Column(db.Float)
    efectividad = db.Column(db.Text)  # Descripción de la efectividad
    verificaciones = db.relationship('VerificacionAccion', backref='accion', lazy=True)

class VerificacionNC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nc_id = db.Column(db.Integer, db.ForeignKey('no_conformidad.id'), nullable=False)
    verificador = db.Column(db.String(100), nullable=False)
    fecha_verificacion = db.Column(db.DateTime, default=datetime.now)
    resultado = db.Column(db.String(20), nullable=False)  # 'CUMPLE', 'NO_CUMPLE', 'PARCIAL'
    observaciones = db.Column(db.Text)
    evidencia = db.Column(db.String(200))  # Nombre archivo
    efectividad_comprobada = db.Column(db.Boolean, default=False)

class VerificacionAccion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accion_id = db.Column(db.Integer, db.ForeignKey('accion_correctiva.id'), nullable=False)
    verificador = db.Column(db.String(100), nullable=False)
    fecha_verificacion = db.Column(db.DateTime, default=datetime.now)
    resultado = db.Column(db.String(20), nullable=False)  # 'EFECTIVA', 'PARCIAL', 'NO_EFECTIVA'
    observaciones = db.Column(db.Text)
    evidencia = db.Column(db.String(200))  # Nombre archivo

# --- Sección 2.3: Control Documental --------------------------------------------------------
class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)  # POE-001, PRO-002, REG-003
    titulo = db.Column(db.String(200), nullable=False)
    version = db.Column(db.String(10), nullable=False)  # v1.0, v2.0
    tipo = db.Column(db.String(50), nullable=False)  # 'POE', 'PROCESO', 'REGISTRO', 'FORMATO', 'MANUAL'
    categoria = db.Column(db.String(50))  # 'CALIDAD', 'SEGURIDAD', 'PRODUCCION', 'MANTENIMIENTO'
    sector = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    archivo = db.Column(db.String(200))  # Nombre archivo PDF
    ruta_fisica = db.Column(db.String(300))  # Ruta completa al archivo
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    fecha_vigencia = db.Column(db.DateTime)
    fecha_revision = db.Column(db.DateTime)
    proxima_revision = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default='BORRADOR')  # BORRADOR, REVISION, APROBADO, VIGENTE, OBSOLETO
    aprobado_por = db.Column(db.String(100))
    revisado_por = db.Column(db.String(100))
    creado_por = db.Column(db.String(100))
    obligatorio = db.Column(db.Boolean, default=False)
    distribucion = db.Column(db.Text)  # Lista de sectores/personas que deben recibirlo
    control_cambios = db.relationship('CambioDocumento', backref='documento', lazy=True, cascade="all, delete-orphan")
    capacitaciones = db.relationship('CapacitacionDocumento', backref='documento', lazy=True)

class CambioDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey('documento.id'), nullable=False)
    version_anterior = db.Column(db.String(10))
    version_nueva = db.Column(db.String(10))
    fecha_cambio = db.Column(db.DateTime, default=datetime.now)
    motivo_cambio = db.Column(db.Text, nullable=False)
    cambiado_por = db.Column(db.String(100))
    aprobado_por = db.Column(db.String(100))
    descripcion_cambios = db.Column(db.Text)

class CapacitacionDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey('documento.id'), nullable=False)
    persona = db.Column(db.String(100), nullable=False)
    sector = db.Column(db.String(50))
    fecha_capacitacion = db.Column(db.DateTime)
    metodo = db.Column(db.String(50))  # 'PRESENCIAL', 'ONLINE', 'AUTOFORMACION'
    estado = db.Column(db.String(20), default='PENDIENTE')  # PENDIENTE, REALIZADA, VENCIDA
    evidencia = db.Column(db.String(200))  # Nombre archivo firma/certificado
    proxima_refrescada = db.Column(db.DateTime)

# --- Sección 2.4: KPIs y Métricas de Calidad ------------------------------------------------
class IndicadorCalidad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # KPI-001
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    categoria = db.Column(db.String(50))  # 'CALIDAD', 'PRODUCCION', 'SEGURIDAD', 'SATISFACCION'
    formula = db.Column(db.String(200), nullable=False)  # Ej: '(rechazos / total) * 100'
    unidad = db.Column(db.String(20))  # '%', 'unidades', 'horas', 'dias'
    objetivo = db.Column(db.Float)
    minimo_aceptable = db.Column(db.Float)
    frecuencia = db.Column(db.String(20))  # 'DIARIO', 'SEMANAL', 'MENSUAL', 'TRIMESTRAL'
    responsable = db.Column(db.String(100))
    estado = db.Column(db.String(20), default='ACTIVO')  # ACTIVO, INACTIVO
    fuente_datos = db.Column(db.String(100))  # 'PRODUCCION', 'CALIDAD', 'RECURSOS_HUMANOS'
    grafico_tipo = db.Column(db.String(20))  # 'LINEA', 'BARRAS', 'CIRCULAR'
    mediciones = db.relationship('MedicionKPI', backref='kpi', lazy=True, cascade="all, delete-orphan")
    alertas = db.relationship('AlertaKPI', backref='kpi', lazy=True, cascade="all, delete-orphan")

class MedicionKPI(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey('indicador_calidad.id'), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    valor_objetivo = db.Column(db.Float)
    fecha = db.Column(db.DateTime, default=datetime.now)
    periodo = db.Column(db.String(20))  # '2026-02', 'SEMANA-6', 'Q1-2026'
    fuente = db.Column(db.String(100))
    comentarios = db.Column(db.Text)
    registrado_por = db.Column(db.String(100))
    cumplimiento = db.Column(db.Boolean)  # True si cumple objetivo

class AlertaKPI(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kpi_id = db.Column(db.Integer, db.ForeignKey('indicador_calidad.id'), nullable=False)
    tipo_alerta = db.Column(db.String(20))  # 'UMBRAL_SUPERIOR', 'UMBRAL_INFERIOR', 'TENDENCIA'
    valor_limite = db.Column(db.Float)
    condicion = db.Column(db.String(10))  # '>', '<', '=', '>='
    mensaje = db.Column(db.Text)
    destinatarios = db.Column(db.Text)  # Emails separados por coma
    estado = db.Column(db.String(20), default='ACTIVA')  # ACTIVA, INACTIVA
    ultima_notificacion = db.Column(db.DateTime)

# --- Sección 2.5: Sistema de Notificaciones -------------------------------------------------
class Notificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # 'VENCIMIENTO', 'NC_CRITICA', 'AUDITORIA', 'DOCUMENTO', 'KPI'
    prioridad = db.Column(db.String(20), default='MEDIA')  # 'BAJA', 'MEDIA', 'ALTA', 'URGENTE'
    destinatario = db.Column(db.String(100))  # Usuario específico
    sector_destino = db.Column(db.String(50))  # Todo el sector
    rol_destino = db.Column(db.String(50))  # 'ADMIN', 'OPERARIO', 'SUPERVISOR'
    fecha_envio = db.Column(db.DateTime, default=datetime.now)
    fecha_vencimiento = db.Column(db.DateTime)
    leida = db.Column(db.Boolean, default=False)
    fecha_lectura = db.Column(db.DateTime)
    link_accion = db.Column(db.String(300))  # URL para acción directa
    icono = db.Column(db.String(50))  # 'warning', 'info', 'success', 'error'
    color = db.Column(db.String(20))  # 'red', 'yellow', 'green', 'blue'
    referencia_id = db.Column(db.Integer)  # ID del objeto relacionado
    referencia_tipo = db.Column(db.String(50))  # 'NC', 'DOCUMENTO', 'AUDITORIA', 'KPI'
    creado_por = db.Column(db.String(100))
    repetir = db.Column(db.Boolean, default=False)
    frecuencia_repeticion = db.Column(db.String(20))  # 'DIARIO', 'SEMANAL', 'MENSUAL'

# --- Sección 2.6: Higiene y Seguridad Industrial (H&S) -----------------------------------------
class IncidenteHYS(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # HYS-2026-001
    tipo_incidente = db.Column(db.String(50), nullable=False)  # 'CASI_ACCIDENTE', 'CONDICION_INSEGURA', 'ACTO_INSEGURO', 'INCIDENTE_LEVE'
    sector = db.Column(db.String(50), nullable=False)  # 'SOLDADURA', 'PINTURA', 'MONTAJE', 'ALMACEN'
    ubicacion_especifica = db.Column(db.String(100))  # 'P1', 'ZONA CARGA', 'AREA PINTURA'
    descripcion = db.Column(db.Text, nullable=False)
    fecha_reporte = db.Column(db.DateTime, default=datetime.now)
    reportado_por = db.Column(db.String(100), nullable=False)
    legajo_reportante = db.Column(db.String(20))
    gravedad = db.Column(db.String(20), default='MEDIO')  # 'BAJO', 'MEDIO', 'ALTO', 'CRITICO'
    estado = db.Column(db.String(20), default='ABIERTO')  # 'ABIERTO', 'EN_INVESTIGACION', 'RESUELTO', 'CERRADO'
    fecha_investigacion = db.Column(db.DateTime)
    investigador = db.Column(db.String(100))
    acciones_tomadas = db.Column(db.Text)
    fecha_resolucion = db.Column(db.DateTime)
    evidencia_fotos = db.Column(db.String(500))  # JSON con nombres de archivos
    audio_descripcion = db.Column(db.String(200))  # Nombre del archivo de audio
    latitud = db.Column(db.Float)  # Geolocalización interna
    longitud = db.Column(db.Float)  # Geolocalización interna
    notificado_supervisor = db.Column(db.Boolean, default=False)
    notificado_seguridad = db.Column(db.Boolean, default=False)

class ChecklistEPP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    sector = db.Column(db.String(50))
    gafas = db.Column(db.Boolean, default=False)
    botines = db.Column(db.Boolean, default=False)
    guantes = db.Column(db.Boolean, default=False)
    proteccion_auditiva = db.Column(db.Boolean, default=False)
    casco = db.Column(db.Boolean, default=False)
    mascara_pintura = db.Column(db.Boolean, default=False)
    arnes = db.Column(db.Boolean, default=False)
    otros_epp = db.Column(db.Text)  # Descripción de EPP adicionales
    observaciones = db.Column(db.Text)
    cumplimiento_total = db.Column(db.Boolean, default=False)  # True si todos los requeridos están marcados
    verificado_por = db.Column(db.String(100))
    
    # Relación con Usuario
    usuario = db.relationship('Usuario', backref='checklists_epp')

class SolicitudEPP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # EPP-2026-001
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_solicitud = db.Column(db.DateTime, default=datetime.now)
    sector = db.Column(db.String(50), nullable=False)
    tipo_epp = db.Column(db.String(100), nullable=False)  # 'GUANTES', 'FILTROS_MASCARA', 'BOTINES', 'GAFAS', 'CASCO'
    descripcion = db.Column(db.Text, nullable=False)
    motivo_solicitud = db.Column(db.String(200))  # 'DESGASTE', 'DAÑO', 'PERDIDA', 'TALLA_INCORRECTA'
    urgencia = db.Column(db.String(20), default='NORMAL')  # 'BAJA', 'NORMAL', 'ALTA', 'URGENTE'
    cantidad_solicitada = db.Column(db.Integer, default=1)
    cantidad_entregada = db.Column(db.Integer, default=0)
    estado = db.Column(db.String(20), default='PENDIENTE')  # 'PENDIENTE', 'APROBADA', 'COMPRADA', 'ENTREGADA', 'RECHAZADA'
    fecha_aprobacion = db.Column(db.DateTime)
    aprobado_por = db.Column(db.String(100))
    fecha_entrega = db.Column(db.DateTime)
    entregado_por = db.Column(db.String(100))
    observaciones = db.Column(db.Text)
    
    # Relación con Usuario
    solicitante = db.relationship('Usuario', backref='solicitudes_epp')

class FichaSeguridadMaquinaria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo_maquina = db.Column(db.String(50), unique=True, nullable=False)  # Código único o QR
    nombre_maquina = db.Column(db.String(100), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    tipo_maquina = db.Column(db.String(50))  # 'PLEGADORA', 'ROBOT_SOLDADURA', 'TALADRO', 'SIERRA'
    fabricante = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(100))
    fecha_instalacion = db.Column(db.DateTime)
    fecha_ultimo_mantenimiento = db.Column(db.DateTime)
    proximo_mantenimiento = db.Column(db.DateTime)
    responsable_mantenimiento = db.Column(db.String(100))
    
    # Puntos de seguridad críticos
    puntos_atrapamiento = db.Column(db.Text)  # JSON con ubicaciones
    boton_parada_emergencia = db.Column(db.Text)  # JSON con ubicaciones
    protecciones_necesarias = db.Column(db.Text)  # Guardas, carcasas, etc.
    riesgos_principales = db.Column(db.Text)  # Atrapamiento, corte, eléctrico, etc.
    
    # Documentación
    manual_seguridad = db.Column(db.String(200))  # Nombre del archivo PDF
    checklist_diario = db.Column(db.String(200))  # Nombre del archivo
    procedimiento_emergencia = db.Column(db.String(200))  # Nombre del archivo
    
    estado = db.Column(db.String(20), default='ACTIVA')  # 'ACTIVA', 'MANTENIMIENTO', 'DESACTIVADA'
    ultima_inspeccion = db.Column(db.DateTime)
    inspector = db.Column(db.String(100))

class ZonaRiesgo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_zona = db.Column(db.String(100), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    tipo_riesgo = db.Column(db.String(30), nullable=False)  # 'ALTO', 'MEDIO', 'BAJO'
    descripcion_riesgos = db.Column(db.Text)  # Descripción de riesgos específicos
    medidas_control = db.Column(db.Text)  # Medidas de control implementadas
    coordenadas = db.Column(db.String(100))  # Coordenadas para el mapa
    area_delimitada = db.Column(db.Text)  # JSON con polígono del área
    
    # Restricciones y alertas
    requiere_epp_especial = db.Column(db.Boolean, default=False)
    epp_requerido = db.Column(db.Text)  # Lista de EPP específicos
    requiere_permiso = db.Column(db.Boolean, default=False)
    responsable_zona = db.Column(db.String(100))
    
    estado = db.Column(db.String(20), default='ACTIVA')  # 'ACTIVA', 'RESTRINGIDA', 'MANTENIMIENTO'
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.now)
    actualizado_por = db.Column(db.String(100))

class ContactoEmergencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo_contacto = db.Column(db.String(50), nullable=False)  # 'MEDICA', 'BOMBEROS', 'SEGURIDAD', 'RESCATE'
    nombre_contacto = db.Column(db.String(100), nullable=False)
    telefono_interno = db.Column(db.String(20))
    telefono_externo = db.Column(db.String(20))
    extension = db.Column(db.String(10))
    email = db.Column(db.String(100))
    sector_responsabilidad = db.Column(db.String(50))
    disponible_24hs = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(20), default='ACTIVO')  # 'ACTIVO', 'INACTIVO'
    orden_prioridad = db.Column(db.Integer, default=1)  # Orden en que se muestra
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # 'VENCIMIENTO', 'NC_CRITICA', 'AUDITORIA', 'DOCUMENTO', 'KPI'
    prioridad = db.Column(db.String(20), default='MEDIA')  # 'BAJA', 'MEDIA', 'ALTA', 'URGENTE'
    destinatario = db.Column(db.String(100))  # Usuario específico
    sector_destino = db.Column(db.String(50))  # Todo el sector
    rol_destino = db.Column(db.String(50))  # 'ADMIN', 'OPERARIO', 'SUPERVISOR'
    fecha_envio = db.Column(db.DateTime, default=datetime.now)
    fecha_vencimiento = db.Column(db.DateTime)
    leida = db.Column(db.Boolean, default=False)
    fecha_lectura = db.Column(db.DateTime)
    link_accion = db.Column(db.String(300))  # URL para acción directa
    icono = db.Column(db.String(50))  # 'warning', 'info', 'success', 'error'
    color = db.Column(db.String(20))  # 'red', 'yellow', 'green', 'blue'
    referencia_id = db.Column(db.Integer)  # ID del objeto relacionado
    referencia_tipo = db.Column(db.String(50))  # 'NC', 'DOCUMENTO', 'AUDITORIA', 'KPI'
    creado_por = db.Column(db.String(100))
    repetir = db.Column(db.Boolean, default=False)
    frecuencia_repeticion = db.Column(db.String(20))  # 'DIARIO', 'SEMANAL', 'MENSUAL'

class ConfiguracionNotificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), nullable=False)
    tipo_notificacion = db.Column(db.String(50), nullable=False)
    email_activo = db.Column(db.Boolean, default=True)
    sistema_activo = db.Column(db.Boolean, default=True)
    frecuencia = db.Column(db.String(20))  # 'INMEDIATA', 'DIARIA', 'SEMANAL'
    ultima_envio = db.Column(db.DateTime)

class CeldaPlayon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(10), unique=True, nullable=False) # Ej: 'A-1'
    estado = db.Column(db.String(20), default='LIBRE') # LIBRE / OCUPADO
    chasis_id = db.Column(db.Integer, nullable=True) # ID del plan que está estacionado aquí

# --- Sección 2.7: Planilla de Producción y Gestión de Chasis ------------------------------------
class ChasisAsignadoTolva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    nro_chasis = db.Column(db.String(50), nullable=False)  # Relación con plan_produccion.nro_chasis
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    
    # --- DATOS BÁSICOS TOLVA ---
    lanzamiento = db.Column(db.String(50))  # LANZAMIENTO (texto libre)
    modelo = db.Column(db.String(100))      # MODELO (texto libre)
    cliente = db.Column(db.String(200))    # CLIENTE (texto libre)
    tubo = db.Column(db.String(50))         # TUBO (texto libre)
    encamisado = db.Column(db.String(50))  # ENCAMISADO (texto libre)
    tipo_tubo = db.Column(db.String(50))   # TIPO TUBO (texto libre)
    tamano_cubierta = db.Column(db.String(50))  # TAMAÑO DE CUBIERTA (texto libre)
    marca_cubiertas = db.Column(db.String(100))  # MARCA DE LAS CUBIERTAS (texto libre)
    color = db.Column(db.String(50))        # COLOR (texto libre)
    balanza = db.Column(db.String(50))      # BALANZA (texto libre)
    observaciones = db.Column(db.Text)      # OBSERVACIONES

    # --- ENTREGA Y VENTAS ---
    entregada = db.Column(db.String(20))    # Entregada (texto libre)
    fecha_entrega = db.Column(db.String(50))  # Fecha de Entrega (texto libre)
    pedido = db.Column(db.String(100))      # Pedido (texto libre)
    liberada_ventas = db.Column(db.String(20))  # Liberada para VENTAS (texto libre)
    llantas_ok = db.Column(db.String(20))    # Llantas OK (texto libre)
    cubiertas_ok = db.Column(db.String(20))  # Cubiertas OK (texto libre)
    observaciones_2 = db.Column(db.Text)      # OBSERVACIÓN 2
    proveedor_sinfin = db.Column(db.String(100))  # PROVEEDOR DE SIN FIN (texto libre)
    dias_consignacion = db.Column(db.String(20))  # DIAS EN CONSIGNACION DESDE SU ENTREGA (texto libre)

    # --- RELACIONES ---
    plan = db.relationship('PlanProduccion', backref='chasis_asignado_tolva')

# --- Sección 2.8: Gestión de Pedidos y Ventas ------------------------------------
class PedidoTolva(db.Model):
    """Modelo para pedidos de TOLVA - Solo columnas necesarias"""
    __tablename__ = 'pedido_tolva'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo_pedido = db.Column(db.String(50), nullable=True)  # Campo temporal para compatibilidad
    pedido = db.Column(db.String(50), unique=True, nullable=False)
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), default='TOLVA')
    
    # Fechas
    fecha_emision = db.Column(db.Date, nullable=False)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    
    # Estado
    estado = db.Column(db.String(25), default='NO ASIGNADO')  # NO ASIGNADO, ASIGNADO, CAMBIO_SOLICITADO, ELIMINACION_SOLICITADA, DISPONIBLE_PARA_ELIMINAR, NO INICIADO, EN_PRODUCCION, FABRICADO SIN ENTREGAR, ENTREGADO
    
    # Relación con chasis asignado
    chasis_id = db.Column(db.Integer, db.ForeignKey('chasis_asignado_tolva.id'), nullable=True)
    
    # Datos específicos de TOLVA
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    llantas = db.Column(db.String(100), nullable=False)
    cubiertas = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(50), nullable=False)
    balanza = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
    
    # Campos opcionales
    pdf_pedido = db.Column(db.String(255))
    creado_por = db.Column(db.String(100))

    # Relaciones
    chasis_asignado = db.relationship('ChasisAsignadoTolva', backref='pedidos', foreign_keys=[chasis_id])

class SolicitudCambioPedido(db.Model):
    """Solicitudes de cambio de chasis para pedidos"""
    __tablename__ = 'solicitud_cambio_pedido'
    
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_tolva.id'), nullable=False)
    chasis_actual_id = db.Column(db.Integer, db.ForeignKey('chasis_asignado_tolva.id'), nullable=False)
    chasis_nuevo_id = db.Column(db.Integer, db.ForeignKey('chasis_asignado_tolva.id'), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default='PENDIENTE')
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_solicitud = db.Column(db.DateTime, default=datetime.now)
    fecha_resolucion = db.Column(db.DateTime)
    aprobador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    observaciones = db.Column(db.Text)
    
    # Relaciones
    pedido = db.relationship('PedidoTolva', backref='solicitudes_cambio')
    chasis_actual = db.relationship('ChasisAsignadoTolva', foreign_keys=[chasis_actual_id])
    chasis_nuevo = db.relationship('ChasisAsignadoTolva', foreign_keys=[chasis_nuevo_id])
    solicitante = db.relationship('Usuario', foreign_keys=[solicitante_id])
    aprobador = db.relationship('Usuario', foreign_keys=[aprobador_id])

class SolicitudEliminacionPedido(db.Model):
    """Solicitudes de eliminación de pedidos"""
    __tablename__ = 'solicitud_eliminacion_pedido'
    
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_tolva.id'), nullable=False)
    chasis_asignado_id = db.Column(db.Integer, db.ForeignKey('chasis_asignado_tolva.id'), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default='PENDIENTE')
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_solicitud = db.Column(db.DateTime, default=datetime.now)
    fecha_resolucion = db.Column(db.DateTime)
    aprobador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    observaciones = db.Column(db.Text)
    
    # Relaciones
    pedido = db.relationship('PedidoTolva', backref='solicitudes_eliminacion')
    chasis_asignado = db.relationship('ChasisAsignadoTolva', foreign_keys=[chasis_asignado_id])
    solicitante = db.relationship('Usuario', foreign_keys=[solicitante_id])
    aprobador = db.relationship('Usuario', foreign_keys=[aprobador_id])

class PedidoMixer(db.Model):
    """Modelo para pedidos de MIXER"""
    __tablename__ = 'pedido_mixer'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo_pedido = db.Column(db.String(50), nullable=True)  # Campo temporal para compatibilidad
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), nullable=False, default='MIXER')

    # Fechas importantes
    fecha_emision = db.Column(db.Date, nullable=False)  # Fecha de emisión del pedido
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    fecha_asignacion_chasis = db.Column(db.DateTime)  # Cuando PCP asigna chasis

    # Estado del pedido
    estado = db.Column(db.String(25), default='NO ASIGNADO')  # NO ASIGNADO, ASIGNADO, CAMBIO_SOLICITADO, ELIMINACION_SOLICITADA, DISPONIBLE_PARA_ELIMINAR, NO INICIADO, EN_PRODUCCION, FABRICADO SIN ENTREGAR, ENTREGADO

    # Datos del pedido
    precio_unitario = db.Column(db.Float)
    precio_total = db.Column(db.Float)

    # Asignación de chasis
    chasis_asignado = db.Column(db.String(50))  # Número de chasis asignado
    plan_produccion_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))

    # Información adicional obligatoria (común a todos)
    pedido = db.Column(db.String(50), nullable=False)  # N° PEDIDO del cliente
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
    pdf_pedido = db.Column(db.String(300))  # Ruta al PDF del pedido original
            
    # Campos opcionales
    vendedor = db.Column(db.String(100))
    forma_pago = db.Column(db.String(50))

    # Campos de auditoría
    creado_por = db.Column(db.String(100))
    modificado_por = db.Column(db.String(100))
    fecha_modificacion = db.Column(db.DateTime)

    # Campos específicos de MIXER
    tipo_motor = db.Column(db.String(100))
    capacidad = db.Column(db.String(100))
    sistema_hidraulico = db.Column(db.String(100))

    # Relaciones
    plan_produccion = db.relationship('PlanProduccion', backref='pedidos_mixer')

class PedidoAtt(db.Model):
    """Modelo para pedidos de ATT"""
    __tablename__ = 'pedido_att'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo_pedido = db.Column(db.String(50), nullable=True)  # Campo temporal para compatibilidad
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), nullable=False, default='ATT')

    # Fechas importantes
    fecha_emision = db.Column(db.Date, nullable=False)  # Fecha de emisión del pedido
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    fecha_asignacion_chasis = db.Column(db.DateTime)  # Cuando PCP asigna chasis

    # Estado del pedido
    estado = db.Column(db.String(25), default='NO ASIGNADO')  # NO ASIGNADO, ASIGNADO, CAMBIO_SOLICITADO, ELIMINACION_SOLICITADA, DISPONIBLE_PARA_ELIMINAR, NO INICIADO, EN_PRODUCCION, FABRICADO SIN ENTREGAR, ENTREGADO

    # Datos del pedido
    precio_unitario = db.Column(db.Float)
    precio_total = db.Column(db.Float)

    # Asignación de chasis
    chasis_asignado = db.Column(db.String(50))  # Número de chasis asignado
    plan_produccion_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))

    # Información adicional obligatoria (común a todos)
    pedido = db.Column(db.String(50), nullable=False)  # N° PEDIDO del cliente
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
    pdf_pedido = db.Column(db.String(300))  # Ruta al PDF del pedido original
            
    # Campos opcionales
    vendedor = db.Column(db.String(100))
    forma_pago = db.Column(db.String(50))

    # Campos de auditoría
    creado_por = db.Column(db.String(100))
    modificado_por = db.Column(db.String(100))
    fecha_modificacion = db.Column(db.DateTime)

    # Campos específicos de ATT
    tipo_corte = db.Column(db.String(100))
    ancho_corte = db.Column(db.String(100))
    sistema_alimentacion = db.Column(db.String(100))

    # Relaciones
    plan_produccion = db.relationship('PlanProduccion', backref='pedidos_att')

class PedidoEmbossadora(db.Model):
    """Modelo para pedidos de EMBOLSADORA"""
    __tablename__ = 'pedido_embolsadora'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo_pedido = db.Column(db.String(50), nullable=True)  # Campo temporal para compatibilidad
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), nullable=False, default='EMBOLSADORA')

    # Fechas importantes
    fecha_emision = db.Column(db.Date, nullable=False)  # Fecha de emisión del pedido
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    fecha_asignacion_chasis = db.Column(db.DateTime)  # Cuando PCP asigna chasis

    # Estado del pedido
    estado = db.Column(db.String(25), default='NO ASIGNADO')  # NO ASIGNADO, ASIGNADO, CAMBIO_SOLICITADO, ELIMINACION_SOLICITADA, DISPONIBLE_PARA_ELIMINAR, NO INICIADO, EN_PRODUCCION, FABRICADO SIN ENTREGAR, ENTREGADO

    # Datos del pedido
    precio_unitario = db.Column(db.Float)
    precio_total = db.Column(db.Float)

    # Asignación de chasis
    chasis_asignado = db.Column(db.String(50))  # Número de chasis asignado
    plan_produccion_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))

    # Información adicional obligatoria (común a todos)
    pedido = db.Column(db.String(50), nullable=False)  # N° PEDIDO del cliente
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
    pdf_pedido = db.Column(db.String(300))  # Ruta al PDF del pedido original
            
    # Campos opcionales
    vendedor = db.Column(db.String(100))
    forma_pago = db.Column(db.String(50))

    # Campos de auditoría
    creado_por = db.Column(db.String(100))
    modificado_por = db.Column(db.String(100))
    fecha_modificacion = db.Column(db.DateTime)

    # Campos específicos de EMBOLSADORA
    tipo_bolsa = db.Column(db.String(100))

    # Relaciones
    plan_produccion = db.relationship('PlanProduccion', backref='pedidos_embolsadora')

class PedidoSembradora(db.Model):
    """Modelo para pedidos de SEMBRADORA"""
    __tablename__ = 'pedido_sembradora'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo_pedido = db.Column(db.String(50), nullable=True)  # Campo temporal para compatibilidad
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), nullable=False, default='SEMBRADORA')

    # Fechas importantes
    fecha_emision = db.Column(db.Date, nullable=False)  # Fecha de emisión del pedido
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    fecha_asignacion_chasis = db.Column(db.DateTime)  # Cuando PCP asigna chasis

    # Estado del pedido
    estado = db.Column(db.String(25), default='NO ASIGNADO')  # NO ASIGNADO, ASIGNADO, CAMBIO_SOLICITADO, ELIMINACION_SOLICITADA, DISPONIBLE_PARA_ELIMINAR, NO INICIADO, EN_PRODUCCION, FABRICADO SIN ENTREGAR, ENTREGADO

    # Datos del pedido
    precio_unitario = db.Column(db.Float)
    precio_total = db.Column(db.Float)

    # Asignación de chasis
    chasis_asignado = db.Column(db.String(50))  # Número de chasis asignado
    plan_produccion_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))

    # Información adicional obligatoria (común a todos)
    pedido = db.Column(db.String(50), nullable=False)  # N° PEDIDO del cliente
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
    pdf_pedido = db.Column(db.String(300))  # Ruta al PDF del pedido original
            
    # Campos opcionales
    vendedor = db.Column(db.String(100))
    forma_pago = db.Column(db.String(50))

    # Campos de auditoría
    creado_por = db.Column(db.String(100))
    modificado_por = db.Column(db.String(100))
    fecha_modificacion = db.Column(db.DateTime)

    # Campos específicos de SEMBRADORA
    ancho_trabajo = db.Column(db.String(100))

    # Relaciones
    plan_produccion = db.relationship('PlanProduccion', backref='pedidos_sembradora')

# Mantener el modelo original para compatibilidad con consultas existentes
class Pedido(db.Model):
    """Modelo unificado para consultas - compatibilidad con código existente"""
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(200), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    implemento = db.Column(db.String(50), nullable=False)  # TOLVA, MIXER, ATT, EMBOLSADORA, SEMBRADORA

    # Fechas importantes
    fecha_emision = db.Column(db.Date, nullable=False)  # Fecha de emisión del pedido
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_compromiso = db.Column(db.Date, nullable=False)
    fecha_asignacion_chasis = db.Column(db.DateTime)  # Cuando PCP asigna chasis

    # Estado del pedido
    estado = db.Column(db.String(20), default='PENDIENTE')  # PENDIENTE, ASIGNADO, EN_PRODUCCION, COMPLETADO, CANCELADO

    # Datos del pedido
    precio_unitario = db.Column(db.Float)
    precio_total = db.Column(db.Float)

    # Asignación de chasis
    chasis_asignado = db.Column(db.String(50))  # Número de chasis asignado
    plan_produccion_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'))

    # Información adicional obligatoria (común a todos)
    pedido = db.Column(db.String(50), nullable=False)  # N° PEDIDO del cliente
    concesionario = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text, nullable=False)
            
    # Campos opcionales
    vendedor = db.Column(db.String(100))
    forma_pago = db.Column(db.String(50))

    # Campos de auditoría
    creado_por = db.Column(db.String(100))
    modificado_por = db.Column(db.String(100))
    fecha_modificacion = db.Column(db.DateTime)

    # Todos los campos opcionales para todos los implementos
    llantas = db.Column(db.String(100))
    cubiertas = db.Column(db.String(100))
    color = db.Column(db.String(50))
    balanza = db.Column(db.String(100))
    tipo_motor = db.Column(db.String(100))
    capacidad = db.Column(db.String(100))
    sistema_hidraulico = db.Column(db.String(100))
    tipo_corte = db.Column(db.String(100))
    ancho_corte = db.Column(db.String(100))
    sistema_alimentacion = db.Column(db.String(100))
    tipo_bolsa = db.Column(db.String(100))
    ancho_trabajo = db.Column(db.String(100))

    # Relaciones
    plan_produccion = db.relationship('PlanProduccion', backref='pedidos')
    historial_estados = db.relationship('HistorialEstadoPedido', backref='pedido', lazy=True, cascade="all, delete-orphan")

class HistorialEstadoPedido(db.Model):
    """Registro de cambios de estado de los pedidos"""
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    estado_anterior = db.Column(db.String(20))
    estado_nuevo = db.Column(db.String(20), nullable=False)
    fecha_cambio = db.Column(db.DateTime, default=datetime.now)
    usuario = db.Column(db.String(100))
    motivo = db.Column(db.Text)

class ChasisAsignadoMixer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    nro_chasis = db.Column(db.String(50), nullable=False)  # Relación con plan_produccion.nro_chasis
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    
    # --- DATOS BÁSICOS MIXER ---
    lanzamiento = db.Column(db.String(50))  # LANZAMIENTO (texto libre)
    modelo = db.Column(db.String(100))      # MODELO (M1600, M2000, M2600)
    cliente = db.Column(db.String(200))    # CLIENTE (texto libre)
    
    # --- DATOS ESPECÍFICOS MIXER ---
    tipo_motor = db.Column(db.String(50))   # Tipo de motor específico para MIXER
    capacidad = db.Column(db.String(50))     # Capacidad de mezcla
    sistema_hidraulico = db.Column(db.String(50))  # Especificaciones hidráulicas
    tipo_tornillo = db.Column(db.String(50))  # Tipo de tornillo sinfín
    
    # --- OBSERVACIONES ---
    observaciones = db.Column(db.Text)      # OBSERVACIONES específicas de MIXER
    
    # --- RELACIONES ---
    plan = db.relationship('PlanProduccion', backref='chasis_asignado_mixer')

class ChasisAsignadoATT(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    nro_chasis = db.Column(db.String(50), nullable=False)  # Relación con plan_produccion.nro_chasis
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    
    # --- DATOS BÁSICOS ATT ---
    lanzamiento = db.Column(db.String(50))  # LANZAMIENTO (texto libre)
    modelo = db.Column(db.String(100))      # MODELO (texto libre)
    cliente = db.Column(db.String(200))    # CLIENTE (texto libre)
    
    # --- DATOS ESPECÍFICOS ATT ---
    tipo_corte = db.Column(db.String(50))     # Tipo de sistema de corte
    ancho_corte = db.Column(db.String(50))     # Ancho de corte
    sistema_alimentacion = db.Column(db.String(50))  # Sistema de alimentación
    velocidad_corte = db.Column(db.String(50))   # Velocidad de corte
    
    # --- OBSERVACIONES ---
    observaciones = db.Column(db.Text)      # OBSERVACIONES específicas de ATT
    
    # --- RELACIONES ---
    plan = db.relationship('PlanProduccion', backref='chasis_asignado_att')

class ChasisAsignadoEmbolsadora(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    nro_chasis = db.Column(db.String(50), nullable=False)  # Relación con plan_produccion.nro_chasis
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    
    # --- DATOS BÁSICOS EMBOLSADORA ---
    lanzamiento = db.Column(db.String(50))  # LANZAMIENTO (texto libre)
    modelo = db.Column(db.String(100))      # MODELO (texto libre)
    cliente = db.Column(db.String(200))    # CLIENTE (texto libre)
    
    # --- DATOS ESPECÍFICOS EMBOLSADORA ---
    tipo_bolsa = db.Column(db.String(50))      # Tipo de bolsa
    capacidad_embolsado = db.Column(db.String(50))  # Capacidad de embolsado
    sistema_pesaje = db.Column(db.String(50))      # Sistema de pesaje
    velocidad_embolsado = db.Column(db.String(50))  # Velocidad de embolsado
    
    # --- OBSERVACIONES ---
    observaciones = db.Column(db.Text)      # OBSERVACIONES específicas de EMBOLSADORA
    
    # --- RELACIONES ---
    plan = db.relationship('PlanProduccion', backref='chasis_asignado_embolsadora')


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # CLI-001
    nombre = db.Column(db.String(200), nullable=False)
    razon_social = db.Column(db.String(200))
    cuit = db.Column(db.String(20))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    direccion = db.Column(db.Text)
    localidad = db.Column(db.String(100))
    provincia = db.Column(db.String(100))
    tipo_cliente = db.Column(db.String(20), default='PARTICULAR')  # 'PARTICULAR', 'EMPRESA', 'COOPERATIVA'
    estado = db.Column(db.String(20), default='ACTIVO')  # 'ACTIVO', 'INACTIVO', 'SUSPENDIDO'
    fecha_alta = db.Column(db.DateTime, default=datetime.now)
    observaciones = db.Column(db.Text)

class CaracteristicaChasis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    implemento = db.Column(db.String(50), nullable=False)  # 'TOLVA', 'MIXER', etc.
    nombre_caracteristica = db.Column(db.String(100), nullable=False)
    tipo_dato = db.Column(db.String(20), nullable=False)  # 'TEXTO', 'NUMERO', 'BOOLEAN', 'LISTA'
    valores_posibles = db.Column(db.Text)  # JSON con opciones para tipo LISTA
    valor_defecto = db.Column(db.String(200))
    obligatoria = db.Column(db.Boolean, default=False)
    orden = db.Column(db.Integer, default=0)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan_produccion.id'), nullable=False)
    nro_chasis = db.Column(db.String(50), nullable=False)  # Relación con plan_produccion.nro_chasis
    fecha_asignacion = db.Column(db.DateTime, default=datetime.now)
    
    # --- DATOS BÁSICOS ---
    lanzamiento = db.Column(db.String(50))  # LANZAMIENTO (texto libre)
    modelo = db.Column(db.String(100))      # MODELO (texto libre)
    cliente = db.Column(db.String(200))    # CLIENTE (texto libre)
    tubo = db.Column(db.String(50))         # TUBO (texto libre)
    encamisado = db.Column(db.String(50))  # ENCAMISADO (texto libre)
    tipo_tubo = db.Column(db.String(50))   # TIPO TUBO (texto libre)
    tamano_cubierta = db.Column(db.String(50))  # TAMAÑO DE CUBIERTA (texto libre)
    marca_cubiertas = db.Column(db.String(100))  # MARCA DE LAS CUBIERTAS (texto libre)
    color = db.Column(db.String(50))        # COLOR (texto libre)
    balanza = db.Column(db.String(50))      # BALANZA (texto libre)
    observaciones = db.Column(db.Text)      # OBSERVACIONES (texto libre)
    
    # --- ENTREGA Y VENTAS ---
    entregada = db.Column(db.String(20))    # Entregada (texto libre)
    fecha_entrega = db.Column(db.String(50))  # Fecha de Entrega (texto libre)
    pedido = db.Column(db.String(100))      # Pedido (texto libre)
    liberada_ventas = db.Column(db.String(20))  # Liberada para VENTAS (texto libre)
    llantas_ok = db.Column(db.String(20))    # Llantas OK (texto libre)
    cubiertas_ok = db.Column(db.String(20))  # Cubiertas OK (texto libre)
    observaciones_2 = db.Column(db.Text)      # OBSERVACIÓN 2 (texto libre)
    proveedor_sinfin = db.Column(db.String(100))  # PROVEEDOR DE SIN FIN (texto libre)
    dias_consignacion = db.Column(db.String(20))  # DIAS EN CONSIGNACION DESDE SU ENTREGA (texto libre)
    
    # --- RELACIONES ---
    plan = db.relationship('PlanProduccion', backref='asignacion_cliente')
    caracteristica_id = db.Column(db.Integer, db.ForeignKey('caracteristica_chasis.id'), nullable=False)
    valor_texto = db.Column(db.String(500))
    valor_numero = db.Column(db.Float)
    valor_booleano = db.Column(db.Boolean)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)
    registrado_por = db.Column(db.String(100))

class Feriado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(10), unique=True, nullable=False)  # DD/MM/YYYY
    descripcion = db.Column(db.String(200))

class Auditoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario_nombre = db.Column(db.String(100), nullable=False)
    accion = db.Column(db.String(200), nullable=False)  # Ej: "CREAR_USUARIO", "EDITAR_USUARIO", "AGREGAR_FERIADO"
    ventana = db.Column(db.String(100), nullable=False)  # Ej: "Gestión de Usuarios", "Gestión de Feriados", "Producción"
    detalles = db.Column(db.Text, nullable=True)  # Detalles específicos: "modifica fecha en chasis XXX"
    ip_address = db.Column(db.String(45), nullable=True)  # IP del usuario
    
    # Relación con usuario
    usuario = db.relationship('Usuario', backref=db.backref('auditorias', lazy=True))
    
    def __repr__(self):
        return f'<Feriado {self.fecha}>'

@login_manager.user_loader
def load_user(user_id):
    """Cargar usuario usando SQL directo para evitar problemas de mapeo"""
    try:
        from sqlalchemy import text
        
        # Usar SQL directo para evitar problemas con el mapeo de SQLAlchemy
        result = db.session.execute(text("SELECT * FROM usuario WHERE id = :user_id"), {"user_id": int(user_id)})
        row = result.fetchone()
        
        if row:
            # Crear objeto Usuario manualmente
            usuario = Usuario()
            usuario.id = row[0]
            usuario.legajo = row[1]
            usuario.pin_secreto = row[2]
            usuario.nombre = row[3]
            usuario.sector = row[4]
            usuario.rol = row[5]
            return usuario
        return None
        
    except Exception as e:
        print(f"Error en load_user: {e}")
        return None

# --- Sección 3: Funciones Auxiliares ---------------------------------------------------------

def registrar_auditoria(usuario_id, usuario_nombre, accion, ventana, detalles=None, ip_address=None):
    """Registra una acción en el log de auditoría"""
    try:
        auditoria = Auditoria(
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            accion=accion,
            ventana=ventana,
            detalles=detalles,
            ip_address=ip_address or request.remote_addr
        )
        db.session.add(auditoria)
        db.session.commit()
    except Exception as e:
        print(f"Error registrando auditoría: {str(e)}")
        db.session.rollback()

# ... Resto del código ...
      # --- Definicion de feriados
def obtener_dias_habiles(fecha_base, cantidad, direccion="futuro"):
    feriados = [f.fecha for f in Feriado.query.all()] # Están en DD/MM/YYYY
    dias_habiles = []
    fecha_aux = fecha_base
    
    while len(dias_habiles) < cantidad:
        paso = 1 if direccion == "futuro" else -1
        fecha_aux += timedelta(days=paso)
        
        es_fin_de_semana = fecha_aux.weekday() >= 5
        # Convertimos la fecha auxiliar al formato de la tabla feriados para comparar
        if not es_fin_de_semana and fecha_aux.strftime('%d/%m/%Y') not in feriados:
            # Guardamos en formato DD/MM/YYYY para que coincida con el Excel del Plan
            dias_habiles.append(fecha_aux.strftime('%d/%m/%Y'))
            
    return dias_habiles

# --- Sección 3: Dashboard (Seguimiento Gerencial)------------------------------------------------------


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.rol != 'ADMIN':
        return "No autorizado"

    # 1. Definir rango de tiempo (Semana actual)
    hoy = datetime.now()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    
    # 2. Obtener todos los puestos únicos
    puestos_db = db.session.query(PlanProduccion.puesto_conjunto).distinct().all()
    resumen = []

    for p in puestos_db:
        nombre_puesto = p[0]
        
        # Total chasis planificados para este puesto
        total = PlanProduccion.query.filter_by(puesto_conjunto=nombre_puesto).count()
        
        # Total chasis terminados para este puesto
        hechos = PlanProduccion.query.filter_by(puesto_conjunto=nombre_puesto, estado='TERMINADO').count()

        # Calcular porcentaje
        porcentaje = round((hechos / total * 100), 1) if total > 0 else 0
        
        # Determinar estado y color
        if porcentaje >= 80:
            estado, color = "Cumpliendo", "success"
        elif porcentaje >= 50:
            estado, color = "En Riesgo", "warning"
        else:
            estado, color = "Atrasado", "danger"

        resumen.append({
            'nombre': nombre_puesto,
            'porcentaje': porcentaje,
            'hechos': hechos,
            'total': total,
            'estado': estado,
            'color': color
        })

    return render_template('dashboard.html', resumen=resumen)


# ----Sección 4: CRUD Administrador (Gestión de Planes)----------------------------------------------------

# --- SECCIÓN: PRODUCCIÓN PARA ADMINISTRADOR ---

# Nueva ruta de decisión
@app.route('/admin/opciones_produccion')
@login_required
def admin_opciones_produccion():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    return render_template('admin_produccion_opciones.html')

# Ruta admin_plan para Plan Maestro - selección de implementos
@app.route('/admin/plan')
@login_required
def admin_plan():
    """Plan Maestro - Selección de implementos"""
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    
    # Si viene con parámetro implemento, mostrar gestión de ese implemento
    implemento = request.args.get('implemento')
    if implemento:
        # Mostrar gestión con sector/puesto para el implemento seleccionado
        s_sel = request.args.get('sector', 'MONTAJE')
        p_sel = request.args.get('puesto', '')  # Cambiado de 'M5' a '' para iniciar sin selección
        busqueda_chasis = request.args.get('busqueda_chasis', '').strip()
        
        # Obtener estructura de puestos
        estructura = {}
        for s in ['MONTAJE', 'SOLDADURA', 'PINTURA']:
            puestos_db = db.session.query(PlanProduccion.puesto_conjunto).filter_by(sector=s).distinct().all()
            puestos_filtrados = [p[0] for p in puestos_db if p[0]]
            
            # Excluir P6 del sector SOLDADURA
            if s == 'SOLDADURA':
                puestos_filtrados = [p for p in puestos_filtrados if p != 'P6']
            
            estructura[s] = puestos_filtrados
        
        # Consultar planes según los filtros con join a tabla específica del implemento
        if implemento == 'TOLVA':
            # Usar ChasisAsignadoTolva para TOLVA - buscar lanzamiento solo por chasis
            # Para TOLVA, muchos registros tienen puesto_conjunto = None, así que manejamos ambos casos
            query_base = db.session.query(
                PlanProduccion,
                ChasisAsignadoTolva.lanzamiento
            ).outerjoin(
                ChasisAsignadoTolva, 
                PlanProduccion.nro_chasis == ChasisAsignadoTolva.nro_chasis
            ).filter(
                PlanProduccion.implemento == implemento,
                PlanProduccion.sector == s_sel
            )
            
            # Agregar filtro de búsqueda de chasis si se proporciona
            if busqueda_chasis:
                query_base = query_base.filter(
                    PlanProduccion.nro_chasis.ilike(f'%{busqueda_chasis}%')
                )
            
            # Si hay búsqueda de chasis, mostrar todos los puestos; si no, aplicar filtro de puesto
            if busqueda_chasis:
                # Mostrar todos los puestos para el chasis buscado (sin filtro de puesto), pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            elif p_sel == '':  # Si no hay puesto seleccionado, mostrar todos, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            elif p_sel == 'M5':  # Compatibilidad con valor antiguo, mostrar todos incluyendo None, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    (PlanProduccion.puesto_conjunto == p_sel) | (PlanProduccion.puesto_conjunto.is_(None))
                ).filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            else:
                # Aplicar filtro de puesto específico, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    PlanProduccion.puesto_conjunto == p_sel
                ).filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
        elif implemento == 'MIXER':
            # Usar ChasisAsignadoMixer para MIXER - buscar lanzamiento solo por chasis
            query_base = db.session.query(
                PlanProduccion,
                ChasisAsignadoMixer.lanzamiento
            ).outerjoin(
                ChasisAsignadoMixer, 
                PlanProduccion.nro_chasis == ChasisAsignadoMixer.nro_chasis
            ).filter(
                PlanProduccion.implemento == implemento,
                PlanProduccion.sector == s_sel
            )
            
            # Agregar filtro de búsqueda de chasis si se proporciona
            if busqueda_chasis:
                query_base = query_base.filter(
                    PlanProduccion.nro_chasis.ilike(f'%{busqueda_chasis}%')
                )
            
            # Si hay búsqueda de chasis, mostrar todos los puestos; si no, aplicar filtro de puesto
            if busqueda_chasis:
                # Mostrar todos los puestos para el chasis buscado (sin filtro de puesto), pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            else:
                # Aplicar filtro de puesto específico, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    PlanProduccion.puesto_conjunto == p_sel
                ).filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
        elif implemento == 'ATT':
            # Usar ChasisAsignadoATT para ATT - buscar lanzamiento solo por chasis
            query_base = db.session.query(
                PlanProduccion,
                ChasisAsignadoATT.lanzamiento
            ).outerjoin(
                ChasisAsignadoATT, 
                PlanProduccion.nro_chasis == ChasisAsignadoATT.nro_chasis
            ).filter(
                PlanProduccion.implemento == implemento,
                PlanProduccion.sector == s_sel
            )
            
            # Agregar filtro de búsqueda de chasis si se proporciona
            if busqueda_chasis:
                query_base = query_base.filter(
                    PlanProduccion.nro_chasis.ilike(f'%{busqueda_chasis}%')
                )
            
            # Si hay búsqueda de chasis, mostrar todos los puestos; si no, aplicar filtro de puesto
            if busqueda_chasis:
                # Mostrar todos los puestos para el chasis buscado (sin filtro de puesto), pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            else:
                # Aplicar filtro de puesto específico, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    PlanProduccion.puesto_conjunto == p_sel
                ).filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
        elif implemento == 'EMBOLSADORA':
            # Usar ChasisAsignadoEmbolsadora para EMBOLSADORA - buscar lanzamiento solo por chasis
            query_base = db.session.query(
                PlanProduccion,
                ChasisAsignadoEmbolsadora.lanzamiento
            ).outerjoin(
                ChasisAsignadoEmbolsadora, 
                PlanProduccion.nro_chasis == ChasisAsignadoEmbolsadora.nro_chasis
            ).filter(
                PlanProduccion.implemento == implemento,
                PlanProduccion.sector == s_sel
            )
            
            # Agregar filtro de búsqueda de chasis si se proporciona
            if busqueda_chasis:
                query_base = query_base.filter(
                    PlanProduccion.nro_chasis.ilike(f'%{busqueda_chasis}%')
                )
            
            # Si hay búsqueda de chasis, mostrar todos los puestos; si no, aplicar filtro de puesto
            if busqueda_chasis:
                # Mostrar todos los puestos para el chasis buscado (sin filtro de puesto), pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
            else:
                # Aplicar filtro de puesto específico, pero excluir P6 de SOLDADURA
                plans = query_base.filter(
                    PlanProduccion.puesto_conjunto == p_sel
                ).filter(
                    ~((PlanProduccion.sector == 'SOLDADURA') & (PlanProduccion.puesto_conjunto == 'P6'))
                ).order_by(
                    func.substr(PlanProduccion.fecha, 7, 4), 
                    func.substr(PlanProduccion.fecha, 4, 2), 
                    func.substr(PlanProduccion.fecha, 1, 2)
                ).all()
        else:
            # Para implementos no específicos, no mostrar datos
            plans = []
        
        # Para cada plan, obtener el modelo desde la tabla correspondiente
        planes_con_lanzamiento = []
        for plan, lanzamiento in plans:
            # Buscar chasis_asignado específico para obtener el modelo - solo por chasis
            if implemento == 'TOLVA':
                chasis_asignado = ChasisAsignadoTolva.query.filter_by(
                    nro_chasis=plan.nro_chasis
                ).first()
            elif implemento == 'MIXER':
                chasis_asignado = ChasisAsignadoMixer.query.filter_by(
                    nro_chasis=plan.nro_chasis
                ).first()
            elif implemento == 'ATT':
                chasis_asignado = ChasisAsignadoATT.query.filter_by(
                    nro_chasis=plan.nro_chasis
                ).first()
            elif implemento == 'EMBOLSADORA':
                chasis_asignado = ChasisAsignadoEmbolsadora.query.filter_by(
                    nro_chasis=plan.nro_chasis
                ).first()
            else:
                chasis_asignado = None
            
            plan_dict = {
                'id': plan.id,
                'fecha': plan.fecha,
                'nro_chasis': plan.nro_chasis,
                'implemento': plan.implemento,
                'modelo': chasis_asignado.modelo if chasis_asignado else 'Sin modelo',
                'sector': plan.sector,
                'puesto_conjunto': plan.puesto_conjunto,
                'estado': plan.estado,
                'usuario_avance': plan.usuario_avance,
                'lanzamiento': lanzamiento  # Agregar el campo lanzamiento
            }
            planes_con_lanzamiento.append(plan_dict)
        
        return render_template('admin_plan.html', 
                             planes=planes_con_lanzamiento, 
                             s_sel=s_sel, 
                             p_sel=p_sel, 
                             estructura=estructura,
                             implemento=implemento)
    
    # Si no viene con implemento, mostrar selección de implementos
    implementos = ['TOLVA', 'MIXER', 'EMBOLSADORA', 'ATT', 'SEMBRADORA']
    return render_template('admin_seleccion_implemento.html', implementos=implementos)

# Nueva ruta para menú de configuración general
@app.route('/admin/configuracion')
@login_required
def admin_configuracion():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    usuarios = Usuario.query.all()
    return render_template('admin_configuracion.html', usuarios=usuarios)

# Nueva ruta para panel de auditoría
@app.route('/admin/auditoria')
@login_required
def admin_auditoria():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    
    # Obtener parámetros de filtro
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 50
    accion_filtro = request.args.get('accion', '')
    ventana_filtro = request.args.get('ventana', '')
    usuario_filtro = request.args.get('usuario', '')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    # Construir query base
    query = Auditoria.query
    
    # Aplicar filtros
    if accion_filtro:
        query = query.filter(Auditoria.accion.ilike(f'%{accion_filtro}%'))
    if ventana_filtro:
        query = query.filter(Auditoria.ventana.ilike(f'%{ventana_filtro}%'))
    if usuario_filtro:
        query = query.filter(Auditoria.usuario_nombre.ilike(f'%{usuario_filtro}%'))
    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query = query.filter(Auditoria.fecha_hora >= fecha_inicio_dt)
        except ValueError:
            pass
    if fecha_fin:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Auditoria.fecha_hora <= fecha_fin_dt)
        except ValueError:
            pass
    
    # Ordenar por fecha descendente y paginar
    auditorias = query.order_by(Auditoria.fecha_hora.desc()).paginate(
        page=pagina, per_page=por_pagina, error_out=False
    )
    
    # Obtener listas para filtros
    acciones = db.session.query(Auditoria.accion).distinct().all()
    acciones = [a[0] for a in acciones]
    
    ventanas = db.session.query(Auditoria.ventana).distinct().all()
    ventanas = [v[0] for v in ventanas]
    
    usuarios_auditoria = db.session.query(Auditoria.usuario_nombre).distinct().all()
    usuarios_auditoria = [u[0] for u in usuarios_auditoria]
    
    return render_template('admin_auditoria.html', 
                         auditorias=auditorias,
                         acciones=acciones,
                         ventanas=ventanas,
                         usuarios_auditoria=usuarios_auditoria,
                         accion_filtro=accion_filtro,
                         ventana_filtro=ventana_filtro,
                         usuario_filtro=usuario_filtro,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin)

# --- RUTAS PARA GESTIÓN DE USUARIOS ---

@app.route('/admin/verificar_legajo/<legajo>')
@login_required
def verificar_legajo(legajo):
    if current_user.rol != 'ADMIN': 
        return jsonify({'valido': False, 'error': 'No autorizado'}), 403
    
    try:
        usuario_existente = Usuario.query.filter_by(legajo=legajo).first()
        if usuario_existente:
            return jsonify({'valido': False, 'error': 'El legajo ya está en uso'})
        else:
            return jsonify({'valido': True})
    except Exception as e:
        return jsonify({'valido': False, 'error': str(e)}), 500

@app.route('/admin/agregar_usuario', methods=['POST'])
@login_required
def agregar_usuario():
    if current_user.rol != 'ADMIN': 
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        # Verificar que el legajo no exista
        legajo_existente = Usuario.query.filter_by(legajo=request.form.get('legajo')).first()
        if legajo_existente:
            return jsonify({'success': False, 'error': 'El legajo ya existe'}), 400
        
        nuevo_usuario = Usuario(
            legajo=request.form.get('legajo'),
            pin_secreto=request.form.get('pin_secreto'),
            nombre=request.form.get('nombre'),
            sector=request.form.get('sector'),
            rol=request.form.get('rol', 'OPERARIO')
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        # Registrar auditoría
        detalles = f"CREAR usuario: Legajo {request.form.get('legajo')}, Nombre: {request.form.get('nombre')}, Sector: {request.form.get('sector')}, Rol: {request.form.get('rol')}"
        registrar_auditoria(
            current_user.id, 
            current_user.nombre, 
            'CREAR_USUARIO', 
            'Gestión de Usuarios', 
            detalles
        )
        
        return jsonify({'success': True, 'message': 'Usuario agregado correctamente'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/editar_usuario/<int:id>', methods=['POST'])
@login_required
def editar_usuario(id):
    if current_user.rol != 'ADMIN': 
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        usuario = Usuario.query.get_or_404(id)
        
        # Guardar valores originales para auditoría
        valores_originales = {
            'nombre': usuario.nombre,
            'sector': usuario.sector,
            'rol': usuario.rol
        }
        
        # Actualizar valores
        usuario.nombre = request.form.get('nombre')
        usuario.sector = request.form.get('sector')
        usuario.rol = request.form.get('rol')
        db.session.commit()
        
        # Registrar auditoría
        cambios = []
        if valores_originales['nombre'] != usuario.nombre:
            cambios.append(f"Nombre: {valores_originales['nombre']} → {usuario.nombre}")
        if valores_originales['sector'] != usuario.sector:
            cambios.append(f"Sector: {valores_originales['sector']} → {usuario.sector}")
        if valores_originales['rol'] != usuario.rol:
            cambios.append(f"Rol: {valores_originales['rol']} → {usuario.rol}")
        
        detalles = f"EDITAR usuario Legajo {usuario.legajo}: " + ", ".join(cambios)
        registrar_auditoria(
            current_user.id, 
            current_user.nombre, 
            'EDITAR_USUARIO', 
            'Gestión de Usuarios', 
            detalles
        )
        
        return jsonify({'success': True, 'message': 'Usuario actualizado correctamente'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/eliminar_usuario/<int:id>', methods=['POST'])
@login_required
def eliminar_usuario(id):
    if current_user.rol != 'ADMIN': 
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        usuario = Usuario.query.get_or_404(id)
        
        # No permitir eliminar al usuario actual
        if usuario.id == current_user.id:
            return jsonify({'success': False, 'error': 'No puedes eliminar tu propio usuario'}), 400
        
        # Guardar datos para auditoría
        datos_usuario = f"Legajo {usuario.legajo}, Nombre: {usuario.nombre}, Sector: {usuario.sector}, Rol: {usuario.rol}"
        
        db.session.delete(usuario)
        db.session.commit()
        
        # Registrar auditoría
        detalles = f"ELIMINAR usuario: {datos_usuario}"
        registrar_auditoria(
            current_user.id, 
            current_user.nombre, 
            'ELIMINAR_USUARIO', 
            'Gestión de Usuarios', 
            detalles
        )
        
        return jsonify({'success': True, 'message': 'Usuario eliminado correctamente'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- SECCIÓN: PLANILLA DE PRODUCCIÓN ---
@app.route('/admin/planilla_produccion')
@login_required
def planilla_produccion_seleccion():
    """Menú de selección de implementos para planilla de producción"""
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    return render_template('planilla_produccion_seleccion.html')

@app.route('/admin/borrar_datos/<implemento>', methods=['POST'])
@login_required
def borrar_datos_produccion(implemento):
    """Borrar todos los datos de producción de un implemento"""
    if current_user.rol != 'ADMIN':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        # Borrar todos los datos del implemento
        borrados = PlanProduccion.query.filter_by(implemento=implemento).delete()
        db.session.commit()
        
        # Registrar auditoría
        detalles = f"BORRAR todos los datos del implemento {implemento}: {borrados} registros eliminados"
        registrar_auditoria(
            current_user.id,
            current_user.nombre,
            'BORRAR_DATOS_PRODUCCION',
            f'Planilla de Producción - {implemento}',
            detalles
        )
        
        return jsonify({
            'success': True,
            'mensaje': f'Se borraron {borrados} registros del implemento {implemento} correctamente.',
            'total_borrados': borrados
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al borrar datos: {str(e)}'
        }), 500


@app.route('/admin/editar_seleccionados', methods=['POST'])
@login_required
def editar_seleccionados():
    """Editar una fila seleccionada"""
    if current_user.rol != 'ADMIN':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        
        # Si viene con 'ids', es para obtener los datos de las filas
        if 'ids' in data:
            ids = data.get('ids', [])
            
            if not ids:
                return jsonify({'success': False, 'error': 'No se seleccionaron filas'}), 400
            
            # Obtener los datos de las filas seleccionadas
            filas = []
            for plan_id in ids:
                try:
                    plan = PlanProduccion.query.get(plan_id)
                    if plan:
                        # Determinar qué tabla usar según el implemento
                        if plan.implemento == 'TOLVA':
                            chasis_asignado = ChasisAsignadoTolva.query.filter_by(
                                plan_id=plan.id, 
                                nro_chasis=plan.nro_chasis
                            ).first()
                        elif plan.implemento == 'MIXER':
                            chasis_asignado = ChasisAsignadoMixer.query.filter_by(
                                plan_id=plan.id, 
                                nro_chasis=plan.nro_chasis
                            ).first()
                        elif plan.implemento == 'ATT':
                            chasis_asignado = ChasisAsignadoATT.query.filter_by(
                                plan_id=plan.id, 
                                nro_chasis=plan.nro_chasis
                            ).first()
                        elif plan.implemento == 'EMBOLSADORA':
                            chasis_asignado = ChasisAsignadoEmbolsadora.query.filter_by(
                                plan_id=plan.id, 
                                nro_chasis=plan.nro_chasis
                            ).first()
                        else:
                            chasis_asignado = None
                        
                        filas.append({
                            'id': plan.id,
                            'nro_chasis': plan.nro_chasis,
                            'fecha': plan.fecha,
                            'modelo': chasis_asignado.modelo if chasis_asignado else plan.modelo,
                            'lanzamiento': chasis_asignado.lanzamiento if chasis_asignado else '',
                            'cliente': chasis_asignado.cliente if chasis_asignado else '',
                            'tubo': chasis_asignado.tubo if chasis_asignado else '',
                            'encamisado': chasis_asignado.encamisado if chasis_asignado else '',
                            'tipo_tubo': chasis_asignado.tipo_tubo if chasis_asignado else '',
                            'tamano_cubierta': chasis_asignado.tamano_cubierta if chasis_asignado else '',
                            'marca_cubiertas': chasis_asignado.marca_cubiertas if chasis_asignado else '',
                            'color': chasis_asignado.color if chasis_asignado else '',
                            'balanza': chasis_asignado.balanza if chasis_asignado else '',
                            'entregada': chasis_asignado.entregada if chasis_asignado else '',
                            'observaciones': chasis_asignado.observaciones if chasis_asignado else ''
                        })
                except Exception as e:
                    print(f"Error obteniendo fila {plan_id}: {e}")
                    continue
            
            return jsonify({
                'success': True,
                'filas': filas,
                'total_filas': len(filas)
            })
        
        # Si viene con 'id', es para actualizar los datos
        elif 'id' in data:
            id_fila = data.get('id')
            if not id_fila:
                return jsonify({'success': False, 'error': 'ID de fila no proporcionado'}), 400
            
            # Primero buscar el registro de chasis para obtener el plan_id y determinar el implemento
            # Intentar en cada tabla hasta encontrar el registro
            chasis = None
            ChasisAsignadoModel = None
            
            # Intentar en TOLVA primero
            chasis = ChasisAsignadoTolva.query.get(id_fila)
            if chasis:
                ChasisAsignadoModel = ChasisAsignadoTolva
            else:
                # Intentar en MIXER
                chasis = ChasisAsignadoMixer.query.get(id_fila)
                if chasis:
                    ChasisAsignadoModel = ChasisAsignadoMixer
                else:
                    # Intentar en ATT
                    chasis = ChasisAsignadoATT.query.get(id_fila)
                    if chasis:
                        ChasisAsignadoModel = ChasisAsignadoATT
                    else:
                        # Intentar en EMBOLSADORA
                        chasis = ChasisAsignadoEmbolsadora.query.get(id_fila)
                        if chasis:
                            ChasisAsignadoModel = ChasisAsignadoEmbolsadora
            
            if not chasis:
                return jsonify({'success': False, 'error': 'Registro de chasis no encontrado'}), 404
            
            # Buscar el plan de producción usando el plan_id del registro de chasis
            plan = PlanProduccion.query.get(chasis.plan_id)
            if not plan:
                return jsonify({'success': False, 'error': 'Plan no encontrado'}), 404
            
            # Guardar valores originales para auditoría
            valores_originales = {
                'modelo': chasis.modelo,
                'lanzamiento': chasis.lanzamiento,
                'cliente': chasis.cliente,
                'tubo': chasis.tubo,
                'encamisado': chasis.encamisado,
                'tipo_tubo': chasis.tipo_tubo,
                'tamano_cubierta': chasis.tamano_cubierta,
                'marca_cubiertas': chasis.marca_cubiertas,
                'color': chasis.color,
                'balanza': chasis.balanza,
                'entregada': chasis.entregada,
                'observaciones': chasis.observaciones
            }
            
            # Actualizar solo la tabla de chasis asignados (no plan_produccion)
            chasis.modelo = data.get('modelo', chasis.modelo)
            chasis.lanzamiento = data.get('lanzamiento', chasis.lanzamiento)
            chasis.cliente = data.get('cliente', chasis.cliente)
            chasis.tubo = data.get('tubo', chasis.tubo)
            chasis.encamisado = data.get('encamisado', chasis.encamisado)
            chasis.tipo_tubo = data.get('tipo_tubo', chasis.tipo_tubo)
            chasis.tamano_cubierta = data.get('tamano_cubierta', chasis.tamano_cubierta)
            chasis.marca_cubiertas = data.get('marca_cubiertas', chasis.marca_cubiertas)
            chasis.color = data.get('color', chasis.color)
            chasis.balanza = data.get('balanza', chasis.balanza)
            chasis.entregada = data.get('entregada', chasis.entregada)
            chasis.observaciones = data.get('observaciones', chasis.observaciones)
            
            db.session.commit()
            
            # Registrar auditoría
            cambios = []
            campos_nombres = {
                'modelo': 'Modelo',
                'lanzamiento': 'Lanzamiento',
                'cliente': 'Cliente',
                'tubo': 'Tubo',
                'encamisado': 'Encamisado',
                'tipo_tubo': 'Tipo Tubo',
                'tamano_cubierta': 'Tamaño Cubierta',
                'marca_cubiertas': 'Marca Cubiertas',
                'color': 'Color',
                'balanza': 'Balanza',
                'entregada': 'Entregada',
                'observaciones': 'Observaciones'
            }
            
            for campo, nombre in campos_nombres.items():
                valor_original = valores_originales[campo]
                valor_nuevo = data.get(campo, valor_original)
                if str(valor_original) != str(valor_nuevo):
                    cambios.append(f"{nombre}: {valor_original} → {valor_nuevo}")
            
            if cambios:
                detalles = f"EDITAR chasis {chasis.nro_chasis} ({plan.implemento}): " + ", ".join(cambios)
                registrar_auditoria(
                    current_user.id,
                    current_user.nombre,
                    'EDITAR_PRODUCCION',
                    f'Planilla de Producción - {plan.implemento}',
                    detalles
                )
            
            return jsonify({
                'success': True,
                'mensaje': 'Fila actualizada correctamente'
            })
        
        else:
            return jsonify({'success': False, 'error': 'Parámetros no válidos'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al procesar la solicitud: {str(e)}'
        }), 500

@app.route('/admin/importar_excel/<implemento>', methods=['POST'])
@login_required
def importar_excel(implemento):
    """Importar datos de Excel a la planilla de producción con validación de duplicados"""
    if current_user.rol != 'ADMIN':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    # Validar implemento
    implementos_validos = ['TOLVA', 'MIXER', 'EMBOLSADORA', 'ATT', 'SEMBRADORA']
    if implemento not in implementos_validos:
        return jsonify({'success': False, 'error': 'Implemento no válido'}), 400
    
    # Verificar archivo
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No se encontró archivo'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nombre de archivo vacío'}), 400
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Formato no válido. Solo Excel (.xlsx, .xls)'}), 400
    
    try:
        # Leer Excel
        df = pd.read_excel(file)
        
        # Validar columnas requeridas (solo las obligatorias principales)
        columnas_obligatorias = ['Nº CHASIS', 'LANZAMIENTO', 'CLIENTE']
        
        # Verificar que existan las columnas obligatorias
        for col_req in columnas_obligatorias:
            encontrada = False
            for col_excel in df.columns:
                if col_req.upper() == col_excel.upper().strip():
                    encontrada = True
                    break
            if not encontrada:
                return jsonify({
                    'success': False, 
                    'error': f'Columna obligatoria faltante: {col_req}',
                    'columnas_encontradas': df.columns.tolist(),
                    'columnas_requeridas': columnas_obligatorias
                }), 400
        
        # Obtener chasis existentes en la tabla específica del implemento
        if implemento == 'TOLVA':
            chasis_existentes = {c.nro_chasis for c in ChasisAsignadoTolva.query.all()}
        elif implemento == 'MIXER':
            chasis_existentes = {c.nro_chasis for c in ChasisAsignadoMixer.query.all()}
        elif implemento == 'ATT':
            chasis_existentes = {c.nro_chasis for c in ChasisAsignadoATT.query.all()}
        elif implemento == 'EMBOLSADORA':
            chasis_existentes = {c.nro_chasis for c in ChasisAsignadoEmbolsadora.query.all()}
        else:
            chasis_existentes = set()
        
        # Validar duplicados
        duplicados = []
        nuevos = []
        
        # Validar que las columnas obligatorias contengan datos
        for index, row in df.iterrows():
            # Debug: Mostrar valores originales antes de limpiar
            print(f"DEBUG ORIGINAL Fila {index + 2}:")
            print(f"  Nº CHASIS original: '{row.get('Nº CHASIS', 'NO_EXISTE')}'")
            print(f"  LANZAMIENTO original: '{row.get('LANZAMIENTO', 'NO_EXISTE')}'")
            print(f"  CLIENTE original: '{row.get('CLIENTE', 'NO_EXISTE')}'")
            print(f"  MODELO original: '{row.get('MODELO', 'NO_EXISTE')}'")
            print(f"  TUBO original: '{row.get('TUBO', 'NO_EXISTE')}'")
            print(f"  OBSERVACIONES original: '{row.get('OBSERVACIONES', 'NO_EXISTE')}'")
            
            # Limpieza de datos - leer exactamente como están en el Excel
            nro_chasis = str(row.get('Nº CHASIS', '')).strip()
            lanzamiento = str(row.get('LANZAMIENTO', '')).strip()
            cliente = str(row.get('CLIENTE', '')).strip()
            modelo = str(row.get('MODELO', '')).strip()
            tubo = str(row.get('TUBO', '')).strip()
            encamisado = str(row.get('ENCAMISADO', '')).strip()
            tipo_tubo = str(row.get('TIPO TUBO', '')).strip()
            tamano_cubierta = str(row.get('TAMAÑO DE CUBIERTA', '')).strip()
            marca_cubiertas = str(row.get('MARCA DE LAS CUBIERTAS', '')).strip()
            color = str(row.get('COLOR', '')).strip()
            balanza = str(row.get('BALANZA', '')).strip()
            observaciones = str(row.get('OBSERVACIONES', '')).strip()
            entregada = str(row.get('Entregada', '')).strip()
            fecha_entrega = str(row.get('Fecha de Entrega', '')).strip()
            pedido = str(row.get('Pedido', '')).strip()
            liberada_ventas = str(row.get('Liberada para VENTAS', '')).strip()
            llantas_ok = str(row.get('Llantas OK', '')).strip()
            cubiertas_ok = str(row.get('Cubiertas OK', '')).strip()
            observacion_2 = str(row.get('OBSERVACIÓN 2', '')).strip()
            proveedor_sinfin = str(row.get('PROVEEDOR DE SIN FIN', '')).strip()
            dias_consignacion = str(row.get('DIAS EN CONSIGNACION DESDE SU ENTREGA', '')).strip()
            
            # Debug: Mostrar qué datos se encontraron después de limpiar
            print(f"DEBUG LIMPIO Fila {index + 2}: Nº CHASIS='{nro_chasis}', LANZAMIENTO='{lanzamiento}', MODELO='{modelo}', CLIENTE='{cliente}', TUBO='{tubo}'")
            
            # Validar que las columnas obligatorias tengan datos
            columnas_vacias = []
            if not nro_chasis or nro_chasis == '':
                columnas_vacias.append('Nº CHASIS')
            if not lanzamiento or lanzamiento == '':
                columnas_vacias.append('LANZAMIENTO')
            if not cliente or cliente == '':
                columnas_vacias.append('CLIENTE')
            
            # Si hay 2 o más columnas vacías, rechazar
            if len(columnas_vacias) >= 2:
                return jsonify({
                    'success': False, 
                    'error': f'Fila {index + 2}: Se requieren datos en Nº CHASIS, LANZAMIENTO y CLIENTE. Columnas vacías: {", ".join(columnas_vacias)}',
                    'fila_vacia': index + 2,
                    'columnas_vacias': columnas_vacias
                }), 400
            
            if nro_chasis in chasis_existentes:
                duplicados.append({
                    'fila': index + 2,
                    'nro_chasis': nro_chasis,
                    'motivo': 'Ya existe en la base de datos'
                })
            else:
                nuevos.append({
                    'nro_chasis': nro_chasis,
                    'lanzamiento': lanzamiento,
                    'modelo': modelo,
                    'cliente': cliente,
                    'tubo': tubo,
                    'encamisado': encamisado,
                    'tipo_tubo': tipo_tubo,
                    'tamano_cubierta': tamano_cubierta,
                    'marca_cubiertas': marca_cubiertas,
                    'color': color,
                    'balanza': balanza,
                    'observaciones': observaciones,
                    'entregada': entregada,
                    'fecha_entrega': fecha_entrega,
                    'pedido': pedido,
                    'liberada_ventas': liberada_ventas,
                    'llantas_ok': llantas_ok,
                    'cubiertas_ok': cubiertas_ok,
                    'observacion_2': observacion_2,
                    'proveedor_sinfin': proveedor_sinfin,
                    'dias_consignacion': dias_consignacion,
                    'fila': index + 2
                })
        
        # Insertar datos nuevos en chasis_asignado (se ejecuta siempre)
        insertados = 0
        for datos in nuevos:
            try:
                # Crear un plan_producción básico para tener plan_id
                nuevo_plan = PlanProduccion(
                    nro_chasis=datos['nro_chasis'],
                    fecha=datos.get('lanzamiento', ''),
                    implemento=implemento,
                    estado='PENDIENTE',
                    sector='MONTAJE'
                )
                db.session.add(nuevo_plan)
                db.session.flush()  # Obtener el ID sin hacer commit
                plan_id = nuevo_plan.id
                
                # Crear en tabla específica según implemento
                if implemento == 'TOLVA':
                    nuevo_chasis = ChasisAsignadoTolva(
                        plan_id=plan_id,  # Ahora tenemos un plan_id válido
                        nro_chasis=datos['nro_chasis'],
                        modelo=datos.get('modelo', implemento),  # MODELO desde Excel
                        lanzamiento=datos.get('lanzamiento', ''),  # LANZAMIENTO
                        cliente=datos.get('cliente', ''),  # CLIENTE
                        tubo=datos.get('tubo', ''),  # TUBO
                        encamisado=datos.get('encamisado', ''),  # ENCAMISADO
                        tipo_tubo=datos.get('tipo_tubo', ''),  # TIPO TUBO
                        tamano_cubierta=datos.get('tamano_cubierta', ''),  # TAMAÑO DE CUBIERTA
                        marca_cubiertas=datos.get('marca_cubiertas', ''),  # MARCA DE LAS CUBIERTAS
                        color=datos.get('color', ''),  # COLOR
                        balanza=datos.get('balanza', ''),  # BALANZA
                        observaciones=datos.get('observaciones', ''),  # OBSERVACIONES
                        entregada=datos.get('entregada', ''),  # Entregada
                        fecha_entrega=datos.get('fecha_entrega', ''),  # Fecha de Entrega
                        pedido=datos.get('pedido', ''),  # Pedido
                        liberada_ventas=datos.get('liberada_ventas', ''),  # Liberada para VENTAS
                        llantas_ok=datos.get('llantas_ok', ''),  # Llantas OK
                        cubiertas_ok=datos.get('cubiertas_ok', ''),  # Cubiertas OK
                        observaciones_2=datos.get('observacion_2', ''),  # OBSERVACIÓN 2
                        proveedor_sinfin=datos.get('proveedor_sinfin', ''),  # PROVEEDOR DE SIN FIN
                        dias_consignacion=datos.get('dias_consignacion', '')  # DIAS EN CONSIGNACION DESDE SU ENTREGA
                    )
                else:
                    # Para otros implementos, no hacer nada (solo TOLVA, MIXER, ATT, EMBOLSADORA están soportados)
                    continue
                db.session.add(nuevo_chasis)
                insertados += 1
                print(f"✓ Fila {datos['fila']}: Chasis '{datos['nro_chasis']}' agregado con plan_id {plan_id}")
            except Exception as e:
                print(f"Error insertando chasis {datos['nro_chasis']}: {e}")
                db.session.rollback()
                continue
        
        # Commit a la base de datos
        if insertados > 0:
            db.session.commit()
            
            # Registrar auditoría
            detalles = f"IMPORTAR Excel {implemento}: {insertados} registros insertados"
            if duplicados:
                detalles += f", {len(duplicados)} duplicados omitidos"
            registrar_auditoria(
                current_user.id,
                current_user.nombre,
                'IMPORTAR_EXCEL',
                f'Planilla de Producción - {implemento}',
                detalles
            )
        
        # Ahora retornamos el resultado final
        if duplicados:
            return jsonify({
                'success': True,
                'warning': True,
                'mensaje': f'Se encontraron {len(duplicados)} chasis duplicados que se omitirán. {insertados} registros nuevos se importaron correctamente.',
                'insertados': insertados,  # Para el frontend
                'duplicados': len(duplicados),  # Para el frontend
                'total_duplicados': len(duplicados),
                'total_nuevos': len(nuevos),
                'total_insertados': insertados,
                'omitidos': len(duplicados)
            }), 200
        else:
            return jsonify({
                'success': True,
                'mensaje': f'Importación exitosa. {insertados} registros insertados.',
                'insertados': insertados,  # Para el frontend
                'total_insertados': insertados,
                'total_leidos': len(df)
            })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al procesar Excel: {str(e)}'
        }), 500



@app.route('/admin/buscar_chasis/<nro_chasis>')
@app.route('/admin/buscar_chasis/<nro_chasis>/<implemento>')
@login_required
def buscar_chasis(nro_chasis, implemento=None):
    """Buscar datos de un chasis específico para autocompletado"""
    if current_user.rol != 'ADMIN':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        # Si se especifica implemento, buscar directamente en la tabla correspondiente
        if implemento:
            chasis_asignado = None
            if implemento == 'TOLVA':
                chasis_asignado = ChasisAsignadoTolva.query.filter_by(nro_chasis=nro_chasis).first()
            elif implemento == 'MIXER':
                chasis_asignado = ChasisAsignadoMixer.query.filter_by(nro_chasis=nro_chasis).first()
            elif implemento == 'ATT':
                chasis_asignado = ChasisAsignadoATT.query.filter_by(nro_chasis=nro_chasis).first()
            elif implemento == 'EMBOLSADORA':
                chasis_asignado = ChasisAsignadoEmbolsadora.query.filter_by(nro_chasis=nro_chasis).first()
            
            if chasis_asignado:
                return jsonify({
                    'success': True,
                    'datos': {
                        'modelo': chasis_asignado.modelo,
                        'lanzamiento': chasis_asignado.lanzamiento,
                        'cliente': chasis_asignado.cliente,
                        'implemento': implemento
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'mensaje': f'Chasis {nro_chasis} no encontrado en {implemento}'
                })
        
        # Búsqueda original por si se llama sin implemento
        plan = PlanProduccion.query.filter_by(nro_chasis=nro_chasis).first()
        
        if not plan:
            return jsonify({
                'success': False,
                'mensaje': f'Chasis {nro_chasis} no encontrado en plan de producción'
            })
        
        # Buscar datos adicionales según el implemento
        chasis_asignado = None
        if plan.implemento == 'TOLVA':
            chasis_asignado = ChasisAsignadoTolva.query.filter_by(plan_id=plan.id).first()
        elif plan.implemento == 'MIXER':
            chasis_asignado = ChasisAsignadoMixer.query.filter_by(plan_id=plan.id).first()
        elif plan.implemento == 'ATT':
            chasis_asignado = ChasisAsignadoATT.query.filter_by(plan_id=plan.id).first()
        elif plan.implemento == 'EMBOLSADORA':
            chasis_asignado = ChasisAsignadoEmbolsadora.query.filter_by(plan_id=plan.id).first()
        
        # Combinar datos
        datos = {
            'id': plan.id,
            'nro_chasis': plan.nro_chasis,
            'modelo': chasis_asignado.modelo if chasis_asignado else plan.modelo,  # Desde chasis_asignado
            'implemento': plan.implemento,
            'fecha': plan.fecha,
            # Datos de chasis_asignado si existen
            'lanzamiento': chasis_asignado.lanzamiento if chasis_asignado else plan.fecha,
            'cliente': chasis_asignado.cliente if chasis_asignado else '',
            'tubo': chasis_asignado.tubo if chasis_asignado else '',
            'encamisado': chasis_asignado.encamisado if chasis_asignado else '',
            'tipo_tubo': chasis_asignado.tipo_tubo if chasis_asignado else '',
            'tamano_cubierta': chasis_asignado.tamano_cubierta if chasis_asignado else '',
            'marca_cubiertas': chasis_asignado.marca_cubiertas if chasis_asignado else '',
            'color': chasis_asignado.color if chasis_asignado else '',
            'balanza': chasis_asignado.balanza if chasis_asignado else '',
            'observaciones': chasis_asignado.observaciones if chasis_asignado else '',
            'entregada': chasis_asignado.entregada if chasis_asignado else '',
            'fecha_entrega': chasis_asignado.fecha_entrega if chasis_asignado else '',
            'pedido': chasis_asignado.pedido if chasis_asignado else '',
            'liberada_ventas': chasis_asignado.liberada_ventas if chasis_asignado else '',
            'llantas_ok': chasis_asignado.llantas_ok if chasis_asignado else '',
            'cubiertas_ok': chasis_asignado.cubiertas_ok if chasis_asignado else '',
            'observaciones_2': chasis_asignado.observaciones_2 if chasis_asignado else '',
            'proveedor_sinfin': chasis_asignado.proveedor_sinfin if chasis_asignado else '',
            'dias_consignacion': chasis_asignado.dias_consignacion if chasis_asignado else ''
        }
        
        return jsonify({
            'success': True,
            'datos': datos
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/agregar_fila_manual', methods=['POST'])
@login_required
def agregar_fila_manual():
    """Agregar una nueva fila manualmente"""
    if current_user.rol != 'ADMIN':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        
        # Validar datos obligatorios
        if not data.get('nro_chasis'):
            return jsonify({'error': 'El número de chasis es obligatorio'}), 400
        
        nro_chasis = data['nro_chasis']
        implemento = data.get('implemento', 'TOLVA')
        
        # Determinar qué tabla de chasis asignados usar según el implemento
        if implemento == 'TOLVA':
            ChasisAsignadoModel = ChasisAsignadoTolva
        elif implemento == 'MIXER':
            ChasisAsignadoModel = ChasisAsignadoMixer
        elif implemento == 'ATT':
            ChasisAsignadoModel = ChasisAsignadoATT
        elif implemento == 'EMBOLSADORA':
            ChasisAsignadoModel = ChasisAsignadoEmbolsadora
        else:
            ChasisAsignadoModel = ChasisAsignado  # Por defecto
        
        # Verificar si ya existe en la tabla correspondiente
        existente = ChasisAsignadoModel.query.filter_by(
            nro_chasis=nro_chasis
        ).first()
        
        if existente:
            return jsonify({'error': f'El chasis {nro_chasis} ya existe en la tabla de asignación'}), 400
        
        # Crear registro en plan_produccion
        nuevo_plan = PlanProduccion(
            nro_chasis=nro_chasis,
            fecha=data.get('lanzamiento', ''),
            implemento=implemento,
            estado='PENDIENTE',
            sector='MONTAJE'
        )
        db.session.add(nuevo_plan)
        db.session.flush()  # Obtener ID sin commit
        plan_id = nuevo_plan.id
        
        # Crear registro en la tabla de chasis asignados correspondiente
        nuevo_chasis = ChasisAsignadoModel(
            plan_id=plan_id,
            nro_chasis=nro_chasis,
            modelo=data.get('modelo', implemento),  # Agregar campo modelo
            lanzamiento=data.get('lanzamiento', ''),
            cliente=data.get('cliente', ''),
            tubo=data.get('tubo', ''),
            encamisado=data.get('encamisado', ''),
            tipo_tubo=data.get('tipo_tubo', ''),
            tamano_cubierta=data.get('tamano_cubierta', ''),
            marca_cubiertas=data.get('marca_cubiertas', ''),
            color=data.get('color', ''),
            balanza=data.get('balanza', ''),
            observaciones=data.get('observaciones', ''),
            entregada=data.get('entregada', ''),
            fecha_entrega=data.get('fecha_entrega', ''),
            pedido=data.get('pedido', ''),
            liberada_ventas=data.get('liberada_ventas', ''),
            llantas_ok=data.get('llantas_ok', ''),
            cubiertas_ok=data.get('cubiertas_ok', ''),
            observaciones_2=data.get('observaciones_2', ''),
            proveedor_sinfin=data.get('proveedor_sinfin', ''),
            dias_consignacion=data.get('dias_consignacion', '')
        )
        db.session.add(nuevo_chasis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mensaje': f'Chasis {nro_chasis} agregado correctamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error agregando fila: {str(e)}'}), 500

@app.route('/admin/eliminar_seleccionados', methods=['POST'])
@login_required
def eliminar_seleccionados():
    """Eliminar múltiples filas seleccionadas"""
    if current_user.rol != 'ADMIN':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        implemento = data.get('implemento', 'TOLVA')
        
        if not ids:
            return jsonify({'success': False, 'error': 'No se seleccionaron filas'}), 400
        
        print(f"DEBUG: Intentando eliminar {len(ids)} filas con IDs: {ids}")
        print(f"DEBUG: Implemento: {implemento}")
        
        # Determinar qué tabla usar según el implemento
        if implemento == 'TOLVA':
            ChasisAsignadoModel = ChasisAsignadoTolva
        elif implemento == 'MIXER':
            ChasisAsignadoModel = ChasisAsignadoMixer
        elif implemento == 'ATT':
            ChasisAsignadoModel = ChasisAsignadoATT
        elif implemento == 'EMBOLSADORA':
            ChasisAsignadoModel = ChasisAsignadoEmbolsadora
        else:
            return jsonify({'success': False, 'error': 'Implemento no válido'}), 400
        
        # Eliminar usando ORM para mayor robustez
        eliminados = 0
        for id in ids:
            try:
                chasis = ChasisAsignadoModel.query.get(id)
                if chasis:
                    db.session.delete(chasis)
                    eliminados += 1
                    print(f"DEBUG: Eliminado ID {id} - {chasis.nro_chasis}")
                else:
                    print(f"DEBUG: No se encontró chasis con ID {id}")
            except Exception as e:
                print(f"Error eliminando ID {id}: {e}")
                continue
        
        # Commit de todos los cambios
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mensaje': f'Se eliminaron {eliminados} registros correctamente.',
            'total_eliminados': eliminados
        })
    except Exception as e:
        print(f"ERROR: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al eliminar: {str(e)}'
        }), 500

@app.route('/admin/planilla_produccion/<implemento>')
@login_required
def planilla_produccion(implemento):
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    
    # Determinar sector y puesto según el implemento
    if implemento == 'MIXER':
        # Es MIXER - mostrar selección de modelos
        modelos_mixer = ['M1600', 'M2000', 'M2600']
        return render_template('admin_seleccion_mixer.html', implemento=implemento, modelos=modelos_mixer)
    elif implemento.startswith('M') and implemento in ['M1600', 'M2000', 'M2600']:
        # Es un modelo específico de MIXER - mostrar vista de conjuntos
        return redirect(url_for('admin_plan_mixer', implemento=implemento))
    else:
        # Es un implemento normal - mostrar planilla completa
        s_sel = request.args.get('sector', 'MONTAJE')
        p_sel = request.args.get('puesto', 'M5')
        
        # Determinar qué tabla de chasis asignados usar según el implemento
        if implemento == 'TOLVA':
            ChasisAsignadoModel = ChasisAsignadoTolva
        elif implemento == 'MIXER':
            ChasisAsignadoModel = ChasisAsignadoMixer
        elif implemento == 'ATT':
            ChasisAsignadoModel = ChasisAsignadoATT
        elif implemento == 'EMBOLSADORA':
            ChasisAsignadoModel = ChasisAsignadoEmbolsadora
        else:
            ChasisAsignadoModel = ChasisAsignado  # Por defecto
        
        # OPTIMIZACIÓN: Consulta optimizada para obtener todos los datos en una sola consulta
        # Usar LEFT JOIN para mostrar chasis_asignados incluso si no tienen plan_produccion
        if implemento == 'TOLVA':
            # Para TOLVA, mostrar todos los chasis asignados aunque no tengan plan de producción
            chasis_asignados_query = db.session.query(ChasisAsignadoTolva).filter(
                ChasisAsignadoTolva.nro_chasis.isnot(None)
            )
        else:
            # Para otros implementos, mantener la lógica original con LEFT JOIN
            chasis_asignados_query = db.session.query(ChasisAsignadoModel).outerjoin(
                PlanProduccion, 
                (ChasisAsignadoModel.plan_id == PlanProduccion.id) & 
                (ChasisAsignadoModel.nro_chasis == PlanProduccion.nro_chasis)
            ).filter(PlanProduccion.implemento == implemento)
        
        # Agrupar por nro_chasis y tomar el primer registro de cada chasis
        chasis_vistos = set()
        chasis_asignados = []
        for chasis in chasis_asignados_query.all():
            if chasis.nro_chasis not in chasis_vistos:
                chasis_asignados.append(chasis)
                chasis_vistos.add(chasis.nro_chasis)
        
        # Obtener todos los planes de una sola vez y agrupar por nro_chasis
        todos_los_planes = PlanProduccion.query.all()
        planes_por_chasis = {}
        for plan in todos_los_planes:
            if plan.nro_chasis not in planes_por_chasis:
                planes_por_chasis[plan.nro_chasis] = []
            planes_por_chasis[plan.nro_chasis].append(plan)
        
        # Para cada chasis asignado, obtener su estado y datos del plan si existe
        planilla_datos = []
        for chasis_asignado in chasis_asignados:
            # Obtener planes para este chasis desde el diccionario (sin consulta a BD)
            planes_chasis = planes_por_chasis.get(chasis_asignado.nro_chasis, [])
            
            # Priorizar estados: TERMINADO > EN_PROGRESO > PENDIENTE
            plan = None
            if planes_chasis:
                # Buscar primero si hay alguno TERMINADO
                plan = next((p for p in planes_chasis if p.estado == 'TERMINADO'), None)
                # Si no hay TERMINADO, buscar EN_PROGRESO
                if not plan:
                    plan = next((p for p in planes_chasis if p.estado == 'EN_PROGRESO'), None)
                # Si no hay ninguno de los anteriores, tomar el primero (será PENDIENTE)
                if not plan:
                    plan = planes_chasis[0]
            
            # Determinar el estado y color según el estado del plan
            if plan and plan.estado == 'TERMINADO':
                estado_color = 'success'  # Verde
                estado_texto = 'TERMINADO'
            elif plan and plan.estado == 'EN_PROGRESO':
                estado_color = 'warning'  # Amarillo
                estado_texto = 'EN_PROGRESO'
            else:  # PENDIENTE o cualquier otro
                estado_color = 'danger'   # Rojo
                estado_texto = 'PENDIENTE'
            
            # Crear un diccionario de estados por puesto para fácil acceso
            estados_por_puesto = {}
            
            if planes_chasis:
                # Si tiene plan, usar los estados reales del plan
                for p in planes_chasis:
                    if p.puesto_conjunto:
                        estados_por_puesto[p.puesto_conjunto] = p.estado
            else:
                # Si no tiene plan (ya terminado), marcar todos los puestos como TERMINADO
                # Lista de todos los puestos posibles para marcar como completados
                todos_los_puestos = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'LAVADO', 'PINTURA', 'M1', 'M2', 'M3', 'M4', 'M5']
                for puesto in todos_los_puestos:
                    estados_por_puesto[puesto] = 'TERMINADO'
            
            # Combinar datos del chasis con estado y datos del plan si existe
            plan_data = {
                'id': chasis_asignado.id,
                'fecha': plan.fecha if plan else chasis_asignado.lanzamiento,
                'implemento': plan.implemento if plan else 'TOLVA',  # Del plan_produccion relacionado
                'sector': plan.sector if plan else 'MONTAJE',
                'puesto_conjunto': plan.puesto_conjunto if plan else 'M5',
                'nro_chasis': chasis_asignado.nro_chasis,  # Este viene de chasis_asignado
                'modelo': chasis_asignado.modelo if chasis_asignado else 'TOLVA',  # MODELO desde chasis_asignado
                'estado': plan.estado if plan else 'PENDIENTE',
                'estado_color': estado_color,
                'estado_texto': estado_texto,
                # Datos del chasis asignado
                'lanzamiento': chasis_asignado.lanzamiento,
                'cliente': chasis_asignado.cliente,
                'tubo': chasis_asignado.tubo,
                'encamisado': chasis_asignado.encamisado,
                'tipo_tubo': chasis_asignado.tipo_tubo,
                'tamano_cubierta': chasis_asignado.tamano_cubierta,
                'marca_cubiertas': chasis_asignado.marca_cubiertas,
                'color': chasis_asignado.color,
                'balanza': chasis_asignado.balanza,
                'observaciones': chasis_asignado.observaciones,
                'entregada': chasis_asignado.entregada,
                'fecha_entrega': chasis_asignado.fecha_entrega,
                'pedido': chasis_asignado.pedido,
                'liberada_ventas': chasis_asignado.liberada_ventas,
                'llantas_ok': chasis_asignado.llantas_ok,
                'cubiertas_ok': chasis_asignado.cubiertas_ok,
                'observaciones_2': chasis_asignado.observaciones_2,
                'proveedor_sinfin': chasis_asignado.proveedor_sinfin,
                'dias_consignacion': chasis_asignado.dias_consignacion,
                # Agregar todos los estados por puesto
                'estados_por_puesto': estados_por_puesto
            }
            
            planilla_datos.append(plan_data)
        
        # Estructura para desplegables
        estructura = {}
        for s in ['MONTAJE', 'SOLDADURA', 'PINTURA']:
            puestos_db = db.session.query(PlanProduccion.puesto_conjunto).filter_by(sector=s).distinct().all()
            estructura[s] = [p[0] for p in puestos_db if p[0]]

        return render_template('planilla_produccion.html', 
                             planilla_datos=planilla_datos, 
                             s_sel=s_sel, 
                             p_sel=p_sel, 
                             estructura=estructura,
                             implemento=implemento)

@app.route('/admin/cambiar_estado/<int:id>')
@login_required
def cambiar_estado_admin(id):
    try:
        item = PlanProduccion.query.get_or_404(id)
        nuevo_estado = request.args.get('estado')
        item.estado = nuevo_estado
        item.usuario_avance = f"ADMIN: {current_user.nombre}"
        db.session.commit()
        return jsonify({"status": "ok", "message": "Estado actualizado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar estado: {str(e)}"})


@app.route('/admin/cambiar_estado_multiple', methods=['POST'])
@login_required
def cambiar_estado_multiple():
    """Cambia el estado de múltiples planes a la vez."""
    data = request.get_json()
    ids = data.get('ids', [])
    nuevo_estado = data.get('estado')
    
    if not ids or not nuevo_estado:
        return jsonify({"success": False, "error": "IDs o estado faltante"}), 400
    
    count = 0
    for plan_id in ids:
        try:
            item = PlanProduccion.query.get(plan_id)
            if item:
                item.estado = nuevo_estado
                item.usuario_avance = f"ADMIN: {current_user.nombre}"
                count += 1
        except:
            pass
    
    db.session.commit()
    return jsonify({"success": True, "count": count})

@app.route('/admin/cambiar_estado_puesto', methods=['POST'])
@login_required
def cambiar_estado_puesto():
    """Cambia el estado de un puesto específico para un chasis."""
    try:
        data = request.get_json()
        chasis = data.get('chasis')
        puesto = data.get('puesto')
        nuevo_estado = data.get('nuevo_estado')
        implemento = data.get('implemento')
        
        if not all([chasis, puesto, nuevo_estado, implemento]):
            return jsonify({"success": False, "error": "Faltan datos requeridos"}), 400
        
        # Validar que el estado sea válido
        estados_validos = ['PENDIENTE', 'EN_PROGRESO', 'TERMINADO']
        if nuevo_estado not in estados_validos:
            return jsonify({"success": False, "error": "Estado no válido"}), 400
        
        # Buscar si ya existe un registro para este chasis, puesto y sector
        # Determinar el sector según el puesto
        if puesto.startswith('P'):
            sector = 'SOLDADURA'
        elif puesto in ['LAVADO', 'PINTURA']:
            sector = 'PINTURA'
        elif puesto.startswith('M'):
            sector = 'MONTAJE'
        else:
            sector = 'MONTAJE'  # Por defecto
        
        # Buscar registro existente
        plan_existente = PlanProduccion.query.filter_by(
            nro_chasis=chasis,
            puesto_conjunto=puesto,
            sector=sector,
            implemento=implemento
        ).first()
        
        if plan_existente:
            # Actualizar el registro existente
            plan_existente.estado = nuevo_estado
            plan_existente.usuario_avance = f"ADMIN: {current_user.nombre}"
            plan_existente.fecha = datetime.now().strftime('%Y-%m-%d')
        else:
            # Crear un nuevo registro
            nuevo_plan = PlanProduccion(
                nro_chasis=chasis,
                puesto_conjunto=puesto,
                sector=sector,
                implemento=implemento,
                estado=nuevo_estado,
                usuario_avance=f"ADMIN: {current_user.nombre}",
                fecha=datetime.now().strftime('%Y-%m-%d')
            )
            db.session.add(nuevo_plan)
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"Estado del puesto {puesto} actualizado a {nuevo_estado}"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Error al actualizar estado: {str(e)}"}), 500

@app.route('/admin/obtener_alertas/<int:plan_id>')
@login_required
def obtener_alertas(plan_id):
    alertas = AlertaCalidad.query.filter_by(plan_id=plan_id).all()
    return jsonify([{
        "usuario": a.usuario,
        "descripcion": a.descripcion,
        "fecha": a.fecha.strftime('%d/%m/%Y %H:%M'),
        "imagen": a.imagen
    } for a in alertas])


@app.route('/admin/editar_chasis_asignado', methods=['POST'])
@login_required
def editar_chasis_asignado():
    if current_user.rol != 'ADMIN': 
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
        
        id_fila = data.get('id')
        if not id_fila:
            return jsonify({'success': False, 'error': 'ID de fila no proporcionado'}), 400
        
        # Buscar el registro en ChasisAsignado
        chasis = ChasisAsignado.query.get_or_404(id_fila)
        
        # Actualizar solo los campos que se pueden editar
        chasis.cliente = data.get('cliente', chasis.cliente)
        chasis.tubo = data.get('tubo', chasis.tubo)
        chasis.encamisado = data.get('encamisado', chasis.encamisado)
        chasis.tipo_tubo = data.get('tipo_tubo', chasis.tipo_tubo)
        chasis.tamano_cubierta = data.get('tamano_cubierta', chasis.tamano_cubierta)
        chasis.marca_cubiertas = data.get('marca_cubiertas', chasis.marca_cubiertas)
        chasis.color = data.get('color', chasis.color)
        chasis.balanza = data.get('balanza', chasis.balanza)
        chasis.observaciones = data.get('observaciones', chasis.observaciones)
        chasis.entregada = data.get('entregada', chasis.entregada)
        chasis.fecha_entrega = data.get('fecha_entrega', chasis.fecha_entrega)
        chasis.pedido = data.get('pedido', chasis.pedido)
        chasis.liberada_ventas = data.get('liberada_ventas', chasis.liberada_ventas)
        chasis.llantas_ok = data.get('llantas_ok', chasis.llantas_ok)
        chasis.cubiertas_ok = data.get('cubiertas_ok', chasis.cubiertas_ok)
        chasis.observaciones_2 = data.get('observaciones_2', chasis.observaciones_2)
        chasis.proveedor_sinfin = data.get('proveedor_sinfin', chasis.proveedor_sinfin)
        chasis.dias_consignacion = data.get('dias_consignacion', chasis.dias_consignacion)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Chasis actualizado correctamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'error': f'Error al actualizar chasis: {str(e)}'
        }), 500

# MODIFICAR SOLO UNA FILA)
@app.route('/admin/editar_fila', methods=['POST'])
@login_required
def editar_fila():
    id_fila = request.form.get('id')
    fila = PlanProduccion.query.get_or_404(id_fila)
    
    # Solo actualizar la fecha, los demás campos son de solo lectura
    # ya que se consultan de las tablas chasis_asignacion_*
    fila.fecha = request.form.get('fecha')
    
    db.session.commit()
    flash("Fecha actualizada correctamente")
    return redirect(request.referrer) # Vuelve a la misma vista filtrada

# Ruta para el botón de "Nuevo Chasis" (Si decides usar el formulario manual)
@app.route('/admin/add_manual', methods=['POST']) # Antes decía /admin/agregar_manual
@login_required
def agregar_manual():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    
    nuevo_plan = PlanProduccion(
        fecha=request.form.get('fecha'),
        nro_chasis=request.form.get('nro_chasis'),
        implemento=request.form.get('implemento'),
        sector=request.form.get('sector'),
        puesto_conjunto=request.form.get('puesto'),
        estado='PENDIENTE' # Por defecto entra pendiente
    )
    
    try:
        db.session.add(nuevo_plan)
        db.session.commit()
        flash("✅ Chasis agregado correctamente al plan de producción", "success")
    except:
        db.session.rollback()
        # Si el chasis ya existe, fallará por el UNIQUE
        flash("❌ Error: El chasis ya existe en el plan de producción", "error")
    
    return redirect(url_for('admin_plan', sector=nuevo_plan.sector, puesto=nuevo_plan.puesto_conjunto))


# --- SECCIÓN NUEVA: RUTAS DE CALIDAD Y PLAYÓN ---

import uuid # Para nombres de archivo únicos

@app.route('/admin/calidad')
@login_required
def admin_calidad():
    if current_user.rol != 'ADMIN': 
        return redirect(url_for('login'))
    
    # Redirigir al nuevo dashboard del Sistema de Gestión de Calidad
    return redirect(url_for('calidad_dashboard'))

@app.route('/admin/upload', methods=['POST'])
@login_required
def importar_excel_general():
    # 1. Verificación de seguridad
    if current_user.rol != 'ADMIN':
        flash("Acceso denegado")
        return redirect(url_for('login'))
    
    # 2. Obtener el archivo desde el input name="file" del HTML
    file = request.files.get('file')
    
    if not file or file.filename == '':
        flash("No seleccionaste ningún archivo")
        return redirect(request.referrer)

    try:
        # 3. Leer el archivo (Excel o CSV)
        if file.filename.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        elif file.filename.lower().endswith('.csv'):
            df = pd.read_csv(file)
        else:
            flash("Formato de archivo no soportado (debe ser .xlsx, .xls o .csv)")
            return redirect(request.referrer)

        # 4. Normalizar encabezados: pasar a minúsculas y quitar espacios
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # DEBUG: Mostrar columnas encontradas
        print(f"\n=== DEBUG EXCEL ===")
        print(f"Columnas en Excel: {list(df.columns)}")
        print(f"Total de filas a procesar: {len(df)}\n")

        # Detectar si es formato clave-valor (columnas 'key', 'value')
        if list(df.columns) == ['key', 'value']:
            print("DEBUG: Detectado formato clave-valor, procesando múltiples registros...")
            
            # Agrupar filas en registros completos
            registros = []
            registro_actual = {}
            chasis_no_encontrados = []  # Lista para guardar los chasis no encontrados
            
            for idx, row in df.iterrows():
                key = str(row['key']).strip().lower()
                value = str(row['value']).strip()
                
                if key and value and value.lower() != 'nan':
                    registro_actual[key] = value
                    
                    # Si tenemos todas las columnas requeridas, guardamos el registro
                    if all(k in registro_actual for k in ['fecha', 'chasis', 'sector', 'puesto']):
                        registros.append(registro_actual.copy())
                        registro_actual = {}
            
            # Agregar el último registro si quedó incompleto pero tiene chasis
            if registro_actual and 'chasis' in registro_actual:
                registros.append(registro_actual)
            
            print(f"DEBUG: Se encontraron {len(registros)} registros completos")
            
            # Procesar los registros encontrados
            contador_nuevos = 0
            contador_omitidos = 0
            contador_no_existentes = 0

            # Obtener todos los chasis existentes en chasis_asignado_tolva
            chasis_existentes_tolva = {c.nro_chasis for c in ChasisAsignadoTolva.query.all()}
            print(f"DEBUG: Chasis existentes en chasis_asignado_tolva: {len(chasis_existentes_tolva)}")

            for idx, datos_tabular in enumerate(registros):
                print(f"DEBUG: Procesando registro {idx+1}: {datos_tabular}")
                
                # Extraer datos del registro
                chasis = str(datos_tabular.get('chasis', '')).strip()
                
                # Si la celda de chasis está vacía, saltar
                if not chasis or chasis.lower() == 'nan':
                    print(f"DEBUG: Registro {idx+1} omitido - Sin chasis")
                    continue

                # Validar que el chasis exista en chasis_asignado_tolva
                if chasis not in chasis_existentes_tolva:
                    print(f"DEBUG: Registro {idx+1} omitido - Chasis '{chasis}' no existe en chasis_asignado_tolva")
                    contador_no_existentes += 1
                    chasis_no_encontrados.append(chasis)  # Agregar a la lista
                    continue

                # Limpiar otros campos
                sector_val = str(datos_tabular.get('sector', '')).strip().upper()
                puesto_val = str(datos_tabular.get('puesto', '')).strip().upper()
                fecha_val = str(datos_tabular.get('fecha', '')).strip()
                
                # Validación: Si falta sector, puesto o fecha, reportar error
                if not sector_val or not puesto_val or not fecha_val:
                    print(f"DEBUG: Registro {idx+1} omitido - Faltan datos. Chasis: {chasis}, Sector: {sector_val}, Puesto: {puesto_val}, Fecha: {fecha_val}")
                    contador_omitidos += 1
                    continue

                # Verificación de Duplicados (Chasis + Sector + Puesto)
                existe = PlanProduccion.query.filter_by(
                    nro_chasis=chasis,
                    sector=sector_val,
                    puesto_conjunto=puesto_val
                ).first()

                if not existe:
                    # Crear nuevo registro
                    nuevo = PlanProduccion(
                        fecha=fecha_val,
                        implemento='TOLVA',  # Agregar el implemento por defecto
                        sector=sector_val,
                        puesto_conjunto=puesto_val,
                        nro_chasis=chasis,
                        estado='PENDIENTE',
                        usuario_avance='',
                        hora_fin=None
                    )
                    db.session.add(nuevo)
                    contador_nuevos += 1
                    print(f"✓ Registro {idx+1}: Chasis '{chasis}' agregado a {sector_val}/{puesto_val}")
                else:
                    contador_omitidos += 1
                    print(f"⊘ Registro {idx+1}: Chasis '{chasis}' YA EXISTE en {sector_val}/{puesto_val}")
            
            # Guardar todos los cambios
            if contador_nuevos > 0:
                db.session.commit()
            
            mensaje = f"Carga finalizada. {contador_nuevos} registros nuevos."
            if contador_omitidos > 0:
                mensaje += f" {contador_omitidos} ya existían o tenían errores y se omitieron."
            if contador_no_existentes > 0:
                mensaje += f" {contador_no_existentes} no existen en chasis_asignado_tolva y se omitieron."
            
            # Devolver JSON con los detalles para el frontend
            return jsonify({
                'success': True,
                'message': mensaje,
                'contador_nuevos': contador_nuevos,
                'contador_omitidos': contador_omitidos,
                'contador_no_existentes': contador_no_existentes,
                'chasis_no_encontrados': chasis_no_encontrados
            })
        
        # Si no es formato clave-valor, procesar como formato tabular normal
        contador_nuevos = 0
        contador_omitidos = 0
        contador_no_existentes = 0
        chasis_no_encontrados = []  # Lista para guardar los chasis no encontrados

        # Obtener todos los chasis existentes en chasis_asignado_tolva
        chasis_existentes_tolva = {c.nro_chasis for c in ChasisAsignadoTolva.query.all()}
        print(f"DEBUG: Chasis existentes en chasis_asignado_tolva: {len(chasis_existentes_tolva)}")

        # 5. Procesar cada fila
        for idx, row in df.iterrows():
            # Extraer y limpiar datos básicos
            # Busca 'chasis' o 'nro_chasis' (flexible para diferentes formatos de Excel)
            chasis = str(row.get('chasis', '') or row.get('nro_chasis', '')).strip()
            
            # Si la celda de chasis está vacía o es 'nan', saltar fila
            if not chasis or chasis.lower() == 'nan':
                continue

            # Validar que el chasis exista en chasis_asignado_tolva
            if chasis not in chasis_existentes_tolva:
                print(f"DEBUG: Fila {idx+1} omitida - Chasis '{chasis}' NO EXISTE en chasis_asignado_tolva")
                contador_no_existentes += 1
                chasis_no_encontrados.append(chasis)  # Agregar a la lista de no encontrados
                continue

            # Limpiar otros campos para evitar errores de búsqueda
            sector_val = str(row.get('sector', '')).strip().upper()
            puesto_val = str(row.get('puesto', '')).strip().upper()
            fecha_val = str(row.get('fecha', '')).strip()
            
            # Validación: Si falta sector, puesto o fecha, reportar error
            if not sector_val or not puesto_val or not fecha_val:
                print(f"DEBUG: Fila {idx+1} omitida - Faltan datos requeridos. Chasis: {chasis}, Sector: {sector_val}, Puesto: {puesto_val}, Fecha: {fecha_val}")
                contador_omitidos += 1
                continue

            # 6. Verificación de Duplicados (Chasis + Sector + Puesto)
            # Esto evita que cargues dos veces la misma etapa del mismo chasis
            existe = PlanProduccion.query.filter_by(
                nro_chasis=chasis,
                sector=sector_val,
                puesto_conjunto=puesto_val
            ).first()

            if not existe:
                # 7. Crear nuevo registro
                nuevo = PlanProduccion(
                    fecha=fecha_val,
                    implemento='TOLVA',  # Agregar el implemento por defecto
                    sector=sector_val,
                    puesto_conjunto=puesto_val,
                    nro_chasis=chasis,
                    estado='PENDIENTE',
                    usuario_avance='',  # Se inicializa vacío para el operario
                    hora_fin=None       # Se inicializa vacío
                )
                db.session.add(nuevo)
                contador_nuevos += 1
                print(f"✓ Fila {idx+1}: Chasis '{chasis}' agregado a {sector_val}/{puesto_val}")
            else:
                contador_omitidos += 1
                print(f"⊘ Fila {idx+1}: Chasis '{chasis}' YA EXISTE (duplicado omitido)")
        
        # 8. Guardar en la base de datos
        db.session.commit()
        
        mensaje = f"Carga finalizada. {contador_nuevos} registros nuevos."
        if contador_omitidos > 0:
            mensaje += f" {contador_omitidos} ya existían y se omitieron."
        if contador_no_existentes > 0:
            mensaje += f" {contador_no_existentes} no existen en chasis_asignado_tolva y se omitieron."
        
        # Devolver JSON con los detalles para el frontend
        return jsonify({
            'success': True,
            'message': mensaje,
            'contador_nuevos': contador_nuevos,
            'contador_omitidos': contador_omitidos,
            'contador_no_existentes': contador_no_existentes,
            'chasis_no_encontrados': chasis_no_encontrados
        })

    except Exception as e:
        db.session.rollback()
        # Imprime el error en la consola y en la interfaz
        error_msg = str(e)
        print(f"DEBUG ERROR EXCEL: {error_msg}")
        return jsonify({
            'success': False,
            'message': f"❌ Error al procesar Excel: {error_msg}. Verifica los nombres de columnas: chasis, sector, puesto, fecha"
        })
    
    # 9. Regresar a la página anterior manteniendo los filtros
    return redirect(request.referrer or url_for('admin_plan'))

@app.route('/admin/delete/<int:id>')
@login_required
def delete_plan(id):
    fila = PlanProduccion.query.get_or_404(id)
    
    db.session.delete(fila)
    db.session.commit()
    
    # Regresar a la página anterior manteniendo todos los filtros (implemento, sector, puesto)
    return redirect(request.referrer or url_for('admin_plan'))


@app.route('/admin/toggle_cubiertas', methods=['POST'])
@login_required
def toggle_cubiertas():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    
    plan_id = request.form.get('plan_id')
    plan = PlanProduccion.query.get(plan_id)
    
    if plan:
        plan.cubiertas = not bool(plan.cubiertas)
        db.session.commit()
        flash('Estado de cubiertas actualizado')
    
    return redirect(request.referrer)


@app.route('/admin/indicadores')
@login_required
def admin_indicadores():
    if current_user.rol != 'ADMIN':
        return redirect(url_for('login'))

    # Lista de implementos para selector
    implementos = db.session.query(PlanProduccion.implemento).distinct().filter(
        PlanProduccion.implemento != None, PlanProduccion.implemento != ''
    ).all()
    implementos = [i[0] for i in implementos if i[0]]

    selected_impl = request.args.get('implemento', '')

    # Definimos la estructura de puestos por sector (igual que en seleccion_puesto)
    estructura = {
        'SOLDADURA': ['P1','P2','P3','P4','P5','P6','P7','P8','P9'],
        'PINTURA': ['LAVADO','PINTURA'],
        'MONTAJE': ['M1','M2','M3','M4','M5']
    }

    hoy = datetime.now().date()
    anio_actual = hoy.year

    # Construimos resumen mensual por implemento y por los últimos 3 puestos de cada sector
    implementos_a_considerar = [selected_impl] if selected_impl else implementos
    mensual = []

    for imp in implementos_a_considerar:
        imp_entry = {'implemento': imp, 'sectors': []}
        for sector, puestos_list in estructura.items():
            ultimos = puestos_list[-3:]
            sector_entry = {'sector': sector, 'puestos': []}
            for puesto in ultimos:
                puesto_entry = {'puesto': puesto, 'months': []}
                for m in range(1,13):
                    plan_count = 0
                    done_count = 0
                    registros = PlanProduccion.query.filter_by(implemento=imp, sector=sector, puesto_conjunto=puesto).all()
                    for r in registros:
                        try:
                            sched = datetime.strptime(str(r.fecha), '%d/%m/%Y').date()
                        except:
                            continue
                        if sched.year == anio_actual and sched.month == m:
                            plan_count += 1
                            if r.hora_fin:
                                try:
                                    hf = r.hora_fin.date()
                                    if hf.year == anio_actual and hf.month == m:
                                        done_count += 1
                                except:
                                    pass
                    puesto_entry['months'].append({'month': m, 'plan': plan_count, 'done': done_count})
                sector_entry['puestos'].append(puesto_entry)
            imp_entry['sectors'].append(sector_entry)
        mensual.append(imp_entry)

    return render_template('indicadores.html', implementos=implementos, selected_impl=selected_impl, mensual=mensual, anio_actual=anio_actual)


@app.route('/admin/playon')
@login_required
def admin_playon():
    if current_user.rol != 'ADMIN': 
        return redirect(url_for('login'))
    
    # 1. Traemos todas las celdas (las 80 que creamos de A a H)
    celdas = CeldaPlayon.query.all()
    
    # 2. Traemos solo los implementos que cumplen estas 3 condiciones:
    #    - Estado 'TERMINADO' (El operario ya le dio click a finalizar)
    #    - Puesto 'M5' (Es el último eslabón de la cadena)
    #    - ubicacion_celda es None (Todavía no se le asignó un lugar en el playón)
    listos = PlanProduccion.query.filter(
        PlanProduccion.estado == 'TERMINADO',
        PlanProduccion.puesto_conjunto == 'M5',
        PlanProduccion.ubicacion_celda == None
    ).all() 
    
    return render_template('playon_despacho.html', celdas=celdas, listos=listos)


@app.route('/admin/playon_dashboard')
@login_required
def admin_playon_dashboard():
    if current_user.rol != 'ADMIN':
        return redirect(url_for('login'))

    # Traemos todas las celdas
    celdas = CeldaPlayon.query.order_by(CeldaPlayon.codigo).all()
    
    # Traemos todos los planes en PLAYON
    planes_playon = PlanProduccion.query.filter_by(estado='PLAYON').all()
    
    # Para cada plan, obtener el modelo desde chasis_asignado
    for plan in planes_playon:
        chasis_asignado = ChasisAsignado.query.filter_by(
            plan_id=plan.id, 
            nro_chasis=plan.nro_chasis
        ).first()
        plan.modelo = chasis_asignado.modelo if chasis_asignado else plan.modelo
    
    # Estadísticas básicas
    total_playon = len(planes_playon)
    en_stock = sum(1 for p in planes_playon if not p.con_cliente)
    con_cliente = sum(1 for p in planes_playon if p.con_cliente)

    # Breakdown por implemento
    implemento_counts = {}
    for plan in planes_playon:
        impl = plan.implemento or 'Sin especificar'
        implemento_counts[impl] = implemento_counts.get(impl, 0) + 1
    
    implemento_breakdown = sorted(implemento_counts.items(), key=lambda x: x[1], reverse=True)

    # Planes agrupados por con_cliente
    now_dt = datetime.now()
    for plan in planes_playon:
        fecha = plan.fecha_playon or plan.hora_fin
        if fecha:
            delta = now_dt - fecha
            days = delta.days
            hours = int(delta.seconds/3600)
            plan.fecha_playon_human = fecha.strftime('%d/%m/%Y %H:%M')
            plan.tiempo_playon = f"{days}d {hours}h"
        else:
            plan.fecha_playon_human = '-'
            plan.tiempo_playon = '-'

    planes_sin_cliente = [p for p in planes_playon if not p.con_cliente]
    planes_con_cliente = [p for p in planes_playon if p.con_cliente]

    stats = {
        'total_playon': total_playon, 
        'en_stock': en_stock, 
        'con_cliente': con_cliente,
        'implemento_breakdown': implemento_breakdown
    }
    
    return render_template('playon_dashboard.html', 
                          stats=stats,
                          celdas=celdas,
                          planes_sin_cliente=planes_sin_cliente, 
                          planes_con_cliente=planes_con_cliente)


# --- RUTAS OPERATIVAS DEL PLAYÓN ---

@app.route('/admin/estacionar', methods=['POST'])
@login_required
def estacionar_chasis():
    celda_codigo = request.form.get('celda_codigo')
    plan_id = request.form.get('plan_id')
    
    celda = CeldaPlayon.query.filter_by(codigo=celda_codigo).first()
    plan = PlanProduccion.query.get(plan_id)
    
    if celda and plan:
        # Actualizamos la celda
        celda.estado = 'OCUPADO'
        celda.chasis_id = plan.id
        # Actualizamos el plan del implemento
        plan.estado = 'PLAYON'
        plan.ubicacion_celda = celda_codigo
        # Registrar fecha de ingreso al playón y asegurar flags
        try:
            plan.fecha_playon = datetime.now()
        except:
            plan.fecha_playon = None
        if not hasattr(plan, 'cubiertas'):
            plan.cubiertas = False
        if not hasattr(plan, 'con_cliente'):
            plan.con_cliente = False
        
        db.session.commit()
        flash(f"Implemento {plan.nro_chasis} ubicado en {celda_codigo}")
    
    return redirect(url_for('admin_playon'))

@app.route('/admin/despachar', methods=['POST'])
@login_required
def despachar_chasis():
    celda_codigo = request.form.get('celda_codigo')
    celda = CeldaPlayon.query.filter_by(codigo=celda_codigo).first()
    
    if celda and celda.chasis_id:
        plan = PlanProduccion.query.get(celda.chasis_id)
        
        # Procesamos las observaciones
        plan.observaciones_despacho = request.form.get('observaciones')
        plan.fecha_despacho = datetime.now()
        plan.estado = 'DESPACHADO'
        
        # Manejo de FOTOS (Lógica básica para guardar archivos)
        fotos = request.files.getlist('fotos')
        nombres_fotos = []
        for foto in fotos:
            if foto.filename != '':
                filename = f"DESP_{plan.nro_chasis}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.filename}"
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                nombres_fotos.append(filename)
        
        if nombres_fotos:
            plan.fotos_despacho = ",".join(nombres_fotos)

        # Liberamos la celda
        celda.estado = 'LIBRE'
        celda.chasis_id = None
        # Limpiamos flags relacionados
        try:
            plan.fecha_playon = None
        except:
            pass
        try:
            plan.cubiertas = False
        except:
            pass
        try:
            plan.con_cliente = False
        except:
            pass
        
        db.session.commit()
        flash(f"Despacho exitoso de la unidad {plan.nro_chasis}. Celda {celda_codigo} liberada.")
        
    return redirect(url_for('admin_playon'))

# ---Sección 5: Operarios (Carga de Avances)--------------------------------------------------------------


@app.route('/operario/ver_plan')
@login_required
def ver_plan_operario():
    imp = request.args.get('implemento')
    sec = request.args.get('sector')
    pue = request.args.get('puesto')
    
    hoy_dt = datetime.now().date()
    hoy_str = hoy_dt.strftime('%d/%m/%Y') # Adaptado a tu formato de fecha en DB
    
    # VERIFICAR SI ES UN MIXER (lógica diferente)
    if imp and imp.startswith('M') and imp in ['M1600', 'M2000', 'M2600']:
        return redirect(url_for('ver_plan_mixer', implemento=imp))
    
    # CALCULAMOS LOS DÍAS HÁBILES REALES (saltando feriados y findes)
    dias_pasados = obtener_dias_habiles(hoy_dt, 3, "pasado")
    dias_futuros = obtener_dias_habiles(hoy_dt, 1, "futuro") # Solo el próximo día hábil
    
    # 1. Pasados (Solo los 3 últimos días hábiles)
    pasados = PlanProduccion.query.filter(
        PlanProduccion.implemento == imp,
        PlanProduccion.sector == sec,
        PlanProduccion.puesto_conjunto == pue,
        PlanProduccion.fecha.in_(dias_pasados)
    ).order_by(
        func.substr(PlanProduccion.fecha, 7, 4), # Año
        func.substr(PlanProduccion.fecha, 4, 2), # Mes
        func.substr(PlanProduccion.fecha, 1, 2)  # Día
    ).all()

    # Agregar modelos desde chasis_asignado_tolva
    for plan in pasados:
        chasis_asignado = ChasisAsignadoTolva.query.filter_by(nro_chasis=plan.nro_chasis).first()
        if chasis_asignado:
            plan.modelo = chasis_asignado.modelo

    # 2. Hoy
    actuales = PlanProduccion.query.filter_by(
        implemento=imp, 
        sector=sec, 
        puesto_conjunto=pue, 
        fecha=hoy_str
    ).all()

    # Agregar modelos desde chasis_asignado_tolva
    for plan in actuales:
        chasis_asignado = ChasisAsignadoTolva.query.filter_by(nro_chasis=plan.nro_chasis).first()
        if chasis_asignado:
            plan.modelo = chasis_asignado.modelo

    # 3. Futuros (Próximos 3 días hábiles)
    futuros = PlanProduccion.query.filter(
        PlanProduccion.implemento == imp,
        PlanProduccion.sector == sec,
        PlanProduccion.puesto_conjunto == pue,
        PlanProduccion.fecha.in_(dias_futuros)
    ).order_by(
        func.substr(PlanProduccion.fecha, 7, 4),
        func.substr(PlanProduccion.fecha, 4, 2),
        func.substr(PlanProduccion.fecha, 1, 2)
    ).all()

    # Agregar modelos desde chasis_asignado_tolva
    for plan in futuros:
        chasis_asignado = ChasisAsignadoTolva.query.filter_by(nro_chasis=plan.nro_chasis).first()
        if chasis_asignado:
            plan.modelo = chasis_asignado.modelo

    return render_template('operario_plan.html', 
                           pasados=pasados, actuales=actuales, futuros=futuros,
                           imp=imp, sec=sec, pue=pue, hoy_str=hoy_str)


@app.route('/admin/ver_plan_mixer')
@login_required
def admin_plan_mixer():
    implemento = request.args.get('implemento')
    
    if not implemento or implemento not in ['M1600', 'M2000', 'M2600']:
        flash("Implemento no válido", "danger")
        return redirect(url_for('admin_plan'))
    
    hoy_dt = datetime.now().date()
    hoy_str = hoy_dt.strftime('%d/%m/%Y')
    
    # Definir conjuntos para MIXER
    conjuntos = ['CHASIS', 'CUBA', 'ACCESORIOS', 'SIN FINES']
    
    # Calcular semanas (actual, anterior, siguiente)
    semana_actual = hoy_dt.isocalendar()[1]
    año_actual = hoy_dt.year
    
    # Semana anterior
    if semana_actual == 1:
        semana_anterior = 52
        año_anterior = año_actual - 1
    else:
        semana_anterior = semana_actual - 1
        año_anterior = año_actual
    
    # Semana siguiente
    if semana_actual == 52:
        semana_siguiente = 1
        año_siguiente = año_actual + 1
    else:
        semana_siguiente = semana_actual + 1
        año_siguiente = año_actual
    
    # Función para obtener planes por semana y conjunto
    def obtener_planes_por_semana(año, semana):
        planes_semana = {}
        
        # PRIMERO: Vamos a ver qué datos existen para MIXER
        todos_mixer = PlanProduccion.query.filter(
            PlanProduccion.implemento == 'MIXER'
        ).all()
        
        print(f"DEBUG: Total de registros con implemento = 'MIXER': {len(todos_mixer)}")
        for plan in todos_mixer:
            print(f"  - Chasis: {plan.nro_chasis}, Modelo: {plan.modelo}, Puesto: {plan.puesto_conjunto}, Sector: {plan.sector}")
        
        # También verificar si hay datos con implemento específico
        mixer_especifico = PlanProduccion.query.filter(
            PlanProduccion.implemento == implemento
        ).all()
        
        print(f"DEBUG: Total de registros con implemento = '{implemento}': {len(mixer_especifico)}")
        
        for conjunto in conjuntos:
            # Para MIXER, buscamos por implemento = 'MIXER', modelo = 1600/2000/2600 (sin M), y varios puestos posibles
            modelo_sin_m = implemento.replace('M', '')  # M1600 -> 1600
            
            # Buscar todos los puestos que contengan el nombre del conjunto
            posibles_puestos = [
                conjunto,  # CHASIS, CUBA, etc.
                f"LAVADO-{conjunto}",  # LAVADO-CHASIS, LAVADO-CUBA, etc.
                f"PINTURA-{conjunto}"  # PINTURA-CHASIS, PINTURA-CUBA, etc.
            ]
            
            # Unir con ChasisAsignado para filtrar por modelo
            planes = db.session.query(
                PlanProduccion,
                ChasisAsignado.modelo
            ).join(
                ChasisAsignado,
                (PlanProduccion.id == ChasisAsignado.plan_id) & 
                (PlanProduccion.nro_chasis == ChasisAsignado.nro_chasis)
            ).filter(
                PlanProduccion.implemento == 'MIXER',
                ChasisAsignado.modelo == modelo_sin_m,  # 1600, 2000, 2600 (sin M)
                PlanProduccion.puesto_conjunto.in_(posibles_puestos),  # CHASIS, LAVADO-CHASIS, PINTURA-CHASIS, etc.
                PlanProduccion.estado.in_(['PENDIENTE', 'TERMINADO'])
            ).all()

            print(f"DEBUG: Conjunto {conjunto}, buscando MIXER con modelo {modelo_sin_m} y puestos {posibles_puestos}")
            print(f"DEBUG: Conjunto {conjunto}, encontrados {len(planes)} planes totales")

            # Filtrar por semana (usando lógica simple de fecha)
            planes_filtrados = []
            for plan, modelo in planes:
                try:
                    # Intentar parsear como datetime primero (formato: 2026-01-22 00:00:00)
                    if ' ' in str(plan.fecha):
                        fecha_plan = datetime.strptime(str(plan.fecha).split(' ')[0], '%Y-%m-%d').date()
                    else:
                        # Si no tiene espacio, intentar como string (formato: 19/01/2026)
                        fecha_plan = datetime.strptime(str(plan.fecha), '%d/%m/%Y').date()

                    semana_plan = fecha_plan.isocalendar()[1]
                    año_plan = fecha_plan.year
                    print(f"DEBUG: Plan {plan.nro_chasis}, fecha {plan.fecha}, semana {semana_plan}, año {año_plan}")
                    if semana_plan == semana and año_plan == año:
                        # Agregar el modelo al objeto plan para que esté disponible en el template
                        plan.modelo = modelo
                        planes_filtrados.append(plan)
                        print(f"DEBUG: Plan {plan.nro_chasis} agregado a la semana {semana} con modelo {modelo}")
                except Exception as e:
                    print(f"ERROR: No se puede parsear fecha {plan.fecha}: {e}")
                    continue

            print(f"DEBUG: Conjunto {conjunto}, {len(planes_filtrados)} planes para semana {semana}")
            planes_semana[conjunto] = planes_filtrados

        return planes_semana

    # Obtener planes para las tres semanas
    planes_anterior = obtener_planes_por_semana(año_anterior, semana_anterior)
    planes_actual = obtener_planes_por_semana(año_actual, semana_actual)
    planes_siguiente = obtener_planes_por_semana(año_siguiente, semana_siguiente)

    return render_template('admin_plan_mixer.html', 
                           implemento=implemento,
                           conjuntos=conjuntos,
                           planes_anterior=planes_anterior,
                           planes_actual=planes_actual,
                           planes_siguiente=planes_siguiente,
                           semana_actual=semana_actual,
                           año_actual=año_actual)


@app.route('/operario/ver_plan_mixer')
@login_required
def ver_plan_mixer():
    implemento = request.args.get('implemento')

    if not implemento or implemento not in ['M1600', 'M2000', 'M2600']:
        flash("Implemento no válido", "danger")
        return redirect(url_for('seleccion_puesto'))

    hoy_dt = datetime.now().date()
    hoy_str = hoy_dt.strftime('%d/%m/%Y')

    # Definir conjuntos para MIXER
    conjuntos = ['CHASIS', 'CUBA', 'ACCESORIOS', 'SIN FINES']

    # Calcular semanas (actual, anterior, siguiente)
    semana_actual = hoy_dt.isocalendar()[1]
    año_actual = hoy_dt.year

    # Semana anterior
    if semana_actual == 1:
        semana_anterior = 52
        año_anterior = año_actual - 1
    else:
        semana_anterior = semana_actual - 1
        año_anterior = año_actual

    # Semana siguiente
    if semana_actual == 52:
        semana_siguiente = 1
        año_siguiente = año_actual + 1
    else:
        semana_siguiente = semana_actual + 1
        año_siguiente = año_actual

    # Función para obtener planes por semana y conjunto
    def obtener_planes_por_semana(año, semana):
        planes_semana = {}

        # PRIMERO: Vamos a ver qué datos existen para MIXER
        todos_mixer = PlanProduccion.query.filter(
            PlanProduccion.implemento == 'MIXER'
        ).all()

        print(f"DEBUG: Total de registros con implemento = 'MIXER': {len(todos_mixer)}")
        for plan in todos_mixer:
            print(f"  - Chasis: {plan.nro_chasis}, Modelo: {plan.modelo}, Puesto: {plan.puesto_conjunto}, Sector: {plan.sector}")

        # También verificar si hay datos con implemento específico
        mixer_especifico = PlanProduccion.query.filter(
            PlanProduccion.implemento == implemento
        ).all()

        print(f"DEBUG: Total de registros con implemento = '{implemento}': {len(mixer_especifico)}")

        for conjunto in conjuntos:
            # Para MIXER, buscamos por implemento = 'MIXER', modelo = 1600/2000/2600 (sin M), y varios puestos posibles
            modelo_sin_m = implemento.replace('M', '')  # M1600 -> 1600

            # Buscar todos los puestos que contengan el nombre del conjunto
            posibles_puestos = [
                conjunto,  # CHASIS, CUBA, etc.
                f"LAVADO-{conjunto}",  # LAVADO-CHASIS, LAVADO-CUBA, etc.
                f"PINTURA-{conjunto}"  # PINTURA-CHASIS, PINTURA-CUBA, etc.
            ]

            # Unir con ChasisAsignado para filtrar por modelo
            planes = db.session.query(
                PlanProduccion,
                ChasisAsignado.modelo
            ).join(
                ChasisAsignado,
                (PlanProduccion.id == ChasisAsignado.plan_id) & 
                (PlanProduccion.nro_chasis == ChasisAsignado.nro_chasis)
            ).filter(
                PlanProduccion.implemento == 'MIXER',
                ChasisAsignado.modelo == modelo_sin_m,  # 1600, 2000, 2600 (sin M)
                PlanProduccion.puesto_conjunto.in_(posibles_puestos),  # CHASIS, LAVADO-CHASIS, PINTURA-CHASIS, etc.
                PlanProduccion.estado.in_(['PENDIENTE', 'TERMINADO'])
            ).all()

            print(f"DEBUG: Conjunto {conjunto}, buscando MIXER con modelo {modelo_sin_m} y puestos {posibles_puestos}")
            print(f"DEBUG: Conjunto {conjunto}, encontrados {len(planes)} planes totales")

            # Filtrar por semana (usando lógica simple de fecha)
            planes_filtrados = []
            for plan, modelo in planes:
                try:
                    # Intentar parsear como datetime primero (formato: 2026-01-22 00:00:00)
                    if ' ' in str(plan.fecha):
                        fecha_plan = datetime.strptime(str(plan.fecha).split(' ')[0], '%Y-%m-%d').date()
                    else:
                        # Si no tiene espacio, intentar como string (formato: 19/01/2026)
                        fecha_plan = datetime.strptime(str(plan.fecha), '%d/%m/%Y').date()

                    semana_plan = fecha_plan.isocalendar()[1]
                    año_plan = fecha_plan.year
                    print(f"DEBUG: Plan {plan.nro_chasis}, fecha {plan.fecha}, semana {semana_plan}, año {año_plan}")
                    if semana_plan == semana and año_plan == año:
                        # Agregar el modelo al objeto plan para que esté disponible en el template
                        plan.modelo = modelo
                        planes_filtrados.append(plan)
                        print(f"DEBUG: Plan {plan.nro_chasis} agregado a la semana {semana} con modelo {modelo}")
                except Exception as e:
                    print(f"ERROR: No se puede parsear fecha {plan.fecha}: {e}")
                    continue

            print(f"DEBUG: Conjunto {conjunto}, {len(planes_filtrados)} planes para semana {semana}")
            planes_semana[conjunto] = planes_filtrados

        return planes_semana
    
    # Obtener planes para las tres semanas
    planes_anterior = obtener_planes_por_semana(año_anterior, semana_anterior)
    planes_actual = obtener_planes_por_semana(año_actual, semana_actual)
    planes_siguiente = obtener_planes_por_semana(año_siguiente, semana_siguiente)
    
    return render_template('operario_mixer.html', 
                           implemento=implemento,
                           conjuntos=conjuntos,
                           planes_anterior=planes_anterior,
                           planes_actual=planes_actual,
                           planes_siguiente=planes_siguiente,
                           semana_actual=semana_actual,
                           año_actual=año_actual)


@app.route('/operario/seleccion_mixer')
@login_required
def operario_seleccion_mixer():
    if current_user.rol == 'ADMIN':
        return redirect(url_for('seleccion_admin'))
    
    modelos_mixer = ['M1600', 'M2000', 'M2600']
    return render_template('operario_seleccion_mixer.html', modelos=modelos_mixer)


@app.route('/admin/seleccion_puesto')
@login_required
def seleccion_puesto():
    # Definimos la estructura lógica de la planta por implemento
    estructura_general = {
        'SOLDADURA': ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9'],
        'PINTURA': ['LAVADO', 'PINTURA'],
        'MONTAJE': ['M1', 'M2', 'M3', 'M4', 'M5']
    }
    
    # Estructura especial para MIXER
    estructura_mixer = {
        'SOLDADURA': ['CHASIS-SOLDADURA', 'CUBA-SOLDADURA', 'SIN FINES-SOLDADURA', 'ACCESORIOS-SOLDADURA'],
        'PINTURA': ['CHASIS-PINTURA', 'CUBA-PINTURA', 'SIN FINES-PINTURA', 'ACCESORIOS-PINTURA'],
        'MONTAJE': ['M1', 'M2', 'M3', 'M4', 'M5']
    }
    
    # Estructura para TOLVA (usando la estructura general)
    estructura_tolva = estructura_general
    
    # Estructura para EMBOLSADORA (usando la estructura general)
    estructura_embolsadora = estructura_general
    
    # Estructura para ATT (usando la estructura general)
    estructura_att = estructura_general
    
    # Estructura para SEMBRADORA (usando la estructura general)
    estructura_sembradora = estructura_general
    
    return render_template('seleccion_puesto.html', 
                         estructura=estructura_general,
                         estructura_mixer=estructura_mixer,
                         estructura_tolva=estructura_tolva,
                         estructura_embolsadora=estructura_embolsadora,
                         estructura_att=estructura_att,
                         estructura_sembradora=estructura_sembradora)


@app.route('/puesto/<nombre_puesto>')
@login_required
def ver_puesto(nombre_puesto):
    # 1. El que debe hacer ahora
    actual = PlanProduccion.query.filter_by(puesto_conjunto=nombre_puesto, estado='PENDIENTE').first()
    
    # 2. Los últimos 5 que ya hizo (para el historial)
    terminados = PlanProduccion.query.filter_by(puesto_conjunto=nombre_puesto, estado='TERMINADO')\
                 .order_by(PlanProduccion.hora_fin.desc()).limit(5).all()
    
    # 3. Los que vienen después (saltando el actual)
    futuros = []
    if actual:
        futuros = PlanProduccion.query.filter_by(puesto_conjunto=nombre_puesto, estado='PENDIENTE')\
                  .filter(PlanProduccion.id != actual.id).limit(3).all()

    return render_template('puesto.html', 
                           puesto_nombre=nombre_puesto, 
                           actual=actual, 
                           terminados=terminados, 
                           futuros=futuros)


@app.route('/operario/dar_avance/<int:id_plan>')
@login_required
def dar_avance(id_plan):
    # Verificar QR como capa adicional de seguridad (solo si se proporciona)
    qr_escaneado = request.args.get('qr_chasis', '').strip()
    
    # Usamos la forma estándar que tienes en el resto del código
    item = PlanProduccion.query.get_or_404(id_plan)
    
    # Si se proporcionó QR, validarlo (caso de dispositivos móviles)
    if qr_escaneado:
        # Validar que el QR corresponda al número de chasis
        if qr_escaneado != item.nro_chasis:
            flash(f"⚠️ Error: El QR escaneado ({qr_escaneado}) no corresponde al chasis asignado ({item.nro_chasis})", "danger")
            return redirect(request.referrer or url_for('seleccion_puesto'))
    # Si no se proporcionó QR, asumimos que es acceso desde PC (permitido)
    
    # Estructura de puestos por sector (mismo orden que en seleccion_puesto)
    estructura = {
        'SOLDADURA': ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9'],
        'PINTURA': ['LAVADO', 'PINTURA'],
        'MONTAJE': ['M1', 'M2', 'M3', 'M4', 'M5']
    }
    
    # Estructura especial para MIXER
    estructura_mixer = {
        'SOLDADURA': ['CHASIS-SOLDADURA', 'CUBA-SOLDADURA', 'SIN FINES-SOLDADURA', 'ACCESORIOS-SOLDADURA'],
        'PINTURA': ['CHASIS-PINTURA', 'CUBA-PINTURA', 'SIN FINES-PINTURA', 'ACCESORIOS-PINTURA'],
        'MONTAJE': ['M1', 'M2', 'M3', 'M4', 'M5']
    }
    
    # VERIFICAR SI ES UN MIXER Y SI ESTÁ EN MONTAJE M1
    if item.implemento and item.implemento.startswith('M') and item.implemento in ['M1600', 'M2000', 'M2600']:
        if item.sector == 'MONTAJE' and item.puesto_conjunto == 'M1':
            # RESTRICCIÓN ESPECIAL: Para M1 de MIXER, verificar que los 4 conjuntos de PINTURA estén completos
            conjuntos_pintura_requeridos = ['CHASIS-PINTURA', 'CUBA-PINTURA', 'SIN FINES-PINTURA', 'ACCESORIOS-PINTURA']
            
            for conjunto_pintura in conjuntos_pintura_requeridos:
                registro_pintura = PlanProduccion.query.filter_by(
                    nro_chasis=item.nro_chasis,
                    implemento=item.implemento,
                    puesto_conjunto=conjunto_pintura,
                    estado='TERMINADO'
                ).first()
                
                if not registro_pintura:
                    flash(f"⚠️ No se puede completar M1 aún. Falta completar {conjunto_pintura} para el chasis {item.nro_chasis}", "warning")
                    return redirect(request.referrer or url_for('seleccion_puesto'))
    
    # Lógica normal para otros casos
    # Obtener la lista de puestos del sector actual
    if item.implemento and item.implemento.startswith('M') and item.implemento in ['M1600', 'M2000', 'M2600']:
        puestos_sector = estructura_mixer.get(item.sector, [])
    else:
        puestos_sector = estructura.get(item.sector, [])
    
    # Encontrar el índice del puesto actual
    if item.puesto_conjunto in puestos_sector:
        idx_actual = puestos_sector.index(item.puesto_conjunto)
        
        # EXCEPCIÓN: Solo validar restricciones desde el 3er puesto (índice 2) en adelante
        # P1 y P2 pueden avanzar sin restricción previa
        if idx_actual >= 2:
            puestos_anteriores = puestos_sector[:idx_actual]
            
            # Buscar si el mismo chasis tiene registros en los puestos anteriores
            registros_anteriores = PlanProduccion.query.filter_by(
                nro_chasis=item.nro_chasis,
                sector=item.sector
            ).all()
            
            # Verificar que todos los puestos anteriores estén completados
            puestos_completados = {r.puesto_conjunto for r in registros_anteriores if r.estado == 'TERMINADO'}
            
            puestos_faltantes = [p for p in puestos_anteriores if p not in puestos_completados]
            
            if puestos_faltantes:
                primer_puesto_faltante = puestos_faltantes[0]
                flash(f"⚠️ No se puede completar {item.puesto_conjunto} aún. Primero debe terminarse {primer_puesto_faltante} para el chasis {item.nro_chasis}", "warning")
                return redirect(request.referrer or url_for('seleccion_puesto'))
    
    # Si llegamos aquí, el avance es válido
    item.estado = 'TERMINADO'
    item.hora_fin = datetime.now()
    db.session.commit()
    
    flash(f"Chasis {item.nro_chasis} terminado con éxito en {item.puesto_conjunto}")
    # request.referrer es lo que te devuelve a la página donde estabas
    return redirect(request.referrer or url_for('seleccion_puesto'))


@app.route('/operario/validar_avance/<int:id_plan>')
@login_required
def validar_avance(id_plan):
    """Valida si es posible dar avance a un chasis. Retorna JSON.
    EXCEPCIÓN: Solo valida restricciones desde el 3er puesto (P3, M3, etc) en adelante.
    P1 y P2 pueden avanzar sin restricciones previas."""
    item = PlanProduccion.query.get_or_404(id_plan)
    
    # Estructura de puestos por sector
    estructura = {
        'SOLDADURA': ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9'],
        'PINTURA': ['LAVADO', 'PINTURA'],
        'MONTAJE': ['M1', 'M2', 'M3', 'M4', 'M5']
    }
    
    # Obtener la lista de puestos del sector actual
    puestos_sector = estructura.get(item.sector, [])
    
    # Encontrar el índice del puesto actual
    if item.puesto_conjunto in puestos_sector:
        idx_actual = puestos_sector.index(item.puesto_conjunto)
        
        # EXCEPCIÓN: Solo validar restricciones desde el 3er puesto (índice 2) en adelante
        # P1 y P2 pueden avanzar sin restricción previa
        if idx_actual >= 2:
            puestos_anteriores = puestos_sector[:idx_actual]
            
            # Buscar si el mismo chasis tiene registros en los puestos anteriores
            registros_anteriores = PlanProduccion.query.filter_by(
                nro_chasis=item.nro_chasis,
                sector=item.sector
            ).all()
            
            # Verificar que todos los puestos anteriores estén completados
            puestos_completados = {r.puesto_conjunto for r in registros_anteriores if r.estado == 'TERMINADO'}
            
            puestos_faltantes = [p for p in puestos_anteriores if p not in puestos_completados]
            
            if puestos_faltantes:
                return jsonify({
                    'valido': False,
                    'primer_puesto_faltante': puestos_faltantes[0],
                    'mensaje': f"Primero debe completar {puestos_faltantes[0]} para el chasis {item.nro_chasis}"
                })
    
    return jsonify({'valido': True})

@app.route('/operario/validar_qr/<int:id_plan>')
@login_required
def validar_qr(id_plan):
    """Valida el QR escaneado para un chasis específico."""
    qr_escaneado = request.args.get('qr_chasis', '').strip()
    
    if not qr_escaneado:
        return jsonify({
            'valido': False,
            'mensaje': 'Debe escanear el código QR del chasis'
        })
    
    # Obtener el plan de producción
    item = PlanProduccion.query.get_or_404(id_plan)
    
    # Validar que el QR corresponda al número de chasis
    if qr_escaneado != item.nro_chasis:
        return jsonify({
            'valido': False,
            'mensaje': f'El QR escaneado ({qr_escaneado}) no corresponde al chasis asignado ({item.nro_chasis})'
        })
    
    return jsonify({
        'valido': True,
        'mensaje': f'QR validado correctamente para chasis {item.nro_chasis}'
    })

# --- RUTAS PARA GESTIÓN DE FERIADOS ---

@app.route('/admin/feriados')
@login_required
def admin_feriados():
    if current_user.rol != 'ADMIN': return redirect(url_for('login'))
    # Traemos todos los feriados de la base de datos y convertimos a diccionarios
    feriados_db = Feriado.query.order_by(Feriado.fecha).all()
    feriados = []
    for f in feriados_db:
        # Convertir fecha a DD/MM/YYYY si está en formato YYYY-MM-DD
        fecha_formateada = f.fecha
        if len(f.fecha) == 10 and f.fecha[4] == '-':
            # Formato YYYY-MM-DD, convertir a DD/MM/YYYY
            try:
                fecha_dt = datetime.strptime(f.fecha, '%Y-%m-%d')
                fecha_formateada = fecha_dt.strftime('%d/%m/%Y')
            except ValueError:
                pass  # Mantener original si hay error
        feriados.append({'id': f.id, 'fecha': fecha_formateada, 'descripcion': f.descripcion})
    return render_template('admin_feriados.html', feriados=feriados)

@app.route('/admin/agregar_feriado', methods=['POST'])
@login_required
def agregar_feriado():
    fecha = request.form.get('fecha')
    desc = request.form.get('descripcion')
    
    # Convertir de YYYY-MM-DD (formato HTML input date) a DD/MM/YYYY
    if fecha:
        try:
            fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
            fecha_formateada = fecha_dt.strftime('%d/%m/%Y')
        except ValueError:
            flash("Formato de fecha inválido")
            return redirect(url_for('admin_feriados'))
    else:
        flash("La fecha es requerida")
        return redirect(url_for('admin_feriados'))
    
    nuevo_feriado = Feriado(fecha=fecha_formateada, descripcion=desc)
    db.session.add(nuevo_feriado)
    db.session.commit()
    
    # Registrar auditoría
    detalles = f"AGREGAR feriado: Fecha {fecha_formateada}, Descripción: {desc}"
    registrar_auditoria(
        current_user.id, 
        current_user.nombre, 
        'AGREGAR_FERIADO', 
        'Gestión de Feriados', 
        detalles
    )
    
    flash("Feriado agregado correctamente")
    return redirect(url_for('admin_feriados'))

@app.route('/admin/eliminar_feriado/<int:id>')
@login_required
def eliminar_feriado(id):
    feriado = Feriado.query.get_or_404(id)
    
    # Guardar datos para auditoría
    datos_feriado = f"Fecha {feriado.fecha}, Descripción: {feriado.descripcion}"
    
    db.session.delete(feriado)
    db.session.commit()
    
    # Registrar auditoría
    detalles = f"ELIMINAR feriado: {datos_feriado}"
    registrar_auditoria(
        current_user.id, 
        current_user.nombre, 
        'ELIMINAR_FERIADO', 
        'Gestión de Feriados', 
        detalles
    )
    
    flash("Feriado eliminado")
    return redirect(url_for('admin_feriados'))


# --- Sección 6: Autenticación e Inicio (UNIFICADA Y CORREGIDA) -----------------------------------------------------------------





@app.route('/')
def index():
    # Si no está autenticado, ir al login
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # Al entrar a la raíz, si es ADMIN va al menú de elección, si es operario a su puesto
    if current_user.rol == 'ADMIN':
        return redirect(url_for('seleccion_admin'))
    else:
        return redirect(url_for('seleccion_puesto'))

@app.route('/admin/seleccion')
@login_required
def seleccion_admin():
    if current_user.rol != 'ADMIN':
        flash("Acceso denegado. Solo administradores.", "danger")
        return redirect(url_for('login'))
    return render_template('seleccion_admin.html')

@app.route('/admin/hys')
@login_required
def hys_dashboard():
    """Dashboard de Higiene y Seguridad Industrial"""
    if current_user.rol not in ['ADMIN', 'CALIDAD']:
        flash("Acceso denegado. Solo administradores y personal de H&S.", "danger")
        return redirect(url_for('login'))
    
    # Estadísticas básicas
    incidentes_hoy = IncidenteHYS.query.filter(
        IncidenteHYS.fecha_reporte >= datetime.now().replace(hour=0, minute=0, second=0)
    ).count()
    
    condiciones_inseguras = IncidenteHYS.query.filter_by(tipo_incidente='CONDICION_INSEGURA').filter(
        IncidenteHYS.estado == 'ABIERTO'
    ).count()
    
    # Checklists EPP de hoy
    checklists_hoy = ChecklistEPP.query.filter(
        ChecklistEPP.fecha >= datetime.now().replace(hour=0, minute=0, second=0)
    ).count()
    
    # Total usuarios para calcular cumplimiento
    total_operarios = Usuario.query.filter_by(rol='OPERARIO').count()
    cumplimiento_epp = round((checklists_hoy / total_operarios * 100), 1) if total_operarios > 0 else 0
    
    # Solicitudes pendientes
    solicitudes_pendientes = SolicitudEPP.query.filter_by(estado='PENDIENTE').count()
    
    # Últimos incidentes
    ultimos_incidentes = IncidenteHYS.query.order_by(
        IncidenteHYS.fecha_reporte.desc()
    ).limit(5).all()
    
    # Zonas de riesgo
    zonas_riesgo = ZonaRiesgo.query.filter_by(estado='ACTIVA').all()
    
    return render_template('hys_dashboard.html',
        incidentes_hoy=incidentes_hoy,
        condiciones_inseguras=condiciones_inseguras,
        cumplimiento_epp=cumplimiento_epp,
        solicitudes_pendientes=solicitudes_pendientes,
        ultimos_incidentes=ultimos_incidentes,
        zonas_riesgo=zonas_riesgo
    )

@app.route('/admin/dashboard-integrado')
@login_required
def dashboard_integrado():
    """Dashboard integrado de Producción y Calidad"""
    if current_user.rol != 'ADMIN':
        flash("Acceso denegado. Solo administradores.", "danger")
        return redirect(url_for('login'))
    
    from datetime import datetime, timedelta
    
    # Métricas principales
    total_produccion = PlanProduccion.query.count()
    produccion_hoy = PlanProduccion.query.filter(
        PlanProduccion.fecha == datetime.now().strftime('%d/%m/%Y')
    ).count()
    
    # No conformidades
    nc_activas = NoConformidad.query.filter(
        NoConformidad.estado.in_(['ABIERTA', 'EN_ANALISIS', 'EN_PROCESO'])
    ).count()
    nc_criticas = NoConformidad.query.filter_by(gravedad='CRITICO').filter(
        NoConformidad.estado.in_(['ABIERTA', 'EN_ANALISIS', 'EN_PROCESO'])
    ).count()
    
    # Eficiencia
    terminados = PlanProduccion.query.filter_by(estado='TERMINADO').count()
    eficiencia = round((terminados / total_produccion * 100), 1) if total_produccion > 0 else 0
    eficiencia_cambio = 5.2  # Simulado - calcular con datos históricos
    
    # Calidad
    auditorias_completadas = AuditoriaRealizada.query.filter_by(estado='APROBADO').count()
    calidad_promedio = 94.5  # Simulado - calcular con auditorías
    
    # Alertas críticas
    alertas_criticas = NoConformidad.query.filter_by(gravedad='CRITICO').filter(
        NoConformidad.estado.in_(['ABIERTA', 'EN_ANALISIS', 'EN_PROCESO'])
    ).order_by(NoConformidad.fecha_deteccion.desc()).limit(5).all()
    
    # Progreso por implemento
    implementos = ['TOLVA', 'MIXER', 'EMBOLSADORA', 'ATT', 'SEMBRADORA']
    progreso_implementos = []
    for impl in implementos:
        total = PlanProduccion.query.filter_by(implemento=impl).count()
        terminados = PlanProduccion.query.filter_by(implemento=impl, estado='TERMINADO').count()
        progreso = round((terminados / total * 100), 1) if total > 0 else 0
        progreso_implementos.append({
            'nombre': impl,
            'total': total,
            'terminados': terminados,
            'progreso': progreso
        })
    
    # Datos para gráficos
    ultimos_7_dias = []
    produccion_data = []
    calidad_data = []
    
    for i in range(7):
        fecha = datetime.now() - timedelta(days=i)
        fecha_str = fecha.strftime('%d/%m')
        ultimos_7_dias.append(fecha_str)
        
        prod = PlanProduccion.query.filter_by(fecha=fecha.strftime('%d/%m/%Y')).count()
        produccion_data.append(prod)
        
        # Calidad simulada - reemplazar con datos reales
        calidad_data.append(92 + (i % 5))
    
    datos_grafico = {
        'labels': ultimos_7_dias[::-1],
        'produccion': produccion_data[::-1],
        'calidad': calidad_data[::-1]
    }
    
    # Estados de producción
    estados = {
        'TERMINADO': PlanProduccion.query.filter_by(estado='TERMINADO').count(),
        'EN_PROGRESO': PlanProduccion.query.filter_by(estado='EN_PROGRESO').count(),
        'PENDIENTE': PlanProduccion.query.filter_by(estado='PENDIENTE').count(),
        'OTROS': PlanProduccion.query.filter(
            PlanProduccion.estado.notin_(['TERMINADO', 'EN_PROGRESO', 'PENDIENTE'])
        ).count()
    }
    
    datos_estados = {
        'labels': list(estados.keys()),
        'values': list(estados.values())
    }
    
    # Alertas recientes
    alertas_recientes = NoConformidad.query.order_by(
        NoConformidad.fecha_deteccion.desc()
    ).limit(3).all()
    
    alertas_activas = nc_activas
    
    return render_template('dashboard_integrado.html',
        total_produccion=total_produccion,
        produccion_hoy=produccion_hoy,
        nc_activas=nc_activas,
        nc_criticas=nc_criticas,
        eficiencia=eficiencia,
        eficiencia_cambio=eficiencia_cambio,
        calidad_promedio=calidad_promedio,
        auditorias_completadas=auditorias_completadas,
        alertas_criticas=alertas_criticas,
        progreso_implementos=progreso_implementos,
        datos_grafico=datos_grafico,
        datos_estados=datos_estados,
        alertas_recientes=alertas_recientes,
        alertas_activas=alertas_activas
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        legajo = request.form.get('legajo')
        pin_secreto = request.form.get('pin_secreto')
        
        print(f"DEBUG: Intento de login - Legajo: '{legajo}', PIN: '{pin_secreto}'")
        
        # Usar SQL directo para evitar problemas con el mapeo de SQLAlchemy
        try:
            from sqlalchemy import text
            result = db.session.execute(text("SELECT * FROM usuario WHERE legajo = :legajo AND pin_secreto = :pin_secreto"), 
                                      {"legajo": legajo, "pin_secreto": pin_secreto})
            row = result.fetchone()
            
            print(f"DEBUG: Resultado de consulta: {row}")
            
            if row:
                print("DEBUG: Usuario encontrado, creando objeto")
                # Crear objeto Usuario manualmente
                user = Usuario()
                user.id = row[0]
                user.legajo = row[1]
                user.pin_secreto = row[2]
                user.nombre = row[3]
                user.sector = row[4]
                user.rol = row[5]
                
                print(f"DEBUG: Objeto usuario creado - Nombre: {user.nombre}, Rol: {user.rol}")
                
                login_user(user)
                print("DEBUG: Usuario logueado exitosamente")
                
                if user.rol == 'ADMIN':
                    print("DEBUG: Redirigiendo a seleccion_admin")
                    return redirect(url_for('seleccion_admin'))
                print("DEBUG: Redirigiendo a bienvenida")
                return redirect(url_for('bienvenida'))
            else:
                print("DEBUG: Usuario no encontrado")
                flash('Legajo o PIN incorrectos')
        except Exception as e:
            print(f"ERROR en login: {e}")
            import traceback
            traceback.print_exc()
            flash('Error en el sistema de autenticación')
            
    return render_template('login.html')

@app.route('/bienvenida')
@login_required
def bienvenida():
    """Página de bienvenida para operarios después del login"""
    if current_user.rol == 'ADMIN':
        return redirect(url_for('seleccion_admin'))
    
    return render_template('bienvenida.html', usuario=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SECCIÓN 7: AJUSTES Y GESTIÓN DE USUARIOS ---

# ===== INICIALIZACIÓN AUTOMÁTICA DE BD =====
def inicializar_base_datos():
    """Inicializa la base de datos al arrancar la aplicación"""
    # Solo inicializar en desarrollo local, no en producción
    if os.environ.get('DATABASE_URL'):
        print("🚀 Producción detectada - Omitiendo inicialización automática")
        print("💡 La base de datos debe ser creada manualmente en Neon.tech")
        return
        
    from sqlalchemy import text
    
    print("📁 Desarrollo local detectado - Inicializando SQLite...")
    
    # 1. Crear todas las tablas
    db.create_all()
    
    # 2. Verificar si la tabla usuario existe y tiene la estructura correcta (SQLite)
    try:
        # Verificar si existe la tabla usuario (SQLite local)
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='usuario'"))
        tabla_usuario = result.fetchone()
        
        if tabla_usuario:
            # Verificar si tiene la columna legajo (SQLite)
            result = db.session.execute(text("PRAGMA table_info(usuario)"))
            columnas = result.fetchall()
            tiene_legajo = any(col[1] == 'legajo' for col in columnas)
            
            if tiene_legajo:
                # Verificar si ya hay usuarios
                result = db.session.execute(text("SELECT COUNT(*) FROM usuario"))
                count = result.fetchone()[0]
                
                if count == 0:
                    # Crear usuarios iniciales
                    admin = Usuario(legajo='0000', pin_secreto='9999', nombre='Administrador', sector='ADMIN', rol='ADMIN')
                    op1 = Usuario(legajo='1111', pin_secreto='1111', nombre='Operario Soldadura', sector='SOLDADURA', rol='OPERARIO')
                    db.session.add_all([admin, op1])
                    db.session.commit()
                    print("Usuarios iniciales creados")
            else:
                print("La tabla usuario no tiene la estructura correcta (falta columna legajo)")
        else:
            print("Tabla usuario no encontrada")
            
    except Exception as e:
        print(f"Error verificando estructura de usuario: {e}")
    
    # 3. Otras inicializaciones (sin modificar usuario)
    try:
        # Resto de las inicializaciones que no dependen de usuario
        pass
    except Exception as e:
        print(f"Error en inicialización general: {e}")
    
    # 3. Crear matriz de playón (80 celdas) si no existe
    try:
        if not CeldaPlayon.query.first():
            filas = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            for letra in filas:
                for numero in range(1, 11):
                    codigo = f"{letra}-{numero}"
                    db.session.add(CeldaPlayon(codigo=codigo, estado='LIBRE'))
            db.session.commit()
            print("Matriz de playón creada")
    except Exception as e:
        print(f"Error creando matriz de playón: {e}")
        db.session.rollback()
    
    # 4. Agregar columnas faltantes si no existen (para SQLite)
    try:
        db.session.execute(text('ALTER TABLE plan_produccion ADD COLUMN usuario_avance VARCHAR(100)'))
        db.session.commit()
    except:
        db.session.rollback()
    
    try:
        db.session.execute(text("ALTER TABLE plan_produccion ADD COLUMN fecha_playon DATETIME"))
        db.session.commit()
    except:
        db.session.rollback()
    
    try:
        db.session.execute(text("ALTER TABLE plan_produccion ADD COLUMN cubiertas BOOLEAN DEFAULT 0"))
        db.session.commit()
    except:
        db.session.rollback()
    
    try:
        db.session.execute(text("ALTER TABLE plan_produccion ADD COLUMN con_cliente BOOLEAN DEFAULT 0"))
        db.session.commit()
    except:
        db.session.rollback()

# --- Sección 5: Sistema de Gestión de Calidad (SGC) ------------------------------------------

# --- 5.1 Checklists y Auditorías Digitales ---
@app.route('/calidad/checklists')
@login_required
def calidad_checklists():
    if current_user.rol not in ['ADMIN', 'CALIDAD']:
        return redirect(url_for('login'))
    
    templates = ChecklistTemplate.query.filter_by(estado='ACTIVO').all()
    return render_template('calidad/checklists.html', templates=templates)

@app.route('/calidad/checklist/nuevo', methods=['GET', 'POST'])
@login_required
def calidad_checklist_nuevo():
    if current_user.rol not in ['ADMIN', 'CALIDAD']:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        template = ChecklistTemplate(
            nombre=request.form['nombre'],
            tipo=request.form['tipo'],
            sector=request.form.get('sector'),
            descripcion=request.form.get('descripcion'),
            frecuencia=request.form.get('frecuencia'),
            creado_por=current_user.nombre
        )
        db.session.add(template)
        db.session.commit()
        
        # Agregar items
        item_count = int(request.form.get('item_count', 0))
        for i in range(1, item_count + 1):
            if f'descripcion_{i}' in request.form:
                item = ChecklistItem(
                    template_id=template.id,
                    descripcion=request.form[f'descripcion_{i}'],
                    tipo_respuesta=request.form[f'tipo_{i}'],
                    obligatorio=f'obligatorio_{i}' in request.form,
                    orden=i,
                    puntos=int(request.form.get(f'puntos_{i}', 0))
                )
                db.session.add(item)
        
        db.session.commit()
        flash('Checklist creado exitosamente', 'success')
        return redirect(url_for('calidad_checklists'))
    
    return render_template('calidad/checklist_form.html')

@app.route('/calidad/auditoria/nueva/<int:template_id>', methods=['GET', 'POST'])
@login_required
def calidad_auditoria_nueva(template_id):
    template = ChecklistTemplate.query.get_or_404(template_id)
    
    if request.method == 'POST':
        auditoria = AuditoriaRealizada(
            template_id=template_id,
            plan_id=request.form.get('plan_id') if request.form.get('plan_id') else None,
            auditor=current_user.nombre,
            observaciones_generales=request.form.get('observaciones_generales'),
            tiempo_inicio=datetime.now()
        )
        db.session.add(auditoria)
        db.session.commit()
        
        # Procesar respuestas
        for item in template.items:
            respuesta = RespuestaAuditoria(
                auditoria_id=auditoria.id,
                item_id=item.id
            )
            
            if item.tipo_respuesta == 'SI/NO':
                respuesta.respuesta_si_no = f'respuesta_{item.id}' in request.form
                respuesta.cumple = respuesta.respuesta_si_no
            elif item.tipo_respuesta == 'TEXTO':
                respuesta.respuesta = request.form.get(f'respuesta_{item.id}', '')
            elif item.tipo_respuesta == 'NUMERICO':
                respuesta.respuesta_numerica = float(request.form.get(f'respuesta_{item.id}', 0))
            
            respuesta.observaciones = request.form.get(f'obs_{item.id}', '')
            
            # Manejar archivo de evidencia
            if f'evidencia_{item.id}' in request.files:
                file = request.files[f'evidencia_{item.id}']
                if file.filename:
                    filename = secure_filename(f"auditoria_{auditoria.id}_item_{item.id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    respuesta.evidencia_foto = filename
            
            db.session.add(respuesta)
        
        # Calcular puntaje y porcentaje
        total_puntos = sum(item.puntos for item in template.items if item.puntos > 0)
        puntos_obtenidos = sum(item.puntos for item in auditoria.respuestas if item.cumple and item.item.puntos > 0)
        
        auditoria.puntaje_total = total_puntos
        auditoria.puntaje_obtenido = puntos_obtenidos
        auditoria.porcentaje_cumplimiento = (puntos_obtenidos / total_puntos * 100) if total_puntos > 0 else 0
        auditoria.tiempo_fin = datetime.now()
        
        # Determinar estado
        if auditoria.porcentaje_cumplimiento >= 90:
            auditoria.estado = 'APROBADO'
        elif auditoria.porcentaje_cumplimiento >= 70:
            auditoria.estado = 'APROBADO_CON_OBSERVACIONES'
        else:
            auditoria.estado = 'RECHAZADO'
        
        db.session.commit()
        flash('Auditoría completada exitosamente', 'success')
        return redirect(url_for('calidad_auditorias'))
    
    # Obtener planes para seleccionar
    planes = PlanProduccion.query.filter_by(estado='PENDIENTE').all() if template.tipo == 'PROCESO' else []
    return render_template('calidad/auditoria_form.html', template=template, planes=planes)

@app.route('/calidad/auditorias')
@login_required
def calidad_auditorias():
    auditorias = AuditoriaRealizada.query.order_by(AuditoriaRealizada.fecha.desc()).all()
    return render_template('calidad/auditorias.html', auditorias=auditorias)

# --- 5.2 No Conformidades y CAPA ---
@app.route('/calidad/noconformidades')
@login_required
def calidad_noconformidades():
    no_conformidades = NoConformidad.query.order_by(NoConformidad.fecha_deteccion.desc()).all()
    return render_template('calidad/noconformidades.html', nc_list=no_conformidades)

@app.route('/calidad/noconformidad/nueva', methods=['GET', 'POST'])
@login_required
def calidad_noconformidad_nueva():
    if request.method == 'POST':
        # Generar código automático
        year = datetime.now().year
        last_nc = NoConformidad.query.filter(NoConformidad.codigo.like(f'NC-{year}-%')).order_by(NoConformidad.codigo.desc()).first()
        
        if last_nc:
            last_number = int(last_nc.codigo.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        
        codigo = f'NC-{year}-{new_number:03d}'
        
        nc = NoConformidad(
            codigo=codigo,
            plan_id=request.form.get('plan_id') if request.form.get('plan_id') else None,
            titulo=request.form['titulo'],
            descripcion=request.form['descripcion'],
            gravedad=request.form['gravedad'],
            tipo=request.form['tipo'],
            fuente_deteccion=request.form['fuente_deteccion'],
            detectado_por=current_user.nombre,
            responsable_analisis=request.form.get('responsable_analisis'),
            sector=current_user.sector,
            impacto=request.form.get('impacto'),
            fecha_limite_analisis=datetime.strptime(request.form['fecha_limite_analisis'], '%Y-%m-%d') if request.form.get('fecha_limite_analisis') else None
        )
        
        # Manejar evidencia inicial
        if 'evidencia_inicial' in request.files:
            file = request.files['evidencia_inicial']
            if file.filename:
                filename = secure_filename(f"nc_{codigo}_evidencia_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                nc.evidencia_inicial = filename
        
        db.session.add(nc)
        db.session.commit()
        
        # Crear notificación para responsables
        notificacion = Notificacion(
            titulo=f'Nueva No Conformidad: {codigo}',
            mensaje=f'Se ha detectado una NC de gravedad {nc.gravedad}: {nc.titulo}',
            tipo='NC_CRITICA' if nc.gravedad in ['GRAVE', 'CRITICO'] else 'NC',
            prioridad='ALTA' if nc.gravedad in ['GRAVE', 'CRITICO'] else 'MEDIA',
            destinatario=nc.responsable_analisis,
            link_accion=url_for('calidad_noconformidad_detalle', id=nc.id),
            referencia_id=nc.id,
            referencia_tipo='NC'
        )
        db.session.add(notificacion)
        db.session.commit()
        
        flash(f'No Conformidad {codigo} creada exitosamente', 'success')
        return redirect(url_for('calidad_noconformidades'))
    
    planes = PlanProduccion.query.all()
    return render_template('calidad/noconformidad_form.html', planes=planes)

@app.route('/calidad/noconformidad/<int:id>')
@login_required
def calidad_noconformidad_detalle(id):
    nc = NoConformidad.query.get_or_404(id)
    return render_template('calidad/noconformidad_detalle.html', nc=nc)

@app.route('/calidad/accion/nueva/<int:nc_id>', methods=['GET', 'POST'])
@login_required
def calidad_accion_nueva(nc_id):
    nc = NoConformidad.query.get_or_404(nc_id)
    
    if request.method == 'POST':
        accion = AccionCorrectiva(
            nc_id=nc_id,
            tipo=request.form['tipo'],
            descripcion=request.form['descripcion'],
            responsable=request.form['responsable'],
            fecha_limite=datetime.strptime(request.form['fecha_limite'], '%Y-%m-%d'),
            prioridad=request.form.get('prioridad', 'MEDIA'),
            recursos_necesarios=request.form.get('recursos'),
            costo_estimado=float(request.form.get('costo_estimado', 0)) if request.form.get('costo_estimado') else None
        )
        
        # Manejar evidencia antes
        if 'evidencia_antes' in request.files:
            file = request.files['evidencia_antes']
            if file.filename:
                filename = secure_filename(f"accion_{nc.codigo}_antes_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                accion.evidencia_antes = filename
        
        db.session.add(accion)
        db.session.commit()
        
        # Actualizar estado de NC
        nc.estado = 'EN_PROCESO'
        db.session.commit()
        
        flash('Acción correctiva asignada exitosamente', 'success')
        return redirect(url_for('calidad_noconformidad_detalle', id=nc_id))
    
    return render_template('calidad/accion_form.html', nc=nc)

# --- 5.3 Control Documental ---
@app.route('/calidad/documentos')
@login_required
def calidad_documentos():
    documentos = Documento.query.order_by(Documento.fecha_creacion.desc()).all()
    return render_template('calidad/documentos.html', documentos=documentos)

@app.route('/calidad/documento/nuevo', methods=['GET', 'POST'])
@login_required
def calidad_documento_nuevo():
    if current_user.rol not in ['ADMIN', 'CALIDAD']:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Generar código automático
        tipo = request.form['tipo']
        last_doc = Documento.query.filter(Documento.codigo.like(f'{tipo}-%')).order_by(Documento.codigo.desc()).first()
        
        if last_doc:
            last_number = int(last_doc.codigo.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        
        codigo = f'{tipo}-{new_number:03d}'
        
        documento = Documento(
            codigo=codigo,
            titulo=request.form['titulo'],
            version=request.form['version'],
            tipo=tipo,
            categoria=request.form['categoria'],
            sector=request.form.get('sector'),
            descripcion=request.form.get('descripcion'),
            fecha_vigencia=datetime.strptime(request.form['fecha_vigencia'], '%Y-%m-%d') if request.form.get('fecha_vigencia') else None,
            proxima_revision=datetime.strptime(request.form['proxima_revision'], '%Y-%m-%d') if request.form.get('proxima_revision') else None,
            aprobado_por=request.form.get('aprobado_por'),
            revisado_por=request.form.get('revisado_por'),
            creado_por=current_user.nombre,
            obligatorio='obligatorio' in request.form,
            distribucion=request.form.get('distribucion')
        )
        
        # Manejar archivo
        if 'archivo' in request.files:
            file = request.files['archivo']
            if file.filename:
                filename = secure_filename(f"doc_{codigo}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                documento.archivo = filename
                documento.ruta_fisica = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        db.session.add(documento)
        db.session.commit()
        
        flash(f'Documento {codigo} creado exitosamente', 'success')
        return redirect(url_for('calidad_documentos'))
    
    return render_template('calidad/documento_form.html')

# --- 5.4 KPIs y Métricas ---
@app.route('/calidad/kpis')
@login_required
def calidad_kpis():
    kpis = IndicadorCalidad.query.filter_by(estado='ACTIVO').all()
    
    # Obtener últimas mediciones para cada KPI
    kpis_data = []
    for kpi in kpis:
        ultima_medicion = MedicionKPI.query.filter_by(kpi_id=kpi.id).order_by(MedicionKPI.fecha.desc()).first()
        
        kpis_data.append({
            'kpi': kpi,
            'ultima_medicion': ultima_medicion,
            'cumple': ultima_medicion.cumplimiento if ultima_medicion else False
        })
    
    return render_template('calidad/kpis.html', kpis_data=kpis_data)

@app.route('/calidad/kpi/medir/<int:kpi_id>', methods=['GET', 'POST'])
@login_required
def calidad_kpi_medir(kpi_id):
    kpi = IndicadorCalidad.query.get_or_404(kpi_id)
    
    if request.method == 'POST':
        valor = float(request.form['valor'])
        
        medicion = MedicionKPI(
            kpi_id=kpi_id,
            valor=valor,
            valor_objetivo=kpi.objetivo,
            periodo=request.form.get('periodo', datetime.now().strftime('%Y-%m')),
            fuente=request.form.get('fuente'),
            comentarios=request.form.get('comentarios'),
            registrado_por=current_user.nombre,
            cumplimiento=valor >= kpi.objetivo if kpi.objetivo else True
        )
        
        db.session.add(medicion)
        db.session.commit()
        
        # Verificar alertas
        alertas = AlertaKPI.query.filter_by(kpi_id=kpi_id, estado='ACTIVA').all()
        for alerta in alertas:
            if alerta.tipo_alerta == 'UMBRAL_INFERIOR' and valor < alerta.valor_limite:
                notificacion = Notificacion(
                    titulo=f'Alerta KPI: {kpi.nombre}',
                    mensaje=alerta.mensaje,
                    tipo='KPI',
                    prioridad='ALTA',
                    link_accion=url_for('calidad_kpis'),
                    referencia_id=kpi_id,
                    referencia_tipo='KPI'
                )
                db.session.add(notificacion)
        
        db.session.commit()
        flash('Medición registrada exitosamente', 'success')
        return redirect(url_for('calidad_kpis'))
    
    return render_template('calidad/kpi_medir.html', kpi=kpi)

# --- 5.5 Notificaciones ---
@app.route('/calidad/notificaciones')
@login_required
def calidad_notificaciones():
    # Filtrar notificaciones para el usuario actual
    notificaciones = Notificacion.query.filter(
        (Notificacion.destinatario == current_user.nombre) |
        (Notificacion.sector_destino == current_user.sector) |
        (Notificacion.rol_destino == current_user.rol)
    ).order_by(Notificacion.fecha_envio.desc()).all()
    
    return render_template('calidad/notificaciones.html', notificaciones=notificaciones)

@app.route('/calidad/notificacion/<int:id>/leer')
@login_required
def calidad_notificacion_leer(id):
    notificacion = Notificacion.query.get_or_404(id)
    notificacion.leida = True
    notificacion.fecha_lectura = datetime.now()
    db.session.commit()
    
    if notificacion.link_accion:
        return redirect(notificacion.link_accion)
    
    return redirect(url_for('calidad_notificaciones'))

# --- 5.6 Dashboard de Calidad ---
@app.route('/calidad/dashboard')
@login_required
def calidad_dashboard():
    if current_user.rol not in ['ADMIN', 'CALIDAD']:
        return redirect(url_for('login'))
    
    # Estadísticas generales
    total_nc = NoConformidad.query.count()
    nc_abiertas = NoConformidad.query.filter(NoConformidad.estado.in_(['ABIERTA', 'EN_ANALISIS', 'EN_PROCESO'])).count()
    total_auditorias = AuditoriaRealizada.query.count()
    auditorias_aprobadas = AuditoriaRealizada.query.filter_by(estado='APROBADO').count()
    
    # NC por gravedad
    nc_por_gravedad = db.session.query(
        NoConformidad.gravedad,
        func.count(NoConformidad.id)
    ).group_by(NoConformidad.gravedad).all()
    
    # KPIs recientes
    kpis_recientes = MedicionKPI.query.order_by(MedicionKPI.fecha.desc()).limit(10).all()
    
    # Notificaciones no leídas
    notificaciones_no_leidas = Notificacion.query.filter(
        (Notificacion.destinatario == current_user.nombre) |
        (Notificacion.sector_destino == current_user.sector) |
        (Notificacion.rol_destino == current_user.rol),
        Notificacion.leida == False
    ).count()
    
    return render_template('calidad/dashboard.html',
                         total_nc=total_nc,
                         nc_abiertas=nc_abiertas,
                         total_auditorias=total_auditorias,
                         auditorias_aprobadas=auditorias_aprobadas,
                         nc_por_gravedad=nc_por_gravedad,
                         kpis_recientes=kpis_recientes,
                         notificaciones_no_leidas=notificaciones_no_leidas)

# --- Sección 7: Gestión de Ventas y Pedidos ---------------------------------------------

@app.route('/admin/ventas/corregir_ids')
@login_required
def admin_corregir_ids():
    """Ruta temporal para corregir IDs duplicados"""
    if current_user.rol not in ['ADMIN']:
        return "No autorizado", 403
    
    try:
        # Obtener todos los pedidos
        pedidos_tolva = PedidoTolva.query.all()
        pedidos_mixer = PedidoMixer.query.all()
        pedidos_att = PedidoAtt.query.all()
        pedidos_embolsadora = PedidoEmbossadora.query.all()
        pedidos_sembradora = PedidoSembradora.query.all()
        
        # Combinar todos los pedidos
        todos_los_pedidos = []
        for p in pedidos_tolva:
            todos_los_pedidos.append(('TOLVA', p))
        for p in pedidos_mixer:
            todos_los_pedidos.append(('MIXER', p))
        for p in pedidos_att:
            todos_los_pedidos.append(('ATT', p))
        for p in pedidos_embolsadora:
            todos_los_pedidos.append(('EMBOLSADORA', p))
        for p in pedidos_sembradora:
            todos_los_pedidos.append(('SEMBRADORA', p))
        
        # Obtener máximo ID
        max_id = 0
        for tipo, pedido in todos_los_pedidos:
            if pedido.id > max_id:
                max_id = pedido.id
        
        # Reasignar IDs únicos
        nuevo_id = max_id + 1
        for tipo, pedido in todos_los_pedidos:
            if pedido.id == 1:  # Si tiene ID duplicado
                # Crear nuevo registro con ID único
                db.session.delete(pedido)
                db.session.commit()
                
                # Asignar nuevo ID
                pedido.id = nuevo_id
                db.session.add(pedido)
                db.session.commit()
                
                nuevo_id += 1
        
        return "IDs corregidos exitosamente"
        
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/admin/ventas')
@login_required
def admin_ventas():
    """Panel principal de gestión de ventas y pedidos"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Obtener filtros
    estado_filtro = request.args.get('estado', '')
    implemento_filtro = request.args.get('implemento', '')
    cliente_filtro = request.args.get('cliente', '')
    
    # Obtener pedidos de todas las tablas específicas - ORDENADOS POR FECHA DE CREACIÓN
    try:
        # Consultar cada tabla específica ordenada por fecha de emisión (más nuevos primero)
        pedidos_tolva = PedidoTolva.query.order_by(PedidoTolva.fecha_emision.desc()).all()
        pedidos_mixer = PedidoMixer.query.order_by(PedidoMixer.fecha_emision.desc()).all()
        pedidos_att = PedidoAtt.query.order_by(PedidoAtt.fecha_emision.desc()).all()
        pedidos_embolsadora = PedidoEmbossadora.query.order_by(PedidoEmbossadora.fecha_emision.desc()).all()
        pedidos_sembradora = PedidoSembradora.query.order_by(PedidoSembradora.fecha_emision.desc()).all()
        
        # Combinar todos los pedidos manteniendo el orden
        pedidos = pedidos_tolva + pedidos_mixer + pedidos_att + pedidos_embolsadora + pedidos_sembradora
        
        # Ordenar final por fecha de emisión (más nuevos primero)
        pedidos.sort(key=lambda x: x.fecha_emision, reverse=True)
        
        # Agregar información de chasis para cada pedido
        for pedido in pedidos:
            pedido.chasis_info = None
            if hasattr(pedido, 'chasis_id') and pedido.chasis_id:
                if isinstance(pedido, PedidoTolva):
                    chasis = ChasisAsignadoTolva.query.get(pedido.chasis_id)
                elif isinstance(pedido, PedidoMixer):
                    chasis = ChasisAsignadoMixer.query.get(pedido.chasis_id)
                elif isinstance(pedido, PedidoAtt):
                    chasis = ChasisAsignadoAtt.query.get(pedido.chasis_id)
                elif isinstance(pedido, PedidoEmbossadora):
                    chasis = ChasisAsignadoEmbossadora.query.get(pedido.chasis_id)
                elif isinstance(pedido, PedidoSembradora):
                    chasis = ChasisAsignadoSembradora.query.get(pedido.chasis_id)
                else:
                    chasis = None
                
                if chasis:
                    pedido.chasis_info = chasis
        
    except Exception as e:
        print(f"DEBUG: Error en consulta ordenada: {e}")
        import traceback
        traceback.print_exc()
        pedidos = []
    
    # Contadores para estadísticas - versión con nuevos estados
    no_asignados_count = asignados_count = modificacion_solicitada_count = eliminacion_solicitada_count = 0
    disponible_eliminar_count = en_proceso_count = fabricado_count = entregado_count = 0
    modificacion_aprobada_count = 0
    
    try:
        no_asignados_count = (
            PedidoTolva.query.filter((PedidoTolva.estado == 'NO ASIGNADO') | (PedidoTolva.estado == 'PENDIENTE')).count() +
            PedidoMixer.query.filter((PedidoMixer.estado == 'NO ASIGNADO') | (PedidoMixer.estado == 'PENDIENTE')).count() +
            PedidoAtt.query.filter((PedidoAtt.estado == 'NO ASIGNADO') | (PedidoAtt.estado == 'PENDIENTE')).count() +
            PedidoEmbossadora.query.filter((PedidoEmbossadora.estado == 'NO ASIGNADO') | (PedidoEmbossadora.estado == 'PENDIENTE')).count() +
            PedidoSembradora.query.filter((PedidoSembradora.estado == 'NO ASIGNADO') | (PedidoSembradora.estado == 'PENDIENTE')).count()
        )
        
        asignados_count = (
            PedidoTolva.query.filter_by(estado='ASIGNADO').count() +
            PedidoMixer.query.filter_by(estado='ASIGNADO').count() +
            PedidoAtt.query.filter_by(estado='ASIGNADO').count() +
            PedidoEmbossadora.query.filter_by(estado='ASIGNADO').count() +
            PedidoSembradora.query.filter_by(estado='ASIGNADO').count()
        )
        
        modificacion_solicitada_count = (
            PedidoTolva.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
            PedidoMixer.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
            PedidoAtt.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
            PedidoEmbossadora.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
            PedidoSembradora.query.filter_by(estado='CAMBIO_SOLICITADO').count()
        )
        
        modificacion_aprobada_count = (
            SolicitudCambioPedido.query.filter_by(estado='APROBADA').count()
        )
        
        eliminacion_solicitada_count = (
            PedidoTolva.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
            PedidoMixer.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
            PedidoAtt.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
            PedidoEmbossadora.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
            PedidoSembradora.query.filter_by(estado='ELIMINACION_SOLICITADA').count()
        )
        
        disponible_eliminar_count = (
            PedidoTolva.query.filter_by(estado='DISPONIBLE_PARA_ELIMINAR').count() +
            PedidoMixer.query.filter_by(estado='DISPONIBLE_PARA_ELIMINAR').count() +
            PedidoAtt.query.filter_by(estado='DISPONIBLE_PARA_ELIMINAR').count() +
            PedidoEmbossadora.query.filter_by(estado='DISPONIBLE_PARA_ELIMINAR').count() +
            PedidoSembradora.query.filter_by(estado='DISPONIBLE_PARA_ELIMINAR').count()
        )
        
        en_proceso_count = (
            PedidoTolva.query.filter_by(estado='EN PROCESO').count() +
            PedidoMixer.query.filter_by(estado='EN PROCESO').count() +
            PedidoAtt.query.filter_by(estado='EN PROCESO').count() +
            PedidoEmbossadora.query.filter_by(estado='EN PROCESO').count() +
            PedidoSembradora.query.filter_by(estado='EN PROCESO').count()
        )
        
        fabricado_count = (
            PedidoTolva.query.filter_by(estado='FABRICADO (SIN ENTREGAR)').count() +
            PedidoMixer.query.filter_by(estado='FABRICADO (SIN ENTREGAR)').count() +
            PedidoAtt.query.filter_by(estado='FABRICADO (SIN ENTREGAR)').count() +
            PedidoEmbossadora.query.filter_by(estado='FABRICADO (SIN ENTREGAR)').count() +
            PedidoSembradora.query.filter_by(estado='FABRICADO (SIN ENTREGAR)').count()
        )
        
        entregado_count = (
            PedidoTolva.query.filter_by(estado='ENTREGADO').count() +
            PedidoMixer.query.filter_by(estado='ENTREGADO').count() +
            PedidoAtt.query.filter_by(estado='ENTREGADO').count() +
            PedidoEmbossadora.query.filter_by(estado='ENTREGADO').count() +
            PedidoSembradora.query.filter_by(estado='ENTREGADO').count()
        )
        
        print(f"SIMPLIFICADO - Contadores calculados")
        
    except Exception as e:
        # Los contadores quedan en 0, pero No afectamos a pedidos
        pass
    
    return render_template('ventas.html', 
                        pedidos=pedidos,
                        no_asignados_count=no_asignados_count,
                        asignados_count=asignados_count,
                        modificacion_solicitada_count=modificacion_solicitada_count,
                        eliminacion_solicitada_count=eliminacion_solicitada_count,
                        disponible_eliminar_count=disponible_eliminar_count,
                        modificacion_aprobada_count=modificacion_aprobada_count,
                        en_proceso_count=en_proceso_count,
                        fabricado_count=fabricado_count,
                        entregado_count=entregado_count,
                        estado_filtro=estado_filtro,
                        implemento_filtro=implemento_filtro,
                        cliente_filtro=cliente_filtro,
                        usuario_actual=current_user)

@app.route('/admin/ventas/solicitar_modificacion/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def admin_ventas_solicitar_modificacion(pedido_id):
    """Solicitar modificación de chasis para un pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Buscar el pedido en todas las tablas
    pedido = None
    tabla_actual = None
    
    # Intentar encontrar en cada tabla
    if not pedido:
        pedido = PedidoTolva.query.get(pedido_id)
        if pedido:
            tabla_actual = 'tolva'
    
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
        if pedido:
            tabla_actual = 'mixer'
    
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
        if pedido:
            tabla_actual = 'att'
    
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
        if pedido:
            tabla_actual = 'embossadora'
    
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
        if pedido:
            tabla_actual = 'sembradora'
    
    if not pedido:
        flash('Pedido no encontrado', 'error')
        return redirect(url_for('admin_ventas'))
    
    # Verificar que el pedido esté asignado
    if pedido.estado != 'ASIGNADO':
        flash('Solo se pueden solicitar modificaciones para pedidos asignados', 'error')
        return redirect(url_for('admin_ventas'))
    
    if request.method == 'POST':
        # Procesar solicitud
        motivo = request.form.get('motivo')
        campo_modificar = request.form.get('campo_modificar')
        detalle_cambio = request.form.get('detalle_cambio')
        
        if not motivo or not campo_modificar:
            flash('Debe especificar el motivo y el campo a modificar', 'error')
            return render_template('solicitar_modificacion.html', 
                                 pedido=pedido, 
                                 tabla_actual=tabla_actual)
        
        # Crear descripción completa de la modificación
        descripcion_completa = f"MODIFICAR {campo_modificar.upper()}: {detalle_cambio}. MOTIVO: {motivo}"
        
        # Actualizar estado del pedido a CAMBIO_SOLICITADO
        pedido.estado = 'CAMBIO_SOLICITADO'
        
        # Crear registro de solicitud (podríamos usar una tabla dedicada más adelante)
        # Por ahora, solo actualizamos el estado
        
        db.session.commit()
        
        flash(f'Solicitud de modificación enviada correctamente. PCP procesará tu solicitud para modificar: {campo_modificar}.', 'success')
        return redirect(url_for('admin_ventas'))
    
    # Mostrar formulario
    return render_template('solicitar_modificacion.html', 
                         pedido=pedido, 
                         tabla_actual=tabla_actual)

@app.route('/admin/ventas/solicitar_cambio/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def admin_ventas_solicitar_cambio(pedido_id):
    """Solicitar cambio de chasis para un pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Obtener pedido
    pedido = PedidoTolva.query.get_or_404(pedido_id)
    
    # Verificar que el pedido esté asignado
    if not pedido.chasis_id or pedido.estado != 'ASIGNADO':
        flash('Solo se pueden solicitar cambios para pedidos asignados', 'error')
        return redirect(url_for('admin_ventas'))
    
    # Obtener chasis actual
    chasis_actual = ChasisAsignadoTolva.query.get(pedido.chasis_id)
    
    if request.method == 'POST':
        # Procesar solicitud
        chasis_nuevo_id = request.form.get('chasis_nuevo_id')
        motivo = request.form.get('motivo')
        
        if not chasis_nuevo_id or not motivo:
            flash('Debe seleccionar un chasis y especificar el motivo', 'error')
            return render_template('solicitar_cambio.html', 
                                 pedido=pedido, 
                                 chasis_actual=chasis_actual,
                                 chasis_disponibles=ChasisAsignadoTolva.query.all())
        
        # Crear solicitud
        solicitud = SolicitudCambioPedido(
            pedido_id=pedido_id,
            chasis_actual_id=pedido.chasis_id,
            chasis_nuevo_id=chasis_nuevo_id,
            motivo=motivo,
            solicitante_id=current_user.id
        )
        
        # Actualizar estado del pedido
        pedido.estado = 'CAMBIO_SOLICITADO'
        
        db.session.add(solicitud)
        db.session.commit()
        
        flash('Solicitud de cambio enviada correctamente', 'success')
        return redirect(url_for('admin_ventas'))
    
    # Mostrar formulario
    chasis_disponibles = ChasisAsignadoTolva.query.filter(
        ChasisAsignadoTolva.id != pedido.chasis_id
    ).all()
    
    return render_template('solicitar_cambio.html', 
                         pedido=pedido, 
                         chasis_actual=chasis_actual,
                         chasis_disponibles=chasis_disponibles)

@app.route('/admin/ventas/solicitar_eliminacion/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def admin_ventas_solicitar_eliminacion(pedido_id):
    """Solicitar eliminación de pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Obtener pedido
    pedido = PedidoTolva.query.get_or_404(pedido_id)
    
    # Verificar que el pedido esté asignado y tenga chasis
    if not pedido.chasis_id:
        flash('El pedido no tiene un chasis asignado. No se puede solicitar eliminación.', 'error')
        return redirect(url_for('admin_ventas'))
    
    if pedido.estado not in ['ASIGNADO', 'CAMBIO_SOLICITADO']:
        flash(f'El pedido está en estado "{pedido.estado}". Solo se puede solicitar eliminación para pedidos asignados.', 'error')
        return redirect(url_for('admin_ventas'))
    
    # Obtener chasis asignado
    chasis_asignado = ChasisAsignadoTolva.query.get(pedido.chasis_id)
    
    if request.method == 'POST':
        # Procesar solicitud
        motivo = request.form.get('motivo')
        
        if not motivo:
            flash('Debe especificar el motivo de la eliminación', 'error')
            return render_template('solicitar_eliminacion.html', 
                                 pedido=pedido, 
                                 chasis_asignado=chasis_asignado)
        
        # Crear solicitud
        solicitud = SolicitudEliminacionPedido(
            pedido_id=pedido_id,
            chasis_asignado_id=pedido.chasis_id,
            motivo=motivo,
            solicitante_id=current_user.id
        )
        
        # Actualizar estado del pedido
        pedido.estado = 'ELIMINACION_SOLICITADA'
        
        db.session.add(solicitud)
        db.session.commit()
        
        flash('Solicitud de eliminación enviada correctamente', 'success')
        return redirect(url_for('admin_ventas'))
    
    # Mostrar formulario
    return render_template('solicitar_eliminacion.html', 
                         pedido=pedido, 
                         chasis_asignado=chasis_asignado)

@app.route('/admin/ventas/eliminar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def admin_ventas_eliminar_pedido(pedido_id):
    """Eliminar pedido directamente (solo para pedidos sin chasis asignado o desasignados)"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Obtener pedido
    pedido = PedidoTolva.query.get_or_404(pedido_id)
    
    # Verificar que el pedido pueda ser eliminado directamente
    if pedido.estado not in ['NO ASIGNADO', 'PENDIENTE', 'DISPONIBLE_PARA_ELIMINAR']:
        return jsonify({'success': False, 'message': 'Este pedido no puede ser eliminado directamente'}), 400
    
    # Si tiene chasis asignado, liberarlo
    if pedido.chasis_id:
        pedido.chasis_id = None
    
    # Eliminar el pedido
    db.session.delete(pedido)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Pedido eliminado correctamente'})

@app.route('/admin/ventas/obtener_proximo_pedido')
@login_required
def admin_obtener_proximo_pedido():
    """Obtener el próximo número de pedido disponible"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        proximo_numero = generar_numero_pedido()
        return jsonify({'proximo_pedido': proximo_numero})
    except Exception as e:
        print(f"Error obteniendo próximo pedido: {e}")
        return jsonify({'error': 'Error al generar número de pedido'}), 500

def generar_numero_pedido():
    """Generar automáticamente el próximo número de pedido único"""
    try:
        # Obtener el máximo número de pedido de todas las tablas
        max_numero = 0
        
        # Buscar en todas las tablas de pedidos
        tablas = [
            (PedidoTolva, 'pedido'),
            (PedidoMixer, 'pedido'), 
            (PedidoAtt, 'pedido'),
            (PedidoEmbossadora, 'pedido'),
            (PedidoSembradora, 'pedido')
        ]
        
        for tabla, campo in tablas:
            try:
                # Obtener todos los números de pedido y convertir a enteros
                pedidos = db.session.query(getattr(tabla, campo)).all()
                for pedido_tuple in pedidos:
                    numero_str = pedido_tuple[0]
                    if numero_str and numero_str.isdigit():
                        numero = int(numero_str)
                        if numero > max_numero:
                            max_numero = numero
            except Exception as e:
                print(f"Error buscando en tabla {tabla.__name__}: {e}")
                continue
        
        # Generar el siguiente número
        siguiente_numero = max_numero + 1
        
        print(f"DEBUG: Número de pedido generado: {siguiente_numero}")
        return str(siguiente_numero)
        
    except Exception as e:
        print(f"Error generando número de pedido: {e}")
        # En caso de error, usar timestamp como fallback
        import time
        return str(int(time.time()))

@app.route('/admin/ventas/nuevo_pedido', methods=['POST'])
@login_required
def admin_nuevo_pedido():
    """Crear un nuevo pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    try:
        # Importar time al inicio para que esté disponible en todo el contexto
        import time
        
        # Generar automáticamente el número de pedido
        nro_pedido = generar_numero_pedido()
        
        # Validar campos obligatorios (excluir 'pedido' que se genera automáticamente)
        campos_obligatorios = ['cliente', 'modelo', 'concesionario', 'localidad', 'llantas', 'cubiertas', 'color', 'balanza', 'observaciones']
        
        for campo in campos_obligatorios:
            if campo not in request.form or not request.form[campo].strip():
                flash(f'El campo "{campo.upper()}" es obligatorio y no puede estar vacío', 'danger')
                return redirect(url_for('admin_ventas'))
        
        print(f"DEBUG: Todos los campos obligatorios están presentes")
        
        print(f"DEBUG: Número de pedido generado automáticamente: {nro_pedido}")
        
        implemento = request.form['implemento']
        
        # Procesar PDF del pedido si se adjuntó
        pdf_pedido = None
        if 'pdf_pedido' in request.files:
            pdf_file = request.files['pdf_pedido']
            if pdf_file and pdf_file.filename:
                # Generar nombre único con timestamp y nro_pedido
                timestamp = int(time.time())
                filename = secure_filename(f"pedido_{nro_pedido}_{timestamp}_{pdf_file.filename}")
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                pdf_file.save(pdf_path)
                pdf_pedido = filename
        
        # Seleccionar el modelo específico según el implemento
        if implemento == 'TOLVA':
            pedido = PedidoTolva(
                pedido=nro_pedido,  # Usar directamente el número de pedido
                cliente=request.form['cliente'],
                modelo=request.form['modelo'],
                implemento=implemento,
                concesionario=request.form['concesionario'],
                localidad=request.form['localidad'],
                llantas=request.form['llantas'],
                cubiertas=request.form['cubiertas'],
                color=request.form['color'],
                balanza=request.form['balanza'],
                observaciones=request.form['observaciones'],
                pdf_pedido=pdf_pedido,  # Guardar ruta del PDF
                creado_por=current_user.nombre
            )
        elif implemento == 'MIXER':
            pedido = PedidoMixer(
                pedido=nro_pedido,
                cliente=request.form['cliente'],
                modelo=request.form['modelo'],
                implemento=implemento,
                concesionario=request.form['concesionario'],
                localidad=request.form['localidad'],
                observaciones=request.form['observaciones'],
                pdf_pedido=pdf_pedido,  # Guardar ruta del PDF
                creado_por=current_user.nombre
            )
            # Campos opcionales de MIXER
            if 'tipo_motor' in request.form and request.form['tipo_motor']:
                pedido.tipo_motor = request.form['tipo_motor']
            if 'capacidad' in request.form and request.form['capacidad']:
                pedido.capacidad = request.form['capacidad']
            if 'sistema_hidraulico' in request.form and request.form['sistema_hidraulico']:
                pedido.sistema_hidraulico = request.form['sistema_hidraulico']
                
        elif implemento == 'ATT':
            pedido = PedidoAtt(
                pedido=nro_pedido,
                cliente=request.form['cliente'],
                modelo=request.form['modelo'],
                implemento=implemento,
                concesionario=request.form['concesionario'],
                localidad=request.form['localidad'],
                observaciones=request.form['observaciones'],
                pdf_pedido=pdf_pedido,  # Guardar ruta del PDF
                creado_por=current_user.nombre
            )
            # Campos opcionales de ATT
            if 'tipo_corte' in request.form and request.form['tipo_corte']:
                pedido.tipo_corte = request.form['tipo_corte']
            if 'ancho_corte' in request.form and request.form['ancho_corte']:
                pedido.ancho_corte = request.form['ancho_corte']
            if 'sistema_alimentacion' in request.form and request.form['sistema_alimentacion']:
                pedido.sistema_alimentacion = request.form['sistema_alimentacion']
                
        elif implemento == 'EMBOLSADORA':
            pedido = PedidoEmbossadora(
                pedido=nro_pedido,
                cliente=request.form['cliente'],
                modelo=request.form['modelo'],
                implemento=implemento,
                concesionario=request.form['concesionario'],
                localidad=request.form['localidad'],
                observaciones=request.form['observaciones'],
                pdf_pedido=pdf_pedido,  # Guardar ruta del PDF
                creado_por=current_user.nombre
            )
            # Campos opcionales de EMBOLSADORA
            if 'tipo_bolsa' in request.form and request.form['tipo_bolsa']:
                pedido.tipo_bolsa = request.form['tipo_bolsa']
                
        elif implemento == 'SEMBRADORA':
            pedido = PedidoSembradora(
                pedido=nro_pedido,
                cliente=request.form['cliente'],
                modelo=request.form['modelo'],
                implemento=implemento,
                concesionario=request.form['concesionario'],
                localidad=request.form['localidad'],
                observaciones=request.form['observaciones'],
                pdf_pedido=pdf_pedido,  # Guardar ruta del PDF
                creado_por=current_user.nombre
            )
            # Campos opcionales de SEMBRADORA
            if 'ancho_trabajo' in request.form and request.form['ancho_trabajo']:
                pedido.ancho_trabajo = request.form['ancho_trabajo']
        else:
            flash('Implemento no válido', 'danger')
            return redirect(url_for('admin_ventas'))
        
        # Procesar fecha de emisión si viene del formulario
        if 'fecha_emision' in request.form and request.form['fecha_emision']:
            pedido.fecha_emision = datetime.strptime(request.form['fecha_emision'], '%Y-%m-%d').date()
        else:
            pedido.fecha_emision = datetime.now().date()
        
        # Fecha compromiso opcional
        if 'fecha_compromiso' in request.form and request.form['fecha_compromiso']:
            pedido.fecha_compromiso = datetime.strptime(request.form['fecha_compromiso'], '%Y-%m-%d').date()
        else:
            pedido.fecha_compromiso = pedido.fecha_emision
        
        # Establecer valores por defecto para campos obligatorios
        pedido.cantidad = 1  # Valor por defecto
        pedido.prioridad = 'NORMAL'  # Valor por defecto
        pedido.estado = 'PENDIENTE'  # Estado inicial
        
        print(f"DEBUG: Creando pedido - N° Pedido: {nro_pedido}, Implemento: {implemento}")
        print(f"DEBUG: Campos - Pedido: {request.form.get('pedido')}, Cliente: {request.form.get('cliente')}")
        
        db.session.add(pedido)
        db.session.commit()
        
        print(f"DEBUG: Pedido guardado con ID: {pedido.id}")
        
        # Registrar historial
        try:
            historial = HistorialEstadoPedido(
                pedido_id=pedido.id,
                estado_anterior=None,
                estado_nuevo='PENDIENTE',
                usuario=current_user.nombre,
                motivo='Creación del pedido'
            )
            db.session.add(historial)
            db.session.commit()
            print(f"DEBUG: Historial registrado para pedido ID: {pedido.id}")
        except Exception as e:
            print(f"DEBUG: Error al crear historial: {e}")
            # No fallar si el historial no se puede crear
        
        flash(f'Pedido {nro_pedido} creado exitosamente', 'success')
        print(f"DEBUG: Pedido {nro_pedido} creado exitosamente")
        
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error al crear pedido: {e}")
        flash(f'Error al crear el pedido: {str(e)}', 'danger')
    
    # Redireccionar con parámetro para forzar actualización
    print(f"DEBUG: Redirigiendo a admin_ventas con refresh=1")
    return redirect(url_for('admin_ventas') + '?refresh=' + str(int(time.time())))

@app.route('/admin/ventas/ver_pedido/<int:pedido_id>')
@login_required
def admin_ver_pedido(pedido_id):
    """Obtener detalles de un pedido en formato JSON"""
    if current_user.rol not in ['ADMIN', 'VENTAS', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    # Buscar el pedido en todas las tablas específicas
    pedido = None
    pedido = PedidoTolva.query.get(pedido_id)
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
    
    if not pedido:
        return jsonify({'error': 'Pedido no encontrado'}), 404
    
    # Preparar datos base del pedido - solo campos que existen en todos los modelos
    datos_pedido = {
        'id': pedido.id,
        'codigo_pedido': pedido.pedido,
        'cliente': pedido.cliente,
        'modelo': pedido.modelo,
        'implemento': pedido.implemento,
        'fecha_compromiso': pedido.fecha_compromiso.isoformat() if pedido.fecha_compromiso else None,
        'estado': pedido.estado,
        'observaciones': getattr(pedido, 'observaciones', None),
        'pdf_pedido': getattr(pedido, 'pdf_pedido', None)
    }
    
    # Agregar campos específicos si existen
    if hasattr(pedido, 'fecha_ingreso') and pedido.fecha_ingreso:
        datos_pedido['fecha_ingreso'] = pedido.fecha_ingreso.isoformat()
    
    if hasattr(pedido, 'fecha_emision') and pedido.fecha_emision:
        datos_pedido['fecha_emision'] = pedido.fecha_emision.isoformat()
    
    # Agregar información de chasis específica según el tipo
    if isinstance(pedido, PedidoTolva):
        # Para TOLVA, usar la relación chasis_asignado
        if hasattr(pedido, 'chasis_asignado') and pedido.chasis_asignado:
            datos_pedido['chasis_asignado'] = pedido.chasis_asignado.nro_chasis
        else:
            datos_pedido['chasis_asignado'] = None
        
        # Campos específicos de TOLVA
        datos_pedido['concesionario'] = getattr(pedido, 'concesionario', None)
        datos_pedido['localidad'] = getattr(pedido, 'localidad', None)
        datos_pedido['llantas'] = getattr(pedido, 'llantas', None)
        datos_pedido['cubiertas'] = getattr(pedido, 'cubiertas', None)
        datos_pedido['color'] = getattr(pedido, 'color', None)
        datos_pedido['balanza'] = getattr(pedido, 'balanza', None)
    else:
        # Para otros tipos, chasis_asignado es un campo string
        datos_pedido['chasis_asignado'] = getattr(pedido, 'chasis_asignado', None)
    
    # Campos opcionales que pueden existir en algunos modelos
    for campo in ['vendedor', 'forma_pago', 'precio_unitario', 'precio_total']:
        if hasattr(pedido, campo):
            datos_pedido[campo] = getattr(pedido, campo)
    
    return jsonify(datos_pedido)

@app.route('/admin/ventas/editar_pedido/<int:pedido_id>')
@login_required
def admin_editar_pedido(pedido_id):
    """Mostrar formulario para editar un pedido existente"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Buscar el pedido en todas las tablas específicas
    pedido = None
    pedido = PedidoTolva.query.get(pedido_id)
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
    
    if not pedido:
        return "Pedido no encontrado", 404
    
    return render_template('editar_pedido.html', pedido=pedido)

@app.route('/admin/ventas/actualizar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def admin_actualizar_pedido(pedido_id):
    """Actualizar un pedido existente"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return "No autorizado", 403
    
    # Buscar el pedido en todas las tablas específicas
    pedido = None
    pedido = PedidoTolva.query.get(pedido_id)
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
    
    if not pedido:
        return "Pedido no encontrado", 404
    
    try:
        # Actualizar campos comunes
        pedido.pedido = request.form['pedido']
        pedido.cliente = request.form['cliente']
        pedido.modelo = request.form['modelo']
        pedido.concesionario = request.form['concesionario']
        pedido.localidad = request.form['localidad']
        pedido.observaciones = request.form['observaciones']
        
        # Actualizar fecha de emisión si viene del formulario
        if 'fecha_emision' in request.form and request.form['fecha_emision']:
            pedido.fecha_emision = datetime.strptime(request.form['fecha_emision'], '%Y-%m-%d').date()
        
        # Actualizar fecha compromiso si viene del formulario
        if 'fecha_compromiso' in request.form and request.form['fecha_compromiso']:
            pedido.fecha_compromiso = datetime.strptime(request.form['fecha_compromiso'], '%Y-%m-%d').date()
        
        # Actualizar campos específicos según el implemento
        if pedido.implemento == 'TOLVA':
            pedido.llantas = request.form.get('llantas', pedido.llantas)
            pedido.cubiertas = request.form.get('cubiertas', pedido.cubiertas)
            pedido.color = request.form.get('color', pedido.color)
            pedido.balanza = request.form.get('balanza', pedido.balanza)
        elif pedido.implemento == 'MIXER':
            pedido.tipo_motor = request.form.get('tipo_motor', pedido.tipo_motor)
            pedido.capacidad = request.form.get('capacidad', pedido.capacidad)
            pedido.sistema_hidraulico = request.form.get('sistema_hidraulico', pedido.sistema_hidraulico)
        elif pedido.implemento == 'ATT':
            pedido.tipo_corte = request.form.get('tipo_corte', pedido.tipo_corte)
            pedido.ancho_corte = request.form.get('ancho_corte', pedido.ancho_corte)
            pedido.sistema_alimentacion = request.form.get('sistema_alimentacion', pedido.sistema_alimentacion)
        elif pedido.implemento == 'EMBOLSADORA':
            pedido.tipo_bolsa = request.form.get('tipo_bolsa', pedido.tipo_bolsa)
        elif pedido.implemento == 'SEMBRADORA':
            pedido.ancho_trabajo = request.form.get('ancho_trabajo', pedido.ancho_trabajo)
        
        # Procesar PDF si se adjuntó uno nuevo o se solicitó eliminar
        if request.form.get('eliminar_pdf') == 'true':
            # Eliminar el PDF existente
            if pedido.pdf_pedido:
                # Eliminar el archivo del sistema de archivos
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pedido.pdf_pedido)
                if os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception as e:
                        print(f"Error al eliminar archivo PDF: {e}")
                
                # Limpiar el campo en la base de datos
                pedido.pdf_pedido = None
        elif 'pdf_pedido' in request.files:
            pdf_file = request.files['pdf_pedido']
            if pdf_file and pdf_file.filename:
                # Generar nombre único con timestamp y nro_pedido
                import time
                timestamp = int(time.time())
                filename = secure_filename(f"pedido_{pedido.pedido}_{timestamp}_{pdf_file.filename}")
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                pdf_file.save(pdf_path)
                pedido.pdf_pedido = filename
        
        pedido.modificado_por = current_user.nombre
        pedido.fecha_modificacion = datetime.now()
        
        db.session.commit()
        
        flash(f'Pedido {pedido.pedido} actualizado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el pedido: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ventas'))

@app.route('/admin/ventas/eliminar_pedido/<int:pedido_id>', methods=['DELETE'])
@login_required
def admin_eliminar_pedido(pedido_id):
    """Eliminar un pedido existente"""
    if current_user.rol not in ['ADMIN', 'VENTAS']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    with app.app_context():  # Asegurar contexto de aplicación
        try:
            # Buscar el pedido en todas las tablas específicas
            pedido = None
            pedido = PedidoTolva.query.get(pedido_id)
            if not pedido:
                pedido = PedidoMixer.query.get(pedido_id)
            if not pedido:
                pedido = PedidoAtt.query.get(pedido_id)
            if not pedido:
                pedido = PedidoEmbossadora.query.get(pedido_id)
            if not pedido:
                pedido = PedidoSembradora.query.get(pedido_id)
            
            if not pedido:
                return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
            
            # Verificar si el pedido puede ser eliminado (no está en producción)
            if pedido.estado in ['EN_PRODUCCION', 'COMPLETADO']:
                return jsonify({
                    'success': False, 
                    'message': f'No se puede eliminar el pedido {pedido.pedido} porque está {pedido.estado}'
                }), 400
            
            # Eliminar PDF adjunto si existe
            if pedido.pdf_pedido:
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pedido.pdf_pedido)
                if os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception as e:
                        print(f"Error al eliminar archivo PDF: {e}")
            
            # Eliminar historial de estados del pedido
            try:
                historial = HistorialEstadoPedido.query.filter_by(pedido_id=pedido.id).all()
                for hist in historial:
                    db.session.delete(hist)
            except Exception as e:
                print(f"Error al eliminar historial: {e}")
            
            # Eliminar solicitudes de eliminación relacionadas
            try:
                if isinstance(pedido, PedidoTolva):
                    solicitudes = SolicitudEliminacionPedido.query.filter_by(pedido_id=pedido.id).all()
                elif isinstance(pedido, PedidoMixer):
                    # Para otros implementos, buscar en tablas correspondientes si existen
                    solicitudes = []
                else:
                    solicitudes = []
                
                for sol in solicitudes:
                    db.session.delete(sol)
            except Exception as e:
                print(f"Error al eliminar solicitudes de eliminación: {e}")
            
            # Guardar número del pedido para el mensaje
            nro_pedido = pedido.pedido
            
            # Eliminar el pedido
            db.session.delete(pedido)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Pedido {nro_pedido} eliminado exitosamente'
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"Error detallado al eliminar pedido: {e}")
            return jsonify({
                'success': False, 
                'message': f'Error al eliminar el pedido: {str(e)}'
            }), 500

@app.route('/admin/ventas/ver_pdf/<filename>')
@login_required
def admin_ver_pdf(filename):
    """Ver un PDF del pedido en el navegador"""
    if current_user.rol not in ['ADMIN', 'VENTAS', 'PCP']:
        return "No autorizado", 403
    
    try:
        # Construir la ruta completa al archivo
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            return "PDF no encontrado", 404
        
        # Enviar el archivo al navegador
        return send_file(pdf_path, mimetype='application/pdf')
        
    except Exception as e:
        print(f"Error al ver PDF: {e}")
        return "Error al cargar el PDF", 500

@app.route('/admin/ventas/descargar_pdf/<filename>')
@login_required
def admin_descargar_pdf(filename):
    """Descargar un PDF del pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS', 'PCP']:
        return "No autorizado", 403
    
    try:
        # Construir la ruta completa al archivo
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            return "PDF no encontrado", 404
        
        # Enviar el archivo como descarga
        return send_file(pdf_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        print(f"Error al descargar PDF: {e}")
        return "Error al descargar el PDF", 500

@app.route('/admin/ventas/obtener_chasis_disponibles/<int:pedido_id>')
@login_required
def admin_obtener_chasis_disponibles(pedido_id):
    """Obtener chasis disponibles para un pedido específico"""
    if current_user.rol not in ['ADMIN', 'VENTAS', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    # Buscar el pedido en todas las tablas específicas
    pedido = None
    pedido = PedidoTolva.query.get(pedido_id)
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
    
    if not pedido:
        return jsonify({'error': 'Pedido no encontrado'}), 404
    
    # Obtener chasis disponibles según el implemento
    chasis_disponibles = []
    if pedido.implemento == 'TOLVA':
        # Buscar chasis en ChasisAsignadoTolva con cliente = 'STOCK' o sin cliente (en producción)
        chasis_asignados = db.session.query(ChasisAsignadoTolva.nro_chasis).filter(
            ChasisAsignadoTolva.nro_chasis.isnot(None),
            db.or_(
                ChasisAsignadoTolva.cliente == 'STOCK',
                ChasisAsignadoTolva.cliente.is_(None),
                ChasisAsignadoTolva.cliente == '',
                db.func.trim(ChasisAsignadoTolva.cliente) == ''
            )
        ).order_by(ChasisAsignadoTolva.nro_chasis).all()  # Ordenar por número de chasis
        
        chasis_ocupados = db.session.query(Pedido.chasis_asignado).filter(
            Pedido.chasis_asignado.isnot(None),
            Pedido.estado.in_(['ASIGNADO', 'EN_PRODUCCION'])
        ).all()
        
        chasis_ocupados_set = {c[0] for c in chasis_ocupados}
        chasis_disponibles_set = {c[0] for c in chasis_asignados}
        
        chasis_libres = chasis_disponibles_set - chasis_ocupados_set
        
        for chasis_num in chasis_libres:
            chasis_info = ChasisAsignadoTolva.query.filter_by(nro_chasis=chasis_num).first()
            if chasis_info:
                chasis_disponibles.append({
                    'nro_chasis': chasis_info.nro_chasis,
                    'modelo': chasis_info.modelo,
                    'cliente': chasis_info.cliente
                })
    
    return jsonify({
        'pedido': {
            'id': pedido.id,
            'codigo_pedido': pedido.pedido,
            'cliente': pedido.cliente,
            'implemento': pedido.implemento
        },
        'chasis_disponibles': chasis_disponibles
    })

@app.route('/admin/ventas/asignar_chasis', methods=['POST'])
@login_required
def admin_asignar_chasis():
    """Asignar un chasis a un pedido"""
    if current_user.rol not in ['ADMIN', 'VENTAS', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json()
    pedido_id = data['pedido_id']
    chasis_asignado = data['chasis_asignado']
    
    try:
        # Buscar el pedido en todas las tablas específicas
        pedido = None
        pedido = PedidoTolva.query.get(pedido_id)
        if not pedido:
            pedido = PedidoMixer.query.get(pedido_id)
        if not pedido:
            pedido = PedidoAtt.query.get(pedido_id)
        if not pedido:
            pedido = PedidoEmbossadora.query.get(pedido_id)
        if not pedido:
            pedido = PedidoSembradora.query.get(pedido_id)
        
        if not pedido:
            return jsonify({'error': 'Pedido no encontrado'}), 404
        
        # Actualizar pedido según el tipo
        if isinstance(pedido, PedidoTolva):
            # PedidoTolva no maneja chasis_asignado ni fecha_asignacion_chasis
            # Solo actualizamos el estado
            pedido.estado = 'ASIGNADO'
        else:
            # Para otros modelos que sí tienen estos campos
            pedido.chasis_asignado = chasis_asignado
            pedido.estado = 'ASIGNADO'
            pedido.fecha_asignacion_chasis = datetime.now()
            pedido.modificado_por = current_user.nombre
            pedido.fecha_modificacion = datetime.now()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Chasis asignado exitosamente'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# --- Sección 8: Gestión PCP (Planificación y Control de Producción) -------------------

@app.route('/admin/pcp')
@login_required
def admin_pcp():
    """Panel principal de PCP"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return "No autorizado", 403
    
    # Estadísticas - usar nuevos estados del flujo de trabajo
    pedidos_pendientes_count = (
        PedidoTolva.query.filter_by(estado='PENDIENTE').count() +
        PedidoMixer.query.filter_by(estado='PENDIENTE').count() +
        PedidoAtt.query.filter_by(estado='PENDIENTE').count() +
        PedidoEmbossadora.query.filter_by(estado='PENDIENTE').count() +
        PedidoSembradora.query.filter_by(estado='PENDIENTE').count()
    )
    
    # Contadores para solicitudes de Ventas
    modificacion_solicitada_count = (
        PedidoTolva.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
        PedidoMixer.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
        PedidoAtt.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
        PedidoEmbossadora.query.filter_by(estado='CAMBIO_SOLICITADO').count() +
        PedidoSembradora.query.filter_by(estado='CAMBIO_SOLICITADO').count()
    )
    
    eliminacion_solicitada_count = (
        PedidoTolva.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
        PedidoMixer.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
        PedidoAtt.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
        PedidoEmbossadora.query.filter_by(estado='ELIMINACION_SOLICITADA').count() +
        PedidoSembradora.query.filter_by(estado='ELIMINACION_SOLICITADA').count()
    )
    
    chasis_disponibles_count = 0
    
    # Función para verificar si un chasis está completo (todos los puestos en verde), no entregado y es STOCK
    def chasis_esta_completado_y_no_entregado(chasis_nro):
        try:
            # Buscar todos los planes de producción para este chasis
            planes_chasis = PlanProduccion.query.filter_by(nro_chasis=chasis_nro).all()
            
            if not planes_chasis:
                return False
            
            # Verificar si hay algún plan que no esté TERMINADO
            for plan in planes_chasis:
                if plan.estado != 'TERMINADO':
                    return False
            
            # Si todos los planes están en TERMINADO, el chasis está completo
            return True
            
        except Exception as e:
            print(f"Error verificando chasis {chasis_nro}: {e}")
            return False
    
    # Contar chasis disponibles por implemento (solo TOLVA por ahora)
    chasis_tolva = ChasisAsignadoTolva.query.filter(ChasisAsignadoTolva.nro_chasis.isnot(None)).all()
    
    # Para cada chasis, verificar si está completo, no entregado y es STOCK
    for chasis in chasis_tolva:
        if chasis_esta_completado_y_no_entregado(chasis.nro_chasis) and chasis.cliente == 'STOCK':
            chasis_disponibles_count += 1
            print(f"Chasis disponible encontrado: {chasis.nro_chasis} (cliente: {chasis.cliente})")
    
    print(f"Total chasis disponibles encontrados: {chasis_disponibles_count}")
    
    # En producción (usar nuevo estado "EN PROCESO")
    en_produccion_count = (
        PedidoTolva.query.filter_by(estado='EN PROCESO').count() +
        PedidoMixer.query.filter_by(estado='EN PROCESO').count() +
        PedidoAtt.query.filter_by(estado='EN PROCESO').count() +
        PedidoEmbossadora.query.filter_by(estado='EN PROCESO').count() +
        PedidoSembradora.query.filter_by(estado='EN PROCESO').count()
    )
    
    # Urgentes (pedidos NO ASIGNADOS con fecha cercana)
    from datetime import date, timedelta
    fecha_urgente = date.today() + timedelta(days=3)
    
    urgentes_count = (
        PedidoTolva.query.filter(
            PedidoTolva.estado == 'NO ASIGNADO',
            PedidoTolva.fecha_compromiso <= fecha_urgente
        ).count() +
        PedidoMixer.query.filter(
            PedidoMixer.estado == 'NO ASIGNADO',
            PedidoMixer.fecha_compromiso <= fecha_urgente
        ).count() +
        PedidoAtt.query.filter(
            PedidoAtt.estado == 'NO ASIGNADO',
            PedidoAtt.fecha_compromiso <= fecha_urgente
        ).count() +
        PedidoEmbossadora.query.filter(
            PedidoEmbossadora.estado == 'NO ASIGNADO',
            PedidoEmbossadora.fecha_compromiso <= fecha_urgente
        ).count() +
        PedidoSembradora.query.filter(
            PedidoSembradora.estado == 'NO ASIGNADO',
            PedidoSembradora.fecha_compromiso <= fecha_urgente
        ).count()
    )
    
    # Pedidos pendientes - combinar todas las tablas (usar PENDIENTE)
    print("DEBUG: PCP - Buscando pedidos PENDIENTES")
    
    pedidos_pendientes_tolva = PedidoTolva.query.filter_by(estado='PENDIENTE').order_by(
        PedidoTolva.fecha_compromiso.asc()
    ).all()
    
    pedidos_pendientes_mixer = PedidoMixer.query.filter_by(estado='PENDIENTE').order_by(
        PedidoMixer.fecha_compromiso.asc()
    ).all()
    
    pedidos_pendientes_att = PedidoAtt.query.filter_by(estado='PENDIENTE').order_by(
        PedidoAtt.fecha_compromiso.asc()
    ).all()
    
    pedidos_pendientes_embolsadora = PedidoEmbossadora.query.filter_by(estado='PENDIENTE').order_by(
        PedidoEmbossadora.fecha_compromiso.asc()
    ).all()
    
    pedidos_pendientes_sembradora = PedidoSembradora.query.filter_by(estado='PENDIENTE').order_by(
        PedidoSembradora.fecha_compromiso.asc()
    ).all()
    
    # Solicitudes de Ventas (nuevas pestañas)
    solicitudes_modificacion_tolva = PedidoTolva.query.filter_by(estado='CAMBIO_SOLICITADO').order_by(
        PedidoTolva.fecha_compromiso.asc()
    ).all()
    
    solicitudes_modificacion_mixer = PedidoMixer.query.filter_by(estado='CAMBIO_SOLICITADO').order_by(
        PedidoMixer.fecha_compromiso.asc()
    ).all()
    
    solicitudes_modificacion_att = PedidoAtt.query.filter_by(estado='CAMBIO_SOLICITADO').order_by(
        PedidoAtt.fecha_compromiso.asc()
    ).all()
    
    solicitudes_eliminacion_tolva = PedidoTolva.query.filter_by(estado='ELIMINACION_SOLICITADA').order_by(
        PedidoTolva.fecha_compromiso.asc()
    ).all()
    
    solicitudes_eliminacion_mixer = PedidoMixer.query.filter_by(estado='ELIMINACION_SOLICITADA').order_by(
        PedidoMixer.fecha_compromiso.asc()
    ).all()
    
    solicitudes_eliminacion_att = PedidoAtt.query.filter_by(estado='ELIMINACION_SOLICITADA').order_by(
        PedidoAtt.fecha_compromiso.asc()
    ).all()
    
    print(f"DEBUG: PCP - Pedidos PENDIENTE encontrados:")
    print(f"  - TOLVA: {len(pedidos_pendientes_tolva)}")
    print(f"  - MIXER: {len(pedidos_pendientes_mixer)}")
    print(f"  - ATT: {len(pedidos_pendientes_att)}")
    print(f"  - EMBOSSADORA: {len(pedidos_pendientes_embolsadora)}")
    print(f"  - SEMBRADORA: {len(pedidos_pendientes_sembradora)}")
    
    # Mostrar detalles de los pedidos pendientes
    all_pendientes = pedidos_pendientes_tolva + pedidos_pendientes_mixer + pedidos_pendientes_att + pedidos_pendientes_embolsadora + pedidos_pendientes_sembradora
    print(f"DEBUG: PCP - Total pedidos PENDIENTE: {len(all_pendientes)}")
    for i, p in enumerate(all_pendientes):
        print(f"  [{i}] ID:{p.id}, Pedido:{getattr(p, 'pedido', 'N/A')}, Cliente:{getattr(p, 'cliente', 'N/A')}, Estado:{getattr(p, 'estado', 'N/A')}")
    
    # Combinar y ordenar todos los pedidos pendientes
    pedidos_pendientes = (pedidos_pendientes_tolva + pedidos_pendientes_mixer + 
                          pedidos_pendientes_att + pedidos_pendientes_embolsadora + 
                          pedidos_pendientes_sembradora)
    pedidos_pendientes.sort(key=lambda x: x.fecha_compromiso)
    
    # Chasis disponibles por implemento
    chasis_por_implemento = {}
    
    # Para TOLVA - Mostrar chasis con cliente = 'STOCK' o sin cliente (en producción)
    chasis_tolva_disponibles = []
    for chasis in chasis_tolva:
        # Mostrar si: (cliente es STOCK OR cliente está vacío/nulo) AND no está ocupado
        cliente_valido = (chasis.cliente == 'STOCK' or 
                         not chasis.cliente or 
                         chasis.cliente.strip() == '')
        
        if cliente_valido:
            # Agregar información adicional del plan de producción
            chasis_info = {
                'id': chasis.id,
                'nro_chasis': chasis.nro_chasis,
                'modelo': chasis.modelo,
                'cliente': chasis.cliente or '',
                'lanzamiento': chasis.lanzamiento,
                'tubo': chasis.tubo,
                'encamisado': chasis.encamisado,
                'tipo_tubo': chasis.tipo_tubo,
                'tamano_cubierta': chasis.tamano_cubierta,
                'marca_cubiertas': chasis.marca_cubiertas,
                'color': chasis.color,
                'balanza': chasis.balanza,
                'observaciones': chasis.observaciones,
                # Información del plan de producción
                'puesto_conjunto': None,
                'fecha_playon': None,
                'sector': None,
                'fecha_despacho': None
            }
            
            # Obtener información del plan de producción si existe
            if chasis.plan:
                chasis_info.update({
                    'puesto_conjunto': chasis.plan.puesto_conjunto,
                    'fecha_playon': chasis.plan.fecha_playon,
                    'sector': chasis.plan.sector,
                    'fecha_despacho': chasis.plan.fecha_despacho
                })
            
            chasis_tolva_disponibles.append(chasis_info)
    
    # Ordenar por número de chasis de menor a mayor
    chasis_tolva_disponibles.sort(key=lambda x: int(x['nro_chasis']) if x['nro_chasis'].isdigit() else 0)
    
    if chasis_tolva_disponibles:
        chasis_por_implemento['TOLVA'] = chasis_tolva_disponibles
    
    # Asignaciones recientes - combinar de todas las tablas
    # Para PedidoTolva, usamos chasis_id como criterio de asignación (no tiene fecha_asignacion_chasis)
    asignaciones_recientes_tolva = PedidoTolva.query.filter(
        PedidoTolva.chasis_id.isnot(None)
    ).order_by(PedidoTolva.id.desc()).limit(10).all()
    
    asignaciones_recientes_mixer = PedidoMixer.query.filter(
        PedidoMixer.fecha_asignacion_chasis.isnot(None)
    ).order_by(PedidoMixer.fecha_asignacion_chasis.desc()).limit(5).all()
    
    asignaciones_recientes_att = PedidoAtt.query.filter(
        PedidoAtt.fecha_asignacion_chasis.isnot(None)
    ).order_by(PedidoAtt.fecha_asignacion_chasis.desc()).limit(5).all()
    
    asignaciones_recientes_embolsadora = PedidoEmbossadora.query.filter(
        PedidoEmbossadora.fecha_asignacion_chasis.isnot(None)
    ).order_by(PedidoEmbossadora.fecha_asignacion_chasis.desc()).limit(5).all()
    
    asignaciones_recientes_sembradora = PedidoSembradora.query.filter(
        PedidoSembradora.fecha_asignacion_chasis.isnot(None)
    ).order_by(PedidoSembradora.fecha_asignacion_chasis.desc()).limit(5).all()
    
    # Combinar asignaciones recientes
    asignaciones_recientes = (asignaciones_recientes_tolva + asignaciones_recientes_mixer +
                           asignaciones_recientes_att + asignaciones_recientes_embolsadora +
                           asignaciones_recientes_sembradora)
    
    # Para PedidoTolva, obtener información de chasis asignados y datos de asignación
    chasis_asignados_info = {}
    for asignacion in asignaciones_recientes_tolva:
        if asignacion.chasis_id:
            chasis = ChasisAsignadoTolva.query.get(asignacion.chasis_id)
            if chasis:
                # Guardar como diccionario simple para el template
                chasis_asignados_info[asignacion.id] = {
                    'id': chasis.id,
                    'nro_chasis': chasis.nro_chasis,
                    'cliente': chasis.cliente,
                    'modelo': chasis.modelo
                }
                
                # Buscar la fecha y usuario de asignación en el historial
                historial_asignacion = HistorialEstadoPedido.query.filter_by(
                    pedido_id=asignacion.id,
                    estado_nuevo='ASIGNADO'
                ).order_by(HistorialEstadoPedido.fecha_cambio.desc()).first()
                
                if historial_asignacion:
                    asignacion.fecha_asignacion_real = historial_asignacion.fecha_cambio
                    asignacion.usuario_asignacion = historial_asignacion.usuario
                else:
                    # Si no hay historial, usar fecha_emision y creado_por
                    asignacion.fecha_asignacion_real = asignacion.fecha_emision
                    asignacion.usuario_asignacion = asignacion.creado_por
    
    # Ordenar por diferentes criterios según el tipo
    def get_fecha_orden(asignacion):
        if hasattr(asignacion, 'fecha_asignacion_chasis') and asignacion.fecha_asignacion_chasis:
            return asignacion.fecha_asignacion_chasis
        else:
            # Para PedidoTolva, usar el ID como referencia (más recientes primero)
            return datetime.max - timedelta(days=asignacion.id)
    
    asignaciones_recientes.sort(key=get_fecha_orden, reverse=True)
    
    return render_template('pcp.html',
                         pedidos_pendientes_count=pedidos_pendientes_count,
                         modificacion_solicitada_count=modificacion_solicitada_count,
                         eliminacion_solicitada_count=eliminacion_solicitada_count,
                         chasis_disponibles_count=chasis_disponibles_count,
                         en_produccion_count=en_produccion_count,
                         urgentes_count=urgentes_count,
                         pedidos_pendientes=pedidos_pendientes,
                         solicitudes_modificacion=(solicitudes_modificacion_tolva + solicitudes_modificacion_mixer + solicitudes_modificacion_att),
                         solicitudes_eliminacion=(solicitudes_eliminacion_tolva + solicitudes_eliminacion_mixer + solicitudes_eliminacion_att),
                         chasis_por_implemento=chasis_por_implemento,
                         asignaciones_recientes=asignaciones_recientes,
                         chasis_asignados_info=chasis_asignados_info,
                         now=datetime.now)  # Agregar now al contexto

@app.route('/admin/pcp/aprobar_eliminacion/<int:pedido_id>', methods=['POST'])
@login_required
def admin_pcp_aprobar_eliminacion(pedido_id):
    """Aprobar solicitud de eliminación de pedido"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        # Buscar el pedido en todas las tablas
        pedido = None
        pedido = PedidoTolva.query.get(pedido_id)
        if not pedido:
            pedido = PedidoMixer.query.get(pedido_id)
        if not pedido:
            pedido = PedidoAtt.query.get(pedido_id)
        if not pedido:
            pedido = PedidoEmbossadora.query.get(pedido_id)
        if not pedido:
            pedido = PedidoSembradora.query.get(pedido_id)
        
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        
        # Verificar que el pedido esté en estado ELIMINACION_SOLICITADA
        if pedido.estado != 'ELIMINACION_SOLICITADA':
            return jsonify({'success': False, 'message': 'El pedido no tiene una solicitud de eliminación pendiente'}), 400
        
        # Desasignar el chasis si tiene uno asignado
        chasis_id_anterior = pedido.chasis_id
        if chasis_id_anterior:
            pedido.chasis_id = None
        
        # Cambiar estado a DISPONIBLE_PARA_ELIMINAR
        pedido.estado = 'DISPONIBLE_PARA_ELIMINAR'
        
        # Crear registro en historial
        historial = HistorialEstadoPedido(
            pedido_id=pedido.id,
            estado_anterior='ELIMINACION_SOLICITADA',
            estado_nuevo='DISPONIBLE_PARA_ELIMINAR',
            fecha_cambio=datetime.now(),
            usuario=current_user.legajo if hasattr(current_user, 'legajo') else current_user.nombre
        )
        db.session.add(historial)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Solicitud de eliminación aprobada para el pedido {pedido.pedido}. El chasis ha sido desasignado y el pedido está disponible para eliminación definitiva.'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al aprobar eliminación: {e}")
        return jsonify({'success': False, 'message': f'Error al aprobar la solicitud: {str(e)}'}), 500

@app.route('/admin/pcp/ver_pedido/<int:pedido_id>')
@login_required
def admin_pcp_ver_pedido(pedido_id):
    """PCP: Ver detalles de un pedido"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    # Buscar el pedido en todas las tablas específicas
    pedido = None
    pedido = PedidoTolva.query.get(pedido_id)
    if not pedido:
        pedido = PedidoMixer.query.get(pedido_id)
    if not pedido:
        pedido = PedidoAtt.query.get(pedido_id)
    if not pedido:
        pedido = PedidoEmbossadora.query.get(pedido_id)
    if not pedido:
        pedido = PedidoSembradora.query.get(pedido_id)
    
    if not pedido:
        return jsonify({'error': 'Pedido no encontrado'}), 404
    
    # Construir respuesta de forma segura según el tipo de pedido
    response_data = {
        'id': pedido.id,
        'codigo_pedido': pedido.pedido,
        'cliente': pedido.cliente,
        'modelo': pedido.modelo,
        'implemento': pedido.implemento,
        'fecha_compromiso': pedido.fecha_compromiso.isoformat() if pedido.fecha_compromiso else None,
        'estado': pedido.estado
    }
    
    # Agregar campos opcionales que no existen en todos los modelos
    if hasattr(pedido, 'observaciones'):
        response_data['observaciones'] = pedido.observaciones
    if hasattr(pedido, 'cantidad'):
        response_data['cantidad'] = pedido.cantidad
    if hasattr(pedido, 'prioridad'):
        response_data['prioridad'] = pedido.prioridad
    if hasattr(pedido, 'fecha_ingreso'):
        response_data['fecha_ingreso'] = pedido.fecha_ingreso.isoformat() if pedido.fecha_ingreso else None
    if hasattr(pedido, 'fecha_emision') and pedido.fecha_emision:
        response_data['fecha_emision'] = pedido.fecha_emision.isoformat()
    
    # Agregar información de chasis específica según el tipo
    if isinstance(pedido, PedidoTolva):
        # Para TOLVA, usar la relación chasis_asignado
        if hasattr(pedido, 'chasis_asignado') and pedido.chasis_asignado:
            response_data['chasis_asignado'] = pedido.chasis_asignado.nro_chasis
        else:
            response_data['chasis_asignado'] = None
        
        # Campos específicos de TOLVA
        response_data['concesionario'] = getattr(pedido, 'concesionario', None)
        response_data['localidad'] = getattr(pedido, 'localidad', None)
        response_data['llantas'] = getattr(pedido, 'llantas', None)
        response_data['cubiertas'] = getattr(pedido, 'cubiertas', None)
        response_data['color'] = getattr(pedido, 'color', None)
        response_data['balanza'] = getattr(pedido, 'balanza', None)
    else:
        # Para otros tipos, chasis_asignado es un campo string
        response_data['chasis_asignado'] = getattr(pedido, 'chasis_asignado', None)
    
    # Campos opcionales que pueden existir en algunos modelos
    for campo in ['vendedor', 'forma_pago', 'precio_unitario', 'precio_total']:
        if hasattr(pedido, campo):
            response_data[campo] = getattr(pedido, campo)
    
    return jsonify(response_data)

@app.route('/admin/pcp/ver_chasis/<string:nro_chasis>')
@login_required
def admin_pcp_ver_chasis(nro_chasis):
    """PCP: Ver detalles de un chasis"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    implemento = request.args.get('implemento', 'TOLVA')
    
    if implemento == 'TOLVA':
        chasis = ChasisAsignadoTolva.query.filter_by(nro_chasis=nro_chasis).first()
        
        if chasis:
            return jsonify({
                'nro_chasis': chasis.nro_chasis,
                'modelo': chasis.modelo,
                'cliente': chasis.cliente,
                'fecha_asignacion': chasis.fecha_asignacion.isoformat() if chasis.fecha_asignacion else None,
                'lanzamiento': chasis.lanzamiento,
                'observaciones': chasis.observaciones
            })
    
    return jsonify({'error': 'Chasis no encontrado'}), 404

@app.route('/admin/pcp/obtener_chasis_disponibles/<string:implemento>')
@login_required
def admin_pcp_obtener_chasis_disponibles(implemento):
    """PCP: Obtener chasis disponibles por implemento"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    # Obtener el modelo y color del parámetro query
    modelo_solicitado = request.args.get('modelo', '')
    color_solicitado = request.args.get('color', '')
    
    chasis_disponibles = []
    
    if implemento == 'TOLVA':
        # Para TOLVA, incluir chasis con cliente = 'STOCK', modelo y color solicitados
        query = ChasisAsignadoTolva.query.filter(
            ChasisAsignadoTolva.nro_chasis.isnot(None),
            ChasisAsignadoTolva.cliente == 'STOCK'
        )
        
        # Filtrar por modelo si se especificó
        if modelo_solicitado:
            query = query.filter(ChasisAsignadoTolva.modelo == modelo_solicitado)
        
        # Filtrar por color si se especificó
        if color_solicitado:
            query = query.filter(ChasisAsignadoTolva.color == color_solicitado)
        
        # Ordenar por número de chasis de menor a mayor
        chasis_disponibles_query = query.order_by(ChasisAsignadoTolva.nro_chasis.asc())
        
        chasis_stock = chasis_disponibles_query.all()
        chasis_disponibles_set = {c.nro_chasis for c in chasis_stock}
        
        # Obtener chasis ocupados de otros modelos (MIXER, ATT, etc.) que podrían usar chasis de TOLVA
        chasis_ocupados_mixer = db.session.query(PedidoMixer.chasis_asignado).filter(
            PedidoMixer.chasis_asignado.isnot(None),
            PedidoMixer.estado.in_(['ASIGNADO', 'EN_PRODUCCION'])
        ).all()
        
        chasis_ocupados_att = db.session.query(PedidoAtt.chasis_asignado).filter(
            PedidoAtt.chasis_asignado.isnot(None),
            PedidoAtt.estado.in_(['ASIGNADO', 'EN_PRODUCCION'])
        ).all()
        
        chasis_ocupados_embolsadora = db.session.query(PedidoEmbossadora.chasis_asignado).filter(
            PedidoEmbossadora.chasis_asignado.isnot(None),
            PedidoEmbossadora.estado.in_(['ASIGNADO', 'EN_PRODUCCION'])
        ).all()
        
        chasis_ocupados_sembradora = db.session.query(PedidoSembradora.chasis_asignado).filter(
            PedidoSembradora.chasis_asignado.isnot(None),
            PedidoSembradora.estado.in_(['ASIGNADO', 'EN_PRODUCCION'])
        ).all()
        
        chasis_ocupados_set = set()
        chasis_ocupados_set.update([c[0] for c in chasis_ocupados_mixer if c[0]])
        chasis_ocupados_set.update([c[0] for c in chasis_ocupados_att if c[0]])
        chasis_ocupados_set.update([c[0] for c in chasis_ocupados_embolsadora if c[0]])
        chasis_ocupados_set.update([c[0] for c in chasis_ocupados_sembradora if c[0]])
        
        chasis_libres = chasis_disponibles_set - chasis_ocupados_set
        
        for chasis_num in chasis_libres:
            chasis_info = ChasisAsignadoTolva.query.filter_by(nro_chasis=chasis_num).first()
            if chasis_info:
                chasis_disponibles.append({
                    'nro_chasis': chasis_info.nro_chasis,
                    'modelo': chasis_info.modelo,
                    'cliente': chasis_info.cliente
                })
    
    return jsonify({'chasis_disponibles': chasis_disponibles})

@app.route('/admin/pcp/asignar_chasis', methods=['POST'])
@login_required
def admin_pcp_asignar_chasis():
    """PCP: Asignar un chasis a un pedido"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json()
    pedido_id = data['pedido_id']
    chasis_asignado = data['chasis_asignado']
    
    try:
        # Buscar el pedido en todas las tablas específicas
        pedido = (PedidoTolva.query.get(pedido_id) or 
                 PedidoMixer.query.get(pedido_id) or 
                 PedidoAtt.query.get(pedido_id) or 
                 PedidoEmbossadora.query.get(pedido_id) or 
                 PedidoSembradora.query.get(pedido_id))
        
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'})
        
        # Actualizar pedido según el tipo
        if isinstance(pedido, PedidoTolva):
            # PedidoTolva necesita chasis_id (ForeignKey), no chasis_asignado (string)
            # Buscar el ID del chasis por el número recibido
            chasis = ChasisAsignadoTolva.query.filter_by(nro_chasis=chasis_asignado).first()
            if chasis:
                pedido.chasis_id = chasis.id
                pedido.estado = 'ASIGNADO'
            else:
                return jsonify({'success': False, 'message': f'Chasis {chasis_asignado} no encontrado'})
        else:
            # Para otros modelos que sí tienen estos campos
            pedido.chasis_asignado = chasis_asignado
            pedido.estado = 'ASIGNADO'
            pedido.fecha_asignacion_chasis = datetime.now()
            pedido.modificado_por = current_user.nombre
            pedido.fecha_modificacion = datetime.now()
        
        db.session.commit()
        
        # TODO: Registrar historial - necesitamos manejar múltiples tablas de pedidos
        # Por ahora, comentamos para evitar errores de foreign key
        # historial = HistorialEstadoPedido(
        #     pedido_id=pedido.id,
        #     estado_anterior='PENDIENTE',
        #     estado_nuevo='ASIGNADO',
        #     usuario=current_user.nombre,
        #     motivo=f'Asignación PCP del chasis {chasis_asignado}'
        # )
        # db.session.add(historial)
        # db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/pcp/obtener_modelos_disponibles')
@login_required
def admin_pcp_obtener_modelos_disponibles():
    """PCP: Obtener modelos de chasis disponibles para filtrar"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        # Obtener modelos únicos de ChasisAsignadoTolva con cliente = 'STOCK' o sin cliente
        modelos = db.session.query(ChasisAsignadoTolva.modelo).filter(
            db.or_(
                ChasisAsignadoTolva.cliente == 'STOCK',
                ChasisAsignadoTolva.cliente.is_(None),
                ChasisAsignadoTolva.cliente == '',
                db.func.trim(ChasisAsignadoTolva.cliente) == ''
            ),
            ChasisAsignadoTolva.modelo.isnot(None)
        ).distinct().all()
        
        modelos_lista = [m[0] for m in modelos if m[0]]
        modelos_lista.sort()  # Ordenar alfabéticamente
        
        return jsonify({'modelos': modelos_lista})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/pcp/obtener_puestos_disponibles')
@login_required
def admin_pcp_obtener_puestos_disponibles():
    """PCP: Obtener puestos de trabajo disponibles para filtrar"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        # Obtener puestos únicos de PlanProducción relacionados con chasis STOCK o sin cliente
        puestos_query = db.session.query(PlanProduccion.puesto_conjunto).join(
            ChasisAsignadoTolva, PlanProduccion.id == ChasisAsignadoTolva.plan_id
        ).filter(
            db.or_(
                ChasisAsignadoTolva.cliente == 'STOCK',
                ChasisAsignadoTolva.cliente.is_(None),
                ChasisAsignadoTolva.cliente == '',
                db.func.trim(ChasisAsignadoTolva.cliente) == ''
            ),
            PlanProduccion.puesto_conjunto.isnot(None)
        ).distinct().all()
        
        puestos_lista = [p[0] for p in puestos_query if p[0]]
        puestos_lista.sort()  # Ordenar alfabéticamente
        
        # Filtrar solo los que contienen "M5" si existen
        puestos_m5 = [p for p in puestos_lista if 'M5' in p.upper()]
        otros_puestos = [p for p in puestos_lista if 'M5' not in p.upper()]
        
        # Priorizar puestos M5
        puestos_ordenados = puestos_m5 + otros_puestos
        
        return jsonify({'puestos': puestos_ordenados})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/pcp/actualizar_cliente_chasis', methods=['POST'])
@login_required
def admin_pcp_actualizar_cliente_chasis():
    """PCP: Actualizar el cliente de un chasis (solo si es STOCK)"""
    if current_user.rol not in ['ADMIN', 'PCP']:
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json()
    nro_chasis = data['nro_chasis']
    nuevo_cliente = data['cliente']
    
    try:
        # Buscar el chasis en ChasisAsignadoTolva
        chasis = ChasisAsignadoTolva.query.filter_by(nro_chasis=nro_chasis).first()
        
        if not chasis:
            return jsonify({'success': False, 'message': 'Chasis no encontrado'}), 404
        
        # Verificar que el cliente actual sea STOCK
        if chasis.cliente != 'STOCK':
            return jsonify({'success': False, 'message': 'Solo se pueden modificar chasis con cliente STOCK'}), 400
        
        # Actualizar el cliente
        chasis.cliente = nuevo_cliente
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Cliente actualizado exitosamente'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# --- Sección 9: Inicialización de Base de Datos --------------------------------------------

with app.app_context():
    inicializar_base_datos()

if __name__ == '__main__':
    # Para desarrollo local - siempre en DEBUG si no estamos en Render
    port = int(os.environ.get("PORT", 5000))
    # En desarrollo local: debug=True. En Render (/var/data existe): debug=False
    debug_mode = not os.path.exists('/var/data')
    print(f" Iniciando servidor en puerto {port} | DEBUG: {debug_mode}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
