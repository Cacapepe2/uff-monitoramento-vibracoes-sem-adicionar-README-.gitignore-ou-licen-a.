# Protocolo experimental e Isolation Forest

Versão: `experimental-v1`, preparada em 10/11/2026. Arquitetura preservada: ESP32 → FastAPI → SQLite. O firmware e o Wokwi não precisam ser alterados para executar este protocolo.

**Estado científico inicial:** medições antigas sem condição física conhecida não são uma baseline normal. Não são reclassificadas, associadas retroativamente ou usadas no treino. Um planejamento cria metadados, não medições. A evidência física do Marco 3 comprova comunicação e persistência; ainda não comprova a eficácia do detector sob as seis condições deste protocolo.

## Plano e critérios definidos antes da coleta

| Sessão | Condição planejada | Meta de registros elegíveis | Papel |
|---|---|---:|---|
| NORMAL_01 | Montagem original, operação normal declarada | 100 | Única fonte de treino |
| NORMAL_02 | Mesma condição, nova sessão no tempo | 50 | Validação separada |
| BORRACHA_01 | Mudança documentada da base de apoio | 50 | Mudança experimental conhecida |
| MADEIRA_01 | Mudança documentada de superfície rígida | 50 | Mudança experimental conhecida |
| TOQUE_01 | Intervalos de perturbações leves na base | Encerramento manual; mínimo analítico 50 | Condição mista; analisar eventos |
| RETORNO_01 | Restaurar montagem original | 50 | Verificação de retorno, separada do treino |

O mínimo de 50 para TOQUE_01 e o mínimo de cinco registros por fase de evento são escolhas operacionais desta versão do protocolo, não resultados medidos nem garantias de significância estatística. Contagens de 100/50 permitem a comparação descritiva planejada; não demonstram generalização a outros ventiladores.

Um experimento contém seis sessões com códigos únicos. Novas campanhas têm novo UUID e novas sessões: não misturar campanhas ou concatenar dados para completar artificialmente uma baseline. Sessões encerradas não são reabertas. Se uma coleta for interrompida antes da meta, o relatório informa insuficiência; repita em nova campanha quando necessário.

### Controles de bancada

Descrever, ao iniciar cada sessão: montagem, material e posição da base, fixação/orientação do MPU, alimentação e ajuste do ventilador, tempo de estabilização e alterações realizadas. Manter alimentação, orientação e fixação constantes ao mudar apenas o apoio, quando possível. A rotação não é medida: manter o ajuste de alimentação não comprova RPM constante. Registrar essa limitação e qualquer mudança não planejada nas observações.

Não aplicar massas, bloquear pás ou tocar partes móveis/energizadas. Em TOQUE_01, usar somente perturbações leves e seguras na base, com proteção do ventilador e sem alterar conexões elétricas. O TACH permanece desconectado/desabilitado.

## Sessões e vínculo verificável

Estados: `planejada → ativa → encerrada`. Somente uma sessão pode estar ativa por dispositivo, mesmo entre campanhas. Uma descrição observada da condição é obrigatória ao iniciar; a descrição planejada não é tratada automaticamente como observação física.

O início é registrado pelo servidor em UTC, junto com o maior ID de medição já existente e `coleta_a_partir`. A guarda inicial padrão é **10 s**, depois da estabilização manual da montagem. Essa guarda é configurável e fica registrada. Medições durante a guarda são persistidas normalmente, mas ficam sem sessão.

No POST original `/medicoes`, a API executa em uma transação SQLite:

1. Insere a medição com instante de ingestão UTC.
2. Procura uma sessão ativa para o mesmo dispositivo.
3. Associa somente `origem=real`, ID posterior ao marco inicial e instante posterior à guarda.
4. Registra elegibilidade/motivo de exclusão.
5. Encerra automaticamente a sessão quando atingir sua meta de registros elegíveis, exceto TOQUE_01.

O ACK conserva `id` e `instante` e acrescenta `sessao_id` somente quando houve associação. O firmware já imprime o corpo da resposta; nenhuma alteração de payload no ESP32 é necessária.

As associações ficam em `medicoes_sessoes`, sem acrescentar rótulos à tabela antiga `medicoes`. Chaves estrangeiras e triggers impedem vínculos fora da sessão ativa, associação retroativa, alteração/exclusão do vínculo e alteração/exclusão de medições já experimentais. Transições e observações de encerramento ficam em `auditoria_sessoes`. A sessão pode ser verificada por `/medicoes/{id}/sessao`, `/sessoes/{id}` e `/sessoes/{id}/medicoes`.

**O vínculo é por recepção/ingestão no servidor, não pelo instante exato de aquisição.** A origem física da condição ainda depende da execução e do registro honesto do operador. A guarda e os marcos impedem reutilizar o histórico, mas não comprovam sincronização física de um impacto com uma janela FFT.

### Elegibilidade, sem inventar dados

