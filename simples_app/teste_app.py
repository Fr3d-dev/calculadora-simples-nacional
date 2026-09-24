"""Teste de integração: login, gravação de faturamentos, persistência e cálculo."""

import app as appmod

appmod.bootstrap()
client = appmod.app.test_client()

# Login
r = client.post("/login", data={"email": "admin@admin.com", "senha": "admin123"},
                follow_redirects=True)
assert r.status_code == 200, r.status_code
print("[ok] login")

# Grava 12 meses + faturamento do mês no Anexo I
dados = {f"mes_{i}": "10000" for i in range(1, 13)}
dados["faturamento_mes"] = "20000"
r = client.post("/anexo/I", data=dados, follow_redirects=True)
assert r.status_code == 200
assert "Dados salvos com sucesso".encode() in r.data
print("[ok] gravacao dos 12 meses + faturamento do mes")

# Recarrega e confere persistência
r = client.get("/anexo/I")
html = r.data.decode("utf-8")
assert 'value="10000"' in html, "meses nao persistiram"
assert "R$ 120.000,00" in html, "RBT12 incorreto na tela"
assert "R$ 800,00" in html, "DAS incorreto na tela"
print("[ok] persistencia e recalculo (RBT12 R$ 120.000,00 / DAS R$ 800,00)")

# Dashboard reflete os dados
r = client.get("/dashboard")
html = r.data.decode("utf-8")
assert "R$ 800,00" in html
print("[ok] dashboard reflete os dados")

# Cadastro de usuário comum
r = client.post("/admin/usuario/novo", data={
    "nome": "Maria Teste", "email": "maria@teste.com", "senha": "senha123", "ativo": "on"
}, follow_redirects=True)
assert r.status_code == 200
print("[ok] cadastro de usuario")

# Login com o novo usuário e acesso restrito
c2 = appmod.app.test_client()
r = c2.post("/login", data={"email": "maria@teste.com", "senha": "senha123"},
            follow_redirects=True)
assert r.status_code == 200
r = c2.get("/admin", follow_redirects=True)
assert "Acesso restrito".encode() in r.data, "usuario comum acessou admin!"
print("[ok] usuario comum bloqueado do admin")

# Usuário inativo não loga
admin = appmod.app.test_client()
admin.post("/login", data={"email": "admin@admin.com", "senha": "admin123"})
with appmod.app.app_context():
    usuarios = appmod.db.listar_usuarios()
    maria = next(u for u in usuarios if u["email"] == "maria@teste.com")
admin.post(f"/admin/usuario/{maria['id']}/editar", data={
    "nome": "Maria Teste", "email": "maria@teste.com", "ativo": ""
}, follow_redirects=True)

c3 = appmod.app.test_client()
r = c3.post("/login", data={"email": "maria@teste.com", "senha": "senha123"},
            follow_redirects=True)
assert "inativos".encode() in r.data or "inválidos".encode() in r.data
print("[ok] usuario inativo bloqueado no login")

print("\n[SUCESSO] Todos os testes de integracao passaram.")
