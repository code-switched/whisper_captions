from pathlib import Path
import time
import socket
import struct
import pyaudio
import wave
from config_utils import load_config, update_config_value, get_config_value, DEFAULT_CONFIG

# _sentinel is still used by get_config_value to check if a key was found
_sentinel = object()

# _save_if_needed helper function is removed

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

def get_device_index(device_count): # device_count passed in, p should be managed by caller or locally
    # This function is called when config device is invalid or not found.
    # It should manage its own PyAudio instance for listing if needed for name matching.
    while True:
        device_name_or_num = input("\nEnter the name or number of your microphone device: ")

        if device_name_or_num.isdigit():
            device_index_candidate = int(device_name_or_num)
            if 0 <= device_index_candidate < device_count:
                return device_index_candidate
        
        # Check by name (requires a local PyAudio instance if not passed)
        p_local = None
        try:
            p_local = pyaudio.PyAudio()
            for i in range(p_local.get_device_count()): # Re-check count in case it changed
                dev = p_local.get_device_info_by_index(i)
                if device_name_or_num.lower() in dev['name'].lower():
                    return i
        finally:
            if p_local:
                p_local.terminate()
        print("Device not found or invalid input. Please try again.")


def get_transcript_filename(): 
    captions_path = Path.home() / "Movies" / "Screencasts" / "Captions"
    captions_path.mkdir(parents=True, exist_ok=True)

    key_path_base = "client.transcript_filename_base"
    default_base = DEFAULT_CONFIG['client']['transcript_filename_base'] 
    
    val_from_config_base = get_config_value(key_path_base, _sentinel)
    
    current_base_for_prompt = default_base
    if val_from_config_base is not _sentinel:
        print(f"Using 'transcript_filename_base' from config: {val_from_config_base}") 
        current_base_for_prompt = val_from_config_base
    elif default_base is None : 
        print("Setting 'transcript_filename_base' not found in config and no default is available. Please provide one for this session.")
        current_base_for_prompt = None 
    else: 
        print(f"Setting 'transcript_filename_base' not in config, using default: '{default_base}' for this session.")
        current_base_for_prompt = default_base

    while True:
        prompt_msg = "\nEnter the base name for your transcript file for this session"
        if current_base_for_prompt is not None:
            prompt_msg += f" [default: {current_base_for_prompt}]: "
        else:
            prompt_msg += " (e.g., 'meeting_notes', required for this session): "
            
        chosen_base_name_input = input(prompt_msg).strip()
        final_chosen_base_name = chosen_base_name_input if chosen_base_name_input else current_base_for_prompt

        if not final_chosen_base_name: 
            print("Filename base cannot be empty for this session. Please try again.")
            current_base_for_prompt = None 
            continue
        
        if chosen_base_name_input and chosen_base_name_input != current_base_for_prompt: 
            print(f"Using '{final_chosen_base_name}' as transcript base name for this session.")
        elif not chosen_base_name_input and current_base_for_prompt is not None: 
             print(f"Using default '{current_base_for_prompt}' as transcript base name for this session.")
        
        timestamp = time.strftime("%Y-%m-%d_-_%I-%M-%S-%p")
        if final_chosen_base_name.endswith('.txt'):
            final_chosen_base_name = final_chosen_base_name[:-4]
            
        full_filename = f"{final_chosen_base_name}-{timestamp}.txt"
        full_path = captions_path / full_filename
        return str(full_path)


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
    wf = None
    stream = None

    try:
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
                            else:
                                print(response.decode('utf-8').strip())
                    except socket.timeout:
                        pass

                except KeyboardInterrupt:
                    print("\nStopping...")
                    break
                except Exception as e:
                    print(f"\nError during streaming: {e}")
                    break
    except ConnectionRefusedError:
        print(f"Could not connect to server at {host}:{port}. Make sure the server is running.")
    except Exception as e:
        print(f"Error setting up audio: {e}")
    finally:
        if wf: wf.close()
        if stream: stream.stop_stream(); stream.close()
        p.terminate()
        print("\nAudio stream closed.")


def create_session_summary(host, port, device_idx, transcript_file_path_str, audio_file_path_str):
    summary = f"""
=== Client Configuration Summary ===
Host: {host}
Port: {port}
Audio Device Index: {device_idx}
Transcript File: {transcript_file_path_str}
Audio File: {audio_file_path_str}
"""
    return summary

