# Laadpaal menubar app (macOS)

Native Swift menubar app that polls the Grid API every 15 minutes and displays
the status in the menu bar.

## Run locally

```
cd menubar_app
swift run
```

The app launches as a menu bar item. Open **Settings…** from the menu to set:

- Grid subscription key
- Location ID (default 674202)
- Update interval in seconds (default 900)

Extras:

- Uses a menubar icon instead of text
- Sends a notification when status flips from bezet to vrij
- Includes an "Open location" menu item

## Notes

- The key is stored in UserDefaults on your machine.
- The app uses the endpoint:
  `https://api.grid.com/charging/ChargingStations/location/{locationId}`
