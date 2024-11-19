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

logger = logging.getLogger(__name__)

# setting whisper object by args 
SAMPLING_RATE = 16000

def get_user_preferences():
    # Default values
    defaults = {
        "model": "medium",
        "backend": "faster-whisper",
        "host": "0.0.0.0",
        "port": 43007,
        "warmup_file": "./jfk.wav",
        "language": "en",
        "vac": True,
        "vad": True,
        "min_chunk_size": 0.25,
        "log_level": "INFO"
    }

    # Available models and backends
    models = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]
    backends = ["faster-whisper", "whisper_timestamped", "openai-api"]
    log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    print("\n=== Whisper Streaming Configuration ===")
    
    # Model selection
    print("\nAvailable models:")
    for i, model in enumerate(models, 1):
        print(f"{i}. {model}")
    while True:
        choice = input(f"\nSelect a model (1-{len(models)}) [default: medium]: ").strip()
        if not choice:
            selected_model = defaults["model"]
            break
        try:
            choice = int(choice)
            if 1 <= choice <= len(models):
                selected_model = models[choice-1]
                break
            print(f"Invalid choice. Please select a number between 1 and {len(models)}.")
        except ValueError:
            print("Please enter a valid number.")

    # Backend selection
    print("\nAvailable backends:")
    for i, backend in enumerate(backends, 1):
        print(f"{i}. {backend}")
    while True:
        choice = input(f"\nSelect a backend (1-{len(backends)}) [default: faster-whisper]: ").strip()
        if not choice:
            selected_backend = defaults["backend"]
            break
        try:
            choice = int(choice)
            if 1 <= choice <= len(backends):
                selected_backend = backends[choice-1]
                break
            print(f"Invalid choice. Please select a number between 1 and {len(backends)}.")
        except ValueError:
            print("Please enter a valid number.")

    # Host
    host = input(f"\nEnter host address [default: {defaults['host']}]: ").strip()
    host = host if host else defaults["host"]

    # Port
    port_input = input(f"\nEnter port number [default: {defaults['port']}]: ").strip()
    port = int(port_input) if port_input else defaults["port"]

    # Warmup file
    warmup_file = input(f"\nEnter warmup file path [default: {defaults['warmup_file']}]: ").strip()
    warmup_file = warmup_file if warmup_file else defaults["warmup_file"]

    # Language
    language = input(f"\nEnter language code (e.g., en, de, cs, or 'auto') [default: {defaults['language']}]: ").strip()
    language = language if language else defaults["language"]

    # VAC
    vac = input("\nEnable Voice Activity Controller (VAC)? (Y/n) [default: Y]: ").strip().lower()
    vac = vac != 'n'

    # VAD
    vad = input("\nEnable Voice Activity Detection (VAD)? (Y/n) [default: Y]: ").strip().lower()
    vad = vad != 'n'

    # Chunk size
    chunk_size = input(f"\nEnter minimum chunk size in seconds [default: {defaults['min_chunk_size']}]: ").strip()
    chunk_size = float(chunk_size) if chunk_size else defaults["min_chunk_size"]

    # Log level
    print("\nAvailable log levels:")
    for i, level in enumerate(log_levels, 1):
        print(f"{i}. {level}")
    while True:
        choice = input(f"\nSelect log level (1-{len(log_levels)}) [default: INFO]: ").strip()
        if not choice:
            selected_log_level = defaults["log_level"]
            break
        try:
            choice = int(choice)
            if 1 <= choice <= len(log_levels):
                selected_log_level = log_levels[choice-1]
                break
            print(f"Invalid choice. Please select a number between 1 and {len(log_levels)}.")
        except ValueError:
            print("Please enter a valid number.")

    # Get the machine's IP address
    try:
        # This creates a temporary socket to get the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't actually connect, just helps get local IP
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "IP Unknown"

    # Create sys.argv with the selected options
    sys.argv = [sys.argv[0]]
    sys.argv.extend(["--model", selected_model])
    sys.argv.extend(["--backend", selected_backend])
    sys.argv.extend(["--host", host])
    sys.argv.extend(["--port", str(port)])
    sys.argv.extend(["--warmup-file", warmup_file])
    sys.argv.extend(["--lan", language])
    if vac:
        sys.argv.append("--vac")
    if vad:
        sys.argv.append("--vad")
    sys.argv.extend(["--min-chunk-size", str(chunk_size)])
    sys.argv.extend(["--log-level", selected_log_level])

    # Create a summary of selected options
    summary = f"""
=== Configuration Summary ===
Server IP: {local_ip}
Model: {selected_model}
Backend: {selected_backend}
Host: {host}
Port: {port}
Warmup File: {warmup_file}
Language: {language}
VAC: {'Enabled' if vac else 'Disabled'}
VAD: {'Enabled' if vad else 'Disabled'}
Chunk Size: {chunk_size}
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