O par de modelos usa os mesmos registros: RMS, amplitude e frequência dominante presentes, finitos e não negativos; pico abaixo de 250 Hz; `atrasos=0` conhecido. Valores ausentes e janelas atrasadas não são preenchidos com médias nem zeros. Permanecem no SQLite e na sessão, com motivo de exclusão e contagem visíveis. A meta considera registros elegíveis, portanto o total recebido pode ser maior que a meta.

Não se excluem registros por apresentarem amplitude alta ou score anômalo. O critério de qualidade é anterior ao modelo. A exclusão de atrasos pode limitar a representatividade; apresentar também as contagens de excluídos.

## Treino, comparação e avaliação

O treino exige NORMAL_01 encerrada, com exatamente 100 registros elegíveis. RMS e amplitude inteiramente constantes bloqueiam o treino para revisão da aquisição. Não existe divisão aleatória das janelas em treino/teste, pois isso misturaria dados temporalmente relacionados.

São treinados dois pipelines na mesma baseline e no mesmo ato de comparação:

- `rms_amplitude`: RMS + amplitude de pico FFT.
- `rms_amplitude_frequencia`: RMS + amplitude + frequência dominante.

Cada pipeline contém `StandardScaler`, ajustado **somente** em NORMAL_01, seguido de Isolation Forest com `n_estimators=200`, `max_samples="auto"`, `contamination="auto"`, `random_state=42`, `n_jobs=1`. Não há busca de hiperparâmetros ou ajuste de limiar usando NORMAL_02, RETORNO_01 ou as condições alteradas.

`score_samples` menor indica observação mais incomum. `decision_function = score_samples - offset`; o critério fixo é **alerta quando decision_function < 0**. Os scores não são probabilidades de falha. `contamination="auto"` não impõe taxa de alerta de 1% ou 5%, nem garante poucos alertas normais. O limiar nativo é um ponto de partida explícito, não um limiar calibrado de engenharia. [Documentação oficial do Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).

O scaler é conservado no pipeline; sua presença explicita o tratamento das unidades, embora árvores de isolamento sejam pouco sensíveis à escala linear de uma feature. A frequência pode ajudar ou acrescentar instabilidade, especialmente com baixo sinal/ruído e picos dominantes variáveis. A comparação deve medir esse efeito, sem preferir automaticamente o modelo com três features.

NORMAL_02 e RETORNO_01 são pontuadas por modelos já congelados. BORRACHA_01 e MADEIRA_01 são **mudanças experimentais**, não falhas mecânicas. TOQUE_01 mistura intervalos sem perturbação e com eventos; sua taxa global não equivale à taxa durante os toques.

Para cada sessão encerrada com dados suficientes: `taxa_alertas = número de scores < 0 / número de registros elegíveis pontuados`. Mostrar numerador, denominador e excluídos. Em NORMAL_01 a taxa é apenas diagnóstico do ajuste, identificado como treino. Nas outras sessões é avaliação separada. Não agregar NORMAL_01 às validações.

As taxas normais são indicadores operacionais de alertas na condição declarada normal. As taxas alteradas medem resposta a mudanças conhecidas; não são sensibilidade para falhas específicas. Não calcular acurácia/F1 de diagnóstico ou chamar as condições alteradas de ground truth de defeito. Não converter ausência de dados em taxa zero: o campo fica `null` e o estado é `dados_insuficientes`.

