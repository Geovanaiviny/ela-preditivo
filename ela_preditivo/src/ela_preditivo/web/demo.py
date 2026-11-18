"""Comandos administrativos: criar administrador (só por CLI) e popular a demonstração com registros fictícios dos três
casos (pessoa, casal e família), VCFs sintéticos anexados, consentimentos e análises de exemplo. Dois registros mostram
o genitor sem exame inferido por parentes: uma pessoa com o pai falecido e a avó testada, e uma família com um filho
que já fez o teste."""

from __future__ import annotations

import json
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auditoria, textos
from .bd import agora
from .. import DIR_DADOS, cenarios
from . import arquivos, vcfs
from .modelos import (
    AceiteTermo,
    Descendente,
    Documento,
    Genitor,
    Paciente,
    Parente,
    PerfilMedico,
    PerfilPesquisador,
    Usuario,
)
from .seguranca import Cifra, hash_senha, normalizar_cpf, normalizar_email, validar_cpf, validar_senha


def _cpf_valido(semente: int) -> str:
    """CPF sintático válido gerado de uma semente (só para a demonstração)."""
    import random

    rng = random.Random(semente)
    while True:
        base = [rng.randint(0, 9) for _ in range(9)]
        if len(set(base)) == 1:
            continue
        for i in (9, 10):
            soma = sum(base[j] * ((i + 1) - j) for j in range(i))
            dv = (soma * 10) % 11
            base.append(0 if dv == 10 else dv)
        cpf = "".join(map(str, base))
        if validar_cpf(cpf):
            return cpf


def _senha() -> str:
    return "Demo-" + secrets.token_urlsafe(9)


def criar_usuario(
    bd: Session,
    cifra: Cifra,
    *,
    nome: str,
    cpf: str,
    email: str,
    senha: str,
    papel: str,
    situacao: str,
    perfil: dict | None = None,
    trocar_senha: bool = False,
) -> Usuario:
    cpf = normalizar_cpf(cpf)
    email = normalizar_email(email)
    if not validar_cpf(cpf):
        raise ValueError("CPF inválido")
    erro = validar_senha(senha, email, cpf)
    if erro:
        raise ValueError(erro)
    if bd.execute(select(Usuario.id).where(Usuario.email == email)).first():
        raise ValueError(f"já existe usuário com o e-mail {email}")
    if bd.execute(select(Usuario.id).where(Usuario.cpf_hmac == cifra.hmac_cpf(cpf))).first():
        raise ValueError("já existe usuário com este CPF")
    hoje = agora()
    u = Usuario(
        nome=nome,
        email=email,
        cpf_cifrado=cifra.cifrar(cpf),
        cpf_hmac=cifra.hmac_cpf(cpf),
        senha_hash=hash_senha(senha),
        papel=papel,
        situacao=situacao,
        criado_em=hoje,
        atualizado_em=hoje,
        verificado_em=hoje if situacao == "VERIFICADO" else None,
        trocar_senha=trocar_senha,  # senha temporária: a conta só serve para definir a senha de uso
    )
    perfil = perfil or {}
    if papel == "MEDICO":
        u.perfil_medico = PerfilMedico(**{"tipo": "CRM", **perfil})
    elif papel == "PESQUISADOR":
        u.perfil_pesquisador = PerfilPesquisador(**{"tipo": "INSTITUCIONAL", **perfil})
    u.aceites = [
        AceiteTermo(documento="AVISO_PRIVACIDADE", versao=textos.VERSAO_AVISO_PRIVACIDADE, aceito_em=hoje),
        AceiteTermo(documento="TERMO_USO", versao=textos.VERSAO_TERMO_USO, aceito_em=hoje),
    ]
    bd.add(u)
    bd.flush()
    return u


def criar_admin(
    bd: Session,
    cifra: Cifra,
    nome: str,
    cpf: str,
    email: str,
    senha: str,
    detalhe: str = "via CLI",
    trocar_senha: bool = False,
) -> Usuario:
    """Administrador criado pela linha de comando. Pela interface: primeiro acesso ou outro administrador
    (`primeiro_acesso.criar_administrador`). Ninguém se cadastra nem é promovido a administrador."""
    u = criar_usuario(
        bd,
        cifra,
        nome=nome,
        cpf=cpf,
        email=email,
        senha=senha,
        papel="ADMIN",
        situacao="VERIFICADO",
        trocar_senha=trocar_senha,
    )
    auditoria.registrar(bd, acao=auditoria.ADMIN_CRIADO, usuario=u, alvo_tipo="usuario", alvo_id=u.id, detalhe=detalhe)
    bd.commit()
    return u


