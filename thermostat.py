import os
import time
import uuid
import hmac
import hashlib
import base64
import requests
from Adafruit_IO import Client
import datetime
import pytz  # Ensure pytz is installed in your environment

def run():
    try:
        # SwitchBot API credentials
        SWITCHBOT_TOKEN = os.environ['SWITCHBOT_TOKEN']
        SWITCHBOT_SECRET = os.environ['SWITCHBOT_SECRET']

        # Adafruit IO credentials
        ADAFRUIT_IO_USERNAME = os.environ['ADAFRUIT_IO_USERNAME']
        ADAFRUIT_IO_KEY = os.environ['ADAFRUIT_IO_KEY']

        # Initialize Adafruit IO REST client
        aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

        # Step 0: Check if System is Active
        system_state = aio.receive('veach-thermostat-status').value.upper()
        print(f'System State: {system_state}')
        if system_state != 'ON':
            print('Thermostat system is turned OFF via veach-thermostat-status feed.')
            return  # Exit the script without running thermostat logic
        else:
            print('Thermostat system is turned ON.')

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
        response.raise_for_status()
        devices = response.json()['body']

        # **Print all infrared remote devices to verify device IDs**
        print("Infrared Remote Devices:")
        for device in devices['infraredRemoteList']:
            print(f"Name: {device['deviceName']}, ID: {device['deviceId']}, Type: {device['remoteType']}")

        # Find Hub 2 device ID
        hub_device_id = None
        for device in devices['deviceList']:
            if device['deviceType'] == 'Hub 2':
                hub_device_id = device['deviceId']
                break

        if not hub_device_id:
            print('Hub 2 not found.')
            return

        # Replace 'Your Heater Name' with the exact name of your heater
        HEATER_NAME = 'Lasko Heater '  # Update this as needed

        # Find heater device ID
        heater_device_id = None
        for device in devices['infraredRemoteList']:
            device_name = device['deviceName']
            if device_name.lower() == HEATER_NAME.lower():
                heater_device_id = device['deviceId']
                break

        if not heater_device_id:
            print(f"Heater '{HEATER_NAME}' not found.")
            return

        # Proceed with thermostat logic

        # Step 2: Get current temperature from Hub 2
        response = requests.get(f'{BASE_URL}/devices/{hub_device_id}/status', headers=headers)
        response.raise_for_status()
        status = response.json()['body']
        current_temp_c = status['temperature']
        print(f'Current Temperature: {current_temp_c}°C')

        # Convert current temperature to Fahrenheit for display
        current_temp_f = current_temp_c * 9 / 5 + 32
        print(f'Current Temperature: {current_temp_f:.1f}°F')

        # **Send current temperature to Adafruit IO**
        aio.send('current-temperature', current_temp_f)
        print('Current temperature sent to Adafruit IO.')

        # Step 3: Get temperature setpoint from Adafruit IO (in Fahrenheit)
        setpoint_f = float(aio.receive('temperature-setpoint').value)
        print(f'Temperature Setpoint: {setpoint_f}°F')

        # Adjust setpoint during morning hours
        # Get current time in California timezone
        pacific_tz = pytz.timezone('America/Los_Angeles')
        current_time_pacific = datetime.datetime.now(pacific_tz)
        print(f'Current Time in California: {current_time_pacific.strftime("%Y-%m-%d %H:%M:%S")}')

        # Check if current time is between 6 am and 8 am
        if 6 <= current_time_pacific.hour < 8:
            setpoint_f += 5
            print('Morning hours detected. Increased setpoint by 5°F.')
        else:
            print('Regular hours. Setpoint remains unchanged.')

        # Convert setpoint to Celsius
        setpoint_c = (setpoint_f - 32) * 5 / 9
        print(f'Temperature Setpoint Converted to Celsius: {setpoint_c:.2f}°C')

        # Step 4: Get heater state from Adafruit IO
        heater_state = aio.receive('heater-state').value.upper()
        print(f'Current Heater State: {heater_state}')

        # Define temperature tolerance (in Celsius)
        temp_tolerance = 0.5  # degrees Celsius

        # Step 5: Thermostat logic with heater state tracking
        if current_temp_c < setpoint_c - temp_tolerance:
            # Desired state: Heater should be ON
            if heater_state != 'ON':
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
                response.raise_for_status()
                print('Heater turned ON.')
                # Update heater state in Adafruit IO
                aio.send('heater-state', 'ON')
            else:
                print('Heater is already ON. No action needed.')
        elif current_temp_c > setpoint_c + temp_tolerance:
            # Desired state: Heater should be OFF
            if heater_state != 'OFF':
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
                response.raise_for_status()
                print('Heater turned OFF.')
                # Update heater state in Adafruit IO
                aio.send('heater-state', 'OFF')
            else:
                print('Heater is already OFF. No action needed.')
        else:
            print('Temperature within setpoint range. No action needed.')

        # Log the action
        print(f"{current_time_pacific.strftime('%Y-%m-%d %H:%M:%S')}: Current Temp={current_temp_c}°C ({current_temp_f:.1f}°F), Setpoint={setpoint_c:.2f}°C ({setpoint_f}°F), Heater State={heater_state}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        exit(1)  # Exit with non-zero status code to indicate failure

if __name__ == '__main__':
    run()
