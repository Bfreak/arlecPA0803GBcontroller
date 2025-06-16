# arlecPA0803GBcontroller
**An attempt to hack the Arlec PA0803GB standing air conditoner, and control it via an RPI pico**

Hi. I'm attempting to modify my arlec portable AC unit by placing it in another room to isolate noise and heat, and pump the cool air into another room.
In the process, I'd like to hack the unit (probably via the communication between the front panel and the main board) via UART to control via an RPI pico W in order to monitor and control it via homeassistant, or something else.

Notes on the hardware:
- the communication I'm attempting to decode is between the devices main control board and a front panel. The connection is 4 wire; 5v, gnd, Rx and Tx. Rx and Tx are labelled opposingly on each, suggesting simple 2 way communication.
- the front panel has 6 buttons, 8 status LEDs, a 2 digit 7 segment display (SSC5023HG-2), a piezo buzzer, and an IR receiver for the remote. It also has a micro controller (eastsoft HR7P169BFGSF)
- the main board has all the usual relays and control gear for the AC fans, compressor, etc. I'm unwilling to unmount the main board to see what the microcontroller situation is on the back as I'm not comfortable getting too close to a very large capacitor and mains elctronic switch gear.
- the main board has 2 temperature sensors; one on the top of the unit near the ac's 'cold side' air intake, and one on the 'hot side' air intake, quite close to or possibly on the condensor coil, presumably monitoring for overheating. 

**warning**
I am a novice. all of the supplied code and information is almost certainly garbage. If you choose to use any information provided, you do so entirely at your own risk.

**update** 15-6-2025

I now have a logic analyzer, as no standard version of UART seemed to apply to the communication. 

![image](https://github.com/user-attachments/assets/234dc970-7463-4eff-8598-4fade56371c1)

**Key observations:**
- both directions has occasional messages. At first I assumed the main board updated the front panel with information for the 2 digit display, mode LEDs, and piezo speaker. Evidently this is not the case.
- The passive messages are 10s apart, first the front panel, then possibly a reply from the main board 300ms later.
- communication in both directions starts with a 4.5ms low, then 2.25ms high.
- normal data then starts with 0.25ms low times per bit(?)
- there are occasional 0.75ms lows
- data then finishes with a .5 ms low from the front panel to the board (RX on the board)
- and a .6ms low from the board to the front panel (TX on the board)
- Logic 2 software suggests baud of 4.032 kHz

With the above notes, chatGPT suggests 'IR-style pulse-width encoded protocol or custom synchronous signaling'.
Needless to say, I'm well out of my depth. I'll be asking for help in misc. online places soon.

**update** 16-6-2025

Success! In the end, I did away with all known forms of communication protocol and decided to wrangle the proprietary one myself. 
I managed to identify the start and stop bit timings, allowing me to read binary codes from the 'high' times, which formed 25 bit codes for button presses.
After moving the timings around a bit, I managed to send any button press using GPIO pins on the rasperry pi via a voltage step up for the logic (5v for the board).
As a result, I can now conceivably press the panel buttons for the unit as needed, with 99% reliability. 

See the new file for a script on how to do so. Decoding of the messages from the main board to the panel to come. If that is complete, I should in theory be able to simulate the front panel entirely within the pico, and allow for control and monitoring of the AC system remotely. 

**update** 16-6-2025 (part 2)

I added the code to decode button presses from the front panel, and added the power button press. All are working well, without the need for pull up/down resistors.
I thought decoding arriving data from the mainboard would be trivial at this point, with a good template for data capture, however the pico absolutely refuses to read incoming data in the same way, even though my scope and logic analyzer have no problems. It may be because of some kind of degradation, as the data capture points are right up against the front panel pins, with a 1m ish cable to the header on the main board.
