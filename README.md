# flood-monitor-florianopolis

Sistema de monitoramento de risco de alagamento urbano para Florianópolis, SC.

Projeto final da disciplina EEL7415/7515 - Tópicos Avançados em Telecomunicações / IoT  
UFSC - Prof. Richard Demo Souza

---

## arquitetura

```
CEMADEN PED API
     ↓ (a cada 10min)
1_coletor_cemaden.ipynb (simula ESP32)
     ↓ MQTT  [flood/cemaden/raw]
2_interpretador_risco.ipynb
     + Open-Meteo (previsão + umidade do solo)
     ↓ MQTT  [flood/risco/classificado]
Dashboard de visualização (em desenvolvimento)
```

o coletor simula o nó IoT (ESP32) em Python. na versão final do projeto, esse papel seria assumido pelo firmware embarcado no ESP32 físico.

broker MQTT: Mosquitto rodando localmente (selfhosted), acessível remotamente via túnel WireGuard

---

## fontes de dados

- **CEMADEN PED** - pluviômetros físicos em Florianópolis (atualização a cada ~10min) | https://ped.cemaden.gov.br/
  - endpoint de cadastro: `/pcds-cadastro/dados-cadastrais?codibge=4205407`
  - endpoint de acumulados: `/pcds-acum/acumulados-recentes?codibge=4205407`
  - autenticação: JWT via header `token` (registro em `ped.cemaden.gov.br`)
  - limite: 12 req/min para usuários externos

- **Open-Meteo** - previsão de precipitação e umidade do solo (sem autenticação) | https://open-meteo.com/
  - forecast API: `api.open-meteo.com/v1/forecast`

---

## índice de risco

pontuação 0-100 baseada em limiares experimentais, a serem calibrados com dados históricos:

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

### pré-requisitos

```bash
pip install -r requirements.txt
```

broker Mosquitto rodando na porta 1883. no Linux/WSL:

```bash
mosquitto -c mosquitto.conf -v
```

`mosquitto.conf`:
```
listener 1883
allow_anonymous true
```

### configuração

preencha o `.env` seguindo o exemplo.  O token CEMADEN pode ser obtido em `ped.cemaden.gov.br`.

### execução

abre os dois notebooks no VSCode e roda em ordem:

1. `2_interpretador_risco.ipynb` - fica em escuta no broker
2. `1_coletor_cemaden.ipynb` - coleta e publica

### landing

cada execução salva os dados brutos e tratados em:

```
landing/
├── coletor_cemaden/
│   ├── raw/
│   └── treated/
├── interpretador_risco/
│   ├── raw/
│   └── treated/
│   └── raw-open_meteo/
```

---

## próximos passos

- [ ] validar dados obtidos do CEMADEN (nulls, estações inativas, outliers)
- [ ] validar e calibrar cálculo do índice de risco com dados históricos
- [ ] avaliar opção de armazenamento dos dados estruturados de maneira open source (PostgreSQL, MySQL, DuckDB)
- [ ] validar arquitetura de ELT
- [ ] decidir plataforma de visualização (Streamlit Community Cloud, Grafana e TagoIO)
- [ ] avaliar implementação do código de extração diretamente no ESP32
- [ ] avaliar execução remota por núvem gerenciada
