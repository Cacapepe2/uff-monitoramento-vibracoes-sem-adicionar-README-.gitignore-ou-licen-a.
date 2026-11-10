# Publicação educacional e sincronização

## Separação entre aquisição e publicação

```text
ESP32 → HTTP autenticado na LAN → FastAPI → SQLite original
                                             ↓ leitura somente
                                  worker e outbox local separada
                                             ↓ HTTPS de saída
                                     Supabase → Streamlit
```

A FastAPI não chama Supabase e o firmware não muda. Internet indisponível interrompe somente a cópia para consulta. O worker é um processo independente. Não abrir porta do notebook no roteador, criar túnel ou expor a API local.

`cloud_sync/public_data.py` define a projeção pública. Inclui apenas medições reais do dispositivo `esp32-fisico-01`, sessões, associações, intervalos de eventos, metadados mínimos dos modelos e scores históricos. Exclui textos livres, credenciais, caminhos locais, logs, identificadores de usuário Auth e binários pickle. Medições antigas sem sessão permanecem sem sessão. Dados sintéticos não entram nessa projeção. O painel não treina, recalibra ou executa modelos.

## Configurar Supabase — intervenção manual necessária

Não há credenciais de projeto configuradas nesta entrega. Use um projeto existente ou crie um projeto no plano gratuito pela sua conta, conferindo o plano antes de confirmar. Nenhum recurso pago foi solicitado ou criado automaticamente.

1. No SQL Editor do projeto, executar [001_vibration.sql](../supabase/migrations/001_vibration.sql). É uma migração transacional e idempotente com prefixo `vibration_`; não altera tabelas de terceiros.
2. Em Authentication, criar um usuário exclusivo para o sincronizador, com senha forte e acesso de e-mail devidamente confirmado. Não reutilizar a senha da sua conta pessoal. Guardar e-mail/senha somente no `.env` local ignorado; não os incluir nos secrets do Streamlit.
3. Preparar a outbox e obter a identidade persistente:

   ```powershell
   .\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --local-only
   .\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --status
   ```

   Copiar o `source_id` retornado. **Preservar `.marco3_local/cloud_queue.db` e seus backups.** Não apagar a fila para reiniciar o worker, não copiar só parte dela e não usar duas outboxes independentes para a mesma origem. Uma cópia independente do banco de aquisição deve receber outra origem. A chave remota é `(source_id, kind, entity_id)`.
4. Associar o UUID desse usuário Auth à origem, como administrador no SQL Editor, substituindo ambos os valores ilustrativos:

   ```sql
   INSERT INTO public.vibration_sources(id, writer_uid, label, published)
   VALUES ('<SOURCE_ID>', '<UUID-USUARIO-AUTH>', 'Bancada acadêmica', false);
   ```

   A origem começa privada. Somente após conferir o contrato e querer publicar essa telemetria:

   ```sql
   UPDATE public.vibration_sources SET published=true WHERE id='<SOURCE_ID>';
   ```

   Para suspender leitura pública, definir `published=false`. Isso não apaga os registros.
5. Acrescentar ao `.env` existente as variáveis de [.env.cloud.example](../.env.cloud.example), preservando `API_KEY`, `DB_PATH` e demais valores locais. Utilizar a URL HTTPS oficial do projeto e a chave **publishable**, ou a chave legada anon. Nunca usar `service_role`, chave secret ou JWT administrativo. O cliente rejeita chaves privilegiadas e destinos fora do domínio oficial do Supabase.
6. Testar um ciclo e depois manter o worker rodando:

   ```powershell
   .\.venv\Scripts\python.exe scripts/sincronizar_supabase.py
   .\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --loop
   ```

   Um ciclo transmite no máximo 100 objetos; na primeira carga haverá vários ciclos. A quantidade pendente deve cair, e `last_success_at` só deve aparecer após confirmação remota. Se não houver configuração completa, o comando informa modo local e **não transmite**. Encerrar o worker com Ctrl+C preserva fila e aquisição.
