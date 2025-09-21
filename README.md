# Halma Net 🎮

Jogo de *Halma online com chat e multiplayer* usando **Python + sockets + Pygame** — Trabalho da Disciplina de Programação Paralela e Distribuída

## 📋 Requisitos

* Python **3.9+**
* Biblioteca **pygame**

Instalação do pygame:

```bash
pip install pygame
```

No Linux, pode ser necessário instalar dependências do SDL:

```bash
sudo apt-get install python3-dev libsdl2-dev libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 libsdl2-mixer-2.0-0
```

---

## ▶️ Como rodar

```bash
cd repositorioDiretorio
```

### 1. Inicie o servidor

Abra um terminal e rode:

```bash
python -m Halma --server --host 192.168.x.y --port 5007
```

### 2. Conecte os clientes

Em outros terminais (ou outros PCs na mesma rede):

* Jogador 1:

```bash
python -m Halma --client --host 192.168.x.y --port 5007
```

* Jogador 2:

```bash
python -m Halma --client --host 192.168.x.y --port 5007
```

> Use **o IP do servidor** no lugar de `192.168.x.y`.
> Se for na mesma máquina, você pode usar `--host 127.0.0.1`.

---

## 🔒 Se não conseguir conectar (Firewall/Rede)

Alguns sistemas/roteadores bloqueiam conexões na rede local. Siga os passos abaixo **nesta ordem**:

### 1) Teste rápido de conectividade

* No **cliente**, teste a porta:

  * **Windows (PowerShell)**:

    ```powershell
    Test-NetConnection -ComputerName 192.168.x.y -Port 5007
    ```
  * **Linux/macOS** (se tiver `nc`):

    ```bash
    nc -vz 192.168.x.y 5007
    ```
  * Se falhar, habilite a porta no firewall (passos a seguir).

### 2) macOS (servidor)

* **Via interface gráfica**:

  1. **Ajustes do Sistema → Rede → Firewall**

     * Desative **“Modo furtivo (Stealth)”** para testar.
     * Em **Opções**/**Aplicativos permitidos**, **adicione** o Python que você usa para rodar o servidor (o mesmo de `which python3`) e marque **“Permitir conexões de entrada”**.
  2. **Privacidade e Segurança → Developer Tools**: marque Terminal/IDE (se aplicável).
* **Via linha de comando (opcional/avançado)**:

  ```bash
  # Descubra o Python que você usa:
  which python3
  # Exemplo de caminho: /opt/homebrew/bin/python3

  # Adiciona e libera esse binário no firewall:
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /opt/homebrew/bin/python3
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /opt/homebrew/bin/python3

  # Desativa o "Stealth mode" (para teste):
  sudo defaults write /Library/Preferences/com.apple.alf stealthenabled -bool false

  # (Opcional) Desativar firewall TEMPORARIAMENTE para teste:
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
  # …teste a conexão…
  # Reative depois:
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
  ```

  > Observação: se você trocar a versão/caminho do Python (pyenv/Homebrew), **repita** a permissão.

### 3) Windows (servidor)

* **Permitir o Python/app no Firewall**:

  * Painel de Controle → **Sistema e Segurança** → **Firewall do Windows Defender** → **Permitir um aplicativo pelo firewall** → **Permitir outro aplicativo…** → selecione o `python.exe` usado (ex.: `C:\Users\...\AppData\Local\Programs\Python\Python3x\python.exe`) e marque **Privado**.
* **Abrir a porta 5007 por regra (alternativa)**:

  ```powershell
  netsh advfirewall firewall add rule name="Halma Server 5007" dir=in action=allow protocol=TCP localport=5007
  ```

### 4) Linux (servidor)

* **UFW (Ubuntu/Debian)**:

  ```bash
  sudo ufw allow 5007/tcp
  sudo ufw status
  ```
* **firewalld (Fedora/CentOS)**:

  ```bash
  sudo firewall-cmd --add-port=5007/tcp --permanent
  sudo firewall-cmd --reload
  ```

### 5) Roteador / Wi-Fi

* Garanta que **servidor e clientes estão na mesma rede/sub-rede** (ex.: 192.168.1.\*).
* Desative **AP/Client Isolation** (Isolamento de clientes) na SSID usada.
* Evite rede de **convidados** (geralmente isola clientes).
* Se nada der certo, teste via **túnel SSH** (prova de que é firewall):

  ```bash
  # no cliente
  ssh -N -L 5007:localhost:5007 usuario@192.168.x.y
  # depois conecte o cliente em 127.0.0.1:5007
  ```

---

## 🎮 Controles

* **Clique**: mover peça
* **Enter**: enviar mensagem no chat
* **Espaço**: encerrar cadeia de saltos
* **R**: pedir reinício (precisa dos dois jogadores)
* **D**: desistir
* **Esc**: sair

---

## 👥 Notas

* Até **2 jogadores** + **espectadores ilimitados**.
* O servidor valida movimentos e distribui mensagens de chat.
* Partida reinicia apenas quando **ambos** solicitam.
