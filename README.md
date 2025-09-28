# Halma Net 🎮

Jogo de *Halma online com chat e multiplayer* usando **Python + sockets + Pygame** — Trabalho da Disciplina de Programação Paralela e Distribuída

## 📋 Requisitos

* Python **3.9+**
* Biblioteca **pygame**

Instalação do pygame:

```bash
cd ~/Downloads/IHC/HalmaNet

# create & activate a venv
python3 -m venv .venv
source .venv/bin/activate

# upgrade pip and install deps
python -m pip install --upgrade pip
# if the project has a requirements file, prefer this:
# pip install -r requirements.txt
pip install pygame

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

## 🔒 Se não conseguir conectar (Desative o Firewall)

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
