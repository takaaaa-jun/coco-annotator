module.exports = {
  presets: [["@vue/app", { modules: process.env.NODE_ENV === "test" ? "commonjs" : false }]]
};
