# MEMORIA.md — projeto Calculadora Simples Nacional

> **Leitura obrigatória para mim, Copilot, antes de mexer em qualquer coisa.**
> Complementa `.github/copilot-instructions.md` (proibições, regras de negócio,
> cicatrizes) e `.github/REGRAS.md` (regras dadas pelo usuário, com data).
>
> **Nada aqui foi inventado.** Cada bloco diz de onde veio: `[código]`,
> `[README]`, `[ALTERACOES.md]` ou `[usuário]`. O que não tem fonte está na
> seção 7 como dúvida em aberto.

Última revisão: 2026-10-17

---

## 1. O que é o sistema

Calculadora de tributos do Simples Nacional. Aplicação web **local**, Flask +
SQLite, sem nuvem. Reproduz as fórmulas da planilha
`CALCULADORA SIMPLES.xlsx`, que é a **fonte da verdade** do cálculo. `[README]`

Caminho raiz:
`C:\Users\User\Documents\Guildahub plataforma\simples nacional`

---

## 2. Como rodar

```powershell
cd "C:\Users\User\Documents\Guildahub plataforma\simples nacional\simples_app"
.\.venv\Scripts\activate
python app.py
```

Depois abrir `http://127.0.0.1:5000`. `[README]`

Dependências: apenas `Flask>=3.0,<4.0` e `requests>=2.31,<3.0`.
Python 3.13+. `[requirements.txt][README]`

Atalho pronto: `simples_app\executar.bat`. `[código]`

> O terminal do usuário é **PowerShell 5.1**. Não existe `&&`.
> Encadear com `;` ou `comando1; if ($?) { comando2 }`.

---

## 3. Mapa dos arquivos — o que cada um faz

Tamanhos medidos em 2026-10-17 (linhas). Servem para eu saber onde procurar.

| Arquivo | Linhas | Papel |
|---|---:|---|
| `simples_app/app.py` | 1608 | Tudo do Flask: `create_app()`, rotas, autenticação, importação, relatórios |
| `simples_app/explicacoes.py` | 1140 | Textos de explicação apresentados ao usuário |
| `simples_app/enquadramento_db.py` | 735 | **Motor de enquadramento CNAE → item LC 116** + banco de conhecimento |
| `simples_app/calc.py` | 514 | **Motor de cálculo**: RBT12, faixas, alíquota efetiva, DAS, repartição |
| `simples_app/itens_lc116.py` | 474 | Os 200 itens da LC 116/2003 (`ITENS_LC116`, `ITENS_VETADOS`) |
| `simples_app/database.py` | 460 | Persistência SQLite (usuários, empresas) |
| `simples_app/enquadramento.py` | 397 | Motor antigo de enquadramento (o novo é `enquadramento_db.py`) |
| `simples_app/xml_import.py` | 275 | Leitura de XML |
| `simples_app/extrato_simples.py` | 217 | Leitura do extrato do Simples |
| `simples_app/consulta_cnpj.py` | 177 | API da Receita Federal |
| `simples_app/cnaes.py` | 153 | Sugestão de anexo por CNAE |

Todos verificados por leitura do código em 2026-10-17.

### 3.1 `calc.py` — convenções da planilha `[código]`

O docstring do módulo mapeia célula a variável. **Isso é contrato:**

| Célula | Variável |
|---|---|
| F2 | `rbt12` |
| F3 | `faturamento_mes` |
| F6 | `aliquota_nominal` |
| F9 | `valor_deduzir` |
| J12 | `aliquota_efetiva` |
| F15 | `das` |

```
J12 = ((F2 * F6) - F9) / F2
F15 = F3 * J12
```

`FAIXAS` é um dicionário por anexo (`I` a `V`), cada faixa sendo
`(limite_inferior, limite_superior, aliquota_nominal, valor_a_deduzir)`.

**Regra de ouro vinda de `ALTERACOES.md`:** o valor em R$ de cada tributo é
`percentual × faturamento_mes` (F3), **nunca** `× rbt12` (F2). Isso já foi
erro corrigido com evidência numérica — `3.773,60 / 0,0188680 = 200.000 = F3`.

### 3.2 `enquadramento_db.py` — o que eu preciso lembrar

Funções reais (nomes conferidos no arquivo):

```
_sem_acento   _digitos   hash_frase
_tokens   _tokens_brutos   _stem   _radicais   _radicais_nucleo   _objeto
_tokens_iniciais   _abre_com   _texto_e_nao_servico
_especificidade_legal   comparar_frases   comparar_item
vazias_lista_lc116
class Conhecimento
```