# Um registro por cenário sintético; nomes, datas e prontuários são fictícios. (`vcf`: número do cenário cujo VCF se anexa;
# None = genitor sem exame, para demonstrar a suposição de não portador.)
# Laudo normal explícito do C9orf72 (derivado do YAML, `cenarios.LAUDO_NORMAL`) para os genitores fictícios cujo cenário
# não envolve o gene: sem laudo o genitor seria "não testado" e o lócus ficaria indeterminado.
LAUDO_NORMAL_DEMO = str(cenarios.LAUDO_NORMAL)
REGISTROS_FICTICIOS = [
    {
        "tipo": "PESSOA",
        "prontuario": "DEMO-0001",
        "momento": "APOS_LAUDO",
        "mae": {"nome": "Maria Fictícia Lima", "nascimento": "1968-05-20", "laudo": LAUDO_NORMAL_DEMO, "vcf": 1},
        "pai": {"nome": "José Fictício Lima", "nascimento": "1965-02-11", "laudo": LAUDO_NORMAL_DEMO, "vcf": 1},
        "descendentes": [{"nome": "Ana Fictícia Lima", "nascimento": "1996-03-12", "sexo": "F"}],
        "observacoes": "Cenário 1 de demonstração: pai heterozigoto SOD1 p.Ala5Val × mãe sem variante. Registro fictício.",
        "consentir": True,
        "analisar": True,
    },
    {
        "tipo": "PESSOA",
        "prontuario": "DEMO-0002",
        "momento": "APOS_LAUDO",
        "mae": {"nome": "Clara Fictícia Souza", "nascimento": "1958-09-03", "laudo": "45", "vcf": 2},
        "pai": {"nome": "Pedro Fictício Souza", "nascimento": "1955-12-30", "laudo": LAUDO_NORMAL_DEMO, "vcf": 2},
        "descendentes": [{"nome": "Bruno Fictício Souza", "nascimento": "1984-07-30", "sexo": "M"}],
        "observacoes": "Cenário 2 de demonstração: mãe com expansão do C9orf72 (45 repetições, laudo) × pai sem variante. Registro fictício.",
        "consentir": False,
        "analisar": False,
    },
    {
        "tipo": "PESSOA",
        "prontuario": "DEMO-0003",
        "momento": "ACOMPANHAMENTO",
        "mae": {"nome": "Helena Fictícia Alves", "nascimento": "1970-01-15", "laudo": "45", "vcf": 3},
        "pai": {"nome": "Marcos Fictício Alves", "nascimento": "1966-07-07", "laudo": LAUDO_NORMAL_DEMO, "vcf": 3},
        "descendentes": [{"nome": "Carla Fictícia Alves", "nascimento": "1996-11-02", "sexo": "F"}],
        "observacoes": "Cenário 3 de demonstração (exemplo literal do TCC, 4.5): pai SOD1 p.Ala5Val × mãe com expansão do C9orf72. Registro fictício.",
        "consentir": True,
        "analisar": True,
    },
    {
        "tipo": "FAMILIA",
        "nome": "Família Fictícia Ramos",
        "prontuario": "DEMO-0004",
        "momento": "ANTES_DO_TESTE",
        "mae": {"nome": "Rosa Fictícia Ramos", "nascimento": "1948-03-01", "laudo": LAUDO_NORMAL_DEMO, "vcf": 4},
        "pai": {"nome": "Antônio Fictício Ramos", "nascimento": "1945-10-22", "laudo": LAUDO_NORMAL_DEMO, "vcf": 4},
        "descendentes": [
            {"nome": "Diego Fictício Ramos", "nascimento": "1971-01-19", "sexo": "M"},
            {"nome": "Lívia Fictícia Ramos", "nascimento": "1975-06-30", "sexo": "F"},
        ],
        "observacoes": "Cenário 4 de demonstração: ambos os pais heterozigotos para SOD1 p.Asp91Ala (herança recessiva); dois filhos. Registro fictício.",
        "consentir": False,
        "analisar": True,
    },
    {
        "tipo": "PESSOA",
        "prontuario": "DEMO-0005",
        "momento": "ANTES_DO_TESTE",
        "mae": {"nome": "Luísa Fictícia Prado", "nascimento": "1982-04-18", "laudo": LAUDO_NORMAL_DEMO, "vcf": 5},
        "pai": {"nome": "Rafael Fictício Prado", "nascimento": "1980-11-02", "laudo": LAUDO_NORMAL_DEMO, "vcf": 5},
        "descendentes": [{"nome": "Elisa Fictícia Prado", "nascimento": "2004-09-08", "sexo": "F"}],
        "observacoes": "Cenário 5 de demonstração: pai TARDBP p.Met337Val × mãe FUS p.Arg521Cys. Registro fictício.",
        "consentir": False,
        "analisar": False,
    },
    {
        "tipo": "CASAL",
        "prontuario": "DEMO-0006",
        "momento": "ANTES_DO_TESTE",
        "mae": {"nome": "Fernanda Fictícia Nunes", "nascimento": "1990-08-14", "laudo": "45", "vcf": "casal_1_mae"},
        "pai": {"nome": "Gustavo Fictício Nunes", "nascimento": "1988-03-03", "laudo": None, "vcf": None},
        "descendentes": [],
        "observacoes": "Casal que planeja filhos: parceira com expansão do C9orf72 (laudo e VCF do cenário 2); parceiro sem exame, assumido não portador na análise. Registro fictício.",
        "consentir": True,
        "analisar": True,
    },
    {
        "tipo": "PESSOA",
        "prontuario": "DEMO-0007",
        "momento": "ANTES_DO_TESTE",
        "mae": {
            "nome": "Tereza Fictícia Moraes",
            "nascimento": "1962-06-10",
            "laudo": LAUDO_NORMAL_DEMO,
            "vcf": "parentes_1_mae",
        },
        "pai": {
            "nome": "Otávio Fictício Moraes",
            "nascimento": "1958-01-25",
            "laudo": None,
            "vcf": None,
            "situacao": {"situacao": "FALECIDO_SEM_ELA", "idade": 60},
            "parentes": [{"parentesco": "MAE_DO_GENITOR", "vcf": "parentes_1_avo_paterna", "laudo": LAUDO_NORMAL_DEMO}],
        },
        "descendentes": [{"nome": "Heitor Fictício Moraes", "nascimento": "1988-04-02", "sexo": "M"}],
        "observacoes": "Cenário de parentes 1 de demonstração: pai falecido sem ELA aos 60 anos, sem exame; avó paterna testada, heterozigota SOD1 p.Ala5Val; mãe testada, sem a variante. Registro fictício.",
        "consentir": False,
        "analisar": True,
    },
    {
        "tipo": "FAMILIA",
        "nome": "Família Fictícia Teles",
        "prontuario": "DEMO-0008",
        "momento": "APOS_LAUDO",
        "mae": {
            "nome": "Vera Fictícia Teles",
            "nascimento": "1966-09-12",
            "laudo": LAUDO_NORMAL_DEMO,
            "vcf": "parentes_2_mae",
        },
        "pai": {
            "nome": "Nelson Fictício Teles",
            "nascimento": "1964-03-18",
            "laudo": None,
            "vcf": None,
            "situacao": {"situacao": "VIVO_ASSINTOMATICO", "idade": 62},
            "parentes": [{"parentesco": "MAE_DO_GENITOR", "vcf": "parentes_2_avo_paterna", "laudo": LAUDO_NORMAL_DEMO}],
        },
        "descendentes": [
            {"nome": "Íris Fictícia Teles", "nascimento": "1990-02-27", "sexo": "F", "vcf": "parentes_2_filho_testado"},
            {"nome": "Jonas Fictício Teles", "nascimento": "1993-08-05", "sexo": "M"},
        ],
        "observacoes": "Cenário de parentes 2 de demonstração: pai sem exame, vivo sem sintomas aos 62 anos; avó paterna testada, heterozigota SOD1 p.Ala5Val; mãe testada, sem a variante; a filha mais velha já fez o teste (sem a variante) e entra como evidência. Registro fictício.",
        "consentir": False,
        "analisar": True,
    },
]
# Todo dado identificável da demonstração, para os testes conferirem que nada disso vaza ao pesquisador ou à auditoria
DADOS_IDENTIFICAVEIS = sorted(
    {
        x
        for r in REGISTROS_FICTICIOS
        for x in [
            r.get("nome"),
            r["prontuario"],
            r["mae"]["nome"],
            r["mae"]["nascimento"],
            r["pai"]["nome"],
            r["pai"]["nascimento"],
        ]
        + [d["nome"] for d in r["descendentes"]]
        + [d["nascimento"] for d in r["descendentes"]]
        if x
    }
)
NOMES_FICTICIOS = [
    r.get("nome") or r["descendentes"][0]["nome"] if r["descendentes"] else f"{r['mae']['nome']} e {r['pai']['nome']}"
    for r in REGISTROS_FICTICIOS
]


