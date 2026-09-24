# -*- coding: utf-8 -*-
"""Valida a reparticao contra a planilha. Base = F3 (faturamento do mes).

Gabarito extraido de CALCULADORA SIMPLES.xlsx (colunas J/K/M, linhas 19-25).
RBT12 = F2 = 1.170.000  -> 4a faixa em todos os anexos.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "simples_app"))
import calc  # noqa: E402

CASOS = {
    "I": {
        "fat_mes": 200000.0,
        "linhas": [
            ("IRPJ", 0.0048273, 965.46),
            ("CSLL", 0.0030719, 614.38),
            ("Cofins", 0.0111818, 2236.36),
            ("PIS/Pasep", 0.0024224, 484.49),
            ("CPP", 0.0368631, 7372.62),
            ("ICMS", 0.0294027, 5880.54),
        ],
        "das": 17553.85,
    },
    "II": {
        "fat_mes": 20000.0,
        "linhas": [
            ("IRPJ", 0.0051023, 102.05),
            ("CSLL", 0.0032469, 64.94),
            ("Cofins", 0.0106777, 213.55),
            ("PIS/Pasep", 0.0023100, 46.20),
            ("CPP", 0.0347885, 695.77),
            ("IPI", 0.0069577, 139.15),
            ("ICMS", 0.0296862, 593.72),
        ],
        "das": 1855.38,
    },
    "III": {
        "fat_mes": 20000.0,
        "linhas": [
            ("IRPJ", 0.0051815, 103.63),
            ("CSLL", 0.0045338, 90.68),
            ("Cofins", 0.0176690, 353.38),
            ("PIS/Pasep", 0.0038343, 76.69),
            ("CPP", 0.0562197, 1124.39),
            ("ISS", 0.0421000, 842.00),
        ],
        "das": 2590.77,
    },
    "IV": {
        "fat_mes": 200000.0,
        "linhas": [
            ("IRPJ", 0.0188680, 3773.60),
            ("CSLL", 0.0203520, 4070.40),
            ("Cofins", 0.0200340, 4006.80),
            ("PIS/Pasep", 0.0043460, 869.20),
            ("ISS", 0.0424000, 8480.00),
        ],
        "das": 21200.00,
    },
}

RBT12 = 1170000.0

falhas = 0
for anexo, caso in CASOS.items():
    res = calc.calcular(anexo, RBT12, caso["fat_mes"])
    det = res["reparticao_detalhada"]
    print("=" * 76)
    print(f"ANEXO {anexo} | faixa {res['faixa']} | aliq.efetiva {res['aliquota_efetiva']:.7f} "
          f"| DAS {res['das']:>10.2f}")

    if det is None:
        print("  !! reparticao_detalhada = None")
        falhas += 1
        continue

    print(f"  {'tributo':<11} {'% calc':>12} {'% plan':>12} {'R$ calc':>12} {'R$ plan':>12}  ok")
    for (trib, k_esp, m_esp), item in zip(caso["linhas"], det):
        p_ok = abs(item["percentual"] - k_esp) < 1e-5
        v_ok = abs(item["valor"] - m_esp) < 0.02
        ok = p_ok and v_ok
        if not ok:
            falhas += 1
        print(f"  {item['tributo']:<11} {item['percentual']:>12.7f} {k_esp:>12.7f} "
              f"{item['valor']:>12.2f} {m_esp:>12.2f}  {'OK' if ok else 'DIVERGE'}")

    soma_v = sum(i["valor"] for i in det)
    soma_p = sum(i["percentual"] for i in det)
    fecha_v = abs(soma_v - caso["das"]) < 0.05
    fecha_p = abs(soma_p - res["aliquota_efetiva"]) < 1e-9
    if not (fecha_v and fecha_p):
        falhas += 1
    print(f"  {'TOTAL':<11} {soma_p:>12.7f} {'':>12} {soma_v:>12.2f} {caso['das']:>12.2f}  "
          f"{'OK' if (fecha_v and fecha_p) else 'DIVERGE'}")

print("=" * 76)
print("RESULTADO:", "TODAS PASSARAM" if falhas == 0 else f"{falhas} FALHA(S)")
