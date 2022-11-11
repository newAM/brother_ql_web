{
  config,
  lib,
  pkgs,
  ...
}: let
  cfg = config.services.brother_ql_web;
in {
  options.services.brother_ql_web = with lib; {
    enable = mkEnableOption "brother_ql_web";

    host = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Address of the webserver.";
    };

    port = mkOption {
      type = types.ints.u16;
      default = 8013;
      description = "Port of the web server.";
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Open the web server port in the firewall.";
    };

    printerModel = mkOption {
      type = types.str;
      description = "Printer model.";
    };

    printerUrl = mkOption {
      type = types.str;
      description = "Printer URL.";
    };

    logLevel = mkOption {
      type = types.enum ["DEBUG" "INFO" "WARNING" "ERROR"];
      default = "WARNING";
      description = "Logging level.";
    };

    defaultOrientation = mkOption {
      type = types.enum ["standard" "rotated"];
      default = "standard";
      description = "Default orientation.";
    };
  };

  config = lib.mkIf cfg.enable {
    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [cfg.port];

    systemd.services.brother_ql_web = let
      configFile = pkgs.writeText "brother_ql_web_config.json" (builtins.toJSON {
        SERVER = {
          PORT = cfg.port;
          HOST = cfg.host;
          LOGLEVEL = cfg.logLevel;
          ADDITIONAL_FONT_FOLDER = false;
        };
        PRINTER = {
          MODEL = cfg.printerModel;
          PRINTER = cfg.printerUrl;
        };
        LABEL = {
          DEFAULT_SIZE = "12";
          DEFAULT_ORIENTATION = cfg.defaultOrientation;
          DEFAULT_FONT_SIZE = 70;
          DEFAULT_FONTS = [
            {
              family = "Minion Pro";
              style = "Semibold";
            }
            {
              family = "Linux Libertine";
              style = "Regular";
            }
            {
              family = "DejaVu Serif";
              style = "Book";
            }
          ];
        };
        WEBSITE = {
          HTML_TITLE = "Label Designer";
          PAGE_TITLE = "Brother QL Label Designer";
          PAGE_HEADLINE = "Design your label and print it...";
        };
      });
    in {
      wantedBy = ["multi-user.target"];
      after = ["network-online.target"];
      description = "Brother QL WebUI";
      path = with pkgs; [fontconfig];
      environment = {
        VIEWS_PATH = "${./views}";
        STATIC_PATH = "${./static}";
      };
      serviceConfig = {
        Type = "idle";
        KillSignal = "SIGINT";
        ExecStart = "${pkgs.python3Packages.brother_ql_web}/bin/brother_ql_web ${configFile}";
        Restart = "on-failure";
        RestartSec = 10;

        # hardening
        DynamicUser = true;
        DevicePolicy = "closed";
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
          "AF_NETLINK"
          "AF_UNIX"
        ];
        DeviceAllow = [];
        NoNewPrivileges = true;
        PrivateDevices = true;
        PrivateMounts = true;
        PrivateTmp = true;
        PrivateUsers = true;
        ProtectClock = true;
        ProtectControlGroups = true;
        ProtectHome = true;
        ProtectKernelLogs = true;
        ProtectKernelModules = true;
        ProtectKernelTunables = true;
        ProtectSystem = "strict";
        BindPaths = [];
        MemoryDenyWriteExecute = true;
        LockPersonality = true;
        RemoveIPC = true;
        RestrictNamespaces = true;
        RestrictRealtime = true;
        RestrictSUIDSGID = true;
        SystemCallArchitectures = "native";
        SystemCallFilter = [
          "~@debug"
          "~@mount"
          "~@privileged"
          "~@resources"
          "~@cpu-emulation"
          "~@obsolete"
        ];
        ProtectProc = "invisible";
        ProtectHostname = true;
        ProcSubset = "pid";
      };
    };
  };
}