7. Conferir no Table Editor os IDs, a origem e os scores; abrir o painel com configuração de leitura e comparar alguns IDs com `scripts/consultar_dados.py`. Não usar um POST fabricado como evidência de nova medição física.

### Segurança e consistência

As tabelas têm RLS. `anon` e `authenticated` podem apenas ler objetos de origens explicitamente publicadas. Não podem inserir, atualizar ou apagar diretamente. A função `vibration_sync_batch` tem execução somente para `authenticated`, verifica `auth.uid()` contra o usuário exclusivo da origem e valida uma allowlist de campos. A tabela com o vínculo do escritor não é legível por esses papéis. O painel usa somente a chave de leitura publishable/anon; a senha de escrita permanece no notebook.

A função é `security definer` com `search_path=''` e referências qualificadas. Essa elevação é limitada ao lote autenticado da origem autorizada; não oferece SQL arbitrário, alteração de permissões ou leitura de segredos. As políticas, restrições de acesso e migração foram exercitadas em PostgreSQL WASM local; ainda precisam ser confirmadas no projeto Supabase real, incluindo o comportamento de Auth/PostgREST.

O worker compara hashes dos objetos da projeção em um snapshot consistente do SQLite. A descoberta faz uma varredura do conjunto publicado a cada ciclo; **o tráfego é incremental**: objetos sem mudança não são reenviados. Isso evita perder encerramentos de sessões existentes e associações que não poderiam ser capturadas por um cursor baseado só no maior ID de medição. Para bases muito grandes, medir o custo dessa varredura antes de ampliar a coleta.

A outbox mantém revisão por entidade, hash, revisão confirmada, contagem de tentativas, próximo reenvio e lease de 120 s. Reenvios têm backoff de 5 s a 300 s. O ACK só confirma a revisão enviada; mudança posterior permanece pendente. No servidor, duplicatas não criam linhas, revisões antigas não revertem novas e colisão de revisão/hash é recusada. Se a resposta se perder depois do commit remoto, reenviar o mesmo lote é seguro. Não há promessa de entrega exatamente uma vez; há entrega com reenvio e aplicação idempotente.

Cada lote remoto é atômico. Entre lotes pode haver metadados ou vínculos ainda em trânsito; o painel tolera registros sem associação e não inventa condições. Um objeto inválido pode impedir o ACK do lote inteiro; corrigir a configuração/contrato, preservando a fila, em vez de apagar registros. O worker omite corpos de erro e segredos. Monitorar pendências persistentes, credenciais e permissões. Há timeouts de conexão/leitura; a duração total depende do lote e da rede.

O status publicado descreve o estado local na hora da verificação e pode ficar desatualizado se o worker parar ou a rede cair. `received_at` é o horário de aplicação remota; `instante` preserva a recepção original na FastAPI. O painel distingue sucesso da consulta à nuvem, idade da última medição e estado do sincronizador. Não confundir esses três sinais.

## Executar o painel e o replay

```powershell
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard/app_publico.py --server.address 127.0.0.1
```

Sem secrets, o painel abre em **Replay · histórico real**, com aviso persistente. O arquivo versionável `dashboard/data/replay.json` contém 355 medições reais associadas às seis sessões e 710 scores preservados. Não contém fixtures, observações livres ou modelos binários. Os horários são originais. Por padrão mostra todo o histórico; ativar “Reproduzir a cada 5 segundos” para apresentar um prefixo crescente. Ao final mantém o último estado, sem inventar novas medições. “Reiniciar replay” reinicia apenas a visualização.

O painel anterior, `dashboard/app.py`, foi mantido para análise local dos relatórios JSON.

Para outra campanha, exportar para um arquivo novo e revisar antes de trocar o bundle da apresentação:

```powershell
.\.venv\Scripts\python.exe scripts/exportar_replay.py --saida <novo-arquivo.json>
```

O exportador recusa sobrescrever arquivos existentes. O replay não é fallback silencioso da nuvem: o modo está identificado e é escolhido pelo usuário. Se uma consulta à nuvem falhar, o painel sinaliza o erro; pode mostrar o último resultado daquela conexão em cache, explicitamente identificado. Não consulta a API privada do notebook.

