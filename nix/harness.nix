{
  lib,
  stdenv,
  androidNdk,
  src,
  version,
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "vtype-linux-harness";
  inherit version src;

  strictDeps = true;
  __structuredAttrs = true;

  nativeBuildInputs = [ androidNdk.binaries ];
  dontConfigure = true;
  # 交叉编译产物不能用本机 strip/patchelf；调试信息用 NDK 自带工具清理。
  dontPatchELF = true;
  dontStrip = true;

  buildPhase = ''
    runHook preBuild
    ${finalAttrs.passthru.clang} -O2 -g0 -o wetype-harness harness/jinterop.c -ldl
    ${finalAttrs.passthru.clang} -shared -fPIC -O2 -Wl,-soname,libandroid${stdenv.hostPlatform.extensions.sharedLibrary} -o libandroid${stdenv.hostPlatform.extensions.sharedLibrary} shim/libandroid.c
    ${finalAttrs.passthru.clang} -shared -fPIC -O2 -Wall -o libwetype-cloud${stdenv.hostPlatform.extensions.sharedLibrary} cloud/cloud_net.c
    ${androidNdk.binaries}/bin/llvm-strip --strip-all wetype-harness lib{android,wetype-cloud}${stdenv.hostPlatform.extensions.sharedLibrary}
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 wetype-harness -t "$out/libexec"
    install -Dm755 lib{android,wetype-cloud}${stdenv.hostPlatform.extensions.sharedLibrary} -t "$out/lib"
    runHook postInstall
  '';

  passthru = {
    apiLevel = "28";
    clang = "${androidNdk.binaries}/bin/aarch64-linux-android${finalAttrs.passthru.apiLevel}-clang";
  };

  meta = {
    description = "微信拼音 Android/bionic 宿主与桥接库";
    license = lib.licenses.gpl3Only;
    platforms = [ "x86_64-linux" ];
  };
})
