# flood-monitor-florianopolis

Sistema de monitoramento de risco de alagamento urbano para Florianópolis, SC.

Projeto final da disciplina EEL7415/7515 - Tópicos Avançados em Telecomunicações / IoT
UFSC - Prof. Richard Demo Souza
Autor: José Eduardo Pereira (23200252)

**vídeo de apresentação:** https://youtu.be/zqdg2aEXK80

---

## arquitetura

```
CEMADEN PED API
     │ (a cada ~10 min)
[client] coletor_cemaden.py        ← nó IoT (simula o ESP32)
     │ MQTT  flood/cemaden/raw
     ▼
[host] interpretador_risco.py      ← funde os dados e classifica
     + Open-Meteo (previsão 6h + umidade do solo)
     │ MQTT  flood/risco/classificado   +   grava em landing/
     ▼
[host] dataviz.py                  ← dashboard Streamlit
```

O projeto é dividido em dois lados, que na implementação final rodam em máquinas diferentes:

- **`client/`** — o **nó sensor**. Roda no dispositivo de campo (aqui, um notebook simulando o ESP32). Só coleta e publica via MQTT.
- **`host/`** — o **backend**. Roda no servidor: broker MQTT, interpretador de risco e dashboard.

Na demonstração, o `client` (notebook) publica no broker do `host` (servidor) através de um túnel **WireGuard**. O `coletor_cemaden.py` simula o papel do ESP32 físico; na versão final, esse papel seria assumido pelo firmware embarcado.

broker MQTT: **Mosquitto** rodando no host (porta 1883).

---

## estrutura do repositório

```
floripa-flood-monitor/
├── client/                     # roda no nó sensor (notebook / ESP32)
│   ├── coletor_cemaden.py      # coleta CEMADEN → publica MQTT
│   ├── simular.py              # publica cenários de teste (demo)
│   ├── requirements.txt
│   └── .env.example
├── host/                       # roda no servidor (backend)
│   ├── interpretador_risco.py  # assina MQTT, funde c/ Open-Meteo, classifica
│   ├── dataviz.py              # dashboard Streamlit
│   ├── landing/                # dados brutos + tratados (gitignored)
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## fontes de dados

### CEMADEN

O **CEMADEN** (Centro Nacional de Monitoramento e Alertas de Desastres Naturais)
é o órgão federal, vinculado ao Ministério da Ciência, Tecnologia e Inovação,
responsável pela rede de pluviômetros automáticos espalhada pelo Brasil —
são esses os sensores físicos reais que este projeto usa como fonte de chuva.

O acesso programático aos dados é feito pelo **PED** (Plataforma de Espalhamento
de Dados), o portal/API do CEMADEN para consumo externo dos dados coletados
pela rede de estações.

- site institucional: https://www.cemaden.gov.br/
- portal PED (cadastro + documentação): https://ped.cemaden.gov.br/
- endpoint base usado neste projeto: `https://sws.cemaden.gov.br/PED/rest`
  - cadastro das estações: `/pcds-cadastro/dados-cadastrais?codibge=4205407`
  - acumulados recentes de chuva: `/pcds-acum/acumulados-recentes?codibge=4205407`
  - `4205407` é o código IBGE de Florianópolis/SC
- autenticação: JWT via header `token`
- limite: 12 requisições/min para usuários externos

**Como obter o token CEMADEN:**
1. Cria uma conta em https://ped.cemaden.gov.br/
2. Faz login no portal
3. Gera/copia o token JWT na área de acesso à API (perfil da conta)
4. Cola em `client/.env`, na variável `CEMADEN_TOKEN`
5. **O token expira em poucas horas.** Se a coleta retornar `401 Token não
   encontrado no banco de dados`, é só gerar um novo no portal e atualizar o
   `.env` — o script não precisa ser alterado.

### Open-Meteo

A **Open-Meteo** é uma API meteorológica gratuita e de código aberto, sem
necessidade de cadastro ou chave de API. Usada aqui para complementar o dado
físico do CEMADEN com previsão de precipitação (próximas 6h) e umidade do solo.

- site: https://open-meteo.com/
- documentação da API (Forecast): https://open-meteo.com/en/docs
- endpoint usado: `https://api.open-meteo.com/v1/forecast`

---

## índice de risco

