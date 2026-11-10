# Roteiro de bancada — sessões e ML

Todos os comandos partem de `monitoramento_ventilador`, em PowerShell. Os rótulos são declarados pelo operador **antes** de cada coleta. Nenhum comando abaixo fabrica medições; os POSTs de medição continuam vindo do ESP32.

O ambiente ML validado usa Python **3.11**, com versões numéricas registradas no lockfile. A instalação básica do backend permanece separada.

## Preparar uma vez

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.lock.txt
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe scripts/iniciar_api_local.py
```

Se já houver API antiga em execução, encerre aquela instância e inicie novamente para carregar as rotas experimentais. Não iniciar dois servidores na mesma porta. Preservar `.env` e `secrets.h`; não é preciso regravar o ESP32. Não alterar firewall nem criar túnel para este protocolo.

Em outro terminal, confirme `/health` com `auth=True` e os POSTs físicos 201 do ESP32. Use o IP local já configurado privadamente, conforme o Marco 3. Não incluir credenciais/endereço da rede nos relatórios.

## Planejar e conferir

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py planejar --nome "Campanha ventilador 01"
.\.venv\Scripts\python.exe scripts/experimento.py status
```

`planejar` cria as seis sessões **planejadas e vazias**. Não executar novamente para a mesma campanha já preparada: cada execução cria outra campanha e atualiza a seleção local. O cliente conserva o UUID em `.marco3_local/experimento_atual.json`. Para selecionar outra campanha explicitamente, use `--experimento UUID` **antes** do subcomando.

## Coletar NORMAL_01 — treino

1. Restaurar a montagem original, ligar o ventilador em condição normal e aguardar estabilização. Manter orientação/fixação do MPU e alimentação. Registrar o ajuste e o apoio usados.
2. Iniciar somente quando a descrição abaixo corresponder à montagem observada; editar o texto se necessário:

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py iniciar NORMAL_01 --condicao "Ventilador em operacao normal; montagem original; descrever apoio, fixacao e alimentacao" --observacoes "Anotar estabilizacao e ajuste realmente utilizados"
.\.venv\Scripts\python.exe scripts/experimento.py acompanhar NORMAL_01
```

Há guarda inicial padrão de 10 s. A sessão encerra automaticamente ao atingir **100 registros elegíveis**, aproximadamente nove minutos com rede saudável, mais estabilização. Leia o progresso: exclusões podem aumentar o tempo. Não mudar a montagem enquanto a sessão estiver ativa. Após encerrar, novos envios ficam sem sessão até o próximo início.

## Coletar as sessões separadas

Para cada condição, esperar o encerramento da anterior, ajustar/estabilizar a montagem e executar o par de comandos correspondente. Os textos são orientações para descrição, não evidência de condição já executada.

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py iniciar NORMAL_02 --condicao "Nova sessao normal; mesma montagem original; registrar intervalo e estabilizacao"
.\.venv\Scripts\python.exe scripts/experimento.py acompanhar NORMAL_02

.\.venv\Scripts\python.exe scripts/experimento.py iniciar BORRACHA_01 --condicao "Base de apoio em borracha; descrever material, posicao e montagem realmente usados"
.\.venv\Scripts\python.exe scripts/experimento.py acompanhar BORRACHA_01

.\.venv\Scripts\python.exe scripts/experimento.py iniciar MADEIRA_01 --condicao "Superficie rigida em madeira; descrever contato e manter demais ajustes"
.\.venv\Scripts\python.exe scripts/experimento.py acompanhar MADEIRA_01
```

Cada uma encerra em 50 registros elegíveis, aproximadamente quatro a cinco minutos com rede saudável. NORMAL_02 deve ser uma coleta distinta, não uma divisão dos registros de NORMAL_01. BORRACHA e MADEIRA são mudanças experimentais, sem rótulo de defeito.

## TOQUE_01 — registrar eventos

Restaurar/descrever o apoio escolhido para esta sessão. Usar apenas perturbações leves na **base**, sem mãos próximas às pás ou partes energizadas e sem mexer no TACH.

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py iniciar TOQUE_01 --condicao "Descrever montagem; intervalos de perturbacoes leves na base serao registrados"
```

Aguardar a guarda inicial e pelo menos 60 s de baseline nesta sessão. Imediatamente antes da sequência de perturbações:

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py evento-iniciar --descricao "Sequencia de perturbacoes leves na base; descrever gesto e observacoes"
```

Se seguro, aplicar perturbações leves repetidas em um intervalo de aproximadamente 40–60 s. Ao terminar:

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py evento-encerrar
```

Aguardar pelo menos 60 s sem perturbação. Se fizer outro evento, deixar pelo menos 120 s entre eventos para separar bem as janelas antes/depois. Para eventos realmente curtos, registrar sua duração real; não prolongar o rótulo depois do fato para produzir mais pontos “durante”. É esperado que a análise possa indicar dados insuficientes nesses casos.

Conferir `status`; coletar pelo menos **50 elegíveis** no total e encerrar manualmente, com todos os eventos já encerrados:

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py status
.\.venv\Scripts\python.exe scripts/experimento.py encerrar TOQUE_01 --observacoes "Registrar a execucao real, ocorrencias e limitacoes"
```

O servidor registra os horários UTC. Não inferir que todo registro da sessão ocorreu durante um toque. A análise exige pelo menos cinco amostras em cada fase e exclui uma guarda de ±5 s das fronteiras.

## RETORNO_01

Restaurar a montagem original e estabilizar antes de iniciar:

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py iniciar RETORNO_01 --condicao "Montagem original restaurada; registrar apoio, fixacao e ajuste observados"
.\.venv\Scripts\python.exe scripts/experimento.py acompanhar RETORNO_01
```

Meta: 50 elegíveis. Não usar estes dados no ajuste do modelo.

## Treinar e avaliar

```powershell
.\.venv\Scripts\python.exe scripts/experimento.py treinar
.\.venv\Scripts\python.exe scripts/experimento.py avaliar --html relatorios/experimento.html
```

O treino sempre usa somente NORMAL_01 da campanha selecionada, para as duas variantes. Ele é recusado enquanto a baseline não estiver encerrada/completa. A avaliação informa insuficiência por sessão/fase; taxa ausente não equivale a zero.

O JSON padrão é `.marco3_local/relatorio_experimental.json`. O HTML é local e pode ser aberto no navegador; não publica nada. Para o painel local:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1
```

O painel lê o JSON exportado ou um JSON selecionado pelo usuário. Escolher TOQUE_01 e antes/durante/depois para inspecionar eventos. Não recebe arquivos de modelo/banco, não envia medições ao ESP32 e não treina automaticamente.

## Evidências e interrupções

Conservar o UUID da campanha, os modelos/versões, o JSON/HTML, IDs dos registros, horários dos eventos e fotos reais das montagens. O relatório já contém a rastreabilidade de cada score. Só concluir que houve resposta às mudanças com dados realmente coletados; não anunciar diagnóstico de falha específica.

Para interromper uma sessão, primeiro encerrar evento aberto e executar `encerrar CODIGO --observacoes "motivo real"`. O que foi recebido permanece no banco. Uma sessão encerrada incompleta não é reaberta nem completada com dados antigos: fica identificada como insuficiente; planejar outra campanha para repetir.

Tempo mínimo de registros do plano: cerca de 30 minutos com 350 elegíveis e envio nominal de 5 s, além de estabilizações, manuseio e exclusões. Reservar tempo maior para execução cuidadosa. Ensaios completos e sua interpretação física dependem do operador; não foram substituídos pelos testes automatizados.
