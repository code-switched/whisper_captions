#!/usr/bin/env python3
from whisper_online import *

import sys
import argparse
import os
import logging
import numpy as np
import time
import socket
import line_packet
import io
import soundfile
from config_utils import load_config, update_config_value, get_config_value, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# setting whisper object by args 
SAMPLING_RATE = 16000

# Helper to manage saving logic
def _save_if_needed(key_path, final_value, value_from_file, sentinel, setting_name_for_print):
    if value_from_file is sentinel: # Not in config file originally
        update_config_value(key_path, final_value)
        # Avoid printing for None if it's a non-critical field or if it's intended to be None
        if final_value is not None or setting_name_for_print in ["model", "backend", "log_level"]: # model/backend/log_level must be explicitly set
             print(f"'{setting_name_for_print}' set to '{final_value}' and saved to config.")
        elif final_value is None and value_from_file is not None : # explicitely setting to None
             print(f"'{setting_name_for_print}' set to '{final_value}' and saved to config.")

    elif final_value != value_from_file: # Was in config, but changed
        update_config_value(key_path, final_value)
        print(f"'{setting_name_for_print}' updated to '{final_value}' and saved to config.")

def get_user_preferences():
    print("Loading server configuration from config.yaml...")
    load_config() # Ensures config file exists or creates default. Messages handled by config_utils.

    models_list = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]
    backends_list = ["faster-whisper", "whisper_timestamped", "openai-api"]
    log_levels_list = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    _sentinel = object()

    print("\n=== Whisper Streaming Server Configuration ===")

    # --- Generic helper for list selections (model, backend, log_level) ---
    def get_selection_from_list(setting_name, item_list, current_value_for_logic, value_from_config_file):
        print(f"\nAvailable {setting_name}s:")
        for i, option in enumerate(item_list, 1):
            print(f"{i}. {option}")
        
        final_selected_value = current_value_for_logic
        while True:
            prompt_message = f"\nSelect a {setting_name} (1-{len(item_list)})"
            if final_selected_value is not None:
                prompt_message += f" [default: {final_selected_value}]: "
            else: # Critical setting like model/backend might be None from DEFAULT_CONFIG
                prompt_message += " (required): "
            
            choice = input(prompt_message).strip()

            if not choice: # User hit Enter
                if final_selected_value is None and setting_name in ["model", "backend"]:
                    print(f"A selection for '{setting_name}' is required.")
                    continue # Re-prompt
                # final_selected_value already holds the correct default (from file or DEFAULT_CONFIG)
                break 
            try:
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(item_list):
                    final_selected_value = item_list[choice_idx-1]
                    print(f"{setting_name.capitalize()} '{final_selected_value}' selected.")
                    break
                print(f"Invalid choice. Please select a number between 1 and {len(item_list)}.")
            except ValueError:
                print("Please enter a valid number.")
        return final_selected_value

    # --- Model Selection ---
    key_path_model = "server.model"
    default_dc_model = DEFAULT_CONFIG['server']['model']
    val_from_config_model = get_config_value(key_path_model, _sentinel)
    
    current_model_val = default_dc_model
    if val_from_config_model is not _sentinel:
        print(f"Using 'model' from config: {val_from_config_model}")
        current_model_val = val_from_config_model
    # If not in config, current_model_val remains default_dc_model
    if current_model_val is None: # Check effective value after considering config and DEFAULT_CONFIG
         print(f"The configured 'model' is None or not set. A selection is required.")

    selected_model = get_selection_from_list("model", models_list, current_model_val, val_from_config_model)
    _save_if_needed(key_path_model, selected_model, val_from_config_model, _sentinel, "model")
    if selected_model is None: # Should not happen if loop in get_selection_from_list is correct
        print("Error: Model not selected. Exiting.")
        sys.exit(1)


    # --- Backend Selection ---
    key_path_backend = "server.backend"
    default_dc_backend = DEFAULT_CONFIG['server']['backend']
    val_from_config_backend = get_config_value(key_path_backend, _sentinel)

    current_backend_val = default_dc_backend
    if val_from_config_backend is not _sentinel:
        print(f"Using 'backend' from config: {val_from_config_backend}")
        current_backend_val = val_from_config_backend
    # If not in config, current_backend_val remains default_dc_backend
    if current_backend_val is None: # Check effective value
        print(f"The configured 'backend' is None or not set. A selection is required.")

    selected_backend = get_selection_from_list("backend", backends_list, current_backend_val, val_from_config_backend)
    _save_if_needed(key_path_backend, selected_backend, val_from_config_backend, _sentinel, "backend")
    if selected_backend is None:
        print("Error: Backend not selected. Exiting.")
        sys.exit(1)

    # --- Helper for direct string/int/float input ---
    def get_direct_input(setting_name, current_value_for_logic, value_from_config_file, data_type=str):
        prompt_message = f"\nEnter {setting_name}"
        if current_value_for_logic is not None:
            prompt_message += f" [default: {current_value_for_logic}]: "
        else:
            prompt_message += ": "
        
        while True:
            user_input_str = input(prompt_message).strip()
            if not user_input_str: # User hit Enter
                # current_value_for_logic already holds the correct default
                return current_value_for_logic
            try:
                return data_type(user_input_str)
            except ValueError:
                print(f"Invalid input. Please enter a valid {data_type.__name__}.")

    # --- Host ---
    key_path_host = "server.host"
    default_dc_host = DEFAULT_CONFIG['server']['host']
    val_from_config_host = get_config_value(key_path_host, _sentinel)
    current_host_val = default_dc_host
    if val_from_config_host is not _sentinel:
        print(f"Using 'host' from config: {val_from_config_host}")
        current_host_val = val_from_config_host
    host = get_direct_input("host address", current_host_val, val_from_config_host, str)
    _save_if_needed(key_path_host, host, val_from_config_host, _sentinel, "host")

    # --- Port ---
    key_path_port = "server.port"
    default_dc_port = DEFAULT_CONFIG['server']['port']
    val_from_config_port = get_config_value(key_path_port, _sentinel)
    current_port_val = default_dc_port
    if val_from_config_port is not _sentinel:
        print(f"Using 'port' from config: {val_from_config_port}")
        current_port_val = val_from_config_port
    port = get_direct_input("port number", current_port_val, val_from_config_port, int)
    _save_if_needed(key_path_port, port, val_from_config_port, _sentinel, "port")
        
    # --- Warmup File ---
    key_path_warmup = "server.warmup_file"
    default_dc_warmup = DEFAULT_CONFIG['server']['warmup_file']
    val_from_config_warmup = get_config_value(key_path_warmup, _sentinel)
    current_warmup_val = default_dc_warmup
    if val_from_config_warmup is not _sentinel:
        print(f"Using 'warmup_file' from config: {val_from_config_warmup}")
        current_warmup_val = val_from_config_warmup
    warmup_file = get_direct_input("warmup file path", current_warmup_val, val_from_config_warmup, str)
    _save_if_needed(key_path_warmup, warmup_file, val_from_config_warmup, _sentinel, "warmup_file")

    # --- Language ---
    key_path_lang = "server.language"
    default_dc_lang = DEFAULT_CONFIG['server']['language']
    val_from_config_lang = get_config_value(key_path_lang, _sentinel)
    current_lang_val = default_dc_lang
    if val_from_config_lang is not _sentinel:
        print(f"Using 'language' from config: {val_from_config_lang}")
        current_lang_val = val_from_config_lang
    language = get_direct_input("language code (e.g., en, de, cs, or 'auto')", current_lang_val, val_from_config_lang, str)
    _save_if_needed(key_path_lang, language, val_from_config_lang, _sentinel, "language")

    # --- Helper for boolean (Y/n) input ---
    def get_boolean_input(setting_name, current_value_for_logic, value_from_config_file):
        prompt_default_display = 'Y' if current_value_for_logic else 'N'
        user_input_str = input(f"\nEnable {setting_name}? (Y/n) [default: {prompt_default_display}]: ").strip().lower()
        
        if not user_input_str: # User hit Enter
            return current_value_for_logic # Use the displayed default
        return user_input_str != 'n'

    # --- VAC Enabled ---
    key_path_vac = "server.vac_enabled"
    default_dc_vac = DEFAULT_CONFIG['server']['vac_enabled']
    val_from_config_vac = get_config_value(key_path_vac, _sentinel)
    current_vac_val = default_dc_vac
    if val_from_config_vac is not _sentinel:
        print(f"Using 'VAC enabled' from config: {'Y' if val_from_config_vac else 'N'}")
        current_vac_val = val_from_config_vac
    vac_enabled = get_boolean_input("Voice Activity Controller (VAC)", current_vac_val, val_from_config_vac)
    _save_if_needed(key_path_vac, vac_enabled, val_from_config_vac, _sentinel, "vac_enabled")

    # --- VAD Enabled ---
    key_path_vad = "server.vad_enabled"
    default_dc_vad = DEFAULT_CONFIG['server']['vad_enabled']
    val_from_config_vad = get_config_value(key_path_vad, _sentinel)
    current_vad_val = default_dc_vad
    if val_from_config_vad is not _sentinel:
        print(f"Using 'VAD enabled' from config: {'Y' if val_from_config_vad else 'N'}")
        current_vad_val = val_from_config_vad
    vad_enabled = get_boolean_input("Voice Activity Detection (VAD)", current_vad_val, val_from_config_vad)
    _save_if_needed(key_path_vad, vad_enabled, val_from_config_vad, _sentinel, "vad_enabled")

    # --- Min Chunk Size ---
    key_path_chunk = "server.min_chunk_size"
    default_dc_chunk = DEFAULT_CONFIG['server']['min_chunk_size']
    val_from_config_chunk = get_config_value(key_path_chunk, _sentinel)
    current_chunk_val = default_dc_chunk
    if val_from_config_chunk is not _sentinel:
        print(f"Using 'min_chunk_size' from config: {val_from_config_chunk}")
        current_chunk_val = val_from_config_chunk
    min_chunk_size = get_direct_input("minimum chunk size in seconds", current_chunk_val, val_from_config_chunk, float)
    _save_if_needed(key_path_chunk, min_chunk_size, val_from_config_chunk, _sentinel, "min_chunk_size")

    # --- Log Level ---
    key_path_log = "server.log_level"
    default_dc_log = DEFAULT_CONFIG['server']['log_level']
    val_from_config_log = get_config_value(key_path_log, _sentinel)
    current_log_val = default_dc_log
    if val_from_config_log is not _sentinel:
        print(f"Using 'log_level' from config: {val_from_config_log}")
        current_log_val = val_from_config_log
    # If not in config, current_log_val remains default_dc_log
    if current_log_val is None: # Check effective value
         print(f"The configured 'log_level' is None or not set. A selection is required.")
    selected_log_level = get_selection_from_list("log level", log_levels_list, current_log_val, val_from_config_log)
    _save_if_needed(key_path_log, selected_log_level, val_from_config_log, _sentinel, "log_level")
    if selected_log_level is None:
        print("Error: Log level not selected. Using INFO.") # Fallback for safety
        selected_log_level = "INFO"


    # Get the machine's IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "IP Unknown"

    # Create sys.argv with the selected options
    sys.argv = [sys.argv[0]] # script name
    if selected_model: sys.argv.extend(["--model", selected_model])
    if selected_backend: sys.argv.extend(["--backend", selected_backend])
    if host: sys.argv.extend(["--host", host])
    if port is not None: sys.argv.extend(["--port", str(port)])
    if warmup_file: sys.argv.extend(["--warmup-file", warmup_file])
    if language: sys.argv.extend(["--lan", language])
    if vac_enabled: sys.argv.append("--vac") # No value needed for argparse
    if vad_enabled: sys.argv.append("--vad") # No value needed for argparse
    if min_chunk_size is not None: sys.argv.extend(["--min-chunk-size", str(min_chunk_size)])
    if selected_log_level: sys.argv.extend(["--log-level", selected_log_level])
    
    summary = f"""
=== Configuration Summary ===
Server IP: {local_ip}
Model: {selected_model}
Backend: {selected_backend}
Host: {host}
Port: {port}
Warmup File: {warmup_file}
Language: {language}
VAC: {'Enabled' if vac_enabled else 'Disabled'}
VAD: {'Enabled' if vad_enabled else 'Disabled'}
Min Chunk Size: {min_chunk_size}
Log Level: {selected_log_level}
"""
    print(summary)
    return summary

