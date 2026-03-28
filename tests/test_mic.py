import pyaudio
import wave

MIC_INDEX = 1
SPEAKER_INDEX = 8
DURATION = 5
FILENAME = "test.wav"

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

p = pyaudio.PyAudio()

print("Recording for 5 seconds...")
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                input=True, input_device_index=MIC_INDEX,
                frames_per_buffer=CHUNK)

frames = []
for _ in range(0, int(RATE / CHUNK * DURATION)):
    frames.append(stream.read(CHUNK))

stream.stop_stream()
stream.close()
print("Done recording. Saving...")

with wave.open(FILENAME, 'wb') as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))

print("Playing back...")
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                output=True, output_device_index=SPEAKER_INDEX)

with wave.open(FILENAME, 'rb') as wf:
    data = wf.readframes(CHUNK)
    while data:
        stream.write(data)
        data = wf.readframes(CHUNK)

stream.stop_stream()
stream.close()
p.terminate()
print("Done!")