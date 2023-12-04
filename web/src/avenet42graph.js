import Chart from 'chart.js/auto'

let decoder = new TextDecoder('utf-8');
let encoder = new TextEncoder('utf-8');
var co2chart;
var tempchart;
var rhchart;
var pressurealtchart;
var device;
var server;
var load_history = true;
var attempt_reconnect = true;
var connected = false;
var show_config = false;
const chart_x_max = 50;
const configdiv = document.querySelector("#configdiv");
const chartdiv = document.querySelector("#chartdiv");
const dis_connectbutton = document.querySelector('#dis_connectbutton');
const co2display = document.querySelector('#co2display');
const tempdisplay = document.querySelector('#tempdisplay');
const rhdisplay = document.querySelector('#rhdisplay');
const pressuredisplay = document.querySelector('#pressuredisplay');
const elevationdisplay = document.querySelector('#elevationdisplay');
const configbox = document.querySelector('#configbox');

async function main() {
  Chart.defaults.font.size = 16;
  Chart.defaults.backgroundColor = 'rgba(255, 255, 255, 0.1)';
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.2)';
  Chart.defaults.color = '#FFFFFF';
  Chart.defaults.plugins.tooltip.intersect = false;
  Chart.defaults.elements.point.radius = 4;
  Chart.defaults.elements.point.hoverRadius = 5;
  co2chart = new Chart(
    document.getElementById('co2graph'),
    {
      type: 'line',
      responsive: true,
      options: {
        maintainAspectRatio: false,
        plugins: {
            tooltip: {
                callbacks: {
                    label: (item) =>
                        `${item.dataset.label}: ${item.formattedValue}ppm`,
                },
            },
        },
      },
      animation: {     
        y: {
          duration: 0 
        }
      },
      data: {
        labels: [],
        datasets: [
          {
            label: 'CO2',
            data: [],
            borderColor: '#36A2EB',
            backgroundColor: '#36A2EB',
          }
        ]
      }
    }
  );
  tempchart = new Chart(
    document.getElementById('tempgraph'),
    {
      type: 'line',
      responsive: true,
      options: {
        maintainAspectRatio: false,
        plugins: {
            tooltip: {
                callbacks: {
                    label: (item) =>
                        `${item.dataset.label}: ${item.formattedValue}°C`,
                },
            },
        },
      },
      animation: {     
        y: {
          duration: 0 
        }
      },
      data: {
        labels: [],
        datasets: [
          {
            label: 'Temperature',
            data: [],
            borderColor: '#ff780a',
            backgroundColor: '#ff780a',
          }
        ]
      }
    }
  );
  rhchart = new Chart(
    document.getElementById('rhgraph'),
    {
      type: 'line',
      responsive: true,
      options: {
        maintainAspectRatio: false,
        plugins: {
            tooltip: {
                callbacks: {
                    label: (item) =>
                        `${item.dataset.label}: ${item.formattedValue}%`,
                },
            },
        },
      },
      animation: {     
        y: {
          duration: 0 
        }
      },
      data: {
        labels: [],
        datasets: [
          {
            label: 'Relative Humidity',
            data: [],
            borderColor: '#568f4f',
            backgroundColor: '#568f4f',
          }
        ]
      }
    }
  );
  pressurealtchart = new Chart(
    document.getElementById('pressurealtgraph'),
    {
      type: 'line',
      responsive: true,
      options: {
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
              callbacks: {
                label: (item) =>
                    `${item.dataset.label}: ${item.formattedValue}Pa`,
                footer: function(tooltipItems) {
                    return "Altitude: " + pa_to_elevation(tooltipItems[0].parsed.y).toFixed(2) + "m";
                }
            }
          }
        }
      },
      animation: {     
        y: {
          duration: 0 
        }
      },
      data: {
        labels: [],
        datasets: [
          {
            label: 'Pressure',
            data: [],
            borderColor: '#f2cc0c',
            backgroundColor: '#f2cc0c',
          }
        ]
      }
    }
  );
}

function format_time(date_int) {
    let date_obj = new Date(date_int);
    return date_obj.toJSON().substr(11, 8);
}

export async function connect_disconnect_button() {
    if (connected) {
        await start_disconnect();
    } else {
        await start_connect();
    }
}

export async function toggle_config_button() {
    show_config = !show_config;
    chartdiv.style.display = show_config ? "none" : "flex";
    configdiv.style.display = show_config ? "flex" : "none";
}

function rename_dis_connect_button() {
    dis_connectbutton.innerText = connected ? "disconnect" : "connect";
}

function pa_to_elevation(pa) {
    return 44330.0 * (1.0 - (((pa / 100) / 1013.25) ** 0.1903))
}

