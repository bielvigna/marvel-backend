# Gameplay API

Serviço online separado do `backend-ai`. Firebase Authentication identifica jogadores; PostgreSQL guarda perfis, amizades, desafios e partidas; Redis atende fila de matchmaking, presença e cache curto do catálogo. O backend de gameplay é autoritativo para equipes, turnos e resultados.

## Configuração local

1. Copie `.env.example` para `.env` e ajuste `DATABASE_URL`, `FIREBASE_PROJECT_ID` e `CHARACTER_API_BASE_URL`. Para habilitar upload assinado de avatar, configure `CLOUDINARY_API_SECRET` somente no backend. O backend aceita as credenciais REST da Upstash (`UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`); alternativamente, configure `REDIS_URL` com a conexão Redis TCP (`redis://` ou `rediss://`). Quando as variáveis REST estão preenchidas, elas têm prioridade. O cliente HTTP da Upstash suporta também os scripts Lua atômicos usados pela fila de matchmaking.
2. Configure credenciais do Firebase Admin por Application Default Credentials ou `FIREBASE_CREDENTIALS_PATH`. A chave de serviço não deve entrar no repositório.
3. Inicie PostgreSQL e Redis. O arquivo `docker-compose.test.yml` serve somente para dependências de teste local; portas `55432` e `56379` são isoladas das portas padrão.
4. Instale `requirements-dev.txt`, aplique `alembic upgrade head` e inicie o servidor:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8090
   ```

O catálogo consultado em `CHARACTER_API_BASE_URL` é o `backend-ai`. Seus dados de poderes são mapeados para os tipos usados pelo combate e cacheados no Redis por 24 horas. O servidor nunca aceita HP, tipo, dano ou resultado de batalha enviados pelo cliente.

## API

- `GET /health/live` e `GET /health/ready`
- `GET/PATCH /v1/profile/me`
- `POST /v1/profile/avatar-signature` (autenticado; assina uma foto para o caminho de avatar associado ao jogador)
- `GET /v1/friends`, `GET /v1/friends/search`, `GET/POST /v1/friend-requests`
- `GET/POST /v1/challenges` e `POST /v1/challenges/{id}/accept|decline`
- `POST/GET/DELETE /v1/matchmaking/queue`
- `GET /v1/matches/{id}`, `PUT /v1/matches/{id}/teams`, `POST /v1/matches/{id}/actions`

`POST /v1/matchmaking/queue` pode retornar `waiting` ou `matched`; enquanto aguarda, o cliente consulta `GET` na mesma rota. A partida começa quando ambos enviam equipes de três personagens. Ações incluem `attack`, `ability`, `defend`, `switch` e `use_item`; cada ação leva `action_id` para repetição idempotente e `expected_version` para detectar estado desatualizado.

## Testes e migrações

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app tests alembic
.\.venv\Scripts\alembic.exe upgrade head
```

Por padrão, os testes usam SQLite temporário e FakeRedis. Para executar a mesma suíte contra PostgreSQL e Redis reais, inicie `docker compose -f docker-compose.test.yml up -d --wait` e configure as variáveis abaixo no PowerShell. Isso apaga/recria as tabelas e limpa o banco Redis de teste a cada teste; use somente o banco e Redis dedicados definidos pelo compose.

```powershell
$env:GAMEPLAY_TEST_DATABASE_URL = "postgresql+asyncpg://gameplay_test:gameplay_test@localhost:55432/gameplay_test"
$env:GAMEPLAY_TEST_REDIS_URL = "redis://localhost:56379/0"
.\.venv\Scripts\python.exe -m pytest
Remove-Item Env:GAMEPLAY_TEST_DATABASE_URL
Remove-Item Env:GAMEPLAY_TEST_REDIS_URL
```
