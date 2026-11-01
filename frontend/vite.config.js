import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiOrigin = env.VITE_API_URL ? new URL(env.VITE_API_URL).origin : "";

  // Content-Security-Policy for the production build: only our own scripts and styles may run,
  // and the page may only talk to itself and the backend. This blunts XSS even if a bug slips in.
  // (Not applied in dev because Vite's hot-reload needs inline scripts.)
  const csp = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    `connect-src 'self' ${apiOrigin}`.trim(),
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");

  return {
    plugins: [
      react(),
      {
        name: "inject-csp",
        apply: "build",
        transformIndexHtml: (html) =>
          html.replace("</head>", `  <meta http-equiv="Content-Security-Policy" content="${csp}" />\n  </head>`),
      },
    ],
    server: {
      port: 5173,
      proxy: { "/api": "http://localhost:8000" }, // same-origin in dev, so no CORS needed
      headers: {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
      },
    },
  };
});