Para leitura Supabase local, copiar `.streamlit/secrets.example.toml` para o arquivo **ignorado** `.streamlit/secrets.toml` e preencher URL, publishable key e source_id. Somente essas três variáveis devem ir ao Streamlit Community Cloud. O leitor é paginado, com limite explícito de 20 mil objetos; ao atingir o limite informa erro em vez de apresentar uma consulta truncada como completa. Cache compartilhado de cinco segundos reduz consultas repetidas entre visitantes da mesma instância. Monitorar cotas de armazenamento/egress no plano gratuito; não ativar upgrade automático.

## Preparar GitHub e Streamlit Community Cloud

O diretório original não tinha `.git` nem remoto. O conector GitHub está autenticado, mas não retornou repositórios acessíveis. Não há destino autorizado configurado para push. A verificação adicional por navegador foi interrompida pela ferramenta por não conseguir confirmar a URL atual; não foi contornada.

1. Gerar o pacote permitido, sem incluir o workspace inteiro:

   ```powershell
   .\.venv\Scripts\python.exe scripts/preparar_publicacao.py --check
   .\.venv\Scripts\python.exe scripts/preparar_publicacao.py --saida <pasta-nova-do-repositorio>
   ```

   O pacote usa allowlist, bloqueia valores de segredos conhecidos e exclui `.env`, `secrets.h`, bancos, outbox, backups e pickle. Não equivale a uma auditoria universal de qualquer segredo desconhecido: revisar os arquivos e o manifesto antes do push. Firmware e logs privados não fazem parte do pacote público. Os relatórios históricos completos e seus anexos permanecem no workspace; o pacote contém somente os documentos de publicação e as evidências selecionadas.
2. Criar um repositório GitHub vazio na sua conta, conferir sua visibilidade e autenticar o Git local. Na pasta preparada:

   ```powershell
   git init -b main
   git add .
   git status --short
   git commit -m "Publica painel educacional e sincronizacao segura"
   git remote add origin <URL-REAL-DO-SEU-REPOSITORIO>
   git push -u origin main
   ```

   Se o Git pedir identidade, configurar seu nome/e-mail na sua máquina; não há identidade inventada no pacote. Nunca incluir tokens na URL do remoto.
3. Entrar no Streamlit Community Cloud pela sua conta e autorizar acesso somente ao repositório pretendido. Escolher branch `main`, entrypoint **`dashboard/app_publico.py`** e Python **3.11**. `dashboard/requirements.txt`, ao lado do entrypoint, contém as dependências leves e versões validadas do painel; não é necessário carregar sklearn ou executar o backend na hospedagem.
4. O replay funciona sem secrets. Para leitura ao vivo, preencher os três valores em Advanced settings → Secrets. **Não colocar senha Auth do worker, API_KEY da FastAPI ou service_role nesse ambiente.** Não versionar `.streamlit/secrets.toml`.
5. Publicar e testar a URL verdadeira: abrir sem login, conferir título/aviso, alternar páginas, testar celular, conferir IDs contra a cópia remota, interromper somente o worker para observar dados ficando antigos e retomar para verificar drenagem da fila. A leitura e o dashboard devem continuar independentes da exposição da API local.

Referências oficiais: [deploy Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app), [secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [dependências](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies), [chaves Supabase](https://supabase.com/docs/guides/getting-started/api-keys) e [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## QR Code somente depois da publicação

Nenhuma URL foi inventada e nenhum QR foi gerado sem publicação real. Após verificar o conteúdo público no navegador:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cloud.txt
.\.venv\Scripts\python.exe scripts/gerar_qrcode.py https://<SEU-APP-REAL>.streamlit.app
```

O script exige HTTPS e domínio Streamlit, rejeita credenciais/parâmetros e só gera o QR após HTTP 200 na URL fornecida. Essa verificação HTTP não substitui conferir o conteúdo, as permissões e os dados no navegador. Saída padrão: `relatorios/qrcode_dashboard.png`.
