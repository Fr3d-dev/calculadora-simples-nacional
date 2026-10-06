"""
Ponto de entrada WSGI para publicação (PythonAnywhere e similares).

O PythonAnywhere (e servidores WSGI em geral) importam a variável `application`
deste arquivo para servir o app.

No painel do PythonAnywhere, no arquivo WSGI gerado automaticamente, troque o
conteúdo por algo como:

    import sys
    path = "/home/SEU_USUARIO/simples_app"
    if path not in sys.path:
        sys.path.insert(0, path)

    import os
    os.environ["SN_PRODUCAO"] = "1"
    os.environ["SIMPLES_SECRET"] = "cole-aqui-a-chave-gerada"
    # opcional: definir a senha inicial do admin
    # os.environ["SIMPLES_ADMIN_SENHA"] = "uma-senha-forte"

    from app import app as application
    application = application

Variáveis de ambiente importantes em produção:
    SN_PRODUCAO     -> "1" (ativa cookies seguros, ProxyFix e exige SECRET)
    SIMPLES_SECRET  -> chave secreta (use: python -c "import secrets;print(secrets.token_urlsafe(48))")
"""

from app import app as application

__all__ = ["application"]