export async function start_connect() {
    device = null;
    attempt_reconnect = true;
    try {
      device = await navigator.bluetooth.requestDevice({filters: [{name: ['avenet42']}], optionalServices: ["environmental_sensing"]});
      device.addEventListener('gattserverdisconnected', connect);
      connect();
    } catch(error) {
      console.log('Argh! ' + error);
    }
}

export async function start_disconnect() {
    attempt_reconnect = false;
    await device.gatt.disconnect();
}

async function connect() {
  exponentialBackoff(10 /* max retries */, 5 /* seconds delay */,
    async function toTry() {
      console.log('Connecting to Bluetooth Device... ');
      server = await device.gatt.connect();
    },
    async function success() {
      console.log('> Bluetooth Device connected.');
      connected = true;
      rename_dis_connect_button();
      let service = await server.getPrimaryService('environmental_sensing');

      if (load_history) {
          let co2_historic_characteristic = await service.getCharacteristic('00006969-0000-1000-8000-00805f9b34fb');
          let co2_historic_value = await co2_historic_characteristic.readValue();
          console.log("co2_historic_value:", co2_historic_value);

          var sleep_time = Boolean(co2_historic_value.getInt8(0)) ? 30 : 5;
          console.log("sleep_time:", sleep_time)

          var data = [];
          var datapoint_count = (co2_historic_value.byteLength - 1) / 2;
          console.log("datapoint_count:", datapoint_count);
          for (let i = 0; i < datapoint_count; i++) {
            var co2_value = co2_historic_value.getUint16((i * 2) + 1);
            if (co2_value == 0) {
                continue;
            }
            var data_time = Date.now() - ((datapoint_count - i) * 1000 * sleep_time);
            addData(co2chart, format_time(data_time), co2_value);
          }
          load_history = false;
      }

      let co2_characteristic = await service.getCharacteristic('00002b8c-0000-1000-8000-00805f9b34fb');
      await co2_characteristic.startNotifications();
      co2_characteristic.addEventListener('characteristicvaluechanged', handle_co2_notifs);

      let temp_characteristic = await service.getCharacteristic('temperature');
      await temp_characteristic.startNotifications();
      temp_characteristic.addEventListener('characteristicvaluechanged', handle_temp_notifs);

      let rh_characteristic = await service.getCharacteristic('humidity');
      await rh_characteristic.startNotifications();
      rh_characteristic.addEventListener('characteristicvaluechanged', handle_rh_notifs);

      let pressure_characteristic = await service.getCharacteristic('pressure');
      await pressure_characteristic.startNotifications();
      pressure_characteristic.addEventListener('characteristicvaluechanged', handle_pressure_notifs);
    },
    function fail() {
      console.log('Failed to reconnect.');
      connected = false;
      rename_dis_connect_button();
    });
}

function onDisconnected() {
  console.log('> Bluetooth Device disconnected');
  connected = false;
  rename_dis_connect_button();
  if (attempt_reconnect) {
    connect();
  }
}

function handle_co2_notifs(event) {
    let value = event.target.value.byteLength == 2 ? event.target.value.getUint16(0, true) : decoder.decode(event.target.value);
    const current_time = Date.now();
    addData(co2chart, format_time(current_time), value);
    if (co2chart.data.labels.length > chart_x_max) {
        removeData(co2chart);
    }
    co2display.innerHTML = "<b>CO2:</b> " + value + "ppm";
}

function handle_temp_notifs(event) {
    let value = event.target.value.getUint16(0, true) / 100;
    const current_time = Date.now();
    addData(tempchart, format_time(current_time), value);
    if (tempchart.data.labels.length > chart_x_max) {
        removeData(tempchart);
    }
    tempdisplay.innerHTML = "<b>Temp:</b> " + value + "°C";
}

function handle_rh_notifs(event) {
    let value = event.target.value.getUint16(0, true) / 100;
    const current_time = Date.now();
    addData(rhchart, format_time(current_time), value);
    if (rhchart.data.labels.length > chart_x_max) {
        removeData(rhchart);
    }
    rhdisplay.innerHTML = "<b>Relative Humidity:</b> " + value + "%";
}

function handle_pressure_notifs(event) {
    let value = event.target.value.getUint32(0, true) / 10;
    let elevation_m = pa_to_elevation(value).toFixed(2);
    const current_time = Date.now();
    addData(pressurealtchart, format_time(current_time), value);
    if (pressurealtchart.data.labels.length > chart_x_max) {
        removeData(pressurealtchart);
    }
    pressuredisplay.innerHTML = "<b>Pressure:</b> " + value + "Pa";
    elevationdisplay.innerHTML = "<b>Elevation:</b> " + elevation_m + "m";
}

