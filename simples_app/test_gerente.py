"""Testes do perfil gerente (acesso desenvolvedor).

Regras que estes testes travam:
  * gerente vê todas as funções, inclusive a Carteira de clientes;
  * gerente enxerga todos os escritórios;
  * gerente NÃO cria/edita/exclui outro gerente nem o master;
  * só o master concede o perfil gerente pelo formulário de usuários.
"""
import os
import sys
import tempfile
import importlib
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class GerenteTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="simples_ger_")
        self.db_path = os.path.join(self.tmpdir, "t.db")
        os.environ["SIMPLES_DB"] = self.db_path

        import app as app_module
        importlib.reload(app_module)
        self.app = app_module.app
        self.app.config.update(TESTING=True, DATABASE=self.db_path)

        import database as db
        self.db = db
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.init_db()

        self.master_id = db.criar_usuario("Master", "m@t.com", "123456", is_admin=True)
        db.definir_master(self.master_id, True)

        # Dois escritórios distintos, para provar que o gerente vê os dois.
        dono_a = db.criar_usuario("Dono A", "da@t.com", "123456")
        dono_b = db.criar_usuario("Dono B", "db@t.com", "123456")
        self.esc_a = db.criar_escritorio(dono_a, "Escritorio A")
        self.esc_b = db.criar_escritorio(dono_b, "Escritorio B")
        db.definir_escritorio_usuario(dono_a, self.esc_a)
        db.definir_escritorio_usuario(dono_b, self.esc_b)

        self.admin_a = db.criar_usuario(
            "Admin A", "a@t.com", "123456", is_admin=True, escritorio_id=self.esc_a,
        )
        self.admin_b = db.criar_usuario(
            "Admin B", "b@t.com", "123456", is_admin=True, escritorio_id=self.esc_b,
        )

        self.gerente_id = db.criar_usuario(
            "Gerente", "g@t.com", "123456", is_admin=True,
            escritorio_id=self.esc_a, is_gerente=True,
        )

    def tearDown(self):
        self.ctx.pop()
        os.environ.pop("SIMPLES_DB", None)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def client(self, uid):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["usuario_id"] = uid
        return c

    # ------------------------- permissões / telas -------------------------

    def test_gerente_tem_todas_as_permissoes(self):
        g = self.db.buscar_usuario_por_id(self.gerente_id)
        perms = self.db.get_permissoes(g)
        self.assertIn("editar_tabelas", perms)
        self.assertIn("gerenciar_usuarios", perms)

    def test_gerente_acessa_carteira(self):
        r = self.client(self.gerente_id).get("/carteira")
        self.assertEqual(r.status_code, 200)

    def test_admin_sem_perfil_gerente_nao_acessa_carteira(self):
        r = self.client(self.admin_a).get("/carteira", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    # ------------------------- escopo de escritórios ----------------------

    def test_gerente_enxerga_usuarios_de_todos_os_escritorios(self):
        r = self.client(self.gerente_id).get("/admin")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("a@t.com", html)
        self.assertIn("b@t.com", html)

    def test_admin_comum_nao_enxerga_outro_escritorio(self):
        html = self.client(self.admin_a).get("/admin").data.decode("utf-8")
        self.assertNotIn("b@t.com", html)

    # ------------------------- escalada de privilégio ---------------------

    def test_gerente_nao_pode_criar_outro_gerente(self):
        c = self.client(self.gerente_id)
        c.post("/admin/usuario/novo", data={
            "nome": "Novo", "email": "n@t.com", "senha": "123456",
            "ativo": "on", "is_admin": "on", "is_gerente": "on",
        }, follow_redirects=True)
        novo = self.db.buscar_usuario_por_email("n@t.com")
        self.assertIsNotNone(novo, "o usuário comum deve ser criado")
        self.assertFalse(self.db.eh_gerente(novo), "não pode nascer como gerente")

    def test_gerente_nao_pode_promover_outro_usuario(self):
        c = self.client(self.gerente_id)
        c.post(f"/admin/usuario/{self.admin_b}/editar", data={
            "nome": "Admin B", "email": "b@t.com", "ativo": "on",
            "is_admin": "on", "is_gerente": "on",
        }, follow_redirects=True)
        alvo = self.db.buscar_usuario_por_id(self.admin_b)
        self.assertFalse(self.db.eh_gerente(alvo))

    def test_gerente_nao_pode_despromover_a_si_mesmo_nem_alterar_perfil(self):
        c = self.client(self.gerente_id)
        c.post(f"/admin/usuario/{self.gerente_id}/editar", data={
            "nome": "Gerente", "email": "g@t.com", "ativo": "on",
            "is_admin": "on",  # sem is_gerente no form
        }, follow_redirects=True)
        g = self.db.buscar_usuario_por_id(self.gerente_id)
        self.assertTrue(self.db.eh_gerente(g), "perfil preservado")

    def test_gerente_nao_exclui_master(self):
        c = self.client(self.gerente_id)
        c.post(f"/admin/usuario/{self.master_id}/excluir", follow_redirects=True)
        self.assertIsNotNone(self.db.buscar_usuario_por_id(self.master_id))

    # ------------------------- master concede o perfil ---------------------

    def test_master_promove_usuario_a_gerente(self):
        c = self.client(self.master_id)
        c.post(f"/admin/usuario/{self.admin_a}/editar", data={
            "nome": "Admin A", "email": "a@t.com", "ativo": "on",
            "is_admin": "on", "is_gerente": "on",
        }, follow_redirects=True)
        alvo = self.db.buscar_usuario_por_id(self.admin_a)
        self.assertTrue(self.db.eh_gerente(alvo))

        # Passa a acessar a Carteira.
        self.assertEqual(self.client(self.admin_a).get("/carteira").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
