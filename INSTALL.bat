:: FOR WINDOWS
git clone https://github.com/code-switched/whisper_captions.git
cd .\whisper_captions\
py -3.10 -m venv --prompt "whcap" venv
.\venv\Scripts\python -m pip install --upgrade pip wheel setuptools
.\venv\Scripts\activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install librosa soundfile faster-whisper pyaudio

:: Create shortcut with proper command prompt settings
powershell "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%userprofile%\Desktop\LIVE Captions Server.lnk'); $SC.TargetPath = 'cmd.exe'; $SC.Arguments = '/k """%~dp0server-connect-captions.bat"""'; $SC.WorkingDirectory = '%~dp0'; $SC.Save()"