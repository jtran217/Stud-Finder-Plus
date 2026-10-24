#include <Arduino.h>

// Stud finder board: turns A0 readings into "S1 <ms>" (stud LED came on) and
// "S0 <ms>" (stud LED went off or finder switched off) lines at 115200 baud.
// A0 = stud-indicator LED pad through 10k, with the internal pull-up.

const int CLEAR_MIN = 900;
const int STUD_MIN  = 650;   
const int STUD_MAX  = 820;   
const int OFF_MAX   = 450;
const unsigned long HOLD_MS = 30;   

enum State { OFF, CLEAR, STUD };
State state = OFF;           // confirmed state
State candidate = OFF;       // what the latest readings say
unsigned long candidateSince = 0;

State classify(int v) {
  if (v >= CLEAR_MIN) return CLEAR;
  if (v >= STUD_MIN && v <= STUD_MAX) return STUD;
  if (v <= OFF_MAX) return OFF;
  return state;              // in a gap between levels: no change
}

void setup() {
  Serial.begin(115200);
  pinMode(A0, INPUT_PULLUP);
}

void loop() {
  State s = classify(analogRead(A0));
  unsigned long now = millis();

  if (s != candidate) {
    candidate = s;
    candidateSince = now;
  } else if (candidate != state && now - candidateSince >= HOLD_MS) {
    if (candidate == STUD) {
      Serial.print("S1 "); Serial.println(now);
    } else if (state == STUD) {
      Serial.print("S0 "); Serial.println(now);
    }
    state = candidate;
  }
  delay(5);
}
