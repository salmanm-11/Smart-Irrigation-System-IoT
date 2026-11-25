import serial
import time
import joblib
import pandas as pd
import serial.tools.list_ports

# -------------------- SERIAL SETUP --------------------
print("🔍 Available Ports:")
for port in serial.tools.list_ports.comports():
    print(port.device, "-", port.description)

# Arduino @9600 (sensors + relay)
arduino = serial.Serial('COM5', 9600, timeout=1)
time.sleep(2)
# NodeMCU @115200 (IoT)
def connect_nodemcu():
    try:
        nodemcu = serial.Serial('COM6', 115200, timeout=1)
        time.sleep(2)
        print("✅ NodeMCU connected")
        return nodemcu
    except Exception as e:
        print("⚠️ NodeMCU connection failed:", e)
        return None

nodemcu = connect_nodemcu()
time.sleep(2)

# -------------------- LOAD ML MODEL --------------------
try:
    model = joblib.load("pump_model_highacc.pkl")
    print("✅ ML Model loaded")
except Exception:
    print("⚠️ No model found, fallback to rule-based")
    model = None

# -------------------- ML DECISION --------------------
def decide_pump(soil_percent, temp, hum, solar_percent):
    if model:
        X = pd.DataFrame([[soil_percent, temp, hum, solar_percent]],
                         columns=["Soil", "Temp", "Hum", "Solar"])
        prediction = model.predict(X)[0]
        proba = model.predict_proba(X)[0][1]
        return ("ON" if prediction == 1 else "OFF"), proba
    else:
        return ("ON" if soil_percent < 40 else "OFF"), 0.0

# -------------------- MAIN LOOP --------------------
try:
    while True:
        if arduino.in_waiting > 0:
            line = arduino.readline().decode('utf-8').strip()

            if not line.startswith("SOIL"):
                continue

            try:
                parts = line.split(',')
                soil_percent = int(parts[1])
                temp = int(parts[3])
                hum = int(parts[5])
                solar_adc = int(parts[7])
            except (IndexError, ValueError):
                print("⚠️ Bad data from Arduino:", line)
                continue

            solar_percent = (solar_adc / 1023.0) * 100.0

            # ---------------- PRESENT DATA ----------------
            print("\n===== PRESENT DATA =====")
            print(f"Soil Moisture: {soil_percent}%")
            print(f"Temperature : {temp}°C")
            print(f"Humidity    : {hum}%")
            print(f"Solar Inten.: {solar_percent:.1f}%")

            # ---------------- FUTURE (ML PREDICTION) ----------------
            pump_cmd, proba = decide_pump(soil_percent, temp, hum, solar_percent)
            print("\n===== FUTURE PREDICTION (ML) =====")
            print(f"Predicted Pump State: {pump_cmd}")
            print(f"Confidence (ON): {proba:.2f}")

            # ---------------- COMPARISON ----------------
            print("\n===== COMPARISON =====")
            if pump_cmd == "ON":
                print("➡️  Based on current soil dryness, the pump will be TURNED ON.")
            else:
                print("➡️  Soil is sufficient, pump will remain OFF.")

            # Send command to Arduino
            arduino.write((pump_cmd + "\n").encode())
            print(f"✔️ Sent Pump Command to Arduino: {pump_cmd}")

            # ---------------- SEND TO NODEMCU ----------------
            data_packet = f"SOIL,{soil_percent},TEMP,{temp},HUM,{hum},SOLAR,{solar_percent:.1f},PUMP,{pump_cmd}"
            if nodemcu is None or not nodemcu.is_open:
                nodemcu = connect_nodemcu()

            if nodemcu:
                try:
                    nodemcu.write((data_packet + "\n").encode())
                    print(f"✔️ Sent to NodeMCU: {data_packet}")
                except Exception as e:
                    print("⚠️ NodeMCU write failed:", e)
                    nodemcu = None  # Force reconnect next loop

            print("============================================")

        time.sleep(1)

except KeyboardInterrupt:
    print("Exiting...")
    arduino.close()
    if nodemcu and nodemcu.is_open:
        nodemcu.close()
