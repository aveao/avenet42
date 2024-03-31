## avenet42

An attempt to make a full-featured (similar to [aranet4](https://aranet.com/products/aranet4/)) while also being more budget friendly (60-100eur).

Written in micropython, initally because of the ease of development, and later for the fun challenge of memory management.

![a picture of avenet42](.repo_assets/avenet42.jpg)

### features

- wifi: can upload data points to influxdb over wifi. also has an optional webserver that makes data available over wifi in both a generic json and in the prometheus text-based exposition format. the json can be used with home assistant, just add [homeassistant_configuration.yaml](/homeassistant_configuration.yaml) to your `configuration.yaml` (change the IP accordingly).
- bluetooth: can fetch data over bluetooth. a simple web ui using webbluetooth is available, see `btweb/` for more info. can be used with esphome, see [esphome-avenet42.yaml](/esphome-avenet42.yaml) for more info.
- screen: supports grayscale waveshare e-ink displays (tested with 1.33in v2).
- local logging: optionally, the sensor data can be stored on flash to be fetched later, for example to save pressure data during a flight.

### building your own

See [BUILDING.md](BUILDING.md) for wiring and flashing instructions. I'll design a PCB eventually.

### general TODOs (will be moved to issues eventually)

- tools/helper_convertfont: make an adj tool to generate font pngs from font files
- hw: battery
- hw: case
- web: make btweb UI available over web
- web: get/set config over web (with some amount of auth)
- btweb: service workers for UI to work offline
- btweb: better UI
- btweb: cleaner code
- btweb: account for losing focus
- btweb: fix disconnect button
- btweb: complex comms to read config
- micropython: complex comms to read config