def pdf_ficticio(linhas: list[str]) -> bytes:
    """PDF mínimo e válido (uma página, texto em Helvetica), gerado sem biblioteca externa, para documentos de demonstração."""
    texto = "\n".join(linhas)
    conteudo = (
        "BT /F1 12 Tf 50 780 Td 16 TL "
        + " ".join(
            "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for l in texto.split("\n")
        )
        + " ET"
    )
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(conteudo.encode('latin-1', 'replace'))} >>\nstream\n{conteudo}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    saida = "%PDF-1.4\n"
    posicoes = []
    for i, obj in enumerate(objetos, start=1):
        posicoes.append(len(saida.encode("latin-1", "replace")))
        saida += f"{i} 0 obj\n{obj}\nendobj\n"
    xref = len(saida.encode("latin-1", "replace"))
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n" + "".join(
        f"{pos:010d} 00000 n \n" for pos in posicoes
    )
    saida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return saida.encode("latin-1", "replace")


def anexar_documento_demo(
    bd: Session, cifra: Cifra, config, p: Paciente, tipo: str, linhas: list[str], genitor=None
) -> None:
    dados = pdf_ficticio(linhas)
    bd.add(
        Documento(
            paciente=p,
            genitor_id=genitor.id if genitor is not None else None,
            tipo=tipo,
            nome_original_cifrado=cifra.cifrar(
                ("prontuario" if tipo == "PRONTUARIO" else "laudo_c9orf72") + "_ficticio.pdf"
            ),
            mime="application/pdf",
            arquivo=arquivos.guardar(config.dir_documentos, cifra, dados),
            tamanho=len(dados),
            hash=arquivos.sha256(dados),
            enviado_em=agora(),
        )
    )


