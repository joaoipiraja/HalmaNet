# Halma Net 🎮


Jogo de *Halma online com chat e multiplayer** usando **Python + sockets + Pygame** - - Trabalho da Disciplina de Programação Paralela e Distribuída


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

### 1. Inicie o servidor

Abra um terminal e rode:

```bash
python halma_net.py --server --host 0.0.0.0 --port 50007
```

### 2. Conecte os clientes

Em outros terminais (ou outros PCs na mesma rede):

* Jogador 1:

```bash
python halma_net.py --client --host 127.0.0.1 --port 50007
```

* Jogador 2:

```bash
python halma_net.py --client --host 127.0.0.1 --port 50007
```

> Substitua `127.0.0.1` pelo IP do servidor se estiver em máquinas diferentes.

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

---

Quer que eu também monte esse README em **formato markdown pronto para GitHub**, com emojis, badges e blocos de código já estilizados?
