# 02 — Modelo matemático do núcleo estocástico

Notação: gene g ∈ {SOD1, C9orf72, TARDBP, FUS}. Os quatro genes ficam em cromossomos diferentes (21, 9, 1, 16), logo as transmissões são independentes entre genes (sem ligação).

## 1. Rede Bayesiana (DAG) por gene

```
Dose materna d_m ──┐
                   ├─→ Alelo transmitido a_m, a_f ─→ Dose do descendente D ─→ Portador C ─→ Manifesta M ─→ Idade de início T
Dose paterna  d_f ──┘                                                  ↑                     ↑
                                                       Herança (dominante/recessiva)   Penetrância π ~ Beta(α, β)
                                                                                             Sexo (deslocamento δ)
```

Variáveis:
- `d_m, d_f ∈ {0, 1, 2}`: dosagem alélica dos pais, observada (vem do VCF anotado). 0 = selvagem, 1 = heterozigoto, 2 = homozigoto para a variante de risco.
- `a_m ~ Bernoulli(d_m / 2)`, `a_f ~ Bernoulli(d_f / 2)`: o alelo transmitido carrega a variante.
- `D = a_m + a_f ∈ {0, 1, 2}`: dosagem do descendente.
- `C = 1[D ≥ 1]` se herança dominante; `C = 1[D = 2]` se recessiva (SOD1 p.D91A). Homozigoto dominante usa a mesma penetrância (multiplicador 1,0 configurável).
- `π ~ Beta(α, β)`: penetrância vitalícia do gene, com prior calibrada ao ponto + IC 95% de Douglas & Baralle (2024).
- `M ~ Bernoulli(C · π)`: manifestação clínica em algum momento da vida.
- `T | M = 1 ~ G(t)`: idade de início, Weibull(k, λ) (ou log-normal), mais deslocamento por sexo `δ_sexo` (C9orf72: δ_M = −1, δ_F = +1; demais genes δ = 0 até haver evidência).

### CPT de segregação P(D = k | d_m, d_f)

Convolução de duas Bernoulli; cobre pais homozigotos sem caso especial.

| d_m × d_f | P(D=0) | P(D=1) | P(D=2) |
|---|---|---|---|
| 0 × 0 | 1 | 0 | 0 |
| 1 × 0 | 0,5 | 0,5 | 0 |
| 1 × 1 | 0,25 | 0,5 | 0,25 |
| 2 × 0 | 0 | 1 | 0 |
| 2 × 1 | 0 | 0,5 | 0,5 |
| 2 × 2 | 0 | 0 | 1 |

### Fórmulas exatas (referência para o teste de aderência)

- Dominante: `P(C=1) = 1 − (1 − d_m/2)(1 − d_f/2)`.
- Recessiva: `P(C=1) = (d_m/2)(d_f/2)`.
- `P(M=1) = P(C=1) · E[π] = P(C=1) · α/(α+β)`.
- Weibull(k, λ): mediana `λ (ln 2)^(1/k) + δ`; média `λ Γ(1 + 1/k) + δ`.

## 2. Calibração das priors (módulo `calibracao.py`)

### Beta(α, β) a partir de ponto p e IC 95% [l, u]

Os ICs são assimétricos (ex.: SOD1 0,54 [0,327; 0,886]), então usar **ajuste de quantis**, não de momentos. Com `θ = (ln α, ln β)` minimizar por Nelder-Mead (`scipy.optimize.minimize`):

```
L(θ) = [F_Beta(l) − 0,025]² + [F_Beta(u) − 0,975]² + w · [F_Beta(p) − 0,5]²,   w = 0,5
```

