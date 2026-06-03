import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Internal standalone build only. The public siderust.github.io benchmark page
// is rendered by Astro at /<locale>/benchmarks and this React app must not
// publish assets into the parent repository's public/lab directory.
const config = {
  base: "./",
  outDir: "dist",
};

export default defineConfig({
  base: config.base,
  plugins: [react(), tailwindcss()],
  build: {
    outDir: config.outDir,
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          plotly: ["plotly.js-dist-min", "react-plotly.js"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
