"""Interface de linha de comando: ela-preditivo {gerar-cenarios | executar | avaliar | tudo | atualizar-base |
servir | criar-admin | popular-demo | verificar-auditoria | gerar-chave}."""

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
    e.add_argument("--vcf-mae", default=None, help="VCF da mãe (dispensável só com parentes dela ou filho testado)")
    e.add_argument("--vcf-pai", default=None, help="VCF do pai (dispensável só com parentes dele ou filho testado)")
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
        help=(
            "laudo do C9orf72 da mãe: nº de repetições GGGGCC do maior alelo (ou dos dois alelos). A expansão não é "
            "lida do VCF (TCC 4.2.1). Ausente = mãe não testada: o lócus do C9orf72 fica indeterminado, sai do cálculo "
            "e o relatório marca o resultado como parcial; um laudo normal também é uma contagem (ex.: 8)"
        ),
    )
    e.add_argument(
        "--c9orf72-pai",
        type=int,
        nargs="+",
        default=None,
        metavar="REP",
        help="idem para o pai (ausente = pai não testado)",
    )
    e.add_argument(
        "--amostra-mae", default=None, help="nome da amostra no VCF materno, se multiamostra (padrão: a primeira)"
    )
    e.add_argument("--amostra-pai", default=None, help="idem para o VCF paterno")
    _arg_parentes(e)
    _arg_extensoes(e)
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
    _arg_verificacao(a)
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
    t.add_argument(
        "--sem-cox", action="store_true", help="não ajusta o modelo de Cox de comparação (Tabela 11, Figura 9)"
    )
    _arg_verificacao(t)
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

    # Plataforma web (extra `web`)
    s = sub.add_parser("servir", help="sobe a plataforma web (FastAPI/uvicorn); exige ELA_WEB_CHAVE")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--porta", type=int, default=8000)
    ca = sub.add_parser("criar-admin", help="cria um administrador (só por comando; nenhuma rota cria ou promove)")
    ca.add_argument("--nome", required=True)
    ca.add_argument("--cpf", required=True)
    ca.add_argument("--email", required=True)
    ca.add_argument("--senha", default=None, help="se omitida, é pedida no terminal sem eco")
    sub.add_parser("popular-demo", help="usuários de demonstração e pacientes fictícios (só num banco vazio)")
    sub.add_parser("verificar-auditoria", help="confere a cadeia de hash da auditoria")
    sub.add_parser("gerar-chave", help="imprime uma chave Fernet nova para ELA_WEB_CHAVE")
    return p


def _arg_verificacao(sp: argparse.ArgumentParser) -> None:
    """Verificação com famílias sintéticas de desfecho conhecido (Tabelas 12 a 20 da avaliação)."""
    g = sp.add_argument_group("verificação com famílias sintéticas (calibração, discriminação, cobertura, tornado)")
    g.add_argument("--sem-metricas", action="store_true", help="não calcula as métricas de verificação")
    g.add_argument("--mundos", type=int, default=200, help="nº de mundos: em cada um a penetrância é sorteada uma vez")
    g.add_argument("--por-estrato", type=int, default=10, help="pessoas por estrato (cenário × sexo × idade) e mundo")
    g.add_argument(
        "--seed-coorte", type=int, default=None, help="semente própria da coorte (padrão: derivada da semente)"
    )


