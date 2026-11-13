"""Interface de linha de comando: ela-preditivo {gerar-cenarios | executar | avaliar | tudo}."""

from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")

from . import AVISO_LEGAL, __version__  # noqa: E402


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ela-preditivo",
        description="Protótipo de apoio ao aconselhamento genético preditivo da ELA (TCC). " + AVISO_LEGAL,
    )
    p.add_argument("--versao", action="version", version=f"ela_preditivo {__version__}")
    sub = p.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("gerar-cenarios", help="gera os VCFs sintéticos dos 5 cenários familiares")
    g.add_argument("--saida", default="data/sinteticos")
    g.add_argument("--seed", type=int, default=2026)
    g.add_argument("--sem-ruido", action="store_true")

    e = sub.add_parser("executar", help="executa as três camadas para um casal (VCF materno + paterno)")
    e.add_argument("--vcf-mae", required=True)
    e.add_argument("--vcf-pai", required=True)
    e.add_argument(
        "--sexo", choices=["M", "F"], default=None, help="sexo do descendente (efeito documentado só para C9orf72)"
    )
    e.add_argument(
        "--idade-atual", type=float, default=None, help="idade atual do descendente sem sintomas (condiciona o risco)"
    )
    e.add_argument("--n", type=int, default=10_000)
    e.add_argument("--seed", type=int, default=42)
    e.add_argument("--motor", choices=["pymc", "numpy"], default="pymc")
    e.add_argument("--saida", required=True)
    e.add_argument("--config", default=None, help="YAML de parâmetros (padrão: config/parametros_literatura.yaml)")
    e.add_argument("--tabela-variantes", default=None, help="CSV de anotação (padrão: data/variantes_curadas.csv)")
    e.add_argument("--horizonte", type=float, default=None)
    e.add_argument("--rotulo", default="")
    e.add_argument("--sem-figuras", action="store_true")
    e.add_argument(
        "--c9orf72-mae",
        type=int,
        nargs="+",
        default=None,
        metavar="REP",
        help="laudo do C9orf72 da mãe: nº de repetições GGGGCC do maior alelo (ou dos dois alelos). A expansão não é lida do VCF (TCC 4.2.1)",
    )
    e.add_argument("--c9orf72-pai", type=int, nargs="+", default=None, metavar="REP", help="idem para o pai")
    e.add_argument(
        "--amostra-mae", default=None, help="nome da amostra no VCF materno, se multiamostra (padrão: a primeira)"
    )
    e.add_argument("--amostra-pai", default=None, help="idem para o VCF paterno")
    _arg_base(e)

    a = sub.add_parser(
        "avaliar", help="estabilidade, tempo, coerência, calibração e sensibilidade nos cenários sintéticos"
    )
    a.add_argument("--dir-cenarios", default="data/sinteticos")
    a.add_argument("--saida", required=True)
    a.add_argument("--cenarios", nargs="+", type=int, default=None)
    a.add_argument("--n", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    a.add_argument("--repeticoes", type=int, default=30)
    a.add_argument("--seed", type=int, default=1000)
    a.add_argument("--sexo", choices=["M", "F"], default="F")
    a.add_argument("--n-coerencia", type=int, default=10_000)
    a.add_argument("--config", default=None)
    _arg_base(a)

    t = sub.add_parser("tudo", help="gera cenários, executa os 5 (dois sexos), avalia e escreve o índice")
    t.add_argument("--saida", default="resultados")
    t.add_argument("--seed", type=int, default=42)
    t.add_argument("--n", type=int, default=10_000)
    t.add_argument("--ns", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    t.add_argument("--repeticoes", type=int, default=30)
    t.add_argument("--motor", choices=["pymc", "numpy"], default="pymc")
    t.add_argument("--config", default=None)
    t.add_argument("--idade-atual", type=float, default=30.0)
    _arg_base(t)

    u = sub.add_parser(
        "atualizar-base",
        help="registra a versão da base ClinVar (release, sha256, instantâneo) e mostra o que mudou desde a anterior",
    )
    u.add_argument(
        "--base",
        default=None,
        metavar="ARQUIVO",
        help="base local a registrar (padrão: a encontrada em ELA_DADOS_BRUTOS ou dados_reais/)",
    )
    u.add_argument(
        "--baixar",
        action="store_true",
        help="antes, baixa a release mensal do ClinVar (VCF GRCh38 do NCBI) filtrada aos quatro genes para dados_reais/",
    )
    u.add_argument(
        "--release",
        default=None,
        metavar="AAAA-MM-DD",
        help="release a baixar (padrão: a mais recente) ou rótulo de uma base local sem data no nome/cabeçalho",
    )
    u.add_argument(
        "--registro", default=None, metavar="DIR", help="pasta do registro de versões (padrão: dados_reais/versoes)"
    )
    u.add_argument(
        "--destino", default=None, metavar="DIR", help="pasta onde o download é gravado (padrão: dados_reais/)"
    )
    u.add_argument("--listar", action="store_true", help="só lista as versões registradas")
    return p


def _arg_base(sp: argparse.ArgumentParser) -> None:
    g = sp.add_mutually_exclusive_group()
    g.add_argument(
        "--base-clinvar",
        default=None,
        metavar="ARQUIVO",
        help="base real do ClinVar dos quatro genes (base_consolidada_ela.csv, clinvar_ela_4genes.csv/.vcf ou variant_summary.txt). "
        "Padrão: procura em ELA_DADOS_BRUTOS ou em dados_reais/ na raiz do repositório",
    )
    g.add_argument(
        "--so-tabela-curada", action="store_true", help="ignora a base real e anota só com data/variantes_curadas.csv"
    )


def _base(args):
    return False if getattr(args, "so_tabela_curada", False) else getattr(args, "base_clinvar", None)


def _laudo(args) -> dict | None:
    laudo = {}
    for lado in ("mae", "pai"):
        v = getattr(args, f"c9orf72_{lado}", None)
        if v:
            laudo[lado] = v[0] if len(v) == 1 else tuple(v)
    return laudo or None


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    from . import cenarios, pipeline

    if args.comando == "gerar-cenarios":
        df = cenarios.gerar_cenarios(args.saida, seed=args.seed, incluir_ruido=not args.sem_ruido)
        print(df.to_string(index=False))
        print(f"\n{len(df) * 2} VCFs sintéticos em {args.saida}")
    elif args.comando == "executar":
        r = pipeline.executar(
            args.vcf_mae,
            args.vcf_pai,
            args.saida,
            sexo=args.sexo,
            idade_atual=args.idade_atual,
            n=args.n,
            seed=args.seed,
            motor=args.motor,
            config=args.config,
            tabela_variantes=args.tabela_variantes,
            horizonte=args.horizonte,
            rotulo=args.rotulo,
            figuras=not args.sem_figuras,
            laudo_c9orf72=_laudo(args),
            base_clinvar=_base(args),
            amostra_mae=args.amostra_mae,
            amostra_pai=args.amostra_pai,
        )
        print(f"Relatório: {r['relatorio']}")
        if r["res"] is not None:
            print(
                r["resumo"][
                    [
                        "variante",
                        "heranca",
                        "p_portador_exato",
                        "p_portador_mc",
                        "p_manifesta_exato",
                        "p_manifesta_mc",
                        "idade_mediana_mc",
                    ]
                ].to_string(index=False)
            )
        else:
            print("Nenhum lócus de risco encontrado (ver relatório).")
        print(f"\n{AVISO_LEGAL}")
    elif args.comando == "avaliar":
        r = pipeline.avaliar(
            args.dir_cenarios,
            args.saida,
            numeros=args.cenarios,
            ns=tuple(args.n),
            repeticoes=args.repeticoes,
            seed=args.seed,
            sexo=args.sexo,
            n_coerencia=args.n_coerencia,
            config=args.config,
            base_clinvar=_base(args),
        )
        print(f"Relatório: {r['relatorio']}")
        print(
            r["estabilidade"][["cenario", "n", "p_manifesta_qualquer_dp", "ep_teorico", "razao_dp_ep"]].to_string(
                index=False
            )
        )
    elif args.comando == "tudo":
        r = pipeline.tudo(
            args.saida,
            seed=args.seed,
            n=args.n,
            ns=tuple(args.ns),
            repeticoes=args.repeticoes,
            motor=args.motor,
            config=args.config,
            idade_atual=args.idade_atual,
            base_clinvar=_base(args),
        )
        print(f"Índice: {r['saida'] / 'README.md'}")
    elif args.comando == "atualizar-base":
        from . import anotacao, atualizacao

        if args.listar:
            versoes = atualizacao.carregar_registro(args.registro)
            print(
                "\n".join(
                    f"{v['release']}  {v['arquivo']}  sha256 {v['sha256'][:12]}  {v['n_variantes']} variantes  registrado em {v['registrado_em']}"
                    for v in versoes
                )
                or "nenhuma versão registrada"
            )
            return 0
        base = args.base
        if args.baixar:
            d = atualizacao.baixar_clinvar(release=args.release, destino=args.destino)
            base = d["arquivo"]
            print(f"Baixado: {base} (release {d['release']}; {d['n_registros']} registros dos genes-alvo)")
        if base is None:
            base = anotacao.localizar_base_real()
            if base is None:
                print(
                    "nenhuma base encontrada em ELA_DADOS_BRUTOS/dados_reais; informe --base ARQUIVO ou use --baixar",
                    file=sys.stderr,
                )
                return 2
        r = atualizacao.atualizar(base, diretorio=args.registro, release=(None if args.baixar else args.release))
        print(atualizacao.resumo_texto(r))
        print(f"\n{AVISO_LEGAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
