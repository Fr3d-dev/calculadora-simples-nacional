"""Testa que clientes da Carteira não aparecem na aba Usuários.

Regra de negócio: um acesso criado na aba Usuários (origem='interno') aparece
só lá; um acesso criado na Carteira de clientes (origem='carteira') aparece
só na Carteira.

Rodar com:  python -m unittest simples_app.test_origem_usuario
"""
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class OrigemUsuarioTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="simples_origem_")
        self.db_path = os.path.join(self.tmpdir, "teste.db")
        os.environ["SIMPLES_DB"] = self.db_path

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.app.config.update(
            TESTING=True, DATABASE=self.db_path, WTF_CSRF_ENABLED=False,
        )
        self.ctx = app_module.app.app_context()
        self.ctx.push()

        import database as db
        self.db = db
        db.init_db()

    def tearDown(self):
        try:
            self.db.get_db().close()
        except Exception:
            pass
        self.ctx.pop()

    def test_cliente_da_carteira_nao_aparece_como_interno(self):
        interno_id = self.db.criar_usuario(
            "Analista", "analista@escritorio.com", "senha123",
        )
        cliente_id = self.db.criar_usuario(
            "Cliente X", "cliente@x.com", "senha123", origem="carteira",
        )

        internos = [u["id"] for u in self.db.listar_usuarios(origem="interno")]
        carteira = [u["id"] for u in self.db.listar_usuarios(origem="carteira")]

        self.assertIn(interno_id, internos)
        self.assertNotIn(cliente_id, internos)
        self.assertEqual(carteira, [cliente_id])

    def test_backfill_marca_dono_de_escritorio(self):
        """Usuário legado que é dono de escritório vira origem='carteira'."""
        uid = self.db.criar_usuario("Antigo", "antigo@x.com", "senha123")
        self.db.criar_escritorio(uid, "Antigo ME")

        # Simula banco legado: origem gravada errada; migração corrige.
        conn = self.db.get_db()
        conn.execute("UPDATE usuarios SET origem='interno' WHERE id=?", (uid,))
        conn.commit()
        self.db.init_db()

        row = conn.execute(
            "SELECT origem FROM usuarios WHERE id=?", (uid,)
        ).fetchone()
        self.assertEqual(row["origem"], "carteira")

    def test_origem_preservada_na_edicao(self):
        uid = self.db.criar_usuario(
            "Cliente Y", "y@x.com", "senha123", origem="carteira",
        )
        self.db.atualizar_usuario(uid, "Cliente Y2", "y2@x.com")
        row = self.db.get_db().execute(
            "SELECT origem FROM usuarios WHERE id=?", (uid,)
        ).fetchone()
        self.assertEqual(row["origem"], "carteira")


if __name__ == "__main__":
    unittest.main()