def _arg_parentes(sp: argparse.ArgumentParser) -> None:
    """Genótipo de parentes para o genitor que não pôde ser testado: avô, avó e tios de cada lado, a situação
    clínica e a idade do genitor, e o VCF de filhos já testados."""
    g = sp.add_argument_group(
        "genitor sem exame, inferido por parentes",
        "Quando um genitor não pôde ser testado, omita o VCF dele e informe o de parentes dele. A dosagem do genitor "
        "passa a ser inferida e condicionada à situação clínica dele; a penetrância é a mesma para toda a família.",
    )
    for lado, de in (("mae", "da mãe"), ("pai", "do pai")):
        s = f"-{'da-mae' if lado == 'mae' else 'do-pai'}"
        g.add_argument(f"--vcf-pai{s}", default=None, metavar="VCF", help=f"VCF do pai {de} (avô do descendente)")
        g.add_argument(f"--vcf-mae{s}", default=None, metavar="VCF", help=f"VCF da mãe {de} (avó do descendente)")
        g.add_argument(
            f"--vcf-irmao{s}",
            nargs="+",
            default=None,
            metavar="VCF",
            help=f"VCF de irmão(s) {de} (tios do descendente)",
        )
        g.add_argument(
            f"--c9orf72-pai{s}", type=int, nargs="+", default=None, metavar="REP", help=f"laudo do C9orf72 do pai {de}"
        )
        g.add_argument(
            f"--c9orf72-mae{s}", type=int, nargs="+", default=None, metavar="REP", help=f"laudo do C9orf72 da mãe {de}"
        )
        g.add_argument(
            f"--c9orf72-irmao{s}",
            type=int,
            nargs="+",
            default=None,
            metavar="REP",
            help=f"laudo do C9orf72 de irmão(s) {de}: uma contagem por irmão, na ordem de --vcf-irmao{s}",
        )
        g.add_argument(
            f"--situacao-{lado}",
            choices=["vivo_assintomatico", "falecido_sem_ela", "afetado", "desconhecido"],
            default=None,
            help=f"situação clínica {de} sem exame (obrigatória com parentes; afetado e desconhecido não condicionam)",
        )
        g.add_argument(
            f"--idade-{lado}",
            type=float,
            default=None,
            metavar="ANOS",
            help=f"idade atual {de} (vivo sem sintomas) ou ao falecer (falecido sem ELA)",
        )
    g.add_argument(
        "--vcf-filho-testado",
        nargs="+",
        default=None,
        metavar="VCF",
        help="VCF de filho(s) já testado(s): evidência sobre o genitor sem exame (o filho testado não é a pessoa em risco)",
    )
    g.add_argument(
        "--prior-avos",
        choices=["nao_portador", "hardy_weinberg"],
        default="nao_portador",
        help="avô ou avó sem exame: suposto não portador (padrão) ou prior de Hardy-Weinberg com a frequência alélica "
        "da base de anotação (sem frequência na base, volta à suposição de não portador)",
    )


def _contagem(v):
    """Laudo passado como um ou dois inteiros → inteiro (maior alelo) ou par (dois alelos)."""
    if not v:
        return None
    return v[0] if len(v) == 1 else tuple(v)


def _parentes(args) -> dict | None:
    """Monta o argumento `parentes` de `pipeline.executar` a partir das opções da linha de comando."""
    out: dict = {}
    for lado in ("mae", "pai"):
        s = "_da_mae" if lado == "mae" else "_do_pai"
        d: dict = {}
        for papel in ("pai", "mae"):
            vcf, laudo = getattr(args, f"vcf_{papel}{s}", None), _contagem(getattr(args, f"c9orf72_{papel}{s}", None))
            if vcf or laudo is not None:
                d[papel] = {"vcf": vcf, "laudo_c9orf72": laudo}
        vcfs_irmaos = getattr(args, f"vcf_irmao{s}", None) or []
        laudos_irmaos = getattr(args, f"c9orf72_irmao{s}", None) or []
        irmaos = []
        for i in range(max(len(vcfs_irmaos), len(laudos_irmaos))):
            irmaos.append(
                {
                    "vcf": vcfs_irmaos[i] if i < len(vcfs_irmaos) else None,
                    "laudo_c9orf72": laudos_irmaos[i] if i < len(laudos_irmaos) else None,
                }
            )
        if irmaos:
            d["irmaos"] = irmaos
        situacao, idade = getattr(args, f"situacao_{lado}", None), getattr(args, f"idade_{lado}", None)
        if d or situacao or idade is not None:
            d.update(situacao=situacao or "desconhecido", idade=idade, prior_avos=getattr(args, "prior_avos", None))
            out[lado] = d
    filhos = getattr(args, "vcf_filho_testado", None) or []
    if filhos:
        out["filhos_testados"] = [{"vcf": v} for v in filhos]
    return out or None


def _arg_extensoes(sp: argparse.ArgumentParser) -> None:
    """Extensões experimentais: transmissão do C9orf72 por repetições e comparação com Cox."""
    g = sp.add_argument_group("extensões experimentais")
    g.add_argument(
        "--c9-delta-mae",
        type=int,
        default=None,
        metavar="REP",
        help="hipótese: variação (±) de repetições do alelo materno do C9orf72 ao ser transmitido (só alelos ≥ faixa intermediária)",
    )
    g.add_argument("--c9-delta-pai", type=int, default=None, metavar="REP", help="idem para o alelo paterno")
    g.add_argument(
        "--c9-antecipacao",
        type=float,
        default=None,
        metavar="ANOS",
        help="hipótese: antecipação da idade de início do C9orf72 no descendente, em anos",
    )
    g.add_argument(
        "--cox", action="store_true", help="ajusta CoxPHFitter na coorte de portadores e compara com a cura mista"
    )
    g.add_argument(
        "--tornado",
        action="store_true",
        help="sensibilidade tipo tornado do caso: um parâmetro por vez, dentro da faixa publicada (Tabela 20, Figura 12)",
    )


