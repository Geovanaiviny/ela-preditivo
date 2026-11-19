"""Textos legais da plataforma, com versão (LGPD, Lei 13.709/2018). Alterar o texto = nova versão = novo aceite."""

from __future__ import annotations

from .. import AVISO_LEGAL  # noqa: F401 - continua disponível à API e ao relatório

VERSAO_AVISO_PRIVACIDADE = "2026-11-16"
VERSAO_TERMO_USO = "2026-11-16"
VERSAO_TERMO_CONSENTIMENTO_PESQUISA = "2026-11-16"

MARCA = "EloSense"
MARCA_SUBTITULO = "Plataforma clínica"
SELO_DEMONSTRACAO = "Ambiente de homologação: todos os pacientes são fictícios."
DESCRICAO_SISTEMA = (
    "O EloSense apoia o aconselhamento genético preditivo da esclerose lateral amiotrófica (ELA): a partir dos "
    "arquivos genéticos (VCF) da mãe e do pai, estima a probabilidade de um descendente herdar e manifestar variantes "
    "associadas à doença em quatro genes, e a idade provável de início. Quando um genitor não pôde ser testado, aceita "
    "o genótipo de parentes dele. O resultado é lido e interpretado por profissional habilitado, com o histórico "
    "clínico da família; não constitui diagnóstico."
)

# Os três casos que o artefato atende (texto do orientador). O rótulo aparece em todas as telas do registro.
TIPOS_ATENDIMENTO = {
    "PESSOA": {
        "numero": 1,
        "rotulo": "Caso 1 · Pessoa assintomática com histórico familiar",
        "curto": "Pessoa com histórico familiar",
        "descricao": (
            "Um filho, irmão ou sobrinho de alguém com a variante quer saber se herdou, qual a chance de adoecer e "
            "em que idade isso tende a acontecer. É o público central do artefato."
        ),
        "responde": ["se herdou a variante", "a chance de a doença se manifestar", "a idade provável de início"],
        "registro": "a pessoa atendida (descendente) e seus genitores, mãe e pai, titulares dos VCFs",
    },
    "CASAL": {
        "numero": 2,
        "rotulo": "Caso 2 · Casal ou pessoa que planeja filhos",
        "curto": "Casal que planeja filhos",
        "descricao": (
            "A probabilidade de transmissão a um futuro filho é o resultado que mais interessa. O artefato calcula "
            "também a chance de manifestação e a idade provável de início para esse futuro filho. Decisões "
            "reprodutivas, como diagnóstico pré-implantacional, ficam fora do escopo."
        ),
        "responde": [
            "a probabilidade de transmissão (futuro filho herdar ao menos uma variante)",
            "a chance de a doença se manifestar no futuro filho",
            "a idade provável de início",
        ],
        "registro": "os dois parceiros (futura mãe e futuro pai), titulares dos VCFs; não há descendente cadastrado",
    },
    "FAMILIA": {
        "numero": 3,
        "rotulo": "Caso 3 · Família de genitor com variante confirmada",
        "curto": "Família com variante confirmada",
        "descricao": (
            "Quando o laboratório confirma a variante em um dos genitores, a família quer avaliar o risco de cada "
            "filho. É o caso para o qual o artefato foi desenhado: uma análise por filho e um comparativo."
        ),
        "responde": ["se cada filho herdou", "a chance de manifestação de cada filho", "a idade provável de início"],
        "registro": "os genitores (ao menos um testado) e cada filho, com sexo e data de nascimento",
    },
}
MOMENTOS = {
    "ANTES_DO_TESTE": "Antes do teste ou da consulta",
    "APOS_LAUDO": "Depois do laudo laboratorial",
    "ACOMPANHAMENTO": "Acompanhamento de portador assintomático",
}
ROTULO_GENITOR = {
    "PESSOA": {"MAE": "Mãe", "PAI": "Pai"},
    "FAMILIA": {"MAE": "Mãe", "PAI": "Pai"},
    "CASAL": {"MAE": "Parceira (futura mãe)", "PAI": "Parceiro (futuro pai)"},
}
# Genitor sem VCF, sem parente testado e sem a suposição declarada: o texto com que a análise é recusada e que a
# ficha mostra antes do clique
GENITOR_SEM_VCF = (
    "{rotulo} sem VCF anexado: anexe o arquivo na ficha, adicione um parente testado ou marque a suposição de não "
    "portador."
)
ROTULO_TITULAR = {
    "MAE": "Mãe",
    "PAI": "Pai",
    "DESCENDENTE": "Paciente",
    "RESPONSAVEL": "Responsável legal",
    "PARENTE": "Parente testado",
}
DESCRICAO_PESQUISA = (
    "Registros de pacientes disponíveis para pesquisa, com as informações referentes à doença: variantes encontradas "
    "nos VCFs dos genitores, laudo do C9orf72, dosagens por lócus e resultados das análises. A identificação é "
    "substituída por um código."
)
SUPOSICAO_NAO_PORTADOR = (
    "Genitor sem exame assumido sem variante de risco (dosagem zero em todos os genes). O resultado depende dessa "
    "suposição e deve ser lido como limite inferior: se esse genitor for portador, o risco é maior."
)
SUPOSICAO_LAUDO_SEM_VCF = (
    "Genitor sem VCF: só o laudo do C9orf72 foi considerado; os demais genes desse genitor foram tratados como sem "
    "variante de risco."
)
SUPOSICAO_LAUDO_NORMAL = (
    "Genitor sem exame e sem o nº de repetições do C9orf72 na ficha: também assumido sem expansão (laudo normal "
    "suposto, abaixo da faixa intermediária). Com o laudo em mãos, digite o nº de repetições na ficha e repita a "
    "análise."
)
C9ORF72_INDETERMINADO = (
    "O modelo usa o nº de repetições do C9orf72 digitado na ficha; o arquivo do laudo fica guardado como documento e "
    "não é lido. Genitor sem esse número é tratado como não testado: o lócus do C9orf72 fica indeterminado, sai do "
    "cálculo e o resultado é parcial para esse gene. Digite na ficha o nº de repetições que consta no laudo e repita "
    "a análise."
)
# genitor sem o nº de repetições: o aviso separa quem tem o arquivo do laudo anexado de quem não tem laudo nenhum
LAUDO_ARQUIVO_SEM_NUMERO = "{rotulo}: o arquivo do laudo está anexado, mas o nº de repetições não foi digitado."
LAUDO_AUSENTE = "{rotulo}: sem laudo do C9orf72 (nem o nº de repetições, nem o arquivo)."


