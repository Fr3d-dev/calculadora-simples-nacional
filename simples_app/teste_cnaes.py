"""Teste rápido do enquadramento CNAE -> Anexo e do fator R."""

from cnaes import calcular_fator_r, formatar_cnae, sugerir_anexo

CASOS = [
    ("4711302", "Comercio varejista de mercadorias em geral"),
    ("4713002", "Comercio varejista de mercadorias em geral - mercearia"),
    ("5611201", "Restaurante e similares"),
    ("6201500", "Desenvolvimento de programas de computador sob encomenda"),
    ("4120400", "Construcao de edificios"),
    ("8011101", "Atividades de vigilancia e seguranca privada"),
    ("6920601", "Atividades de contabilidade"),
    ("1011201", "Fabricacao de produtos de carne"),
    ("8630503", "Atividade medica ambulatorial restrita a consultas"),
    ("8121400", "Limpeza em predios e em domicilios"),
    ("4911600", "Transporte rodoviario de cargas"),
    ("8599604", "Treinamento em desenvolvimento profissional"),
    ("4520001", "Servicos de manutencao e reparacao mecanica de veiculos"),
    ("9602502", "Atividades de estetica e outros servicos de beleza"),
    ("0111301", "Cultivo de arroz"),
]


def main():
    print("=" * 78)
    print("ENQUADRAMENTO POR CNAE")
    print("=" * 78)
    for codigo, descricao in CASOS:
        r = sugerir_anexo(codigo, descricao)
        anexo = r["anexo"] or "??"
        print(f"{formatar_cnae(codigo):<12} Anexo {anexo:<3} "
              f"[{r['confianca']:<5}] {r['descricao_grupo']}")

    print()
    print("=" * 78)
    print("FATOR R (folha 12m / RBT12)")
    print("=" * 78)
    for folha, rbt in [(30000, 100000), (10000, 100000), (0, 0), (28000, 100000)]:
        r = calcular_fator_r(folha, rbt)
        print(f"folha={folha:>7} rbt12={rbt:>7} -> fator={r['fator']:.2%} "
              f"-> Anexo {r['anexo']}")

    print()
    print("=" * 78)
    print("NORMALIZACAO / FORMATACAO")
    print("=" * 78)
    for entrada in ["4711302", "47.11-3/02", "4711-3/02", "47.11-3"]:
        print(f"{entrada!r:<14} -> {formatar_cnae(entrada)!r}")


if __name__ == "__main__":
    main()
