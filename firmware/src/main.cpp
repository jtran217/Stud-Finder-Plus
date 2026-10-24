#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  pinMode(A0, INPUT_PULLUP);   // hold A0 high when the stud LED is off
}

void loop() {
  Serial.println(analogRead(A0));
  delay(50);
}