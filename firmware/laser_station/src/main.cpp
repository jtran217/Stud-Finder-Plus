// Laser station - 28BYJ-48 on a ULN2003 board + line laser
//
// Commands (115200 baud, one per line):
//   G <steps>   go to absolute position (half steps, ~4096/rev)
//   Z           zero here
//   L 1 | L 0   laser on/off
//   P           print position
//   ID          replies "ID LASER" so the laptop can find us

#include <Arduino.h>

const uint8_t COIL_PINS[4] = {4, 5, 6, 7};   // ULN2003 IN1..IN4
const uint8_t LASER_PIN = 9;                 // 1k -> PN2222 base

// half-step sequence, bit i -> COIL_PINS[i]
const uint8_t HALF_STEPS[8] = {0b0001, 0b0011, 0b0010, 0b0110,
                               0b0100, 0b1100, 0b1000, 0b1001};

const unsigned long STEP_US = 1400;          // ~700 steps/s, go higher if it skips
const unsigned long RELEASE_AFTER_MS = 500;  // cut coil power when idle

long position = 0;
long target = 0;
uint8_t phase = 0;
bool coilsOn = false;
unsigned long lastStepUs = 0;
unsigned long lastMoveMs = 0;

char line[32];
uint8_t lineLen = 0;

void writeCoils(uint8_t bits) {
  for (uint8_t i = 0; i < 4; i++) digitalWrite(COIL_PINS[i], (bits >> i) & 1);
}

void stepOnce(int dir) {
  phase = (phase + dir + 8) % 8;
  writeCoils(HALF_STEPS[phase]);
  coilsOn = true;
  position += dir;
}

void handleCommand(char *cmd) {
  switch (cmd[0]) {
    case 'G':
      target = atol(cmd + 1);
      Serial.print("OK G ");
      Serial.println(target);
      break;
    case 'Z':
      position = target = 0;
      Serial.println("OK Z");
      break;
    case 'L': {
      bool on = atoi(cmd + 1) != 0;
      digitalWrite(LASER_PIN, on ? HIGH : LOW);
      Serial.println(on ? "OK L 1" : "OK L 0");
      break;
    }
    case 'P':
      Serial.print("POS ");
      Serial.println(position);
      break;
    default:
      if (strcmp(cmd, "ID") == 0) {
        Serial.println("ID LASER");
      } else {
        Serial.print("ERR unknown command: ");
        Serial.println(cmd);
      }
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        line[lineLen] = '\0';
        handleCommand(line);
        lineLen = 0;
      }
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

void setup() {
  for (uint8_t i = 0; i < 4; i++) pinMode(COIL_PINS[i], OUTPUT);
  pinMode(LASER_PIN, OUTPUT);
  writeCoils(0);
  digitalWrite(LASER_PIN, LOW);
  Serial.begin(115200);
  Serial.println("READY LASER");
}

void loop() {
  readSerial();

  unsigned long nowUs = micros();
  if (position != target) {
    if (nowUs - lastStepUs >= STEP_US) {
      lastStepUs = nowUs;
      stepOnce(target > position ? 1 : -1);
      lastMoveMs = millis();
    }
  } else if (coilsOn && millis() - lastMoveMs > RELEASE_AFTER_MS) {
    writeCoils(0);
    coilsOn = false;
  }
}
