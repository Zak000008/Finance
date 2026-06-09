# Le mie Finanze

App personale per gestire transazioni, obiettivi, storico saldo, report CSV e analisi AI.

Il backend Python serve sia le API sia il frontend statico in `app/`. I dati vengono salvati in SQLite.

## Avvio locale

```bash
python3 backend/server.py
```

Poi apri:

```text
http://127.0.0.1:8000
```

Di default il database locale viene creato in:

```text
data/finanze.sqlite
```

Puoi cambiare configurazione copiando `.env.example` in `.env` e impostando le variabili necessarie.

## Variabili d'ambiente

| Variabile | Uso |
| --- | --- |
| `PORT` | Porta usata da Render. Ha priorità su `FINANZE_PORT`. |
| `FINANZE_HOST` | Host del server. In locale default `127.0.0.1`, su Render `0.0.0.0`. |
| `FINANZE_PORT` | Porta locale, default `8000`. |
| `FINANZE_DB_PATH` | Percorso del file SQLite. Su Render deve puntare al disco persistente. |
| `FINANZE_AUTH_USER` | Utente per la protezione Basic Auth, default `finanze`. |
| `FINANZE_APP_PASSWORD` | Se impostata, protegge l'app pubblica con password. |
| `OPENROUTER_API_KEY` | Chiave per `POST /api/ai/analisi`. |
| `OPENROUTER_MODEL` | Modello OpenRouter, default consigliato `openrouter/free`. |
| `OPENROUTER_URL` | Endpoint OpenRouter, opzionale. |

## Deploy su Render

Il file `render.yaml` prepara un Web Service Python con:

- runtime Python
- regione `frankfurt`
- health check su `/api/health`
- start command `python backend/server.py`
- disco persistente montato su `/var/data`
- database SQLite in `/var/data/finanze.sqlite`

Render richiede che il server ascolti su `0.0.0.0` e sulla porta indicata da `PORT`; il backend lo fa automaticamente.

### Passi

1. Carica il progetto su GitHub o GitLab.
2. Su Render crea un nuovo Blueprint usando questo repository.
3. Durante la creazione imposta i secret richiesti:
   - `FINANZE_APP_PASSWORD`
   - `OPENROUTER_API_KEY`, se vuoi usare l'analisi AI
4. Completa il deploy.
5. Apri l'URL pubblico `https://...onrender.com`.

Nota: il disco persistente richiede un servizio Render a pagamento. Senza disco persistente, i dati SQLite non sopravvivono a restart e redeploy.

## Migrazione del database esistente

Il database locale reale non va pubblicato nel repository. Dopo il primo deploy, trasferiscilo una sola volta sul disco persistente Render:

```bash
scp -s data/finanze.sqlite YOUR_SERVICE@ssh.YOUR_REGION.render.com:/var/data/finanze.sqlite
```

In alternativa, usa la Shell di Render con Magic Wormhole:

```bash
wormhole receive
```

e salva il file ricevuto come:

```text
/var/data/finanze.sqlite
```

Dopo il trasferimento, riavvia il servizio Render.

## Test

```bash
python3 tests/test_salvataggio.py
python3 tests/test_transazioni_crud.py
python3 tests/test_obiettivi_crud.py
python3 tests/test_storico_periodi.py
python3 tests/test_export_csv.py
```

## AI (OpenRouter)

Per usare l'endpoint `POST /api/ai/analisi`, imposta nel backend:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_URL` opzionale, default `https://openrouter.ai/api/v1/chat/completions`
