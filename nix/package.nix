{ lib, stdenv, fetchurl, cmake, fcitx5, pkgsStatic, python3, unzip, patchelf, zlib, openssl, snappy, wxc, writeShellScript, src }:

let
  python = python3.withPackages (ps: [ ps.cryptography ps.python-snappy ]);
  cloudPython = writeShellScript "wetype-cloud-python" ''
    export PATH="${lib.makeBinPath [ openssl wxc ]}:$PATH"
    export WETYPE_WXC="''${WETYPE_WXC:-${wxc}/bin/wxc}"
    export WETYPE_SNAPPY_LIBRARY="${lib.getLib snappy}/lib/libsnappy.so"
    exec ${python}/bin/python3 "$@"
  '';
  version = "0-unstable";
  ndk = fetchurl {
    url = "https://dl.google.com/android/repository/android-ndk-r27c-linux.zip";
    hash = "sha256-WcL23JZ0O12vXRYmaEZAsgpr0rHYWxMVa5AzN0G61cw=";
  };
  harness = stdenv.mkDerivation {
    pname = "vtype-linux-harness";
    inherit version src;
    nativeBuildInputs = [ unzip patchelf ];
    dontConfigure = true;
    # 宿主程序面向 Android/bionic，不能用本机的 strip 和 ELF 修复钩子处理。
    dontFixup = true;
    buildPhase = ''
      runHook preBuild
      unzip -q ${ndk} 'android-ndk-r27c/toolchains/llvm/prebuilt/linux-x86_64/*'
      toolchain="$PWD/android-ndk-r27c/toolchains/llvm/prebuilt/linux-x86_64"
      for tool in clang ld.lld; do
        patchelf --set-interpreter ${stdenv.cc.bintools.dynamicLinker} \
          --add-rpath ${lib.makeLibraryPath [ zlib ]} \
          "$(readlink -f "$toolchain/bin/$tool")"
      done
      "$toolchain/bin/clang" --target=aarch64-linux-android28 -O0 -g \
        -o wetype-harness harness/jinterop.c -ldl
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      install -Dm755 wetype-harness "$out/libexec/wetype-harness"
      runHook postInstall
    '';
  };
in
stdenv.mkDerivation {
  pname = "vtype-linux";
  inherit version src;

  nativeBuildInputs = [ cmake ];
  buildInputs = [ fcitx5 ];
  cmakeDir = "../fcitx5-wetype";
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ctest --output-on-failure
    (cd .. && ${cloudPython} -m unittest discover -s tests -p 'test_*.py')
    (cd .. && ${cloudPython} tests/test_snapshot_transport.py)
    runHook postCheck
  '';

  postPatch = ''
    # 上游的云代理入口使用 /usr/bin/python3；NixOS 使用固定的运行时。
    substituteInPlace fcitx5-wetype/src/wetype.cpp \
      --replace-fail '"/usr/bin/python3"' '"${cloudPython}"' \
      --replace-fail '(eng + "/wetype-harness").c_str()' '"${harness}/libexec/wetype-harness"' \
      --replace-fail '(eng+"/wetype-harness").c_str()' '"${harness}/libexec/wetype-harness"'
  '';

  postInstall = ''
    # profile 安装的插件不在 Fcitx 的默认库目录，使用绝对路径注册。
    substituteInPlace "$out/share/fcitx5/addon/wetype.conf" \
      --replace-fail 'Library=libfcitx5-wetype' "Library=$out/lib/fcitx5/libfcitx5-wetype"
    mkdir -p "$out/libexec"
    ln -s ${pkgsStatic.qemu-user}/bin/qemu-aarch64 "$out/libexec/qemu-aarch64-static"
    ln -s ${harness}/libexec/wetype-harness "$out/libexec/wetype-harness"
    install -Dm644 ../src/wetype-ime-demo.sh "$out/share/vtype-linux/wetype-ime-demo.sh"
    cp -r ../cloud "$out/share/vtype-linux/cloud"
    install -Dm644 ../scripts/wetype-cloud.py "$out/share/vtype-linux/wetype-cloud.py"
    mkdir -p "$out/bin"
    ln -s ${wxc}/bin/wxc "$out/bin/wxc"
    cat > "$out/bin/wetype-demo" <<'EOF'
    #!${stdenv.shell}
    export WETYPE_ENGINE_DIR="''${WETYPE_ENGINE_DIR:-$HOME/.local/lib/wetype-ime/arm64}"
    export WETYPE_HARNESS="${harness}/libexec/wetype-harness"
    exec ${stdenv.shell} "@out@/share/vtype-linux/wetype-ime-demo.sh" "$@"
    EOF
    cat > "$out/bin/wetype-cloud" <<'EOF'
    #!${stdenv.shell}
    exec ${cloudPython} "@out@/share/vtype-linux/wetype-cloud.py" "$@"
    EOF
    chmod +x "$out/bin/wetype-demo" "$out/bin/wetype-cloud"
    substituteInPlace "$out/bin/wetype-demo" --replace-fail '@out@' "$out"
    substituteInPlace "$out/bin/wetype-cloud" --replace-fail '@out@' "$out"
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    ${cloudPython} ../nix/check-wxc.py --package "$out" --wxc ${wxc}/bin/wxc
    runHook postInstallCheck
  '';

  meta = {
    description = "微信拼音 Fcitx5 插件（引擎和词库需另行下载到用户目录）";
    homepage = "https://github.com/zhl-HFUT/vtype-linux";
    license = lib.licenses.gpl3Only;
    platforms = [ "x86_64-linux" ];
  };
}
