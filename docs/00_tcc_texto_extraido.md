# 00 — Texto integral do TCC (revisão vigente)

> Cópia em Markdown da revisão do TCC enviada pelo usuário em 03/11/2026 e declarada por ele como a **versão vigente**. Substitui a extração de 24/10/2026 feita a partir de `TCC II - Escrita.docx` (o `.docx` no repositório ainda é a revisão anterior; a diferença principal está na seção 4.2, que antes trazia a exploração bruta do ClinVar/dbSNP com os Quadros 2 a 6 e agora descreve a entrada em VCF, as bases de referência e os parâmetros epidemiológicos). Fonte da verdade sobre requisitos; consulte quando houver dúvida.

# Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas

Geovana Íviny Santos Lima, Fabricio Carneiro Costa

**Resumo:** A área dos Sistemas de Informação aplicados à saúde vem se consolidando como campo de desenvolvimento de soluções capazes de transformar dados moleculares em conhecimento útil à decisão clínica, especialmente no contexto da medicina de precisão. No domínio do aconselhamento genético, entretanto, observa-se uma defasagem entre o avanço do sequenciamento genético e a oferta de ferramentas computacionais integradas, capazes de apoiar predições personalizadas sobre a transmissão e a manifestação de doenças hereditárias. Esse cenário se manifesta de forma particularmente crítica na Esclerose Lateral Amiotrófica, doença neurodegenerativa marcada por penetrância incompleta, expressividade variável e risco dependente da idade, atributos que os modelos clássicos de herança e as ferramentas atualmente disponíveis não conseguem representar de maneira satisfatória. Diante dessa lacuna, o presente trabalho tem como objetivo geral desenvolver um artefato computacional de apoio à decisão para o aconselhamento genético preditivo da Esclerose Lateral Amiotrófica, fundamentado no padrão da modelagem estocástica. A pesquisa adota a metodologia Design Science Research, com construção e avaliação iterativa do artefato a partir de dados sintéticos calibrados pela literatura científica. A solução é organizada em três camadas integradas: o tratamento e a interpretação dos dados genômicos parentais; a representação das dependências entre variáveis genéticas por meio de Redes Bayesianas, articuladas a simulações de Monte Carlo para a propagação da incerteza sobre a transmissão; e a projeção temporal do risco por meio de análise de sobrevivência, com a estimativa da manifestação clínica ao longo da vida e da idade provável de início da doença. Como resultado, espera-se entregar um protótipo funcional acompanhado da documentação da arquitetura e da descrição dos modelos empregados, apto a ser apropriado por equipes clínicas e de pesquisa em estudos posteriores. Estima-se, ainda, contribuir para o campo dos Sistemas de Informação aplicados à saúde ao demonstrar, por meio de um caso concreto, como a integração entre dados genômicos e modelagem estocástica pode dar origem a soluções alinhadas aos princípios da medicina de precisão e ao processo de aconselhamento genético preditivo.

**Palavras-Chave:** Sistemas de Informação em Saúde; Aconselhamento Genético Preditivo; Esclerose Lateral Amiotrófica; Redes Bayesianas; Apoio à Decisão Clínica.

## Introdução

Nos últimos anos, a área da saúde tem passado por transformações significativas impulsionadas pelo avanço da tecnologia aplicada ao sequenciamento genético. O que antes configurava um processo demorado e de custo muito elevado tornou-se cada vez mais acessível, abrindo espaço para o que hoje pode-se chamar de medicina de precisão, uma abordagem que considera as características genéticas de cada indivíduo no momento de alguma decisão clínica. Esse novo cenário trouxe, junto com possibilidades antes impensáveis, um desafio capaz de ultrapassar o campo biológico e tecnológico: como organizar, interpretar e transformar uma quantidade tão grande de informações em conhecimento útil para pacientes e profissionais de saúde por meio da tecnologia (RHEENEN et al., 2021).

Dentro desses cenários, a Esclerose Lateral Amiotrófica (ELA), doença neurodegenerativa grave, de evolução rápida e ainda sem cura, que afeta de maneira diferente cada pessoa que a desenvolve, vem se mostrando como uma condição em que essas dificuldades se tornam particularmente evidentes (FELDMAN et al., 2022). Embora a maior parte dos casos ainda não tenha origem hereditária conhecida, existe um grupo importante de indivíduos com histórico familiar que convive com a possibilidade de desenvolver a doença ou de transmiti-la aos descendentes. Conforme Goutman et al. (2022), os instrumentos atualmente utilizados no aconselhamento genético são modelos clássicos de herança que trabalham com probabilidades fixas, o que não reflete a complexidade observada nos estudos populacionais mais recentes.

Dessa forma, estudos recentes mostram que portadores de variantes genéticas associadas à doença manifestam os sintomas em frequências bastante diferentes daquelas previstas pelos modelos tradicionais, e que essa manifestação depende de fatores que vão além da própria mutação, como a idade e a influência de outros genes (DOUGLAS e BARALLE, 2024). Diante disso, abordagens baseadas em modelos probabilísticos em simulações computacionais vêm sendo apontadas como caminhos promissores para estimar, na visão de Westeneng et al. (2018), de uma forma mais realista, o risco genético e o curso provável da doença ao longo da vida.

Apesar do avanço dessas técnicas, observa-se uma lacuna relevante no campo da tecnologia aplicada à saúde, pois ainda são poucas as propostas que reúnem, em um único artefato computacional, a leitura de dados genômicos, aplicados a modelos probabilísticos para geração de visões personalizadas para cada perfil familiar. Trabalhos recentes voltados à predição em ELA concentram-se, em sua maior parte, na progressão da doença após o diagnóstico (PANCOTTI et al., 2022) e (PAPAIZ et al., 2025) ou em modelos prognósticos com validação em um segmento clínico (WESTENENG et al., 2018). Essas tecnologias operam de forma fragmentada, algumas voltadas à análise genética, outras ao cálculo estatístico, sem oferecer uma estrutura integrada capaz de apoiar, de fato, o aconselhamento genético preditivo.

Assim, o problema de pesquisa foi delimitado em duas questões principais: É viável projetar um artefato computacional capaz de integrar, em uma mesma arquitetura, dados genômicos e modelos probabilísticos? É possível por meio desse artefato oferecer predição personalizada com informações sobre, transmissão genética, manifestação clínica ao longo da vida e estimativa da idade provável do início da doença?

Para Zatz (2001), mais do que uma demanda técnica, trata-se de uma necessidade que vem sendo apontada há mais de duas décadas no contexto brasileiro das doenças neuromusculares, em que se observa uma defasagem entre o avanço do sequenciamento genético e uma proposta definitiva de ferramentas de apoio ao aconselhamento genético. É nesse encontro entre a acessibilidade e estabilidade das ferramentas de análises de dados, a persistência de uma demanda clínica e social ainda não atendida que se justifica o desenvolvimento deste trabalho.

A partir do exposto, o presente trabalho tem como objetivo o desenvolvimento de um artefato computacional voltado ao apoio à decisão no aconselhamento genético preditivo da Esclerose Lateral Amiotrófica. Para atingir o desenvolvimento, adota-se como referência processual o modelo CRISP-DM (Chapman et al., 2000), seguindo os seguintes objetivos específicos descritos a seguir.

