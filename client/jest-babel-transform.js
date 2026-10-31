// Jest 23 bundles Babel 6, while this app uses Babel 7. Adapt the installed Babel directly.
const babel = require("@babel/core");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

module.exports = {
  process(source, filename) {
    return babel.transformSync(source, { filename, plugins: [require.resolve("babel-plugin-jest-hoist")] }).code;
  },
  getCacheKey(source, filename, config) {
    return crypto.createHash("sha256").update(source).update(filename).update(config)
      .update(process.env.NODE_ENV || "test")
      .update(fs.readFileSync(path.join(__dirname, "babel.config.js"))).digest("hex");
  }
};
