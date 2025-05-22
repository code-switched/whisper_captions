# Installation Guide for whisper captions (Linux/Ubuntu)

This guide provides the necessary command-line steps to set up and install the `whisper_captions` project from scratch on a Linux system (specifically tested on Ubuntu 24.04).

## Quick Navigation

- [Linux/Ubuntu Installation](#installation-steps)
- [Windows Installation](#windows-installation-guide)
- [Ubuntu 24.04 with CUDA 11.8](#ubuntu-2404-installation-guide-with-cuda-118)
- [Troubleshooting](#troubleshooting)

## Prerequisites

* A Linux system (Ubuntu 20.04+, Debian 11+, etc.)
* `sudo` access for installing system packages.
* `git` installed.
* Basic build tools (usually included or installed automatically).

## Installation Steps

1. **Clone the Repository:**
   Navigate to the directory where you want to clone the project and run:

   ```bash
   git clone https://github.com/code-switched/whisper_captions/
   ```

2. **Navigate into the Project Directory:**

   ```bash
   cd whisper_captions
   ```

3. **Install Required System Packages:**
   Some Python dependencies require system libraries to compile. This project specifically needs Python 3.10 (which may not be default on newer Ubuntu versions) and the PortAudio development libraries.

   Add the deadsnakes PPA to get Python 3.10 (if not already available):

   ```bash
   sudo add-apt-repository ppa:deadsnakes/ppa
   ```

   Update your package list:

   ```bash
   sudo apt update
   ```

   Install Python 3.10, its venv module, development headers, and the PortAudio development libraries:

   ```bash
   sudo apt install python3.10 python3.10-venv python3.10-dev portaudio19-dev
   ```

   *Note: `sudo` is required for installing system packages.*

4. **Create and Activate a Python Virtual Environment:**
   It's best practice to install Python dependencies in a virtual environment to avoid conflicts with system-wide packages.

   ```bash
   python3.10 -m venv --prompt captions venv
   ```

   Activate the environment:

   ```bash
   source venv/bin/activate
   ```

   *(Your prompt should change to indicate the active environment, e.g., `(captions) your_user@your_host:...`)*

5. **Upgrade Core Packaging Tools:**
   Ensure you have the latest versions of `pip`, `wheel`, and `setuptools` within your virtual environment.

   ```bash
   ./venv/bin/python -m pip install --upgrade pip wheel setuptools
   ```

   *Note: Using `./venv/bin/python -m pip` explicitly calls the pip inside the virtual environment, even if it's not activated.*

6. **Install Python Dependencies:**
   Install the project's Python dependencies. Torch is installed separately using a specific index URL for CUDA 11.8 compatibility.

   Install Torch with CUDA support:

   ```bash
   ./venv/bin/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

   Install other dependencies including `librosa`, `soundfile`, `faster-whisper`, and `pyaudio`:

   ```bash
   ./venv/bin/python -m pip install librosa soundfile faster-whisper pyaudio
   ```

   Install `whisper-timestamped` directly from the Git repository:

   ```bash
   ./venv/bin/python -m pip install git+https://github.com/linto-ai/whisper-timestamped
   ```

## Post-Installation

Once the installation is complete, your virtual environment contains all the necessary Python packages. You can now run the project's scripts using the Python interpreter inside the virtual environment (e.g., `./venv/bin/python your_script.py`) or by activating the environment first (`source venv/bin/activate`) and then running `python your_script.py`.

## Post Mortem

It took me quite a bit to actually get this working. On Windows Python will automatically handle the CUDA 11 thing even though CUDA 12 is installed. I also dont have issues with the cuDNN thing on Windows. I will give an overview of steps I took and the issues I ran into.

Installing CUDA 11.8 on Ubuntu 24.04 was weird:
Resources:
- https://forums.developer.nvidia.com/t/how-to-install-cuda-11-08-on-ubuntu-24-04/294033
- https://developer.nvidia.com/cuda-11-8-0-download-archive?target_os=Linux&target_arch=x86_64&Distribution=Ubuntu&target_version=22.04&target_type=runfile_local

What I ended up doing was using the .run file for CUDA Toolkit 11.8 for Ubuntu 22.04. Once downloaded it required me to install gcc-11 and g++-11. Then I had to temporarily change the symlink for gcc and g++ to point to the old 11 versions. Only then would the installer run.
It was suggested online to use the option to override the gcc check but that is not a good idea in my opinion.
I had to heavily customize the .run file installer to make sure it did not create a new symlink for CUDA 11.8 and make sure it did not install the CUDA drivers. As long as you explore all options and mostly stick to the barebones Toolkit you should be fine.

Even after getting the right version of CUDA installed the pytorch script for whisper captions kept saying it could not find the cuDNN version of 9.1.0 - 
What really helped was ssage suggesting that I run a command that showed LD_DEBUG:
`LD_DEBUG=libs CUDA_HOME=/usr/local/cuda-11.8 PATH=/usr/local/cuda-11.8/bin:$PATH ./venv/bin/python whisper_online_server.py`

that command is priceless, esepcially when using ssage and giving it access to your history via tmux. it solved something i would have never caught using copy paste back and forth to perplexity or chatgpt.

So I went down the rabbit hole of downloading the binaries and installing them system wide but it seemed like a lot to do for one project. Or just didnt want to mess up anything else in terms of libcudnn_ops.so

cuDNN Archive:
- https://developer.nvidia.com/rdp/cudnn-archive

I stumbled across an article that detailed using pip install to get the cudnn so libs installed. Lightbulb moment.

Resources:
- https://www.cnblogs.com/kevinarcsin001/p/18545837
- https://pypi.org/project/nvidia-cudnn-cu11/9.1.0.70/

After a lot of back and forth with ssage and inspect the site-packages directory we figured out that nvidia-cudnn-cu11 was actually already installed!
We just needed to specify the path to the cudnn so libs in the LD_LIBRARY_PATH environment variable. Another thing that Windows handled natively.
Actually thinking back I'm not really sure if I need to be specifying the whole CUDA 11.8 thing, maybe 12 would do just fine. I'll test that out.

But ultimately we had to specify a bunch of environment variables to get the pytorch script to work.

```sh
LD_LIBRARY_PATH="./venv/lib/python3.10/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH" CUDA_HOME="/usr/local/cuda-11.8" PATH="/usr/local/cuda-11.8/bin:$PATH" ./venv/bin/python whisper_online_server.py
```

I created START.sh and then aliased that to `captions` via .zprofile so i could just easily run this and get everything started.

NOTE: i just tried to run the script without specifying the CUDA env vars and it actually worked so maybe all this extra effort to get CUDA 11.8 installed was not necessary. Even so, I now have 11.8 on 24.04 and can use it in the future if need be. I do get the feeling that almost all my old projects are good because CUDA 12 is so good at being backwards compatible.

BUT this does not apply to the LD LIBRARY variable lol, that one is still necessary. Even if the venv is activated it still wont find the proper libcudnn_ops.so files without that env. I'm still not sure why it works automatically on Windows and not on Ubuntu but maybe a journey for another day.

Learned alot here :D

## Windows Installation Guide

If you're installing on Windows, the process is simpler as Windows Python handles CUDA compatibility more automatically:

1. **Ensure NVIDIA Drivers are Installed**
   - Install the latest NVIDIA drivers for your GPU
   - CUDA 12 works fine and handles backward compatibility well

2. **Create a Python Virtual Environment**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```powershell
   pip install --upgrade pip wheel setuptools
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
   pip install librosa soundfile faster-whisper pyaudio
   pip install git+https://github.com/linto-ai/whisper-timestamped
   ```

4. **Run the Application**
   ```powershell
   python whisper_online_server.py
   ```

## Ubuntu 24.04 Installation Guide (with CUDA 11.8)

Installing on Ubuntu 24.04 requires some additional steps, especially for CUDA 11.8 compatibility:

1. **Install CUDA 11.8**
   - Download the runfile installer for Ubuntu 22.04 from [NVIDIA CUDA Archive](https://developer.nvidia.com/cuda-11-8-0-download-archive?target_os=Linux&target_arch=x86_64&Distribution=Ubuntu&target_version=22.04&target_type=runfile_local)
   - Install gcc-11 and g++-11:
     ```bash
     sudo apt install gcc-11 g++-11
     ```
   - Temporarily update gcc/g++ symlinks:
     ```bash
     sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 11
     sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 11
     sudo update-alternatives --set gcc /usr/bin/gcc-11
     sudo update-alternatives --set g++ /usr/bin/g++-11
     ```
   - Run the installer with customizations:
     ```bash
     sudo sh cuda_11.8.0_520.61.05_linux.run
     ```
     - Choose custom installation
     - Select only the CUDA Toolkit components
     - Deselect driver installation
     - Deselect creating symlinks (to avoid conflicts)

2. **Follow Standard Installation Steps**
   - Complete steps 1-6 from the Linux installation guide above

3. **Configure Environment Variables**
   - Create a startup script (START.sh):
     ```bash
     #!/bin/bash
     
     # Set up environment variables for CUDA and cuDNN
     # NOTE: The LD_LIBRARY_PATH is ESSENTIAL even if CUDA environment vars might not be needed
     export LD_LIBRARY_PATH="$HOME/PATH/TO/whisper_captions/venv/lib/python3.10/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH"
     export CUDA_HOME="/usr/local/cuda-11.8"
     export PATH="/usr/local/cuda-11.8/bin:$PATH"
     
     # Run the application
     ./venv/bin/python whisper_online_server.py
     ```
   - Make it executable:
     ```bash
     chmod +x START.sh
     ```
   - Optional: Add an alias to your shell profile (.bashrc or .zprofile):
     ```bash
     echo 'alias captions="cd /PATH/TO/whisper_captions && ./START.sh"' >> ~/.bashrc
     source ~/.bashrc
     ```

4. **Note on cuDNN**
   - The nvidia-cudnn-cu11 package should be automatically installed with PyTorch
   - If you encounter cuDNN errors, you may need to explicitly install:
     ```bash
     pip install nvidia-cudnn-cu11==9.1.0.70
     ```

## Troubleshooting

- If you encounter library loading errors, use LD_DEBUG to investigate:
  ```bash
  LD_DEBUG=libs CUDA_HOME=/usr/local/cuda-11.8 PATH=/usr/local/cuda-11.8/bin:$PATH ./venv/bin/python whisper_online_server.py
  ```

- While the CUDA_HOME and PATH environment variables might not always be necessary (as CUDA 12 has good backward compatibility), the LD_LIBRARY_PATH pointing to the cuDNN libraries is essential on Ubuntu. Windows handles this path resolution automatically, but Linux requires explicit path specification.

- Try running with just the LD_LIBRARY_PATH set:
  ```bash
  export LD_LIBRARY_PATH="$HOME/PATH/TO/whisper_captions/venv/lib/python3.10/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH"
  ./venv/bin/python whisper_online_server.py
  ```