def _genitores_sem_numero(sem_numero: dict | None, tipo: str | None, papeis) -> list[str]:
    rotulos = ROTULO_GENITOR.get(tipo or "PESSOA", ROTULO_GENITOR["PESSOA"])
    return [
        (LAUDO_ARQUIVO_SEM_NUMERO if (sem_numero or {}).get(papel) else LAUDO_AUSENTE).format(rotulo=rotulos[papel])
        for papel in ("MAE", "PAI")
        if papel in (sem_numero or {}) and papel in papeis
    ]


def c9orf72_indeterminado(sem_numero: dict | None = None, tipo: str | None = None, supostos=()) -> str:
    """Aviso do resultado parcial para o C9orf72. `sem_numero` traz os genitores sem o nº de repetições e diz se o
    arquivo do laudo de cada um está anexado; os cobertos pela suposição de laudo normal (`supostos`) ficam de fora."""
    quem = _genitores_sem_numero(sem_numero, tipo, [p for p in ("MAE", "PAI") if p not in supostos])
    return " ".join([*quem, C9ORF72_INDETERMINADO])


def suposicao_laudo_normal(sem_numero: dict | None = None, tipo: str | None = None, supostos=()) -> str:
    """Texto da suposição de laudo normal; avisa quando o arquivo do laudo do genitor suposto está anexado."""
    com_arquivo = {p: True for p in supostos if (sem_numero or {}).get(p)}
    return " ".join([SUPOSICAO_LAUDO_NORMAL, *_genitores_sem_numero(com_arquivo, tipo, supostos)])


