// Steam-Aware Valve Control - Unified Idle-Shutoff Experiment
// Compares NAIVE (fixed 15% idle crack) vs SMART (physics-based idle shutoff & preheat)

#include <Arduino.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS 4
#define RELAY_PIN 5
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

// ==== TOGGLE THIS BETWEEN RUNS ====
#define SMART_MODE true    // true = SMART (physics-based 0% idle shutoff & dynamic preheat)
// ===================================

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

const float SETPOINT = 85.0;
const float SAFETY_MAX = 95.0;

// Measured physics rates from physical rig:
const float HEATING_RATE_C_PER_SEC = 1.03 / 60.0; // ~0.01717 C/s
const float COOLING_RATE_C_PER_SEC = 0.375 / 60.0; // ~0.00625 C/s

// Naive baseline parameters:
const unsigned long NAIVE_PREHEAT_LEAD_SEC = 90; // Fixed 90s lead guess
const float NAIVE_IDLE_CRACK_PCT = 15.0;         // Fixed 15% wasted idle power

// ---- 2-Job Schedule with 4-minute Idle Gap ----
struct Job { unsigned long start; unsigned long end; };
Job schedule[] = {
  {0, 60},      // Job 1: 0s to 60s
  {300, 420},   // Job 2: 300s to 420s (Idle Gap: 60s to 300s)
};
const int NUM_JOBS = 2;

// PID Gains
float Kp = 30.0, Ki = 0.2, Kd = 5.0;
float integral = 0, lastError = 0;
unsigned long lastPIDTime = 0, windowStartTime = 0, onTimeMs = 0;
const unsigned long WINDOW_SIZE_MS = 15000; // 15-second smooth relay window
bool heaterOn = false;

enum Mode { IN_JOB, IDLE_HOLD, IDLE_SHUTOFF, PREHEATING, DONE };
Mode currentMode = IN_JOB;

void setup() {
  Serial.begin(115200);
  delay(1500);

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_OFF);

  sensors.begin();
  sensors.setWaitForConversion(true);

  Serial.println("\n==============================================");
  Serial.print("   IDLE-SHUTOFF EXPERIMENT - MODE: ");
  Serial.println(SMART_MODE ? "SMART (Physics Shutoff)" : "NAIVE (Fixed 15% Crack)");
  Serial.println("   Schedule: Job1 (0-60s) -> Gap (60-300s) -> Job2 (300-420s)");
  Serial.println("==============================================");
  Serial.println("timestamp_s,temperature_C,mode,output_pct,heater_state");

  lastPIDTime = millis();
  windowStartTime = millis();
}

long secondsUntilNextJob(unsigned long nowSec, bool &inJobNow) {
  inJobNow = false;
  for (int i = 0; i < NUM_JOBS; i++) {
    if (nowSec >= schedule[i].start && nowSec < schedule[i].end) {
      inJobNow = true;
      return 0;
    }
    if (nowSec < schedule[i].start) return schedule[i].start - nowSec;
  }
  return -1; // Schedule complete
}

void loop() {
  unsigned long nowMs = millis();
  unsigned long nowSec = nowMs / 1000;

  sensors.requestTemperatures();
  float tempC = sensors.getTempCByIndex(0);

  if (tempC == DEVICE_DISCONNECTED_C || tempC < -50.0) {
    digitalWrite(RELAY_PIN, RELAY_OFF);
    Serial.println("ERROR: Sensor disconnected, heater forced OFF");
    delay(1000);
    return;
  }

  if (tempC >= SAFETY_MAX) {
    digitalWrite(RELAY_PIN, RELAY_OFF);
    Serial.printf("SAFETY CUTOFF: %.2f C >= %.1f C\n", tempC, SAFETY_MAX);
    delay(1000);
    return;
  }

  bool inJobNow;
  long gapSec = secondsUntilNextJob(nowSec, inJobNow);
  float output = 0;

  if (inJobNow) {
    currentMode = IN_JOB;
  } 
  else if (gapSec > 0) {
    #if SMART_MODE
      // ---- SMART DECISION LOGIC ----
      float predictedDropIfOff = gapSec * COOLING_RATE_C_PER_SEC;
      float predictedTempAtNextJob = tempC - predictedDropIfOff;
      float reheatTimeNeeded = (SETPOINT - predictedTempAtNextJob) / HEATING_RATE_C_PER_SEC;

      if (reheatTimeNeeded <= gapSec) {
        float leadTime = (SETPOINT - tempC + predictedDropIfOff) / HEATING_RATE_C_PER_SEC;
        currentMode = (gapSec - leadTime > 5) ? IDLE_SHUTOFF : PREHEATING;
      } else {
        currentMode = IDLE_HOLD;
      }
    #else
      // ---- NAIVE BASELINE: Fixed 15% crack, fixed 90s preheat ----
      if ((unsigned long)gapSec <= NAIVE_PREHEAT_LEAD_SEC) {
        currentMode = PREHEATING;
      } else {
        currentMode = IDLE_HOLD; // Naive wastes power with continuous 15% crack
      }
    #endif
  } 
  else {
    currentMode = DONE;
  }

  float dt = (nowMs - lastPIDTime) / 1000.0;
  if (dt <= 0) dt = 1.0;
  lastPIDTime = nowMs;

  // Calculate output based on Mode
  if (currentMode == IDLE_SHUTOFF || currentMode == DONE) {
    output = 0.0;
    integral = 0;
  }
  #if !SMART_MODE
  else if (currentMode == IDLE_HOLD) {
    output = NAIVE_IDLE_CRACK_PCT; // 15% power
  }
  #endif
  else {
    // IN_JOB, PREHEATING, or SMART IDLE_HOLD
    if (tempC >= SETPOINT) {
      output = 0.0;
      integral = 0;
    } else if (tempC < (SETPOINT - 2.0f)) {
      output = 100.0;
    } else {
      float error = SETPOINT - tempC;
      integral += error * dt;
      integral = constrain(integral, -20.0f, 20.0f);
      float derivative = (error - lastError) / dt;
      output = (Kp * error) + (Ki * integral) + (Kd * derivative);
      output = constrain(output, 0.0f, 100.0f);
    }
    lastError = SETPOINT - tempC;
  }

  // Smooth Time-Proportioning Relay Control (15s Window)
  if (nowMs - windowStartTime >= WINDOW_SIZE_MS) windowStartTime = nowMs;
  onTimeMs = (unsigned long)((output / 100.0f) * WINDOW_SIZE_MS);
  unsigned long elapsed = nowMs - windowStartTime;
  if (elapsed < onTimeMs && output > 5.0f) {
    digitalWrite(RELAY_PIN, RELAY_ON);
    heaterOn = true;
  } else {
    digitalWrite(RELAY_PIN, RELAY_OFF);
    heaterOn = false;
  }

  String modeStr;
  switch (currentMode) {
    case IN_JOB: modeStr = "IN_JOB"; break;
    case IDLE_HOLD: modeStr = "IDLE_HOLD"; break;
    case IDLE_SHUTOFF: modeStr = "IDLE_SHUTOFF"; break;
    case PREHEATING: modeStr = "PREHEATING"; break;
    case DONE: modeStr = "DONE"; break;
  }

  Serial.printf("%lu,%.2f,%s,%.1f,%d\n", nowSec, tempC, modeStr.c_str(), output, heaterOn ? 1 : 0);

  if (currentMode == DONE && nowSec == 421) {
    Serial.println("\n----------------------------------------------");
    Serial.println(">>> SCHEDULE FINISHED at second 420 (7 mins)!");
    Serial.println("----------------------------------------------\n");
  }

  delay(1000);
}