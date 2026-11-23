const { createProxyMiddleware } = require('http-proxy-middleware');

// Mirror the production nginx history route during local development.
module.exports = function (app) {
  app.use(createProxyMiddleware('/terra/api/monitoring/history', {
    target: 'http://127.0.0.1:8081',
  }));
};