pontuação 0-100, com limiares **experimentais** para chuva acumulada em 24h
(<10mm baixo, 10-30 moderado, 30-60 alto, 60+ crítico), na mesma ordem de
grandeza da classificação meteorológica geral de intensidade de chuva diária
usada por institutos como o INMET (fraca até ~10mm, moderada 10-25mm, forte
25-50mm, muito forte 50mm+).

**importante:** não existe uma tabela oficial única de risco de alagamento em
mm publicada pela Defesa Civil. o CEMADEN, na prática, define seus níveis de
alerta (moderado/alto/muito alto) combinando múltiplos fatores — chuva
observada, previsão, tipo de terreno e vulnerabilidade da população — com
valores críticos calibrados individualmente por estação, não por uma tabela
universal. o código COBRADE 1.1.1.1.2 (citado no protótipo inicial,
`propostsa_projeto_final/teste/floripapluvio.py`) também não define limiares
em mm: ele apenas classifica o *tipo* de desastre ("inundação gradual").
uma calibração de verdade exigiria dados históricos de ocorrências cruzados
com os acumulados de chuva de cada estação — isso fica como próximo passo.

| variável | fonte | peso máximo |
|---|---|---|
| chuva acumulada 24h | CEMADEN | 40 pts |
| chuva acumulada 72h | CEMADEN | 20 pts |
| previsão precipitação 6h | Open-Meteo | 25 pts |
| umidade do solo | Open-Meteo | 15 pts |

| score | classificação |
|---|---|
| 0-19 | BAIXO |
| 20-44 | MEDIO |
| 45-69 | ALTO |
| 70+ | CRITICO |

---

## como rodar

### 1. broker MQTT (no host)

Mosquitto na porta 1883. `mosquitto.conf`:
```
listener 1883
allow_anonymous true
```
Para um teste rápido sem instalar nada, dá pra apontar `MQTT_BROKER` para um broker público (ex: `broker.hivemq.com`).

### 2. host (backend)

```bash
cd host
pip install -r requirements.txt
cp .env.example .env      # e preencha
python interpretador_risco.py     # fica escutando o broker
streamlit run dataviz.py          # dashboard em http://localhost:8501
```

### 3. client (nó sensor)

```bash
cd client
pip install -r requirements.txt
cp .env.example .env      # token CEMADEN + MQTT_BROKER = IP do host
python coletor_cemaden.py -i 30   # coleta real a cada 30s
```

### configuração (.env)

- **client** precisa de: `CEMADEN_TOKEN`, `CEMADEN_BASE`, `CEMADEN_CODIBGE`, `MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC_RAW`
- **host** precisa de: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC_RAW`, `MQTT_TOPIC_RISCO`

Rodando tudo numa máquina só (teste local), use `MQTT_BROKER=localhost` nos dois.

---

## simulação (demo)

Como nem sempre está chovendo, o `client/simular.py` publica cenários fixos no mesmo tópico do coletor, pra demonstrar as 4 classes de risco ao vivo:

```bash
python simular.py baixo       # dashboard verde
python simular.py medio
python simular.py alto
python simular.py critico      # dashboard vermelho
python simular.py critico -n 5 -i 2    # publica 5x, a cada 2s (popula o gráfico 12h)
```

Cada cenário inclui valores forçados de previsão/umidade (campo `simulacao` no payload), que o interpretador usa no lugar da consulta ao Open-Meteo — garantindo a classe de risco desejada mesmo com tempo seco.

---

## landing

cada execução salva os dados brutos e tratados localmente, em `landing/` (gitignored):

```
client/landing/
└── coletor_cemaden/
    ├── raw/                  # resposta bruta do CEMADEN (cadastro + acumulados)
    └── treated/              # payload publicado no MQTT

host/landing/
└── interpretador_risco/
    ├── raw/
    ├── raw-open_meteo/
    └── treated/              # ← lido pelo dashboard
```

---

## próximos passos

- [ ] validar dados obtidos do CEMADEN (nulls, estações inativas, outliers)
- [ ] validar e calibrar cálculo do índice de risco com dados históricos
- [ ] avaliar opção de armazenamento dos dados estruturados (PostgreSQL, DuckDB)
- [ ] avaliar implementação do código de extração diretamente no ESP32 físico
- [ ] avaliar execução remota por nuvem gerenciada
