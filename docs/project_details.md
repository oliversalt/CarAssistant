I am trying to make a device that sits in my car. its a raspberry pi powered by a portable charger with its own microphone and speaker. you can use this to speak to claude api and have a conversation with it. later steps will be getting it to change what music is playing on my phone and maps navigation.

I have a raspberry pi 4 B with 4gb 
I have a Belkin BPB012 (which is the standard BoostCharge 20K) which outputs 5v - 3A which is attatched to the usbc power input to the pi
Here are the other parts I have bought:
Diffused RGB (tri-color) LED (Common Anode)
SanDisk MicroSD Card (Class 10 A1)
32GB
Micro HDMI Cable
GPIO Screw Terminal HAT
4-Piece Raspberry Pi 4 Heatsink Set
3.2" IPS HDMI LCD Display for Raspberry Pi (800x480)
Mini External USB Stereo Speaker

I am running Raspberry Pi OS Lite

I am using tailscale to ssh into the pi each time. this means i can do it regarless of the wifi connection both the pi and the ssh device has. 

The pi's hostname is salt-raspberry-pi

I have my own 3d printer which i will use to make custom housing for the pi for this project
The car device will have a screen that displays states and graphics. maybe in the future it will show navigation. also it will show the pi's status loading up screen etc. 

The screen is purely a glanceable status display. Four states:
Idle, Listening, Thinking, Speaking 