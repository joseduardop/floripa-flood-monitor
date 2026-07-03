"""
coletor_cemaden.py - no IoT (ESP32 simulado)

consulta a API do CEMADEN PED em intervalos regulares e publica os dados brutos
de pluviometria via MQTT no topico flood/cemaden/raw.

na arquitetura final esse papel e do ESP32 fisico; aqui um script Python faz o
mesmo trabalho: autentica, puxa os acumulados das estacoes de Florianopolis e
publica no broker.

uso:
    python coletor_cemaden.py             # coleta a cada 600s (10 min, limite do cemaden)
    python coletor_cemaden.py -i 30       # coleta a cada 30s (util pra demo ao vivo)
"""
import os
import json
import time
import argparse
from pathlib import Path

import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).resolve().parent

CEMADEN_TOKEN = os.getenv("CEMADEN_TOKEN")
CEMADEN_BASE = os.getenv("CEMADEN_BASE")
CODIBGE = os.getenv("CEMADEN_CODIBGE")

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC_RAW")


def salvar_json(payload, origem="coletor_cemaden"):
    ts = payload.get("ts_coleta", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    pasta = BASE / "landing" / origem
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{ts.replace(':', '-')}.json"
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[landing] salvo em {arquivo}")


def buscar_estacoes():
    url = f"{CEMADEN_BASE}/pcds-cadastro/dados-cadastrais?codibge={CODIBGE}"
    r = requests.get(url, headers={"token": CEMADEN_TOKEN}, timeout=10)
    r.raise_for_status()
    return r.json()


def buscar_acumulados():
    url = f"{CEMADEN_BASE}/pcds-acum/acumulados-recentes?codibge={CODIBGE}"
    r = requests.get(url, headers={"token": CEMADEN_TOKEN}, timeout=10)
    r.raise_for_status()
    return r.json()


def montar_payload(estacoes, acumulados):
    # o join entre cadastro (coords) e acumulados (chuva) e feito pelo codestacao.
    # so entram no payload as estacoes presentes em "acumulados-recentes": esse
    # endpoint ja reflete quem esta reportando de fato. o campo dh_inicio_inativo
    # do cadastro nao e confiavel (estacoes com esse campo preenchido continuam
    # aparecendo em acumulados-recentes com remessa do dia anterior).
    mapa_coords = {}
    for e in estacoes:
        mapa_coords[e["codestacao"]] = {
            "nome": e.get("nome", ""),
            "lat": e.get("latitude"),
            "lon": e.get("longitude"),
        }

    descartadas = 0
    leituras = []
    for a in acumulados:
        cod = a.get("codestacao")
        if cod not in mapa_coords:
            descartadas += 1
            continue  # sem cadastro correspondente (nome/coordenadas desconhecidos)
        coords = mapa_coords.get(cod, {})
        leituras.append({
            "codestacao": cod,
            "nome": coords.get("nome", ""),
            "lat": coords.get("lat"),
            "lon": coords.get("lon"),
            "timestamp": a.get("datahora"),
            "chuva_1h": a.get("acc1hr"),
            "chuva_3h": a.get("acc3hr"),
            "chuva_6h": a.get("acc6hr"),
            "chuva_12h": a.get("acc12hr"),
            "chuva_24h": a.get("acc24hr"),
            "chuva_48h": a.get("acc48hr"),
            "chuva_72h": a.get("acc72hr"),
            "chuva_96h": a.get("acc96hr"),
            "chuva_120h": a.get("acc120hr"),
        })

    if descartadas:
        print(f"[cemaden] {descartadas} leitura(s) descartada(s) sem cadastro correspondente")

    return {
        "fonte": "cemaden_ped",
        "codibge": CODIBGE,
        "ts_coleta": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "estacoes": leituras,
    }


def publicar(cliente, payload):
    msg = json.dumps(payload, ensure_ascii=False)
    resultado = cliente.publish(MQTT_TOPIC, msg, qos=1)
    resultado.wait_for_publish()
    print(f"[mqtt] publicado {len(payload['estacoes'])} estacoes em '{MQTT_TOPIC}'")


def main():
    p = argparse.ArgumentParser(description="Coletor CEMADEN: publica pluviometria via MQTT")
    p.add_argument("-i", "--intervalo", type=int, default=600,
                   help="segundos entre coletas (default 600; use ~30 na demo)")
    args = p.parse_args()

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esp32-simulado-cemaden")
    cliente.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    cliente.loop_start()

    print(f"[info] conectado ao broker {MQTT_BROKER}:{MQTT_PORT}")
    print(f"[info] coletando a cada {args.intervalo}s. Ctrl+C para parar.\n")

    while True:
        try:
            print("[cemaden] buscando estacoes...")
            estacoes = buscar_estacoes()
            acumulados = buscar_acumulados()
            payload = montar_payload(estacoes, acumulados)

            salvar_json({"estacoes": estacoes, "acumulados": acumulados}, origem="coletor_cemaden/raw")
            salvar_json(payload, origem="coletor_cemaden/treated")

            print(f"[cemaden] {len(payload['estacoes'])} estacoes coletadas.")
            publicar(cliente, payload)

        except requests.HTTPError as e:
            print(f"[erro] HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            print(f"[erro] {e}")

        print(f"[info] aguardando {args.intervalo}s...\n")
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
