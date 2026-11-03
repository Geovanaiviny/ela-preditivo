import warnings

import numpy as np
import pandas as pd
import pytest
import vcf

from ela_preditivo import cenarios, ingestao


def test_gera_dez_vcfs_e_csv(dir_cenarios):
    arquivos = sorted(p.name for p in dir_cenarios.glob("*.vcf"))
    assert len(arquivos) == 10
    idx = pd.read_csv(dir_cenarios / "cenarios.csv")
    assert {"c9orf72_mae", "c9orf72_pai"} <= set(idx.columns)
    assert idx.set_index("numero").loc[2, "c9orf72_mae"] == 45 and pd.isna(idx.set_index("numero").loc[1, "c9orf72_mae"])
    # todos legíveis pelo PyVCF, com uma amostra e com os campos do Quadro 2 do TCC
    for a in arquivos:
        r = vcf.Reader(filename=str(dir_cenarios / a))
        assert len(r.samples) == 1 and {"AC", "AN", "DB"} <= set(r.infos) and {"GT", "DP", "GQ"} <= set(r.formats)
        assert r.metadata["reference"] == "GRCh38"
        regs = list(r)
        assert len(regs) >= 5
        assert not any(str(rec.ALT[0]).startswith("<STR") for rec in regs)   # a expansão do C9orf72 não vai no VCF (TCC 4.2.1)


def test_vcfs_sao_reproduziveis(tmp_path):
    cenarios.gerar_cenarios(tmp_path / "a", seed=7)
    cenarios.gerar_cenarios(tmp_path / "b", seed=7)
    for n in range(1, 6):
        for lado in ("mae", "pai"):
            la = [l for l in (tmp_path / "a" / f"cenario_{n}_{lado}.vcf").read_text().splitlines() if not l.startswith("##fileDate")]
            lb = [l for l in (tmp_path / "b" / f"cenario_{n}_{lado}.vcf").read_text().splitlines() if not l.startswith("##fileDate")]
            assert la == lb


