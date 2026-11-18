
#define MyAppName "STRUCTPIN"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "STRUCTPIN"
#define MyAppExeName "STRUCTPIN.exe"

[Setup]
AppId={{8C8B72A1-2D19-4F13-9E72-8C8B72A12D19}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\STRUCTPIN
DefaultGroupName=STRUCTPIN
OutputDir=output
OutputBaseFilename=STRUCTPIN-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\STRUCTPIN\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STRUCTPIN"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\STRUCTPIN"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch STRUCTPIN"; Flags: postinstall nowait skipifsilent