CONFIRMACAO_ASSINTOMATICO = "Confirmo que a pessoa analisada não apresenta sintomas de ELA"
ERRO_CONFIRMACAO_ASSINTOMATICO = (
    "Confirme que a pessoa analisada não apresenta sintomas de ELA: o condicionamento pela idade só vale para quem "
    "não manifestou a doença. Sem a confirmação, a análise não é executada."
)
EXPLICACAO_CONDICIONADO = (
    "Com a idade atual informada, os três indicadores valem para a pessoa sem sintomas a partir dessa idade: a chance "
    "de portar a variante, o risco de manifestar daqui em diante e a idade provável de início entre quem vai manifestar."
)
FORA_DO_ESCOPO = [
    "Pessoas já sintomáticas ou com diagnóstico: o condicionamento pela idade só vale para quem não manifestou a "
    "doença, e o problema delas é prognóstico clínico, outro produto com outra validação.",
    "Números agregados da família, como a chance de pelo menos um filho manifestar: cada pessoa é analisada em separado.",
    'Fenótipo de parente sem genótipo (por exemplo, "meu tio teve ELA", sem teste genético): só o genótipo de '
    "parentes entra no cálculo.",
    "Ancestralidade: as estimativas de penetrância vêm de coortes europeias e norte-americanas e não são ajustadas.",
    "Pessoas sem histórico familiar: o modelo depende do genótipo dos genitores e não estima o risco populacional de "
    "base (a forma familiar é 10 a 15 % dos casos).",
    "Decisões reprodutivas, como diagnóstico pré-implantacional: não cabem a esta ferramenta.",
]
USOS_NA_PRATICA = [
    (
        "Antes do teste ou da consulta",
        "o profissional prepara o aconselhamento e identifica quais informações a família precisa ouvir.",
    ),
    (
        "Depois do laudo laboratorial",
        "o resultado do sequenciamento vira o VCF de entrada, e o artefato traduz a variante em probabilidades ao "
        "longo da vida, ajudando a explicar a incerteza, que é grande: os intervalos de penetrância são largos.",
    ),
    (
        "Acompanhamento",
        "para portadores assintomáticos, a idade provável de início orienta a frequência de avaliações, sem "
        "substituir o exame clínico.",
    ),
]


def ajuda() -> dict:
    """Conteúdo da página Ajuda: para quem é, para quem não é, como se encaixa na prática e o fluxo de uso."""
    return {
        "titulo": "Ajuda",
        "descricao": DESCRICAO_SISTEMA,
        "casos": [{"tipo": k, **v} for k, v in TIPOS_ATENDIMENTO.items()],
        "fora_do_escopo": FORA_DO_ESCOPO,
        "usos": [{"momento": m, "texto": t} for m, t in USOS_NA_PRATICA],
        "operacao": (
            "O artefato não é usado diretamente pelo paciente. Quem o opera é o médico geneticista, o neurologista ou "
            "o conselheiro genético, como ferramenta de apoio ao aconselhamento. Em nenhum uso o resultado vale como "
            "diagnóstico: ele é lido por um profissional, que o interpreta com o histórico clínico da família."
        ),
        "fluxo": [
            "Cadastre o atendimento escolhendo o caso (pessoa, casal ou família) e informe prontuário, genitores "
            "(nome, nascimento, laudo do C9orf72 e VCF) e, quando houver, os descendentes.",
            "Na ficha, anexe ou substitua os VCFs, registre os consentimentos para pesquisa (opcional) e acompanhe o "
            "histórico de análises. Se um genitor não pôde ser testado (faleceu, não está disponível ou não quer fazer "
            'o teste), use "Adicionar parente testado" para anexar o VCF e o laudo do pai, da mãe ou de um irmão dele, '
            "e informe a situação clínica e a idade desse genitor; na família, o VCF de um filho já testado também "
            "entra como evidência.",
            "Execute a análise confirmando que a pessoa analisada não apresenta sintomas de ELA: o resultado traz se "
            "herdou (probabilidade de transmissão), a chance de manifestação com banda de 95 % e a idade provável de "
            "início, além do pacote completo para download. Com a idade atual informada, os três indicadores valem a "
            "partir dessa idade, sem sintomas.",
        ],
        "perfis": [
            (
                "Médico ou aconselhador genético",
                "cadastra atendimentos, anexa VCFs, registra consentimentos e executa análises; vê só os próprios registros.",
            ),
            (
                "Pesquisador",
                "consulta casos liberados de forma pseudonimizada (código, sexo, década de idade, resultados), com filtros, totais e exportação; nunca vê nome, prontuário ou nascimento.",
            ),
            (
                "Administrador",
                "aprova cadastros, gere usuários e consulta a auditoria; não acessa registros, arquivos genéticos nem resultados.",
            ),
        ],
        "limitacao": LIMITACAO_MODELO,
    }