def main():
    print("Loading client configuration from config.yaml...")
    load_config() 
    print("\nNote: Configuration is loaded from config.yaml. Settings chosen during this session")
    print("will not be saved back to the file. To make persistent changes, please edit config.yaml directly.\n")

    final_device_index = None
    p_main = pyaudio.PyAudio() 

    try:
        key_device_idx = "client.device_index"
        key_device_name = "client.device_name"
        device_index_saved = get_config_value(key_device_idx, _sentinel)
        device_name_saved = get_config_value(key_device_name, _sentinel)

        if device_index_saved is not _sentinel and device_index_saved is not None:
            try:
                device_info = p_main.get_device_info_by_index(device_index_saved)
                if device_name_saved is not _sentinel and device_info['name'] == device_name_saved:
                    print(f"Using audio device from config: {device_name_saved} (Index: {device_index_saved})")
                    final_device_index = device_index_saved
                else:
                    print(f"Warning: Saved device name ('{device_name_saved}') does not match current name ('{device_info['name']}') for index {device_index_saved}. Please re-select for this session.")
            except OSError: 
                print(f"Warning: Saved device index {device_index_saved} is invalid. Please re-select for this session.")
        
        if final_device_index is None:
            print("Prompting for audio device selection for this session...")
            device_count = list_audio_devices() 
            if device_count == 0:
                print("No audio devices found. Exiting.")
                return
            
            chosen_idx_from_prompt = get_device_index(device_count)
            chosen_device_info = p_main.get_device_info_by_index(chosen_idx_from_prompt)
            chosen_device_name = chosen_device_info['name']
            final_device_index = chosen_idx_from_prompt
            print(f"Using selected audio device for this session: {chosen_device_name} (Index: {final_device_index})")
    finally:
        p_main.terminate()

    transcript_file_path = get_transcript_filename() 
    audio_file_path = str(Path(transcript_file_path).with_suffix('.wav'))

    key_host = "client.host"
    default_host = DEFAULT_CONFIG['client']['host']
    val_from_config_host = get_config_value(key_host, _sentinel)
    current_host_for_prompt = default_host
    if val_from_config_host is not _sentinel:
        print(f"Using 'server host' from config: {val_from_config_host}")
        current_host_for_prompt = val_from_config_host
    else: 
        print(f"Setting 'server host' not in config, using default: '{default_host}' for this session.")
        # current_host_for_prompt is already default_host
    
    host_input = input(f"\nEnter server IP address for this session [default: {current_host_for_prompt}]: ").strip()
    final_host = host_input if host_input else current_host_for_prompt
    
    if host_input and final_host != current_host_for_prompt : 
        print(f"Using server host '{final_host}' for this session.")
    elif not host_input and current_host_for_prompt is not None: 
        print(f"Using default server host '{current_host_for_prompt}' for this session.")

    key_port = "client.port"
    default_port = DEFAULT_CONFIG['client']['port']
    val_from_config_port = get_config_value(key_port, _sentinel)
    current_port_for_prompt = default_port
    if val_from_config_port is not _sentinel:
        print(f"Using 'server port' from config: {val_from_config_port}")
        current_port_for_prompt = val_from_config_port
    else: 
        print(f"Setting 'server port' not in config, using default: '{default_port}' for this session.")
        # current_port_for_prompt is already default_port

    port_input_str = input(f"\nEnter port number for this session [default: {current_port_for_prompt}]: ").strip()
    final_port = int(port_input_str) if port_input_str else current_port_for_prompt

    if port_input_str and final_port != current_port_for_prompt: 
        print(f"Using server port '{final_port}' for this session.")
    elif not port_input_str and current_port_for_prompt is not None: 
        print(f"Using default server port '{current_port_for_prompt}' for this session.")

    summary = create_session_summary(final_host, final_port, final_device_index, transcript_file_path, audio_file_path)
    print(summary)
    log_file = "whisper_sessions.log" 
    with open(log_file, "a") as f:
        f.write(f"\n=== Client Session Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(summary)
        f.write("="*50 + "\n")

    send_audio(host=final_host, port=final_port, device_index=final_device_index, transcript_file=transcript_file_path)

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
