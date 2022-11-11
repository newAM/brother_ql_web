# brother_ql_web

[![CI](https://github.com/newAM/brother_ql_web/actions/workflows/ci.yml/badge.svg)](https://github.com/newAM/brother_ql_web/actions/workflows/ci.yml)
[![black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A fork of [pklaus/brother_ql_web](https://github.com/pklaus/brother_ql_web) for use with NixOS.

## Usage

This is a pretty niche application, and I do not expect other people to use this.
Please open an issue if you want more detailed instructions!

1. Add this flake to your flake inputs.
2. Add `overlays.default` to your nixpkgs overlays.
3. Add `nixosModules.default` to your NixOS module imports.
4. See [module.nix](./module.nix) for configuration options.
