# Monitoramento de Vibração de Ventilador (ESP32 + FFT + FastAPI + SQLite)

Protótipo acadêmico com dois caminhos preservados: **Wokwi (`origem=simulacao`)** e **ESP32 físico (`origem=real`)**. Os cenários do Wokwi são sintéticos e não comprovam falhas reais. **A integração física até o SQLite foi confirmada em 03/11/2026**, com HTTP 201 observado no Serial e os mesmos IDs conferidos na API e no banco. Veja as [evidências capturadas](docs/evidencias_marco3/README.md).

## Protocolo experimental e Machine Learning

As sessões NORMAL_01, NORMAL_02, BORRACHA_01, MADEIRA_01, TOQUE_01 e RETORNO_01 têm planejamento e coleta prospectiva, com associação transacional no servidor. O firmware permanece igual. **Medições antigas de condição desconhecida não são rotuladas nem usadas no treino. Planejamento não significa coleta concluída.**

Isolation Forest compara RMS + amplitude versus RMS + amplitude + frequência dominante. O treino exige 100 registros elegíveis de NORMAL_01 encerrada; NORMAL_02 e RETORNO_01 ficam fora do ajuste. Há scores rastreáveis por modelo/sessão/ID, taxas descritivas com estado de insuficiência, análise de eventos e gráficos locais. Nenhuma condição é automaticamente chamada de falha mecânica.

