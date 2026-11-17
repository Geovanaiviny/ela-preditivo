"""Item C12 — `atualizacao.py`: registro de versões da base ClinVar, comparação entre releases e download filtrado aos genes-alvo."""

import gzip
from pathlib import Path

import pytest

from ela_preditivo import anotacao, atualizacao, cli

A5V = dict(
    allele_id="15",
    gene="SOD1",
    nome="NM_000454.5(SOD1):c.14C>T (p.Ala5Val)",
    rs="121912442",
    crom="21",
    pos=31659783,
    ref="C",
    alt="T",
    vid="13891",
)
D91A = dict(
    allele_id="17",
    gene="SOD1",
    nome="NM_000454.5(SOD1):c.272A>C (p.Asp91Ala)",
    rs="80265967",
    crom="21",
    pos=31667290,
    ref="A",
    alt="C",
    vid="13894",
)
X_TARDBP = dict(
    allele_id="18",
    gene="TARDBP",
    nome="NM_007375.4(TARDBP):c.1A>G (p.Met1Val)",
    rs="-1",
    crom="1",
    pos=11012700,
    ref="A",
    alt="G",
    vid="9999",
)
Y_FUS = dict(
    allele_id="19",
    gene="FUS",
    nome="NM_004960.4(FUS):c.1561C>T (p.Arg521Cys)",
    rs="121909668",
    crom="16",
    pos=31191418,
    ref="C",
    alt="T",
    vid="777",
)
MULTI = "criteria provided, multiple submitters, no conflicts"
SINGLE = "criteria provided, single submitter"


def test_registra_compara_e_relata(tmp_path, variant_summary_fake, linha_vs):
    v1 = variant_summary_fake(
        tmp_path / "v1.txt",
        [
            linha_vs(clnsig="Pathogenic", revstat=MULTI, **A5V),
            linha_vs(
                clnsig="Conflicting classifications of pathogenicity",
                revstat="criteria provided, conflicting classifications",
                **D91A,
            ),
            linha_vs(clnsig="Uncertain significance", revstat=SINGLE, **X_TARDBP),
        ],
    )
    v2 = variant_summary_fake(
        tmp_path / "v2.txt",
        [
            linha_vs(clnsig="Pathogenic", revstat="reviewed by expert panel", **A5V),
            linha_vs(clnsig="Pathogenic", revstat=MULTI, **D91A),
            linha_vs(clnsig="Likely pathogenic", revstat=SINGLE, **Y_FUS),
        ],
    )
    reg = tmp_path / "versoes"
    r1 = atualizacao.atualizar(v1, diretorio=reg, release="2026-09-28")
    assert r1["anterior"] is None and r1["relatorio"] is None
    assert (
        r1["atual"]["release"] == "2026-09-28"
        and r1["atual"]["n_variantes"] == 3
        and r1["atual"]["por_classe"] == {"conflitante": 1, "risco": 1, "vus": 1}
    )
    assert (
        (reg / r1["atual"]["instantaneo"]).is_file()
        and len(r1["atual"]["sha256"]) == 64
        and len(atualizacao.carregar_registro(reg)) == 1
    )
    r2 = atualizacao.atualizar(v2, diretorio=reg, release="2026-10-26")
    res = r2["comparacao"]["resumo"]
    assert r2["anterior"]["release"] == "2026-09-28" and res["n_anterior"] == 3 and res["n_atual"] == 3
    assert (
        res["novas"] == 1
        and res["removidas"] == 1
        and res["reclassificadas"] == 1
        and res["mudanca_so_de_clnsig_ou_estrelas"] == 1
    )  # A5V: 2★ → 3★
    assert (
        res["transicoes_de_classe"] == {"conflitante → risco": 1}
        and res["novas_por_classe"] == {"risco": 1}
        and res["removidas_por_classe"] == {"vus": 1}
    )
    assert r2["comparacao"]["novas"].nome_curto.tolist() == ["p.Arg521Cys"] and r2["comparacao"][
        "removidas"
    ].gene.tolist() == ["TARDBP"]
    rec = r2["comparacao"]["reclassificadas"].set_index("nome_curto")
    assert (
        rec.loc["p.Asp91Ala", "classe_anterior"] == "conflitante" and rec.loc["p.Asp91Ala", "classe_atual"] == "risco"
    )
    assert rec.loc["p.Ala5Val", "estrelas_anterior"] == 2 and rec.loc["p.Ala5Val", "estrelas_atual"] == 3
    afet = r2["comparacao"]["curadas_afetadas"]
    assert set(zip(afet.evento, afet.nome_curto)) == {
        ("nova", "p.Arg521Cys"),
        ("reclassificada", "p.Asp91Ala"),
        ("estrelas/clnsig", "p.Ala5Val"),
    }
    texto = Path(r2["relatorio"]).read_text(encoding="utf-8")
    assert (
        "2026-09-28 → 2026-10-26" in texto
        and "conflitante → risco" in texto
        and "p.Asp91Ala" in texto
        and "AVISO" in texto
    )
    assert [v["release"] for v in atualizacao.carregar_registro(reg)] == ["2026-09-28", "2026-10-26"]
    # registrar a mesma base de novo não duplica a entrada; sem release identificável e sem parâmetro, erro claro
    atualizacao.registrar_versao(v2, reg, release="2026-10-26")
    assert len(atualizacao.carregar_registro(reg)) == 2
    with pytest.raises(ValueError, match="release"):
        atualizacao.registrar_versao(v1, tmp_path / "outro")
    assert "1 novas, 1 removidas, 1 reclassificadas" in atualizacao.resumo_texto(r2)