def test_normalizacao_cromossomo_e_regioes():
    assert ingestao.normalizar_cromossomo("chr21") == "21"
    assert ingestao.normalizar_cromossomo("MT") == "M"
    reg = ingestao.carregar_regioes()
    assert set(reg.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"}
    assert ingestao.gene_da_posicao("chr21", 31659783, reg) == "SOD1"
    assert ingestao.gene_da_posicao("21", 31659509, reg) == "SOD1"   # 157 pb acima do gene, dentro do flanco
    assert ingestao.gene_da_posicao("9", 27573529, reg) == "C9orf72"
    assert ingestao.gene_da_posicao("17", 7675088, reg) is None


def test_motivo_repeticao_biopython():
    assert ingestao.mesmo_motivo("GGGGCC", "GGCCCC")   # complemento reverso (as duas grafias do ClinVar)
    assert ingestao.mesmo_motivo("GGGGCC", "CCGGGG")   # rotação do complemento reverso
    assert not ingestao.mesmo_motivo("GGGGCC", "CAGCAG")
    assert ingestao.contar_repeticoes("GGGGCC" * 31) == 31
    assert ingestao.contar_repeticoes("GGCCCC" * 7) == 7


def test_leitura_cenario_3_mae(dir_cenarios):
    df = ingestao.ler_vcf(dir_cenarios / "cenario_3_mae.vcf")
    assert df.amostra.unique().tolist() == ["MAE"]
    assert set(df.cromossomo) <= {"1", "9", "16", "17", "21"}   # sem prefixo chr
    assert (df.montagem == "GRCh38").all() and df.attrs["vcf"]["montagem"] == "GRCh38"
    assert df[df.tipo == "repeticao"].empty                      # expansão vem do laudo, não do VCF
    # multialélico decomposto em duas linhas, GT 0/2 -> dosagens (0, 1); AC por ALT acompanha
    multi = df[(df.cromossomo == "1") & (df.posicao == 11020000)].sort_values("indice_alt")
    assert multi.dosagem.tolist() == [0, 1] and multi.n_alt.tolist() == [2, 2] and multi.ac.tolist() == [0, 1] and multi.an.tolist() == [2, 2]
    # reprovações
    rep = df[~df.aprovado].set_index("posicao")
    assert rep.loc[7675088, "motivo_reprovacao"] == "fora_das_regioes"
    assert set(rep.loc[31663000, "motivo_reprovacao"].split(";")) == {"filtro_nao_pass", "dp_baixo", "gq_baixo"}
    # variante de risco do pai aparece com GT 0/0 e dosagem 0, aprovada, e com flag DB (tem rs)
    a5v = df[df.id == "rs121912442"].iloc[0]
    assert a5v.dosagem == 0 and a5v.aprovado and a5v.no_dbsnp is np.True_ or a5v.no_dbsnp is True
    assert df.loc[df.id.isna(), "no_dbsnp"].eq(False).all()
    res = ingestao.resumo_ingestao(df)
    assert res["registros"] == 7 and res["aprovados"] == 5 and res["montagem"] == "GRCh38" and res["no_dbsnp"] == 2
    assert res["taxa_aprovacao"] == pytest.approx(5 / 7)


def test_filtro_configuravel(dir_cenarios):
    df = ingestao.ler_vcf(dir_cenarios / "cenario_1_pai.vcf", filtro={"dp_minimo": 0, "gq_minimo": 0, "exigir_pass": False})
    assert df.loc[df.posicao == 31663000, "aprovado"].item()


def test_expansao_no_vcf_caminho_secundario(tmp_path):
    """Um VCF no estilo ExpansionHunter continua legível (ALT <STRn>, REPCN), embora o fluxo do TCC use o laudo."""
    rng = np.random.default_rng(1)
    p = cenarios.escrever_vcf(tmp_path / "exp.vcf", "MAE", [cenarios.c9orf72_expansao(45)], rng, incluir_ruido=False)
    df = ingestao.ler_vcf(p)
    exp = df.iloc[0]
    assert exp.tipo == "repeticao" and exp.gene == "C9orf72" and exp.dosagem == 1 and exp.repeticoes == 45 and exp.aprovado
    assert not exp.normalizada and exp.alt == "<STR45>"


def test_esperado_dos_cenarios():
    e = cenarios.cenario_por_numero(4).esperado
    assert e.heranca.tolist() == ["recessiva"] and e.p_portador_exato.tolist() == [0.25]
    e3 = cenarios.cenario_por_numero(3).esperado.set_index("gene")
    assert e3.loc["SOD1", "dosagem_pai"] == 1 and e3.loc["C9orf72", "dosagem_mae"] == 1   # C9orf72 vem do laudo
    assert cenarios.laudo_da_linha({"c9orf72_mae": 45, "c9orf72_pai": pd.NA}) == {"mae": 45}
    with pytest.raises(KeyError):
        cenarios.cenario_por_numero(9)


# ---------------------------------------------------------------------------
# TCC 4.2.1, "quatro cuidados": montagem, normalização, multialélicos (acima), QUAL vs GQ (filtro)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pos,ref,alt,esperado", [
    (10, "C", "T", (10, "C", "T", False)),                 # SNV já parcimoniosa
    (10, "CAT", "CAG", (12, "T", "G", True)),              # prefixo comum removido, POS desloca
    (10, "CATG", "CG", (11, "AT", "", False)),             # ← placeholder, substituído abaixo
    (10, "GAC", "GACAC", (10, "G", "GAC", True)),           # sufixo comum "AC" sai; prefixo "G" fica (≥ 1 base)
    (10, "ACGT", "ACGA", (13, "T", "A", True)),
    (10, "A", "<DEL>", (10, "A", "<DEL>", False)),         # simbólico intocado
])
def test_normalizar_alelos(pos, ref, alt, esperado):
    if ref == "CATG":      # deleção: sufixo "G" sai, prefixo "C" sai mantendo ≥ 1 base
        esperado = (10, "CAT", "C", True)
    assert ingestao.normalizar_alelos(pos, ref, alt) == esperado


