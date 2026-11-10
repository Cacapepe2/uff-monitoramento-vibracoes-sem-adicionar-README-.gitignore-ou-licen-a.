# Checagem na apresentação presencial

No PowerShell, dentro de `monitoramento_ventilador`:

```powershell
.\.venv\Scripts\python.exe scripts/checar_bancada.py
```

O comando só lê dados. Verifica integridade do SQLite, API com autenticação, igualdade entre API e SQLite, chegada de novos IDs durante 12 segundos, sucesso recente do sincronizador, uma medição no Supabase e saúde do Streamlit público. Não exibe chaves, senhas ou IPs. `[ATENCAO]` indica o item que precisa de verificação; HTTP 200 do Streamlit não substitui olhar as métricas no navegador. A observação de novos IDs não é uma inspeção física da montagem.

Se os serviços estiverem parados, abra dois terminais separados. Não iniciar outra instância se a checagem indicar que já estão ativos:

```powershell
# Terminal 1: aquisição na rede local
.\.venv\Scripts\python.exe scripts/iniciar_api_local.py
```

```powershell
# Terminal 2: envio para nuvem
.\.venv\Scripts\python.exe scripts/sincronizar_supabase.py --loop
```

Mantenha os terminais abertos; Ctrl+C encerra o processo de cada terminal. Os serviços em segundo plano desta sessão têm os auxiliares locais `parar_cloud.py` (worker e painel local) e `parar_api.py`, dentro de `.marco3_local/`, que conferem a identidade dos processos antes de encerrá-los.

Antes de sair, teste a rede que será usada. O ESP32 precisa reconhecer o Wi-Fi 2,4 GHz e alcançar o notebook na mesma LAN; o notebook precisa de internet para enviar ao Supabase. Uma rede diferente pode exigir alterar SSID/senha e o IPv4 da URL em `firmware_fisico/secrets.h`, compilar e gravar novamente. O firmware usa IPv4 literal: o endereço do notebook pode mudar por DHCP mesmo em uma rede conhecida. Não editar apenas o `.env` esperando alterar a URL já gravada no ESP32. Isolamento de clientes e redes de convidados podem bloquear a comunicação. Não desligar firewall nem abrir túnel público.

O hotspot do celular já foi configurado em 2,4 GHz, o firmware foi recompilado e gravado na COM8 e o caminho até o Supabase foi comprovado com os IDs reais 5973–5975. Após autorização explícita, foi criada a regra `UFF-Monitoramento-Hotspot-8000`: entrada TCP 8000, perfil Private, interface Wi-Fi, programa da API, endereço local do notebook e origem limitada ao IP do ESP32. Nenhuma regra antiga foi removida e o firewall continua ativo. A evidência sanitizada está em [hotspot_validacao.json](evidencias_cloud/hotspot_validacao.json).

Mantenha o mesmo nome/senha do hotspot e a banda 2,4 GHz. Ao religar ou reconectar, notebook e ESP32 podem receber outros endereços: isso pode exigir atualizar tanto a URL do firmware quanto a regra restrita. Execute o checklist antes de apresentar; não há promessa de IP fixo. Não mude para o Wi-Fi doméstico esperando que o firmware configurado para o hotspot o reconheça automaticamente.

Para remover exclusivamente essa liberação após a bancada, se desejar, execute manualmente em PowerShell como administrador:

```powershell
Remove-NetFirewallRule -Name 'UFF-Monitoramento-Hotspot-8000'
```

A remoção interrompe a permissão de entrada correspondente; não execute antes de concluir a demonstração ao vivo.

Para demonstrar, abra o dashboard público, selecione **Nuvem · Supabase**, observe a idade da medição e novos IDs. Preserve a fixação do sensor e não ligue o TACH. Não use alertas de ML como diagnóstico de falha.

Se a rede falhar, selecione **Replay · histórico real**. Esse modo usa as 355 medições e os 710 scores preservados e informa explicitamente que não são dados ao vivo. Para apresentar sem internet alguma, inicie o painel local:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app_publico.py --server.address 127.0.0.1
```

Abra `http://127.0.0.1:8501` e escolha Replay. Não iniciar outro painel se a porta já estiver ocupada.

Fechar o ChatGPT não encerra os serviços. Desligar ou suspender o notebook interrompe a aquisição e a sincronização; o histórico já enviado permanece na nuvem. Ao retomar, execute novamente a checagem. Não há recuperação de medições que deixaram de ser recebidas durante a suspensão. Para a demonstração ao vivo, mantenha o notebook ligado e conectado à energia.

Ao pedir auxílio ao agente no local, diga: **“Execute scripts/checar_bancada.py e confira se estão chegando IDs novos.”** O agente verifica o ambiente disponível sem precisar de credenciais pelo chat.
