; Copyright (c) 2026 Geoazimut SàRL. Tous droits réservés.
; Installateur ELPRO Config (Inno Setup 6) — installation pour tous les utilisateurs
#define AppName "ELPRO Config"
#define AppPublisher "GeoAzimut"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
; Identifiant unique de l'application : NE JAMAIS LE CHANGER (sert aux mises à jour et à la désinstallation)
AppId={{F6B9958C-CE5D-42AC-825C-19E6DB311BD8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppPublisher}\{#AppName}
DefaultGroupName={#AppPublisher}
DisableProgramGroupPage=yes
; Installation générale (tous les utilisateurs) : droits administrateur obligatoires
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=ELPRO_Config_Setup_{#AppVersion}
SetupIconFile=..\resources\app_icon.ico
UninstallDisplayIcon={app}\ELPRO Config.exe
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; L'application doit être fermée avant une mise à jour
CloseApplications=yes
; Mentions légales
AppCopyright=© 2026 Geoazimut SàRL. Tous droits réservés.
AppPublisherURL=https://geoazimut.com
AppSupportURL=https://geoazimut.com
AppUpdatesURL=https://github.com/lucapancottigz/elpro-config/releases
VersionInfoCompany=Geoazimut SàRL
VersionInfoCopyright=© 2026 Geoazimut SàRL. Tous droits réservés.
VersionInfoDescription=Installateur ELPRO Config
VersionInfoProductName=ELPRO Config
; Page « Contrat de licence » : l'utilisateur doit accepter avant d'installer
LicenseFile=..\build\LICENSE.txt

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
; Deux cases, cochées par défaut (absence du drapeau « unchecked »)
Name: "desktopicon"; Description: "Créer une icône sur le bureau"; GroupDescription: "Raccourcis :"
Name: "startmenuicon"; Description: "Créer un raccourci dans le menu Démarrer"; GroupDescription: "Raccourcis :"

[Files]
; Tout le dossier produit par PyInstaller
Source: "..\dist\ELPRO Config\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licence et composants tiers, lisibles dans le dossier d'installation
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; {autodesktop} / {autoprograms} = bureau et menu Démarrer communs (tous les utilisateurs)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ELPRO Config.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autoprograms}\{#AppPublisher}\{#AppName}"; Filename: "{app}\ELPRO Config.exe"; WorkingDir: "{app}"; Tasks: startmenuicon

[Run]
; Proposer de lancer l'application à la fin de l'installation
Filename: "{app}\ELPRO Config.exe"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent
