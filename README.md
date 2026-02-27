# INVISTIS — Real-Time Crypto Intelligence Pipeline

> Pipeline de données temps réel pour l'investissement en cryptomonnaies  
> **DATA NEXT** × **INVISTIS** — Février 2026

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Stack Technique](#stack-technique)
- [Sources de données](#sources-de-données)
- [Kafka Topics](#kafka-topics)
- [Spark Structured Streaming](#spark-structured-streaming)
- [Outputs](#outputs)
- [Installation & Configuration](#installation--configuration)
- [Structure du projet](#structure-du-projet)
- [Statut des livrables](#statut-des-livrables)
- [Problèmes connus & Solutions](#problèmes-connus--solutions)

---

## Vue d'ensemble

Ce pipeline ingère des données crypto en temps réel depuis **Binance WebSocket**, **NewsAPI** et **FRED API**, les traite via **Spark Structured Streaming sur Databricks**, et les écrit vers un **Delta Lake** et **Supabase PostgreSQL**.

```
Binance WS ──┐
NewsAPI ──────┼──► Confluent Kafka ──► Spark Databricks ──► Delta Lake
FRED + Airflow┘                                          ──► Supabase
                                                         ──► alerts_topic
```

---

## Architecture

![Architecture Diagram](docs/architec<img width="1400" height="960" alt="architecture_invistis" src="https://github.com/user-attachments/assets/275ead2f-ccf1-4a25-b0a2-0345369faa96" />
ture_invistis.png)

### Flux de données

1. **Ingestion** : Producers Python → Kafka topics (Confluent Cloud)
2. **Processing** : Spark Structured Streaming (Databricks Serverless)
   - Parse JSON + Schema Validation
   - Stream-to-Stream Join avec Watermark 5min
   - Windowing 1min / 5min
   - Enrichissement FRED (macro data)
   - Scoring sentiment
3. **Fan-Out** : Multi-sink via `foreachBatch`
   - → Delta Lake (raw + enriched)
   - → Supabase REST API (warehouse)
   - → alerts_topic (Kafka)

---

## Stack Technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Message Broker | Confluent Cloud (Kafka) | Latest |
| Stream Processing | Databricks Serverless | Spark 3.5 |
| Data Lake | Delta Lake | /Volumes Unity Catalog |
| Warehouse | Supabase (PostgreSQL) | 15 |
| Orchestration | Apache Airflow | 2.x |
| Language | Python | 3.10+ |
| Serialization | JSON / Parquet | — |

---

## Sources de données

### 1. Binance WebSocket
- **Endpoint** : `wss://stream.binance.com:9443/ws/btcusdt@trade`
- **Données** : symbol, price, quantity, timestamp, trade_id
- **Fréquence** : Temps réel (tick-by-tick)

### 2. NewsAPI
- **Endpoint** : `https://newsapi.org/v2/everything?q=bitcoin`
- **Données** : title, description, source, published_at, sentiment
- **Fréquence** : Toutes les heures

### 3. FRED API (Federal Reserve)
- **Endpoint** : `https://fred.stlouisfed.org/graph/fredgraph.csv`
- **Données** : Indicateurs macro-économiques (taux, inflation, etc.)
- **Fréquence** : Quotidien via Airflow DAG

---

## Kafka Topics

| Topic | Description | Schéma |
|-------|-------------|--------|
| `trades_topic` | Trades Binance temps réel | `{symbol, price, quantity, timestamp, trade_id}` |
| `news_topic` | Articles NewsAPI | `{title, description, source, published_at, sentiment}` |
| `fred_topic` | Données macro FRED | `{indicator, value, date, frequency}` |
| `alerts_topic` | Alertes price spike | `{symbol, price, alert_type, threshold, event_time}` |

### Configuration Confluent Cloud

```python
kafka_options = {
    "kafka.bootstrap.servers": "pkc-921jm.us-east-2.aws.confluent.cloud:9092",
    "kafka.sasl.mechanism": "PLAIN",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.jaas.config": 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="API_KEY" password="API_SECRET";',
    "startingOffsets": "earliest",
    "failOnDataLoss": "false"
}
```

---

## Spark Structured Streaming

### Stream-to-Stream Join

```python
# Watermark obligatoire sur les deux streams
trades_df = trades_df.withWatermark("event_time", "5 minutes")
news_df   = news_df.withWatermark("event_time", "5 minutes")

# Join dans une fenêtre ±5 minutes
joined_df = trades_df.alias("t").join(
    news_df.alias("n"),
    expr("""
        t.symbol = n.symbol AND
        t.event_time BETWEEN n.event_time - INTERVAL 5 MINUTES
                         AND n.event_time + INTERVAL 5 MINUTES
    """),
    "inner"
)
```

### Batch Join (implémenté en production)

```python
# Fenêtre 24h pour maximiser les correspondances trades/news
joined_batch = trades_batch.alias("t").join(
    news_batch.alias("n"),
    (col("t.symbol") == col("n.symbol")) &
    (col("t.event_time").between(
        col("n.event_time") - expr("INTERVAL 24 HOURS"),
        col("n.event_time") + expr("INTERVAL 24 HOURS")
    )),
    "left"
)
```

### Multi-Sink Fan-Out

```python
# Sink 1 — Delta Lake
joined_batch.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .save("/Volumes/invistis/datalake/raw/enriched")

# Sink 2 — Supabase REST API
response = requests.post(
    "https://XXXX.supabase.co/rest/v1/enriched_trades",
    headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
    data=json.dumps(batch)
)
```

---

## Outputs

### Delta Lake

```
/Volumes/invistis/datalake/
├── raw/
│   ├── enriched/          # Données enrichies (Delta format)
│   └── checkpoints/       # Spark streaming checkpoints
```

### Supabase — Table `enriched_trades`

```sql
CREATE TABLE enriched_trades (
    symbol       TEXT,
    price        FLOAT8,
    quantity     FLOAT8,
    trade_time   TIMESTAMP,
    news_title   TEXT,
    sentiment    FLOAT8,
    news_time    TIMESTAMP,
    window_start TIMESTAMP,
    window_end   TIMESTAMP
);
```

> **3 993 lignes ingérées** — Février 2026

---

## Installation & Configuration

### Prérequis

```bash
pip install kafka-python confluent-kafka pyspark requests psycopg2-binary pandas numpy
```

### Variables d'environnement

```bash
# Confluent Kafka
CONFLUENT_BOOTSTRAP="pkc-921jm.us-east-2.aws.confluent.cloud:9092"
CONFLUENT_API_KEY="YOUR_API_KEY"
CONFLUENT_SECRET="YOUR_API_SECRET"

# Supabase
SUPABASE_URL="https://XXXX.supabase.co"
SUPABASE_KEY="YOUR_ANON_KEY"

# FRED API
FRED_API_KEY="YOUR_FRED_KEY"

# NewsAPI
NEWS_API_KEY="YOUR_NEWS_KEY"
```

### Databricks — Checkpoints

> **Important** : Les checkpoints Spark Streaming **doivent** être sur `/Volumes` (Unity Catalog).  
> Le path `/Workspace` est interdit pour le state store RocksDB en mode Serverless.

```python
CHECKPOINT_PATH = "/Volumes/invistis/datalake/raw/checkpoints"
DATA_PATH       = "/Volumes/invistis/datalake/raw/enriched"
```

---

## Structure du projet

```
invistis-crypto-pipeline/
├── producers/
│   ├── binance_producer.py        # WebSocket → trades_topic
│   ├── news_producer.py           # NewsAPI → news_topic
│   └── fred_producer.py           # FRED API → fred_topic (Airflow)
├── notebooks/
│   └── spark_streaming_pipeline   # Databricks notebook principal
├── airflow/
│   └── fred_dag.py                # DAG ingestion FRED quotidien
├── supabase/
│   └── schema.sql                 # DDL table enriched_trades
├── docs/
│   ├── architecture_invistis.png  # Diagramme architecture
│   └── confluence_doc.docx        # Documentation technique complète
└── README.md
```

---

## Statut des livrables

| Livrable | Statut |
|----------|--------|
| Kafka topics (4 topics) | Opérationnel |
| Stream-to-Stream Join + Watermark | Implémenté |
| Delta Lake écriture | 3993 rows |
| Supabase ingestion | 3993 rows via REST |
| Multi-sink Fan-Out | Delta + Supabase |
| alerts_topic Kafka | En cours |
| Airflow DAG FRED | En cours |
| Architecture alternative | En cours |
| Redis cache layer | Optionnel |
| Documentation Confluence | Livrée |
| Architecture diagram | Livré |
| README | Ce fichier |

---

## Problèmes connus & Solutions

### JDBC bloqué en Serverless
**Erreur** : `UNSUPPORTED_DATA_SOURCE` — Databricks Serverless bloque JDBC PostgreSQL  
**Solution** : Utilisation de l'API REST Supabase (HTTPS port 443) avec `requests`

### Checkpoint /Workspace interdit
**Erreur** : `Mkdirs failed` — RocksDB state store ne peut pas écrire dans `/Workspace`  
**Solution** : Chemin déplacé vers `/Volumes/invistis/datalake/raw/checkpoints`

### Schema mismatch Delta
**Erreur** : Schema mismatch detected — ancienne table avec `window_5min` struct  
**Solution** : `.option("overwriteSchema", "true")` + suppression de l'ancienne table

###  NaT timestamps en JSON
**Erreur** : `invalid input syntax for type timestamp: "NaT"`  
**Solution** : `pdf.where(pdf.notna(), None)` avant la sérialisation JSON

### Left join streaming impossible
**Erreur** : Left join avec deux streams interdit par Spark  
**Solution** : `inner` join en streaming, `left` join conservé en mode batch