AVISO_EXPERIMENTAL = (
    "Sistema experimental de apoio ao aconselhamento genético preditivo da ELA. Não constitui diagnóstico, "
    "não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes."
)
LIMITACAO_MODELO = (
    "O risco estimado é condicionado ao genótipo dos genitores nos quatro genes-alvo, ao sexo e à idade atual da "
    "pessoa sem sintomas. Quando um genitor não pôde ser testado, entra o genótipo de parentes dele (pai, mãe, irmão "
    "ou filho já testado), com a situação clínica do próprio genitor. O modelo não usa ancestralidade nem o fenótipo "
    "de parentes sem teste genético, não calcula números agregados da família e assume independência entre os genes; "
    'por isso "personalizado" significa condicionado a essas informações, e não um perfil clínico completo.'
)
INFERENCIA_POR_PARENTES = (
    "O genótipo do genitor sem exame foi inferido a partir de parentes testados: a dosagem dele deixa de ser observada "
    "e passa a ser uma probabilidade, calculada pela segregação mendeliana e condicionada à situação clínica dele. A "
    "penetrância é a mesma para toda a família: um genitor que chegou a certa idade sem sintomas torna menos prováveis "
    "tanto a variante nele quanto os valores altos de penetrância."
)
AVISO_PARCEIRO_INFERIDO = (
    "Atenção: o parceiro não fez o teste. O cálculo a partir dos parentes dele revela indiretamente a chance de o "
    "próprio parceiro ser portador. Leve isso em conta antes de apresentar o resultado ao casal."
)
SUPOSICAO_VARIANTE_HERDADA = "Supõe-se que a variante do parente foi herdada, e não surgiu nele: não há taxa de mutação nova nas fontes do modelo."
SITUACOES_GENITOR = {
    "VIVO_ASSINTOMATICO": "Vivo, sem sintomas de ELA",
    "FALECIDO_SEM_ELA": "Falecido sem ter tido ELA",
    "AFETADO": "Teve ou tem ELA",
    "DESCONHECIDA": "Situação desconhecida",
}
LIMITE_INFERIOR_GENITOR_AFETADO = (
    "Limite inferior: o fenótipo do genitor não é modelado. O genitor teve ELA, o que torna a variante nele mais "
    "provável do que o cálculo considera; o risco real tende a ser maior."
)
PARENTESCOS = {
    "PAI_DO_GENITOR": "Pai do genitor",
    "MAE_DO_GENITOR": "Mãe do genitor",
    "IRMAO_DO_GENITOR": "Irmão ou irmã do genitor",
}
_PARENTE_DO_ATENDIDO = {
    ("MAE", "PAI_DO_GENITOR"): "Avô materno",
    ("MAE", "MAE_DO_GENITOR"): "Avó materna",
    ("MAE", "IRMAO_DO_GENITOR"): "Tio(a) materno(a)",
    ("PAI", "PAI_DO_GENITOR"): "Avô paterno",
    ("PAI", "MAE_DO_GENITOR"): "Avó paterna",
    ("PAI", "IRMAO_DO_GENITOR"): "Tio(a) paterno(a)",
}
_PARENTE_DO_CASAL = {
    ("MAE", "PAI_DO_GENITOR"): "Pai da parceira",
    ("MAE", "MAE_DO_GENITOR"): "Mãe da parceira",
    ("MAE", "IRMAO_DO_GENITOR"): "Irmão(ã) da parceira",
    ("PAI", "PAI_DO_GENITOR"): "Pai do parceiro",
    ("PAI", "MAE_DO_GENITOR"): "Mãe do parceiro",
    ("PAI", "IRMAO_DO_GENITOR"): "Irmão(ã) do parceiro",
}


def rotulo_parente(tipo: str, papel_genitor: str, parentesco: str) -> str:
    """Nome do parentesco na tela: em relação ao atendido (avô, avó, tio) ou, no casal, ao parceiro."""
    tabela = _PARENTE_DO_CASAL if tipo == "CASAL" else _PARENTE_DO_ATENDIDO
    return tabela.get((papel_genitor, parentesco), PARENTESCOS.get(parentesco, parentesco))


LINHA_RISCO_PACIENTE = (
    "O risco estimado é o do paciente (descendente). Os arquivos genéticos analisados são os da mãe e do pai, "
    "que também são titulares desses dados."
)
LINHA_RISCO = {
    "PESSOA": LINHA_RISCO_PACIENTE,
    "FAMILIA": (
        "O risco é estimado para cada filho, um a um. Os arquivos genéticos analisados são os da mãe e do pai, "
        "titulares desses dados."
    ),
    "CASAL": (
        "O risco é estimado para um futuro filho do casal. Os arquivos genéticos analisados são os dos dois "
        "parceiros, titulares desses dados."
    ),
}


