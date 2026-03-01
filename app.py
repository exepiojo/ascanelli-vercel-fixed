import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, text
from datetime import datetime, timedelta

app = Flask(__name__)
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

# ===== MODELO USUARIO =====
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    
    id = db.Column(db.Integer, primary_key=True)
    legajo = db.Column(db.String(20), unique=True, nullable=False)
    pin_secreto = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    rol = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<Usuario {self.nombre}>'

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ===== RUTAS PRINCIPALES =====
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login_post():
    if request.method == 'POST':
        legajo = request.form.get('legajo')
        pin_secreto = request.form.get('pin_secreto')
        
        if not legajo or not pin_secreto:
            flash('Por favor completa todos los campos', 'error')
            return redirect(url_for('login'))
        
        usuario = Usuario.query.filter_by(legajo=legajo, pin_secreto=pin_secreto).first()
        
        if usuario:
            login_user(usuario)
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', usuario_actual=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# ===== RUTA DE PRUEBA =====
@app.route('/test')
def test():
    return "¡ASCANELLI WEB funcionando en Vercel! 🚀"

# ===== INICIALIZACIÓN =====
# NUNCA inicializar base de datos en producción
print("🚀 App iniciada - Sin inicialización automática en producción")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.path.exists('/var/data')
    print(f" Iniciando servidor en puerto {port} | DEBUG: {debug_mode}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
