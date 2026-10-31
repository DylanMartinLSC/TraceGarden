#define MyAppVersion "0.3.0"
[Setup]
AppId={{BF23298D-0696-4770-BDE4-9816E2AE0FE7}
AppName=TraceGarden
AppVersion={#MyAppVersion}
AppPublisher=TraceGarden contributors
AppPublisherURL=https://github.com/DylanMartinLSC/TraceGarden
DefaultDirName={localappdata}\Programs\TraceGarden
DefaultGroupName=TraceGarden
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TraceGarden-Windows-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\TraceGarden.exe
WizardStyle=modern
[Files]
Source: "..\dist\TraceGarden\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\TraceGarden"; Filename: "{app}\TraceGarden.exe"
Name: "{userdesktop}\TraceGarden"; Filename: "{app}\TraceGarden.exe"
[Run]
Filename: "{app}\TraceGarden.exe"; Description: "Open TraceGarden"; Flags: nowait postinstall skipifsilent
