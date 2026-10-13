{
  description = "VType Linux：微信拼音 Fcitx5 插件";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.zst";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      wxc = pkgs.callPackage ./nix/wxc.nix { };
      package = pkgs.callPackage ./nix/package.nix {
        inherit wxc;
        src = pkgs.lib.cleanSourceWith {
          src = self;
          filter = path: type: pkgs.lib.cleanSourceFilter path type
            && builtins.baseNameOf path != ".jj"
            && builtins.baseNameOf path != "__pycache__";
        };
      };
    in
    {
      packages.${system} = {
        inherit wxc;
        default = package;
        vtype-linux = package;
      };
      apps.${system} = {
        wxc = { type = "app"; program = "${wxc}/bin/wxc"; };
        wetype-demo = { type = "app"; program = "${package}/bin/wetype-demo"; };
        wetype-cloud = { type = "app"; program = "${package}/bin/wetype-cloud"; };
      };
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.cmake
          pkgs.fcitx5
          pkgs.pkg-config
          pkgs.openssl
          wxc
          (pkgs.python3.withPackages (ps: [ ps.cryptography ps.dbus-python ps.pygobject3 ]))
        ];
        WETYPE_SNAPPY_LIBRARY = "${pkgs.lib.getLib pkgs.snappy}/lib/libsnappy.so";
      };
      formatter.${system} = pkgs.nixpkgs-fmt;
    };
}
