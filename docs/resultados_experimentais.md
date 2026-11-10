# Resultado experimental fisico ? 10/11/2026

Foram coletados **355 registros reais elegiveis**, distribuidos em seis sessoes, com confirmacao das condicoes pelo operador. Nenhum registro historico de condicao desconhecida foi rotulado. Nao houve exclusoes por qualidade nestas coletas; todos os registros associados possuem atrasos=0.

**A integracao e a rastreabilidade funcionaram, mas a discriminacao normal/alterado nao foi validada com sucesso nesta campanha.** Ambos os modelos alertaram em todos os registros das sessoes normais de validacao. Portanto, alertas nas condicoes alteradas nao demonstram, sozinhos, deteccao seletiva das perturbacoes ou diagnostico mecanico.

## Coletas e taxas observadas

Taxa = quantidade de registros com score de decisao < 0 dividida pelo numero de registros da sessao. Sao proporcoes descritivas por registro, com dependencia temporal; nao representam desempenho populacional ou repeticoes independentes.

| Sessao | Registros | IDs | RMS + amplitude | RMS + amplitude + frequencia |
|---|---:|---|---:|---:|
| NORMAL_01 | 100 | 275?374 | 26/100 (26%) | 26/100 (26%) |
| NORMAL_02 | 50 | 413?462 | 50/50 (100%) | 50/50 (100%) |
| BORRACHA_01 | 50 | 494?543 | 50/50 (100%) | 50/50 (100%) |
| MADEIRA_01 | 50 | 576?625 | 50/50 (100%) | 50/50 (100%) |
| TOQUE_01 | 55 | 661?715 | 55/55 (100%) | 55/55 (100%) |
| RETORNO_01 | 50 | 757?806 | 50/50 (100%) | 50/50 (100%) |

NORMAL_01 e treinamento; sua taxa de 26% e uma observacao no proprio treino, nao validacao. NORMAL_02 e RETORNO_01 totalizam 100 alertas em 100 registros de condicoes declaradas normais: taxa observada de alertas indevidos de 100% neste conjunto. Nao ha evidencia de vantagem da frequencia dominante nas taxas desta campanha; isso nao demonstra equivalencia geral entre as variantes.

## Diferencas observadas entre sessoes

| Sessao | Mediana RMS (m/s?) | Mediana amplitude (m/s?) | Mediana pico dominante (Hz) |
|---|---:|---:|---:|
| NORMAL_01 | 0.673682 | 0.909501 | 44.921875 |
| NORMAL_02 | 0.596593 | 0.814619 | 44.921875 |
| BORRACHA_01 | 0.369737 | 0.423929 | 181.640625 |
| MADEIRA_01 | 0.359699 | 0.459574 | 44.921875 |
| TOQUE_01 | 0.815692 | 0.989861 | 44.921875 |
| RETORNO_01 | 0.477989 | 0.531659 | 42.968750 |

A variacao tambem aparece nas sessoes declaradas normais. Ela sugere que a referencia unica de treinamento nao representa suficientemente as condicoes normais observadas nesta campanha. A causa nao foi determinada: estabilizacao, reproducibilidade do apoio, fixacao, alimentacao e variacao operacional sao hipoteses para novos ensaios, nao conclusoes. Nao interpretar o pico dominante como RPM ou falha mecanica.

## TOQUE_01 e limites temporais

Um unico intervalo de toques leves foi confirmado pelo operador. Com janela de 60 s antes/depois e exclusao de 5 s em torno dos marcadores, ambos os modelos alertaram em **10/10 antes, 12/12 durante e 11/11 depois**. Quatro registros ficaram nas fronteiras incertas e 18 fora dessas janelas. Assim, nao houve contraste nas taxas que permita atribuir os alertas especificamente aos toques.

Os marcadores no servidor foram registrados apos confirmacao de inicio e no aviso para parar; a confirmacao posterior de fim foi preservada separadamente. A latencia humana e do chat nao foi medida, e a guarda de 5 s nao garante conter essa incerteza. As fases sao aproximadas por recepcao. Nao e possivel atribuir cada janela a um contato exato. Ha 256 amostras a 500 Hz (0,512 s) por janela enviada aproximadamente a cada 5 s; toques individuais podem ocorrer entre as janelas transmitidas.

## Treinamento e verificacao

Duas variantes de StandardScaler + Isolation Forest, 200 arvores, random_state=42, max_samples=auto, contamination=auto e limiar score_decisao < 0 (offset=-0,5). Scaler e modelos foram ajustados **somente aos mesmos 100 IDs de NORMAL_01**. Nenhum limiar ou parametro foi ajustado apos observar a validacao. Contamination=auto nao fixa a taxa de alertas em uma porcentagem escolhida.

Foram verificados no SQLite os 200 vinculos de treinamento, hashes dos dois artefatos e os **710 scores** (355 por modelo), com sessao e ID original correspondentes ao relatorio. Os 140 registros presentes antes desta implementacao permaneceram identicos, assim como firmware, credenciais e arquivos Wokwi protegidos. integrity_check=ok e foreign_key_check sem violacoes. Backup consistente apos coleta/modelos foi criado na pasta privada ignorada .marco3_local.

Houve erro de thread SQLite no inicio de NORMAL_02, corrigido com conexao por requisicao permitindo troca de thread no FastAPI. A API foi reiniciada preservando a sessao; maior intervalo de recepcao nessa sessao foi 15,770 s. Nao foram fabricadas janelas perdidas. A ocorrencia esta na evidencia individual. A suite passou com **93 testes** apos a correcao, incluindo regressao de troca de thread e insercoes concorrentes em banco temporario; um aviso de deprecacao do TestClient permanece.

## Evidencias e proximos ensaios

- [Relatorio estruturado com modelos, scores e IDs](evidencias_ml/avaliacao_fisica.json).
- [Graficos interativos locais de scores, condicoes e taxas](../relatorios/experimento_fisico.html): arquivo local gerado, sem deploy.
- Cada arquivo coleta_*.json em docs/evidencias_ml preserva a sessao, auditoria, registros e verificacoes.
- Dashboard local recebeu copia deste relatorio no caminho padrao .marco3_local/relatorio_experimental.json; a copia inicial foi preservada.

Esta e uma primeira campanha, com uma sessao por condicao, ordem fixa, materiais de apoio sem tipo/espessura informados, intensidade dos toques nao instrumentada e sem calibracao externa. Retorno foi feito na montagem original ja restaurada antes de TOQUE_01, apos novo desligamento/religamento; nao houve nova troca de apoio entre essas duas sessoes.

Proximo passo: repetir sessoes normais independentes e acompanhar a estabilizacao por mais tempo, registrando apoio, fixacao e condicoes operacionais. Se o protocolo de treinamento ou limiar for revisto, criar nova campanha/versionamento e reservar novas sessoes de validacao intocadas. Preservar esta avaliacao como resultado do protocolo atual; nao reclassificar os registros para melhorar metricas. Ainda nao ha evidencia suficiente para concluir generalizacao, confiabilidade do alerta ou diagnostico de falhas especificas.
