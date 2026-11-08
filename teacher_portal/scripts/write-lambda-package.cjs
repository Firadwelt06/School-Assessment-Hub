const fs = require("node:fs");
const path = require("node:path");

const outputDirectory = path.resolve(__dirname, "..", "dist");
fs.mkdirSync(outputDirectory, { recursive: true });
fs.writeFileSync(
  path.join(outputDirectory, "package.json"),
  JSON.stringify({ type: "commonjs" }),
);