class Connection:
    '''it wraps conn object'''
    PACKET_SIZE = 32000*5*60 # 5 minutes # was: 65536

    def __init__(self, conn):
        self.conn = conn
        self.last_line = ""

        self.conn.setblocking(True)

    def send(self, line):
        '''it doesn't send the same line twice, because it was problematic in online-text-flow-events'''
        if line == self.last_line:
            return
        line_packet.send_one_line(self.conn, line)
        self.last_line = line

    def receive_lines(self):
        in_line = line_packet.receive_lines(self.conn)
        return in_line

    def non_blocking_receive_audio(self):
        try:
            r = self.conn.recv(self.PACKET_SIZE)
            return r
        except ConnectionResetError:
            return None

# wraps socket and ASR object, and serves one client connection. 
# next client should be served by a new instance of this object
class ServerProcessor:

    def __init__(self, c, online_asr_proc, min_chunk):
        self.connection = c
        self.online_asr_proc = online_asr_proc
        self.min_chunk = min_chunk

        self.last_end = None

        self.is_first = True

    def receive_audio_chunk(self):
        # receive all audio that is available by this time
        # blocks operation if less than self.min_chunk seconds is available
        # unblocks if connection is closed or a chunk is available
        out = []
        minlimit = self.min_chunk*SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            raw_bytes = self.connection.non_blocking_receive_audio()
            if not raw_bytes:
                break
