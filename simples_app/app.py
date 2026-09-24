"""
Calculadora do Simples Nacional — aplicação web local (Flask + SQLite).

Execução:
    python app.py
Depois acesse http://127.0.0.1:5000

Usuário administrador padrão criado no primeiro start:
    e-mail: admin@admin.com
    senha:  admin123
"""

from __future__ import annotations

import os
from functools import wraps

from flask import (
    Flask, flash, g, jsonify, redirect, render_template,
    request, session, url_for,
)

import calc
import cnaes
import consulta_cnpj
import database as db

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ANEXOS_VALIDOS = ["I", "II", "III", "IV"]
# Todos os anexos possíveis do Simples Nacional (inclusive o V).
ANEXOS_TODOS = ["I", "II", "III", "IV", "V"]

ANO_REFERENCIA = "2026"
SIMPLES_EMPRESA = "Minha Empresa LTDA"
CNPJ_EMPRESA = "00.000.000/0001-00"


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SIMPLES_SECRET", "troque-esta-chave-em-producao"),
        DATABASE=os.path.join(APP_DIR, "instance", "simples.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    os.makedirs(os.path.join(APP_DIR, "instance"), exist_ok=True)

    app.teardown_appcontext(db.close_db)
    app.jinja_env.globals.update(
        formatar_moeda=calc.formatar_moeda,
        formatar_percentual=calc.formatar_percentual,
        ANO_REFERENCIA=ANO_REFERENCIA,
        SIMPLES_EMPRESA=SIMPLES_EMPRESA,
        CNPJ_EMPRESA=CNPJ_EMPRESA,
        empresa_ativa=empresa_ativa,
        sugerir_anexo=cnaes.sugerir_anexo,
        formatar_cnae=cnaes.formatar_cnae,
    )
    # Disponibiliza também como filtros Jinja: {{ valor | formatar_moeda }}
    app.jinja_env.filters["formatar_moeda"] = calc.formatar_moeda
    app.jinja_env.filters["formatar_percentual"] = calc.formatar_percentual

    registrar_rotas(app)

    @app.context_processor
    def _injetar_usuario():
        """Deixa o usuário logado (e o flag is_admin) disponível em todo template."""
        usuario = g.get("usuario")
        admin = bool(usuario and usuario["is_admin"])

        # Menu: administrador enxerga todos os anexos; o usuário comum enxerga
        # apenas os anexos identificados no cadastro da sua empresa.
        if admin or not usuario:
            anexos_menu = list(ANEXOS_TODOS)
        else:
            anexos_menu = anexos_identificados(empresa_ativa())

        return {
            "usuario_logado": usuario,
            "is_admin": admin,
            "anexos_menu": anexos_menu,
        }

    return app


# ---------------------------------------------------------------------------
# Helpers de autenticação / autorização
# ---------------------------------------------------------------------------

def usuario_atual():
    uid = session.get("usuario_id")
    if not uid:
        return None
    return db.buscar_usuario_por_id(uid)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = usuario_atual()
        if user is None or not user["ativo"]:
            session.clear()
            flash("Faça login para continuar.", "aviso")
            return redirect(url_for("login"))
        g.usuario = user
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not g.usuario["is_admin"]:
            flash("Acesso restrito ao administrador.", "erro")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


def _ler_form_empresa() -> dict:
    """Lê os campos do formulário de empresa e devolve um dicionário pronto."""
    return {
        "razao_social": request.form.get("razao_social", "").strip(),
        "nome_fantasia": request.form.get("nome_fantasia", "").strip(),
        "cnpj": consulta_cnpj.formatar_cnpj(request.form.get("cnpj", "")),
        "cnae_principal": cnaes.formatar_cnae(request.form.get("cnae_principal", "")),
        "cnae_descricao": request.form.get("cnae_descricao", "").strip(),
        "cnaes_secundarios": request.form.get("cnaes_secundarios", "").strip(),
        "anexo_sugerido": request.form.get("anexo_sugerido", "").strip(),
        "anexo_confirmado": request.form.get("anexo_confirmado", "").strip(),
        "municipio": request.form.get("municipio", "").strip(),
        "uf": request.form.get("uf", "").strip(),
        "observacoes": request.form.get("observacoes", "").strip(),
    }


def empresa_ativa():
    """Empresa selecionada pelo usuário logado (quando houver)."""
    user = usuario_atual()
    if not user:
        return None
    empresa_id = user["empresa_id"] if "empresa_id" in user.keys() else None
    if not empresa_id:
        return None
    return db.buscar_empresa_por_id(empresa_id)


def anexos_identificados(empresa) -> list:
    """
    Anexos efetivamente identificados para a empresa.

    Leva em conta o anexo confirmado e o sugerido pelo CNAE principal,
    além dos CNAEs secundários (um deles pode apontar outro anexo).
    """
    if not empresa:
        return []

    encontrados = []
    for candidato in (empresa["anexo_confirmado"], empresa["anexo_sugerido"]):
        codigo = (candidato or "").strip().upper()
        if codigo in ANEXOS_TODOS and codigo not in encontrados:
            encontrados.append(codigo)

    for linha in _linhas_cnae_empresa(empresa):
        codigo = (linha.get("anexo") or "").strip().upper()
        if codigo in ANEXOS_TODOS and codigo not in encontrados:
            encontrados.append(codigo)

    return [a for a in ANEXOS_TODOS if a in encontrados]


def _linhas_cnae_empresa(empresa) -> list:
    """
    Relação (código, descrição, anexo) dos CNAEs principal e secundários.

    Usada tanto pelo endpoint do quadro informativo quanto pelo cálculo dos
    anexos identificados da empresa.
    """
    if not empresa:
        return []

    linhas = []

    principal = (empresa["cnae_principal"] or "").strip()
    if principal:
        sugestao = cnaes.sugerir_anexo(principal, empresa["cnae_descricao"] or "")
        linhas.append({
            "codigo": principal,
            "descricao": empresa["cnae_descricao"] or "",
            "escopo": "principal",
            "anexo": sugestao.get("anexo"),
            "descricao_grupo": sugestao.get("descricao_grupo", ""),
            "observacao": sugestao.get("observacao", ""),
            "confianca": sugestao.get("confianca", ""),
        })

    for bruto in (empresa["cnaes_secundarios"] or "").splitlines():
        bruto = bruto.strip()
        if not bruto:
            continue
        codigo = cnaes.formatar_cnae(bruto)
        # A linha pode vir como "1234-5/67 Descrição do CNAE".
        descricao = bruto
        if codigo and bruto.startswith(codigo):
            descricao = bruto[len(codigo):].strip(" -–—\t")
        sugestao = cnaes.sugerir_anexo(codigo or bruto, descricao)
        linhas.append({
            "codigo": codigo or bruto,
            "descricao": descricao,
            "escopo": "secundario",
            "anexo": sugestao.get("anexo"),
            "descricao_grupo": sugestao.get("descricao_grupo", ""),
            "observacao": sugestao.get("observacao", ""),
            "confianca": sugestao.get("confianca", ""),
        })

    return linhas


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

def registrar_rotas(app: Flask):

    @app.route("/")
    def index():
        if usuario_atual():
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    # ------------------------------ Autenticação ------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "")
            senha = request.form.get("senha", "")
            user = db.buscar_usuario_por_email(email)
            if user and user["ativo"] and db.verificar_senha(senha, user["senha_hash"], user["sal"]):
                session.clear()
                session["usuario_id"] = user["id"]
                db.registrar_log(user, "login", f"{user['email']}")
                return redirect(url_for("dashboard"))
            flash("E-mail ou senha inválidos, ou usuário inativo.", "erro")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        user = usuario_atual()
        if user:
            db.registrar_log(user, "logout", "")
        session.clear()
        flash("Sessão encerrada.", "ok")
        return redirect(url_for("login"))

    # ------------------------------ Dashboard --------------------------------

    @app.route("/dashboard")
    @login_required
    def dashboard():
        usuario = g.usuario
        resumos = []
        if usuario["is_admin"]:
            id_alvo = request.args.get("usuario_id", type=int) or usuario["id"]
        else:
            id_alvo = usuario["id"]

        alvo = db.buscar_usuario_por_id(id_alvo) or usuario

        # Usuário comum só enxerga os anexos identificados na própria empresa.
        # O administrador continua vendo todos (ele acompanha qualquer usuário).
        exibir_todos = bool(usuario["is_admin"])
        if exibir_todos:
            anexos_dashboard = list(ANEXOS_TODOS)
        elif id_alvo == usuario["id"]:
            anexos_dashboard = anexos_identificados(empresa_ativa())
        else:
            anexos_dashboard = []

        for anexo in anexos_dashboard:
            row = db.obter_ou_criar_anexo(alvo["id"], anexo)
            valores = db.obter_faturamentos(row["id"])
            rbt12 = calc.calcular_rbt12(valores)
            fat_mes = row["faturamento_mes"] or 0
            resultado = calc.calcular(anexo, rbt12, fat_mes)
            resumos.append(resultado)

        total_das = sum(r["das"] for r in resumos)
        total_fat_mes = sum(r["faturamento_mes"] for r in resumos)
        max_rbt12 = max((r["rbt12"] for r in resumos), default=0)

        usuarios = db.listar_usuarios() if usuario["is_admin"] else []
        filtros = {a: [r for r in resumos if r["anexo"] == a] for a in anexos_dashboard}

        return render_template(
            "dashboard.html",
            resumos=resumos,
            filtros=filtros,
            total_das=total_das,
            total_fat_mes=total_fat_mes,
            max_rbt12=max_rbt12,
            usuarios=usuarios,
            alvo=alvo,
            anexos=anexos_dashboard,
            sem_anexo=not anexos_dashboard,
        )

    # ------------------------------ Anexos -----------------------------------

    @app.route("/anexo/<anexo>", methods=["GET", "POST"])
    @login_required
    def anexo_view(anexo):
        anexo = anexo.upper()
        if anexo not in ANEXOS_VALIDOS:
            flash("Anexo inválido.", "erro")
            return redirect(url_for("dashboard"))

        usuario = g.usuario
        if usuario["is_admin"]:
            id_alvo = request.args.get("usuario_id", type=int) or usuario["id"]
        else:
            id_alvo = usuario["id"]
        alvo = db.buscar_usuario_por_id(id_alvo) or usuario

        # Usuário comum só acessa anexos identificados na própria empresa.
        if not usuario["is_admin"] and anexo not in anexos_identificados(empresa_ativa()):
            flash("Este anexo não está identificado no cadastro da sua empresa.", "aviso")
            return redirect(url_for("dashboard"))

        row = db.obter_ou_criar_anexo(alvo["id"], anexo)

        if request.method == "POST":
            try:
                for i in range(1, 13):
                    campo = f"mes_{i}"
                    if campo in request.form:
                        db.salvar_faturamento_mes(row["id"], i, request.form.get(campo, "").strip())

                valores = db.obter_faturamentos(row["id"])
                rbt12 = calc.calcular_rbt12(valores)
                fat_mes = request.form.get("faturamento_mes", "").strip()
                db.salvar_dados_anexo(row["id"], rbt12=f"{rbt12:.2f}", faturamento_mes=fat_mes)
                db.registrar_log(usuario, "editar_anexo", f"Anexo {anexo} — {alvo['nome']}")
                flash("Dados salvos com sucesso.", "ok")
            except Exception as exc:  # noqa: BLE001
                flash(f"Erro ao salvar: {exc}", "erro")
            return redirect(url_for("anexo_view", anexo=anexo, usuario_id=id_alvo))

        valores = db.obter_faturamentos(row["id"])
        rbt12 = calc.calcular_rbt12(valores)
        fat_mes = row["faturamento_mes"] or ""
        resultado = calc.calcular(anexo, rbt12, fat_mes)
        faixas = db.listar_tabelas_base(anexo)

        return render_template(
            "anexo.html",
            anexo=anexo,
            meses=calc.MESES,
            valores=valores,
            resultado=resultado,
            faixas=faixas,
            alvo=alvo,
        )

    # ----------------------- Cálculo dinâmico (AJAX) --------------------------

    @app.route("/api/calcular", methods=["POST"])
    @login_required
    def api_calcular():
        dados = request.get_json(silent=True) or {}
        anexo = (dados.get("anexo") or "I").upper()
        valores = dados.get("faturamentos") or []
        fat_mes = dados.get("faturamento_mes") or 0

        if anexo not in ANEXOS_VALIDOS:
            return jsonify({"erro": "Anexo inválido"}), 400

        rbt12 = calc.calcular_rbt12(valores)
        resultado = calc.calcular(anexo, rbt12, fat_mes)
        return jsonify({
            "rbt12": resultado["rbt12"],
            "rbt12_fmt": calc.formatar_moeda(resultado["rbt12"]),
            "faturamento_mes": resultado["faturamento_mes"],
            "faturamento_mes_fmt": calc.formatar_moeda(resultado["faturamento_mes"]),
            "aliquota_nominal": resultado["aliquota_nominal"],
            "aliquota_nominal_fmt": calc.formatar_percentual(resultado["aliquota_nominal"]),
            "valor_deduzir": resultado["valor_deduzir"],
            "valor_deduzir_fmt": calc.formatar_moeda(resultado["valor_deduzir"]),
            "aliquota_efetiva": resultado["aliquota_efetiva"],
            "aliquota_efetiva_fmt": calc.formatar_percentual(resultado["aliquota_efetiva"]),
            "das": resultado["das"],
            "das_fmt": calc.formatar_moeda(resultado["das"]),
            "faixa": resultado["faixa"],
        })

    # ---------------------- Administração: usuários --------------------------

    @app.route("/admin")
    @admin_required
    def admin():
        return render_template("admin.html", usuarios=db.listar_usuarios())

    @app.route("/admin/usuario/novo", methods=["GET", "POST"])
    @admin_required
    def admin_usuario_novo():
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            email = request.form.get("email", "").strip()
            senha = request.form.get("senha", "")
            is_admin = request.form.get("is_admin") == "on"
            ativo = request.form.get("ativo") == "on"
            if not nome or not email or not senha:
                flash("Nome, e-mail e senha são obrigatórios.", "erro")
            elif db.buscar_usuario_por_email(email):
                flash("Já existe um usuário com este e-mail.", "erro")
            else:
                novo_id = db.criar_usuario(nome, email, senha, is_admin=is_admin, ativo=ativo)
                empresa_id = request.form.get("empresa_id", type=int)
                if empresa_id:
                    db.definir_empresa_usuario(novo_id, empresa_id)
                db.registrar_log(g.usuario, "criar_usuario", f"{nome} <{email}>")
                flash("Usuário cadastrado com sucesso.", "ok")
                return redirect(url_for("admin"))
        return render_template("usuario_form.html", usuario=None, empresas=db.listar_empresas())

    @app.route("/admin/usuario/<int:user_id>/editar", methods=["GET", "POST"])
    @admin_required
    def admin_usuario_editar(user_id):
        usuario = db.buscar_usuario_por_id(user_id)
        if not usuario:
            flash("Usuário não encontrado.", "erro")
            return redirect(url_for("admin"))
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            email = request.form.get("email", "").strip()
            senha = request.form.get("senha", "")
            is_admin = request.form.get("is_admin") == "on"
            ativo = request.form.get("ativo") == "on"
            existente = db.buscar_usuario_por_email(email)
            if not nome or not email:
                flash("Nome e e-mail são obrigatórios.", "erro")
            elif existente and existente["id"] != user_id:
                flash("Já existe outro usuário com este e-mail.", "erro")
            else:
                db.atualizar_usuario(user_id, nome, email, senha=senha or None,
                                     is_admin=is_admin, ativo=ativo)
                empresa_id = request.form.get("empresa_id", type=int)
                db.definir_empresa_usuario(user_id, empresa_id)
                db.registrar_log(g.usuario, "editar_usuario", f"{nome} <{email}>")
                flash("Usuário atualizado.", "ok")
                return redirect(url_for("admin"))
        return render_template("usuario_form.html", usuario=usuario, empresas=db.listar_empresas())

    @app.route("/admin/usuario/<int:user_id>/excluir", methods=["POST"])
    @admin_required
    def admin_usuario_excluir(user_id):
        if user_id == g.usuario["id"]:
            flash("Você não pode excluir o próprio usuário.", "erro")
            return redirect(url_for("admin"))
        alvo = db.buscar_usuario_por_id(user_id)
        db.excluir_usuario(user_id)
        db.registrar_log(g.usuario, "excluir_usuario", alvo["email"] if alvo else str(user_id))
        flash("Usuário excluído.", "ok")
        return redirect(url_for("admin"))

    # ---------------------------- Empresas -----------------------------------

    @app.route("/empresas")
    @login_required
    def empresas():
        usuario = g.usuario
        if usuario["is_admin"]:
            lista = db.listar_empresas()
        else:
            lista = db.listar_empresas(usuario_id=usuario["id"])
        return render_template("empresas.html", empresas=lista, grupos=cnaes.listar_grupos())

    @app.route("/empresa/nova", methods=["GET", "POST"])
    @login_required
    def empresa_nova():
        if request.method == "POST":
            dados = _ler_form_empresa()
            if not dados["razao_social"]:
                flash("A razão social é obrigatória.", "erro")
            else:
                empresa_id = db.criar_empresa(g.usuario["id"], **dados)
                db.registrar_log(g.usuario, "criar_empresa", dados["razao_social"])
                flash("Empresa cadastrada com sucesso.", "ok")
                return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        return render_template(
            "empresa_form.html",
            empresa=None,
            acao="nova",
            grupos=cnaes.listar_grupos(),
            anexos_simples=cnaes.ANEXOS_SIMPLES,
        )

    @app.route("/empresa/<int:empresa_id>/editar", methods=["GET", "POST"])
    @login_required
    def empresa_editar(empresa_id):
        empresa = db.buscar_empresa_por_id(empresa_id)
        if not empresa:
            flash("Empresa não encontrada.", "erro")
            return redirect(url_for("empresas"))
        if not g.usuario["is_admin"] and empresa["usuario_id"] != g.usuario["id"]:
            flash("Você não tem acesso a esta empresa.", "erro")
            return redirect(url_for("empresas"))

        if request.method == "POST":
            dados = _ler_form_empresa()
            if not dados["razao_social"]:
                flash("A razão social é obrigatória.", "erro")
            else:
                db.atualizar_empresa(empresa_id, **dados)
                db.registrar_log(g.usuario, "editar_empresa", dados["razao_social"])
                flash("Empresa atualizada com sucesso.", "ok")
                return redirect(url_for("empresa_editar", empresa_id=empresa_id))

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            acao="editar",
            grupos=cnaes.listar_grupos(),
            anexos_simples=cnaes.ANEXOS_SIMPLES,
        )

    @app.route("/empresa/<int:empresa_id>/excluir", methods=["POST"])
    @login_required
    def empresa_excluir(empresa_id):
        empresa = db.buscar_empresa_por_id(empresa_id)
        if not empresa:
            flash("Empresa não encontrada.", "erro")
            return redirect(url_for("empresas"))
        if not g.usuario["is_admin"] and empresa["usuario_id"] != g.usuario["id"]:
            flash("Você não tem acesso a esta empresa.", "erro")
            return redirect(url_for("empresas"))
        db.excluir_empresa(empresa_id)
        db.registrar_log(g.usuario, "excluir_empresa", empresa["razao_social"])
        flash("Empresa excluída.", "ok")
        return redirect(url_for("empresas"))

    @app.route("/empresa/<int:empresa_id>/selecionar", methods=["POST"])
    @login_required
    def empresa_selecionar(empresa_id):
        empresa = db.buscar_empresa_por_id(empresa_id)
        if not empresa:
            flash("Empresa não encontrada.", "erro")
            return redirect(url_for("empresas"))
        if not g.usuario["is_admin"] and empresa["usuario_id"] != g.usuario["id"]:
            flash("Você não tem acesso a esta empresa.", "erro")
            return redirect(url_for("empresas"))
        db.definir_empresa_usuario(g.usuario["id"], empresa_id)
        db.registrar_log(g.usuario, "selecionar_empresa", empresa["razao_social"])
        flash(f"Empresa ativa: {empresa['razao_social']}.", "ok")
        return redirect(url_for("dashboard"))

    # ------------------- CNAE: sugestão de anexo (AJAX) ----------------------

    @app.route("/api/cnae/sugerir", methods=["POST"])
    @login_required
    def api_cnae_sugerir():
        dados = request.get_json(silent=True) or {}
        cnae = dados.get("cnae") or ""
        descricao = dados.get("descricao") or ""
        resultado = cnaes.sugerir_anexo(cnae, descricao)
        resultado["cnae_fmt"] = cnaes.formatar_cnae(cnae)
        return jsonify(resultado)

    @app.route("/api/cnae/quadro", methods=["POST"])
    @login_required
    def api_cnae_quadro():
        """
        Monta o quadro CNAE · Descrição · Anexo para exibição no formulário.

        Recebe o CNAE principal + descrição e o texto livre dos secundários
        (uma linha por CNAE) e devolve uma lista já com o anexo sugerido de
        cada linha. Nada é persistido — o quadro é apenas informativo.
        """
        dados = request.get_json(silent=True) or {}
        linhas = []

        principal = (dados.get("cnae_principal") or "").strip()
        desc_principal = (dados.get("cnae_descricao") or "").strip()

        if principal or desc_principal:
            sug = cnaes.sugerir_anexo(principal, desc_principal)
            linhas.append({
                "escopo": "principal",
                "codigo": cnaes.formatar_cnae(principal),
                "descricao": desc_principal,
                "anexo": sug["anexo"],
                "descricao_grupo": sug.get("descricao_grupo", ""),
                "confianca": sug.get("confianca", ""),
            })

        for linha in (dados.get("cnaes_secundarios") or "").splitlines():
            linha = linha.strip()
            if not linha:
                continue

            # Separa o CNAE (primeiro bloco com dígitos) do restante (descrição).
            partes = linha.split(None, 1)
            codigo = partes[0] if partes else ""
            descricao = partes[1].strip() if len(partes) > 1 else ""

            if not cnaes.apenas_digitos(codigo):
                # Linha sem CNAE: tenta enquadrar apenas pela descrição.
                codigo, descricao = "", linha

            sug = cnaes.sugerir_anexo(codigo, descricao)
            linhas.append({
                "escopo": "secundario",
                "codigo": cnaes.formatar_cnae(codigo),
                "descricao": descricao,
                "anexo": sug["anexo"],
                "descricao_grupo": sug.get("descricao_grupo", ""),
                "confianca": sug.get("confianca", ""),
            })

        return jsonify({"linhas": linhas})

    # ------------------- CNPJ: consulta na Receita (AJAX) --------------------

    @app.route("/api/cnpj/<cnpj>")
    @login_required
    def api_consulta_cnpj(cnpj):
        try:
            dados = consulta_cnpj.consultar_cnpj(cnpj)
        except consulta_cnpj.ConsultaCNPJError as exc:
            return jsonify({"erro": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"erro": f"Falha na consulta: {exc}"}), 500

        # Enquadramento: usa o CNAE principal e as descrições como reforço.
        texto = " ".join(
            [dados["cnae_descricao"]]
            + [item["descricao"] for item in dados["cnaes_secundarios"][:5]]
        )
        dados["sugestao_anexo"] = cnaes.sugerir_anexo(dados["cnae_principal"], texto)

        # Formata os CNAEs secundários para exibição no textarea.
        dados["cnaes_secundarios_texto"] = "\n".join(
            f"{cnaes.formatar_cnae(item['codigo'])} {item['descricao']}".strip()
            for item in dados["cnaes_secundarios"]
        )
        dados["cnae_principal_fmt"] = cnaes.formatar_cnae(dados["cnae_principal"])

        # Anexo sugerido para cada CNAE secundário (sempre automático; o quadro
        # no formulário apenas apresenta o resultado, sem persistir).
        dados["cnaes_secundarios_analise"] = [
            {
                "codigo": cnaes.formatar_cnae(item["codigo"]),
                "codigo_digitos": item["codigo"],
                "descricao": item["descricao"],
                "anexo": cnaes.sugerir_anexo(item["codigo"], item["descricao"])["anexo"],
            }
            for item in dados["cnaes_secundarios"]
        ]

        db.registrar_log(g.usuario, "consultar_cnpj", dados["cnpj"])
        return jsonify(dados)

    # ---------------------- Administração: tabelas base -----------------------

    @app.route("/admin/tabelas", methods=["GET", "POST"])
    @admin_required
    def admin_tabelas():
        if request.method == "POST":
            try:
                for key, valor in request.form.items():
                    if key.startswith("id_"):
                        tabela_id = int(key[3:])
                        db.atualizar_tabela_base(
                            tabela_id,
                            request.form.get(f"inf_{tabela_id}", ""),
                            request.form.get(f"sup_{tabela_id}", ""),
                            request.form.get(f"aliq_{tabela_id}", ""),
                            request.form.get(f"ded_{tabela_id}", ""),
                        )
                db.registrar_log(g.usuario, "editar_tabela_base", "Tabelas de faixas")
                flash("Tabelas base atualizadas com sucesso.", "ok")
            except Exception as exc:  # noqa: BLE001
                flash(f"Erro ao atualizar: {exc}", "erro")
            return redirect(url_for("admin_tabelas"))

        tabelas = {a: db.listar_tabelas_base(a) for a in ANEXOS_VALIDOS}
        return render_template("admin_tabelas.html", tabelas=tabelas, anexos=ANEXOS_VALIDOS)

    # ------------------------------ Logs -------------------------------------

    @app.route("/admin/logs")
    @admin_required
    def admin_logs():
        return render_template("logs.html", logs=db.listar_logs(200))

    # ---------------------------- Erros --------------------------------------

    @app.errorhandler(404)
    def nao_encontrado(e):
        return render_template("erro.html", codigo=404,
                               mensagem="Página não encontrada."), 404

    @app.errorhandler(500)
    def erro_interno(e):
        return render_template("erro.html", codigo=500,
                               mensagem="Erro interno do servidor."), 500


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------

def bootstrap():
    """Garante o schema e o usuário administrador padrão."""
    with app.app_context():
        db.init_db()
        if not db.buscar_usuario_por_email("admin@admin.com"):
            db.criar_usuario("Administrador", "admin@admin.com", "admin123", is_admin=True)
            print("[setup] Usuário admin criado -> admin@admin.com / admin123")


app = create_app()


if __name__ == "__main__":
    bootstrap()
    app.run(host="127.0.0.1", port=5000, debug=True)
