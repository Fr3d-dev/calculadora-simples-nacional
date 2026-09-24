"""Teste rápido do motor de cálculo (executar: python teste_calc.py)."""

import calc

# Cenário 1: RBT12 de 240.000 no Anexo I -> 2ª faixa (7,3%, deduzir 5.940)
res = calc.calcular("I", 240000, 20000)
print("Cenário 1 — Anexo I, RBT12 240.000, faturamento 20.000")
print(f"  Faixa:            {res['faixa']}ª")
print(f"  Alíquota nominal: {calc.formatar_percentual(res['aliquota_nominal'])}")
print(f"  Valor a deduzir:  {calc.formatar_moeda(res['valor_deduzir'])}")
print(f"  Alíquota efetiva: {calc.formatar_percentual(res['aliquota_efetiva'])}")
print(f"  DAS:              {calc.formatar_moeda(res['das'])}")
# Esperado: (240000*0.073 - 5940)/240000 = (17520-5940)/240000 = 0.048250 -> 4,8250%
# DAS = 20000 * 0.048250 = 965.00
assert abs(res["aliquota_efetiva"] - 0.04825) < 1e-9, res["aliquota_efetiva"]
assert abs(res["das"] - 965.00) < 1e-9, res["das"]

# Cenário 2: RBT12 médio a partir de 12 meses (planilha: C15 = 12*SOMA/CONT)
valores = [10000, 10000, 10000, 10000, 10000, 10000,
           20000, 20000, 20000, 20000, 20000, 20000]
rbt12 = calc.calcular_rbt12(valores)
print("\nCenário 2 — média dos 12 meses")
print(f"  RBT12 calculado:  {calc.formatar_moeda(rbt12)}")
# Soma = 180000; (12*180000)/12 = 180000
assert abs(rbt12 - 180000) < 1e-9, rbt12

# Cenário 3: apenas 6 meses preenchidos (média proporcional)
rbt12_b = calc.calcular_rbt12([10000, 10000, 10000, 10000, 10000, 10000, "", "", "", "", "", ""])
print("\nCenário 3 — apenas 6 meses preenchidos (10.000 cada)")
print(f"  RBT12 calculado:  {calc.formatar_moeda(rbt12_b)}")
# (12*60000)/6 = 120000
assert abs(rbt12_b - 120000) < 1e-9, rbt12_b

# Cenário 4: todas as faixas de cada anexo
print("\nCenário 4 — verificação de faixas")
for anexo, faixas in calc.FAIXAS.items():
    for idx, (inf, sup, aliq, ded) in enumerate(faixas, start=1):
        meio = (inf + sup) / 2 if idx > 1 else 90000
        r = calc.calcular(anexo, meio, 10000)
        assert r["faixa"] == idx, f"{anexo} faixa {idx} -> obtido {r['faixa']}"
    print(f"  Anexo {anexo}: 6 faixas OK")

# Cenário 5: formatação de moeda brasileira
print("\nCenário 5 — formatação")
print(f"  {calc.formatar_moeda(1234567.89)}")
print(f"  {calc.formatar_percentual(0.04825)}")
assert calc.formatar_moeda(1234567.89) == "R$ 1.234.567,89"
# 0.04825 = 4,825% -> arredonda para 4,83% (2 casas)
assert calc.formatar_percentual(0.04825) == "4,83%"

print("\n✅ Todos os testes passaram.")
