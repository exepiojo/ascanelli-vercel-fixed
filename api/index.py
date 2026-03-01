# Vercel Serverless Function Handler
import sys
import os

# Agregar el directorio actual al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importar la app Flask
from app import app

# Handler para Vercel
def handler(request):
    return app

# Para Vercel
app.wsgi_app = app
