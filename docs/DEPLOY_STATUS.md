# Estado da publicação — 10/11/2026

## Atualização: sincronização hospedada

Auth e RPC foram validados no Supabase real, por HTTPS. O UUID autenticado corresponde ao usuário exclusivo e a escrita anônima foi negada. O operador confirmou por SQL os IDs reais 275–277: três linhas mesmo após reenvio, com payload integral, revisão e hash iguais ao SQLite. Após a conferência completa, o operador habilitou a origem para **leitura pública**, preservando as restrições de escrita.

A carga desta etapa contém **6.459 objetos únicos**: 5.384 medições reais, 355 vínculos, seis sessões, um evento, dois modelos, 710 scores e um status. A RPC confirmou 66 lotes e 6.460 aplicações de objetos, incluindo duas revisões do status. A fila terminou com **zero pendências e zero falhas**, com horário de sucesso registrado. Novas medições requerem novos ciclos do worker.

A consulta `.marco3_local/verificar_carga_supabase.sql` foi executada no Supabase pelo operador: sete linhas, todas com `quantidade_ok=true` e `ids_revisoes_hashes_ok=true`. Foram confirmados contagens, IDs, revisões e hashes do snapshot completo enviado. Depois da publicação da origem, o cliente anônimo leu os 6.459 objetos e **todos os payloads integrais foram comparados com a outbox, sem diferenças**. A evidência sem credenciais está em [supabase_real.json](evidencias_cloud/supabase_real.json). Não repetir migração, criação do usuário ou associação da origem. Credenciais locais estão configuradas e não são publicadas; o dashboard recebe somente os três campos de leitura.

O SQLite passou em `integrity_check`; todas as linhas existentes antes da carga foram comparadas por tabela e preservadas. A outbox foi copiada antes do envio. A API local estava parada e foi reiniciada em segundo plano: `/health` retornou HTTP 200, `banco=ok`, `auth=True`. Não houve alteração de firewall ou exposição pública da API. A suíte completa foi reexecutada: **129 testes aprovados**, com um aviso preexistente de depreciação; os testes do painel agora isolam variáveis de nuvem para não usar credenciais locais reais.

Os resultados anteriores abaixo documentam a preparação inicial; as pendências de configuração de Supabase/Auth foram resolvidas nesta atualização. Deploy do Streamlit e QR Code continuam pendentes. O pacote `.marco3_local/publicacao_streamlit/` foi atualizado e auditado: **76 arquivos versionados**, incluindo o manifesto, e commit local criado com a identidade Git já configurada. O remoto GitHub foi configurado e o push da branch `main` foi concluido, com igualdade do commit local e remoto. Os arquivos extras encontrados eram apenas caches Python ignorados pelo Git e foram preservados.

### Repositorio publicado no GitHub

