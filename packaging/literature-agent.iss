#ifndef AppVersion
  #define AppVersion "0.3.0-rc.3"
#endif
#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif

[Setup]
AppId={{7A27D50A-4AF1-49D5-A064-FCB5F56AB815}
AppName=Literature Agent
AppVersion={#AppVersion}
AppPublisher=Literature Agent
AppPublisherURL=https://github.com/EdwardAiyw/literature-agent
DefaultDirName={localappdata}\Programs\Literature Agent
DefaultGroupName=Literature Agent
OutputDir={#ProjectRoot}\release
OutputBaseFilename=Literature-Agent-{#AppVersion}-Windows-x64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\LiteratureAgent.exe
WizardStyle=modern

[Files]
Source: "{#ProjectRoot}\release\stage\LiteratureAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Literature Agent"; Filename: "{app}\LiteratureAgent.exe"
Name: "{group}\卸载 Literature Agent"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LiteratureAgent.exe"; Description: "启动 Literature Agent"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\register-windows-task.ps1"" -Unregister"; Flags: runhidden; RunOnceId: "RemoveDailyTask"
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\register-local-startup.ps1"" -Unregister"; Flags: runhidden; RunOnceId: "RemoveStartupTask"
