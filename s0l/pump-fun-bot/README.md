# pump.fun trader

Research tooling for Solana pump.fun markets. The project listens to Yellowstone gRPC streams, decodes pump.fun, pump.fun AMM, Raydium Launchpad, and Raydium CPMM events, and stores normalized event data in TimescaleDB for analysis and strategy development.

## Features

- Decode create, buy, sell, complete, migration, swap, deposit, and withdraw events.
- Store event streams in PostgreSQL/TimescaleDB tables generated from typed event models.
- Analyze token history, market structure, and optimization runs from collected data.
- Keep manual sandbox trading scripts separate from the ingestion pipeline.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill `.env` with local RPC, gRPC, database, and optional notification credentials. Do not commit real keys or wallet material.

## Run Ingestion

```bash
uv run python data_store/pumpfun_grpc.py
```

The default config uses public-safe placeholders. For production-grade ingestion, provide a low-latency Solana stream endpoint and a TimescaleDB connection through environment variables.

## Docker

### Connect To Docker Image

```bash
docker ps
docker exec -it <image> bash
```

### Restart Container

```bash
docker start pumpfundata
```

### Connect To Docker DB

```bash
psql -d "postgres://postgres:<db_pw>@<db_ip>/<db>"
```

### Check Or Create Docker Volume

```bash
docker volume create pumpfundata
docker volume inspect pumpfundata
docker volume ls
docker volume rm <volname>
```

### Copy Data From Docker

```bash
docker ps -a
docker start <container_id>
docker cp <container_id>:/home/postgres/pgdata/data /tmp/pfdata
```

### Check Docker Logs

```bash
docker container ls -a
docker container logs <id>
```

### Get Bash Inside Docker

```bash
docker exec -it <container_id> bash
```

## TimescaleDB

### Install

https://docs.timescale.com/self-hosted/latest/install/installation-docker/

### Run TimescaleDB With Docker Volume

```bash
docker run -d --name pumpfundata -p 5432:5432 -e POSTGRES_PASSWORD=postgres -v pfdata:/var/lib/postgresql/data timescale/timescaledb-ha:pg17
```

### Check DB Size

```bash
docker volume inspect pumpfundata
du -sh <Mountpoint>
```

## Export And Import DB Data

### Dump All DB Data

```bash
docker exec <container_id> pg_dump -U postgres -Fc postgres > db_dumps/backup.dump
```

### Dump Only Specific Tables

#### v10_* from postgres

```bash
TABLES=$(docker exec pumpfundata psql -U postgres -d postgres -t -A -c \
"SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'v10_%';")

for tbl in $TABLES; do
    TABLE_ARGS+=" --table=public.\"$tbl\""
done

docker exec pumpfundata pg_dump -U postgres -Fc postgres $TABLE_ARGS > db_dumps/20250412_v10_tables.dump
```

#### v00_ from pfamm

```bash
TABLES=$(docker exec pumpfundata psql -U postgres -d pfamm -t -A -c \
"SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'v00_%';")

for tbl in $TABLES; do
    TABLE_ARGS+=" --table=public.\"$tbl\""
done

docker exec pumpfundata pg_dump -U postgres -Fc pfamm $TABLE_ARGS > db_dumps/20250412_v00_pfamm_tables.dump
```

### Start Local DB

```bash
docker volume create pfdata
docker run -d --name pumpfundata -p 5432:5432 -e POSTGRES_PASSWORD=postgres -v pfdata:/var/lib/postgresql/data timescale/timescaledb-ha:pg17
```

### Restore Exported DB Dump

```bash
docker exec -i pumpfundata pg_restore -U postgres -d postgres --disable-triggers --verbose < ./db_dumps/backup.dump
```

### Table Indexing

Indexes improve large event-table queries, especially filters such as `WHERE mint = ...` or `WHERE pool_pc_token_account = ...`.

```bash
uv run python data_store/db_create_index.py
```

## Links

### Python pump.fun Decode

https://github.com/chainstacklabs/pump-fun-bot

## TODO

### Identify Rugs

https://neo.bullx.io/terminal?chainId=1399811149&address=GKz1sWjZ52hXpQQodQVRp5H9hrHdbgPTLVguZ6a7pump

## Convert IDL To Legacy Format

- Download IDL from https://solscan.io/account/pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA#programIdl
- Run `utils/idl_converter.py` with proper paths.

## Profiler

```bash
uv run -m cProfile -o profile.out trader/nautilus/data_catalog_handler.py
uv run snakeviz profile.out
```
