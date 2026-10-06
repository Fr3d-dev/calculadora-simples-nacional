"""
Camada de banco de dados (SQLite) e autenticação.

Usa apenas a biblioteca padrão do Python (sqlite3 + hashlib), mantendo a
ferramenta simples e sem dependências externas além do Flask.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime

from flask import current_app, g


def _row_get(row, key, default=None):
    """Acesso seguro a sqlite3.Row — suporta dict-style .get() mesmo sem o método."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default

# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    sal TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    empresa_id INTEGER,
    permissoes TEXT DEFAULT '{}',
    criado_em TEXT NOT NULL,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    razao_social TEXT NOT NULL,
    nome_fantasia TEXT,
    cnpj TEXT,
    cnae_principal TEXT,
    cnae_descricao TEXT,
    cnaes_secundarios TEXT,
    anexo_sugerido TEXT,
    anexo_confirmado TEXT,
    municipio TEXT,
    uf TEXT,
    observacoes TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anexos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    empresa_id INTEGER,
    anexo TEXT NOT NULL,
    rbt12 TEXT,
    faturamento_mes TEXT,
    competencia TEXT,
    atualizado_em TEXT NOT NULL,
    UNIQUE(empresa_id, anexo),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS faturamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anexos_id INTEGER NOT NULL,
    mes_ano TEXT NOT NULL,
    valor TEXT,
    FOREIGN KEY (anexos_id) REFERENCES anexos(id) ON DELETE CASCADE,
    UNIQUE(anexos_id, mes_ano)
);

CREATE TABLE IF NOT EXISTS tabelas_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anexo TEXT NOT NULL,
    faixa INTEGER NOT NULL,
    limite_inferior TEXT,
    limite_superior TEXT,
    aliquota_nominal TEXT,
    valor_deduzir TEXT,
    UNIQUE(anexo, faixa)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    usuario_nome TEXT,
    acao TEXT NOT NULL,
    detalhe TEXT,
    criado_em TEXT NOT NULL
);
"""


def get_db() -> sqlite3.Connection:
    """Obtém (ou cria) a conexão SQLite para o request atual."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def _limpar_objetos_anexos_old(conn: sqlite3.Connection) -> None:
    """Remove triggers, views ou qualquer objeto que referencie anexos_old."""
    try:
        cur = conn.execute(
            "SELECT type, name FROM sqlite_master WHERE sql LIKE '%anexos_old%'"
        )
        for row in cur.fetchall():
            tipo, nome = row["type"], row["name"]
            conn.execute(f"DROP {tipo} IF EXISTS \"{nome}\"")
            print(f"  >>> Objeto removido: {tipo} {nome}")
        conn.commit()
    except Exception:
        pass  # se der erro, ignora — o importante é tentar


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    # Remove qualquer trigger/view que referencie a tabela anexos_old
    # antes de executar o schema, evitando erro no primeiro acesso.
    _limpar_objetos_anexos_old(db)
    db.executescript(SCHEMA)
    # Migração: adiciona coluna permissoes se não existir (bancos antigos)
    try:
        db.execute("ALTER TABLE usuarios ADD COLUMN permissoes TEXT DEFAULT '{}'")
        db.commit()
    except Exception:
        pass  # coluna já existe
    db.commit()
    _seed_tabelas_base(db)


def _seed_tabelas_base(db: sqlite3.Connection):
    """Popula a tabela de faixas a partir do motor de cálculo, se estiver vazia."""
    from calc import FAIXAS

    for anexo, faixas in FAIXAS.items():
        for idx, (inf, sup, aliq, ded) in enumerate(faixas, start=1):
            db.execute(
                """INSERT OR IGNORE INTO tabelas_base
                   (anexo, faixa, limite_inferior, limite_superior,
                    aliquota_nominal, valor_deduzir)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (anexo, idx, str(inf), str(sup), str(aliq), str(ded)),
            )
    db.commit()


# ---------------------------------------------------------------------------
# Hash de senha (PBKDF2-HMAC-SHA256, biblioteca padrão)
# ---------------------------------------------------------------------------

def hash_senha(senha: str, sal: str = None) -> tuple:
    if sal is None:
        sal = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal.encode("utf-8"), 120000)
    return dk.hex(), sal


def verificar_senha(senha: str, senha_hash: str, sal: str) -> bool:
    calculado, _ = hash_senha(senha, sal)
    return hashlib.compare_digest(calculado, senha_hash) if hasattr(hashlib, "compare_digest") else calculado == senha_hash


# ---------------------------------------------------------------------------
# Permissões (sistema granular baseado em JSON)
# ---------------------------------------------------------------------------

# Lista de todas as permissões disponíveis no sistema.
PERMISSOES_DISPONIVEIS = {
    "ver_dashboard": "Acessar o dashboard principal",
    "ver_anexos": "Visualizar dados dos anexos",
    "editar_anexos": "Editar/inserir faturamento nos anexos",
    "simular_anexos": "Usar modo de simulação nos anexos",
    "importar_xml": "Importar XML de notas fiscais",
    "importar_extrato": "Importar extrato PGDAS-D (PDF)",
    "gerenciar_empresas": "Cadastrar/editar/excluir empresas",
    "gerenciar_usuarios": "Criar/editar/excluir usuários",
    "ver_logs": "Visualizar logs de auditoria",
    "editar_tabelas": "Editar tabelas de alíquotas e faixas",
    "consultar_cnpj": "Consultar CNPJ na Receita Federal",
}

# Conjunto de permissões que o administrador tem por padrão (todas).
PERMISSOES_ADMIN = set(PERMISSOES_DISPONIVEIS.keys())


def get_permissoes(usuario) -> set:
    """Retorna um set com as permissões do usuário.

    Administradores sempre têm todas as permissões, independentemente do
    campo `permissoes` no banco.
    """
    if not usuario:
        return set()
    if _row_get(usuario, "is_admin"):
        return set(PERMISSOES_ADMIN)
    raw = _row_get(usuario, "permissoes") or "{}"
    if isinstance(raw, str):
        try:
            import json
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return set()
    else:
        data = raw
    if isinstance(data, dict):
        return {k for k, v in data.items() if v}
    if isinstance(data, (list, tuple)):
        return set(data)
    return set()


def tem_permissao(usuario, permissao: str) -> bool:
    """Verifica se o usuário tem uma permissão específica."""
    return permissao in get_permissoes(usuario)


def salvar_permissoes(user_id: int, permissoes: set, conn=None):
    """Salva um conjunto de permissões para o usuário (formato JSON dict)."""
    db = conn or get_db()
    data = {p: True for p in permissoes}
    import json
    db.execute(
        "UPDATE usuarios SET permissoes=? WHERE id=?",
        (json.dumps(data, ensure_ascii=False), user_id),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------

def criar_usuario(
    nome, email, senha, *,
    is_admin=False, ativo=True, permissoes=None, empresa_id=None, conn=None,
):
    db = conn or get_db()
    senha_hash, sal = hash_senha(senha)
    import json
    permissoes_json = json.dumps(permissoes or {}, ensure_ascii=False)
    cur = db.execute(
        """INSERT INTO usuarios (nome, email, senha_hash, sal, is_admin, ativo,
                                 empresa_id, permissoes, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome.strip(), email.strip().lower(), senha_hash, sal,
         1 if is_admin else 0, 1 if ativo else 0,
         empresa_id, permissoes_json,
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return cur.lastrowid


def buscar_usuario_por_email(email, conn=None):
    db = conn or get_db()
    return db.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)
    ).fetchone()


def buscar_usuario_por_id(user_id, conn=None):
    db = conn or get_db()
    return db.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()


def listar_usuarios(conn=None):
    db = conn or get_db()
    return db.execute(
        "SELECT * FROM usuarios ORDER BY is_admin DESC, nome"
    ).fetchall()


def atualizar_usuario(
    user_id, nome, email, *,
    senha=None, is_admin=False, ativo=True, permissoes=None, empresa_id=None, conn=None,
):
    db = conn or get_db()
    import json
    permissoes_json = json.dumps(permissoes or {}, ensure_ascii=False)

    if senha:
        senha_hash, sal = hash_senha(senha)
        db.execute(
            """UPDATE usuarios
               SET nome=?, email=?, senha_hash=?, sal=?,
                   is_admin=?, ativo=?, empresa_id=?, permissoes=?
               WHERE id=?""",
            (nome.strip(), email.strip().lower(), senha_hash, sal,
             1 if is_admin else 0, 1 if ativo else 0,
             empresa_id, permissoes_json, user_id),
        )
    else:
        db.execute(
            """UPDATE usuarios
               SET nome=?, email=?, is_admin=?, ativo=?, empresa_id=?, permissoes=?
               WHERE id=?""",
            (nome.strip(), email.strip().lower(),
             1 if is_admin else 0, 1 if ativo else 0,
             empresa_id, permissoes_json, user_id),
        )
    db.commit()


def excluir_usuario(user_id, conn=None):
    db = conn or get_db()
    db.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Anexos e faturamentos
# ---------------------------------------------------------------------------

def obter_ou_criar_anexo(usuario_id, anexo, conn=None, empresa_id=None):
    db = conn or get_db()
    if empresa_id:
        row = db.execute(
            "SELECT * FROM anexos WHERE empresa_id=? AND anexo=?",
            (empresa_id, anexo.upper()),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM anexos WHERE usuario_id=? AND anexo=? AND empresa_id IS NULL",
            (usuario_id, anexo.upper()),
        ).fetchone()
    if row:
        return row
    cur = db.execute(
        """INSERT INTO anexos (usuario_id, empresa_id, anexo, rbt12, faturamento_mes, competencia, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (usuario_id, empresa_id, anexo.upper(), "", "", "", datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return db.execute("SELECT * FROM anexos WHERE id=?", (cur.lastrowid,)).fetchone()


def obter_faturamentos(anexos_id, conn=None):
    """
    Retorna um dict {mes_ano: valor} com todos os faturamentos salvos
    para este anexo.
    """
    db = conn or get_db()
    rows = db.execute(
        "SELECT mes_ano, valor FROM faturamentos WHERE anexos_id=? ORDER BY mes_ano",
        (anexos_id,),
    ).fetchall()
    return {r["mes_ano"]: r["valor"] or "" for r in rows}


def salvar_faturamento_mes(anexos_id, mes_ano, valor, conn=None):
    db = conn or get_db()
    db.execute(
        """INSERT INTO faturamentos (anexos_id, mes_ano, valor)
           VALUES (?, ?, ?)
           ON CONFLICT(anexos_id, mes_ano) DO UPDATE SET valor=excluded.valor""",
        (anexos_id, mes_ano, valor),
    )
    db.commit()


def salvar_dados_anexo(anexos_id, rbt12=None, faturamento_mes=None,
                       competencia=None, conn=None):
    db = conn or get_db()
    campos = []
    valores = []
    if rbt12 is not None:
        campos.append("rbt12=?"), valores.append(rbt12)
    if faturamento_mes is not None:
        campos.append("faturamento_mes=?"), valores.append(faturamento_mes)
    if competencia is not None:
        campos.append("competencia=?"), valores.append(competencia)
    if not campos:
        return
    campos.append("atualizado_em=?")
    valores.append(datetime.now().isoformat(timespec="seconds"))
    valores.append(anexos_id)
    db.execute(f"UPDATE anexos SET {', '.join(campos)} WHERE id=?", valores)
    db.commit()


# ---------------------------------------------------------------------------
# Tabelas base (administração)
# ---------------------------------------------------------------------------

def verificar_anexos_com_dados(empresa_id, conn=None):
    """Verifica se a empresa já possui faturamento importado em algum anexo.

    Retorna uma lista de anexos (ex: ['I', 'III']) que já têm dados.
    """
    db = conn or get_db()
    linhas = db.execute(
        """SELECT DISTINCT a.anexo FROM anexos a
           INNER JOIN faturamentos f ON f.anexos_id = a.id
           WHERE a.empresa_id = ?""",
        (empresa_id,),
    ).fetchall()
    return [r["anexo"] for r in linhas]


def listar_tabelas_base(anexo=None, conn=None):
    db = conn or get_db()
    if anexo:
        return db.execute(
            "SELECT * FROM tabelas_base WHERE anexo=? ORDER BY faixa", (anexo.upper(),)
        ).fetchall()
    return db.execute(
        "SELECT * FROM tabelas_base ORDER BY anexo, faixa"
    ).fetchall()


def atualizar_tabela_base(tabela_id, limite_inferior, limite_superior,
                          aliquota_nominal, valor_deduzir, conn=None):
    db = conn or get_db()
    db.execute(
        """UPDATE tabelas_base SET limite_inferior=?, limite_superior=?,
           aliquota_nominal=?, valor_deduzir=? WHERE id=?""",
        (limite_inferior, limite_superior, aliquota_nominal, valor_deduzir, tabela_id),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Logs / auditoria
# ---------------------------------------------------------------------------

def registrar_log(usuario, acao, detalhe="", conn=None):
    try:
        db = conn or get_db()
        db.execute(
            "INSERT INTO logs (usuario_id, usuario_nome, acao, detalhe, criado_em) VALUES (?,?,?,?,?)",
            (
                usuario["id"] if usuario else None,
                usuario["nome"] if usuario else "sistema",
                acao,
                detalhe,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.commit()
    except Exception:
        # Log nunca deve quebrar a aplicação.
        pass


def listar_logs(limite=100, conn=None):
    db = conn or get_db()
    return db.execute(
        "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------

def criar_empresa(usuario_id, razao_social, nome_fantasia="", cnpj="",
                  cnae_principal="", cnae_descricao="", cnaes_secundarios="",
                  anexo_sugerido="", anexo_confirmado="", municipio="", uf="",
                  observacoes="", conn=None):
    db = conn or get_db()
    agora = datetime.now().isoformat(timespec="seconds")
    cur = db.execute(
        """INSERT INTO empresas
           (usuario_id, razao_social, nome_fantasia, cnpj, cnae_principal,
            cnae_descricao, cnaes_secundarios, anexo_sugerido, anexo_confirmado,
            municipio, uf, observacoes, criado_em, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (usuario_id, razao_social.strip(), nome_fantasia.strip(), cnpj.strip(),
         cnae_principal.strip(), cnae_descricao.strip(), cnaes_secundarios.strip(),
         (anexo_sugerido or "").upper(), (anexo_confirmado or "").upper(),
         municipio.strip(), uf.strip().upper(), observacoes.strip(), agora, agora),
    )
    db.commit()
    return cur.lastrowid


def buscar_empresa_por_id(empresa_id, conn=None):
    db = conn or get_db()
    return db.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()


def listar_empresas(usuario_id=None, conn=None):
    db = conn or get_db()
    if usuario_id is not None:
        return db.execute(
            "SELECT * FROM empresas WHERE usuario_id = ? ORDER BY razao_social",
            (usuario_id,),
        ).fetchall()
    return db.execute("SELECT * FROM empresas ORDER BY razao_social").fetchall()


def atualizar_empresa(empresa_id, razao_social, nome_fantasia="", cnpj="",
                      cnae_principal="", cnae_descricao="", cnaes_secundarios="",
                      anexo_sugerido="", anexo_confirmado="", municipio="", uf="",
                      observacoes="", conn=None):
    db = conn or get_db()
    db.execute(
        """UPDATE empresas SET razao_social=?, nome_fantasia=?, cnpj=?,
           cnae_principal=?, cnae_descricao=?, cnaes_secundarios=?,
           anexo_sugerido=?, anexo_confirmado=?, municipio=?, uf=?,
           observacoes=?, atualizado_em=? WHERE id=?""",
        (razao_social.strip(), nome_fantasia.strip(), cnpj.strip(),
         cnae_principal.strip(), cnae_descricao.strip(), cnaes_secundarios.strip(),
         (anexo_sugerido or "").upper(), (anexo_confirmado or "").upper(),
         municipio.strip(), uf.strip().upper(), observacoes.strip(),
         datetime.now().isoformat(timespec="seconds"), empresa_id),
    )
    db.commit()


def excluir_empresa(empresa_id, conn=None):
    db = conn or get_db()
    db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
    db.commit()


def definir_empresa_usuario(usuario_id, empresa_id, conn=None):
    """Define qual empresa está ativa para o usuário."""
    db = conn or get_db()
    db.execute("UPDATE usuarios SET empresa_id=? WHERE id=?", (empresa_id, usuario_id))
    db.commit()
