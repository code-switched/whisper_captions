from pathlib import Path
import time
import socket
import struct
import pyaudio
import wave
from config_utils import load_config, update_config_value, get_config_value, DEFAULT_CONFIG

# Helper to manage saving logic, similar to server-side
_sentinel = object()

def _save_if_needed(key_path, final_value, value_from_file, setting_name_for_print):
    if value_from_file is _sentinel: # Not in config file originally
        update_config_value(key_path, final_value)
        if final_value is not None: # Avoid printing for initial None if that's the default
            print(f"'{setting_name_for_print}' set to '{final_value}' and saved to config.")
    elif final_value != value_from_file: # Was in config, but changed
        update_config_value(key_path, final_value)
        print(f"'{setting_name_for_print}' updated to '{final_value}' and saved to config.")


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


def get_transcript_filename(): # Modified to use config for base name
    captions_path = Path.home() / "Movies" / "Screencasts" / "Captions"
    captions_path.mkdir(parents=True, exist_ok=True)

    key_path_base = "client.transcript_filename_base"
    default_base = DEFAULT_CONFIG['client']['transcript_filename_base'] # Might be None
    
    val_from_config_base = get_config_value(key_path_base, _sentinel)
    
    current_base_for_prompt = default_base
    if val_from_config_base is not _sentinel:
        print(f"Using 'transcript_filename_base' from config: {val_from_config_base}")
        current_base_for_prompt = val_from_config_base
    elif default_base is None : # Not in config, and DEFAULT_CONFIG is None
        print("No 'transcript_filename_base' found in config and no default available. Please provide one.")


    while True:
        prompt_msg = "\nEnter the base name for your transcript file"
        if current_base_for_prompt:
            prompt_msg += f" [default: {current_base_for_prompt}]: "
        else:
            prompt_msg += " (e.g., 'meeting_notes'): "
            
        chosen_base_name_input = input(prompt_msg).strip()

        final_chosen_base_name = chosen_base_name_input if chosen_base_name_input else current_base_for_prompt

        if not final_chosen_base_name: # Still no base name (e.g. default was None, user hit enter)
            print("Filename base cannot be empty. Please try again.")
            current_base_for_prompt = None # Ensure prompt shows no default next time if it was initially None
            continue

        _save_if_needed(key_path_base, final_chosen_base_name, val_from_config_base, _sentinel, "transcript_filename_base")
        
        timestamp = time.strftime("%Y-%m-%d_-_%I-%M-%S-%p")
        # Remove .txt from base if user added it, as we add it with timestamp
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

    transcript_path = Path(transcript_file)
    audio_file_path_str = str(transcript_path.with_suffix('.wav')) # Corrected audio file name

    p = pyaudio.PyAudio()
    wf = None
    stream = None

    try:
        wf = wave.open(audio_file_path_str, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)

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
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    wf.writeframes(data)
                    
                    # Basic voice activity detection (placeholder)
                    # audio_samples = struct.unpack(f'{CHUNK}h', data)
                    # if max(abs(min(audio_samples)), abs(max(audio_samples))) > 500: # Basic VAD
                    s.sendall(data)

                    try:
                        s.settimeout(0.01) # Non-blocking receive
                        response = s.recv(1024)
                        if response:
                            parts = response.decode('utf-8').strip().split('  ', 1) # Assuming 'timestamp  text'
                            if len(parts) > 1: # Check if format is as expected
                                transcription = parts[1]
                                print(transcription, end='\r', flush=True) 
                                with open(transcript_file, 'a', encoding='utf-8') as f:
                                    f.write(transcription + '\n')
                            else: # Handle simpler responses or debug
                                print(response.decode('utf-8').strip(), end='\r', flush=True)

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
        if wf:
            wf.close()
        if stream:
            stream.stop_stream()
            stream.close()
        p.terminate()
        print("\nAudio stream closed.") # Ensure this prints after stopping