(três restrições para dois parâmetros). **Achado da calibração (24/10/2026)**: os quatro IC de Douglas & Baralle são simétricos em escala logarítmica (ex.: SOD1 ln 0,54 dista 0,50 de ln 0,327 e de ln 0,886), típico de estimativas de razão; uma Beta não reproduz ponto e IC ao mesmo tempo. Decisão D12: `peso_ponto = 1,0` faz do ponto publicado a mediana da Beta e reproduz o limite inferior; o limite superior fica subestimado (SOD1: 0,74 vs 0,886) e o erro é reportado na Tabela 6. Com `peso_ponto = 0` a Beta reproduz o IC e a mediana sobe (SOD1 0,64). Saída: tabela com (α, β), mediana e IC implícitos vs publicados.

### Distribuição de início G(t) a partir de pontos de Kaplan-Meier ou faixas etárias

Entrada: pontos `(t_i, pen_i)` da literatura (Murphy 2017 para C9orf72, digitalizados no YAML; faixas etárias de Richard 2026 para os demais, placeholders com `confirmar: true`).
1. Normalizar pelo platô: `g_i = pen_i / pen_platô` (isso remove o nível, que vem de Douglas & Baralle, e deixa só a forma).
2. Ponto de partida pela linearização Weibull: `ln(−ln(1 − g)) = k ln t − k ln λ` (regressão linear).
3. Refinar com `scipy.optimize.least_squares` sobre `G(t_i; k, λ) − g_i`. Alternativa log-normal; escolher pela soma de quadrados residual.

Valores de partida provisórios (até a autora confirmar com Richard et al. 2026): C9orf72 mediana ≈ 58 anos (Murphy); SOD1 ≈ 50; TARDBP ≈ 54; FUS ≈ 44 (início mais precoce). Todos com `confirmar: true` no YAML.

### Distribuição de início a partir de estatísticas publicadas (forma fechada; 08/11/2026, D22)

Quando a literatura publica estatísticas e não pontos de curva (Berdyński et al. 2022: média e desvio padrão da idade de início; McFarlane et al. 2025: mediana e IQR), `calibracao.ajustar_inicio(estatisticas=...)` resolve (k, λ) sem ajuste numérico de curva:

- **Momentos** `{media: m, dp: s}`: `CV² = s²/m² = Γ(1 + 2/k)/Γ(1 + 1/k)² − 1` depende só de k e decresce com k → k por bissecção (`scipy.optimize.brentq` em [0,1; 500]); depois `λ = m / Γ(1 + 1/k)`.
- **Quantis** `{mediana: Q₂, iqr: Q₃ − Q₁}` (casamento de quantis): com `Q(p) = λ(−ln(1 − p))^{1/k}`, `IQR/Q₂ = [(ln 4)^{1/k} − (ln 4/3)^{1/k}] / (ln 2)^{1/k}` depende só de k e decresce com k → k por bissecção; depois `λ = Q₂ / (ln 2)^{1/k}`.
- Log-normal alternativa (coluna da Tabela 6): momentos `σ² = ln(1 + CV²)`, `μ = ln m − σ²/2`; quantis `μ = ln Q₂`, `σ = asenh(IQR / 2Q₂) / z₀,₇₅`.

No YAML: `inicio: {distribuicao: weibull, estatisticas: {media: 50.2, dp: 10.6}}` ou `estatisticas: {mediana: 58.30, iqr: 16.23}`, no lugar de `pontos` (exatamente um dos dois por gene). A Tabela 6 informa `metodo_inicio` (pontos, momentos ou quantis); sem pontos não há soma de quadrados residual. Os pontos continuam valendo para o C9orf72 (curva de Murphy) e, se a autora preferir, para o FUS.

**Reconciliação Murphy × Douglas & Baralle (C9orf72)**: Douglas & Baralle fornecem π (nível populacional, 0,33); Murphy fornece apenas a forma de G(t). Análise de sensibilidade adicional com π = 0,9 ("cenário familiar") para mostrar o efeito da escolha.

## 3. Modelo de cura mista e projeção temporal

