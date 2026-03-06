A MacOs menubar widget that checks availability of a public car charger
=======

This repo contain one tool for checking a Equans charging location.

- `menubar_app/`: Native macOS menubar app (Swift) that polls the Grid API

## Requirements

- Swift 5.9+ (for the menubar app)

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
