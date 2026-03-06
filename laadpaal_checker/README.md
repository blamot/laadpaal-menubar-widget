# Laadpaal status checker (Python)

Lokaal script om de bezet/vrij-status van laadpunten te checken. Ondersteunt een
publieke API (Open Charge Map) of scraping als fallback.

## Installatie

```
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4
```

## Configuratie

Kopieer `config.example.json` naar `config.json` en vul de waarden in:

- `source.type`: `grid`, `openchargemap` of `scrape`
- `connectors`: map je eigen namen naar bron-IDs (of selectors bij scraping)
- `source.api_key`: vraag gratis aan bij Open Charge Map (indien API)
- `source.site_match`: tekst om de juiste locatie te vinden
- `source.params.latitude/longitude`: coördinaten van de laadpaal

### Grid API

Als je een `subscription_key` hebt, gebruik `type: "grid"` en zet de key in
`config.json` (niet in versiebeheer). Het script stuurt de key als
`Ocp-Apim-Subscription-Key` header.

Grid heeft meerdere endpoints. Je kunt ook het `Share` endpoint gebruiken door
`base_url` op `https://api.grid.com/app/v0.2/Share` te zetten en `params` te
vullen met `id`, `type` en `urlInfo`.

Voor detailinformatie per locatie kun je ook dit endpoint gebruiken (voorbeeld):

```
"source": {
  "type": "grid",
  "base_url": "https://api.grid.com/charging/ChargingStations/location/674202",
  "subscription_key": "SET-ME"
}
```

Voor dit detail-endpoint kun je in `connectors` één van deze mappings gebruiken:

- `location` of `location:<id>` voor de totale beschikbaarheid
- `charger:<chargerId>` voor een specifieke charger (als aanwezig)

Als je een 405 krijgt op `Share`, probeer een POST:

```
"source": {
  "type": "grid",
  "base_url": "https://api.grid.com/app/v0.2/Share",
  "method": "POST",
  "params_in_body": true,
  "params": {
    "id": "563901",
    "type": "ChargingLocation",
    "urlInfo": "EQUANS, Lissenvaart 96, Zoetermeer"
  }
}
```

### Scraping fallback

Als je geen API-bron vindt, gebruik dan `type: "scrape"` en vul selectors in:

```
{
  "source": {
    "type": "scrape",
    "page_url": "https://<kaartpagina>",
    "connector_selectors": {
      "SGHZ2-08068": "#connector-1 .status",
      "SGHZ": "#connector-2 .status"
    },
    "available_texts": ["available", "vrij"],
    "occupied_texts": ["occupied", "bezet", "in use"]
  }
}
```

Tip: open de kaartpagina in een browser, gebruik DevTools → Elements en zoek de
status-tekst om een stabiele CSS selector te bepalen.

## Gebruik

```
python check_status.py --config config.json
```

Cache is standaard 60 seconden. Gebruik `--no-cache` om altijd live te fetchen.

Bij Grid detaildata komt er ook een `summary` veld in de output, zoals `0/2 bezet`.

### Grid debug

Gebruik dit om de ruwe Grid response te zien (handig om connector IDs te vinden):

```
python check_status.py --config config.json --dump-grid
```

Bij het `Share` endpoint krijg je meestal `data.locations.markers`. Gebruik de
`id` uit elke marker als waarde in `connectors` (bijv. `"SGHZ2-08068": "674202"`).
