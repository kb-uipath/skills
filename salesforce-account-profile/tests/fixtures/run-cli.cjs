#!/usr/bin/env node
const { dirname, join } = require("node:path");

(async () => {
  const { main } = await import("../../scripts/account-profile.mjs");
  process.exitCode = await main({
    dependencies: { sfPath: join(dirname(__filename), "fake-sf") },
  });
})();
