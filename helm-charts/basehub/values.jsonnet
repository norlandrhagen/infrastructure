local hub_name = std.extVar('2I2C_VARS.HUB_NAME');

// Assume we are a staging hub if the word 'staging' is in the
// name of the hub.
local is_staging = std.member(hub_name, 'staging');

local emitDaskHubCompatibleConfig(basehubConfig) =
  // Handle legacy 'daskhub' type hubs
  // Note: This relies on `jsonnet` being called with absolute path to
  // the file, and the symlink from helm-charts/daskhub/values.jsonnet
  local isDaskHub = std.splitLimitR(std.thisFile, '/', 3)[2] == 'daskhub';

  if isDaskHub then { basehub: basehubConfig } else basehubConfig;

local jupyterhubHomeNFSResources = {
  quotaEnforcer: {
    path: '/export/%s' % hub_name,
    resources: {
      requests: {
        cpu: 0.02,
        memory: '20M',
      },
      limits: {
        cpu: 0.04,
        memory: '30M',
      },
    },
  },
  nfsServer: {
    resources: {
      requests: {
        cpu: 0.2,
        memory: '2G',
      },
      limits: {
        cpu: 0.4,
        memory: '6G',
      },
    },
  },
  prometheusExporter: {
    resources: {
      requests: {
        cpu: 0.02,
        memory: '15M',
      },
      limits: {
        cpu: 0.04,
        memory: '20M',
      },
    },
  },
};

local jupyterhubGroupsExporterResources = {
  // Memory resources chosen by querying PromQL "max(container_memory_working_set_bytes{name!='', pod=~'.*groups-exporter.*'})" over all hubs
  // CPU resources chosen by querying PromQL "max(irate(container_cpu_usage_seconds_total{name!='', pod=~'.*groups-exporter.*'}[5m]))" over all hubs
  resources: {
    requests: {
      cpu: 0.01,
      memory: '128Mi',
    },
    limits: {
      cpu: 0.1,
      memory: '256Mi',
    },
  },
};

emitDaskHubCompatibleConfig({
  'jupyterhub-home-nfs': if is_staging then {} else jupyterhubHomeNFSResources,
  'jupyterhub-groups-exporter': if is_staging then {} else jupyterhubGroupsExporterResources,
})
