; ============================================================================
;  DME Innovation Tools - Windows installer (Inno Setup 6)
;
;  Build:  build_installer.bat        (from the repository root)
;  or:     ISCC.exe /DAppVersion=1.0.0 installer\dme-innovation-tools.iss
;
;  Expects the three PyInstaller builds in ..\dist:
;      DME Innovation Tools.exe   (launcher)
;      AutoTuner Backup Tool.exe
;      MHD Lock Tool.exe
; ============================================================================

#ifndef AppVersion
  #define AppVersion "1.4.1"
#endif

#define AppName      "DME Innovation Tools"
#define AppPublisher "DME Innovation"
#define AppURL       "https://github.com/dmeinnovation777-droid/Tools"
#define LauncherExe  "DME Innovation Tools.exe"
#define AutoTunerExe "AutoTuner Backup Tool.exe"
#define MhdLockExe   "MHD Lock Tool.exe"
#define SourceDir    "..\dist"

[Setup]
AppId={{6720D8C7-002C-56FA-A655-7B4720E0E2B9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup

DefaultDirName={autopf}\DME Innovation\Tools
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

; Per-user by default (no UAC prompt); the wizard offers an all-users install.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir={#SourceDir}
OutputBaseFilename=DME-Innovation-Tools-Setup-{#AppVersion}
SetupIconFile=..\assets\dme-icon.ico
UninstallDisplayIcon={app}\{#LauncherExe}
UninstallDisplayName={#AppName} {#AppVersion}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto

[Languages]
Name: "german";  MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
german.CreateDesktopIcon=Desktop-Verknuepfung anlegen
german.ToolsGroup=Werkzeuge
english.CreateDesktopIcon=Create a desktop shortcut
english.ToolsGroup=Tools

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\{#LauncherExe}";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\{#AutoTunerExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\{#MhdLockExe}";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";                 DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";      Filename: "{app}\{#LauncherExe}"
Name: "{group}\{#AutoTunerExe}"; Filename: "{app}\{#AutoTunerExe}"
Name: "{group}\{#MhdLockExe}";   Filename: "{app}\{#MhdLockExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#LauncherExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#LauncherExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

; Settings live in %APPDATA%\DME Innovation and are intentionally kept on
; uninstall, so a reinstall finds the configured MHD builder path again.
