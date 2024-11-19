import os
import time
import uuid
import hmac
import hashlib
import base64
import requests
from dotenv import load_dotenv
from Adafruit_IO import Client

# Load environment variables from .env file
load_dotenv()

# SwitchBot API credentials
SWITCHBOT_TOKEN = os.getenv('SWITCHBOT_TOKEN')
SWITCHBOT_SECRET = os.getenv('SWITCHBOT_SECRET')

# Adafruit IO credentials
ADAFRUIT_IO_USERNAME = os.getenv('ADAFRUIT_IO_USERNAME')
ADAFRUIT_IO_KEY = os.getenv('ADAFRUIT_IO_KEY')

# Initialize Adafruit IO REST client
aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

# Function to generate SwitchBot API signature
def generate_signature(token, secret):
    nonce = uuid.uuid4()
    t = int(round(time.time() * 1000))
    string_to_sign = f'{token}{t}{nonce}'
    string_to_sign = bytes(string_to_sign, 'utf-8')
    secret = bytes(secret, 'utf-8')
    sign = base64.b64encode(
        hmac.new(secret, msg=string_to_sign, digestmod=hashlib.sha256).digest()
    )
    return {
        'Authorization': token,
        'Content-Type': 'application/json; charset=utf8',
        't': str(t),
        'sign': sign.decode('utf-8'),
        'nonce': str(nonce),
    }

# Generate API headers
headers = generate_signature(SWITCHBOT_TOKEN, SWITCHBOT_SECRET)

# Base URL for SwitchBot API
BASE_URL = 'https://api.switch-bot.com/v1.1'

# Step 1: Get device list
response = requests.get(f'{BASE_URL}/devices', headers=headers)
devices = response.json()['body']

# Find Hub 2 device ID
hub_device_id = None
for device in devices['deviceList']:
    if device['deviceType'] == 'Hub 2':
        hub_device_id = device['deviceId']
        break

if not hub_device_id:
    print('Hub 2 not found.')
    exit()

# Replace 'Your Heater Name' with the exact name of your heater as it appears in the SwitchBot app
HEATER_NAME = 'Lasko Heater '  # <-- Ensure this matches your heater's name

# Find heater device ID (with stripped spaces and case-insensitive comparison)
heater_device_id = None
for device in devices['infraredRemoteList']:
    device_name = device['deviceName'].strip().lower()
    if device_name == HEATER_NAME.strip().lower():
        heater_device_id = device['deviceId']
        break

if not heater_device_id:
    print(f"Heater '{HEATER_NAME}' not found.")
    print("Available Infrared Remote Devices:")
    for device in devices['infraredRemoteList']:
        print(f"- {device['deviceName']}")
    exit()

# Step 2: Get current temperature from Hub 2
response = requests.get(f'{BASE_URL}/devices/{hub_device_id}/status', headers=headers)
status = response.json()['body']
current_temp_c = status['temperature']
print(f'Current Temperature: {current_temp_c}°C')

# Convert current temperature to Fahrenheit for display
current_temp_f = current_temp_c * 9 / 5 + 32
print(f'Current Temperature: {current_temp_f:.1f}°F')

# Step 3: Get temperature setpoint from Adafruit IO (in Fahrenheit)
setpoint_f = float(aio.receive('temperature-setpoint').value)
print(f'Temperature Setpoint: {setpoint_f}°F')

# Convert setpoint to Celsius
setpoint_c = (setpoint_f - 32) * 5 / 9
print(f'Temperature Setpoint Converted to Celsius: {setpoint_c:.2f}°C')

# Define temperature tolerance (to prevent frequent on/off)
temp_tolerance = 0.5  # degrees Celsius

# Step 4: Thermostat logic
if current_temp_c < setpoint_c - temp_tolerance:
    # Turn on the heater
    command = {
        'command': 'Power ',
        'parameter': 'default',
        'commandType': 'customize'
    }
    response = requests.post(
        f'{BASE_URL}/devices/{heater_device_id}/commands',
        headers=headers,
        json=command
    )
    print('Heater turned ON.')
elif current_temp_c > setpoint_c + temp_tolerance:
    # Turn off the heater
    command = {
        'command': 'Power ',
        'parameter': 'default',
        'commandType': 'customize'
    }
    response = requests.post(
        f'{BASE_URL}/devices/{heater_device_id}/commands',
        headers=headers,
        json=command
    )
    print('Heater turned OFF.')
else:
    print('Heater state unchanged.')

# Optional: Log the action
with open('thermostat_log.txt', 'a') as log_file:
    log_file.write(f"{time.asctime()}: Current Temp={current_temp_c}°C ({current_temp_f:.1f}°F), Setpoint={setpoint_c:.2f}°C ({setpoint_f}°F)\n")
