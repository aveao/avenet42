## avenet42

An attempt to make a full-featured (similar to [aranet4](https://aranet.com/products/aranet4/)) while also being more budget friendly (60-100eur).

Written in micropython, initally because of the ease of development, and later for the fun challenge of memory management.

![a picture of avenet42](.repo_assets/avenet42.jpg)

### features

- wifi: can upload data points to influxdb over wifi.
- bluetooth: can fetch data over bluetooth. a simple web ui using webbluetooth is available, see `web/` for more info. can be used with esphome, see [esphome-avenet42.yaml](/esphome-avenet42.yaml) for more info.
- screen: supports grayscale waveshare e-ink displays (tested with 1.33in v2).
- local logging: optionally, the sensor data can be stored on flash to be fetched later, for example to save pressure data during a flight.

### building your own

See [BUILDING.md](BUILDING.md) for wiring and flashing instructions. I'll design a PCB eventually.

### general TODOs (will be moved to issues eventually)

- tools/helper_convertfont: make an adj tool to generate font pngs from font files
- hw: battery
- hw: case
- web: service workers for UI to work offline
- web: better UI
- web: cleaner code
- web: account for losing focus
- web: fix disconnect button
- web: complex comms to read config
- micropython: complex comms to read config