def aviso_privacidade(encarregado_nome: str, encarregado_contato: str) -> dict:
    """Aviso de privacidade em linguagem simples (art. 6º, VI; art. 9º)."""
    return {
        "titulo": "Privacidade e proteção de dados",
        "versao": VERSAO_AVISO_PRIVACIDADE,
        "secoes": [
            {
                "titulo": "O que é este sistema",
                "paragrafos": [
                    DESCRICAO_SISTEMA,
                    "Atende três situações: a pessoa assintomática com histórico familiar; o casal que planeja filhos; "
                    "e a família de um genitor com variante confirmada, que quer o risco de cada filho. Pessoas já "
                    "sintomáticas e pessoas sem histórico familiar estão fora do escopo, assim como números agregados "
                    "da família, o fenótipo de parentes sem teste genético e a ancestralidade.",
                    LIMITACAO_MODELO,
                ],
            },
            {
                "titulo": "Quais dados tratamos",
                "itens": [
                    "Dos usuários (médicos, aconselhadores genéticos, pesquisadores e administradores): nome, CPF, e-mail, "
                    "senha (guardada só como hash) e dados profissionais informados no cadastro.",
                    "Do atendimento, cadastrado pelo médico: nome do registro, número e documento do prontuário, momento do "
                    "aconselhamento (opcional) e observações; de cada descendente: nome, data de nascimento e sexo; de "
                    "cada genitor: nome, data de nascimento e laudo do C9orf72 (número de repetições e documento). Não "
                    "pedimos CPF, endereço, telefone nem e-mail de pacientes ou genitores. A pessoa analisada precisa "
                    "estar sem sintomas de ELA: o profissional confirma isso a cada análise, e só a confirmação e a data "
                    "ficam guardadas, sem nenhum dado clínico.",
                    "Dados genéticos dos genitores (arquivos VCF), anexados pelo médico à ficha e guardados cifrados em "
                    "disco, e o resultado completo de cada análise (relatório, tabelas, figuras e resumo), também cifrado. "
                    "Dado genético e dado de saúde são dados pessoais sensíveis (art. 5º, II).",
                    "Quando um genitor não pôde ser testado: de cada parente dele anexado pelo médico (pai, mãe ou irmão "
                    "do genitor), o parentesco, o arquivo genético (VCF), o laudo do C9orf72 e a data, sem nome nem "
                    "documento (o nome só é registrado se o parente consentir com o uso em pesquisa); do próprio "
                    "genitor, a situação clínica (vivo sem sintomas, falecido sem ELA, teve ELA ou "
                    "desconhecida) e a idade correspondente; e, na família, o VCF de um filho já testado. O parente "
                    "também é titular de dado genético sensível, tratado com as mesmas regras dos genitores.",
                    "Registros de auditoria: quem fez o quê e quando, sem nome de paciente, sem CPF completo e sem senha.",
                ],
            },
            {
                "titulo": "Para que usamos",
                "itens": [
                    "Atendimento: estimar o risco do paciente a pedido do médico, com base legal na tutela da saúde "
                    "por profissional de saúde (art. 11, II, f). O cadastro do paciente não depende de consentimento.",
                    "Pesquisa: só com consentimento específico, destacado e registrado de cada descendente (ou responsável, "
                    "se menor), de cada genitor e de cada parente cujo dado genético seria exposto (art. 11, I; art. 8º). "
                    "Nunca vem pré-marcado e pode ser revogado na mesma tela, com efeito imediato (art. 8º, §5º).",
                    "Segurança e prestação de contas: auditoria das operações (art. 37) e proteção de contas.",
                ],
            },
            {
                "titulo": "Por quanto tempo",
                "itens": [
                    "Arquivos VCF (dos genitores, dos parentes e do filho já testado): cifrados em disco enquanto o "
                    "registro existir; nunca podem ser baixados pela plataforma e são decifrados só na pasta temporária "
                    "da análise, apagada ao fim. Substituir ou remover o anexo apaga o arquivo anterior.",
                    "Resultados completos das análises, documentos do prontuário e laudos: cifrados em disco enquanto o "
                    "registro existir; só o médico dono os abre, e cada abertura fica na auditoria. A análise avulsa, sem "
                    "registro, expira em duas horas.",
                    "Registro, descendentes, genitores, consentimentos e resumos: enquanto o médico mantiver o registro. "
                    "Excluir o registro remove identificadores, VCFs, documentos, resultados e consentimentos (art. 16); a "
                    "auditoria permanece, sem dado identificável.",
                    'Conta de usuário: enquanto ativa. O usuário pode pedir o encerramento em "Minha conta".',
                ],
            },
            {
                "titulo": "Quem acessa",
                "itens": [
                    "O médico vê apenas os próprios registros e os resultados das análises que executou.",
                    "O pesquisador nunca vê dado identificável. Casos liberados para pesquisa recebem um código "
                    "pseudonimizado (art. 13, §4º), gerado ao acaso e não derivado de nome, prontuário ou data, que não é "
                    "exibido ao médico nem ao administrador; o pesquisador vê o caso (tipo de atendimento, sexo, década de "
                    "idade, resultados das análises), nunca nome, prontuário, data de nascimento nem o VCF. O vínculo "
                    "com o atendido continua existindo: os dados são pseudonimizados e continuam sendo dados pessoais "
                    "(art. 12 e art. 13, §4º).",
                    "O administrador aprova cadastros, gere usuários e consulta a auditoria; não acessa pacientes, dados "
                    "clínicos, arquivos genéticos nem resultados.",
                ],
            },
            {
                "titulo": "Como exercer seus direitos (art. 18)",
                "itens": [
                    "Atendidos e genitores, por intermédio do médico: acesso e portabilidade (exportar os dados cadastrais), "
                    "correção (editar), eliminação (excluir), informação sobre compartilhamento (a ficha mostra se o caso "
                    "está liberado para pesquisa) e revogação do consentimento.",
                    'Usuários: em "Minha conta" é possível ver e corrigir os dados, exportá-los e pedir o encerramento da conta.',
                    f"Encarregado pelo tratamento de dados (art. 41): {encarregado_nome}; contato: {encarregado_contato}.",
                ],
            },
            {
                "titulo": "Como protegemos",
                "itens": [
                    "Identificadores, laudos, resumos de análise e CPF cifrados em repouso; VCFs cifrados em disco com "
                    "nome aleatório; senhas com Argon2id.",
                    "Sessão que expira por inatividade (30 minutos), cookie protegido, proteção contra falsificação de "
                    "requisição e limite de tentativas de login.",
                    "Nenhum dado pessoal em endereço de página (URL), em mensagem de erro ou no armazenamento do navegador.",
                    "Verificação de acesso no servidor em toda rota, com negação por padrão (art. 46, §2º; art. 49).",
                ],
            },
        ],
    }