Arquitetura: o módulo **não decide** — registra catálogo de CNAE, decisões
(origem, item casado, score) e correções humanas, que têm precedência.
Banco separado em `instance/enquadramento.db`, para não conflitar com o
`simples.db` de usuários e empresas. `[docstring do módulo]`

Fluxo de uso, segundo o próprio docstring:

```python
kb = Conhecimento()
kb.init()
kb.registrar_cnae("7112000", "Serviços de engenharia")
item, score, motivo = kb.casar_lc116("serviços de engenharia e projeto")
kb.registrar_decisao(...)
```

---

## 4. Rotas de `app.py` `[código]`

Levantadas lendo os decorators. É o mapa para eu não me perder no arquivo.

| Rota | Função | Observação |
|---|---|---|
| `/` | `index` | |
| `/login`, `/logout` | `login`, `logout` | |
| `/dashboard` | `dashboard` | |
| `/anexo/<anexo>` | `anexo_view` | GET e POST |
| `/api/calcular` | `api_calcular` | POST |
| `/admin` | `admin` | |
| `/admin/usuario/novo`, `/editar`, `/excluir` | gestão de usuários | |
| `/admin/tabelas` | `admin_tabelas` | faixas editáveis |
| `/admin/logs` | `admin_logs` | |
| `/empresas`, `/empresa/nova`, `/editar`, `/excluir`, `/selecionar` | CRUD de empresas | |
| `/importar-xml` + `/api/xml/analisar`, `/api/xml/aplicar` | importação XML | |
| `/api/extrato/analisar`, `/api/extrato/aplicar` | extrato do Simples | |
| `/relatorios`, `/relatorios/excel`, `/relatorios/pdf` | relatórios | |
| `/api/cnae/sugerir`, `/api/cnae/quadro`, `/api/cnae/explicar` | enquadramento | |
| `/api/cnpj/<cnpj>` | `api_consulta_cnpj` | Receita Federal |

Decorators de controle: `login_required`, `admin_required`, `permissao_required`.

---

## 5. Bancos de dados `[código]`

| Banco | Onde | Conteúdo |
|---|---|---|
| `simples.db` | `simples_app/instance/` | usuários, empresas |
| `enquadramento.db` | `simples_app/instance/` | catálogo CNAE, decisões, correções humanas |

`instance/` está fora do Git. Recriar ao subir do zero. `[README][.gitignore]`

---

## 6. Como o usuário quer que eu trabalhe

Isto está detalhado em `.github/copilot-instructions.md` (seções 1 a 4).
Resumo do que não pode escapar:

1. **Não inventar nada.** Sem fonte, é "não sei".
2. **Consultar antes de perguntar.**
3. **Gravar a regra na hora** em que ela for dita.
4. **Diagnóstico antes de editar** o motor de enquadramento.
5. **Apagar `__pycache__`** antes de verificar, sempre.
6. **Critério de aceite do enquadramento:** `Falhas: 0` e
   `Itens da LC 116 bloqueados: 0 de 200`.
7. **Não declarar "validado"** sem ter rodado a verificação.
8. **Não mexer em `calc.py` para "fazer bater"** com a planilha.

Comandos de verificação e armadilhas: seções 4.2 e 4.4 do
`copilot-instructions.md`.

---

## 7. O que eu ainda NÃO sei — não supor

Nada abaixo foi confirmado. Se precisar de qualquer um destes, **perguntar**.

- [ ] Se a **tabela `cnae`** está realmente vazia hoje. A nota antiga dizia
      "0 registros", mas não reconferi nesta sessão.
- [ ] Qual motor o `app.py` usa de fato hoje: `enquadramento.py`,
      `enquadramento_db.py` ou os dois.
- [ ] Regras de cálculo próprias que o usuário tenha decidido e não estejam
      registradas em lugar nenhum que eu tenha lido.
- [ ] Se `explicacoes.py` (1140 linhas, o segundo maior arquivo) tem regra de
      negócio embutida ou é só texto.
- [ ] Onde ficam `templates/` e `static/` de fato e quais telas existem —
      não abri nesta sessão.
- [ ] Se existe regra de negócio que o usuário disse e que se perdeu com a
      conversa anterior apagada.

**Como fechar uma dúvida:** perguntar ao usuário, depois mover a resposta para
a seção certa e marcar a caixa. Nunca riscar sem resposta.