async function exponentialBackoff(max, delay, toTry, success, fail) {
    if (!attempt_reconnect) {
        return;
    }
  try {
    const result = await toTry();
    await success(result);
  } catch(error) {
    if (max === 0) {
      return fail();
    }
    console.log('Retrying in ' + delay + 's... (' + max + ' tries left) error:', error);
    setTimeout(function() {
      exponentialBackoff(--max, delay * 2, toTry, success, fail);
    }, delay * 1000);
  }
}

function addData(chart, label, data) {
    chart.data.labels.push(label);
    chart.data.datasets[0].data.push(data);
    chart.update();
}

function removeData(chart) {
    chart.data.labels.shift();
    chart.data.datasets.forEach((dataset) => {
        dataset.data.shift();
    });
    chart.update();
}

export function apply_debug_level() {
    let config_json = JSON.parse(configbox.value);
    config_json["debug_level"] = parseInt(document.querySelector('#debug_level_input').value);
    configbox.value = JSON.stringify(config_json);
}

export function apply_local_logs() {
    let selected_option_objs = document.querySelector("#local_logs_input").selectedOptions;
    let config_json = JSON.parse(configbox.value);
    config_json["logs"] = Array.from(selected_option_objs).map(({ value }) => value);
    configbox.value = JSON.stringify(config_json);
}

export function apply_co2_history_size() {
    let config_json = JSON.parse(configbox.value);
    config_json["history_size"] = parseInt(document.querySelector('#co2_history_size_input').value);
    configbox.value = JSON.stringify(config_json);
}

export function apply_wlan() {
    let config_json = JSON.parse(configbox.value);
    config_json["wlan"] = {
        "ssid": document.querySelector('#wlan_ssid_input').value,
        "password": document.querySelector('#wlan_password_input').value,
        "connection_wait_s": document.querySelector('#wlan_connection_wait_s_input').value,
    };
    configbox.value = JSON.stringify(config_json);
}

export function apply_bt() {
    let config_json = JSON.parse(configbox.value);
    config_json["bluetooth"] = {
        "name": document.querySelector('#bt_name_input').value,
        "advertisement_freq_us": document.querySelector('#bt_advertisement_freq_us_input').value,
    };
    configbox.value = JSON.stringify(config_json);
}

export function apply_scd41() {
    let config_json = JSON.parse(configbox.value);
    config_json["scd41"] = {
        "low_power": document.querySelector('#scd41_low_power_input').checked,
        "asc": document.querySelector('#scd41_asc_input').checked,
    };
    configbox.value = JSON.stringify(config_json);
}

export function apply_bmp180() {
    let config_json = JSON.parse(configbox.value);
    config_json["bmp180"] = {
        "upper_pressure": parseInt(document.querySelector('#bmp180_upper_pressure_input').value),
        "lower_pressure": parseInt(document.querySelector('#bmp180_lower_pressure_input').value),
        "oversampling": parseInt(document.querySelector('#bmp180_oversampling_input').value),
        "oversampling_wlan": parseInt(document.querySelector('#bmp180_oversampling_wlan_input').value),
    };
    configbox.value = JSON.stringify(config_json);
}

export function apply_influx() {
    let config_json = JSON.parse(configbox.value);
    config_json["influx"] = {
        "host": document.querySelector('#influx_host_input').value,
        "bucket": document.querySelector('#influx_bucket_input').value,
        "username": document.querySelector('#influx_username_input').value,
        "password": document.querySelector('#influx_password_input').value,
        "datapoint": document.querySelector('#influx_datapoint_input').value,
    };
    configbox.value = JSON.stringify(config_json);
}

export async function send_config() {
    if (!connected) {
        return;
    }
    let service = await server.getPrimaryService('environmental_sensing');
    let config_characteristic = await service.getCharacteristic('00006970-0000-1000-8000-00805f9b34fb');
    console.log(configbox.value, encoder.encode(configbox.value), decoder.decode(encoder.encode(configbox.value)));
    await config_characteristic.writeValue(encoder.encode(configbox.value))
}


window.connect_disconnect_button = connect_disconnect_button;
window.toggle_config_button = toggle_config_button;
window.apply_debug_level = apply_debug_level;
window.apply_local_logs = apply_local_logs;
window.apply_co2_history_size = apply_co2_history_size;
window.apply_wlan = apply_wlan;
window.apply_bt = apply_bt;
window.apply_scd41 = apply_scd41;
window.apply_bmp180 = apply_bmp180;
window.apply_influx = apply_influx;
window.send_config = send_config;
main();