O pacote auditado foi enviado para [uff-monitoramento-vibracoes-sem-adicionar-README-.gitignore-ou-licen-a.](https://github.com/Cacapepe2/uff-monitoramento-vibracoes-sem-adicionar-README-.gitignore-ou-licen-a.), branch `main`. O commit remoto foi comparado ao local e corresponde ao pacote auditado. O manifesto e 81 blobs do historico foram verificados sem valores de segredos conhecidos antes do primeiro push. Nenhum `.env`, secrets local, SQLite, outbox, backup ou pickle foi incluido.

Entrypoint para Streamlit Community Cloud: `dashboard/app_publico.py`. Dependencias: `dashboard/requirements.txt`; horario de Brasilia com `tzdata`. Os secrets de leitura estao prontos apenas no arquivo local ignorado `.streamlit/secrets.toml`. Login e criacao do app no Streamlit ainda dependem do operador; nao ha URL publica do dashboard ou QR Code confirmados.

### Dashboard e operação nesta etapa

Atualização de fluidez: o painel mantém um cache compartilhado protegido por lock e consulta alterações por `received_at`, com sobreposição de dois minutos e merge por identidade. A carga completa ocorre inicialmente e a cada cinco minutos para reconciliação; o fragmento visual continua atualizando aproximadamente a cada cinco segundos. Em uma comparação na rede real, a carga inicial retornou 6.690 objetos em 2,384 s; a consulta incremental retornou 25 objetos em 0,209 s, mantendo o histórico completo. São tempos observados nessa execução, sem garantia para outras redes. A carga inicial e a reconciliação completa ainda podem demorar mais.

A mensagem de sucesso repetitiva foi retirada e o aviso de validação do ML ficou na área de Machine Learning. Falhas de consulta, uso de cache e idade da medição continuam identificados. Os gráficos preservam o zoom por `uirevision`. Não houve alteração de modelos, scores, limiares ou registros originais. Os 31 testes de sincronização e dashboard passaram, incluindo atualização incremental, sobreposição, reenvio sem duplicação, reconciliação e preservação do cache após falha.

Gráficos, tabelas e horários de medição, consulta e sincronização são exibidos no fuso **America/Sao_Paulo (Brasília, UTC−3 nas datas desta campanha)**. A conversão ocorre somente na apresentação; SQLite, Supabase, replay e scores mantêm os timestamps UTC originais. A dependência `tzdata` está incluída para disponibilizar o fuso também no Windows.

O painel foi exercitado com leitura real do Supabase por Streamlit AppTest: seis áreas renderizadas sem exceções e três métricas exibidas na visão geral. Não se trata de inspeção visual em celular nem de deploy. Os 28 testes de sincronização e painel passaram após isolar também os secrets locais nos testes; a suíte completa tinha acabado de passar com 129 testes na etapa anterior. Modelos e scores foram preservados.

FastAPI e painel responderam HTTP 200 nos seus endpoints de saúde. O painel local está em **http://127.0.0.1:8501**, com configuração somente de leitura. O worker de sincronização foi iniciado em segundo plano para continuar enviando novas medições enquanto o notebook estiver ligado. Logs e estado operacional ficam na pasta privada `.marco3_local/`. A leitura do histórico não comprova que o ESP32 esteja ligado agora; conferir o horário da última medição no painel.

Para encerrar somente o worker e o painel iniciados nesta etapa, preservando a API e os dados:

```powershell
.\.venv\Scripts\python.exe .marco3_local/parar_cloud.py
```

O conector GitHub foi consultado novamente e não retornou repositórios acessíveis; o pacote local ainda não tem remoto. A próxima intervenção é criar um repositório vazio e informar seu endereço. Secrets do Streamlit ficarão no painel privado de configuração do serviço, nunca no Git. Ainda não há URL pública do Streamlit ou QR Code.

## Registro da preparação inicial

**Implementação local preparada; sincronização hospedada e deploy ainda pendentes.** O autor informou que criou o projeto `uff-monitoramento-vibracoes`, Healthy, executou a migração com retorno `Success. No rows returned` e confirmou **28 verificações OK** na consulta [001_verificar_migracao.sql](../supabase/checks/001_verificar_migracao.sql). Resultado dos catálogos hospedados confirmado pelo operador; ainda falta validar Auth/PostgREST e sincronização real. Usuário Auth e credenciais locais ainda não configurados. Não existe URL pública confirmada nem QR Code nesta entrega. Nenhum recurso pago, túnel ou regra de firewall foi criado.

## Implementado

- FastAPI e firmware preservados. SQLite continua fonte primária, independente da internet.
- Worker HTTPS independente com outbox SQLite em `.marco3_local/cloud_queue.db`, identidade persistente por origem, hash por objeto e ACK por revisão.
- Sincronização incremental por conteúdo, lotes de 100, timeout, lease, reenvio com backoff e aplicação idempotente. Nenhuma chamada remota ocorre no POST da FastAPI.
- Migração Supabase transacional/idempotente, RLS, origem inicialmente privada, usuário Auth exclusivo para escrita via RPC e leitura pública apenas da projeção autorizada.
- Contrato público por allowlist: medições reais, sessões, vínculos, eventos sem texto livre, metadados dos modelos sem pickle e scores históricos.
- Novo painel `dashboard/app_publico.py`, com título/subtítulo e paleta solicitados, seis áreas, gráficos interativos, atualização por fragmento a cada cinco segundos e estilos para telas estreitas. Painel anterior preservado.
- Visão geral, histórico, comparação de sessões, educação, scores experimentais, limitações, idade da medição e status da sincronização.
- Aviso obrigatório de ML, sem classificação de defeito mecânico. Modelos, limiares e relatório diagnóstico anteriores preservados.
- Replay explícito com **355 medições físicas e 710 scores** da campanha já coletada, conservando horários e IDs. Nenhum dado sintético foi convertido em evidência real.
- Exportador de replay sem sobrescrita, pacote de publicação por allowlist, configuração/segredos de exemplo, workflow CI e gerador de QR condicionado à URL verdadeira.

## Sincronização nesta execução

Foi executado `scripts/sincronizar_supabase.py --local-only`: a fila foi preparada sem conexão externa. Na primeira varredura: **2.291 objetos pendentes**, zero ACKs remotos e `last_success_at=null`. A contagem inclui a projeção do histórico real do dispositivo, seus vínculos/metadados e um status; pode aumentar se o ESP32 continuar transmitindo. Zero falhas nessa preparação não significa sincronização bem-sucedida: nenhuma tentativa remota foi feita.

Na preparação inicial, não foram encontradas variáveis locais de Supabase ou senha do worker. A migração e RLS foram testadas em PostgreSQL WASM local. Posteriormente o autor informou a aplicação no projeto hospedado; nenhum acesso remoto foi executado pelo agente. Resultado da sincronização remota: **pendente, não comprovado**.

## Acessos e publicação

| Item | Resultado observado |
|---|---|
| Git local | Executável disponível; diretório original sem `.git`/remoto |
| Conector GitHub | Perfil autenticado; consulta de repositórios retornou lista vazia |
| Supabase | Projeto Healthy e 28 verificações dos catálogos OK, confirmados pelo operador; Auth, configuração local e sincronização real pendentes |
| Streamlit Community Cloud | Sem repositório/destino de publicação configurado; deploy não executado |
| Navegador | Tentativa de verificação encerrada pela ferramenta por não conseguir confirmar a URL atual com segurança; sem contornar a restrição |
| URL pública | **Não disponível** |
| QR Code | **Não gerado**, pois não há URL publicada e verificada |

## Testes e verificações

Os resultados finais desta execução estão em [evidência de validação](evidencias_cloud/validacao.json). A suíte anterior de 101 testes foi mantida; novos testes cobrem fila, reenvio, lease, ACK antigo, retomada, incremento por nova medição, falha remota sem interromper ingestão, projeção pública, rejeição de chaves privilegiadas/destinos inseguros, replay, páginas, estados de conexão e atualização da apresentação.

**Resultado: 129 testes aprovados**, com um aviso preexistente de depreciação do TestClient. O teste adicional de leitura remota usa respostas simuladas isoladas; nenhuma fixture foi enviada ao Supabase nem tratada como medição física.

RLS/SQL: teste executável `supabase/tests/rls.test.mjs` em **PGlite 0.5.16 (PostgreSQL local)**, com `auth.uid()` simulado por claim de teste. Verifica negação de escrita anônima, isolamento por escritor, origem privada/publicada, ausência de escrita direta, duplicidade, revisão antiga, colisão, allowlist e reaplicação da migração. Isso não substitui validar Supabase Auth/PostgREST no projeto real.

As páginas foram exercitadas por Streamlit AppTest. Há CSS responsivo; inspeção visual em navegador/celular e teste da URL pública permanecem pendentes devido à indisponibilidade de controle seguro do navegador. Não foram fabricados screenshots. O painel foi iniciado em **http://127.0.0.1:8501**, limitado ao loopback, e respondeu HTTP 200 em `/_stcore/health`; isso não comprova deploy. A FastAPI respondeu `status=ok`, `banco=ok`, `auth=True`.

A varredura de valores conhecidos encontrou credenciais somente em `firmware_fisico/secrets.h` e `wokwi/sketch_pronto.ino`, já ignorados e excluídos do pacote público. Seus conteúdos foram preservados e não foram impressos. A allowlist de publicação passou na verificação de segredos conhecidos; isso não substitui revisão de segredos desconhecidos antes do push.

## Pendências registradas na preparação inicial

Pacote de publicação preparado em **`.marco3_local/publicacao_streamlit/`**, com allowlist e manifesto de hashes. Use essa pasta para criar o repositório; não faça `git add .` na raiz do workspace com arquivos privados. A outbox e os backups ficam fora do pacote.

O Git desse pacote já foi inicializado na branch `main`, com **72 arquivos preparados no índice**, sem commit, remoto ou push. Nenhuma identidade Git foi inventada. `pip check` não encontrou dependências quebradas. O painel do pacote foi testado em um processo Python isolado, sem acesso aos arquivos privados do workspace.

1. Migração e 28 verificações confirmadas pelo operador. Próxima etapa: criar usuário Auth exclusivo e confirmar seu UUID; só depois associá-lo ao source_id da outbox e preencher o `.env` local. Não repetir a migração nem enviar senhas ou chaves pelo chat.
2. Conferir a projeção e publicar a origem no Supabase; iniciar o worker e verificar ACK, IDs e leitura do painel. Testar desconexão e retomada em ambiente hospedado.
3. Criar/autorizar um repositório GitHub e enviar **somente o pacote auditado**, não a pasta inteira do workspace.
4. Entrar no Streamlit Community Cloud, escolher o entrypoint e configurar somente secrets de leitura. Publicar, testar sem login e em celular.
5. Usar a URL verdadeira para o QR Code. Nenhuma dessas ações foi registrada como concluída.

## Comandos de operação

Todos a partir de `monitoramento_ventilador`, no PowerShell:

```powershell
# Aquisição local, caso a API ainda não esteja ativa:
.\.venv\Scripts\python.exe scripts/iniciar_api_local.py

# Outro terminal: preparar fila sem enviar, ou consultar estado:
.\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --local-only
.\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --status

# Somente após configurar o Supabase no .env:
.\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --loop

# Painel local, independente de deploy:
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard/app_publico.py --server.address 127.0.0.1

# Validação e pacote seguro para publicação:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/preparar_publicacao.py --check
.\.venv\Scripts\python.exe scripts/preparar_publicacao.py --saida <pasta-nova>
```

Detalhes de SQL, permissões, secrets, publicação e QR: [guia de nuvem](guia_nuvem.md). O pacote preparado não contém banco original, outbox, credenciais, backups, firmware local ou pickle. O processo de aquisição existente pode continuar ativo; não iniciar duas APIs na porta 8000.


### Validacao da atualizacao incremental

A suite completa apos esta alteracao passou com **132 testes aprovados**, com um aviso preexistente de depreciacao. A visao geral foi exercitada com leitura real do Supabase, tres metricas e ausencia dos dois avisos removidos. A limitacao de generalizacao permanece explicada na area de Machine Learning. A API, o worker, o firmware, os registros e os modelos foram preservados.
