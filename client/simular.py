"""
simular.py - no IoT (ESP32) simulado

publica cenarios de chuva no broker MQTT, no mesmo formato do coletor cemaden,
pra demonstrar as classes de risco ao vivo sem depender do tempo real.

os cenarios batem com as 4 classes do dashboard:
    python simular.py baixo
    python simular.py medio
    python simular.py alto
    python simular.py critico
    python simular.py critico -n 5 -i 2     # publica 5x, a cada 2s

o interpretador consome o topico flood/cemaden/raw, classifica, e o dashboard acende.
"""
import os
import json
import time
import argparse
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC_RAW", "flood/cemaden/raw")
CODIBGE = os.getenv("CEMADEN_CODIBGE", "4205407")

# estacoes reais de floripa (mesmas coordenadas do coletor cemaden)
ESTACOES = [
    {"codestacao": "420540702A", "nome": "Coqueiros",      "lat": -27.599, "lon": -48.573},
    {"codestacao": "420540703A", "nome": "Areias Campeche", "lat": -27.706, "lon": -48.500},
    {"codestacao": "420540705A", "nome": "Rodovia SC406",   "lat": -27.754, "lon": -48.510},
    {"codestacao": "420540707A", "nome": "Canasvieiras",    "lat": -27.432, "lon": -48.458},
    {"codestacao": "420540708A", "nome": "Rio Vermelho",    "lat": -27.491, "lon": -48.418},
]

# perfils por cenario: chuva acumulada (mm) + valores forcados de open-meteo.
# o campo "simulacao" faz o interpretador usar esses valores no lugar da API live,
# garantindo a classe de risco desejada (senao o open-meteo real, seco, nunca
# deixaria o score chegar em ALTO/CRITICO). valores calibrados pra cair no meio
# de cada faixa de host/interpretador_risco.py:calcular_risco (escala ancorada
# na Defesa Civil de Florianopolis / COBRADE 1.1.1.1.2).
CENARIOS = {
    "baixo": {  # score ~0
        "chuva": {"chuva_1h": 0.0, "chuva_3h": 0.2, "chuva_6h": 0.5, "chuva_12h": 1.0,
                  "chuva_24h": 2.0, "chuva_48h": 4.0, "chuva_72h": 6.0, "chuva_96h": 7.0, "chuva_120h": 8.0},
        "openmeteo": {"precip_prev_6h": 0.0, "umidade_solo": 0.25},
    },
    "medio": {  # score ~32 (10 c24 + 10 c72 + 5 precip6h + 7 solo)
        "chuva": {"chuva_1h": 1.0, "chuva_3h": 4.0, "chuva_6h": 8.0, "chuva_12h": 12.0,
                  "chuva_24h": 15.0, "chuva_48h": 45.0, "chuva_72h": 65.0, "chuva_96h": 70.0, "chuva_120h": 75.0},
        "openmeteo": {"precip_prev_6h": 5.0, "umidade_solo": 0.32},
    },
    "alto": {  # score ~57 (25 c24 + 10 c72 + 15 precip6h + 7 solo)
        "chuva": {"chuva_1h": 4.0, "chuva_3h": 12.0, "chuva_6h": 20.0, "chuva_12h": 28.0,
                  "chuva_24h": 35.0, "chuva_48h": 55.0, "chuva_72h": 70.0, "chuva_96h": 75.0, "chuva_120h": 80.0},
        "openmeteo": {"precip_prev_6h": 15.0, "umidade_solo": 0.32},
    },
    "critico": {  # score ~100
        "chuva": {"chuva_1h": 25.0, "chuva_3h": 60.0, "chuva_6h": 110.0, "chuva_12h": 180.0,
                  "chuva_24h": 260.0, "chuva_48h": 320.0, "chuva_72h": 344.0, "chuva_96h": 360.0, "chuva_120h": 380.0},
        "openmeteo": {"precip_prev_6h": 35.0, "umidade_solo": 0.9},
    },
}


def montar_payload(cenario):
    cfg = CENARIOS[cenario]
    agora = datetime.now(timezone.utc)
    estacoes = [{**est, "timestamp": agora.isoformat(), **cfg["chuva"]} for est in ESTACOES]
    return {
        "fonte": "simulador",
        "codibge": CODIBGE,
        "ts_coleta": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cenario": cenario,
        "simulacao": cfg["openmeteo"],
        "estacoes": estacoes,
    }


def main():
    p = argparse.ArgumentParser(description="No ESP32 simulado: publica cenarios de chuva via MQTT")
    p.add_argument("cenario", choices=list(CENARIOS), help="cenario de chuva a publicar")
    p.add_argument("-n", "--repeticoes", type=int, default=1, help="quantas vezes publicar (default 1)")
    p.add_argument("-i", "--intervalo", type=float, default=3.0, help="segundos entre publicacoes (default 3)")
    args = p.parse_args()

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulador-esp32")
    cliente.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    cliente.loop_start()
    print(f"[sim] conectado em {MQTT_BROKER}:{MQTT_PORT} - topico '{MQTT_TOPIC}'")

    for i in range(args.repeticoes):
        msg = json.dumps(montar_payload(args.cenario), ensure_ascii=False)
        res = cliente.publish(MQTT_TOPIC, msg, qos=1)
        res.wait_for_publish()
        print(f"[sim] ({i + 1}/{args.repeticoes}) cenario '{args.cenario}' publicado - {len(ESTACOES)} estacoes")
        if i < args.repeticoes - 1:
            time.sleep(args.intervalo)

    cliente.loop_stop()
    cliente.disconnect()


if __name__ == "__main__":
    main()
