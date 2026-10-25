"""Interface de linha de comando: ela-preditivo {gerar-cenarios | executar | avaliar | tudo}."""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")

from . import AVISO_LEGAL, __version__  # noqa: E402


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ela-preditivo", description="Protótipo de apoio ao aconselhamento genético preditivo da ELA (TCC). " + AVISO_LEGAL)
    p.add_argument("--versao", action="version", version=f"ela_preditivo {__version__}")
    sub = p.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("gerar-cenarios", help="gera os VCFs sintéticos dos 5 cenários familiares")
    g.add_argument("--saida", default="data/sinteticos"); g.add_argument("--seed", type=int, default=2026); g.add_argument("--sem-ruido", action="store_true")

    e = sub.add_parser("executar", help="executa as três camadas para um casal (VCF materno + paterno)")
    e.add_argument("--vcf-mae", required=True); e.add_argument("--vcf-pai", required=True)
    e.add_argument("--sexo", choices=["M", "F"], default=None, help="sexo do descendente (efeito documentado só para C9orf72)")
    e.add_argument("--idade-atual", type=float, default=None, help="idade atual do descendente sem sintomas (condiciona o risco)")
    e.add_argument("--n", type=int, default=10_000); e.add_argument("--seed", type=int, default=42)
    e.add_argument("--motor", choices=["pymc", "numpy"], default="pymc"); e.add_argument("--saida", required=True)
    e.add_argument("--config", default=None, help="YAML de parâmetros (padrão: config/parametros_literatura.yaml)")
    e.add_argument("--tabela-variantes", default=None, help="CSV de anotação (padrão: data/variantes_curadas.csv)")
    e.add_argument("--horizonte", type=float, default=None); e.add_argument("--rotulo", default=""); e.add_argument("--sem-figuras", action="store_true")

    a = sub.add_parser("avaliar", help="estabilidade, tempo, coerência, calibração e sensibilidade nos cenários sintéticos")
    a.add_argument("--dir-cenarios", default="data/sinteticos"); a.add_argument("--saida", required=True)
    a.add_argument("--cenarios", nargs="+", type=int, default=None); a.add_argument("--n", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    a.add_argument("--repeticoes", type=int, default=30); a.add_argument("--seed", type=int, default=1000); a.add_argument("--sexo", choices=["M", "F"], default="F")
    a.add_argument("--n-coerencia", type=int, default=10_000); a.add_argument("--config", default=None)

    t = sub.add_parser("tudo", help="gera cenários, executa os 5 (dois sexos), avalia e escreve o índice")
    t.add_argument("--saida", default="resultados"); t.add_argument("--seed", type=int, default=42); t.add_argument("--n", type=int, default=10_000)
    t.add_argument("--ns", nargs="+", type=int, default=[1_000, 10_000, 100_000]); t.add_argument("--repeticoes", type=int, default=30)
    t.add_argument("--motor", choices=["pymc", "numpy"], default="pymc"); t.add_argument("--config", default=None); t.add_argument("--idade-atual", type=float, default=30.0)
    return p


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    from . import cenarios, pipeline
    if args.comando == "gerar-cenarios":
        df = cenarios.gerar_cenarios(args.saida, seed=args.seed, incluir_ruido=not args.sem_ruido)
        print(df.to_string(index=False)); print(f"\n{len(df) * 2} VCFs sintéticos em {args.saida}")
    elif args.comando == "executar":
        r = pipeline.executar(args.vcf_mae, args.vcf_pai, args.saida, sexo=args.sexo, idade_atual=args.idade_atual, n=args.n, seed=args.seed, motor=args.motor,
                              config=args.config, tabela_variantes=args.tabela_variantes, horizonte=args.horizonte, rotulo=args.rotulo, figuras=not args.sem_figuras)
        print(f"Relatório: {r['relatorio']}")
        if r["res"] is not None:
            print(r["resumo"][["variante", "heranca", "p_portador_exato", "p_portador_mc", "p_manifesta_exato", "p_manifesta_mc", "idade_mediana_mc"]].to_string(index=False))
        print(f"\n{AVISO_LEGAL}")
    elif args.comando == "avaliar":
        r = pipeline.avaliar(args.dir_cenarios, args.saida, numeros=args.cenarios, ns=tuple(args.n), repeticoes=args.repeticoes, seed=args.seed, sexo=args.sexo,
                             n_coerencia=args.n_coerencia, config=args.config)
        print(f"Relatório: {r['relatorio']}"); print(r["estabilidade"][["cenario", "n", "p_manifesta_qualquer_dp", "ep_teorico", "razao_dp_ep"]].to_string(index=False))
    elif args.comando == "tudo":
        r = pipeline.tudo(args.saida, seed=args.seed, n=args.n, ns=tuple(args.ns), repeticoes=args.repeticoes, motor=args.motor, config=args.config, idade_atual=args.idade_atual)
        print(f"Índice: {r['saida'] / 'README.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
