# Calculadora Simples Nacional 📊

Aplicação web local (Flask + SQLite) para calcular tributos do Simples
Nacional — alíquotas, repartição de tributos (IRPJ, CSLL, Cofins, PIS/Pasep,
CPP, ICMS, ISS, IPI), faixas e DAS, com suporte aos Anexos I a V.

## Funcionalidades

- ✅ **Dashboard** com visão consolidada de todos os anexos identificados
- ✅ **Repartição do imposto** — percentual e valor em R$ por tributo
- ✅ **Cadastro de empresas** com CNAE principal + secundários
- ✅ **Quadro CNAE · Descrição · Anexo** (informativo, só visual)
- ✅ **Consulta automática de CNPJ** via API da Receita Federal
- ✅ **Gestão de usuários** (admin / comum)
- ✅ **Tabelas de faixas** editáveis pelo administrador
- ✅ **Anexos I a V** com cálculos por faixa de faturamento
- ✅ **Autenticação** com sessão e senhas hash (PBKDF2)

## Tecnologias

- Python 3.13+
- Flask
- SQLite
- HTML + CSS + JavaScript (vanilla)

## Como executar

1. Acesse a pasta do projeto:
   ```
   cd simples_app
   ```

2. Ative o ambiente virtual:
   ```
   .\.venv\Scripts\activate
   ```

3. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

4. Execute:
   ```
   python app.py
   ```

5. Acesse [http://127.0.0.1:5000](http://127.0.0.1:5000)

> No primeiro start, o banco é criado automaticamente junto com o usuário
> administrador padrão. Altere a senha após o primeiro login.

## Estrutura do projeto

```
simples_app/
├── app.py              # Rotas, autenticação, endpoints
├── calc.py             # Motor de cálculo (RBT12, alíquotas, DAS, repartição)
├── cnaes.py            # Sugestão de anexo por CNAE
├── consulta_cnpj.py    # Integração com API da Receita Federal
├── database.py         # Modelo e persistência (SQLite)
├── templates/          # Jinja2 templates
├── static/             # CSS e assets
├── instance/           # Banco SQLite (ignorado pelo Git)
├── executar.bat        # Atalho para iniciar
└── requirements.txt    # Dependências Python
```