def create_session_summary(host, port, device_idx, transcript_file_path_str, audio_file_path_str):
    # Using device_idx as device_index might be confusing, renaming for clarity if needed.
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
    load_config() # Ensures config file exists or creates default.

    final_device_index = None
    p_main = pyaudio.PyAudio() # For device validation in main scope

    try:
        # --- Device Index and Name ---
        key_device_idx = "client.device_index"
        key_device_name = "client.device_name"
        
        device_index_saved = get_config_value(key_device_idx, _sentinel)
        device_name_saved = get_config_value(key_device_name, _sentinel)

        if device_index_saved is not _sentinel and device_index_saved is not None: # Check not None explicitly
            try:
                device_info = p_main.get_device_info_by_index(device_index_saved)
                if device_name_saved is not _sentinel and device_info['name'] == device_name_saved:
                    print(f"Using audio device from config: {device_name_saved} (Index: {device_index_saved})")
                    final_device_index = device_index_saved
                else:
                    print(f"Warning: Saved device name ('{device_name_saved}') does not match current name ('{device_info['name']}') for index {device_index_saved}. Please re-select.")
            except OSError: # Invalid device index
                print(f"Warning: Saved device index {device_index_saved} is invalid. Please re-select.")
        
        if final_device_index is None:
            print("Prompting for audio device selection...")
            device_count = list_audio_devices() # Manages its own PyAudio
            if device_count == 0:
                print("No audio devices found. Exiting.")
                return
            
            chosen_idx_from_prompt = get_device_index(device_count) # Manages its own PyAudio for name matching if needed
            chosen_device_info = p_main.get_device_info_by_index(chosen_idx_from_prompt)
            chosen_device_name = chosen_device_info['name']
            
            _save_if_needed(key_device_idx, chosen_idx_from_prompt, device_index_saved, "device_index")
            _save_if_needed(key_device_name, chosen_device_name, device_name_saved, "device_name")
            final_device_index = chosen_idx_from_prompt
            print(f"Selected audio device: {chosen_device_name} (Index: {final_device_index})")
    finally:
        p_main.terminate()

    # --- Transcript Filename (base name handled by get_transcript_filename) ---
    transcript_file_path = get_transcript_filename() # This now handles its own config for base name
    audio_file_path = str(Path(transcript_file_path).with_suffix('.wav'))

    # --- Host ---
    key_host = "client.host"
    default_host = DEFAULT_CONFIG['client']['host']
    val_from_config_host = get_config_value(key_host, _sentinel)
    current_host_for_prompt = default_host
    if val_from_config_host is not _sentinel:
        print(f"Using server host from config: {val_from_config_host}") # Removed single quotes
        current_host_for_prompt = val_from_config_host
    
    host_input = input(f"\nEnter server IP address [default: {current_host_for_prompt}]: ").strip()
    final_host = host_input if host_input else current_host_for_prompt
    _save_if_needed(key_host, final_host, val_from_config_host, "host")

    # --- Port ---
    key_port = "client.port"
    default_port = DEFAULT_CONFIG['client']['port']
    val_from_config_port = get_config_value(key_port, _sentinel)
    current_port_for_prompt = default_port
    if val_from_config_port is not _sentinel:
        print(f"Using server port from config: {val_from_config_port}") # Removed single quotes
        current_port_for_prompt = val_from_config_port

    port_input_str = input(f"\nEnter port number [default: {current_port_for_prompt}]: ").strip()
    final_port = int(port_input_str) if port_input_str else current_port_for_prompt
    _save_if_needed(key_port, final_port, val_from_config_port, "port")

    # --- Summary and Logging ---
    summary = create_session_summary(final_host, final_port, final_device_index, transcript_file_path, audio_file_path)
    print(summary)
    log_file = "whisper_sessions.log" # Consider making this configurable too
    with open(log_file, "a") as f:
        f.write(f"\n=== Client Session Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(summary)
        f.write("="*50 + "\n")

    send_audio(host=final_host, port=final_port, device_index=final_device_index, transcript_file=transcript_file_path)

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
