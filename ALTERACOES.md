# Registro de alterações — Calculadora Simples Nacional

Data: 2026-09-18
Backup correspondente: `_backup/2026-09-18_2242/`

---

## Objetivo da sessão

Corrigir a repartição de tributos (percentual e valor em R$ por tributo) para
que os valores do sistema batam exatamente com a planilha
`CALCULADORA SIMPLES.xlsx`, e exibir essa repartição no dashboard.

---

## Diagnóstico inicial

A repartição apresentava divergências em relação à planilha. Foram levantadas
duas hipóteses de erro, investigadas uma a uma.

### Erro 1 — Base de cálculo dos valores em R$ (CONFIRMADO)

O código multiplicava o percentual dividido pelo **RBT12**:

```python
"valor": divididos.get(tributo, 0.0) * rbt12
```

A planilha multiplica pelo **faturamento do mês** (célula `F3`).

Evidência (Anexo IV): `M_IRPJ = 3.773,60` com `K = 0,0188680`.
`3.773,60 / 0,0188680 = 200.000` → exatamente o valor de `F3`, e não de `F2`
(RBT12 = 1.170.000).

**Correção:** trocar `rbt12` por `faturamento_mes` no cálculo do valor.

> Nota sobre consistência: a soma dos percentuais divididos é a própria
> alíquota efetiva (`J12`), e `DAS = F3 * J12`. Por isso a soma dos valores
> fecha exatamente no DAS.

### Erro 2 — Rótulo da faixa (FALSO ALARME)

A planilha exibe `"5ª Faixa"` em texto fixo, mas os parâmetros da faixa
(`F6 = 0,14` e `F9 = 39.780`) correspondem à **4ª faixa** do Anexo IV:

```python
(720000.01, 1800000.0, 0.140, 39780.0),   # 4ª faixa
```

Com `RBT12 = 1.170.000`, a faixa correta é mesmo a **4ª**. O rótulo da
planilha é texto digitado à mão e está desatualizado.

**Correção:** nenhuma no código — o cálculo já estava certo.

---

## Arquivos alterados

### `simples_app/calc.py`

1. `calcular_reparticao()` — assinatura atualizada e base de cálculo corrigida:

```python
def calcular_reparticao(anexo: str, faturamento_mes: float, aliquota_efetiva: float,
                        indice_faixa: Optional[int]) -> Optional[list]:
    ...
    base = faturamento_mes or 0.0
    return [
        {
            "tributo": tributo,
            "percentual": divididos.get(tributo, 0.0),
            "valor": divididos.get(tributo, 0.0) * base,
        }
        for tributo in tributos
    ]
```

2. Call site em `calcular()` — passou a enviar o faturamento do mês:

```python
reparticao_detalhada = calcular_reparticao(
    anexo, faturamento_f, aliquota_efetiva, indice_faixa
)
```

3. `formatar_percentual()` — ganhou o parâmetro `casas` (default 2). Sem isso,
   percentuais como `0,48273%` eram arredondados para `0,48%`, perdendo
   precisão na exibição da repartição:

```python
def formatar_percentual(valor, casas: int = 2) -> str:
    ...
    return f"{v * 100:.{casas}f}".replace(".", ",") + "%"
```

### `simples_app/templates/dashboard.html`

Adicionado o bloco "Repartição do imposto" abaixo dos cards de cada anexo,
iterando sobre `r.reparticao_detalhada` e exibindo tributo, percentual e valor.

### `simples_app/static/style.css`

Bloco CSS da repartição. Regras principais:

```css
.reparticao {
  grid-column: 1 / -1;   /* ocupa a linha inteira do card do anexo */
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--cinza-borda);
}

.reparticao-grid {
  display: flex;
  flex-wrap: nowrap;     /* nunca quebra linha */
  gap: 10px;
}

.reparticao-item {
  flex: 1 1 0;           /* larguras iguais, preenchendo a linha */
  min-width: 0;
}
```

Ajuste complementar no `.linha-anexo`: `align-items: center` → `align-items:
start`, com `align-self: center` aplicado só em `.identificacao`.

---

## Histórico de tentativas de layout

Vale registrar, porque a causa raiz não era óbvia:

1. **Primeira tentativa** — `grid-template-columns: repeat(auto-fit,
   minmax(104px, 1fr))`. Os cards quebravam em várias linhas.
2. **Segunda tentativa** — `grid-auto-flow: column` +
   `grid-auto-columns: minmax(0, 1fr)`. Ficaram na mesma linha, porém
   espremidos.
3. **Terceira tentativa** — `flex` com `flex: 1 1 0` e `gap: 10px`. Melhorou a
   distribuição, mas o usuário relatou que "não houve mudança".
4. **Causa raiz encontrada** — o `.reparticao` estava dentro da **2ª coluna**
   do grid do `.linha-anexo` (que é
   `minmax(190px, 1fr) minmax(0, 3fr)`), ou seja, limitado a ~75% da largura.
   Resolvido com `grid-column: 1 / -1`.

---

## Validação

Script `_validar_reparticao.py` compara o resultado de `calc.calcular()` com o
gabarito extraído da planilha (`RBT12 = 1.170.000`, 4ª faixa, 4 anexos).

Resultado: **TODAS PASSARAM** — percentuais e valores em R$ batem linha a linha,
e o TOTAL fecha exatamente no DAS de cada anexo.

```
ANEXO I   | faixa 4 | aliq.efetiva 0.0877692 | DAS 17553.85
ANEXO II  | faixa 4 | aliq.efetiva 0.0927692 | DAS  1855.38
ANEXO III | faixa 4 | aliq.efetiva 0.1295385 | DAS  2590.77
ANEXO IV  | faixa 4 | aliq.efetiva 0.1060000 | DAS 21200.00
RESULTADO: TODAS PASSARAM
```

Para reexecutar:

```powershell
cd "c:\Users\User\Documents\Guildahub plataforma\simples nacional"
.\simples_app\.venv\Scripts\python.exe _validar_reparticao.py
```

---

## Pendências e observações

- **Validação visual não concluída pelo assistente.** Não foi possível fazer
  login no sistema (`admin@admin.com / admin123` retorna credenciais
  inválidas — a senha do admin provavelmente já foi trocada), então a
  renderização da tela não foi conferida diretamente. A verificação foi feita
  no nível de dados (cálculo + gabarito) e por inspeção do CSS servido via
  `Invoke-WebRequest`.
- **Sem controle de versão.** O Git não está instalado na máquina
  (`git` não é reconhecido no PATH, e não foi encontrado em
  `Program Files`, `Program Files (x86)` nem `LOCALAPPDATA`). O backup foi
  feito por cópia manual de arquivos.
- **Sugestão:** instalar o Git para versionar o projeto de forma adequada.
- **Arquivos temporários** `_inspect.py` e `_validar_reparticao.py` ainda estão
  na raiz. O segundo é útil (validação); o primeiro pode ser removido.
