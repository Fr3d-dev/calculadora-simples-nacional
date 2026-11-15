"""
Testes do isolamento entre escritórios (Carteira de clientes / master).

Rodar com:  python test_isolamento_escritorio.py

Usa um banco SQLite temporário — NUNCA toca em instance/simples.db.
"""
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class IsolamentoEscritorioTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="simples_teste_")
        self.db_path = os.path.join(self.tmpdir, "teste.db")
        os.environ["SIMPLES_DB"] = self.db_path

        import app as app_module
        import importlib
        importlib.reload(app_module)

        self.app = app_module.app
        self.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            WTF_CSRF_ENABLED=False,
        )
        import database as db
        self.db = db
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.init_db()

        # Dois escritórios, cada um com um admin.
        self.uid_a = db.criar_usuario("Admin A", "a@teste.com", "123456", is_admin=True)
        self.uid_b = db.criar_usuario("Admin B", "b@teste.com", "123456", is_admin=True)
        self.esc_a = db.criar_escritorio(self.uid_a, "Escritorio A")
        self.esc_b = db.criar_escritorio(self.uid_b, "Escritorio B")
        db.definir_escritorio_usuario(self.uid_a, self.esc_a)
        db.definir_escritorio_usuario(self.uid_b, self.esc_b)

        # Um funcionário dentro do escritório A.
        self.uid_func = db.criar_usuario("Func A", "func@teste.com", "123456", is_admin=False)
        db.definir_escritorio_usuario(self.uid_func, self.esc_a)

        # Empresas de cada um.
        self.emp_a = db.criar_empresa(self.uid_a, "EMPRESA DO A")
        self.emp_b = db.criar_empresa(self.uid_b, "EMPRESA DO B")
        self.emp_func = db.criar_empresa(self.uid_func, "EMPRESA DO FUNC A")

    def tearDown(self):
        self.ctx.pop()
        try:
            os.environ.pop("SIMPLES_DB", None)
            import shutil
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        except Exception:
            pass

    def _client_logado(self, uid):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["usuario_id"] = uid
        return client

    # ---------------------- Camada de dados -------------------------

    def test_coluna_escritorio_id_existe(self):
        colunas = [r[1] for r in self.db.get_db().execute("PRAGMA table_info(usuarios)")]
        self.assertIn("escritorio_id", colunas)

    def test_usuarios_do_escritorio(self):
        ids = self.db.usuarios_do_escritorio(self.esc_a)
        self.assertIn(self.uid_a, ids)
        self.assertIn(self.uid_func, ids)
        self.assertNotIn(self.uid_b, ids)

    def test_listar_empresas_por_escritorio(self):
        ids_a = self.db.usuarios_do_escritorio(self.esc_a)
        nomes = {e["razao_social"] for e in self.db.listar_empresas(usuario_ids=ids_a)}
        self.assertEqual(nomes, {"EMPRESA DO A", "EMPRESA DO FUNC A"})

    def test_listar_empresas_lista_vazia_nao_vaza(self):
        self.assertEqual(self.db.listar_empresas(usuario_ids=[]), [])

    # ---------------------- Camada web ------------------------------

    def test_admin_a_nao_ve_empresa_do_b_na_listagem(self):
        client = self._client_logado(self.uid_a)
        html = client.get("/empresas").get_data(as_text=True)
        self.assertIn("EMPRESA DO A", html)
        self.assertNotIn("EMPRESA DO B", html)

    def test_usuario_nao_ve_empresa_de_colega_do_mesmo_escritorio(self):
        # Mesmo escritório, cadastros diferentes: ninguém vê a empresa do outro.
        client = self._client_logado(self.uid_a)
        html = client.get("/empresas").get_data(as_text=True)
        self.assertNotIn("EMPRESA DO FUNC A", html)

        # Funcionário não tem "gerenciar_empresas" (a rota /empresas redireciona),
        # então a verificação é feita na camada de dados.
        nomes = {e["razao_social"] for e in self.db.listar_empresas(usuario_ids=[self.uid_func])}
        self.assertIn("EMPRESA DO FUNC A", nomes)
        self.assertNotIn("EMPRESA DO A", nomes)
        self.assertNotIn("EMPRESA DO B", nomes)

    def test_admin_a_nao_ve_empresa_do_funcionario(self):
        client = self._client_logado(self.uid_a)
        html = client.get("/empresas").get_data(as_text=True)
        self.assertNotIn("EMPRESA DO FUNC A", html)

    def test_empresa_de_outro_usuario_da_404_ao_editar(self):
        client = self._client_logado(self.uid_a)
        resp = client.get(f"/empresa/{self.emp_func}/editar", follow_redirects=True)
        self.assertNotIn("EMPRESA DO FUNC A", resp.get_data(as_text=True))

    def test_empresa_de_outro_escritorio_da_404_ao_editar(self):
        client = self._client_logado(self.uid_a)
        resp = client.get(f"/empresa/{self.emp_b}/editar", follow_redirects=True)
        self.assertNotIn("EMPRESA DO B", resp.get_data(as_text=True))

    def test_nao_pode_selecionar_empresa_de_outro_escritorio(self):
        client = self._client_logado(self.uid_a)
        client.post(f"/empresa/{self.emp_b}/selecionar", follow_redirects=True)
        self.ctx.pop()
        self.ctx.push()
        self.db.get_db()
        linha = self.db.buscar_usuario_por_id(self.uid_a)
        self.assertNotEqual(linha["empresa_id"], self.emp_b)

    # ---------------------- Master ------------------------------

    def test_master_sem_escritorio_ve_apenas_as_proprias(self):
        uid_m = self.db.criar_usuario("Master", "m@teste.com", "123456", is_admin=True)
        self.db.definir_master(uid_m, True)
        emp_m = self.db.criar_empresa(uid_m, "EMPRESA DO MASTER")
        client = self._client_logado(uid_m)
        html = client.get("/empresas").get_data(as_text=True)
        self.assertIn("EMPRESA DO MASTER", html)
        self.assertNotIn("EMPRESA DO B", html)
        self.assertNotIn("EMPRESA DO A", html)

    def test_master_nao_e_admin_de_escritorio_por_acidente(self):
        uid_m = self.db.criar_usuario("Master2", "m2@teste.com", "123456", is_admin=True)
        self.db.definir_master(uid_m, True)
        self.assertIsNone(self.db.escritorio_do_usuario(self.db.buscar_usuario_por_id(uid_m)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