def _hipoteses(args) -> dict | None:
    h = {
        "delta_mae": getattr(args, "c9_delta_mae", None),
        "delta_pai": getattr(args, "c9_delta_pai", None),
        "antecipacao": getattr(args, "c9_antecipacao", None),
    }
    return h if any(v is not None for v in h.values()) else None


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
        extras = cenarios.gerar_cenarios_parentes(args.saida, seed=args.seed, incluir_ruido=not args.sem_ruido)
        n_extras = len(list(__import__("pathlib").Path(args.saida).glob("parentes_*.vcf")))
        for c in extras:
            print(f"cenário de parentes {c['numero']}: {c['descricao']}")
        print(f"\n{len(df) * 2} VCFs sintéticos dos cenários e {n_extras} dos cenários de parentes em {args.saida}")
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
            hipoteses_c9orf72=_hipoteses(args),
            comparar_cox=args.cox,
            parentes=_parentes(args),
            tornado=args.tornado,
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
            metricas=not args.sem_metricas,
            mundos=args.mundos,
            por_estrato=args.por_estrato,
            seed_coorte=args.seed_coorte,
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
            comparar_cox=not args.sem_cox,
            metricas=not args.sem_metricas,
            mundos=args.mundos,
            por_estrato=args.por_estrato,
            seed_coorte=args.seed_coorte,
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
    elif args.comando == "gerar-chave":
        from .web.config import gerar_chave

        print(gerar_chave())
    elif args.comando in ("servir", "criar-admin", "popular-demo", "verificar-auditoria"):
        return _comando_web(args)
    return 0


def _comando_web(args) -> int:
    from .web import auditoria, demo
    from .web.bd import criar_engine, criar_tabelas, fabrica_sessoes
    from .web.config import Configuracao, ConfiguracaoInvalida
    from .web.seguranca import Cifra

    try:
        config = Configuracao.do_ambiente()
    except ConfiguracaoInvalida as e:
        print(e, file=sys.stderr)
        return 2
    if args.comando == "servir":
        import uvicorn

        from .web.api import criar_app

        print(
            f"Banco: {config.bd}; VCFs cifrados: {config.dir_vcfs}; ambiente: {config.ambiente}; "
            f"cookie seguro: {config.cookie_seguro}"
        )
        uvicorn.run(criar_app(config), host=args.host, port=args.porta, log_level="info")
        return 0
    engine = criar_engine(config.bd)
    criar_tabelas(engine)
    cifra = Cifra(config.chave)
    with fabrica_sessoes(engine)() as bd:
        if args.comando == "criar-admin":
            senha = args.senha
            if not senha:
                import getpass

                senha = getpass.getpass("Senha do administrador (mínimo 10 caracteres): ")
            try:
                u = demo.criar_admin(bd, cifra, args.nome, args.cpf, args.email, senha)
            except ValueError as e:
                print(f"não foi possível criar o administrador: {e}", file=sys.stderr)
                return 2
            print(f"Administrador criado: id {u.id}, e-mail {u.email}")
        elif args.comando == "popular-demo":
            try:
                r = demo.popular(bd, cifra, config)
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                return 2
            print(
                f"Demonstração populada: {len(r['credenciais'])} usuários, {r['pacientes']} registros fictícios "
                f"(pessoa, casal e família, dois deles com genitor inferido por parentes), {r['vcfs']} VCFs sintéticos "
                f"anexados e {r['analises']} análises.\n"
            )
            print(f"{'papel':<12} {'situação':<26} {'e-mail':<34} senha")
            for c in r["credenciais"]:
                print(f"{c['papel']:<12} {c['situacao']:<26} {c['email']:<34} {c['senha']}")
            print("\nGuarde as senhas: elas não ficam em claro no banco.")
        elif args.comando == "verificar-auditoria":
            r = auditoria.verificar(bd)
            if r["ok"]:
                print(f"Auditoria íntegra: {r['total']} registros encadeados.")
            else:
                print(f"ADULTERAÇÃO DETECTADA na sequência {r['primeira_falha']} (de {r['total']} registros).")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