A proposta se desenvolve no campo dos Sistemas de Informação aplicados à saúde e prevê a construção de uma solução modular, organizada em três grandes etapas integradas. A primeira etapa é responsável pela leitura e pelo tratamento dos dados genômicos parentais, transformando informações brutas oriundas de exames de sequenciamento em um conjunto estruturado de variáveis interpretáveis pelo restante do sistema. A segunda aplica os modelos probabilísticos: a partir das variantes identificadas, o artefato calcula o risco de transmissão da doença entre gerações, considerando as características de cada perfil familiar e a variabilidade observada na literatura científica. A terceira projeta esse risco ao longo do tempo, gerando estimativas personalizadas sobre a manifestação clínica ao longo da vida e a idade provável de início, organizadas em formato de curvas que podem ser consultadas pelo profissional de saúde.

Tem-se como hipótese que um protótipo funcional com documentação fundamentada na literatura, possa ser uma ferramenta de grande utilidade para pesquisadores e equipes clínicas para experimentação e evolução em estudos. O impacto pretendido se distribui em três frentes. Para os profissionais de aconselhamento genético, a ferramenta busca oferecer um ambiente único em que informações hoje dispersas passem a ser organizadas de maneira interpretável, contribuindo para um diálogo mais consistente com as famílias atendidas, sem substituir o julgamento clínico. Para as famílias que convivem com o histórico hereditário da doença, o impacto está na qualidade da informação recebida nos momentos de decisão mais delicados, especialmente os que envolvem planejamento reprodutivo e o acompanhamento de indivíduos assintomáticos geneticamente predispostos. Para o campo da tecnologia aplicada à saúde, o estudo visa demonstrar, por meio de um caso concreto, como a integração entre dados genômicos e modelagem probabilística pode dar origem a soluções alinhadas aos princípios da medicina de precisão.

## 2. Fundamentação Teórica

### 2.1. Esclerose Lateral Amiotrófica e o problema da hereditariedade

A Esclerose Lateral Amiotrófica é uma doença neurodegenerativa que compromete progressivamente os neurônios motores e, em geral, conduz à perda funcional severa em poucos anos após o surgimento dos sintomas, como afirma (WESTENENG., 2017). Estima-se que cerca de uma a cada dez pessoas com doença apresente histórico familiar reconhecido, ainda que estudos mais recentes venham demonstrando que parte expressiva dos casos considerados esporádicos também carrega variantes genéticas associadas à forma hereditária, conforme Douglas e Baralle (2024).

Quatro genes recebem maior atenção na literatura por centralizarem a maior parte das alterações já descritas como: SOD1, C9orf72, TARDBP e FUS. O SOD1 foi o primeiro a ser associado à doença, ainda na década de 1990, e tornou-se referência nos estudos sobre transmissão genética. Já o C9orf72, identificado anos depois, mostrou-se a alteração mais frequente em populações de origem europeia. Agora os genes TARDBP e FUS, embora menos prevalentes, ampliaram a compreensão sobre os mecanismos envolvidos no surgimento da doença (FELDMAN et al., 2022).

Um aspecto ainda bastante discutido em pesquisas recentes diz respeito ao fato de que portadores dessas variantes nem sempre desenvolvem a doença e, caso desenvolvam, manifestam os sintomas em idades distintas. Douglas e Baralle (2024), em revisão sistemática, descreveram que a probabilidade de manifestação varia de forma significativa entre os genes envolvidos. Esse comportamento, conhecido como penetrância reduzida, leva à conclusão de que os modelos clássicos de herança mendeliana, por si só, não conseguem descrever o que se observa na prática clínica e populacional. Por essa razão, a literatura sobre aconselhamento genético em doenças neurodegenerativas tem defendido abordagens que tratem o risco como estimativa probabilística, como argumenta Goutman et al. (2022), sensível ao tempo e ao contexto familiar. No contexto brasileiro, Zatz (2001) já apontava o papel do estudo do genoma humano na compreensão, no diagnóstico e na prevenção das doenças neuromusculares, ressaltando a importância de aproximar os avanços do sequenciamento da prática clínica e do aconselhamento familiar, sendo essa uma agenda que, mais de duas décadas depois, segue como referência para o desenvolvimento de instrumentos voltados a esse propósito.

### 2.2. Dados genômicos e o trabalho com a informação genética

O sequenciamento de nova geração trouxe ao campo da genética uma escala de informação até então nunca vista. Stephens et al. (2015) chamaram a atenção para o fato de que, dentre os domínios mais produtores de dados, a genômica caminha de forma ágil para igualar o volume gerado em áreas como astronomia e mídia digital. A consequência perceptível desse crescimento foi o deslocamento do principal desafio da pesquisa: não se trata mais de obter as sequências, mas de interpretá-las de modo confiável.

