{
  lib,
  stdenvNoCC,
  androidenv,
  e2fsprogs,
  src,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "vtype-linux-bionic";
  version = "android-9";
  inherit src;

  strictDeps = true;
  nativeBuildInputs = [ e2fsprogs ];
  dontConfigure = true;
  dontStrip = true;
  dontPatchELF = true;

  buildPhase = ''
    runHook preBuild
    WETYPE_AOSP_IMAGE_DIR=${finalAttrs.passthru.systemImage}/libexec/android-sdk/system-images/android-${finalAttrs.passthru.androidPlatformVersion}/default/arm64-v8a \
      bash scripts/prepare_bionic.sh "$PWD/sysroot"
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    cp -a sysroot "$out"
    runHook postInstall
  '';

  passthru = {
    androidPlatformVersion = "28";
    androidPackages = androidenv.composeAndroidPackages {
      platformVersions = [ finalAttrs.passthru.androidPlatformVersion ];
      includeSystemImages = true;
      systemImageTypes = [ "default" ];
      abiVersions = [ "arm64-v8a" ];
      includeCmake = false;
    };
    systemImage = lib.head finalAttrs.passthru.androidPackages.system-images;
  };

  meta = {
    description = "微信拼音所需的 Android 9 ARM64 运行库";
    homepage = "https://source.android.com/";
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
    license = with lib.licenses; [
      asl20
      bsd2
      bsd3
      mit
      zlib
    ];
    platforms = lib.platforms.linux;
  };
})