def _vcf_minimo(tmp_path, cabecalho_extra: list[str], registro: str = "chr21\t31659783\trs121912442\tC\tT\t99\tPASS\tAC=1;AN=2;DB\tGT:DP:GQ\t0/1:40:90"):
    linhas = ["##fileformat=VCFv4.2", *cabecalho_extra,
              '##INFO=<ID=AC,Number=A,Type=Integer,Description="x">', '##INFO=<ID=AN,Number=1,Type=Integer,Description="x">',
              '##INFO=<ID=DB,Number=0,Type=Flag,Description="x">', '##FORMAT=<ID=GT,Number=1,Type=String,Description="x">',
              '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="x">', '##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="x">',
              "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1", registro]
    p = tmp_path / "m.vcf"
    p.write_text("\n".join(linhas) + "\n")
    return p


def test_montagem_grch37_e_rejeitada(tmp_path):
    p = _vcf_minimo(tmp_path, ["##reference=file:///refs/human_g1k_v37.fasta", "##contig=<ID=21,length=48129895>"])
    with pytest.raises(ingestao.MontagemDivergente, match="GRCh37"):
        ingestao.ler_vcf(p)
    df = ingestao.ler_vcf(p, montagem_esperada=None)          # conferência desligada: lê e marca a montagem
    assert df.montagem.iloc[0] == "GRCh37"


def test_montagem_inferida_pelo_contig(tmp_path):
    p = _vcf_minimo(tmp_path, ["##contig=<ID=chr21,length=46709983>"])
    df = ingestao.ler_vcf(p)
    assert df.montagem.iloc[0] == "GRCh38" and "contig" in df.attrs["vcf"]["evidencia"]


def test_montagem_desconhecida_avisa(tmp_path):
    p = _vcf_minimo(tmp_path, [])
    with pytest.warns(UserWarning, match="montagem"):
        df = ingestao.ler_vcf(p)
    assert df.montagem.iloc[0] == "desconhecida" and df.aprovado.all()


def test_normalizacao_na_leitura(tmp_path):
    # mesma substituição descrita de forma redundante: pos 31659782 "AC>AT" ≡ pos 31659783 "C>T"
    p = _vcf_minimo(tmp_path, ["##reference=GRCh38"], "chr21\t31659782\t.\tAC\tAT\t99\tPASS\tAC=1;AN=2\tGT:DP:GQ\t0/1:40:90")
    df = ingestao.ler_vcf(p)
    r = df.iloc[0]
    assert (r.posicao, r.ref, r.alt, bool(r.normalizada)) == (31659783, "C", "T", True)
    assert (r.posicao_vcf, r.ref_vcf, r.alt_vcf) == (31659782, "AC", "AT") and r.tipo == "snv"
    assert r.no_dbsnp is False or r.no_dbsnp == False  # noqa: E712  (DB declarado no cabeçalho, ausente no registro)
    assert ingestao.resumo_ingestao(df)["normalizadas"] == 1


def test_amostra_multiamostra(tmp_path):
    linhas = ["##fileformat=VCFv4.2", "##reference=GRCh38", '##FORMAT=<ID=GT,Number=1,Type=String,Description="x">',
              "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tMAE\tPAI", "chr21\t31659783\trs121912442\tC\tT\t99\tPASS\t.\tGT\t0/0\t0/1"]
    p = tmp_path / "trio.vcf"; p.write_text("\n".join(linhas) + "\n")
    assert ingestao.ler_vcf(p, amostra="PAI").dosagem.item() == 1 and ingestao.ler_vcf(p, amostra="MAE").dosagem.item() == 0
    with pytest.raises(ValueError, match="amostra"):
        ingestao.ler_vcf(p, amostra="FILHO")
