module.exports = {
  baseUrl: process.env.VUE_APP_BASE_PATH || "/",
  devServer: {
    disableHostCheck: true,
    proxy: {
      "/api/*": {
        target: "http://webserver:5000/api/",
        changeOrigin: true,
        pathRewrite: {
          "^/api": ""
        }
      },
      "/socket.io*": {
        target: "http://webserver:5000/socket.io",
        changeOrigin: true,
        pathRewrite: {
          "^/socket.io": ""
        }
      }
    }
  },
  lintOnSave: undefined,
  runtimeCompiler: true
};
