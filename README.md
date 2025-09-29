# Halma Net 🎮

Jogo de **Halma online** com **chat** e **multiplayer** usando **Python + sockets + Pygame**.
Trabalho da disciplina **Programação Paralela e Distribuída**.

---

## ✨ Funcionalidades

* Partidas **multiplayer (2 jogadores)** com **espectadores ilimitados**
* **Chat** integrado entre jogadores/espectadores
* **Servidor** valida movimentos e distribui mensagens
* Reinício de partida apenas quando **ambos os jogadores concordam**

---

## 📦 Requisitos

* **Python 3.9+**
* Biblioteca **pygame**

### Instalação rápida

```bash
# entre no diretório do repositório
cd repositorioDiretorio

# crie e ative um ambiente virtual
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# atualize o pip e instale dependências
python -m pip install --upgrade pip
# se existir requirements.txt, prefira:
# pip install -r requirements.txt
pip install pygame
```

---

## ▶️ Como executar

> Substitua `192.168.x.y` pelo **IP da máquina do servidor**.
> Se tudo estiver na mesma máquina, use `--host 127.0.0.1`.

### 1) Inicie o servidor

Em um terminal:

```bash
python -m Halma --server --host 192.168.x.y --port 5010
```

### 2) Conecte os clientes

Em outros terminais (ou outros PCs na mesma rede):

```bash
# Jogador 1
python -m Halma --client --host 192.168.x.y --port 5010

# Jogador 2
python -m Halma --client --host 192.168.x.y --port 5010
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

## 🌐 Rede & Firewall

Se não conseguir conectar:

* Confirme o **IP do servidor** (ex.: `ipconfig` no Windows, `ip addr`/`ifconfig` no Linux/Mac).
* Verifique se a **porta** usada (padrão `5010`) não está ocupada.
* **Firewall**: libere a porta TCP no servidor (ou teste temporariamente com o firewall desativado).
* Certifique-se de que os dispositivos estão na **mesma rede**.

---

## 🧰 Opções de linha de comando

```text
--server / --client   Modo de execução
--host <IP>           Interface/IP a escutar (servidor) ou conectar (cliente)
--port <PORTA>        Porta TCP (ex.: 5010)
```

> Exemplo servidor local: `python -m Halma --server --host 0.0.0.0 --port 5010`
> Exemplo cliente local: `python -m Halma --client --host 127.0.0.1 --port 5010`

---

## ❗ Dicas e solução de problemas

* **Pygame não encontrado**: garanta que o *venv* está **ativo** antes de rodar.
* **Conexão recusada**: inicie o **servidor** primeiro; confira `host/port`.
* **Lag na rede**: prefira conexão por cabo ou Wi-Fi de 5 GHz; feche apps que usam muita banda.
* **Porta em uso**: tente outra (ex.: `--port 5011`).

---

## 👥 Notas

* Máximo de **2 jogadores** por partida; espectadores ilimitados podem acompanhar e usar o chat.
* O **servidor** é a autoridade do jogo (valida movimentos e sincroniza estado).
* O **reinício** da partida ocorre somente quando **ambos** os jogadores solicitam.