#            print("received audio:",len(raw_bytes), "bytes", raw_bytes[:10])
            sf = soundfile.SoundFile(io.BytesIO(raw_bytes), channels=1,endian="LITTLE",samplerate=SAMPLING_RATE, subtype="PCM_16",format="RAW")
            audio, _ = librosa.load(sf,sr=SAMPLING_RATE,dtype=np.float32)
            out.append(audio)
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)

    def format_output_transcript(self,o):
        # output format in stdout is like:
        # 0 1720 Takhle to je
        # - the first two words are:
        #    - beg and end timestamp of the text segment, as estimated by Whisper model. The timestamps are not accurate, but they're useful anyway
        # - the next words: segment transcript

        # This function differs from whisper_online.output_transcript in the following:
        # succeeding [beg,end] intervals are not overlapping because ELITR protocol (implemented in online-text-flow events) requires it.
        # Therefore, beg, is max of previous end and current beg outputed by Whisper.
        # Usually it differs negligibly, by appx 20 ms.

        if o[0] is not None:
            beg, end = o[0]*1000,o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)

            self.last_end = end
            print("%1.0f %1.0f %s" % (beg,end,o[2]),flush=True,file=sys.stderr)
            return "%1.0f %1.0f %s" % (beg,end,o[2])
        else:
            logger.debug("No text in this segment")
            return None

    def send_result(self, o):
        msg = self.format_output_transcript(o)
        if msg is not None:
            self.connection.send(msg)

    def process(self):
        # handle one client connection
        self.online_asr_proc.init()
        while True:
            a = self.receive_audio_chunk()
            if a is None:
                break
            self.online_asr_proc.insert_audio_chunk(a)
            o = self.online_asr_proc.process_iter()
            try:
                self.send_result(o)
            except BrokenPipeError:
                logger.info("broken pipe -- connection closed?")
                break

