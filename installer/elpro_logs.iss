; Copyright (c) 2026 Geoazimut SàRL. Tous droits réservés.
; Installateur ELPRO Logs (Inno Setup 6) — installation pour tous les utilisateurs
#define AppName "ELPRO Logs"
#define AppPublisher "GeoAzimut"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
; Identifiant unique de l'application : NE JAMAIS LE CHANGER (sert aux mises à jour et à la désinstallation).
; Différent de celui d'ELPRO Config : les deux applications s'installent et se désinstallent séparément.
AppId={{03F29B91-B96E-4D63-88AB-3F452B5FC18C}
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
OutputBaseFilename=ELPRO_Logs_Setup_{#AppVersion}
SetupIconFile=..\resources\app_icon.ico
UninstallDisplayIcon={app}\ELPRO Logs.exe
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; L'application doit être fermée avant une mise à jour
CloseApplications=yes
; La base Documents\ELPRO Logs\elpro_logs.db appartient à l'utilisateur : la désinstallation ne la touche pas
; Mentions légales
AppCopyright=© 2026 Geoazimut SàRL. Tous droits réservés.
AppPublisherURL=https://geoazimut.com
AppSupportURL=https://geoazimut.com
AppUpdatesURL=https://github.com/lucapancottigz/elpro-logs/releases
VersionInfoCompany=Geoazimut SàRL
VersionInfoCopyright=© 2026 Geoazimut SàRL. Tous droits réservés.
VersionInfoDescription=Installateur ELPRO Logs
VersionInfoProductName=ELPRO Logs
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
Source: "..\dist\ELPRO Logs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licence et composants tiers, lisibles dans le dossier d'installation
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; {autodesktop} / {autoprograms} = bureau et menu Démarrer communs (tous les utilisateurs)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ELPRO Logs.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autoprograms}\{#AppPublisher}\{#AppName}"; Filename: "{app}\ELPRO Logs.exe"; WorkingDir: "{app}"; Tasks: startmenuicon

[Run]
; Proposer de lancer l'application à la fin de l'installation
Filename: "{app}\ELPRO Logs.exe"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent
