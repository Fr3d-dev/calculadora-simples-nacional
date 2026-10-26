"""
Camada de banco de dados (SQLite) e autenticação.

Usa apenas a biblioteca padrão do Python (sqlite3 + hashlib), mantendo a
ferramenta simples e sem dependências externas além do Flask.
"""

from __future__ import annotations

import hashlib
import json
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

-- Vínculo oficial CNAE -> item da LC 116/2003 (Cnae_X_Item_Lista_Servicos).
-- Editável pela aba Tabelas, para corrigir um vínculo sem republicar o app.
CREATE TABLE IF NOT EXISTS cnae_itens_lc116 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cnae TEXT NOT NULL,
    item TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT,
    UNIQUE(cnae, item)
);

CREATE INDEX IF NOT EXISTS idx_cnae_itens_cnae ON cnae_itens_lc116(cnae);

-- Relação CNAE x ANEXO (base da planilha CNAE_Subclasses_..._DESCRICOES).
-- Precedência sobre a regra fixa do motor: o que estiver aqui manda no
-- cadastro da empresa. Editável na aba Tabelas, sem republicar o app.
CREATE TABLE IF NOT EXISTS cnae_anexos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cnae TEXT NOT NULL,
    descricao TEXT,
    anexo TEXT NOT NULL,          -- "II", "V/III", "I/III" ...
    anexos TEXT NOT NULL,         -- JSON: ["V","III"] (ordem = precedência)
    origem TEXT NOT NULL DEFAULT 'planilha',
    atualizado_em TEXT,
    UNIQUE(cnae)
);

CREATE INDEX IF NOT EXISTS idx_cnae_anexos_cnae ON cnae_anexos(cnae);

-- Relação NBS x cClassTrib x Indicador de Operação (INDOP), carregada da
-- planilha RELAÇÃO NBS Cclasstrib e Ind Operac.xlsx e exibida na aba Tabelas.
CREATE TABLE IF NOT EXISTS relacao_nbs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ordem INTEGER NOT NULL DEFAULT 0,
    item_lc116 TEXT,
    descricao_item TEXT,
    nbs TEXT,
    descricao_nbs TEXT,
    ps_onerosa TEXT,
    adq_exterior TEXT,
    indop TEXT,
    local_incidencia TEXT,
    cclasstrib TEXT,
    nome_cclasstrib TEXT
);

CREATE INDEX IF NOT EXISTS idx_relacao_nbs_nbs ON relacao_nbs(nbs);
CREATE INDEX IF NOT EXISTS idx_relacao_nbs_cclasstrib ON relacao_nbs(cclasstrib);

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
    _seed_cnae_itens_lc116(db)
    _seed_cnae_anexos(db)
    _seed_relacao_nbs(db)


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


