from pathlib import Path
import time
import socket
import struct
import pyaudio
import wave

def list_audio_devices():
    p = pyaudio.PyAudio()
    try:
        device_count = p.get_device_count()
        print("\nAvailable audio devices:")
        for i in range(device_count):
            dev = p.get_device_info_by_index(i)
            print(f"{i}: {dev['name']}")
        return device_count
    finally:
        p.terminate()

def get_device_index(device_count):
    while True:
        device_name = input("\nEnter the name or number of your microphone device: ")

        # Check if input is a number
        if device_name.isdigit():
            device_index = int(device_name)
            if 0 <= device_index < device_count:
                return device_index

        # Check if input is a name
        p = pyaudio.PyAudio()
        for i in range(device_count):
            dev = p.get_device_info_by_index(i)
            if device_name.lower() in dev['name'].lower():
                p.terminate()
                return i

        p.terminate()
        print("Device not found. Please try again.")

def get_transcript_filename():
    # Create the directory structure
    captions_path = Path.home() / "Movies" / "Screencasts" / "Captions"
    captions_path.mkdir(parents=True, exist_ok=True)

    while True:
        filename = input("\nEnter the name for your transcript file (e.g., 'meeting_notes'): ").strip()
        if not filename:
            print("Filename cannot be empty. Please try again.")
            continue

        # Remove .txt extension if user included it
        if filename.endswith('.txt'):
            filename = filename[:-4]

        # Add timestamp and .txt extension
        timestamp = time.strftime("%Y-%m-%d_-_%I-%M-%S-%p")
        filename = f"{filename}-{timestamp}.txt"
        
        # Create full path for the file
        full_path = captions_path / filename
        return str(full_path)  # Convert Path to string for compatibility

def send_audio(host="localhost", port=43007, device_index=None, transcript_file="transcript.txt"):
    # Audio stream configuration
    CHUNK = 3200
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    # Create audio file name based on transcript file name
    transcript_path = Path(transcript_file)
    audio_file = transcript_path.parent / f"{transcript_path.stem}.wav"

    # Initialize PyAudio first
    p = pyaudio.PyAudio()

    # Set up WAV file
    wf = wave.open(str(audio_file), 'wb')  # Convert Path to string for wave module
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)

    # Open audio stream with selected device
    stream = p.open(format=FORMAT,
                   channels=CHANNELS,
                   rate=RATE,
                   input=True,
                   input_device_index=device_index,
                   frames_per_buffer=CHUNK)

    print("\nConnecting to server...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((host, port))
            print("Connected! Start speaking (Ctrl+C to exit)...")

            while True:
                try:
                    # Read audio data from microphone
                    data = stream.read(CHUNK, exception_on_overflow=False)

                    # Save audio chunk to WAV file
                    wf.writeframes(data)

                    # Check for voice activity (silently)
                    audio_samples = struct.unpack(f'{CHUNK}h', data)
                    max_amplitude = max(abs(min(audio_samples)), abs(max(audio_samples)))

                    # Send the data if above noise threshold
                    if max_amplitude > 500:
                        s.sendall(data)

                    # Try to receive any response
                    try:
                        s.settimeout(0.1)
                        response = s.recv(1024)
                        if response:
                            # Parse and display the transcription text
                            parts = response.decode('utf-8').strip().split('  ', 1)
                            if len(parts) > 1:
                                transcription = parts[1]
                                print(transcription)  # Print to console
                                # Save to file
                                with open(transcript_file, 'a', encoding='utf-8') as f:
                                    f.write(transcription + '\n')
                    except socket.timeout:
                        pass

                except KeyboardInterrupt:
                    print("\nStopping...")
                    break
                except Exception as e:
                    print(f"\nError: {e}")
                    break

        except ConnectionRefusedError:
            print("Could not connect to server. Make sure the server is running.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            wf.close()  # Close the WAV file
            stream.stop_stream()
            stream.close()
            p.terminate()

def create_session_summary(host, port, device_index, transcript_file, audio_file):
    summary = f"""
=== Configuration Summary ===
Host: {host}
Port: {port}
Audio Device Index: {device_index}
Transcript File: {transcript_file}
Audio File: {audio_file}
"""
    return summary

def main():
    # List available devices and get user selection
    device_count = list_audio_devices()
    device_index = get_device_index(device_count)

    # Get transcript filename from user
    transcript_file = get_transcript_filename()
    audio_file = str(Path(transcript_file).parent / f"{Path(transcript_file).stem}.wav")

    # Add host/IP selection
    host_input = input("\nEnter server IP address (press Enter for localhost): ").strip()
    host = "localhost" if not host_input else host_input

    # Add port selection
    port_input = input("\nEnter port number (press Enter for default 43007): ").strip()
    port = 43007 if not port_input else int(port_input)

    # Create and display summary
    summary = create_session_summary(host, port, device_index, transcript_file, audio_file)
    print(summary)

    # Save to log file
    log_file = "whisper_sessions.log"
    with open(log_file, "a") as f:
        f.write(f"\n=== Client Session Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(summary)
        f.write("="*50 + "\n")

    # Start audio streaming
    send_audio(host=host, port=port, device_index=device_index, transcript_file=transcript_file)

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
