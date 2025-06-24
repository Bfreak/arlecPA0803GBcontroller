# arlecPA0803GBcontroller
**An attempt to hack the Arlec PA0803GB standing air conditoner, and control it via an RPI pico**

Hi. I'm attempting to modify my arlec portable AC unit by placing it in another room to isolate noise and heat, and pump the cool air into another room.
In the process, I'd like to hack the unit (probably via the communication between the front panel and the main board) via UART to control via an RPI pico W in order to monitor and control it via homeassistant, or something else.

# Notes on the hardware:
- the communication I'm attempting to decode is between the devices main control board and a front panel. The connection is 4 wire; 5v, gnd, Rx and Tx. Rx and Tx are labelled opposingly on each, suggesting simple 2 way communication.
- the front panel has 6 buttons, 8 status LEDs, a 2 digit 7 segment display (SSC5023HG-2), a piezo buzzer, and an IR receiver for the remote. It also has a micro controller (eastsoft HR7P169BFGSF)
- the main board has all the usual relays and control gear for the AC fans, compressor, etc. I'm unwilling to unmount the main board to see what the microcontroller situation is on the back as I'm not comfortable getting too close to a very large capacitor and mains elctronic switch gear.
- the main board has 2 temperature sensors; one on the top of the unit near the ac's 'cold side' air intake, and one on the 'hot side' air intake, quite close to or possibly on the condensor coil, presumably monitoring for overheating. 

# **warning**
I am a novice. all of the supplied code and information is almost certainly garbage. If you choose to use any information provided, you do so entirely at your own risk.

## Updates

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

**update** 21-6-2025

Efforts to decode the communication sent from the main board to the front panel have proven fruitless. This is almost certainly due to my lack of knowledge with PIO, and I was unable to make accurate enough reads of the data using the same method used to capture button presses. 
I have decided to change tack to get a working controller of some sorts in place, and will simply have the pico providing commands to the unit with no communication from the main board. This has two main drawbacks; no ability to be 100% certain of the state of the air conditioner at any given moment (the pico will store the current state in memory) and no ability to read the ambient air temperature recorded by the unit. I will add an AHT 20 to the Pico to overcome the former issue (and add humidity sensing, a feature not present on the unit by default) at some point.
The pico is powered by the 5v provided by the main board, so in the event of a total power loss, both the pico and the AC return to the default state. So in the event that the state of the board and the unit become seperarated, I can flip a mains power switch which is easily accessible to return them both back to the default state.
That said, It does seem like button presses sent from the pico are pretty much 100% reliable, so provided I've got the logic correct, I don't see this really being an issue ever.

For now, I'm going to have the device host a local webpage to ensure offline control is available, and add MQTT functionlity or nodered or whatever else down the line, depending on how soon it becomes annoying not to have.

**update** 24-6-2025

Success on mainboard message decoding! Switching to IRQ has made things much easier. The timings are a bit questionable, but the decoding rate is sufficient to reliable decode and send mainboard messages to the front panel. I made a few attempts to try and decode the output binary in order to figure out segments, but couldn't make any sense of it, and instead worked to just record all of the various states of the digit display and LEDs so that they can be looked up on arrival. 

With this, the project is properly ready to start building a full remote management system that can confidently and accurately command the mainboard, and interpret it's replies, ensuring that commands were sent succesfully, and continued monitoring. 

Though sending commands TO the front panel is possible, I don't realistically have a need to do so as my unit will be inaccessible during use, and what's on the front panel is irrelevant. For that reason, the code for sending messages TO the front panel will purely be to validate the received messages from the mainboard, and probably won't feature in any final full working versions of the controller. 
