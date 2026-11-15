"""Testes das rotas de escrita da Carteira e do modo suporte."""
import os
import sys
import tempfile
import importlib
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class CarteiraTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="simples_cart_")
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
        self.emp_master = db.criar_empresa(self.master_id, "EMPRESA MASTER")

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

    def test_criar_escritorio_gera_usuario_e_vinculo(self):
        c = self.client(self.master_id)
        r = c.post("/carteira/novo", data={
            "razao_social": "Contabilidade XPTO",
            "admin_email": "xpto@t.com",
            "admin_nome": "Fulano",
            "cnpj": "11.222.333/0001-44",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        esc = self.db.listar_escritorios()
        self.assertEqual(len(esc), 1)
        self.assertEqual(esc[0]["razao_social"], "Contabilidade XPTO")

        user = self.db.buscar_usuario_por_email("xpto@t.com")
        self.assertIsNotNone(user)
        # Cliente da carteira nunca é admin: entra só com as permissões
        # marcadas pelo master, e a senha só muda pela Carteira.
        self.assertEqual(user["is_admin"], 0)
        self.assertEqual(user["escritorio_id"], esc[0]["id"])

    def test_email_duplicado_nao_cria_escritorio(self):
        self.db.criar_usuario("Ja Existe", "dup@t.com", "123456", is_admin=True)
        c = self.client(self.master_id)
        c.post("/carteira/novo", data={
            "razao_social": "Outro",
            "admin_email": "dup@t.com",
        }, follow_redirects=True)
        self.assertEqual(len(self.db.listar_escritorios()), 0)

    def test_sem_razao_social_nao_cria(self):
        c = self.client(self.master_id)
        c.post("/carteira/novo", data={"razao_social": "  ", "admin_email": "a@t.com"},
               follow_redirects=True)
        self.assertEqual(len(self.db.listar_escritorios()), 0)

    def test_editar_escritorio(self):
        uid = self.db.criar_usuario("Adm", "adm@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid, "Antigo Nome")
        c = self.client(self.master_id)
        c.post("/carteira/{}/editar".format(eid), data={
            "razao_social": "Novo Nome", "ativo": "on",
        }, follow_redirects=True)
        self.assertEqual(self.db.buscar_escritorio_por_id(eid)["razao_social"], "Novo Nome")

    def test_excluir_escritorio_nao_apaga_usuario(self):
        uid = self.db.criar_usuario("Adm2", "adm2@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid, "Some")
        c = self.client(self.master_id)
        c.post("/carteira/{}/excluir".format(eid), follow_redirects=True)
        self.assertEqual(len(self.db.listar_escritorios()), 0)
        self.assertIsNotNone(self.db.buscar_usuario_por_id(uid))

    def test_suporte_abre_e_isola_no_escritorio(self):
        uid_a = self.db.criar_usuario("Adm A", "adma@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid_a, "Esc A")
        self.db.definir_escritorio_usuario(uid_a, eid)
        self.db.criar_empresa(uid_a, "EMPRESA DO CLIENTE")

        c = self.client(self.master_id)
        # Antes: master ve so a propria
        html = c.get("/empresas").get_data(as_text=True)
        self.assertIn("EMPRESA MASTER", html)
        self.assertNotIn("EMPRESA DO CLIENTE", html)

        c.post("/carteira/{}/suporte".format(eid), follow_redirects=True)
        html = c.get("/empresas").get_data(as_text=True)
        self.assertIn("EMPRESA DO CLIENTE", html)

    def test_suporte_expirado_perde_acesso(self):
        from datetime import datetime, timedelta
        uid_a = self.db.criar_usuario("Adm B", "admb@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid_a, "Esc B")
        self.db.definir_escritorio_usuario(uid_a, eid)
        self.db.criar_empresa(uid_a, "EMPRESA CLIENTE B")

        c = self.client(self.master_id)
        with c.session_transaction() as s:
            s["suporte"] = {
                "escritorio_id": eid,
                "razao_social": "Esc B",
                "expira": (datetime.now() - timedelta(minutes=1)).isoformat(),
            }
        html = c.get("/empresas").get_data(as_text=True)
        self.assertNotIn("EMPRESA CLIENTE B", html)

    def test_suporte_encerrado_volta_ao_normal(self):
        uid_a = self.db.criar_usuario("Adm C", "admc@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid_a, "Esc C")
        self.db.definir_escritorio_usuario(uid_a, eid)
        self.db.criar_empresa(uid_a, "EMPRESA CLIENTE C")

        c = self.client(self.master_id)
        c.post("/carteira/{}/suporte".format(eid), follow_redirects=True)
        c.post("/carteira/suporte/encerrar", follow_redirects=True)
        html = c.get("/empresas").get_data(as_text=True)
        self.assertNotIn("EMPRESA CLIENTE C", html)
        self.assertIn("EMPRESA MASTER", html)

    def test_suporte_registra_log(self):
        uid_a = self.db.criar_usuario("Adm D", "admd@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid_a, "Esc D")
        c = self.client(self.master_id)
        c.post("/carteira/{}/suporte".format(eid), follow_redirects=True)
        logs = self.db.get_db().execute(
            "SELECT acao FROM logs WHERE acao='suporte_iniciado'"
        ).fetchall()
        self.assertGreaterEqual(len(logs), 1)

    def test_nao_master_nao_acessa_suporte(self):
        u = self.db.criar_usuario("Comum", "comum@t.com", "1")
        uid_a = self.db.criar_usuario("Adm E", "adme@t.com", "1", is_admin=True)
        eid = self.db.criar_escritorio(uid_a, "Esc E")
        c = self.client(u)
        r = c.post("/carteira/{}/suporte".format(eid), follow_redirects=False)
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main(verbosity=2)
