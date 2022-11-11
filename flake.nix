{
  description = "WebUI for brother QL label printers";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    pyproject = nixpkgs.lib.importTOML ./pyproject.toml;
    pname = pyproject.tool.poetry.name;

    python3Overlay = final: prev:
      prev.buildPythonPackage {
        inherit pname;
        inherit (pyproject.tool.poetry) version;
        format = "pyproject";

        src = nixpkgs.lib.sources.sourceFilesBySuffices ./. [".py" ".toml"];

        nativeBuildInputs = [
          prev.poetry-core
        ];

        propagatedBuildInputs = [
          prev.bottle
          prev.brother-ql
          prev.jinja2
          prev.systemd
        ];

        pythonImportsCheck = [
          pname
        ];

        meta = with nixpkgs.lib; {
          inherit (pyproject.tool.poetry) description;
          homepage = pyproject.tool.poetry.repository;
          license = with licenses; [gpl3];
        };
      };

    overlay = final: prev: rec {
      python3 = prev.python3.override {
        packageOverrides = final: prev: {
          brother_ql_web = python3Overlay final prev;
        };
      };
      python3Packages = python3.pkgs;
    };

    pkgs = import nixpkgs {
      system = "x86_64-linux";
      overlays = [overlay];
    };
  in {
    overlays = {
      default = overlay;
      python3 = python3Overlay;
    };

    formatter.x86_64-linux = pkgs.alejandra;

    packages.x86_64-linux.default = pkgs.python3Packages.brother_ql_web;

    nixosModules.default = import ./module.nix;

    checks.x86_64-linux = let
      nixSrc = nixpkgs.lib.sources.sourceFilesBySuffices ./. [".nix"];
      pySrc = nixpkgs.lib.sources.sourceFilesBySuffices ./. [".py"];
    in {
      pkg = self.packages.x86_64-linux.default;

      black = pkgs.runCommand "black" {} ''
        ${pkgs.python3Packages.black}/bin/black --config ${./pyproject.toml} ${pySrc}
        touch $out
      '';

      flake8 =
        pkgs.runCommand "flake8"
        {
          buildInputs = with pkgs.python3Packages; [
            flake8
            flake8-bugbear
            pep8-naming
          ];
        }
        ''
          flake8 --max-line-length 88 ${pySrc}
          touch $out
        '';

      alejandra = pkgs.runCommand "alejandra" {} ''
        ${pkgs.alejandra}/bin/alejandra --check ${nixSrc}
        touch $out
      '';

      statix = pkgs.runCommand "statix" {} ''
        ${pkgs.statix}/bin/statix check ${nixSrc}
        touch $out
      '';
    };
  };
}