def _seed_cnae_itens_lc116(db: sqlite3.Connection):
    """Popula o vínculo CNAE -> item LC 116 a partir de cnae_item_lc116.py.

    Só roda quando a tabela está vazia: depois da primeira carga, o banco passa
    a ser a fonte da verdade (e o que o usuário editar na aba Tabelas prevalece).
    """
    try:
        total = db.execute("SELECT COUNT(*) FROM cnae_itens_lc116").fetchone()[0]
        if total:
            return
        from cnae_item_lc116 import CNAE_ITEM
    except Exception as exc:  # noqa: BLE001 - não impede a subida do app
        print(f"  >>> Seed CNAE x Item LC 116 ignorado: {exc}")
        return

    agora = datetime.now().isoformat(timespec="seconds")
    for cnae, itens in CNAE_ITEM.items():
        for ordem, item in enumerate(itens):
            db.execute(
                """INSERT OR IGNORE INTO cnae_itens_lc116
                   (cnae, item, ordem, atualizado_em)
                   VALUES (?, ?, ?, ?)""",
                (str(cnae).strip(), str(item).strip(), ordem, agora),
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
    "ver_relatorios": "Visualizar/baixar relatórios (Excel e PDF)",
    "ver_logs": "Visualizar logs de auditoria",
    "editar_tabelas": "Editar tabelas de alíquotas e faixas",
    "consultar_cnpj": "Consultar CNPJ na Receita Federal",
    "ver_explicacao_cnae": "Ver explicação do enquadramento de CNAE (LC 116/2003)",
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
# Vínculo CNAE -> item da LC 116/2003 (administração)
# ---------------------------------------------------------------------------

def _normalizar_cnae(cnae) -> str:
    """Deixa só os dígitos do CNAE (ex.: '1813-0/99' -> '1813099')."""
    return "".join(c for c in str(cnae or "") if c.isdigit())


def listar_cnae_itens(busca=None, limite=500, conn=None):
    """Vínculos CNAE -> item, filtrando por dígitos ou prefixo do item."""
    db = conn or get_db()
    if busca and busca.strip():
        termo = busca.strip()
        digitos = _normalizar_cnae(termo)
        if digitos:
            return db.execute(
                """SELECT * FROM cnae_itens_lc116
                   WHERE cnae LIKE ? OR item = ?
                   ORDER BY cnae, ordem, item LIMIT ?""",
                (f"%{digitos}%", termo, limite),
            ).fetchall()
        return db.execute(
            """SELECT * FROM cnae_itens_lc116
               WHERE item LIKE ? ORDER BY cnae, ordem, item LIMIT ?""",
            (f"%{termo}%", limite),
        ).fetchall()
    return db.execute(
        "SELECT * FROM cnae_itens_lc116 ORDER BY cnae, ordem, item LIMIT ?",
        (limite,),
    ).fetchall()


def itens_do_cnae(cnae, conn=None) -> list:
    """Itens da LC 116 vinculados a um CNAE, na ordem cadastrada."""
    db = conn or get_db()
    codigo = _normalizar_cnae(cnae)
    if not codigo:
        return []
    linhas = db.execute(
        """SELECT item FROM cnae_itens_lc116
           WHERE cnae=? ORDER BY ordem, item""",
        (codigo,),
    ).fetchall()
    return [r["item"] for r in linhas]


def todos_cnae_itens(conn=None) -> dict:
    """Mapa {cnae: [itens]} de toda a tabela (uso em memória/explicações)."""
    db = conn or get_db()
    mapa = {}
    for linha in db.execute(
        "SELECT cnae, item FROM cnae_itens_lc116 ORDER BY cnae, ordem, item"
    ):
        mapa.setdefault(linha["cnae"], []).append(linha["item"])
    return mapa


def atualizar_cnae_item(registro_id, cnae, item, conn=None):
    """Edita o CNAE e/ou o item de um vínculo, preservando a ordem."""
    db = conn or get_db()
    codigo = _normalizar_cnae(cnae)
    novo_item = (item or "").strip()
    if not codigo or not novo_item:
        raise ValueError("Informe o CNAE e o item da LC 116.")
    db.execute(
        """UPDATE cnae_itens_lc116 SET cnae=?, item=?, atualizado_em=?
           WHERE id=?""",
        (codigo, novo_item, datetime.now().isoformat(timespec="seconds"),
         registro_id),
    )
    db.commit()


def adicionar_cnae_item(cnae, item, conn=None) -> int:
    """Inclui um vínculo. Se já existir, mantém o registro existente."""
    db = conn or get_db()
    codigo = _normalizar_cnae(cnae)
    novo_item = (item or "").strip()
    if not codigo or not novo_item:
        raise ValueError("Informe o CNAE e o item da LC 116.")
    proxima = db.execute(
        "SELECT COALESCE(MAX(ordem), -1) + 1 FROM cnae_itens_lc116 WHERE cnae=?",
        (codigo,),
    ).fetchone()[0]
    cur = db.execute(
        """INSERT OR IGNORE INTO cnae_itens_lc116
           (cnae, item, ordem, atualizado_em) VALUES (?, ?, ?, ?)""",
        (codigo, novo_item, proxima,
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return cur.lastrowid


def excluir_cnae_item(registro_id, conn=None):
    db = conn or get_db()
    db.execute("DELETE FROM cnae_itens_lc116 WHERE id=?", (registro_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Relação CNAE x ANEXO (base editável do enquadramento)
# ---------------------------------------------------------------------------

# Planilha de origem, lida uma única vez quando a tabela está vazia.
PLANILHA_CNAE_ANEXO = "CNAE_Subclasses_2_3_Estrutura_Detalhada_DESCRICOES.xlsx"

# Ordem canônica dos anexos (usada quando o texto não deixa a ordem clara).
_ORDEM_ANEXOS = ["I", "II", "III", "IV", "V"]


def normalizar_anexo_expressao(texto) -> tuple:
    """Converte "Anexo V / Anexo III" em ("V/III", ["V", "III"]).

    Aceita as formas que aparecem no cadastro e na planilha:
    "III", "Anexo II", "Anexo V / Anexo III", "I/III", "V,III".
    A ordem informada é preservada: o primeiro é o anexo sugerido.
    """
    import re

    bruto = str(texto or "").upper()
    # Captura "ANEXO II" e também "II" solto, sempre como palavra isolada.
    tokens = re.findall(r"[A-Z]+", bruto)
    anexos = []
    for token in tokens:
        if token == "ANEXO":
            continue
        if token in _ORDEM_ANEXOS and token not in anexos:
            anexos.append(token)
    if not anexos:
        return "", []
    return "/".join(anexos), anexos


def _seed_cnae_anexos(db: sqlite3.Connection):
    """Carrega a relação CNAE x ANEXO da planilha, se a tabela estiver vazia.

    Depois da primeira carga o BANCO é a fonte da verdade: o que o usuário
    corrigir em Tabelas > CNAE x Anexo prevalece sobre a planilha e sobre a
    regra fixa do motor, sem precisar republicar o app.
    """
    try:
        total = db.execute("SELECT COUNT(*) FROM cnae_anexos").fetchone()[0]
        if total:
            return
        import os as _os
        from openpyxl import load_workbook

        base = _os.path.dirname(_os.path.abspath(__file__))
        caminho = None
        for pasta in (base, _os.path.dirname(base)):
            candidato = _os.path.join(pasta, PLANILHA_CNAE_ANEXO)
            if _os.path.exists(candidato):
                caminho = candidato
                break
        if not caminho:
            print(f"  >>> Seed CNAE x ANEXO ignorado: {PLANILHA_CNAE_ANEXO} não encontrada.")
            return

        wb = load_workbook(caminho, data_only=True, read_only=True)
        ws = wb[wb.sheetnames[0]]
    except Exception as exc:  # noqa: BLE001 - não impede a subida do app
        print(f"  >>> Seed CNAE x ANEXO ignorado: {exc}")
        return

    agora = datetime.now().isoformat(timespec="seconds")
    carregados = 0
    for linha in ws.iter_rows(min_row=2, values_only=True):
        if not linha or not linha[0]:
            continue
        codigo = _normalizar_cnae(linha[0])
        if len(codigo) != 7:
            continue
        descricao = " ".join(str(linha[1] or "").split())
        expressao, anexos = normalizar_anexo_expressao(linha[2] if len(linha) > 2 else "")
        if not anexos:
            # Sem anexo definido (extrativismo, administração pública etc.):
            # guardamos a descrição para o cadastro, sem inventar enquadramento.
            expressao, anexos = "", []
        db.execute(
            """INSERT OR IGNORE INTO cnae_anexos
               (cnae, descricao, anexo, anexos, origem, atualizado_em)
               VALUES (?, ?, ?, ?, 'planilha', ?)""",
            (codigo, descricao, expressao,
             json.dumps(anexos, ensure_ascii=False), agora),
        )
        carregados += 1
    db.commit()
    print(f"  >>> CNAE x ANEXO: {carregados} subclasse(s) carregada(s) da planilha.")


def _seed_relacao_nbs(db: sqlite3.Connection):
    """Carrega a relação NBS x cClassTrib x INDOP a partir do JSON/planilha.

    Só roda quando a tabela está vazia. Prefere o `relacao_nbs.json` versionado
    no Git (disponível no servidor) e cai na planilha .xlsx se ela existir.
    Se nenhuma fonte estiver disponível, o app sobe normalmente e a aba Tabelas
    avisa.
    """
    try:
        total = db.execute("SELECT COUNT(*) FROM relacao_nbs").fetchone()[0]
        if total:
            return
        import relacao_nbs as fonte
        registros = fonte.carregar()
    except Exception as exc:  # noqa: BLE001 - não impede a subida do app
        print(f"  >>> Seed RELAÇÃO NBS ignorado: {exc}")
        return

    db.executemany(
        """INSERT INTO relacao_nbs
           (ordem, item_lc116, descricao_item, nbs, descricao_nbs,
            ps_onerosa, adq_exterior, indop, local_incidencia,
            cclasstrib, nome_cclasstrib)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                r.get("ordem", 0), r.get("item_lc116", ""),
                r.get("descricao_item", ""), r.get("nbs", ""),
                r.get("descricao_nbs", ""), r.get("ps_onerosa", ""),
                r.get("adq_exterior", ""), r.get("indop", ""),
                r.get("local_incidencia", ""), r.get("cclasstrib", ""),
                r.get("nome_cclasstrib", ""),
            )
            for r in registros
        ],
    )
    db.commit()
    print(f"  >>> RELAÇÃO NBS: {len(registros)} linha(s) carregada(s).")


def listar_relacao_nbs(busca=None, limite=2000, conn=None):
    """Relação NBS x cClassTrib x INDOP, filtrando por NBS, item, cClassTrib
    ou texto da descrição."""
    db = conn or get_db()
    if busca and busca.strip():
        termo = busca.strip()
        padrao = f"%{termo}%"
        return db.execute(
            """SELECT * FROM relacao_nbs
               WHERE nbs LIKE ? OR cclasstrib LIKE ? OR item_lc116 LIKE ?
                  OR descricao_item LIKE ? OR descricao_nbs LIKE ?
                  OR nome_cclasstrib LIKE ?
               ORDER BY ordem, id LIMIT ?""",
            (padrao, padrao, padrao, padrao, padrao, padrao, limite),
        ).fetchall()
    return db.execute(
        "SELECT * FROM relacao_nbs ORDER BY ordem, id LIMIT ?", (limite,)
    ).fetchall()


def contar_relacao_nbs(conn=None) -> int:
    """Quantidade total de linhas da relação NBS no banco."""
    db = conn or get_db()
    return db.execute("SELECT COUNT(*) FROM relacao_nbs").fetchone()[0]


def relacao_nbs_por_itens(itens, conn=None) -> list:
    """Linhas da relação NBS dos itens LC 116 informados (ex.: ["01.01"]).

    Retorna na ordem da planilha (ordem, id) para que as classificações de um
    mesmo item apareçam agrupadas e na sequência original.
    """
    db = conn or get_db()
    codigos = [i for i in (itens or []) if i]
    if not codigos:
        return []
    marcadores = ",".join("?" for _ in codigos)
    return db.execute(
        f"""SELECT * FROM relacao_nbs
            WHERE item_lc116 IN ({marcadores})
            ORDER BY ordem, id""",
        tuple(codigos),
    ).fetchall()


def _campos_relacao_nbs(dados: dict) -> tuple:
    """Normaliza os 10 campos editáveis, na ordem das colunas do banco."""
    return tuple(" ".join(str(dados.get(col) or "").split())
                 for col in (
                     "item_lc116", "descricao_item", "nbs", "descricao_nbs",
                     "ps_onerosa", "adq_exterior", "indop",
                     "local_incidencia", "cclasstrib", "nome_cclasstrib",
                 ))


def atualizar_relacao_nbs(registro_id, dados: dict, conn=None):
    """Atualiza uma linha da relação NBS x cClassTrib x INDOP.

    Vale imediatamente para todo o sistema: o banco é a fonte da verdade.
    """
    db = conn or get_db()
    campos = _campos_relacao_nbs(dados)
    db.execute(
        """UPDATE relacao_nbs SET
               item_lc116=?, descricao_item=?, nbs=?, descricao_nbs=?,
               ps_onerosa=?, adq_exterior=?, indop=?, local_incidencia=?,
               cclasstrib=?, nome_cclasstrib=?
           WHERE id=?""",
        (*campos, registro_id),
    )
    db.commit()


def adicionar_relacao_nbs(dados: dict, conn=None) -> int:
    """Inclui uma nova linha na relação. Exige NBS ou cClassTrib informado."""
    db = conn or get_db()
    campos = _campos_relacao_nbs(dados)
    if not campos[2] and not campos[8]:
        raise ValueError(
            "Informe a NBS e/ou o cClassTrib (ex.: 1.0101.10 / 000001)."
        )
    ordem = db.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM relacao_nbs").fetchone()[0]
    cur = db.execute(
        """INSERT INTO relacao_nbs
           (ordem, item_lc116, descricao_item, nbs, descricao_nbs,
            ps_onerosa, adq_exterior, indop, local_incidencia,
            cclasstrib, nome_cclasstrib)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ordem, *campos),
    )
    db.commit()
    return cur.lastrowid


def excluir_relacao_nbs(registro_id, conn=None):
    """Remove uma linha da relação NBS."""
    db = conn or get_db()
    db.execute("DELETE FROM relacao_nbs WHERE id=?", (registro_id,))
    db.commit()


def listar_cnae_anexos(busca=None, limite=2000, conn=None):
    """Relação CNAE x ANEXO, filtrando por dígitos do CNAE ou pelo anexo."""
    db = conn or get_db()
    if busca and busca.strip():
        termo = busca.strip()
        digitos = _normalizar_cnae(termo)
        if digitos:
            return db.execute(
                """SELECT * FROM cnae_anexos
                   WHERE cnae LIKE ? ORDER BY cnae LIMIT ?""",
                (f"%{digitos}%", limite),
            ).fetchall()
        return db.execute(
            """SELECT * FROM cnae_anexos
               WHERE anexo LIKE ? OR descricao LIKE ? ORDER BY cnae LIMIT ?""",
            (f"%{termo.upper()}%", f"%{termo}%", limite),
        ).fetchall()
    return db.execute(
        "SELECT * FROM cnae_anexos ORDER BY cnae LIMIT ?", (limite,)
    ).fetchall()


def buscar_cnae_anexo(cnae, conn=None):
    """Registro de anexo de um CNAE (ou None). Usado pelo motor."""
    db = conn or get_db()
    codigo = _normalizar_cnae(cnae)
    if len(codigo) != 7:
        return None
    return db.execute(
        "SELECT * FROM cnae_anexos WHERE cnae=?", (codigo,)
    ).fetchone()


def todos_cnae_anexos(conn=None) -> dict:
    """Mapa {cnae: {"anexo": ..., "anexos": [...], "descricao": ...}}."""
    db = conn or get_db()
    mapa = {}
    for linha in db.execute(
        "SELECT cnae, descricao, anexo, anexos FROM cnae_anexos"
    ):
        try:
            anexos = json.loads(linha["anexos"] or "[]")
        except Exception:  # noqa: BLE001
            anexos = []
        mapa[linha["cnae"]] = {
            "descricao": linha["descricao"] or "",
            "anexo": linha["anexo"] or "",
            "anexos": anexos,
        }
    return mapa


def atualizar_cnae_anexo(registro_id, anexo, conn=None):
    """Corrige o anexo de um CNAE. Vale imediatamente para todo o sistema."""
    db = conn or get_db()
    expressao, anexos = normalizar_anexo_expressao(anexo)
    db.execute(
        """UPDATE cnae_anexos
           SET anexo=?, anexos=?, origem='humano', atualizado_em=?
           WHERE id=?""",
        (expressao, json.dumps(anexos, ensure_ascii=False),
         datetime.now().isoformat(timespec="seconds"), registro_id),
    )
    db.commit()


def adicionar_cnae_anexo(cnae, anexo, descricao="", conn=None) -> int:
    """Inclui (ou atualiza) a relação de um CNAE com o anexo."""
    db = conn or get_db()
    codigo = _normalizar_cnae(cnae)
    if len(codigo) != 7:
        raise ValueError("Informe o CNAE com 7 dígitos (ex.: 1813099).")
    expressao, anexos = normalizar_anexo_expressao(anexo)
    if not anexos:
        raise ValueError("Informe o anexo (ex.: II ou V/III).")
    agora = datetime.now().isoformat(timespec="seconds")
    db.execute(
        """INSERT INTO cnae_anexos
           (cnae, descricao, anexo, anexos, origem, atualizado_em)
           VALUES (?, ?, ?, ?, 'humano', ?)
           ON CONFLICT(cnae) DO UPDATE SET
               anexo=excluded.anexo, anexos=excluded.anexos,
               origem='humano', atualizado_em=excluded.atualizado_em""",
        (codigo, " ".join((descricao or "").split()), expressao,
         json.dumps(anexos, ensure_ascii=False), agora),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM cnae_anexos WHERE cnae=?", (codigo,)
    ).fetchone()[0]


def excluir_cnae_anexo(registro_id, conn=None):
    """Remove a linha: o CNAE volta a usar a regra fixa do motor."""
    db = conn or get_db()
    db.execute("DELETE FROM cnae_anexos WHERE id=?", (registro_id,))
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