def test_baixar_clinvar_de_url_local_filtra_os_genes_alvo(tmp_path):
    linhas = [
        "##fileformat=VCFv4.1",
        "##fileDate=2026-11-01",
        "##reference=GRCh38",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        "21\t31659783\t13891\tC\tT\t.\t.\tALLELEID=15;CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;CLNSIG=Pathogenic;GENEINFO=SOD1:6647;RS=121912442",
        "1\t11012700\t9999\tA\tG\t.\t.\tALLELEID=18;CLNREVSTAT=criteria_provided,_single_submitter;CLNSIG=Uncertain_significance;GENEINFO=MASP2:10747|TARDBP:23435",
        "17\t7675088\t1\tC\tT\t.\t.\tALLELEID=1;CLNSIG=Pathogenic;GENEINFO=TP53:7157",
    ]
    gz = tmp_path / "clinvar.vcf.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    d = atualizacao.baixar_clinvar(destino=tmp_path / "dados", url=gz.as_uri())
    assert (
        d["release"] == "2026-11-01"
        and d["release_fonte"] == "##fileDate"
        and d["n_registros"] == 2
        and d["arquivo"].endswith("clinvar_ela_4genes_20261101.vcf")
    )
    t = anotacao.carregar_clinvar_vcf(d["arquivo"])
    assert set(t.gene) == {"SOD1", "TARDBP"} and anotacao.identificar_base(d["arquivo"])["release"] == "2026-11-01"
    assert anotacao.localizar_base_real(tmp_path / "dados") == Path(d["arquivo"])
    e = atualizacao.registrar_versao(d["arquivo"], tmp_path / "reg")  # release lida do cabeçalho, sem parâmetro
    assert (
        e["release"] == "2026-11-01"
        and e["release_fonte"] == "##fileDate"
        and e["n_variantes"] == 2
        and e["formato"] == "clinvar_vcf"
    )
    with pytest.raises(ValueError, match="release"):
        atualizacao.baixar_clinvar(release="outubro", destino=tmp_path / "x")


def test_cli_atualizar_base(tmp_path, variant_summary_fake, linha_vs, capsys):
    v1 = variant_summary_fake(tmp_path / "clinvar_20260928.txt", [linha_vs(clnsig="Pathogenic", revstat=MULTI, **A5V)])
    reg = tmp_path / "reg"
    assert cli.main(["atualizar-base", "--base", str(v1), "--registro", str(reg)]) == 0
    out = capsys.readouterr().out
    assert "release 2026-09-28 (nome do arquivo)" in out and "Primeira versão registrada" in out and "AVISO" in out
    assert cli.main(["atualizar-base", "--listar", "--registro", str(reg)]) == 0
    assert "2026-09-28  clinvar_20260928.txt" in capsys.readouterr().out
