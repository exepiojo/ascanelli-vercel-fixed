# Vercel Serverless Function Handler
from app import app

# Exportar la app Flask para Vercel
handler = app

# Para Vercel
app.wsgi_app = app
