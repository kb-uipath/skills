#!/usr/bin/env node
const { dirname, join } = require("node:path");

(async () => {
  const { main } = await import("../../scripts/account-profile.mjs");
  const { digest } = await import("../../scripts/security.mjs");
  const { SfClient } = await import("../../scripts/sf-client.mjs");
  const fakeSf = join(dirname(__filename), "fake-sf");
  const fixedNow = process.env.SFAP_TEST_NOW
    ? () => new Date(process.env.SFAP_TEST_NOW)
    : undefined;
  process.exitCode = await main({
    dependencies: {
      sfPath: fakeSf,
      clientFactory: async (targetOrg) => new SfClient({
        commandSpec: {
          executable: fakeSf,
          fixedArgs: [],
          attestationDigest: digest({
            synthetic_test_runtime: fakeSf,
          }),
        },
        targetOrg,
      }),
      stateRoot: process.env.SFAP_TEST_STATE_ROOT || undefined,
      allowOfflineExecution: true,
      now: fixedNow,
    },
  });
})();