def _vcf_sintetico(referencia, lado: str):
    """VCF sintético versionado: número do cenário (arquivo do lado) ou nome do arquivo de parentes ou de casal."""
    if isinstance(referencia, int):
        return cenarios.vcf_cenario(DIR_DADOS / "sinteticos", referencia, lado)
    return cenarios.vcf_sintetico(DIR_DADOS / "sinteticos", referencia)


def criar_registro(bd: Session, cifra: Cifra, config, medico: Usuario, r: dict) -> Paciente:
    """Cria um registro fictício com genitores, descendentes e, quando indicado, os VCFs sintéticos do cenário."""
    hoje = agora()
    nome = r.get("nome")
    if not nome:
        nome = r["descendentes"][0]["nome"] if r["descendentes"] else f"{r['mae']['nome']} e {r['pai']['nome']}"
    p = Paciente(
        medico_id=medico.id,
        tipo=r["tipo"],
        nome_cifrado=cifra.cifrar(nome),
        prontuario_cifrado=cifra.cifrar(r["prontuario"]),
        momento=r.get("momento"),
        observacoes_cifradas=cifra.cifrar(r.get("observacoes")),
        criado_em=hoje,
        atualizado_em=hoje,
    )
    for papel, lado in (("MAE", "mae"), ("PAI", "pai")):
        g = r[lado]
        p.genitores.append(
            Genitor(
                papel=papel,
                nome_cifrado=cifra.cifrar(g["nome"]),
                data_nascimento_cifrada=cifra.cifrar(g["nascimento"]),
                laudo_c9orf72_cifrado=cifra.cifrar(g.get("laudo")),
                atualizado_em=hoje,
            )
        )
    for i, d in enumerate(r["descendentes"], start=1):
        p.descendentes.append(
            Descendente(
                ordem=i,
                nome_cifrado=cifra.cifrar(d["nome"]),
                data_nascimento_cifrada=cifra.cifrar(d["nascimento"]),
                sexo=d["sexo"],
                atualizado_em=hoje,
            )
        )
    bd.add(p)
    bd.flush()
    for papel, lado in (("MAE", "mae"), ("PAI", "pai")):
        num = r[lado].get("vcf")
        if num is not None:
            origem = _vcf_sintetico(num, lado)
            if origem.exists():
                vcfs.anexar(config, cifra, p.genitor(papel), origem)
        # genitor sem exame: situação clínica e parentes testados (o VCF segue as mesmas regras dos genitores)
        if r[lado].get("situacao"):
            p.genitor(papel).situacao_clinica_cifrada = cifra.cifrar(json.dumps(r[lado]["situacao"]))
        for x in r[lado].get("parentes") or []:
            parente = Parente(
                papel_genitor=papel,
                parentesco=x["parentesco"],
                laudo_c9orf72_cifrado=cifra.cifrar(x.get("laudo")),
                criado_em=hoje,
                atualizado_em=hoje,
            )
            origem = _vcf_sintetico(x["vcf"], lado) if x.get("vcf") else None
            if origem is not None and origem.exists():
                vcfs.anexar(config, cifra, parente, origem)
            p.parentes.append(parente)
        if r[lado].get("laudo"):
            anexar_documento_demo(
                bd,
                cifra,
                config,
                p,
                "LAUDO_C9ORF72",
                [
                    "LAUDO FICTICIO - DEMONSTRACAO",
                    f"Genitor: {papel}",
                    f"C9orf72: {r[lado]['laudo']} repeticoes GGGGCC",
                    "Sem valor clinico.",
                ],
                genitor=p.genitor(papel),
            )
    for d, dados in zip(p.descendentes, r["descendentes"]):  # filho que já fez o teste (caso de família)
        if dados.get("vcf"):
            origem = _vcf_sintetico(dados["vcf"], "")
            if origem.exists():
                vcfs.anexar(config, cifra, d, origem)
    anexar_documento_demo(
        bd,
        cifra,
        config,
        p,
        "PRONTUARIO",
        [
            "PRONTUARIO FICTICIO - DEMONSTRACAO",
            f"Numero: {r['prontuario']}",
            f"Caso: {r['tipo']}",
            "Documento sem valor clinico.",
        ],
    )
    bd.flush()
    return p