#        o = self.online_asr_proc.finish()  # this should be working
#        self.send_result(o)

def check_shutdown_command():
    """Check if a shutdown command file exists"""
    if os.path.exists('shutdown.txt'):
        os.remove('shutdown.txt')  # Clean up the file
        return True
    return False

def main():
    parser = argparse.ArgumentParser()

    # server options
    parser.add_argument("--host", type=str, default='0.0.0.0')
    parser.add_argument("--port", type=int, default=43007)
    parser.add_argument("--warmup-file", type=str, dest="warmup_file", 
            help="The path to a speech audio wav file to warm up Whisper...")

    # options from whisper_online
    add_shared_args(parser)

    # Check if we should use interactive mode
    if len(sys.argv) == 1:  # No command line arguments provided
        summary = get_user_preferences()
        
        # Optional: Save to a log file
        log_file = "whisper_sessions.log"
        with open(log_file, "a") as f:
            f.write(f"\n=== Session Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(summary)
            f.write("="*50 + "\n")

    args = parser.parse_args()
    set_logging(args, logger, other="")

    size = args.model
    language = args.lan
    asr, online = asr_factory(args)
    min_chunk = args.min_chunk_size

    # warm up the ASR...
    msg = "Whisper is not warmed up. The first chunk processing may take longer."
    if args.warmup_file:
        if os.path.isfile(args.warmup_file):
            a = load_audio_chunk(args.warmup_file,0,1)
            asr.transcribe(a)
            logger.info("Whisper is warmed up.")
        else:
            logger.critical("The warm up file is not available. "+msg)
            sys.exit(1)
    else:
        logger.warning(msg)

    # Server loop
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((args.host, args.port))
            s.listen(1)
            logger.info('Listening on'+str((args.host, args.port)))
            logger.info('Press Ctrl+C or create "shutdown.txt" file to stop the server')
            
            while True:
                if check_shutdown_command():
                    logger.info('Shutdown command received, stopping server...')
                    break
                    
                try:
                    # Set a timeout so we can check for shutdown command periodically
                    s.settimeout(1.0)
                    conn, addr = s.accept()
                    s.settimeout(None)  # Reset timeout for normal operation
                    
                    logger.info('Connected to client on {}'.format(addr))
                    connection = Connection(conn)
                    proc = ServerProcessor(connection, online, args.min_chunk_size)
                    proc.process()
                    conn.close()
                    logger.info('Connection to client closed')
                except socket.timeout:
                    continue  # Check for shutdown command again
                except KeyboardInterrupt:
                    logger.info('Received interrupt, shutting down...')
                    break
                except Exception as e:
                    logger.error(f'Error processing connection: {str(e)}')
                    continue
                
    except KeyboardInterrupt:
        logger.info('Received interrupt, shutting down...')
    except Exception as e:
        logger.error(f'Server error: {str(e)}')
    finally:
        logger.info('Server shutdown complete')
        sys.exit(0)

if __name__ == "__main__":
    main()
