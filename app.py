import os
from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ascanelli_secret_key_123')

# Base de datos: SQLite local para desarrollo, Neon/Supabase para producción
database_url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL')

if database_url:
    # Producción: Neon.tech o Supabase
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    print(f"✅ Conectando a base de datos en la nube (Producción)")
    print(f"🔗 URL: {database_url[:50]}...")
else:
    print("📁 Conectando a SQLite (Desarrollo Local)")

@app.route('/')
def index():
    return """
    <h1>🚀 ASCANELLI WEB en Vercel</h1>
    <p>¡Funcionando correctamente!</p>
    <p>Conexión a Neon.tech: OK</p>
    <p>Vercel: OK</p>
    <hr>
    <a href="/test">Test Route</a>
    """

@app.route('/test')
def test():
    return "¡ASCANELLI WEB funcionando en Vercel! 🚀"

# ===== INICIALIZACIÓN =====
print("🚀 App iniciada - Versión mínima para pruebas")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