Instalação adicional e início, na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.lock.txt
.\.venv\Scripts\python.exe scripts/iniciar_api_local.py
# Em outro terminal, se ainda não existir planejamento para a campanha:
.\.venv\Scripts\python.exe scripts/experimento.py planejar --nome "Campanha ventilador 01"
.\.venv\Scripts\python.exe scripts/experimento.py status
```

Não iniciar sessão antes de confirmar fisicamente sua condição. Cada `planejar` cria uma nova campanha. Para a campanha já preparada no workspace, execute apenas `status` e siga o [roteiro simples de bancada](docs/roteiro_bancada_ml.md). Regras de qualidade, mínimos, eventos e limites de inferência estão no [protocolo experimental](docs/protocolo_experimental.md).

Os modelos e scores ficam em novas tabelas SQLite, sem reescrever a tabela de medições. `scripts/experimento.py avaliar --html relatorios/experimento.html` exporta JSON e gráficos; se faltar coleta, mostra **dados insuficientes**, sem scores fictícios. `dashboard/app.py` visualiza somente relatórios JSON em Streamlit local; a estrutura permite evolução para publicação futura, **sem deploy nesta etapa**. As dependências do dashboard ficam em `dashboard/requirements.txt`.

Validação desta etapa: **91 testes aprovados**, banco íntegro e planejamento criado, com as seis sessões ainda vazias. Nenhum modelo real foi treinado com o histórico desconhecido. Ver [validacao_experimental.md](docs/validacao_experimental.md).

## Marco 3 — começar pelo hardware físico

Roteiro completo, resultados e critérios de evidência: [docs/marco3.md](docs/marco3.md).

**Estado desta bancada:** firmware gravado e transmitindo, API local autenticada ativa em segundo plano, oito registros antigos preservados e TACH desabilitado. Os IDs 14–20 e 33–35 têm correlação Serial 201 → API 200 → SQLite documentada. O estado ligado/desligado do ventilador não foi rotulado nesta captura. Nenhuma regra de firewall foi alterada e nenhum túnel foi criado. Os passos abaixo permitem repetir a configuração; ela já foi executada nesta sessão.

1. No PowerShell, entre nesta pasta (`monitoramento_ventilador`). Use o ambiente Python existente ou a instalação abaixo. Confira a chave em `.env` **sem publicá-la**. Não sobrescreva o `.env` existente.
2. Execute `ipconfig` e anote o **IPv4 do adaptador Wi-Fi** do notebook. ESP32 e notebook devem estar na mesma rede, sem isolamento de clientes. O ESP32 DevKit usa Wi-Fi 2,4 GHz.
3. Inicie a API com autenticação obrigatória para a bancada:

   ```powershell
   .\.venv\Scripts\python.exe scripts/iniciar_api_local.py
   ```

   Esse iniciador ouve em `0.0.0.0:8000` e recusa chave vazia/exemplo. Equivalente direto, após configurar `API_KEY`: `python -m uvicorn backend.main:create_app --factory --host 0.0.0.0 --port 8000`.
4. Em outro terminal: `Invoke-RestMethod http://127.0.0.1:8000/health`. Espere `status=ok`, `banco=ok` e **`auth=True`**. A migração é automática na inicialização, com backup `.bak` antes de alterar um banco antigo. Os oito registros simulados encontrados inicialmente devem ser preservados.
5. Copie `firmware_fisico/secrets.example.h` para **`firmware_fisico/secrets.h`**, ignorado pelo Git. Edite SSID, senha, chave igual à do servidor e URL `http://<IPv4-Wi-Fi-do-notebook>:8000/medicoes`. `<IPv4-Wi-Fi-local>` no exemplo é ilustrativo; `localhost` e `0.0.0.0` não são destinos para o ESP32. O sketch desta bancada exige IPv4 privado literal na URL.
6. Abra **`firmware_fisico/firmware_fisico.ino`** no Arduino IDE. As abas `processamento.h`, `tacometro.h` e `secrets.h` ficam na mesma pasta. Selecione **ESP32 Dev Module**, **COM8**, core **esp32 3.3.12** e biblioteca **arduinoFFT 2.0.4**, encontrados neste computador. `Wire`, `WiFi` e `HTTPClient` já fazem parte do core; este sketch lê os registradores do MPU diretamente.
7. Compile e carregue. Abra o Serial Monitor em **115200 baud**. Observe `[MPU] detectado 0x68`, `[FFT] REAL`, `[WiFi] conectado` e `[HTTP] POST -> 201 {"id":...}` a cada aproximadamente 5 s com rede saudável. O TACH continua desconectado e desabilitado; a FFT funciona sem RPM.
8. Confirme o mesmo ID no notebook:

   ```powershell
   .\.venv\Scripts\python.exe scripts/consultar_api.py -d esp32-fisico-01
   .\.venv\Scripts\python.exe scripts/consultar_dados.py -d esp32-fisico-01 -n 10
   .\.venv\Scripts\python.exe scripts/print_banco.py -d esp32-fisico-01 -n 10
   ```

Os novos campos são `rms` (m/s², após remover a média e antes da Hann) e `atrasos` (contagem por janela). Sem tacômetro: `rpm=null`, `frequencia_1x=null`; sem cenário sintético: `cenario=null`. Dados antigos retornam `rms=null` e `atrasos=null`. Clientes de simulação continuam obrigados a informar RPM, frequência de rotação e cenário.

**Nesta etapa use HTTP local, sem Cloudflare Tunnel.** A chave trafega sem criptografia: limite a demonstração à rede doméstica confiável. Fora da rede local é necessário HTTPS com validação de certificado. O novo sketch implementa apenas a bancada HTTP local.