Para tornar essa interpretação possível, a comunidade científica adotou padrões comuns para a representação dos dados genéticos. O formato chamado Variant Call Format, introduzido no contexto do 1000 Genomes Project, tornou-se a maneira mais usada de registrar as variantes encontradas em um genoma, conforme (DANECK et al., 2011). A leitura e análise desses arquivos, no entanto, depende de pipelines bem definidas que combinam etapas de alinhamento, chamada e anotação de variantes, conforme as boas práticas consolidadas (VAN DER AUWERA e O'CONNOR, 2020). Landrum et al. (2018) propõe que a interpretação clínica das variantes acontece em diálogo com bases públicas: o ClinVar reúne classificações de patogenicidade segundo critérios reconhecidos internacionalmente, enquanto o dbSNP organiza a variação observada em diferentes populações, conforme (SHERRY et al., 2001). Apesar dessa infraestrutura consolidada, a manutenção dessas bases envolve constantes reclassificações e atualizações, o que impõe desafios contínuos de sincronização e compatibilidade entre os repositórios.

### 2.3. Modelagem estocástica à predição clínica

A predição computacional em fenômenos cuja evolução envolve aleatoriedade exige instrumentos matemáticos capazes de operar sob incerteza. Esse é o domínio da modelagem estocástica, abordagem na qual sistemas são representados por variáveis aleatórias e por processos que incorporam a incerteza como elemento essencial. Sua pertinência à Esclerose Lateral Amiotrófica decorre do próprio fenômeno, pois, conforme demonstrado por Douglas e Baralle (2024), portadores de uma mesma variante patogênica desenvolvem a doença em frequências e idades distintas, comportamento que regras determinísticas de herança não conseguem representar. A maturidade da abordagem é evidenciada por aplicações em sistemas complexos, como ilustra o trabalho de Degregori (2016) sobre o modelo de Ising.

Na Esclerose Lateral Amiotrófica, a modelagem computacional tem sido aplicada em problemas distintos. Matoso (2017) construiu modelos biofísicos de neurônios motores inferiores; Gazola (2025) propôs um modelo computacional para o efeito do fingolimod na esclerose múltipla; e Pancotti et al. (2022) e Papaiz et al. (2025) aplicaram aprendizagem profunda à progressão da doença após o diagnóstico. Esses esforços concentram-se em estágios pós-sintomáticos. A presente proposta opera em etapa anterior, a do aconselhamento genético preditivo, articulando três técnicas sob a abordagem estocástica: Redes Bayesianas, para as dependências condicionais entre variáveis genéticas; Monte Carlo, para a propagação da incerteza; e análise de sobrevivência, operacionalizada pela Lifelines (Davidson-Pilon, 2026), para a projeção temporal do risco.

As Redes Bayesianas, formalizadas por Pearl (1988) e sistematizadas por Koller e Friedman (2009), constituem modelos gráficos probabilísticos em que um grafo acíclico orientado representa as dependências condicionais entre variáveis aleatórias, com tabelas de probabilidade condicional descrevendo essas relações. Essa estrutura divide distribuições conjuntas complexas em componentes locais interpretáveis, permitindo tanto a dedução probabilística automática quanto a leitura semântica do modelo. Entre suas propriedades estão a conclusão em qualquer direção do grafo, a atualização de crenças diante de novas evidências e o tratamento explícito da incerteza. Na tecnologia voltada à saúde, esse formalismo foi aplicado por Kinjo et al. (2022) ao cálculo de probabilidade de falha em sistemas baseados em Internet das Coisas.

No artefato proposto, a Rede Bayesiana representa as dependências condicionais entre o perfil genômico parental, as variantes herdadas pelo descendente e a probabilidade de manifestação clínica. A escolha decorre de três propriedades convergentes ao aconselhamento genético preditivo: a interpretabilidade, necessária para justificar decisões clínicas às famílias; a capacidade de tratar a penetrância incompleta como dependência probabilística, de acordo com as evidências de Douglas e Baralle (2024) e Feldman et al. (2022) sobre a heterogeneidade fenotípica; e a flexibilidade para incorporar, em versões futuras, fatores modificadores adicionais sem reestruturação do modelo.

A simulação de Monte Carlo, originalmente proposta por Metropolis e Ulam (1949), consiste na estimação de propriedades de modelos probabilísticos por meio da repetição controlada de experimentos numéricos, substituindo cálculos analíticos inviáveis por amostragens sucessivas das distribuições de base. Variantes como o Monte Carlo via Cadeias de Markov viabilizam dedução em modelos cuja distribuição posterior não possui solução fechada. Em Python, sua execução em projetos de saúde tem sido facilitada por bibliotecas como o PyMC (PyMC Development Team, 2026). Em contextos correlatos da modelagem computacional aplicada a doenças neurodegenerativas, abordagens baseadas em simulação aparecem nos trabalhos Matoso (2017) e Gazola (2025).

No artefato proposto, a simulação de Monte Carlo opera sobre a Rede Bayesiana, gerando trajetórias amostrais que reconstituem cenários de transmissão e manifestação em descendentes hipotéticos. Cumpre duas funções complementares: propagar a incerteza presente nas variantes parentais ao longo das dependências modeladas, produzindo distribuições de probabilidade sobre o fenótipo do descendente; e se estrutura à análise de sobrevivência implementada pela Lifelines (Davidson-Pilon, 2026), traduzindo os cenários amostrados em curvas temporais de risco que descrevem a manifestação clínica ao longo da vida e a idade provável de início da doença. Essa conexão constitui o núcleo estocástico do artefato.

### 2.4. Design Science Research em Sistemas de Informação

A Design Science Research é uma abordagem de pesquisa orientada à construção e à avaliação de artefatos voltados à solução de problemas fáceis no campo dos Sistemas de Informação.

Na área da saúde, essa abordagem tem sido adotada no desenvolvimento de sistemas de apoio à decisão e de plataformas voltadas à integração de dados clínicos e genômicos, alinhada às bases conceituais propostas por Hevner et al. (2004) para a pesquisa em tecnologia aplicada à saúde. A escolha desse referencial dá ao trabalho uma base reconhecida para tratar a construção do artefato como objeto de pesquisa, e não apenas como atividade técnica.

Como complemento ao referencial da Design Science Research, o desenvolvimento técnico do artefato proposto neste trabalho adota o CRISP-DM, modelo de processo formalizado por Chapman et al. (2000) a partir de uma iniciativa colaborativa reunida no final da década de 1990 e amplamente consolidado, desde então, como referência em projetos de ciência de dados. O CRISP-DM organiza a condução desses projetos em seis fases interdependentes e iterativas que se iniciam com o Entendimento do Negócio, em que o domínio do problema é caracterizado e os objetivos analíticos são definidos. Em seguida, Entendimento dos Dados, em que se examina a natureza, a qualidade e os limites das informações disponíveis, estruturando a base necessária para a Preparação dos Dados, em que se constroem as estruturas e os pipelines responsáveis pela ingestão, normalização e aprimoramento das informações brutas. Com a base consolidada, passa-se à Modelagem, em que técnicas analíticas e algoritmos são aplicados sobre os dados preparados. Finalizando o processo, as etapas de Avaliação e Implantação encerram, verificando a coerência dos resultados frente aos objetivos propostos e entregando a estrutura detalhada ao seu ambiente de aplicação. Aplicadas ao artefato proposto neste trabalho, essas fases assumem a configuração descrita a seguir.

A fase de Entendimento do Negócio compreende a investigação, por meio de revisão da literatura, de como os sistemas computacionais de apoio à decisão vêm sendo empregados no contexto do aconselhamento genético, identificando avanços e lacunas existentes, bem como o exame das limitações dos modelos atualmente utilizados na predição de doenças neurodegenerativas hereditárias, sobretudo no que se refere à transmissão entre gerações, à manifestação clínica e à estimativa da idade provável de início da doença. Essa fase delimita o domínio do problema e fundamenta as decisões de projeto que orientarão as etapas seguintes.

O Entendimento dos Dados consiste em analisar as características dos dados genômicos manipulados no contexto da Esclerose Lateral Amiotrófica, incluindo o formato Variant Call Format, as bases públicas de classificação clínica, como ClinVar e dbSNP, e as possibilidades de integração entre esses dados e modelos estocásticos no apoio à predição personalizada. Trata-se de etapa necessária para identificar a natureza, a estrutura e os limites das informações disponíveis para o sistema. Com essa fase, se estrutura a base necessária para a Preparação dos Dados, envolvendo a caracterização dos requisitos funcionais e não funcionais necessários ao artefato e o desenho do pipeline responsável pela ingestão, pela normalização e pela anotação das variantes parentais, transformando informações brutas em variáveis estruturadas e interpretáveis pelas camadas subsequentes do sistema.

A de Modelagem corresponde à proposição da arquitetura e do fluxo de dados que orientam o desenvolvimento do artefato e à implementação de uma versão inicial centrada no núcleo estocástico, que articula Redes Bayesianas para a representação das dependências entre variáveis genéticas, simulações de Monte Carlo para a propagação da incerteza sobre a transmissão e análise de sobrevivência para a projeção temporal do risco.

Fase de Avaliação consiste em verificar o comportamento do artefato sobre cenários sintéticos aferidos pela literatura científica, observando sua lógica interna, a estabilidade das simulações em execuções sucessivas, a aderência das estimativas às distribuições teóricas conhecidas e sua adequação ao propósito de apoio à decisão no aconselhamento genético. Após ela, se segue para a Implantação, no contexto desta pesquisa, traduz-se na entrega de um protótipo funcional acompanhado da documentação da arquitetura e da descrição dos modelos empregados, apto a ser apropriado por pesquisadores e por equipes clínicas para experimentação e evolução em estudos futuros, sem se configurar como ferramenta diagnóstica ou substituto do julgamento profissional.

Por se manter independente em relação a tecnologias específicas e por enfatizar o caráter iterativo do desenvolvimento, o modelo se mostra particularmente adequado a contextos em que dados heterogêneos precisam ser integrados a pipelines analíticos complexos, situação que se observa de forma evidente no domínio genômico. Na área da saúde, o CRISP-DM tem sido recorrentemente adotado em estudos de exploração de dados clínicos e em pipelines bioinformáticos, sustentado pelo modelo originalmente proposto por Chapman et al. (2000), que segue como referência processual em projetos aplicados de ciência de dados.

A articulação entre Design Science Research e CRISP-DM, no contexto deste trabalho, ocorre em planos distintos e complementares. Enquanto a DSR organiza a pesquisa em sua dimensão científica, oferecendo um percurso reconhecido para tratar a construção e a avaliação do artefato como objeto de investigação, o CRISP-DM organiza a dimensão processual do desenvolvimento, estruturando, em fases sequenciais e iterativas, as atividades técnicas que levam o artefato da concepção ao protótipo funcional. Essa combinação permite ao presente estudo manter o rigor metodológico da DSR sem abrir mão da consistência operacional que o CRISP-DM oferece à etapa de design e desenvolvimento, ela mesma uma das fases previstas no modelo (PEFFERS et al., 2007).

## 3. Metodologia

Esta pesquisa é de abordagem aplicada, pois busca gerar conhecimento voltado a uma finalidade prática: o desenvolvimento de um artefato computacional de apoio ao aconselhamento genético. Quanto aos objetivos, caracteriza-se como exploratória, já que pretende investigar um problema ainda pouco estruturado em soluções computacionais; no que diz respeito à abordagem, combina elementos qualitativos e quantitativos. No que se refere aos procedimentos, adota-se a Design Science Research, por se tratar de uma estratégia adequada à construção de artefatos que respondam a problemas reais. Essa perspectiva foi consolidada por Hevner et al. (2004), ao defenderem que a pesquisa em tecnologia aplicada à saúde não se limita à descrição de fenômenos, mas inclui a produção de artefatos úteis ao ambiente em que são aplicados. Em seguida, Peffers et al. (2007) propuseram um percurso metodológico organizado em etapas, que vão da identificação do problema à comunicação dos resultados, passando pelo desenvolvimento e pela avaliação da solução. A condução deste trabalho adota o modelo proposto pelos referidos autores, organizado nas quatro fases descritas a seguir.

### 3.1. Identificação do problema e motivação

Nessa fase, foi feito o levantamento do problema a partir da literatura sobre aconselhamento genético e sobre os sistemas atualmente utilizados para apoiar esse trabalho. Observou-se que boa parte das ferramentas disponíveis se respalda em modelos clássicos de herança, que tratam o risco como um valor fixo. No caso da Esclerose Lateral Amiotrófica, esse tipo de abordagem deixa de lado características importantes da doença, como o fato de que nem toda pessoa portadora de uma variante de risco desenvolve a condição e a idade de início pode ser bastante variável. Também se notou a falta de soluções que tratem, em um mesmo ambiente, a leitura dos dados genômicos parentais, o cálculo do risco e a apresentação dos resultados de forma compreensível para o profissional que faz esse tipo de aconselhamento.

### 3.2. Definição dos requisitos do artefato

A partir do problema identificado, foram definidos os requisitos que o sistema precisa atender. Os requisitos funcionais descrevem o que o artefato deve fazer: ler arquivos no formato Variant Call Format provenientes dos pais; reconhecer variantes nos genes mais associados à ELA, como SOD1, C9orf72, TARDBP e FUS; consultar bases públicas, como ClinVar e dbSNP, para classificar a relevância clínica dessas variantes; calcular o risco de transmissão por meio de uma Rede Bayesiana; simular cenários de herança com o método de Monte Carlo; estimar a idade provável de início da doença; e apresentar os resultados em forma de gráficos. Já os requisitos não funcionais tratam de aspectos da qualidade do sistema, como a organização em módulos independentes, a possibilidade de atualizar as bases de variantes ao longo do tempo, o desempenho frente a arquivos grandes e a clareza dos resultados gerados.

### 3.3. Design e desenvolvimento

Nesta etapa, o artefato é projetado e construído. A arquitetura foi organizada em módulos com responsabilidades bem definidas, de modo que cada parte do sistema possa ser desenvolvida, testada e atualizada de forma independente. O módulo de ingestão é responsável pela leitura dos arquivos VCF e pela aplicação de critérios de qualidade e normalização dessas variantes. O módulo de anotação cruza essas variantes com as bases ClinVar e dbSNP, atribuindo a elas uma classificação de patogenicidade. O motor de cálculo concentra a dedução probabilística: nele, a Rede Bayesiana representa as dependências entre o perfil genômico dos pais e a probabilidade de manifestação no descendente, enquanto a simulação de Monte Carlo é usada para reconstruir diferentes cenários de transmissão.

O módulo de análise temporal estima a idade provável de início da doença, traduzindo o perfil genômico em curvas de risco ao longo da vida. Por fim, o módulo de visualização apresenta os resultados em formato gráfico, com o cuidado de torná-los compreensíveis no contexto do aconselhamento genético. A linguagem escolhida para a implementação foi o Python, pela maturidade do seu ambiente tecnológico voltado a dados e à bioinformática. Para a leitura e o tratamento dos arquivos VCF utiliza-se a biblioteca Biopython; para a construção das Redes Bayesianas e a dedução probabilística, a PyMC; e para a análise de sobrevivência, a Lifelines. A estruturação dos dados intermediários é feito com Pandas.

### 3.4. Demonstração e avaliação

A demonstração consiste em executar o artefato em cima de dados sintéticos, criados a partir das distribuições estatísticas relatadas na literatura sobre a arquitetura genética da ELA, como frequências de variantes e curvas de penetrância por idade. A opção por dados sintéticos se deve a duas razões: a primeira é a inviabilidade ética e jurídica de utilizar dados genômicos reais sem aprovação em comitê de ética e em conformidade com a Lei Geral de Proteção de Dados; a segunda é que dados controlados permitem observar o comportamento do sistema em cenários definidos previamente. A avaliação considera o quanto os resultados se aproximam das probabilidades teóricas conhecidas, a estabilidade das simulações em execuções repetidas, a coerência das curvas de risco geradas e o tempo necessário para o processamento. Esses critérios permitem verificar se o artefato de fato cumpre o que foi proposto e se é viável do ponto de vista computacional, sem se distanciar do caráter de apoio à decisão, e não de diagnóstico, que orienta todo esse trabalho.

## 4. DESENVOLVIMENTO

O desenvolvimento do artefato computacional adota como referência processual o modelo CRISP-DM, articulado à abordagem metodológica da Design Science Research (DSR). A condução técnica organiza-se nas seis fases iterativas do ciclo de vida, guiando o projeto desde a formalização do problema clínico até a entrega do protótipo funcional.

### 4.1 Entendimento do Negócio

A delimitação da primeira fase se baseia na compreensão do domínio da aplicação, desenvolvendo essa fase em objetivos analíticos bem alinhados e na definição dos critérios para a validação dos resultados obtidos (CHAPMAN et al., 2000).

#### 4.1.1 Mapeamento do Problema Clínico

O aconselhamento genético preditivo atende assintomáticos em risco hereditário, sobretudo familiares de primeiro grau de portadores de variantes associadas à ELA e se estrutura em três perguntas: a probabilidade de transmissão do gene mutado, o risco de manifestação clínica e a projeção da idade de início. A lógica de processamento computacional proposta precisa diferenciar essas dimensões, evitando unificar parâmetros de origens distintas.

Feldman et al. (2022) descrevem a forma familiar entre 10% e 15% dos casos e observam que um histórico mal conhecido pode ocultar casos familiares, o que coloca o dado genômico como evidência principal. Dos mais de 40 genes associados à doença, os quatro desse trabalho respondem por cerca de 55% das famílias de ascendência europeia (DOUGLAS; BARALLE, 2024, p. 294), recorte que define as regiões a selecionar no arquivo.

A transmissão segue o padrão de herança do gene, predominantemente dominante e raramente recessivo (FELDMAN et al., 2022; DOUGLAS; BARALLE, 2024). A lógica de manifestação clínica se encontra descrita no levantamento de Douglas e Baralle (2024), que estimaram a penetrância populacional das variantes patogênicas e provavelmente patogênicas em valores máximos de 33% para o C9orf72 (IC 95% 20,9–53,2), 54% para o SOD1 (IC 95% 32,7–88,6), 38% para o TARDBP (IC 95% 21,1–69,8) e 19% para o FUS (IC 95% 13,0–28,4). Essa amplitude dos intervalos mostra o quanto a estimativa é incerta e delimita os valores para contexto populacional, não para o caso individual. Inseridos nesse cenário, somado ao tempo e o sexo observa-se que o pico de incidência se concentra entre 60 e 75 anos e o adoecimento ocorre em múltiplas etapas (FELDMAN et al., 2022; DOUGLAS; BARALLE, 2024). Seguindo essa perspectiva, o período já vivido pelo indivíduo sem sintomas atua como variável de cálculo, complementado pela distinção de sexo, dado que homens portadores da expansão no C9orf72 tendem a manifestar a condição cerca de dois anos mais cedo do que as mulheres (GOUTMAN et al., 2022).

A definição do risco com base apenas na frequência fixa de herança desconsidera que a proporção de 50% reflete exclusivamente a transmissão do alelo, divergindo da probabilidade real de manifestação da doença. Dessa forma, o cálculo exige a separação de duas variáveis, entre o mecanismo de herança e o prognóstico clínico da condição. Uma representação adequada mantém as três variáveis separadas, condicionando a manifestação da condição à idade e ao sexo, além de manter a incerteza dos parâmetros até os resultados finais. A literatura opera em outro momento, trazendo o modelo ENCALS (WESTENENG et al., 2018), bem como os trabalhos de Pancotti et al. (2022) e Papaiz et al. (2025), em um período de tempo diferente daquele do aconselhamento, pois utilizam variáveis pós-manifestação e baseadas no diagnóstico. O aconselhamento, no entando, ocorre em uma etapa pré-clínica, limitando a análise às informações genômicas disponíveis e aos dados populacionais da literatura sobre portadores.

#### 4.1.2 Objetivo do Artefato

O delineamento do artefato se fundamenta na unificação de dados genômicos brutos e parâmetros epidemiológicos para gerar estimativas probabilísticas projetadas no tempo, que hoje estão dispersas. Esse método, é estruturado a partir de taxas de penetrância populacional, caracterizando como instrumento de apoio à decisão, sem pretensão diagnóstica.

#### 4.1.3 Critérios de Sucesso do Projeto

O sistema deve ler e processar dados no padrão VCF, verificados por arquivos de teste de conteúdo conhecido, sabendo diferenciar as deduções de risco segundo o gene afetado, refletindo as variações de penetrância documentadas (DOUGLAS; BARALLE, 2024). Gerar de forma diferente a probabilidade de transmissão e a curva temporal de risco, registrando também os intervalos de confiança e as versões das bases.

O desenvolvimento do modelo prevê a integração de quatro fontes principais de informação, envolvendo os arquivos parentais no padrão Variant Call Format (VCF), as bases ClinVar e dbSNP, a literatura epidemiológica e a massa sintética de validação. Como suas estruturas, vocabulários e ciclos de atualização diferem, a preparação exige um fluxo de extração, transformação e carga voltado à combinação das chaves genômicas, à verificação de integridade e à rastreabilidade das versões, com isolamento dos dados parentais, que a Lei Geral de Proteção de Dados classifica como pessoais sensíveis (BRASIL, 2018, art. 5º, II).

Essa etapa apresenta um risco metodológico de gerar dados incorretos, porém coerentes de forma estrutural, caso ocorra uma correspondência equivocada entre as fontes. Como no cruzamento de uma variante com um registro anotado em outra versão do genoma de referência (DANECEK et al., 2011). Realizar essa detecção depois da modelagem gera custos, o que justifica uma verificação própria na preparação.

### 4.2. Entendimento dos Dados

A segunda fase compreende a coleta inicial dos dados, sua descrição, exploração e verificação de qualidade (CHAPMAN et al., 2000), mapeando as potencialidades, limitações e exigências técnicas específicas de cada fonte consultada.

#### 4.2.1 Entrada Principal no Variant Call Format

O arquivo de entrada resulta de um fluxo de laboratório que alinha as leituras brutas do sequenciamento de nova geração contra um genoma de referência e identifica onde a amostra difere dele (VAN DER AUWERA; O'CONNOR, 2020). O VCF é o formato em que esse resultado é registrado (DANECEK et al., 2011) e foi escolhido por ser a saída desses fluxos e um dos formatos de distribuição do ClinVar (LANDRUM et al., 2018). Como um genoma humano difere da referência em 4,1 a 5,0 milhões de sítios (THE 1000 GENOMES PROJECT CONSORTIUM, 2015), a filtragem prévia das regiões dos quatro genes surge como um requisito de viabilidade metodológica. O arquivo utilizado para esse mapeamento é composto por um cabeçalho descritivo da versão de referência e do programa gerador, além de uma seção de dados com os campos fundamentais apresentados no Quadro 2.

**Quadro 2 — Campos essenciais do VCF e uso previsto no artefato**

| Campo | O que contém | Uso no artefato |
|---|---|---|
| CHROM, POS, REF e ALT | Cromossomo, posição contada a partir de 1, alelo de referência e alelos alternativos | Chave de correspondência com as bases; multialélicos exigem decomposição |
| ID | Identificador único da variante, normalmente o rsID | Ligação complementar com o dbSNP |
| QUAL, FILTER e INFO | Qualidade phred do sítio, resultado dos filtros e anotações, com chaves reservadas como AC, AN e DB | Critérios de qualidade da leitura; presença no dbSNP e contagens alélicas |
| FORMAT, GT, DP e GQ | Campos de amostra: genótipo, com 0 para o alelo de referência, profundidade e qualidade da chamada | Indicam se o genitor é heterozigoto ou homozigoto, base do cálculo de transmissão |

*Fonte: elaborado pela autora, com base em Danecek et al. (2011).*

O arquivo informa qual variante existe e em que genótipo, mas não especifica sobre patogenicidade, frequência e risco, o que torna as bases de referência parte essencial da entrada. Sua leitura requer quatro cuidados (DANECEK et al., 2011) como conferir a versão do genoma de referência, porque as mesmas coordenadas apontam para posições diferentes em GRCh37 e GRCh38. Em seguida, normalizar a representação da variante, já que descrições distintas do mesmo evento não se encontram em comparação direta e decompor os sítios multialélicos, que reúnem em uma linha alelos que precisam ser avaliados em separado. Por fim, distinguir QUAL, qualidade do sítio, de GQ, qualidade da chamada de genótipo.

Identificou-se uma limitação maior que afeta a um dos quatro genes do escopo, resultante do fato de o fluxo de trabalho gera um arquivo de variantes curtas, e as repetições em série confundem a detecção de variantes em regiões complexas do genoma (VAN DER AUWERA; O'CONNOR, 2020). A expansão de hexanucleotídeos do C9orf72 entra no modelo como um parâmetro da literatura, por isso, Douglas e Baralle (2024) buscaram suas frequências em estudos anteriores, já que a detecção laboratorial desse gene está fora do escopo. A entrada efetiva do desenvolvimento será uma massa sintética que reproduz a estrutura do formato nas regiões dos quatro genes selecionados. Por ser baseada na literatura, essa avaliação verifica se o artefato se comporta como esperado em cenários predefinidos. No entanto, ela não valida as afirmações da própria literatura, uma limitação que condiciona todo o processo.

#### 4.2.2 Bases de Dados Genômicas de Referência

O ClinVar é um arquivo público de interpretação clínica formado por submissões de mais de 800 organizações. Como uma mesma variante pode receber interpretações divergentes, a plataforma agrega esses dados e atribui um status de revisão que varia em uma escala de zero a quatro estrelas (LANDRUM et al., 2018; NCBI, 2026a). Interessam Pathogenic e Likely pathogenic, que sustentam a atribuição de risco e Uncertain significance, cujo tratamento segue o estudo que fornece os parâmetros de penetrância, já que Douglas e Baralle (2024) contaram como causadoras apenas as duas primeiras. Como a classificação é revisável e as atualizações semanais não são arquivadas, só a publicação mensal permite reproduzir uma estimativa depois (NCBI, 2026b).

O dbSNP é o catálogo geral da variação genética e não exige frequência alélica mínima ou neutralidade funcional das variações depositadas (SHERRY et al., 2001): cataloga a variação sem afirmar se ela causa doença. O rsID é identificador complementar, e a chave de coordenadas e alelos permanece como critério primário, porque nem sempre está presente e pode ser retirado entre versões da base, hoje na edição 157 (NCBI, 2025). Suas frequências populacionais ajudam a verificar inconsistências de anotação, mas refletem as populações submetidas, predominantemente de ascendência europeia (DOUGLAS; BARALLE, 2024), limitação que pesa em um trabalho destinado à população brasileira.

#### 4.2.3 Parâmetros Epidemiológicos e Genéticos

Para estimar com precisão a probabilidade e a idade de adoecimento de um portador, a análise deve separar informações da literatura que costumam ser tratadas de forma unificada. Essa abordagem requer o isolamento entre a presença da variante no arquivo clínico, a taxa de penetrância no grupo analisado, a curva de probabilidade de manifestação ao longo do tempo e as nuances de variabilidade fenotípica entre indivíduos com o mesmo genótipo.

As estimativas de Douglas e Baralle (2024) são agregadas por gene e deixam de fora a distribuição ao longo da idade, exigida pelas curvas de risco temporal. No caso do gene C9orf72, as estimativas disponíveis baseiam-se no estudo de Murphy et al. (2017), que avaliaram a penetrância relacionada à idade via curvas de Kaplan-Meier em uma amostra de 1.170 indivíduos. Essa análise indicou uma idade mediana de início dos sintomas aos 58,0 anos (IC 95% 57,0–59,0) e uma penetrância descrita como próxima de completa aos 83 anos. Para os outros três genes se apresenta maior variabilidade na literatura, conforme evidenciado pela revisão de Richard et al. (2026) sobre o comportamento da penetrância nessa doença. No caso do SOD1, os autores apontam uma penetrância baixa antes dos 40 a 50 anos que se torna quase completa após os 50 a 60 anos nas mutações mais frequentes, ressalvando a variante D91A em heterozigose como uma exceção. Já para os genes TARDBP e FUS, as evidências indicam, uma penetrância incompleta e dependente do contexto genético e uma taxa de desenvolvimento do quadro clínico superior a 80% em portadores adultos. São descrições por faixa etária, de granularidade menor do que a de uma tabela acumulada ano a ano, de modo que os quatro genes entrarão no modelo com resoluções diferentes. O sexo entra como atributo desses parâmetros, com risco ao longo da vida de 1 em 347 para homens e 1 em 436 para mulheres (DOUGLAS; BARALLE, 2024, p. 294), assim como o modo de herança.

O encadeamento entre as fontes parte do VCF, identifica as variantes pela chave de coordenadas e alelos, consulta o ClinVar e soma os parâmetros da literatura. A verificação de qualidade prevista nesta fase (CHAPMAN et al., 2000) acompanha esse processo por meio de indicadores mensuráveis, avaliando taxas de variantes aprovadas nos filtros, volume de variantes registradas encontradas no ClinVar e seus estados de revisão, a proporção de variantes de significado incerto e a coerência entre as versões de referência adotadas.

Essa etapa resulta no estabelecimento de um conjunto de dados estruturado, que reúne as curvas de penetrância por idade para os quatro genes, o modelo de herança, o sexo, a população de origem e as incertezas associadas a cada estimativa.

### 4.3. Preparação dos Dados

A fase de preparação engloba o pipeline de ETL (Extract, Transform, Load) genômico responsável por higienizar, normalizar e preparar as variáveis para os motores estatísticos.

[VCF Materno/Paterno] ➔ [Ingestão & Validação] ➔ [Filtragem por Genes Alvo] ➔ [Anotação (ClinVar/dbSNP)] ➔ [Matriz de Variáveis Controladas]

- Ingestão e Validação: Filtro de qualidade de leitura para descartar artefatos de sequenciamento.
- Filtragem por Região de Interesse: Aplicação de máscaras de coordenadas genômicas delimitando exclusivamente os exons e regiões intrônicas adjacentes dos quatro genes de estudo (SOD1, C9orf72, TARDBP, FUS).
- Normalização e Anotação de Variantes: Decomposição de variantes complexas (multialélicas) e cruzamento automatizado das chaves genômicas com as tabelas do ClinVar e dbSNP.
- Construção do Vetor Genotípico Parental: Mapeamento do genótipo dos pais em termos de dosagem alélica (0 = homozigoto selvagem; 1 = heterozigoto; 2 = homozigoto mutante), que alimentará o nó inicial da Rede Bayesiana.

### 4.4. Modelagem

Na fase de modelagem constitui o núcleo estocástico do artefato, composto por três componentes matemático-computacionais integrados:

NÚCLEO ESTOCÁSTICO: Redes Bayesianas (Dependência Gen.) -> Simulação Monte Carlo (Propag. Incerteza) -> Análise de Sobrev. (Lifelines / Risco)

#### A. Rede Bayesiana (Representação de Dependências)

Construção de um Grafo Acíclico Dirigido (DAG) aplicando os formalismos de Pearl (1988) e Koller e Friedman (2009).

- Nós de Entrada (Variáveis Aleatórias): Genótipo Materno e Genótipo Paterno.
- Nó Intermediário (Herança Mendeliana): Genótipo do Descendente, cujas Tabelas de Probabilidade Condicional (CPT) derivam da segregação alemática.
- Nó de Saída (Status de Portador / Expressão): Probabilidade de portar a variante de risco combinada ao fator modificador de penetrância incompleta específico do gene identificado.

#### B. Simulação de Monte Carlo (Propagação de Incerteza)

- Execução de reamostragens sucessivas via algoritmo de Monte Carlo sobre a Rede Bayesiana, simulando N = 10.000 eventos de fecundação e transmissão hipotética.
- Permite estimar a distribuição de probabilidade empírica do fenótipo da prole diante de cenários de penetrância incerta.

#### C. Análise de Sobrevivência (Projeção Temporal de Risco)

Integração do status probabilístico do descendente a funções de risco acumulado.

- Função de Sobrevivência S(t): Modela a probabilidade de um indivíduo portador permanecer assintomático até a idade t.
- Função de Risco Incondicional / Penetrância F(t) = 1 - S(t): Gera estimativas da idade provável de início dos sintomas baseadas em distribuições parametricas calibradas com dados da literatura.

#### D. Arquitetura Modular e Tecnologias

O software construído sob uma arquitetura modular em Python:

- Biopython e PyVCF: Manipulação e parsing de arquivos VCF.
- Pandas e NumPy: Estruturação e manipulação matricial dos dados genômicos e CPTs.
- PyMC: Implementação e inferência probabilística nas Redes Bayesianas e simulação de Monte Carlo.
- Lifelines: Modelagem da análise de sobrevivência e curvas de risco temporal.
- Matplotlib e Seaborn: Renderização das curvas de penetrância e gráficos de risco para interface gráfica de suporte clínico.

### 4.5. Avaliação

Nesta etapa, verifica-se a acurácia, estabilidade e consistência do modelo desenvolvido frente aos objetivos do negócio.

- Simulações com Dados Sintéticos: Devido a restrições éticas e de conformidade com a LGPD, o artefato foi testado com genótipos sintéticos criados para simular 5 cenários clínicos familiares representativos (ex.: Pai heterozigoto para variante de alta penetrância no SOD1 vs. Mãe portadora da expansão de hexanucleotídeos no C9orf72).

Métricas e Critérios de Validação:

- Aderência Teórica: Comparação das frequências obtidas na Simulação de Monte Carlo com as distribuições teóricas esperadas pela genética populacional.
- Estabilidade Numérica: Avaliação da variação do desvio padrão e erro padrão dos resultados em execuções sucessivas (N=1.000, N=10.000 e N=100.000 iterações).
- Coerência das Curvas de Risco: Verificação do comportamento assintótico das curvas temporais de sobrevivência/manifestação em relação aos dados de idade de início descritos por Douglas e Baralle (2024).

### 4.6. Implantação

Na fase final do CRISP-DM a entrega do artefato para uso em ambiente experimental de pesquisa e suporte ao aconselhamento.

- Protótipo Funcional: Empacotamento do código em uma aplicação modular.
- Interface de Visualização Clínica: Módulo gráfico que exibe o perfil de variantes detectadas, a probabilidade de transmissão e as curvas de risco de manifestação por idade, de forma simplificada para interpretação médica.
- Documentação Técnica e Repositório: Disponibilização da arquitetura do sistema, especificações das APIs internas, dicionário de dados e instruções de instalação para uso por equipes de pesquisa.
- Diretrizes de Apropriação: Inclusão explícita no relatório do sistema de avisos legais indicando o caráter preditivo-experimental da solução, reforçando seu papel estritamente voltado ao apoio à decisão e não como diagnóstico autônomo.

## 5. RESULTADOS

O objetivo é demonstrar o funcionamento prático do artefato e validar sua lógica estocástica diante de cenários clínicos representativos. Como o sistema opera sob a perspectiva da Design Science Research e do CRISP-DM, a seção de resultados deve apresentar as saídas geradas em cada etapa do pipeline (ingestão/anotação, inferência bayesiana, simulação de Monte Carlo e análise de sobrevivência).

## 6. ANÁLISE E DISCUSSÃO

- Interpretação dos resultados
- Conexão com a fundamentação teórica
- Limitações

## 7. CONCLUSÃO

- Resposta ao problema
- Contribuições
- Trabalhos futuros

## Referências

BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Dispõe sobre a proteção de dados pessoais e altera a Lei nº 12.965, de 23 de abril de 2014 (Marco Civil da Internet). Brasília, DF: Presidência da República, 2018. Disponível em: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm. Acesso em: 29 set. 2026.

CHAPMAN, P. et al. CRISP-DM 1.0: step-by-step data mining guide. [S. l.]: SPSS Inc., 2000. Disponível em: https://public.dhe.ibm.com/software/analytics/spss/documentation/modeler/14.2/es/CRISP-DM.pdf. Acesso em: 27 maio 2026.

DANECEK, P. et al. The variant call format and VCFtools. Bioinformatics, [s. l.], v. 27, n. 15, p. 2156-2158, 2011. Disponível em: https://doi.org/10.1093/bioinformatics/btr330. Acesso em: 1 maio 2026.

DAVIDSON-PILON, C. Introduction to survival analysis: lifelines 0.30.3 documentation. [S. l.], 2026. Disponível em: https://lifelines.readthedocs.io/. Acesso em: 13 maio 2026.

DEGREGORI, D. B. Soluções exatas no modelo de Ising unidimensional com interações competitivas na presença de campo externo. 2016. 71 f. Dissertação (Mestrado em Física) – Instituto de Física, Universidade Federal do Rio Grande do Sul, Porto Alegre, 2016.

DOUGLAS, A. G. L.; BARALLE, D. Reduced penetrance of gene variants causing amyotrophic lateral sclerosis. Journal of Medical Genetics, [s. l.], v. 61, p. 294-297, 2024. Disponível em: http://dx.doi.org/10.1136/jmg-2023-109580. Acesso em: 13 maio 2026.

FELDMAN, E. L. et al. Amyotrophic lateral sclerosis. The Lancet, [s. l.], v. 400, n. 10360, p. 1363-1380, 2022. Disponível em: https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(22)01272-7/abstract. Acesso em: 16 set. 2026.

GAZOLA, G. M. Modelo computacional para analisar o efeito do fingolimod no bloqueio de migração de células T CD8+ na esclerose múltipla. 2025. 39 f. Trabalho de Conclusão de Curso (Graduação em Engenharia Computacional) – Faculdade de Engenharia, Universidade Federal de Juiz de Fora, Juiz de Fora, 2025.

GOUTMAN, S. A. et al. Recent advances in the diagnosis and prognosis of amyotrophic lateral sclerosis. The Lancet Neurology, [s. l.], v. 21, n. 5, p. 480-493, 2022. Disponível em: https://pmc.ncbi.nlm.nih.gov/articles/PMC9513753/. Acesso em: 28 maio 2026.

HEVNER, A. R.; MARCH, S. T.; PARK, J.; RAM, S. Design science in information systems research. MIS Quarterly, [s. l.], v. 28, n. 1, p. 75-105, 2004. Disponível em: https://wise.vub.ac.be/sites/default/files/thesis_info/design_science.pdf. Acesso em: 1 jun. 2026.

KINJO, E. M. et al. Modelagem Bayesiana aplicada para cálculo da probabilidade de falha em Sistemas de Saúde IoT. RISTI – Revista Ibérica de Sistemas e Tecnologias de Informação, Porto, n. 47, p. 87-108, set. 2022. Disponível em: https://doi.org/10.17013/risti.47.87-108. Acesso em: 13 maio 2026.

KOLLER, D.; FRIEDMAN, N. Probabilistic graphical models: principles and techniques. Cambridge, MA: MIT Press, 2009. Disponível em: https://mitpress.mit.edu/9780262013192/probabilistic-graphical-models/. Acesso em: 1 jun. 2026.

LANDRUM, M. J. et al. ClinVar: improving access to variant interpretations and supporting evidence. Nucleic Acids Research, [s. l.], v. 46, n. D1, p. D1062-D1067, 2018. Disponível em: https://academic.oup.com/nar/article/46/D1/D1062/4641904. Acesso em: 17 maio 2026.

MATOSO, D. E. C. Modelagem computacional de neurônios motores inferiores para o estudo de alterações biofísicas decorrentes da esclerose lateral amiotrófica. 2017. 117 f. Dissertação (Mestrado em Engenharia Elétrica) – Faculdade de Engenharia Elétrica e de Computação, Universidade Estadual de Campinas, Campinas, 2017.

METROPOLIS, N.; ULAM, S. The Monte Carlo method. Journal of the American Statistical Association, Washington, v. 44, n. 247, p. 335-341, set. 1949. Disponível em: https://web.williams.edu/Mathematics/sjmiller/public_html/341Fa09/handouts/MetropolisUlam_TheMonteCarloMethod.pdf. Acesso em: 17 maio 2026.

MURPHY, N. A. et al. Age-related penetrance of the C9orf72 repeat expansion. Scientific Reports, [s. l.], v. 7, n. 1, art. 2116, 2017. Disponível em: https://doi.org/10.1038/s41598-017-02364-1. Acesso em: 18 set. 2026.

NCBI – NATIONAL CENTER FOR BIOTECHNOLOGY INFORMATION. Review status in ClinVar. Bethesda, MD: NCBI, 2024. Disponível em: https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/. Acesso em: 18 set. 2026.

NCBI – NATIONAL CENTER FOR BIOTECHNOLOGY INFORMATION. dbSNP Build 157 Release. NCBI Insights, Bethesda, MD, 18 mar. 2025. Disponível em: https://ncbiinsights.ncbi.nlm.nih.gov/2025/03/18/dbsnp-release-157/. Acesso em: 18 set. 2026.

NCBI – NATIONAL CENTER FOR BIOTECHNOLOGY INFORMATION. Release cycle. Bethesda, MD: NCBI, 2026. Disponível em: https://www.ncbi.nlm.nih.gov/clinvar/docs/release_cycle/. Acesso em: 18 set. 2026.

PANCOTTI, C. et al. Deep learning methods to predict amyotrophic lateral sclerosis disease progression. Scientific Reports, [s. l.], v. 12, n. 1, art. 13738, 2022. Disponível em: https://doi.org/10.1038/s41598-022-17805-9. Acesso em: 13 maio 2026.

PAPAIZ, F. et al. Predicting ALS progression using autoregressive deep learning models. Intelligence-Based Medicine, [s. l.], v. 11, art. 100247, 2025. Disponível em: https://doi.org/10.1016/j.ibmed.2025.100247. Acesso em: 13 maio 2026.

PEARL, J. Probabilistic reasoning in intelligent systems: networks of plausible inference. San Francisco: Morgan Kaufmann, 1988. Disponível em: https://www.sciencedirect.com/book/9780080514895/probabilistic-reasoning-in-intelligent-systems. Acesso em: 20 maio 2026.

PEFFERS, K.; TUUNANEN, T.; ROTHENBERGER, M. A.; CHATTERJEE, S. A design science research methodology for information systems research. Journal of Management Information Systems, [s. l.], v. 24, n. 3, p. 45-77, 2007. Disponível em: https://www.researchgate.net/publication/284503626_A_design_science_research_methodology_for_information_systems_research. Acesso em: 24 maio 2026.

PYMC DEVELOPMENT TEAM. Introductory overview of PyMC. [S. l.], 2026. Disponível em: https://www.pymc.io/. Acesso em: 13 maio 2026.

RICHARD, E. et al. From mutation to manifestation: penetrance in amyotrophic lateral sclerosis. Genes, [s. l.], v. 17, n. 5, art. 576, 2026. Disponível em: https://doi.org/10.3390/genes17050576. Acesso em: 29 set. 2026.

SHERRY, S. T. et al. dbSNP: the NCBI database of genetic variation. Nucleic Acids Research, [s. l.], v. 29, n. 1, p. 308-311, 2001. Disponível em: https://academic.oup.com/nar/article/29/1/308/1116004. Acesso em: 1 maio 2026.

STEPHENS, Z. D. et al. Big data: astronomical or genomical? PLoS Biology, [s. l.], v. 13, n. 7, art. e1002195, 2015. Disponível em: https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1002195. Acesso em: 12 maio 2026.

THE 1000 GENOMES PROJECT CONSORTIUM. A global reference for human genetic variation. Nature, [s. l.], v. 526, n. 7571, p. 68-74, 2015. Disponível em: https://doi.org/10.1038/nature15393. Acesso em: 17 set. 2026.

VAN DER AUWERA, G. A.; O'CONNOR, B. D. Genomics in the cloud: using Docker, GATK, and WDL in Terra. Sebastopol: O'Reilly Media, 2020. Disponível em: https://www.oreilly.com/library/view/genomics-in-the/9781491975183/. Acesso em: 13 maio 2026.

WESTENENG, H.-J. et al. Prognosis for patients with amyotrophic lateral sclerosis: development and validation of a personalised prediction model. The Lancet Neurology, [s. l.], v. 17, n. 5, p. 423-433, 2018. Disponível em: https://www.thelancet.com/journals/laneur/article/PIIS1474-4422(18)30089-9/abstract. Acesso em: 17 maio 2026.

ZATZ, M. O estudo do genoma humano contribuindo para a compreensão, o diagnóstico e a prevenção de doenças genéticas: o exemplo das doenças neuromusculares. Revista de Medicina, São Paulo, v. 80, n. 1, p. 24-40, jan./mar. 2001.