def popular(bd: Session, cifra: Cifra, config, analisar: bool = True) -> dict:
    """Um usuário verificado de cada papel, um cadastro pendente de cada tipo e oito registros fictícios do médico
    (cinco pessoas, duas famílias e um casal), com VCFs sintéticos, consentimentos e análises. Dois deles têm o pai sem
    exame, inferido por parentes: a avó testada e, numa das famílias, um filho que já fez o teste.

    Recusa rodar se já houver médico ou pesquisador, ou se a demonstração já foi criada; administradores podem
    existir. Devolve as credenciais geradas (mostradas uma vez pela interface ou pela CLI, nunca gravadas em claro).
    """
    if bd.execute(select(func.count(Usuario.id)).where(Usuario.papel != "ADMIN")).scalar_one() > 0:
        raise RuntimeError("o banco já tem médicos ou pesquisadores; a demonstração só é criada antes deles")
    if bd.execute(select(Usuario.id).where(Usuario.email == "admin@demo.local")).first():
        raise RuntimeError("a demonstração já foi criada neste banco")
    credenciais = []

    def _novo(nome, email, papel, situacao, perfil=None, mensagem=None):
        senha = _senha()
        u = criar_usuario(
            bd,
            cifra,
            nome=nome,
            cpf=_cpf_valido(len(credenciais) + 1),
            email=email,
            senha=senha,
            papel=papel,
            situacao=situacao,
            perfil=perfil,
        )
        u.mensagem_admin = mensagem
        credenciais.append({"papel": papel, "situacao": situacao, "nome": nome, "email": email, "senha": senha})
        return u

    admin = _novo("Administrador de Demonstração", "admin@demo.local", "ADMIN", "VERIFICADO")
    medico = _novo(
        "Dra. Demonstração Médica",
        "medico@demo.local",
        "MEDICO",
        "VERIFICADO",
        {"tipo": "CRM", "crm": "123456", "uf": "SP", "especialidade": "Neurologia / genética médica"},
    )
    _novo(
        "Pesquisador de Demonstração",
        "pesquisador@demo.local",
        "PESQUISADOR",
        "VERIFICADO",
        {
            "tipo": "INSTITUCIONAL",
            "instituicao": "Universidade de Demonstração",
            "grupo": "Grupo de Neurogenética",
            "cargo": "Doutorando(a)",
            "linha_pesquisa": "Modelagem estocástica de doenças neurodegenerativas",
            "orcid": "0000-0002-1825-0097",
        },
    )
    _novo(
        "Aconselhador Pendente",
        "medico.pendente@demo.local",
        "MEDICO",
        "PENDENTE",
        {
            "tipo": "ACONSELHADOR",
            "formacao": "Biomedicina, especialização em aconselhamento genético",
            "instituicao": "Hospital de Demonstração",
        },
    )
    _novo(
        "Pesquisadora Pendente",
        "pesquisador.pendente@demo.local",
        "PESQUISADOR",
        "INFORMACOES_SOLICITADAS",
        {
            "tipo": "INDEPENDENTE",
            "cargo": "Pesquisadora independente",
            "linha_pesquisa": "Epidemiologia genética da ELA",
            "evidencias": "https://exemplo.invalid/publicacao-1",
        },
        mensagem="Informe o vínculo com projeto de pesquisa aprovado por comitê de ética, se houver, e um link para publicação.",
    )
    registros = [criar_registro(bd, cifra, config, medico, r) for r in REGISTROS_FICTICIOS]
    n_vcfs = sum(1 for p in registros for x in list(p.genitores) + list(p.parentes) + list(p.descendentes) if x.tem_vcf)
    bd.flush()

    # consentimentos (nunca pré-marcados na interface; aqui a demonstração registra em nome de cada titular fictício)
    from .modelos import Consentimento
    from .pacientes import atualizar_liberacao, idades

    for p, r in zip(registros, REGISTROS_FICTICIOS):
        if not r["consentir"]:
            continue
        titulares = [
            ("MAE", None, cifra.decifrar(p.genitor("MAE").nome_cifrado)),
            ("PAI", None, cifra.decifrar(p.genitor("PAI").nome_cifrado)),
        ]
        if p.tipo != "CASAL":
            idd = idades(p, cifra)
            for d in p.descendentes:
                t = "RESPONSAVEL" if idd[d.id] < 18 else "DESCENDENTE"
                nome_t = (
                    cifra.decifrar(p.genitor("MAE").nome_cifrado)
                    if t == "RESPONSAVEL"
                    else cifra.decifrar(d.nome_cifrado)
                )
                titulares.append((t, d.id, nome_t))
        for t, did, nome_t in titulares:
            bd.add(
                Consentimento(
                    paciente=p,
                    descendente_id=did,
                    titular=t,
                    nome_titular_cifrado=cifra.cifrar(nome_t),
                    versao_termo=textos.VERSAO_TERMO_CONSENTIMENTO_PESQUISA,
                    concedido_em=agora(),
                    registrado_por_id=medico.id,
                )
            )
        bd.flush()
        bd.refresh(p)
        atualizar_liberacao(bd, p, cifra, medico)
    bd.flush()

    # análises de exemplo (NumPy, N pequeno), para que ficha, filtros e lista do pesquisador tenham conteúdo
    n_analises = 0
    if analisar:
        from .analises import Execucao, RegistroAnalises, executar_para_registro

        registro_an = RegistroAnalises(config)
        try:
            for p, r in zip(registros, REGISTROS_FICTICIOS):
                if not r["analisar"]:
                    continue
                assumir = frozenset(papel for papel in ("MAE", "PAI") if not p.genitor(papel).tem_vcf)
                alvos = [d for d in p.descendentes if not d.tem_vcf] if p.tipo != "CASAL" else [None]
                for d in alvos:  # o filho que já fez o teste é evidência, não pessoa em risco
                    # registros fictícios: todos declarados sem sintomas (confirmação exigida para pessoa analisada)
                    exec_ = Execucao(
                        n=2000, seed=42, motor="numpy", cox=False, assumir=assumir, assintomatico=d is not None
                    )
                    executar_para_registro(bd, config, cifra, registro_an, medico, p, d, exec_)
                    n_analises += 1
        finally:
            registro_an.encerrar()

    auditoria.registrar(
        bd,
        acao=auditoria.DEMO_POPULADA,
        usuario=admin,
        detalhe=f"{len(credenciais)} usuários, {len(registros)} registros fictícios, {n_vcfs} VCFs, {n_analises} análises",
    )
    bd.commit()
    return {"credenciais": credenciais, "pacientes": len(registros), "vcfs": n_vcfs, "analises": n_analises}