Se houver bloqueio, consulte o procedimento de firewall em [docs/marco3.md](docs/marco3.md#firewall-e-diagnóstico). Não desligue o firewall, não abra portas no roteador e não exponha a API à internet. Os arquivos Wokwi antigos contêm uma chave de bancada: trate-a como exposta e substitua-a antes de reutilizá-la; não a mostre nas evidências.

## Arquitetura

```text
MPU-6050 real (X, I²C 21/22, 0x68) -> ESP32 físico (FFT + RMS)
   -> Wi-Fi doméstico -> HTTP POST local + X-API-Key
   -> FastAPI (notebook, 0.0.0.0:8000) -> SQLite (origem=real)
```

Caminho histórico do Marco 2, preservado para simulação:

```
Wokwi (ESP32 simulado + FFT) -- Wi-Fi --> HTTPS POST JSON (X-API-Key)
   --> Cloudflare Quick Tunnel --> FastAPI (notebook, 127.0.0.1:8000) --> SQLite (dados/medicoes.db)
```

Só a porta da API é exposta pelo túnel; o arquivo do banco nunca é exposto. Sem Docker, MQTT, PostgreSQL ou serviços pagos.

## Estrutura

```
backend/   main.py (API) | database.py | models.py (SQL) | schemas.py (Pydantic)
analytics/ isolation.py (ML rastreável) | visualization.py (gráficos de JSON)
dashboard/ app.py (Streamlit somente leitura) | requirements.txt
firmware_fisico/ firmware_fisico.ino | processamento.h | tacometro.h | secrets.example.h
wokwi/     sketch.ino | diagram.json | libraries.txt
scripts/   simular_envio.py (cliente de teste) | consultar_dados.py (SQLite)
           experimento.py (planejamento, coleta, eventos, treino e avaliação)
tests/     test_api.py
dados/     banco SQLite (ignorado pelo Git)
docs/      marco2.md (histórico) | marco3.md (bancada física)
```

## Requisitos

Windows, Python 3.10+, VS Code. Hardware: Arduino IDE e as versões de core/biblioteca acima. Somente para o caminho antigo de simulação: `cloudflared` e conta em wokwi.com.

## Instalação (PowerShell, na pasta do projeto)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # se bloquear: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_urlsafe(32))"   # cole o resultado em API_KEY no .env
```

## Executar a API

```powershell
uvicorn backend.main:create_app --factory --port 8000
```
O banco `dados/medicoes.db` é criado na primeira execução e persiste entre reinícios. Docs interativas: http://127.0.0.1:8000/docs

Endpoints: `POST /medicoes`, `GET /medicoes?limite=50&dispositivo=...`, `GET /medicoes/{id}`, `GET /health` (sem chave). Os demais exigem o cabeçalho `X-API-Key`. Se `API_KEY` não estiver definida, a autenticação fica **desligada** (aviso no log) — nunca abra o túnel assim.

Teste rápido sem Wokwi (em outro terminal):
```powershell
python scripts/simular_envio.py
python scripts/consultar_dados.py            # últimas 10 (também: -n 50, -d DISPOSITIVO, --resumo)
```

## Testes

```powershell
python -m pytest -q
```
Usam banco temporário (`tmp_path`); não tocam em `dados/`.

Validação do Marco 3: **58 testes aprovados** (incluindo os 14 originais), firmware compilado e gravado na COM8, oito registros antigos preservados e dez respostas HTTP 201 físicas correlacionadas com a API e o SQLite. A captura somou 92 janelas FFT, com atrasos zero nessas janelas. Detalhes e limites: [docs/validacao_marco3.md](docs/validacao_marco3.md).

## Marco 2 — Túnel HTTPS (somente simulação histórica)

Esta seção não faz parte da demonstração física do Marco 3.

1. API rodando e testada em localhost (`curl http://127.0.0.1:8000/health`).
2. Instalar: `winget install --id Cloudflare.cloudflared` (feche e reabra o terminal).
3. Em **outro** terminal: `cloudflared tunnel --url http://127.0.0.1:8000`
4. Procure no log a linha com `https://<palavras-aleatorias>.trycloudflare.com`. Essa é a URL pública (muda a cada execução).
5. Verifique: `curl https://<url>/health` deve retornar `{"status":"ok",...}`.
6. Teste também a autenticação pelo túnel: `python scripts/simular_envio.py --url https://<url>`.

## Configurar o Wokwi

1. Em wokwi.com crie um projeto **ESP32** (Arduino).
2. Substitua o conteúdo de `sketch.ino`, `diagram.json` e `libraries.txt` pelos arquivos de `wokwi/` (abas do editor).
3. No topo do `sketch.ino`, edite `API_URL` (`https://<url>/medicoes`) e `API_KEY` (a mesma do `.env`). **Não suba esses valores ao Git.**
4. Clique em ▶. No Serial Monitor observe `[WiFi] conectado`, `[FFT] ...` e, a cada 5 s, `[HTTP] POST -> 201 {"id":...}`.
5. Confirme no notebook: `python scripts/consultar_dados.py -d esp32-wokwi-01`.

Notas:
- Tacômetro: o sketch gera os pulsos no GPIO26 (timer) e o `diagram.json` liga GPIO26→GPIO27. Se você usa um gerador de pulsos próprio já ligado ao GPIO27, remova a ligação 26→27 e o bloco `esp_timer`.
- `TLS_INSEGURO = true` usa `setInsecure()` (sem validar certificado). **Limitação aceita apenas na simulação**; em produção, embarque a CA e valide o certificado.
- A API Wi-Fi do Wokwi usa o gateway público, que monitora tráfego: não envie dados sensíveis.
- Cenários: digite `0`, `1` ou `2` no Serial Monitor, ou use `CICLAR_CENARIOS`.

## Consultar o SQLite

```powershell
python scripts/consultar_dados.py -n 20
python -c "import sqlite3; print(sqlite3.connect('dados/medicoes.db').execute('SELECT * FROM medicoes ORDER BY id DESC LIMIT 5').fetchall())"
```
Ou use a extensão "SQLite Viewer" do VS Code.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| HTTP 401 | `API_KEY` do sketch ≠ `.env`, ou API iniciada antes de criar o `.env` |
| HTTP 422 | JSON fora das regras (ver `backend/schemas.py`) |
| `-1` / `connection refused` no Serial | URL do túnel antiga/errada; túnel ou API parados |
| `begin() falhou` | URL sem `https://` ou com erro de digitação |
| `SSL - The connection indicated an EOF` (~13 s) | Handshake TLS do ESP32 no Wokwi foi encerrado pela Cloudflare (observado neste projeto). Use `http://<url>/medicoes` apenas na simulação e troque a `API_KEY` depois |
| Erro de compilação com arduinoFFT | Versão diferente da 2.x (a API mudou da 1.x para a 2.x) |
| `Activate.ps1` bloqueado | `Set-ExecutionPolicy -Scope Process Bypass` |
| Túnel muda de URL | Normal no Quick Tunnel; atualize o sketch a cada nova execução |


### Campanha fisica de 10/11/2026

As seis coletas foram concluidas (355 registros reais) e os dois modelos foram avaliados. Houve alertas em 100% das sessoes normais de validacao; a discriminacao normal/alterado ainda nao foi demonstrada. Consulte [resultados experimentais e evidencias](docs/resultados_experimentais.md).

Investigação posterior: [diagnóstico técnico do ML](docs/diagnostico_ml.md), com auditoria dos artefatos originais, distribuições, scores contínuos, baseline estatístico e proposta de ensaio de repetibilidade normal. Os modelos anteriores foram preservados.

## Painel educacional e preparação da nuvem

```powershell
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard/app_publico.py --server.address 127.0.0.1
```

Sem configuração remota, abre em replay explícito dos 355 registros físicos e 710 scores preservados. A sincronização SQLite → Supabase é um worker separado; não expõe a FastAPI e não interrompe a aquisição em falhas de internet. O dashboard usa somente leitura e informa que o ML continua experimental, sem generalização validada.

Consulte [DEPLOY_STATUS](docs/DEPLOY_STATUS.md) para o estado efetivamente verificado e [guia de nuvem](docs/guia_nuvem.md) para RLS, outbox, secrets, GitHub, Streamlit Community Cloud e QR Code. Nenhuma URL pública deve ser presumida sem confirmação nesse relatório.
