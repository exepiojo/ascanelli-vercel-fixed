# Archivo para Vercel Serverless Functions
from app import app

# Handler para Vercel
def handler(request):
    return app(request.environ, request.start_response)

# Exportar para Vercel
app.handler = handler