Se NORMAL_02/RETORNO_01 forem usadas para escolher a variante, serão conjuntos de validação usados nessa escolha. Não apresentar o mesmo resultado como teste final cego. Uma conclusão de generalização requer outras campanhas independentes e uma avaliação final reservada. Janelas do mesmo ventilador/sessão não são réplicas físicas independentes; não calcular intervalos de confiança ingênuos assumindo independência. [Prevenção de vazamento de dados](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## Eventos: antes, durante e depois

Os endpoints registram início/fim pelo relógio UTC do servidor, em TOQUE_01 ativa. Não aceitam horários retroativos. Um evento por vez; encerrar o evento é obrigatório antes de encerrar a sessão. Descrever o tipo de perturbação e registrar observações, sem afirmar falha.

Análise por evento e por modelo, usando os instantes de recepção:

- **Antes:** até 60 s antes do início, excluindo a guarda de 5 s junto ao início.
- **Durante:** entre início +5 s e fim −5 s.
- **Depois:** de fim +5 s até fim +60 s.
- **Fronteira incerta:** até ±5 s dos limites; não entra nas três taxas.
- **Fora da janela:** demais pontos; não entram nas taxas daquele evento.

Janelas antes/depois são limitadas pelos eventos vizinhos, para não incluir outra perturbação como baseline. Cinco registros elegíveis por fase são necessários para exibir sua taxa. Os intervalos e guardas constam do relatório. A guarda é uma convenção operacional conservadora, **não uma garantia medida de atraso máximo**: aquisição não tem timestamp próprio e há latência humana/rede. As fases representam associação aproximada por recepção, sem causalidade comprovada.

Um toque de um segundo pode não ter nenhuma amostra no período “durante”; isso deve resultar em `n=0`, taxa `null` e insuficiência. Para testar resposta sustentada, é possível registrar um intervalo de cerca de 40–60 s com perturbações leves repetidas, apenas se seguro; esse intervalo é um envelope experimental, não uma falha contínua. Ainda registrar separadamente eventos curtos se forem o objeto de estudo, aceitando a limitação de observabilidade.

O relatório distingue suficiência por sessão e suficiência por fases dos eventos. Somente com ambas preenchidas aparece `avaliacao_descritiva_disponivel`. Mesmo assim, isso significa conclusão descritiva do protocolo, não validação de diagnóstico mecânico.

## Limites de aquisição para transientes

Cada FFT usa **256 amostras / 500 Hz = 0,512 s**, resolução nominal **1,953125 Hz**. O firmware processa diversas janelas localmente, com pausas entre elas, e envia aproximadamente uma medição a cada cinco segundos. O registro recebido representa uma janela, não RMS ou máximo de todo o intervalo de cinco segundos.

Como ordem de grandeza, uma janela de 0,512 s a cada 5 s representa cerca de 10% do tempo exportado; a cadência real varia. Transientes entre as janelas transmitidas podem desaparecer do dataset, mesmo se vistos em alguma FFT local não enviada. Remoção da média, Hann e posição do evento na janela também influenciam amplitude e pico. Eventos não estacionários podem distribuir energia em vários bins; um único pico dominante não descreve o espectro inteiro. Não há sinal bruto, espectro completo ou buffer pré/pós-evento persistido nesta versão.

Analisar transientes curtos com rigor exigirá futuramente timestamp de aquisição, retenção de mais janelas/sinal e talvez outra cadência. Isso não foi introduzido agora para preservar o firmware comprovado. Zero na contagem de atrasos não comprova ausência de jitter. O filtro de 184 Hz e as demais limitações de montagem/calibração do Marco 3 continuam válidos.

## Rastreabilidade e persistência

`modelos_ml` registra UUID do modelo e da comparação, sessão de treino, features, parâmetros/limiar, versões Python/NumPy/sklearn, hashes dos fontes e do dataset e hash do artefato. `ml_treino` conserva os 100 IDs usados por modelo e possui verificação SQL para aceitar somente NORMAL_01 elegível da mesma campanha. Os artefatos são gerados localmente no banco; não existe upload de modelos.

`ml_scores` conserva `(modelo_id, medicao_id)`, sessão, papel de treino/avaliação, scores bruto e de decisão, alerta e instante do cálculo. Chaves estrangeiras e trigger validam a correspondência modelo–campanha–sessão–medição. Scores são imutáveis e avaliações repetidas não duplicam linhas. Modelos com hash divergente ou versão sklearn diferente são recusados. Os artefatos pickle só devem ser carregados a partir do banco local confiável produzido pelo projeto; bancos/modelos de terceiros não são fontes de upload.

As tabelas experimentais são adicionadas sem reescrever as medições existentes. A inicialização faz backup consistente `.pre-experimentos-<UTC>.bak` quando estende um banco anterior, com transação, integridade referencial e repetibilidade da migração.

Consulta de rastreabilidade:

```sql
SELECT sc.modelo_id, md.variante, se.codigo, sc.medicao_id,
       m.instante, m.origem, m.rms, m.amplitude, m.pico_fft,
       sc.score_decisao, sc.alerta, sc.papel
FROM ml_scores sc
JOIN modelos_ml md ON md.id = sc.modelo_id
JOIN sessoes_experimentais se ON se.id = sc.sessao_id
JOIN medicoes m ON m.id = sc.medicao_id
ORDER BY m.instante, sc.modelo_id;
```

## Visualização e futura publicação

O cliente exporta relatório JSON e HTML Plotly local, com scores no tempo, distribuição por condição, taxas e fases dos eventos. O hover mantém IDs de medição, sessão e modelo. Treinamento é identificado nos gráficos. Um filtro de fase não reutiliza a taxa global como se fosse a taxa daquela fase.

`dashboard/app.py` é um visualizador Streamlit **somente leitura de JSON**, com filtros e rastreabilidade. Não acessa credenciais, API privada, banco ou modelos pickle. Pode servir futuramente de entrada para Streamlit Community Cloud com snapshots JSON autorizados; **não houve deploy, publicação ou configuração de hospedagem nesta etapa**. Não apontar um dashboard público para o SQLite do notebook ou expor a API doméstica. Planejar armazenamento/ingestão persistentes e HTTPS autenticado separadamente se esse escopo for ampliado.

Para instalar e executar localmente, consulte [roteiro_bancada_ml.md](roteiro_bancada_ml.md). O relatório de validação local diferencia testes com fixtures de evidência física coletada.
