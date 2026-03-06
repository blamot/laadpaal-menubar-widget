<<<<<<< HEAD
# laadpaal-menubar-widget
A MacOs menubar widget that checks availability of a public car charger
=======
# Laadpaal status tools

This repo contains two tools for checking the Equans charging location at
Lissenvaart 96 (Zoetermeer):

- `laadpaal_checker/`: Python CLI that fetches Grid API status
- `menubar_app/`: Native macOS menubar app (Swift) that polls the Grid API

## Requirements

- Python 3.10+ (for the CLI)
- Swift 5.9+ (for the menubar app)

## Python CLI

Setup:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r laadpaal_checker/requirements.txt
```

Configure:

```
cp laadpaal_checker/config.example.json laadpaal_checker/config.json
```

Edit `laadpaal_checker/config.json` and set:

- `subscription_key` (Grid key)

Run:

```
python laadpaal_checker/check_status.py --config laadpaal_checker/config.json
```

## macOS menubar app

Run locally:

```
cd menubar_app
swift run
```

Open the menu bar item → **Settings…** and set:

- Grid subscription key
- Location ID (default 674202)
- Update interval (default 900 seconds)

Notes:

- Notifications only work when the app is packaged as a `.app` bundle.
- The menubar app uses the endpoint:
  `https://api.grid.com/charging/ChargingStations/location/{locationId}`

## Security

Your Grid subscription key should never be committed. This repo ignores
`laadpaal_checker/config.json`. The menubar app stores the key in UserDefaults
on your machine.
>>>>>>> c71e3ff (Add charging tools and menubar app)