TERMO_USO = {
    "titulo": "Termo de uso",
    "versao": VERSAO_TERMO_USO,
    "itens": [
        "O EloSense é um instrumento de apoio à decisão no aconselhamento genético preditivo da ELA, construído com "
        "parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não "
        "deve ser usado isoladamente em decisões sobre pacientes.",
        "O sistema destina-se a médicos, aconselhadores genéticos e pesquisadores, após verificação manual do cadastro "
        "pelo administrador. Pacientes e familiares não são usuários.",
        "O usuário responde pela veracidade dos dados profissionais informados e pelo sigilo da própria senha.",
        "O médico só cadastra pacientes sob seu cuidado e só envia arquivos genéticos com autorização de quem é titular "
        "deles, o que inclui os parentes do genitor que não pôde ser testado.",
        "A cada análise de uma pessoa, o profissional confirma que ela não apresenta sintomas de ELA; o sistema não se "
        "aplica a pessoas sintomáticas.",
        "Resultados são estimativas produzidas com parâmetros populacionais da literatura, com intervalos largos de "
        "incerteza, e devem ser interpretados por profissional habilitado, no contexto do aconselhamento genético.",
        "Toda operação relevante é registrada em auditoria, sem dado identificável de paciente.",
    ],
}

TERMO_CONSENTIMENTO_PESQUISA = {
    "titulo": "Consentimento para uso em pesquisa (separado do atendimento)",
    "versao": VERSAO_TERMO_CONSENTIMENTO_PESQUISA,
    "itens": [
        "Este consentimento é específico para a finalidade de pesquisa e independe do atendimento, que tem base legal própria.",
        "Ao consentir, o titular autoriza que o caso seja disponibilizado a pesquisadores de forma pseudonimizada: um código "
        "aleatório substitui o nome; nenhum nome, prontuário ou data de nascimento é exibido ao pesquisador.",
        "Como os dados genéticos analisados são dos genitores e, quando anexados, de parentes deles, a liberação exige "
        "o consentimento de cada descendente (ou do responsável legal, se menor de 18 anos), de cada genitor e de cada "
        "parente cujo dado seria exposto.",
        "O consentimento pode ser revogado a qualquer momento, pelo médico, na ficha do paciente, com efeito imediato.",
    ],
}
