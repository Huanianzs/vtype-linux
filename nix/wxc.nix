{
  lib,
  rustPlatform,
  fetchFromGitHub,
  pkg-config,
  protobuf,
  openssl,
  versionCheckHook,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "wxc";
  version = "0.1.0";

  src = fetchFromGitHub {
    owner = "mkdir700";
    repo = "wx-ime-sdk";
    tag = "v${finalAttrs.version}";
    hash = "sha256-QR1fruu/+6Ol2iixo6ETAY+laXKM59gynVKu8hewGHs=";
  };

  cargoHash = "sha256-vAyUKGWkews7Crp77x24Ly3PqvEEeD1+O5IY9hD8QPo=";
  cargoBuildFlags = [ "--package=wxc" ];
  cargoTestFlags = [ "--workspace" ];

  nativeBuildInputs = [
    pkg-config
    protobuf
  ];
  buildInputs = [ openssl ];

  doInstallCheck = true;
  nativeInstallCheckInputs = [ versionCheckHook ];

  meta = {
    description = "微信输入法设备关联与剪贴板命令行客户端";
    homepage = "https://github.com/mkdir700/wx-ime-sdk";
    license = lib.licenses.asl20;
    mainProgram = "wxc";
    platforms = lib.platforms.linux;
  };
})