- `F(t) = P(C=1) · π · G(t)` é a probabilidade de o descendente ter manifestado até a idade t; `S(t) = 1 − F(t)`.
- `F(∞) = P(C=1) · π` (fração que manifesta); `1 − F(∞)` é a "fração curada" (nunca manifesta). Consequência: a mediana de sobrevivência é infinita quando `F(∞) < 0,5`; reportar percentis (ex.: idade em que F atinge 90% de F(∞)) e risco condicional em vez da mediana.
- Função de risco (hazard): `h(t) = f(t) / S(t)`, com `f = dF/dt`; usado na figura de pico de risco. A faixa 60–75 anos é o pico de incidência populacional (Feldman et al., 2022) e só é comparada, como referência, com o pico de h(t) do **risco combinado** de cada cenário; o pico de cada variante é propriedade da sua própria G(t) e não é aprovado nem reprovado por essa faixa (D25).

### Condicionamento à idade atual a (assintomático)

- Portador conhecido: `P(T ≤ t | T > a) = (F_c(t) − F_c(a)) / (1 − F_c(a))`, com `F_c = π G`; risco vitalício residual `π (1 − G(a)) / (1 − π G(a))`.
- Descendente não testado com prior mendeliano `q = P(C=1)`:
  - atualização bayesiana: `P(C=1 | assintomático em a) = q (1 − π G(a)) / (1 − q π G(a))`;
  - `P(T ≤ t | T > a) = q (F_c(t) − F_c(a)) / (1 − q F_c(a))`.
- No Monte Carlo isso equivale a **condicionamento por rejeição**: manter os sorteios com `T > a` ou `M = 0`.

### Sexo

`T = T_0 + δ_sexo`. Para C9orf72 a diferença de 2 anos entre homens e mulheres (Goutman 2022) é aplicada como δ_M = −1, δ_F = +1, preservando a média agrupada. Os demais genes ficam com δ = 0 até existir evidência no YAML.

### Vários genes na mesma família

Independência entre genes: `P(qualquer manifestação) = 1 − ∏_g (1 − P(M_g))`; `F_qualquer(t) = 1 − ∏_g (1 − F_g(t))`. No MC: `M_qualquer = max_g M_g` e `T_qualquer = min_g T_g` entre os genes que manifestam. Interação oligogênica fica explicitamente fora do escopo (limitação a registrar na seção 5).

## 4. Monte Carlo

Um sorteio = uma fecundação hipotética: sorteia `a_m, a_f, π, M, T` conjuntamente. **N = 10.000** sorteios é o que o TCC chama de "10.000 eventos de fecundação". Estimadores: `P̂ = média`, erro padrão teórico `EP = √(p(1−p)/N)`.

### PyMC (motor declarado no TCC)

```python
import pymc as pm, pytensor.tensor as pt
with pm.Model(coords={"gene": genes}) as modelo:
    dm = pm.Data("dose_materna", d_m, dims="gene")
    df = pm.Data("dose_paterna", d_f, dims="gene")
    a_m = pm.Bernoulli("alelo_materno", p=dm / 2, dims="gene")
    a_f = pm.Bernoulli("alelo_paterno", p=df / 2, dims="gene")
    dose = pm.Deterministic("dose_descendente", a_m + a_f, dims="gene")
    portador = pm.Deterministic("portador", pt.switch(recessivo, pt.eq(dose, 2), pt.ge(dose, 1)), dims="gene")
    pen = pm.Beta("penetrancia", alpha=alpha, beta=beta, dims="gene")
    manifesta = pm.Bernoulli("manifesta", p=portador * pen, dims="gene")
    t0 = pm.Weibull("idade_inicio_latente", alpha=k, beta=lam, dims="gene")   # alpha = forma k, beta = escala λ
    idade = pm.Deterministic("idade_inicio", t0 + delta_sexo, dims="gene")
    pm.Deterministic("manifesta_qualquer", pt.max(manifesta))
    idata = pm.sample_prior_predictive(draws=N, random_seed=seed)
```

Bandas de credibilidade: reutilizar os sorteios `π_j` e calcular `F_j(t) = P(C) · π_j · G(t)`, tomando percentis 2,5 / 50 / 97,5 sobre j. Para o risco combinado (linha "qualquer lócus" da Tabela 3 e curva correspondente da Figura 4) vale a mesma propagação, `F_any,j(t) = 1 − ∏_g (1 − P(C_g) · π_{g,j} · G_g(t))`, com percentis sobre j — e não a combinação dos quantis de cada lócus, que alarga a banda (D26).

Opcional (ilustra "atualização de crenças"): `pm.sample()` em um modelo Beta-Binomial sobre uma coorte sintética de portadores para mostrar o estreitamento da posterior de π.

### Amostrador NumPy equivalente (para N = 1e5 × 30 repetições e verificação cruzada)

```python
rng = np.random.default_rng(seed)
a_m = rng.random((N, 4)) < d_m / 2;  a_f = rng.random((N, 4)) < d_f / 2
dose = a_m.astype(int) + a_f.astype(int)
portador = np.where(recessivo, dose == 2, dose >= 1)
pen = rng.beta(alpha, beta, (N, 4))
manifesta = rng.random((N, 4)) < portador * pen
idade = lam * rng.weibull(k, (N, 4)) + delta_sexo
```

Teste: PyMC ≈ NumPy ≈ exato, com |diferença| < 4·EP.

**Armadilha de nomes do Weibull**: PyMC `Weibull(alpha=k, beta=λ)`; Lifelines `rho_ = k`, `lambda_ = λ`; scipy `weibull_min(c=k, scale=λ)`.

## 5. Lifelines sem dados individuais (módulo `sobrevivencia.py`)

Construir uma coorte sintética a partir dos sorteios do MC: `duracao = min(T, 90)` e `evento = (M = 1) ∧ (T ≤ 90)`; os demais são censurados no horizonte de 90 anos (ou na idade atual `a` na variante "assintomático hoje").

- `KaplanMeierFitter().fit(duracao, evento)`: `survival_function_`, `confidence_interval_` (Greenwood), `survival_function_at_times([40, 50, 60, 70, 80])`, `percentile(0.9)`, `conditional_time_to_event_`; `median_survival_time_` = inf quando o risco vitalício < 50% (assinatura do modelo de cura, explicar no texto).
- `WeibullFitter` apenas entre portadores que manifestam (recupera k, λ).
- `MisturaCuraWeibullFitter(ParametricUnivariateFitter)` com `_cumulative_hazard(params, t) = −log(1 − π (1 − exp(−(t/λ)^k)))` e parâmetros `(pi_, lambda_, rho_)`: ajustado à coorte sintética deve **recuperar** π, k, λ de entrada com erro < 5% (tabela de recuperação de parâmetros = evidência de coerência interna).
- Figuras: F(t) e S(t) por cenário com banda Beta e degrau KM com IC sobreposto; histograma de idade de início por sexo com densidade Weibull.

## 6. Métricas de avaliação (seção 4.5)

- **Aderência teórica**: `|P̂_MC(C) − P_exata(C)|` com IC de 95% do MC; teste binomial/qui-quadrado das frequências de D ∈ {0,1,2} vs CPT.
- **Estabilidade numérica**: para N ∈ {1e3, 1e4, 1e5} e R = 30 sementes: DP entre execuções de P̂(C), P̂(M) e mediana de T; comparar com `EP_teórico = √(p(1−p)/N)`; gráfico log-log (inclinação esperada −1/2).
- **Coerência das curvas**: mediana/percentis de início (Lifelines) vs literatura por gene; `F(∞) ≈ P(C)·π`; posição do pico de h(t) por lócus e do risco combinado (a faixa 60–75 anos só para o combinado, como referência; D25).
- **Tempo de processamento** por cenário e por N (PyMC e NumPy separados).

## 7. Limitações a declarar na seção 5

Independência entre genes (sem oligogenia); penetrância populacional de coortes europeias/norte-americanas; idade de início de SOD1/TARDBP/FUS provisória até confirmação de Richard et al. 2026; efeito do sexo só documentado para C9orf72; sem fatores modificadores ambientais; dados sintéticos; sem mosaicismo, de novo ou faseamento.
